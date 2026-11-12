"""
GPU 集中推理调度器：多会话共享每 GPU 单 worker，跨会话动态批处理 Wav2Lip forward。
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, replace
from queue import Empty, Full, Queue
from typing import Any, Dict, List, Tuple, Union

import numpy as np
import torch

from .logger import logger

DeviceKey = Union[int, str]

_RESULT_PUT_TIMEOUT_S = 0.1


def _put_result_queue_gpu(result_queue: Any, item: Any, session_id: int) -> None:
    try:
        result_queue.put(item, timeout=_RESULT_PUT_TIMEOUT_S)
    except Full:
        logger.warning(
            "GPUInferenceScheduler: result_queue full session=%s frame dropped",
            session_id,
        )


@dataclass(frozen=True)
class InferenceRequest:
    """单次会话一个 Wav2Lip batch 的推理任务。"""

    device_id: DeviceKey
    session_id: int
    mel_batch: np.ndarray
    img_batch: np.ndarray
    audio_frames: List[Tuple[Any, Any, Any]]
    frame_indices: List[int]
    result_queue: Any
    submit_ts: float = 0.0


class GPUInferenceScheduler:
    """
    每个 device 一条请求队列 + 一个 worker 线程；worker 积攒若干请求后拼接为 super_batch 做一次 forward。
    """

    def __init__(
        self,
        models_by_device: Dict[DeviceKey, torch.nn.Module],
        max_super_batch: int = 256,
        collect_timeout_ms: float = 5.0,
        queue_maxsize: int | None = None,
    ) -> None:
        self.models_by_device = models_by_device
        self.max_super_batch = max_super_batch
        self.collect_timeout_s = collect_timeout_ms / 1000.0
        _qmax = (
            queue_maxsize
            if queue_maxsize is not None
            else int(os.getenv("LT_SCHEDULER_QUEUE_MAXSIZE", "2000"))
        )
        self._queues: Dict[DeviceKey, Queue] = {
            dev: Queue(maxsize=_qmax) for dev in models_by_device
        }
        self._stop_event = threading.Event()
        self._workers: List[threading.Thread] = []

    def start(self) -> None:
        for device_id, model in self.models_by_device.items():
            t = threading.Thread(
                target=self._worker,
                args=(device_id, model),
                name=f"gpu-infer-worker-{device_id}",
                daemon=True,
            )
            t.start()
            self._workers.append(t)
            logger.info("GPUInferenceScheduler: worker started device=%s", device_id)

    def stop(self) -> None:
        self._stop_event.set()
        for t in self._workers:
            t.join(timeout=5.0)
        self._workers.clear()
        logger.info("GPUInferenceScheduler: all workers stopped")

    def submit(self, request: InferenceRequest) -> None:
        q = self._queues[request.device_id]
        req = replace(request, submit_ts=time.perf_counter())
        try:
            q.put(req, timeout=0.1)
        except Full:
            logger.warning(
                "GPUInferenceScheduler: queue full device=%s session=%s frames=%d dropped",
                req.device_id,
                req.session_id,
                req.mel_batch.shape[0],
            )
            batch_items = []
            for i in range(len(req.frame_indices)):
                pair = req.audio_frames[i * 2 : i * 2 + 2]
                batch_items.append((None, req.frame_indices[i], pair))
            _put_result_queue_gpu(req.result_queue, batch_items, req.session_id)

    @staticmethod
    def _torch_device_str(device_id: DeviceKey) -> str:
        if device_id == "cpu":
            return "cpu"
        if device_id == "mps":
            return "mps"
        if isinstance(device_id, int):
            return f"cuda:{device_id}"
        return str(device_id)

    def _worker(self, device_id: DeviceKey, model: torch.nn.Module) -> None:
        device_str = self._torch_device_str(device_id)
        if device_str.startswith("cuda") and torch.cuda.is_available():
            idx = int(device_str.split(":")[1]) if ":" in device_str else 0
            torch.cuda.set_device(idx)

        q = self._queues[device_id]

        while not self._stop_event.is_set():
            try:
                first = q.get(timeout=0.5)
            except Empty:
                continue

            requests: List[InferenceRequest] = [first]
            total_frames = first.mel_batch.shape[0]
            deadline = time.perf_counter() + self.collect_timeout_s

            while time.perf_counter() < deadline and total_frames < self.max_super_batch:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    break
                try:
                    req = q.get(timeout=min(remaining, 0.005))
                    requests.append(req)
                    total_frames += req.mel_batch.shape[0]
                except Empty:
                    break

            try:
                queue_depth = q.qsize()
                now_pc = time.perf_counter()
                wait_ms = 0.0
                for req in requests:
                    if req.submit_ts > 0.0:
                        w = (now_pc - req.submit_ts) * 1000.0
                        if w > wait_ms:
                            wait_ms = w

                super_mel = torch.FloatTensor(
                    np.concatenate([r.mel_batch for r in requests], axis=0)
                ).to(device_str)
                super_img = torch.FloatTensor(
                    np.concatenate([r.img_batch for r in requests], axis=0)
                ).to(device_str)

                t0 = time.perf_counter()
                with torch.no_grad():
                    super_pred = model(super_mel, super_img)
                forward_ms = (time.perf_counter() - t0) * 1000.0

                super_pred_np = super_pred.cpu().numpy().transpose(0, 2, 3, 1) * 255.0

                offset = 0
                for req in requests:
                    bs = req.mel_batch.shape[0]
                    pred_frames = super_pred_np[offset : offset + bs]
                    offset += bs
                    batch_items = []
                    for i, pred_frame in enumerate(pred_frames):
                        pair = req.audio_frames[i * 2 : i * 2 + 2]
                        batch_items.append((pred_frame, req.frame_indices[i], pair))
                    _put_result_queue_gpu(req.result_queue, batch_items, req.session_id)

                logger.info(
                    "POLYINTERVIEW_ANCHOR:gpu_infer_batch "
                    "device=%s sessions=%d frames=%d queue_depth=%d "
                    "forward_ms=%.2f wait_ms=%.2f",
                    device_id,
                    len(requests),
                    total_frames,
                    queue_depth,
                    forward_ms,
                    wait_ms,
                )

            except Exception as e:
                logger.error(
                    "GPUInferenceScheduler: inference error device=%s: %s",
                    device_id,
                    e,
                    exc_info=True,
                )
                for req in requests:
                    bs = req.mel_batch.shape[0]
                    batch_items = []
                    for i in range(bs):
                        pair = (
                            req.audio_frames[i * 2 : i * 2 + 2]
                            if len(req.audio_frames) > i * 2 + 1
                            else []
                        )
                        idx = (
                            req.frame_indices[i]
                            if i < len(req.frame_indices)
                            else 0
                        )
                        batch_items.append((None, idx, pair))
                    _put_result_queue_gpu(req.result_queue, batch_items, req.session_id)
