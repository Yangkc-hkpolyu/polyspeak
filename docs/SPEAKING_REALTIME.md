# PolyInterview realtime interaction port

Updated 2026-11-11. The selected scope is the original application's live avatar,
streaming speech input, and feature/aspect/proficiency feedback architecture.
The IELTS/TOEFL product, current Lisa/Nora visual and exam-room scene remain.
Neither the protected E: `backend/livetalking/` nor the C: project was edited.

## What actually runs

The browser creates an RTCPeerConnection with receive-only audio/video tracks
and the original `dh-state` DataChannel. `/api/speaking/live/offer` returns an
SDP answer and an opaque connection id. The video element receives a MediaStream
through `srcObject`; it does not receive an utterance MP4 URL.

`backend/speaking/vendor/livetalking/` contains the supplied original HumanPlayer,
PlayerStreamTrack, BaseReal, LipReal, BaseASR, LipASR and GPUInferenceScheduler,
plus the original audio feature functions/hyperparameters. Source and vendored
hashes are recorded in PROVENANCE.json. Package imports and the hosted TTS
constructor are adapted; the producer/consumer queues, render loop, inference
scheduler, 20 ms audio packets, 40 ms video frames and shared timestamps come
from the original project. The original library is read-only.

SpeakingLipReal overrides scene paste-back and base-frame selection so the new
desk occlusion, face masks and 13.28-second calm-motion cycle remain. It uses
the same original face inputs and corresponding coordinates. CUDA Wav2Lip is
retained. CPU mel extraction is selected by default because this portable
environment does not include a matching torchaudio CUDA installation; it is the
upstream-supported CPU path, not a change to mel parameters.

Speech output defaults to EdgeTTS with `en-US-JennyNeural`, matching the original
PolyInterview Amy English configuration. Chinese requests select
`zh-CN-XiaoxiaoNeural` separately; exam questions always use English. The original
application has separate language ports and injects the selected voice per
session. PolySpeak selects the voice per utterance within its existing service.
`SPEAKING_TTS_PROVIDER`, `SPEAKING_VOICE_EN`, and `SPEAKING_VOICE_ZH` apply to the
live path as well as the compatibility renderer. A mismatched Edge voice locale
is rejected, and provider failures never silently switch to another voice.

The previous live path was fixed to Qwen `Cherry` with `language_type=English`.
That multilingual voice supports English; it was not the original Chinese
endpoint, but it was a different synthesis provider and voice. Qwen remains an
explicit configuration alternative. Recognition and text generation still use
Qwen; changing the output voice does not change those services.
The optional Qwen voice is selected with `SPEAKING_REALTIME_TTS_VOICE` (default
`Cherry`), applying to both live and compatibility synthesis. It has no effect
on the default EdgeTTS language-specific voices.

Both sources yield PCM16/24 kHz, statefully resampled to 16 kHz. The complete
utterance audio is collected before its 320-sample packets enter LiveTalking,
matching the original configured EdgeTTS buffering boundary.
This adds startup wait but prevents cloud chunk gaps from becoming mid-sentence
silence. The video is still generated and transmitted over live WebRTC; no
utterance MP4 is built. Speech end events come from audio-track consumption,
and the same live track continues
with idle frames afterward. Disconnect, interruption and page unload close
sessions and stop the original producer threads. The model/scheduler are shared
across at most two local live connections.

The speaking adapter serializes each session's GPU batch completion so later
silent frames cannot overtake speech. Its producer retains approximately 480 ms
of queued media, instead of sleeping until the entire audio queue is empty.
Explicit interruption invalidates pending batches and their output. Rates stay
at 50 audio packets and 25 video frames per second. Vendor files are unchanged.

Leading/trailing near-silence supplied by TTS selects neutral rendering instead
of speech rendering; the audio itself is retained. This prevents the model's
future audio context from opening the mouth during the utterance's silent
padding. Inner pauses keep their normal lip animation. The `quiet_lip_frames`
counter records this separately from source underruns.

The existing job-status endpoint exposes connection counters and the latest
utterance's synthesis metrics, including provider, voice and language, not
historical metrics for each job. Run
`python scripts/verify_speaking_stream.py` against the local service to measure
synthetic speech continuity without microphone input. A passing connection test
alone is insufficient: inspect inserted silence, frame drops, source/playback
duration agreement and receive gaps.

The retired MP4 renderer and endpoints remain for compatibility and developer
comparisons; the active frontend does not use them as a silent fallback.

## Realtime speech input

Microphone audio uses an AudioWorklet at 16 kHz, sending PCM16 chunks over
`/api/speaking/sessions/{id}/stt?question_id=...`. The server relays to the same
`qwen3-asr-flash-realtime` model/protocol used by PolyInterview streamstt.
Interim text appears while recording; completed segments accumulate without
duplicate prefixes. The API key remains server-side.

The server assembles the original PCM into a WAV, saves its own final transcript,
and binds that recording to the current question. Mock answers use that server
transcript; client-edited text cannot replace it. Coach mode may edit text as
before. Duration/size limits, origin checks and pending-question ownership remain.
Interrupted ASR does not discard already received audio. The old upload-ASR
endpoint remains compatible, but the active recorder does not use it.

## Layered assessment and report

Each non-repeat answer starts parallel text-content and expression feature
evaluation. The original 13-feature structure remains: six text features,
three independent acoustic features and four candidate-video features.
Content definitions are adapted from job competence to speaking-task relevance,
reasoning and vocabulary; workplace/leadership judgements are not applied.

Feature evidence feeds four language-practice aspects: coherence, vocabulary,
grammar and task response. The original primary/secondary evidence weighting
guidance is retained. Safe span corrections provide an answer-polishing view.
New numbers, named entities and unsupported family-history additions are
rejected, and spelling/punctuation-only changes are not treated as spoken errors.
No server check can prove every semantic judgement correct; learners should
review model suggestions against their recording.

The original FinalEvaluationService's pure `_aggregate_features` and
`_aggregate_aspects` methods are copied into `vendor/evaluation_aggregation.py`.
The adapter excludes unavailable evidence before aggregation and displays missing
items as unavailable rather than zero. The final report contains overview,
feature summary, per-question evidence, expression revisions and JSON export;
the existing print flow remains available. The aggregate practice indicator is
the mean of evaluated text aspects, not an official IELTS/TOEFL score.

Azure acoustic features are used only if that service returns actual results.
No Azure credential is configured here, and candidate video is not collected;
those seven fields therefore remain unassessed. Text-model fine-tuning is still
unfinished. Offline demo and repetition-only reports do not fabricate scores.

## Local validation

- 27 automated checks passed, including existing exam protocol regressions,
  transcription merging, missing acoustic evidence, polishing grounding and
  original report aggregation with unavailable features.
- A real WebRTC loopback received audio/video, speech start/end and continuous
  idle. Closing left zero sessions in that isolated backend test.
- Edge received a real MediaStream and requested no utterance MP4 or legacy
  `/capture`/`question-media` path. Synthetic microphone audio produced 13 ASR
  updates before recording stopped. It is a synthetic fixture, not a learner.
- Real model requests produced feature/aspect layers, expression corrections,
  an exportable report and a 390-pixel layout without horizontal overflow or
  browser script errors. The new report is not calibrated against human raters.
- A timed TOEFL mock automatically recorded and submitted the server transcript;
  repeat text stayed hidden before submission and appeared afterward.

Evidence is under `speaking-runtime/qa/`: webrtc-backend.json,
realtime-browser.json, realtime-mock.json, realtime-layered-report.json and
matching UI images. Runtime evidence, recordings and local databases are not
included in public source archives.

## Deployment boundaries

Windows localhost with the available NVIDIA GPU was tested. Mac/MPS, Linux cloud,
internet NAT traversal and multiple simultaneous speakers have not been tested.
Current signalling uses local host ICE candidates. A public cloud deployment
requires STUN/TURN and corresponding network configuration; the existing cloud
Compose files are still a scaffold rather than a verified realtime deployment.
No cloud account was provisioned or billed during this work.

## Protocol references

- [Qwen realtime ASR client events](https://www.alibabacloud.com/help/en/model-studio/qwen-asr-realtime-client-events)
- [Qwen realtime TTS client events](https://www.alibabacloud.com/help/en/model-studio/qwen-tts-realtime-client-events)
- [aiortc API](https://aiortc.readthedocs.io/en/latest/api.html)

`scripts/port_speaking_realtime.py` is a maintainer helper requiring the full E:
source copy. The generated vendor files are already in the portable source
archive, so recipients do not need the protected original project at runtime.
