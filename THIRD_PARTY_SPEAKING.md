# Sources and third-party components

This is an authorized local copy of the user-provided PolyInterview application,
adapted into the PolySpeak speaking practice product. The untouched source of
the original application remains on C:. The speaking product uses its copied
Vue 2 toolchain and the existing Qwen speech / Wav2Lip approach. The additional
speaking state machine, task bank, feedback controls and interface are authored
for this course prototype.

Reference repository: https://github.com/yinlaetitia/JobInterview

`backend/speaking/vendor/wav2lip/model.py` derives from the reference LiveTalking
`wav2lip_v2.py`; the adjacent convolution definitions are retained. The supplied
Apache 2.0 LiveTalking license is in `backend/speaking/vendor/LIVE_TALKING_LICENSE`.
Upstream: https://github.com/lipku/LiveTalking and https://github.com/Rudrabha/Wav2Lip

The realtime port also vendors the supplied PolyInterview LiveTalking media
player, render/ASR classes and GPU scheduler under
`backend/speaking/vendor/livetalking/`, retaining Apache-2.0 headers. Its
PROVENANCE.json records protected-source hashes and adapted copies. Pure
feature/aspect aggregation methods from PolyInterview FinalEvaluationService
are retained separately; language-practice prompts, recording relay and report
adaptation are product-specific. See `docs/SPEAKING_REALTIME.md`.

The pretrained checkpoint has separate upstream provenance and usage terms;
its download manifest and hashes are in `speaking-models/source.json`. This local
prototype does not claim authorship of pretrained networks or hosted models.

The current Nora visual uses the supplied PolyInterview Lisa video-frame assets,
retaining their existing watermark and source attribution. Frame-cycle, face
preprocessing and paste-back operations adapt the original LiveTalking logic.
Nora is the assistant's product name; this visual is not claimed as a new,
independently generated person. Details are in `docs/SPEAKING_AVATAR.md`.

The fictional speaking-room backdrop was generated with built-in imagegen.
The offline avatar preparation uses the official Robust Video Matting
MobileNetV3 TorchScript release (GPL-3.0):
https://github.com/PeterL1n/RobustVideoMatting . This model is not distributed in
the portable archives and is not a serving-time dependency. Recurrent person
matting preserves the supplied video motion; LiveTalking attribution is
retained on the composed frames. Prompt: `docs/IELTS_ROOM_PROMPT.md`.

Official IELTS / ETS sample documents keep their original copyright notices.
Their links, hashes and study positions are in `speaking-resources/manifest.json`.
Complete documents are downloaded from official sites for local study and are
not included in the source ZIP. They are public practice resources, not claimed
to be past live exam papers. The in-app official excerpts are short and attributed;
the six full practice sets are original questions. IELTS and TOEFL trademarks
identify exam formats; this project is not an official test provider.

Hosted services: Qwen text, ASR and TTS from Alibaba Cloud Model Studio; optional
Azure Speech pronunciation assessment. Service accounts and credentials are not
distributed with the source package. Other dependencies retain their own licenses.
