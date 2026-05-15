# Beatmaper — setup

A song-to-Beat-Saber-map generator with a Three.js gameplay preview.

## Requirements
- Python 3.10+
- Node.js 18+ and npm
- ffmpeg (optional but recommended — used to encode the `song.egg` audio file
  inside the exported Beat Saber zip; without it, the app falls back to a
  WAV-renamed file)

## Install
```
./install.sh
```
This will:
1. Create a Python virtualenv in `.venv` and install the backend deps
   (`fastapi`, `uvicorn`, `numpy`, `python-multipart`).
2. Install the frontend Node deps with `npm install`.

## Run
```
./run.sh
```
Starts the backend on `http://127.0.0.1:8008` and the Vite dev server on
`http://127.0.0.1:5173`. Open the second URL in your browser. Ctrl+C stops both.

## Usage
1. Click **upload song** and pick an MP3/WAV/OGG.
2. Wait for analysis (a few seconds).
3. The page shows generated map stats and a download link for the Beat Saber zip.
4. Below that, the Three.js preview plays the generated chart synced to the song.

## What's in this bundle
- `backend/` — FastAPI service that analyses audio and builds the map.
- `src/` — React + Three.js frontend.
- `models/ranked_pattern_model.json` — pre-trained pattern model used by the backend.
- `models/ranked_spacing_profile.json` — pre-trained spacing profile.
- `models/brain/dataset_brain.json` — small derived feature cache.
- `index.html`, `package.json`, `package-lock.json` — frontend boilerplate.
- `requirements.txt` — backend Python deps.

Generated maps and preview projects are written to `generated_maps/` and
`generated_projects/` at runtime; those folders are created automatically.

## Troubleshooting
- **Frontend says "backend failed"**: make sure `./run.sh` is running and
  `http://127.0.0.1:8008/docs` loads.
- **`song.egg` is huge or invalid in the export**: install ffmpeg.
- **Port already in use**: kill whatever's on 8008 or 5173, or edit `run.sh`.
