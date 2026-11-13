from fractions import Fraction

import av
import numpy as np

from backend.speaking.video_encoder import SpeakingH264Encoder


def test_bandwidth_changes_keep_encoder_and_frames_decodable():
    encoder = SpeakingH264Encoder()
    decoder = av.CodecContext.create("h264", "r")
    pixels = np.random.default_rng(4).integers(0, 255, (240, 320, 3), dtype=np.uint8)
    context = None
    decoded = []
    for i, bitrate in enumerate([1000000] * 4 + [600000] * 4 + [2000000] * 4):
        encoder.target_bitrate = bitrate
        frame = av.VideoFrame.from_ndarray(np.roll(pixels, i, axis=1), format="bgr24")
        frame.pts, frame.time_base = i * 3600, Fraction(1, 90000)
        nals = list(encoder._encode_frame(frame, i == 0))
        if context is None:
            context = encoder.codec
        assert encoder.codec is context, "Bandwidth feedback must not restart the encoder"
        for packet in decoder.parse(b"".join(b"\x00\x00\x00\x01" + nal for nal in nals)):
            decoded.extend(decoder.decode(packet))
    for packet in decoder.parse(b""):
        decoded.extend(decoder.decode(packet))
    decoded.extend(decoder.decode(None))
    assert len(decoded) == 12
    assert all((frame.width, frame.height) == (320, 240) for frame in decoded)
    assert sum(frame.key_frame for frame in decoded) == 1


def test_resolution_change_creates_correct_new_context():
    encoder = SpeakingH264Encoder()
    contexts = []
    for size in [(320, 240), (640, 360)]:
        frame = av.VideoFrame(*size, "yuv420p")
        frame.pts, frame.time_base = 0, Fraction(1, 90000)
        list(encoder._encode_frame(frame, True))
        contexts.append(encoder.codec)
        assert (encoder.codec.width, encoder.codec.height) == size
    assert contexts[0] is not contexts[1]
