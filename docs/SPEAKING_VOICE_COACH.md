# Optional fine-tuned voice advice

This integration selectively imports the experiment from `yukiiqwq245`, commit
`92d84575062ee177a0a5e6a3880d562cc2a69815` on `fine-tuned`. File provenance is in
`experiments/voice-coach/PROVENANCE.json`. The experiment's scripts, synthetic data,
training record and evaluation results are preserved there; those results have
not been independently reproduced by this integration.

The Qwen cloud examiner still handles questions, follow-ups and language feedback.
The optional Qwen2.5-1.5B LoRA worker only receives numeric recording measurements.
It never receives the recording, question, answer text or API keys as model input.
It does not score pronunciation, accents, IELTS bands or TOEFL performance.

## Using it

Complete a practice session, then choose **Review pace and pauses** under a saved
recording in the report. Measurements and advice are saved with that answer and
included in JSON export. Typed answers have no voice review. Existing recordings
can be reviewed without re-recording. Missing weights, rejected outputs or a slow
worker do not prevent the ordinary report from working; no cloud or base-model
answer is substituted and labelled as fine-tuned advice.

Pace uses the original saved ASR word count divided by the first-to-last detected
activity span. Audio energy is measured in 20 ms frames; interior quiet intervals
of at least 0.6 seconds count as pauses. Background sound and ASR mistakes can
affect these estimates. Leading and trailing silence are excluded from the span.
The model is an experiment trained on synthetic measurements, not teacher-labelled
speech or a validated pronunciation assessment.

## Setup

The complete `PolySpeak-Coursework-With-Models` folder supplied on 2026-11-13
contains the trained adapter and the base model. Both are installed on this
development computer. The trained adapter is now included in this repository at
`experiments/voice-coach/adapter`; the setup script downloads the larger base
from a pinned official Qwen revision. No separate handoff is needed for the adapter.
The delivered adapter contains 112 LoRA tensors, occupies 4,372,840 bytes and has
SHA-256 `911120929075507066c461d4f00a2a9b08b15792cb8c4a0d00bdcf632ab7792c`.
The base model SHA-256 is
`dd924a11b4c220f385b51ffa522daea7c9f3d850e31b162bb5661df483c6d3ee`.

Run using the same Python that runs PolySpeak:

```powershell
.\.venv\Scripts\python.exe -s scripts/setup_voice_coach.py
```

If the supplied folder already contains the base, add
`--base-dir "E:\Models\voice-coach-finetuned\base"` to copy it locally instead of
downloading it. The setup checks the base hash and adapter structure. Use
`--skip-deps` when the isolated packages are already installed; imports are still checked.

To use a different training output, supply `--adapter-dir "E:\Models\trained-adapter"`.
To prepare only dependencies, use `--deps-only` instead.
This installs pinned optional packages in `speaking-runtime/voice-coach-deps`,
without changing the avatar environment's installed packages. PyTorch and common
dependencies come from the existing speaking environment. Weights are downloaded
or copied into ignored `speaking-models/voice-coach/{base,adapter}` directories.
The source archive includes the 4.37 MB trained adapter; the 3.09 GB base is downloaded
separately. Base revision: `989aa7980e4cf806f80c7fef2b1adb7bc71aa306`.

Inference uses an isolated FP16 CPU subprocess with two threads and a 120-second
timeout. It runs only on explicit review requests after a session has completed.
CUDA is hidden from this subprocess to keep the avatar GPU available. CPU inference
uses more RAM than the original experiment's 4-bit GPU path and is slower;
the first verified local inference took 51.05 seconds, including loading.
Successful advice is saved, so reopening or exporting it does not rerun the model.
Real speech quality and broad reliability have not been established by these smoke
tests. This integration does not replace any speech, WebRTC or avatar modules.

`GET /api/speaking/voice-coach/status` reports setup readiness (file/package
presence, not proof of successful inference). `model_finetuned` on the existing
platform status still describes the main examiner, which is not fine-tuned.

## Integration validation, 2026-11-13

- 61 automated tests passed, including the existing media/language/turn protocol
  tests and 11 added voice-review cases. Subprocess success and timeout tests use
  controlled test doubles; they do not establish real model inference quality.
- Production Vue build passed. A separate test server with synthetic audio/ASR
  verified desktop/mobile display, English text, missing-adapter messaging,
  persistence, and report export. Screenshots were visually checked.
- Eight speech/avatar configuration and transport files remained byte-identical.
  A real EdgeTTS Jenny + WebRTC playback check completed with zero source
  underruns, zero audio/video drops, and no packet gaps above 100 ms; observed
  maximum audio/video gaps were 35.3/58.3 ms. The quiet-mouth handling remained
  active (53 quiet lip frames). This is a transport check, not a new perceptual
  lip-sync study.
- Optional inference package imports passed in the isolated package directory.
  The supplied adapter loaded on CPU and generated grounded advice for a synthetic
  120 words/minute, 10-second, zero-pause input. Both the real weights and the
  contributor's grounding filter were used. Explicit CPU placement for the PEFT
  loader prevents its automatic second dispatch from unexpectedly requesting
  disk offload. Other computers still show unavailable until their weights are installed.
- A second real-adapter run went through the browser using a synthetic recording
  and a fixed test transcript (120 words/minute, one detected pause). Generated
  advice, saving, reopening, JSON export, English UI and mobile layout passed.
  While that request was running, a separate live avatar test retained zero
  underruns and dropped audio/video frames, with maximum gaps of 46.1/64.3 ms
  and no gaps above 100 ms. Screenshots of the generated advice were inspected.
