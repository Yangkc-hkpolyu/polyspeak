###############################################################################
#  Copyright (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking
#  email: lipku@foxmail.com
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import os
import pickle
import queue
import threading
import time
from queue import Queue
from threading import Event, Thread
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2
import glob
import numpy as np
import torch
import torch.nn.functional as F
import torch.multiprocessing as mp

from tqdm import tqdm

from .basereal import BaseReal, _gpu_rgb_to_yuv420p
from .gpu_inference_scheduler import InferenceRequest
from .lipasr import LipASR
from .logger import logger
from ..wav2lip import Wav2Lip

device = (
    "cuda"
    if torch.cuda.is_available()
    else (
        "mps"
        if (hasattr(torch.backends, "mps") and torch.backends.mps.is_available())
        else "cpu"
    )
)
print("Using {} for inference.".format(device))

# render 循环最小周期（秒）：防止说话时以 ~200Hz 全速轮询 mel 计算吃满 CPU。
# batch_size=16 对应 320ms 音频窗口；40ms 周期仍远快于实时，不引入明显延迟。
# LT_RENDER_LOOP_PERIOD_S=0 关闭节流，还原原行为。
_RENDER_LOOP_PERIOD_S = float(os.environ.get("LT_RENDER_LOOP_PERIOD_S", "0.04") or "0.04")
_GPU_YUV_ENABLED = os.environ.get("LT_GPU_YUV", "1").lower() not in (
    "0",
    "false",
    "no",
)


def _resolve_torch_device(torch_device: Optional[Union[int, str]]) -> str:
    if torch_device is None:
        return device
    if isinstance(torch_device, int):
        return f"cuda:{torch_device}"
    return str(torch_device)


def _load_checkpoint_cpu(checkpoint_path: str):
    return torch.load(checkpoint_path, map_location="cpu")


def load_model(path: str, torch_device: Optional[Union[int, str]] = None):
    tgt = _resolve_torch_device(torch_device)
    model = Wav2Lip()
    logger.info("Load checkpoint from: {}".format(path))
    checkpoint = _load_checkpoint_cpu(path)
    s = checkpoint["state_dict"]
    new_s = {}
    for k, v in s.items():
        new_s[k.replace("module.", "")] = v
    model.load_state_dict(new_s)
    model = model.to(tgt)
    return model.eval()


def load_avatar(avatar_id):
    avatar_path = f"./data/avatars/{avatar_id}"
    full_imgs_path = f"{avatar_path}/full_imgs"
    face_imgs_path = f"{avatar_path}/face_imgs"
    coords_path = f"{avatar_path}/coords.pkl"

    with open(coords_path, "rb") as f:
        coord_list_cycle = pickle.load(f)
    input_img_list = glob.glob(os.path.join(full_imgs_path, "*.[jpJP][pnPN]*[gG]"))
    input_img_list = sorted(
        input_img_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0])
    )
    frame_list_cycle = read_imgs(input_img_list)
    input_face_list = glob.glob(os.path.join(face_imgs_path, "*.[jpJP][pnPN]*[gG]"))
    input_face_list = sorted(
        input_face_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0])
    )
    face_list_cycle = read_imgs(input_face_list)

    return frame_list_cycle, face_list_cycle, coord_list_cycle


@torch.no_grad()
def warm_up(
    batch_size: int,
    model: torch.nn.Module,
    modelres: int,
    torch_device: Optional[Union[int, str]] = None,
):
    tgt = _resolve_torch_device(torch_device)
    logger.info("warmup model...")
    img_batch = torch.ones(batch_size, 6, modelres, modelres).to(tgt)
    mel_batch = torch.ones(batch_size, 1, 80, 16).to(tgt)
    model(mel_batch, img_batch)


def read_imgs(img_list):
    frames = []
    logger.info("reading images...")
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames


DeviceKey = Union[int, str]

_face_input_cache: Dict[int, np.ndarray] = {}
_frame_gpu_cache: Dict[Tuple[int, str], torch.Tensor] = {}
_avatar_preprocess_lock = threading.Lock()


def _device_id_cache_key(device_id: DeviceKey) -> str:
    if isinstance(device_id, int):
        return str(device_id)
    return str(device_id)


class LipReal(BaseReal):
    @torch.no_grad()
    def __init__(
        self,
        opt,
        avatar,
        scheduler: Any,
        device_id: DeviceKey,
    ):
        super().__init__(opt)
        self.fps = opt.fps
        self.batch_size = opt.batch_size
        self.idx = 0
        self.res_frame_queue = Queue(self.batch_size * 6)
        self.frame_list_cycle, self.face_list_cycle, self.coord_list_cycle = avatar
        self._scheduler = scheduler
        self._device_id = device_id
        self._infer_index = 0

        self.asr = LipASR(opt, self)
        self.asr.warm_up()

        self.render_event = mp.Event()
        face_list_id = id(self.face_list_cycle)
        frame_list_id = id(self.frame_list_cycle)
        dev_key = _device_id_cache_key(device_id)
        with _avatar_preprocess_lock:
            if face_list_id not in _face_input_cache:
                _face_input_cache[face_list_id] = self._precompute_face_inputs(
                    self.face_list_cycle
                )
            self._face_input_cache = _face_input_cache[face_list_id]
            gpu_key = (frame_list_id, dev_key)
            if gpu_key not in _frame_gpu_cache:
                _frame_gpu_cache[gpu_key] = self._build_frame_gpu_cycle(device_id)
            self.frame_gpu_cycle = _frame_gpu_cache[gpu_key]
        self.frame_yuv_list_cycle = [
            cv2.cvtColor(f, cv2.COLOR_BGR2YUV_I420) for f in self.frame_list_cycle
        ]
        self._yuv_pinned_pool: Optional[List[torch.Tensor]] = self._build_yuv_pinned_pool()
        self._yuv_pinned_idx = 0

    @staticmethod
    def _precompute_face_inputs(face_list: list) -> np.ndarray:
        """
        预计算每张人脸的 masked+concat+归一化+NCHW，避免每批次 copy/concat/transpose。
        返回 [N, 6, H, W] float32，与 _drain_inference_batches 中原 img_combined 语义一致。
        """
        rows: List[np.ndarray] = []
        for face in face_list:
            masked = np.array(face, copy=True)
            h_half = int(face.shape[0]) // 2
            masked[h_half:, :, :] = 0
            combined = np.concatenate((masked, face), axis=2).astype(np.float32) / 255.0
            rows.append(np.transpose(combined, (2, 0, 1)))
        return np.stack(rows, axis=0)

    def _build_frame_gpu_cycle(self, device_id: DeviceKey) -> Optional[torch.Tensor]:
        tdev = _resolve_torch_device(device_id)
        if not str(tdev).startswith("cuda"):
            return None
        try:
            frames_u8 = np.stack(
                [np.ascontiguousarray(f, dtype=np.uint8) for f in self.frame_list_cycle],
                axis=0,
            )
        except ValueError:
            logger.warning(
                "LipReal: avatar full_imgs 尺寸不一致，无法构建 frame_gpu_cycle，回退 CPU paste_back"
            )
            return None
        return torch.from_numpy(frames_u8).to(tdev, non_blocking=True).contiguous()

    def _build_yuv_pinned_pool(self) -> Optional[List[torch.Tensor]]:
        if self.frame_gpu_cycle is None:
            return None
        if not torch.cuda.is_available():
            return None
        h, w = self.frame_list_cycle[0].shape[:2]
        if h % 2 != 0 or w % 2 != 0:
            logger.warning(
                "LipReal: full frame 尺寸不是偶数，禁用 GPU->YUV 快速路径 shape=(%s,%s)",
                h,
                w,
            )
            return None
        yuv_size = h * w * 3 // 2
        return [
            torch.empty(yuv_size, dtype=torch.uint8, pin_memory=True),
            torch.empty(yuv_size, dtype=torch.uint8, pin_memory=True),
        ]

    def _mirror_index(self, index: int) -> int:
        size = len(self.coord_list_cycle)
        turn = index // size
        res = index % size
        if turn % 2 == 0:
            return res
        return size - res - 1

    def _drain_inference_batches(self) -> None:
        while True:
            try:
                mel_chunks = self.asr.feat_queue.get_nowait()
            except queue.Empty:
                break

            is_all_silence = True
            audio_frames = []
            for _ in range(self.batch_size * 2):
                try:
                    frame, audio_type, eventpoint = self.asr.output_queue.get(timeout=0.05)
                except queue.Empty:
                    frame = np.zeros(self.asr.chunk, dtype=np.float32)
                    audio_type = 1
                    eventpoint = None
                audio_frames.append((frame, audio_type, eventpoint))
                if audio_type == 0:
                    is_all_silence = False

            if is_all_silence:
                for i in range(self.batch_size):
                    idx = self._mirror_index(self._infer_index)
                    try:
                        self.res_frame_queue.put(
                            (None, idx, audio_frames[i * 2 : i * 2 + 2]),
                            timeout=0.1,
                        )
                    except queue.Full:
                        pass
                    self._infer_index += 1
                continue

            frame_indices = [
                self._mirror_index(self._infer_index + i) for i in range(self.batch_size)
            ]
            img_combined = np.ascontiguousarray(
                self._face_input_cache[frame_indices], dtype=np.float32
            )
            mel_batch_np = np.asarray(mel_chunks)
            mel_batch_np = np.reshape(
                mel_batch_np,
                [len(mel_batch_np), mel_batch_np.shape[1], mel_batch_np.shape[2], 1],
            )
            mel_batch_np = np.transpose(mel_batch_np, (0, 3, 1, 2)).astype(np.float32)

            request = InferenceRequest(
                device_id=self._device_id,
                session_id=self.opt.sessionid,
                mel_batch=mel_batch_np,
                img_batch=img_combined,
                audio_frames=audio_frames,
                frame_indices=frame_indices,
                result_queue=self.res_frame_queue,
            )
            self._scheduler.submit(request)
            self._infer_index += self.batch_size

    def paste_back_frame(self, pred_frame, idx: int):
        bbox = self.coord_list_cycle[idx]
        combine_frame = self.frame_list_cycle[idx].copy()
        y1, y2, x1, x2 = bbox
        res_frame = cv2.resize(pred_frame.astype(np.uint8), (x2 - x1, y2 - y1))
        combine_frame[y1:y2, x1:x2] = res_frame
        return combine_frame

    @torch.no_grad()
    def _paste_back_frame_tensor(self, pred_hwc: torch.Tensor, idx: int) -> np.ndarray:
        if self.frame_gpu_cycle is None:
            return super()._paste_back_frame_tensor(pred_hwc, idx)
        bbox = self.coord_list_cycle[idx]
        y1, y2, x1, x2 = bbox
        h = y2 - y1
        w = x2 - x1
        base = self.frame_gpu_cycle[idx].clone()
        pred = pred_hwc.to(base.device, non_blocking=True).float().clamp(0.0, 255.0)
        pred_nchw = pred.permute(2, 0, 1).unsqueeze(0)
        resized = F.interpolate(
            pred_nchw, size=(h, w), mode="bilinear", align_corners=False
        )
        patch = (
            resized.squeeze(0)
            .permute(1, 2, 0)
            .clamp(0.0, 255.0)
            .round()
            .to(torch.uint8)
        )
        base[y1:y2, x1:x2] = patch
        return base.detach().cpu().numpy()

    @torch.no_grad()
    def _paste_back_frame_tensor_yuv(self, pred_hwc: torch.Tensor, idx: int):
        if not _GPU_YUV_ENABLED:
            return None
        if self.frame_gpu_cycle is None or not self._yuv_pinned_pool:
            return None
        bbox = self.coord_list_cycle[idx]
        y1, y2, x1, x2 = bbox
        h = y2 - y1
        w = x2 - x1
        base = self.frame_gpu_cycle[idx].clone()
        pred = pred_hwc.to(base.device, non_blocking=True).float().clamp(0.0, 255.0)
        pred_nchw = pred.permute(2, 0, 1).unsqueeze(0)
        resized = F.interpolate(
            pred_nchw, size=(h, w), mode="bilinear", align_corners=False
        )
        patch = (
            resized.squeeze(0)
            .permute(1, 2, 0)
            .clamp(0.0, 255.0)
            .round()
            .to(torch.uint8)
        )
        base[y1:y2, x1:x2] = patch
        buf = self._yuv_pinned_pool[self._yuv_pinned_idx]
        self._yuv_pinned_idx = (self._yuv_pinned_idx + 1) % len(self._yuv_pinned_pool)
        return _gpu_rgb_to_yuv420p(base, buf)

    def render(self, quit_event, loop=None, audio_track=None, video_track=None):
        self.init_customindex()
        self.tts.render(quit_event)

        process_quit_event = Event()
        process_thread = Thread(
            target=self.process_frames,
            args=(process_quit_event, loop, audio_track, video_track),
        )
        process_thread.start()

        _render_t0 = time.perf_counter()
        while not quit_event.is_set():
            self.asr.run_step()
            self._drain_inference_batches()
            vq = video_track._queue.qsize() if video_track else 0
            aq = audio_track._queue.qsize() if audio_track else 0
            # 视频与音频背压必须同时满足：生产比例 1v:2a，消耗比例 40ms:20ms
            # 原 elif 导致视频背压 sleep=512ms 时音频净积压 +6.4 帧/轮，最终 wa→64（1280ms 延迟）
            # 改为独立 if 并取 max，确保两个队列都能充分消耗
            _bp_sleep_s = 0.0
            if vq >= 5:
                _bp_sleep_s = max(_bp_sleep_s, 0.04 * vq * 0.8)
            if aq >= 10:
                # 精确消耗：aq 帧 × 20ms/帧，防止音频积压超出 2:1 比例
                _bp_sleep_s = max(_bp_sleep_s, aq * 0.020)
            if _bp_sleep_s > 0:
                logger.debug("bp sleep vq=%d aq=%d sleep_s=%.3f", vq, aq, _bp_sleep_s)
                time.sleep(_bp_sleep_s)
                _render_t0 = time.perf_counter()
            elif _RENDER_LOOP_PERIOD_S > 0:
                _elapsed = time.perf_counter() - _render_t0
                _remaining = _RENDER_LOOP_PERIOD_S - _elapsed
                if _remaining > 0.002:
                    time.sleep(_remaining)
                _render_t0 = time.perf_counter()

        logger.info("lipreal thread stop")

        process_quit_event.set()
        process_thread.join()
