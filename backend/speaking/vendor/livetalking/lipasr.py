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
import time
import torch
import numpy as np

import queue
from queue import Queue
#import multiprocessing as mp

from .baseasr import BaseASR
from .logger import logger
from . import audio


class LipASR(BaseASR):

    def _melspectrogram_with_optional_gpu(self, inputs: np.ndarray) -> np.ndarray:
        use_gpu = os.environ.get("LT_MEL_USE_GPU", "1").lower() not in (
            "0",
            "false",
            "no",
        )
        mel_dev = None
        if use_gpu and torch.cuda.is_available() and self.parent is not None:
            did = getattr(self.parent, "_device_id", None)
            if isinstance(did, int):
                mel_dev = torch.device(f"cuda:{did}")
            elif isinstance(did, str) and did.startswith("cuda"):
                mel_dev = torch.device(did)
        if mel_dev is None:
            return audio.melspectrogram(inputs)
        try:
            if os.environ.get("LT_MEL_VERIFY", "0").lower() in ("1", "true", "yes"):
                if not getattr(self, "_lt_mel_verified", False):
                    self._lt_mel_verified = True
                    try:
                        mx, mn = audio.melspectrogram_compare_gpu_cpu(inputs, mel_dev)
                        logger.info(
                            "LT_MEL_VERIFY: gpu_vs_cpu max_abs_diff=%.6f mean_abs_diff=%.6f",
                            mx,
                            mn,
                        )
                    except Exception as ex:
                        logger.warning("LT_MEL_VERIFY 对比未执行或失败: %s", ex)
            return audio.melspectrogram_gpu(inputs, mel_dev)
        except Exception as e:
            logger.warning("melspectrogram_gpu 失败，回退 CPU mel: %s", e)
            return audio.melspectrogram(inputs)

    def flush_talk(self) -> None:
        """
        清空输入 PCM 队列，并排空 output_queue / feat_queue，避免 flush 后 mel 与
        output 帧计数错位导致 _drain_inference_batches 长时间阻塞。
        """
        super().flush_talk()
        while True:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break
        while True:
            try:
                self.feat_queue.get_nowait()
            except queue.Empty:
                break

    def run_step(self):
        ############################################## extract audio feature ##############################################
        # get a frame of audio
        _dht_t0 = None  # 提取本批次的 dht_t0 用于 T2 锚点
        for _ in range(self.batch_size*2):
            frame,type,eventpoint = self.get_audio_frame()
            self.frames.append(frame)
            # put to output（非阻塞：满时丢弃最旧帧，防止渲染线程因队列满而死锁）
            try:
                self.output_queue.put_nowait((frame, type, eventpoint))
            except queue.Full:
                try:
                    self.output_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.output_queue.put_nowait((frame, type, eventpoint))
                except queue.Full:
                    pass
            if _dht_t0 is None and isinstance(eventpoint, dict) and eventpoint.get('dht_t0'):
                _dht_t0 = eventpoint['dht_t0']
        # context not enough, do not run network.
        if len(self.frames) <= self.stride_left_size + self.stride_right_size:
            return
        
        inputs = np.concatenate(self.frames)  # [N * chunk]
        mel = self._melspectrogram_with_optional_gpu(inputs)
        #print(mel.shape[0],mel.shape,len(mel[0]),len(self.frames))
        # cut off stride
        left = max(0, self.stride_left_size*80/50)
        right = min(len(mel[0]), len(mel[0]) - self.stride_right_size*80/50)
        mel_idx_multiplier = 80.*2/self.fps 
        mel_step_size = 16
        i = 0
        mel_chunks = []
        while i < (len(self.frames)-self.stride_left_size-self.stride_right_size)/2:
            start_idx = int(left + i * mel_idx_multiplier)
            #print(start_idx)
            if start_idx + mel_step_size > len(mel[0]):
                mel_chunks.append(mel[:, len(mel[0]) - mel_step_size:])
            else:
                mel_chunks.append(mel[:, start_idx : start_idx + mel_step_size])
            i += 1
        try:
            self.feat_queue.put(mel_chunks, timeout=0.1)
        except queue.Full:
            logger.warning(
                "LipASR: feat_queue full session=%s, dropping mel batch",
                getattr(self.parent.opt, "sessionid", None) if self.parent else None,
            )
        else:
            # [DHT] T2: 第一批 mel 特征放入 feat_queue（即将进入 Wav2Lip 推理）
            if _dht_t0 and not getattr(self, '_dht_t2_logged_t0', None) == _dht_t0:
                self._dht_t2_logged_t0 = _dht_t0
                dt_ms = (time.perf_counter() - _dht_t0) * 1000
                logger.info(f'[DHT] T2_first_mel_batch dt_ms={dt_ms:.1f}')

        # discard the old part to save memory
        self.frames = self.frames[-(self.stride_left_size + self.stride_right_size):]
