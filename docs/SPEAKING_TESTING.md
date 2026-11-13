# Speaking platform validation

Current status (2026-11-14): **audio/video synchronization is still unresolved**,
as confirmed by the user after the latest playback changes. Earlier automated
checks and estimated timing improvements are diagnostic results, not acceptance
of the lip-sync behavior. This checkpoint must not be presented as a verified
fix for the reported mouth-before-audio problem.

Latest verification: 2026-11-11 in the E: sharing checkout.

## Shared changes from the Live2D branch

Selected compatible changes from `live2d-ver` commit
`6032b87a6409e871ef586340b7f2cba99da387de` were integrated into the existing root
layout. This is a selective integration, not a merge of the complete branch.
It includes configurable Qwen voice selection, shared question-library/report
wording, and readability, mobile layout and keyboard-focus styles. The Live2D
renderer, assets, audio-only route replacement and nested project layout remain
on that branch. The current English validation, provenance labels, error
sanitization, EdgeTTS Jenny default and real-avatar synchronization fixes remain.

All 50 automated checks and the production frontend build passed. The browser
question-library check passed filtering, pagination, single-question practice,
source attribution, English-only UI and mobile overflow checks. The live WebRTC
check still reported `edgetts / en-US-JennyNeural / en`, zero source underruns,
zero dropped frames and no receive gap above 100 ms in its synthetic greeting.
The selected Qwen voice setting was verified with simulated protocol requests;
it does not replace the live EdgeTTS default.

## Mouth movement before audible speech

The Jenny greeting contains about 180 ms of near-silent leading PCM. Previously,
every supplied audio packet was classified as speech, including that padding.
Wav2Lip's forward-looking mel window could therefore animate the mouth before
the corresponding audio was audible. The idle source images were checked and
have closed mouths; there was no need to freeze the idle blink/head motion.

The adapter now identifies only the outer quiet extent of each complete
utterance using 20 ms RMS windows (threshold 0.0002 of full scale). Those packets
keep their original PCM, timestamps and events but select idle rendering.
Internal pauses and quiet speech inside the utterance retain normal animation.
Intentional visual silence is counted separately from missing source audio.

All 49 automated checks passed, including retained PCM duration, correct event
markers, quiet-consonant/internal-pause bounds and underflow classification.
The real greeting was received over WebRTC before and after this change and its
face crops were visually inspected. Relative to the first received audio frame
with RMS above 0.001, generated mouth movement began about 200 ms early before
the fix and about 20 ms early afterward (within one 40 ms video frame). These
are media-timestamp comparisons; they do not measure browser/device playout
latency. The 8.784-second source was retained, with zero underruns and frame drops.
Local JSON, WAV and annotated frame evidence is saved as
`speaking-runtime/qa/av-onset-before.*` and `av-onset-after.*`.

## English voice selection

The original Amy configuration uses EdgeTTS `en-US-JennyNeural` for English and
`zh-CN-XiaoxiaoNeural` for Chinese, with separate language service ports and a
per-session voice header. The previous PolySpeak live path bypassed its provider
setting and always used Qwen `Cherry` with `language_type=English`. Cherry is
documented as multilingual, so this was not a call to a Chinese-only endpoint;
it was a different provider/voice from the original English setup.

The active default and local configuration now select EdgeTTS Jenny. Live jobs
carry their language to synthesis, configuration rejects an Edge voice with the
wrong language prefix, and both live and compatibility paths honor the selected
provider. Failed synthesis does not silently switch voices.

All 46 automated checks passed. The new cases cover English/Chinese voice
selection, real MP3 decoding, complete-source buffering, Qwen language events,
environment settings, mismatched voice rejection, and provider failure.
An actual WebRTC greeting reported `edgetts / en-US-JennyNeural / en`, with
8.784 seconds of source audio and 8.795 seconds between playback events. Extra
underflow silence and audio/video drops were zero; maximum receive gaps were
35.7 ms for audio and 57.0 ms for video. The local evidence is
`speaking-runtime/qa/stream-timing-english-jenny.json` and its companion WAV.
This verifies the selected provider and continuity in that run, not a subjective
accent-quality comparison or a benchmark against the original running app.

## Continuous speech repair

The protected PolyInterview configuration selects EdgeTTS with batch size 8.
Its adapter collects the complete utterance before queueing audio. The earlier
PolySpeak Qwen adapter forwarded each arrival immediately; it did not preserve
that buffering boundary. Core vendor scheduler, lip processing and WebRTC code
otherwise match apart from imports. A deterministic test also reproduced a
later silent batch overtaking a pending speech batch.

The application adapter now collects complete audio, orders pending batches,
and retains playback reserve. Before the later English voice change, a Qwen
synthetic greeting produced 8.64 seconds
of source audio and 8.643 seconds between speech start/end. Its counters showed
zero input underruns, zero inserted speech silence and zero audio/video drops;
maximum receive gaps were 38.1 ms audio and 59.6 ms video. This is one local
measurement, not a guarantee for every network/device. The earlier baseline
also had regular packet timing, demonstrating why timing alone misses inserted
silence or batch-order defects. The original application was inspected, not
launched for a head-to-head performance benchmark.

Regression checks cover deferred batch ordering, interruption, retained media
reserve, source-underflow counting, full-utterance buffering and short utterances.
`scripts/verify_speaking_stream.py` saves a synthetic WAV and timing JSON under
the ignored runtime QA folder. It does not capture a participant microphone.

## English interface update

All 30 automated checks and the production frontend build passed. The English
catalog preserves 282 questions and their source provenance. Browser checks
covered the homepage, settings, history, question filters, pagination, empty
results, single-question practice and a 390-pixel layout, with no Chinese UI
text or horizontal overflow.

Live checks received the WebRTC avatar stream and incremental speech transcripts
from synthetic microphone audio. The first feedback attempt returned a retryable
failure; the existing session then produced an English report after one UI retry:
13 features, four assessed dimensions, and no Chinese generated commentary.
The full browser report/export script did not complete in that initial run;
the successful retry was verified through the saved report API. Original user
answers and evidence are preserved, even when the user supplies another language.

Use `verify_question_bank.cjs`, `verify_realtime_speaking.cjs` and
`verify_realtime_mock.cjs` for the current English app. The older
`verify_speaking_browser.cjs` is a historical MP4-era check and is excluded from
the current source package. Timed TOEFL capture has previous-version evidence
below; it was not rerun for this text update.

## Current realtime version

27 automated checks passed after the PolyInterview realtime port. Live Edge
checks verified WebRTC MediaStream playback, continuous idle after speech,
WebSocket transcription before microphone recording ended, layered feature/
aspect reports, grounded revisions, JSON export, mobile layout and no browser
script errors. A separate timed TOEFL mock verified automatic microphone
capture/submission and hidden repeat text. Synthetic audio was used throughout.

Current evidence and remaining unverified hardware/deployment paths are listed
in `docs/SPEAKING_REALTIME.md`. The historical MP4 checks below describe earlier
versions; they do not describe the active browser transport.

## Automated protocol checks

Command:

```powershell
.\.venv\Scripts\python.exe -s -m pytest speaking-tests -q --basetemp=speaking-runtime/pytest-temp
```

**21 checks passed.** Coverage includes the 7+4 TOEFL sequence, fixed mock interview
questions, hidden repeat targets, hidden task card before preparation, 60/120-second
IELTS long-turn settings, preparation not being reset by repeated requests,
answer-dependent IELTS Part 3 questions, bounded coaching follow-ups, duplicate
answer rejection, mock requiring audio and ignoring client-edited transcripts,
audio/question ownership, duration caps, transcript failure preserving original
audio, retryable report failures, verified quotes, rejecting nonfinite scores,
not grading fixed repetition text for lexical range, exam/set validation, local
origin checks and credential-free export. These tests use fake model and speech
services and make no claims about recognition or scoring accuracy.

The added question-bank checks cover unique question IDs and text, source/date
consistency, the 2026 TOEFL format, labelled translations and spelling edits,
bounded source excerpts, all collected questions being available as individual
coaching sessions, rejection of partial excerpts as full mocks, provenance saved
with answers, and generated follow-ups not inheriting institutional attribution.

## Expanded question-bank verification

The 2026-10-24 expansion contains 282 questions from 129 articles. A separate
source-text audit matched all 216 verbatim/edited excerpts against saved public
article text (reversing the declared spelling edits): zero mismatches. The other
66 questions are explicitly labelled translations or rephrasings of recollections;
their topics and question intentions were reviewed against the source articles.

`scripts/verify_question_bank.cjs` checked the running local app in Edge:
search, exam/year/stage/form filters, pagination, empty states, source links,
selection of a single coaching question, provenance labels in the practice room,
and a 390-pixel mobile viewport. No horizontal overflow or browser errors occurred.
This check blocks speech playback intentionally and consumes no external API
quota; it is not a new live speech or pronunciation validation. Evidence:
`speaking-runtime/qa/question-source-audit.json`, `question-bank-browser.json`,
and `question-bank-*.png`.

## Actual services and browser

The subsequent desk/motion correction passes 23 automated checks. Added timing
checks compare one minute of source-frame playback: the new schedule has fewer
than half as many closed-eye events while retaining five-frame closure duration.
The silent cycle is 13.28 seconds at 25 fps. A full-width foreground tabletop
occludes the examiner's lower torso in every source frame; face crops and
coordinates remain unchanged. The source remains a short looping recording.

Actual speech playback and return to idle passed with
`nora-v5-desk-calm-motion`; the recorded greeting job took 16.38 seconds in this
run. Browser evidence is retained separately in `speaking-runtime/qa/desk-motion-browser.json`
and `desk-motion-ui.png`; full-frame desk and timing checks are in
`speaking-runtime/background-preparation/desk-motion-check.json`.

The IELTS room scene update on 2026-10-25 passed 22 automated checks and the
production frontend build. The additional mask check ensures old room pixels
in rectangular face-crop corners are excluded without suppressing lip motion.
All 64 original face-input hashes remain unchanged. Source frame hashes were
checked before and after offline processing; the protected source was not edited.

Actual Qwen speech rendered and played with `nora-v4-ielts-room`, 1276 x 720,
25 fps. The recorded greeting job took 12.7 seconds in this run, including speech
generation; it is a single sample rather than a performance guarantee. Dynamic
idle playback, speech playback, return to idle, mobile layout and absence of
browser script errors passed. Evidence: `speaking-runtime/background-preparation/`
and `speaking-runtime/qa/dynamic-avatar-browser.json`, `dynamic-avatar-ui.png`.

On 2026-10-25 the photo-based avatar was replaced by the original dynamic-frame
logic. Added checks cover frame cycling, source-preserving paste-back, path
validation, cache invalidation and CUDA/MPS/CPU device selection. The local
upstream comparison found identical cycle indices, face tensors, paste-back
pixels and mel features. A real 3.92-second CUDA render used 64 distinct source
frames and output 98 frames at 25 fps, retaining visible head and eye motion.

`scripts/verify_dynamic_avatar_browser.cjs` checks actual silent idle playback,
speaking playback, automatic return to idle and mobile layout. Its selectors
distinguish the idle and speaking elements. Physical Mac rendering is untested.

`scripts/verify_speaking_live.py` created a **synthetic English speech fixture**
using the configured Qwen TTS service and recognized it with Qwen ASR. It was
not a human participant or an actual test attempt.

`scripts/verify_speaking_browser.cjs` used Edge with that synthetic microphone:

- Seven locally downloaded official PDFs opened successfully.
- Original Nora Wav2Lip video was generated and actually played.
- IELTS Part 2 preparation led to microphone recording and saved server-side ASR.
- Live text feedback was produced; returned quotes matched submitted text.
- Feedback JSON exported, refresh restored the report, and audio remained available.
- TOEFL official short repeat text stayed hidden before submission and appeared after it.
- A mock repeat recording ended and submitted automatically when its timer expired.
- Desktop and 390-pixel mobile layouts had no horizontal overflow or browser script errors.

A mobile timer overlap and a coaching submit event-handling error found during
browser verification were fixed before the passing rerun. Visual inspection also
revealed ungrounded full-answer expansions; those fields are no longer exposed.
The application only retains grounded quotes plus targeted suggestions.

A separate live Qwen follow-up check used a synthetic written answer about benches
around a playground. The returned question asked about that specific feature,
confirming that the live route consumed the submitted answer.

Evidence is under `speaking-runtime/qa/`: screenshots, speech-results.json,
browser-results.json, live-followup.json, feedback export and original-preservation.json.
These local artifacts and all recordings are excluded from the source package.

## Preservation and E: environment

Hashes of **2,181 original files** matched their pre-modification snapshot. The
C: repository's existing modified/untracked paths were unchanged. The protected
LiveTalking library was copied but not edited.

The active interpreter is the E: project `.venv`; disabling Python user packages
and checking loaded module paths found no C: module dependencies. The CUDA
PyTorch package is shared from the existing E: environment, as described in the
README. Node modules are a physical E: copy. The model checksum matches its manifest.

## Scope of the evidence

Azure pronunciation credentials are absent, so **Azure audio evaluation was not
tested live**. The UI correctly shows unavailable evidence rather than a score.
No fine-tuning, human examiner calibration, real learner study, production load
test or official score validation was performed. Timed browser checks used the
explicit classroom/demo option and a normal short repetition task; they do not
establish end-to-end official test-duration equivalence.

Frontend production build passed with the existing dependency lockfile. Its
Browserslist data produces an age notice; that did not prevent compilation.

## Desktop, recording-clock and video regression checks (2026-11-14)

- 65 Python tests passed, including delayed microphone setup, preparation timing,
  idempotent answer deadlines, decoder continuity across bitrate changes, and
  holding speech PCM until avatar warm-up completes.
- `scripts/verify_recording_timer.cjs` used the actual browser AudioWorklet with
  a synthetic microphone and mocked ASR socket. A failed connection left the
  deadline unset; a subsequent 3.5-second setup delay left all 30 seconds intact.
  Recording stopped after 29,986 ms. This validates timing, not cloud ASR accuracy.
  Run it against an isolated test server with `POLYSPEAK_TEST_URL` (default 8009).
- Desktop question-library navigation/filter/practice checks passed. Home and
  active practice screenshots were inspected at 1440 px; no new mobile work.
- Browser receive statistics changed from VP8 / 11 keyframes to H.264 / 3
  keyframes over comparable approximately 28-second idle samples (699 vs 709
  decoded frames, zero lost packets). Visual samples retained facial detail.
- The final live English greeting used EdgeTTS Jenny with the real lip model.
  Maximum arrival gaps were 57.0 ms audio / 84.4 ms video, with no gaps above
  100 ms, no dropped frames and no source underruns. Quiet lip markers remained
  active. The initial default H.264 experiment stalled and was superseded by
  the low-latency encoder and pre-speech warm-up; only the final run passed.

Local evidence: `speaking-runtime/qa/recording-timer.json`,
`browser-quality-before.json`, `browser-quality-final.json`,
`stream-timing-h264-ready-first.json`, `timer-recording.png`, and
`browser-final-15.png`. These measure one local computer, not cloud throughput
or perceptual quality across all networks.

Follow-up regression: 67 Python tests pass with paired media clocks and stale
frame rejection. Six explicit interruptions reproduced a 160 ms decoded lip
lead before the fix; `verify_av_sync.py paired-final` measured 20 ms afterwards.
The fresh real-adapter desktop test passed automatic report review, persisted
`model: local_lora` advice, export and cache reuse without another inference.

Run `node speaking-tests/test_live_avatar_client.cjs` for the complete-stream
startup regression. It delays each track in both possible arrival orders,
checks that no partial stream is attached/played, checks one unmuted binding,
and verifies that blocked or pending playback cannot trigger generated speech.
It also checks that stopping an idle avatar does not flush the media pipeline.
These client lifecycle tests do not measure physical lip/audio alignment.

A real in-app browser check used the current LiveAvatar client for three
consecutive English utterances and verified that the same complete, unmuted
stream remained attached throughout. In an isolated run, median receiver
playout differences were -35 ms, +2 ms and -1 ms. The first run overlapped
the Python regression suite and had much larger startup variance; that run is
not used as normal-playback evidence. Local reports are
`speaking-runtime/qa/browser-playout-combined.json` and
`browser-playout-combined-under-test-load.json`.
These are browser estimates, not a physical speaker/display recording or a
phoneme-by-phoneme assessment. The statistic follows the
[W3C estimatedPlayoutTimestamp definition](https://www.w3.org/TR/webrtc-stats/#dom-rtcinboundrtpstreamstats-estimatedplayouttimestamp).
