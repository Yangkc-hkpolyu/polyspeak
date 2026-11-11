# Nora: PolyInterview-compatible dynamic avatar

Updated 2026-10-25. Nora is the product's assistant name. The current visual uses
the supplied PolyInterview Lisa frame sequence, which differs from its default
Amy character. It is reused material, not an independently created person.

## Current dynamic pipeline

The implementation loads matching full frames, preprocessed 256 x 256 face
crops and original per-frame coordinates. It follows LiveTalking's mirrored
frame cycle, lower-half masking, face-input concatenation, Wav2Lip v2 float32
inference and per-frame paste-back. The former fixed Haar crop, feathered ellipse
and sharpening are no longer used. Original head, eye and body motion stays in
the source frames. A silent dynamic cycle plays while waiting and after speech.

Adapted operations are in `backend/speaking/vendor/livetalking_sequence.py` with
Apache-2.0 attribution. The protected `backend/livetalking/` library and C: source
remain unedited. `scripts/verify_dynamic_avatar.py` compares the relevant pure
upstream methods: cycle indices, face inputs, paste-back pixels and mel features
match the original code.

The selected material has 64 frames at 1276 x 720, 25 fps, copied into
`speaking-models/avatars/nora/`. JSON coordinates and per-frame source hashes
are in `avatar.json`; the runtime does not deserialize uploaded pickle files.
The local preparation helper converts only the supplied upstream asset pickle.
`backend/speaking/assets/nora-idle.mp4` contains the silent waiting cycle.

## IELTS practice room scene

The current scene is a fictional speaking-test room with a light oak table,
clock, neutral walls, test booklet and recorder. It was generated with built-in
imagegen; the saved background and final prompt set are
`backend/speaking/assets/ielts-room.png` and `docs/IELTS_ROOM_PROMPT.md`.

`scripts/prepare_exam_room.py` processes all 64 original frames offline using
the official Robust Video Matting MobileNetV3 FP32 TorchScript release,
retaining its recurrent states. It removes disconnected matting mistakes such
as the old laptop, preserves opaque person pixels and stores a small person
mask for each face rectangle. These masks keep the old office out of predicted
face-crop corners when Wav2Lip pastes back. The face inputs and coordinates
remain identical to Lisa's source. Both idle and speech use the new scene.

The corrected scene uses `backend/speaking/assets/ielts-room-desk.png`.
Its tabletop is explicitly composited in front of the examiner from y=620
downward, hiding her lower torso rather than leaving her in front of the desk.
All 64 prepared frames carry this occlusion; it is not a poster-only correction.

The original 64-frame clip is only 2.56 seconds long. At its original timing,
the mirrored forward/back cycle repeats every 5.12 seconds, including the same
blink twice. The current base-motion schedule slows open-eye head/body motion
by repeating each source frame three times. Blink frames 37--49 retain their
native timing. The resulting idle cycle is 332 frames / 13.28 seconds.
`backend/speaking/motion.py` supplies exactly the same sequence to speaking
renders. Audio, mel sampling, mouth inference and output remain at 25 fps;
the browser does not slow down video or audio. The native mirrored-index helper
is unchanged, while production cadence now intentionally differs from upstream.
The underlying material still has limited gesture variety; a longer source
recording would be needed for a wider range of independent natural gestures.

The matting model is only an offline preparation tool. It is not shipped in the
portable asset archive or needed by the running application. The official
release is https://github.com/PeterL1n/RobustVideoMatting/releases/tag/v1.0.0.
To rebuild locally, place `rvm_mobilenetv3_fp32.torchscript` in
`speaking-runtime/background-preparation/`, then run
`python -s scripts/prepare_exam_room.py` for inspection and add `--apply` after
inspection. The existing protected source frames remain read-only.

The render version and avatar-manifest digest invalidate office-scene speech
caches. Idle and poster URLs also carry a scene version for browser caches.
Visible LiveTalking attribution is carried onto the new room.

Speaking now uses the original LiveTalking player/render loop and WebRTC media
tracks. Streaming PCM drives Wav2Lip while a continuous browser MediaStream
carries both speech and idle. The prior per-utterance MP4 renderer remains only
for compatibility; the active frontend no longer requests it. Details and
validation are in `docs/SPEAKING_REALTIME.md`. The scene and calm base-frame
timing remain as described above.

A 3.92-second audio fixture rendered 98 frames on CUDA in 9.12 seconds including
initialization in the recorded run. This single sample is not a throughput
benchmark or proof of real-time service. `auto` selects CUDA, Apple MPS, then CPU.
MPS selection is covered by unit tests; no physical Mac render was performed.
Mac startup uses `start-speaking.sh`, without Docker.

Evidence: `speaking-runtime/qa/dynamic-avatar-source-check.json`,
`dynamic-avatar-render.json`, `dynamic-avatar-browser.json` and matching images.

## Retired photo implementation (historical record)

The portrait was created with the built-in ImageGen tool on 2026-10-23.
Workspace asset: `backend/speaking/assets/nora.png`.
It is a new fictional interviewer, using a bob haircut, round glasses, navy blazer,
ivory blouse and a warm grey studio. Existing PolyInterview avatar images were
not used as source portraits.

### Retired portrait generation prompt

Use case: photorealistic-natural. Asset type: original fictional digital interviewer's source portrait for a lip-synced talking-head application. Generate one photorealistic, professional East Asian female interviewer, approximately 35 years old, with a neat chin-length dark bob haircut, thin understated round glasses, charcoal navy blazer over a light ivory blouse. Calm friendly professional expression, lips gently closed, full face completely unobstructed, looking directly into the camera, head upright and front-facing. Upper-body waist-up seated portrait, both shoulders and complete head visible, centered with moderate headroom, eye level webcam perspective. Clean warm-grey modern interview studio with very subtle out of focus architectural details, soft even frontal light across the whole face, natural realistic skin texture, no harsh shadows, restrained teal background accent. Landscape 4:3 or square composition. The face should occupy roughly the center 35 percent of the image width so it can be cropped for Wav2Lip, keep mouth perfectly visible, no microphone, no hands near face, no text, no logos, no watermark, no collage. This is an entirely fictional newly created person and must not resemble a known celebrity. Deliver a single continuous image, not a UI mockup.

### Retired rendering approach

The source portrait is preserved. For model input, OpenCV locates the face and
resizes the face crop to the checkpoint's 256 x 256 input. Audio is resampled to
16 kHz and transformed into normalized 80-band mel spectrograms. Wav2Lip predicts
mouth motion conditioned on these audio features. A feathered lower-face mask
blends predicted pixels into the original frame, preserving the eyes and glasses.
The detail revision on 2026-10-25 derives this model crop from a 1280 x 960
portrait rather than first reducing it to 768 x 576. On Nora's portrait, the
old face crop was only about 178 pixels wide and was enlarged to 256 pixels;
the revised crop has about 296 pixels before reduction to the model input.
The composite mask now covers the mouth and its immediate surroundings,
preserving more original cheek and jaw texture. Mild local sharpening and cubic
resampling improve edge contrast without changing the model's intrinsic detail.
FFmpeg encodes 1280 x 960, 25 fps H.264/AAC MP4 at CRF 18, compared with
768 x 576, 15 fps, CRF 23 before. A versioned media cache prevents old compressed
clips from being reused for new requests. Higher output resolution does not make
the mouth generator itself a high-resolution model.

This is genuine audio-conditioned neural lip sync. It is turn-based: each spoken
question is generated as a short video before playback. The single source image
does not supply natural idle head motion or eye blinks; those are outside this
simplified implementation.

An identical 3.92-second audio clip was rendered on CUDA for the before/after
visual comparison. The new clip contains 98 frames; the cold generation took
50.6 seconds including initialization. Higher frame rate and output size increase
generation cost, so this remains a turn-based demonstration rather than a
real-time avatar. Local evidence is in `speaking-runtime/qa/avatar-clarity-result.json`
and `avatar-mouth-comparison.png` (old on the left, revised on the right).

