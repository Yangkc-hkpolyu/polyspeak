"""Base-image timing independent of the 25 fps audio-conditioned mouth stream."""
from .vendor.livetalking_sequence import mirror_index


def build_motion_cycle(frame_count, repeats=None):
    if frame_count < 2:
        raise ValueError("The animated avatar requires at least two frames.")
    if repeats is None:
        repeats = [1] * frame_count
    if (len(repeats) != frame_count or
            any(type(value) is not int or not 1 <= value <= 8 for value in repeats)):
        raise ValueError("Avatar motion timing must use 1 to 8 video frames per source frame.")
    return tuple(index for step in range(2 * frame_count)
                 for index in [mirror_index(frame_count, step)]
                 for _ in range(repeats[index]))
