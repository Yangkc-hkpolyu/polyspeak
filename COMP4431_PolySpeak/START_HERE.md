# Start here

This private package contains service configuration in `speaking.env`. Share it only with authorized recipients and keep the configuration out of public repositories.

On Windows, install Python 3.11 or 3.12, open a terminal in this folder and run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-speaking.txt
```

Keep the existing `speaking.env`. Double-click `start-speaking.bat`, leave the server window open and visit <http://127.0.0.1:8008/>. Allow microphone access when prompted. A network connection and valid service credentials are required for live speech and AI feedback.

If you edit the frontend, install Node.js and run `npm ci` and `npm run build` in the `frontend` folder. The browser needs WebGL and Web Audio for the Live2D avatar. Anya uses audio volume to animate the mouth after speech has been synthesized; it is not phoneme-level lip synchronization. The supplied model notice prohibits secondary redistribution and for-profit livestreaming. Review the included MODEL_USE_NOTICE.txt before use.

See `README.md` for more detail. A separate Azure Speech key is needed for pronunciation assessment. Scores are practice metrics, not official exam results.
