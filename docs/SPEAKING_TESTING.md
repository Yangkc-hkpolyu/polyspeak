# Speaking platform validation

Latest verification: 2026-11-11 in the E: sharing checkout.

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
