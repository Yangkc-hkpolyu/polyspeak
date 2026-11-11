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

import asyncio
import json
import math
import torch
import numpy as np

import subprocess
import os
import time
import cv2
import glob
import resampy

import queue
from queue import Queue
from threading import Thread, Event
from io import BytesIO
import soundfile as sf
from typing import Any, Optional

from av import AudioFrame, VideoFrame

import av
from fractions import Fraction

from ...live_tts import StreamingTTS
from .logger import logger

from tqdm import tqdm
def read_imgs(img_list):
    frames = []
    logger.info('reading images...')
    for img_path in tqdm(img_list):
        frame = cv2.imread(img_path)
        frames.append(frame)
    return frames

def play_audio(quit_event,queue):        
    import pyaudio
    p = pyaudio.PyAudio()
    stream = p.open(
        rate=16000,
        channels=1,
        format=8,
        output=True,
        output_device_index=1,
    )
    stream.start_stream()
    # while queue.qsize() <= 0:
    #     time.sleep(0.1)
    while not quit_event.is_set():
        stream.write(queue.get(block=True))
    stream.close()


@torch.no_grad()
def _gpu_rgb_to_yuv420p(bgr_u8_hwc: torch.Tensor, pinned_buf: torch.Tensor) -> np.ndarray:
    h, w, c = bgr_u8_hwc.shape
    if c != 3:
        raise ValueError(f"期望 BGR 三通道，实际={bgr_u8_hwc.shape}")
    if h % 2 != 0 or w % 2 != 0:
        raise ValueError(f"YUV420P 要求宽高为偶数，实际=({h},{w})")

    bgr = bgr_u8_hwc.float()
    b = bgr[..., 0]
    g = bgr[..., 1]
    r = bgr[..., 2]

    y = (0.257 * r + 0.504 * g + 0.098 * b + 16.0).clamp(16.0, 235.0).to(torch.uint8)
    u_full = (-0.148 * r - 0.291 * g + 0.439 * b + 128.0).clamp(16.0, 240.0)
    v_full = (0.439 * r - 0.368 * g - 0.071 * b + 128.0).clamp(16.0, 240.0)
    u = u_full[::2, ::2].to(torch.uint8)
    v = v_full[::2, ::2].to(torch.uint8)

    flat = torch.cat([y.reshape(-1), u.reshape(-1), v.reshape(-1)], dim=0)
    n = int(flat.numel())
    if pinned_buf.numel() < n:
        raise ValueError(f"pinned_buf 容量不足: have={pinned_buf.numel()} need={n}")
    pinned_buf[:n].copy_(flat.cpu(), non_blocking=True)
    if bgr_u8_hwc.is_cuda:
        torch.cuda.current_stream(bgr_u8_hwc.device).synchronize()
    return pinned_buf[:n].numpy().reshape(h * 3 // 2, w)

class BaseReal:
    def __init__(self, opt):
        self.opt = opt
        self.sample_rate = 16000
        self.chunk = self.sample_rate // opt.fps # 320 samples per chunk (20ms * 16000 / 1000)
        self.sessionid = self.opt.sessionid

        self.tts = StreamingTTS(opt, self)

        self.speaking = False
        # DataChannel 推送 speaking 状态所需的去抖状态（由 process_frames 线程独占访问）
        self._dc_last_emitted_speaking: Optional[bool] = None
        self._dc_last_emit_monotonic: float = 0.0
        # 可由外部（SessionManager）注入；不注入时 _emit_speaking_state 静默跳过
        self._session_mgr: Optional[Any] = None

        self.recording = False
        self._record_video_pipe = None
        self._record_audio_pipe = None
        self.width = self.height = 0

        self.curr_state=0
        self.custom_img_cycle = {}
        self.custom_audio_cycle = {}
        self.custom_audio_index = {}
        self.custom_index = {}
        self.custom_opt = {}
        self.__loadcustom()

    def put_msg_txt(self,msg,datainfo:dict={}):
        self.tts.put_msg_txt(msg,datainfo)

    def put_audio_frame(self,audio_chunk,datainfo:dict={}): #16khz 20ms pcm
        self.asr.put_audio_frame(audio_chunk,datainfo)

    def attach_session_mgr(self, session_mgr: Any) -> None:
        """由 SessionManager 在 build_nerfreal 后注入，使 process_frames 可推 DataChannel 事件。"""
        self._session_mgr = session_mgr

    def _emit_speaking_state(self, now_speaking: bool, now_monotonic: float) -> None:
        """
        节流策略：仅状态翻转或距离上次推送 >=1s 时发送一次。
        process_frames 线程直接调用；DataChannel.send 必须在 session loop 上执行，
        故用 run_coroutine_threadsafe 投递，不阻塞渲染线程。
        """
        changed = self._dc_last_emitted_speaking != now_speaking
        elapsed = now_monotonic - self._dc_last_emit_monotonic
        if not changed and elapsed < 1.0:
            return
        sess = self._session_mgr
        if sess is None:
            return
        loop, dc = sess.get_session_dc_and_loop(self.sessionid)
        if loop is None or dc is None:
            return
        # DataChannel 需 readyState == 'open' 才能 send；关闭态静默跳过
        if getattr(dc, "readyState", None) not in ("open", None):
            return
        payload = json.dumps({
            "type": "speaking",
            "is_speaking": bool(now_speaking),
            "sessionid": self.sessionid,
            "ts_ms": int(time.time() * 1000),
        })

        def _send() -> None:
            try:
                dc.send(payload)
            except Exception as exc:
                logger.debug(
                    "POLYINTERVIEW_ANCHOR:dh_dc_send_error sessionid=%d err=%s",
                    self.sessionid,
                    exc,
                )

        try:
            loop.call_soon_threadsafe(_send)
        except Exception as exc:
            logger.debug(
                "POLYINTERVIEW_ANCHOR:dh_dc_schedule_error sessionid=%d err=%s",
                self.sessionid,
                exc,
            )
            return
        self._dc_last_emitted_speaking = now_speaking
        self._dc_last_emit_monotonic = now_monotonic

    def put_audio_file(self,filebyte,datainfo:dict={}): 
        input_stream = BytesIO(filebyte)
        stream = self.__create_bytes_stream(input_stream)
        streamlen = stream.shape[0]
        idx=0
        while streamlen >= self.chunk:  #and self.state==State.RUNNING
            self.put_audio_frame(stream[idx:idx+self.chunk],datainfo)
            streamlen -= self.chunk
            idx += self.chunk
    
    def __create_bytes_stream(self,byte_stream):
        #byte_stream=BytesIO(buffer)
        stream, sample_rate = sf.read(byte_stream) # [T*sample_rate,] float64
        logger.info(f'[INFO]put audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.info(f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]
    
        if sample_rate != self.sample_rate and stream.shape[0]>0:
            logger.info(f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            # 使用更高质量的重采样算法，减少电音
            stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate, filter='kaiser_best')

        return stream

    def flush_talk(self):
        self.tts.flush_talk()
        self.asr.flush_talk()

    def is_speaking(self)->bool:
        return self.speaking
    
    def __loadcustom(self):
        for item in self.opt.customopt:
            logger.info(item)
            input_img_list = glob.glob(os.path.join(item['imgpath'], '*.[jpJP][pnPN]*[gG]'))
            input_img_list = sorted(input_img_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
            self.custom_img_cycle[item['audiotype']] = read_imgs(input_img_list)
            self.custom_audio_cycle[item['audiotype']], sample_rate = sf.read(item['audiopath'], dtype='float32')
            self.custom_audio_index[item['audiotype']] = 0
            self.custom_index[item['audiotype']] = 0
            self.custom_opt[item['audiotype']] = item

    def init_customindex(self):
        self.curr_state=0
        for key in self.custom_audio_index:
            self.custom_audio_index[key]=0
        for key in self.custom_index:
            self.custom_index[key]=0

    def notify(self,eventpoint):
        logger.info("notify:%s",eventpoint)

    def start_recording(self):
        """开始录制视频"""
        if self.recording:
            return

        command = ['ffmpeg',
                    '-y', '-an',
                    '-f', 'rawvideo',
                    '-vcodec','rawvideo',
                    '-pix_fmt', 'bgr24', #像素格式
                    '-s', "{}x{}".format(self.width, self.height),
                    '-r', str(25),
                    '-i', '-',
                    '-pix_fmt', 'yuv420p', 
                    '-vcodec', "h264",
                    #'-f' , 'flv',                  
                    f'temp{self.opt.sessionid}.mp4']
        self._record_video_pipe = subprocess.Popen(command, shell=False, stdin=subprocess.PIPE)

        acommand = ['ffmpeg',
                    '-y', '-vn',
                    '-f', 's16le',
                    #'-acodec','pcm_s16le',
                    '-ac', '1',
                    '-ar', '16000',
                    '-i', '-',
                    '-acodec', 'aac',
                    #'-f' , 'wav',                  
                    f'temp{self.opt.sessionid}.aac']
        self._record_audio_pipe = subprocess.Popen(acommand, shell=False, stdin=subprocess.PIPE)

        self.recording = True
        # self.recordq_video.queue.clear()
        # self.recordq_audio.queue.clear()
        # self.container = av.open(path, mode="w")
    
        # process_thread = Thread(target=self.record_frame, args=())
        # process_thread.start()
    
    def record_video_data(self,image):
        if self.width == 0:
            print("image.shape:",image.shape)
            self.height,self.width,_ = image.shape
        if self.recording:
            self._record_video_pipe.stdin.write(image.tostring())

    def record_audio_data(self,frame):
        if self.recording:
            self._record_audio_pipe.stdin.write(frame.tostring())
    
    # def record_frame(self): 
    #     videostream = self.container.add_stream("libx264", rate=25)
    #     videostream.codec_context.time_base = Fraction(1, 25)
    #     audiostream = self.container.add_stream("aac")
    #     audiostream.codec_context.time_base = Fraction(1, 16000)
    #     init = True
    #     framenum = 0       
    #     while self.recording:
    #         try:
    #             videoframe = self.recordq_video.get(block=True, timeout=1)
    #             videoframe.pts = framenum #int(round(framenum*0.04 / videostream.codec_context.time_base))
    #             videoframe.dts = videoframe.pts
    #             if init:
    #                 videostream.width = videoframe.width
    #                 videostream.height = videoframe.height
    #                 init = False
    #             for packet in videostream.encode(videoframe):
    #                 self.container.mux(packet)
    #             for k in range(2):
    #                 audioframe = self.recordq_audio.get(block=True, timeout=1)
    #                 audioframe.pts = int(round((framenum*2+k)*0.02 / audiostream.codec_context.time_base))
    #                 audioframe.dts = audioframe.pts
    #                 for packet in audiostream.encode(audioframe):
    #                     self.container.mux(packet)
    #             framenum += 1
    #         except queue.Empty:
    #             print('record queue empty,')
    #             continue
    #         except Exception as e:
    #             print(e)
    #             #break
    #     for packet in videostream.encode(None):
    #         self.container.mux(packet)
    #     for packet in audiostream.encode(None):
    #         self.container.mux(packet)
    #     self.container.close()
    #     self.recordq_video.queue.clear()
    #     self.recordq_audio.queue.clear()
    #     print('record thread stop')
		
    def stop_recording(self):
        """停止录制视频"""
        if not self.recording:
            return
        self.recording = False 
        self._record_video_pipe.stdin.close()  #wait() 
        self._record_video_pipe.wait()
        self._record_audio_pipe.stdin.close()
        self._record_audio_pipe.wait()
        cmd_combine_audio = f"ffmpeg -y -i temp{self.opt.sessionid}.aac -i temp{self.opt.sessionid}.mp4 -c:v copy -c:a copy data/record.mp4"
        os.system(cmd_combine_audio) 
        #os.remove(output_path)

    def _paste_back_frame_tensor(self, pred_t: torch.Tensor, idx: int) -> np.ndarray:
        """
        TensorRT 路径下 pred 为 GPU 张量 [H,W,3] float；默认回退为 CPU numpy + paste_back_frame。
        LipReal 在存在 frame_gpu_cycle 时覆写为 GPU 合成。
        """
        arr = pred_t.detach().float().clamp(0.0, 255.0).cpu().numpy()
        arr_u8 = np.round(arr).astype(np.uint8)
        return self.paste_back_frame(arr_u8, idx)

    def _paste_back_frame_tensor_yuv(self, pred_t: torch.Tensor, idx: int):
        return None

    def mirror_index(self,size, index):
        #size = len(self.coord_list_cycle)
        turn = index // size
        res = index % size
        if turn % 2 == 0:
            return res
        else:
            return size - res - 1 
    
    def get_audio_stream(self,audiotype):
        idx = self.custom_audio_index[audiotype]
        stream = self.custom_audio_cycle[audiotype][idx:idx+self.chunk]
        self.custom_audio_index[audiotype] += self.chunk
        if self.custom_audio_index[audiotype]>=self.custom_audio_cycle[audiotype].shape[0]:
            self.curr_state = 1  #当前视频不循环播放，切换到静音状态
        return stream
    
    def set_custom_state(self,audiotype, reinit=True):
        print('set_custom_state:',audiotype)
        if self.custom_audio_index.get(audiotype) is None:
            return
        self.curr_state = audiotype
        if reinit:
            self.custom_audio_index[audiotype] = 0
            self.custom_index[audiotype] = 0

    def process_frames(self,quit_event,loop=None,audio_track=None,video_track=None):
        enable_transition = False  # 设置为False禁用过渡效果，True启用
        
        if enable_transition:
            _last_speaking = False
            _transition_start = time.time()
            _transition_duration = 0.1  # 过渡时间
            _last_silent_frame = None  # 静音帧缓存
            _last_speaking_frame = None  # 说话帧缓存
        
        if self.opt.transport=='virtualcam':
            import pyvirtualcam
            vircam = None

            audio_tmp = queue.Queue(maxsize=3000)
            audio_thread = Thread(target=play_audio, args=(quit_event,audio_tmp,), daemon=True, name="pyaudio_stream")
            audio_thread.start()

        last_idx = 0

        while not quit_event.is_set():
            try:
                result_item = self.res_frame_queue.get(block=True, timeout=1)
            except queue.Empty:
                continue

            result_items = result_item if isinstance(result_item, list) else [result_item]
            for res_frame,idx,audio_frames in result_items:
                combine_frame = None
                yuv_i420 = None

                if enable_transition:
                    # 检测状态变化
                    current_speaking = not (audio_frames[0][1]!=0 and audio_frames[1][1]!=0)
                    if current_speaking != _last_speaking:
                        logger.info(f"状态切换：{'说话' if _last_speaking else '静音'} → {'说话' if current_speaking else '静音'}")
                        _transition_start = time.time()
                    _last_speaking = current_speaking

                if audio_frames[0][1]!=0 and audio_frames[1][1]!=0: #全为静音数据，只需要取fullimg
                    self.speaking = False
                    self._emit_speaking_state(False, time.monotonic())
                    audiotype = audio_frames[0][1]
                    use_precomputed_silent_yuv = False
                    if self.custom_index.get(audiotype) is not None: #有自定义视频
                        mirindex = self.mirror_index(len(self.custom_img_cycle[audiotype]),self.custom_index[audiotype])
                        target_frame = self.custom_img_cycle[audiotype][mirindex]
                        self.custom_index[audiotype] += 1
                    else:
                        target_frame = self.frame_list_cycle[idx]
                        use_precomputed_silent_yuv = (
                            self.opt.transport != 'virtualcam'
                            and not enable_transition
                            and hasattr(self, "frame_yuv_list_cycle")
                        )

                    if use_precomputed_silent_yuv:
                        yuv_i420 = self.frame_yuv_list_cycle[idx]
                        if self.recording:
                            combine_frame = target_frame
                    elif enable_transition:
                        # 说话→静音过渡
                        if time.time() - _transition_start < _transition_duration and _last_speaking_frame is not None:
                            alpha = min(1.0, (time.time() - _transition_start) / _transition_duration)
                            combine_frame = cv2.addWeighted(_last_speaking_frame, 1-alpha, target_frame, alpha, 0)
                        else:
                            combine_frame = target_frame
                        # 缓存静音帧
                        _last_silent_frame = combine_frame.copy()
                    else:
                        combine_frame = target_frame
                else:
                    self.speaking = True
                    self._emit_speaking_state(True, time.monotonic())
                    try:
                        if res_frame is None:
                            current_frame = self.frame_list_cycle[last_idx].copy()
                        elif isinstance(res_frame, torch.Tensor):
                            if (
                                self.opt.transport != 'virtualcam'
                                and not enable_transition
                                and not self.recording
                            ):
                                yuv_i420 = self._paste_back_frame_tensor_yuv(res_frame, idx)
                            if yuv_i420 is None:
                                current_frame = self._paste_back_frame_tensor(res_frame, idx)
                        else:
                            current_frame = self.paste_back_frame(res_frame, idx)
                    except Exception as e:
                        logger.warning(f"paste_back_frame error: {e}")
                        current_frame = self.frame_list_cycle[last_idx].copy()
                        yuv_i420 = None
                    if yuv_i420 is None:
                        if enable_transition:
                            # 静音→说话过渡
                            if time.time() - _transition_start < _transition_duration and _last_silent_frame is not None:
                                alpha = min(1.0, (time.time() - _transition_start) / _transition_duration)
                                combine_frame = cv2.addWeighted(_last_silent_frame, 1-alpha, current_frame, alpha, 0)
                            else:
                                combine_frame = current_frame
                            # 缓存说话帧
                            _last_speaking_frame = combine_frame.copy()
                        else:
                            combine_frame = current_frame

                if self.opt.transport=='virtualcam':
                    if combine_frame is None:
                        combine_frame = self.frame_list_cycle[idx]
                    cv2.putText(combine_frame, "LiveTalking", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (128,128,128), 1)
                    if vircam==None:
                        height, width,_= combine_frame.shape
                        vircam = pyvirtualcam.Camera(width=width, height=height, fps=25, fmt=pyvirtualcam.PixelFormat.BGR,print_fps=True)
                    vircam.send(combine_frame)
                    self.record_video_data(combine_frame)
                else:  # webrtc：优先使用预计算/GPU 产出的 yuv420p，避免每帧 cvtColor
                    if yuv_i420 is None:
                        if combine_frame is None:
                            combine_frame = self.frame_list_cycle[idx]
                        cv2.putText(combine_frame, "LiveTalking", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (128,128,128), 1)
                        yuv_i420 = cv2.cvtColor(combine_frame, cv2.COLOR_BGR2YUV_I420)
                        self.record_video_data(combine_frame)
                    new_frame = VideoFrame.from_ndarray(yuv_i420, format="yuv420p")
                    video_track.put_frame_nowait((new_frame, None))

                for audio_frame in audio_frames:
                    frame,type,eventpoint = audio_frame
                    # 改进音频格式转换：裁剪到有效范围，减少量化噪声
                    # 裁剪到 [-1, 1] 范围，防止溢出
                    frame = np.clip(frame, -1.0, 1.0)
                    # 转换为 int16（32767 是 int16 的最大正值）
                    frame = (frame * 32767).astype(np.int16)

                    if self.opt.transport=='virtualcam':
                        audio_tmp.put(frame.tobytes()) #TODO
                    else: #webrtc
                        new_frame = AudioFrame(format='s16', layout='mono', samples=frame.shape[0])
                        new_frame.planes[0].update(frame.tobytes())
                        new_frame.sample_rate=16000
                        audio_track.put_frame_nowait((new_frame, eventpoint))
                    self.record_audio_data(frame)
                last_idx = idx
                if self.opt.transport=='virtualcam':
                    vircam.sleep_until_next_frame()
        if self.opt.transport=='virtualcam':
            audio_thread.join()
            vircam.close()
        logger.info('basereal process_frames thread stop') 
    
    # def process_custom(self,audiotype:int,idx:int):
    #     if self.curr_state!=audiotype: #从推理切到口播
    #         if idx in self.switch_pos:  #在卡点位置可以切换
    #             self.curr_state=audiotype
    #             self.custom_index=0
    #     else:
    #         self.custom_index+=1