# PolySpeak

PolySpeak is an IELTS and TOEFL speaking-practice application. This edition uses the Anya Live2D model supplied with the project and an English-language interface.

## Start locally

1. Install Python 3.11 or 3.12 and Node.js. In the project directory, create a virtual environment and install the Python dependencies:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\python -m pip install -r requirements-speaking.txt
   ```

2. The private package already contains `speaking.env`. Keep that file private; it contains service credentials. Configure your own Qwen credentials there if needed. Do not overwrite it with the example file.
3. To rebuild the browser interface, run `npm ci` followed by `npm run build` in the `frontend` directory. Node.js is not needed to run an already-built interface.
4. Double-click `start-speaking.bat` and open <http://127.0.0.1:8008/>. The browser needs WebGL, Web Audio and microphone permission for the corresponding features. Keep the server window open.

Choose an exam, mode, question set and section. A mock test records answers with timers; interactive practice also accepts typed answers. Review feedback and recordings when finished. Offline demo mode does not generate model scores. Speech and live model services require valid credentials and a network connection. Optional Azure credentials enable independent pronunciation assessment.

Anya is animated in the browser. Mouth movement follows the volume of the synthesized speech, rather than individual phonemes; a complete sentence is synthesized before playback. The supplied model notice prohibits secondary redistribution and for-profit livestreaming. Review the included MODEL_USE_NOTICE.txt before use. Practice metrics are not official IELTS or TOEFL scores.

Source material retains links and provenance. Some questions are excerpts, translations or rephrasings of recalled questions; these are labeled and are not represented as official exam questions. Original source documents and third-party notices remain in their original languages.
