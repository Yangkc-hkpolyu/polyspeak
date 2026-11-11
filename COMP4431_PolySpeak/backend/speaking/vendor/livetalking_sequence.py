"""Sequence operations adapted from PolyInterview's unmodified LiveTalking.

Sources: lipreal.py (face inputs / paste-back), basereal.py (mirror_index).
Copyright (C) 2024 LiveTalking@lipku. Apache-2.0; see LIVE_TALKING_LICENSE.
The adapters accept explicit frame arrays instead of the upstream instance.
"""
import cv2
import numpy as np


def mirror_index(size, index):
    turn = index // size
    res = index % size
    if turn % 2 == 0:
        return res
    return size - res - 1


def prepare_face_inputs(face_list):
    rows = []
    for face in face_list:
        masked = np.array(face, copy=True)
        h_half = int(face.shape[0]) // 2
        masked[h_half:, :, :] = 0
        combined = np.concatenate((masked, face), axis=2).astype(np.float32) / 255.0
        rows.append(np.transpose(combined, (2, 0, 1)))
    return np.stack(rows, axis=0)


def paste_back_frame(pred_frame, idx, frame_list, coord_list):
    y1, y2, x1, x2 = coord_list[idx]
    combine_frame = frame_list[idx].copy()
    res_frame = cv2.resize(pred_frame.astype(np.uint8), (x2 - x1, y2 - y1))
    combine_frame[y1:y2, x1:x2] = res_frame
    return combine_frame
