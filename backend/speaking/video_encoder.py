"""Low-latency H.264 adapter for the speaking service's aiortc senders.

Keep aiortc's packetization, feedback and codec fallback. Configure libx264
before its normal encode path so changing bandwidth does not recreate the
encoder and replace a clear reference image with a coarse new keyframe.
"""
from fractions import Fraction

import av
from aiortc.codecs.h264 import H264Encoder
from aiortc import rtcrtpsender


class SpeakingH264Encoder(H264Encoder):
    def _encode_frame(self, frame, force_keyframe):
        if self.codec is None or (self.codec.width, self.codec.height) != (frame.width, frame.height):
            self.codec = av.CodecContext.create("libx264", "w")
            self.codec.width, self.codec.height = frame.width, frame.height
            self.codec.pix_fmt = "yuv420p"
            self.codec.framerate = Fraction(25, 1)
            self.codec.time_base = Fraction(1, 25)
            self.codec.thread_count = 2
            self.codec.profile = "Baseline"
            self.codec.options = {"level": "31", "preset": "veryfast", "tune": "zerolatency"}
            self.codec.bit_rate = self.target_bitrate
        elif abs(self.target_bitrate - self.codec.bit_rate) / self.codec.bit_rate > 0.1:
            # libx264 reconfigures ABR in place; keep motion/reference history.
            self.codec.bit_rate = self.target_bitrate
        return super()._encode_frame(frame, force_keyframe)


def install_speaking_encoder():
    """Override only H.264 creation inside this dedicated service process."""
    original = rtcrtpsender.get_encoder
    if getattr(original, "speaking_encoder", False):
        return

    def create(codec):
        return SpeakingH264Encoder() if codec.mimeType.lower() == "video/h264" else original(codec)

    create.speaking_encoder = True
    rtcrtpsender.get_encoder = create
