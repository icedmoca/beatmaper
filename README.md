# Beatmaper

Beatmaper is a local web app that turns an uploaded audio file into a Beat Saber custom map ZIP. It includes:

- A React/Vite frontend.
- A FastAPI Python backend.
- Audio analysis for tempo, beat peaks, bass peaks, vocal/mid peaks, and high-frequency accents.
- A learned ranked-pattern model trained from ranked Beat Saber maps.
- Multiple generation modes: Normal, Fun, Overkill, and Direct Instrument Mode.
- A Three.js preview that simulates blocks moving toward sabers in sync with the generated song audio.
- Exported Beat Saber map files: `Info.dat`, `ExpertStandard.dat`, and `song.egg`.

This project is designed to run locally on your own computer. It does not require an online API once dependencies are installed.

---

## What the app does

When you upload a song:

1. The backend receives the audio file.
2. If the file is not already WAV, the backend uses `ffmpeg` to convert it to WAV for analysis.
3. The backend analyzes the waveform and extracts:
   - overall beats/onsets,
   - bass events,
   - vocal/mid-range events,
   - high-frequency accent events,
   - estimated BPM,
   - section intensity.
4. The generator creates Beat Saber notes using both:
   - direct audio events from the song,
   - learned note-pattern tendencies from ranked Beat Saber maps.
5. The backend converts the song to `song.egg`, which is an Ogg/Vorbis audio file with the `.egg` extension used by Beat Saber maps.
6. The backend writes a Beat Saber map folder and ZIP.
7. The frontend shows the generated stats and a Three.js gameplay preview.
8. You can download the generated ZIP and put it into your Beat Saber custom levels folder.

---

## Important limitation

This is an experimental generator. It can create valid Beat Saber-style files, but it is not guaranteed to make perfect human-authored maps. Beat Saber mapping is artistic and technical. You should still test maps in-game and refine them if you want polished results.

The current generator tries to be readable by default in Normal mode, then lets you increase complexity through Fun and Overkill settings.

---

## Project structure

```text
beatmaper/
├── backend/
│   └── main.py                  # FastAPI backend, audio analysis, map generation, export endpoints
├── models/
│   ├── ranked_pattern_model.json # Learned local pattern model used by the generator
│   └── training_report.json      # Summary of the training dataset/model
├── src/
│   ├── main.jsx                 # React app and Three.js preview
│   └── style.css                # App styling
├── index.html                   # Vite HTML entrypoint
├── package.json                 # Frontend dependencies/scripts
├── package-lock.json            # Locked npm dependency versions
├── requirements.txt             # Python backend dependencies
├── train_ranked_patterns.py     # Optional training script for rebuilding the model
└── README.md                    # This file
```

Generated maps, virtual environments, `node_modules`, logs, process IDs, and test exports are intentionally not included in the clean GitHub ZIP.

---

## Requirements

You need these installed:

### 1. Python

Recommended: Python 3.11 or newer.

The app was developed with Python 3.14, but 3.11+ should work.

Check:

```bash
python3 --version
```

### 2. Node.js and npm

Recommended: recent Node.js LTS or newer.

Check:

```bash
node -v
npm -v
```

### 3. ffmpeg

`ffmpeg` is required for audio conversion and for creating proper `song.egg` files.

Check:

```bash
ffmpeg -version
```

Install examples:

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

macOS with Homebrew:

```bash
brew install ffmpeg
```

Windows:

Install ffmpeg from <https://ffmpeg.org/download.html> and make sure it is on your PATH.

---

## Install

From inside the `beatmaper` folder:

```bash
cd beatmaper
```

### 1. Install Python backend dependencies

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate it:

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install backend packages:

```bash
pip install -r requirements.txt
```

### 2. Install frontend dependencies

```bash
npm install
```

---

## Run the app

You need two terminals: one for the backend and one for the frontend.

### Terminal 1: backend

From the `beatmaper` folder, activate the Python environment first:

```bash
source .venv/bin/activate
```

Then run:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8008
```

Backend URL:

```text
http://127.0.0.1:8008
```

Health check:

```text
http://127.0.0.1:8008/health
```

If everything is working, health should show `ok: true` and `modelLoaded: true`.

### Terminal 2: frontend

From the `beatmaper` folder:

```bash
npm run dev -- --port 5174
```

Open:

```text
http://127.0.0.1:5174
```

---

## How to use

1. Open the frontend in your browser.
2. Choose a generation preset:
   - **Normal**: readable, spaced, vocal/mid-driven by default.
   - **Fun**: denser and more energetic.
   - **Overkill**: much denser, faster, and more aggressive.
3. Optionally adjust advanced controls:
   - overall density,
   - stream aggression,
   - note jump speed,
   - jump offset,
   - max simultaneous blocks,
   - difficulty label,
   - seed,
   - bombs/walls/lights,
   - Direct Instrument Mode.
4. Upload an audio file.
5. Wait for analysis and generation to complete.
6. Preview the generated gameplay in the Three.js simulation.
7. Press **Download Beat Saber ZIP**.
8. Install the ZIP as a custom Beat Saber map.

---

## Generation controls explained

### Normal / Fun / Overkill presets

The preset buttons configure multiple generation settings at once.

- **Normal** is intentionally spaced apart. It tries to follow vocal/mid-range peaks and important musical events without spamming blocks.
- **Fun** increases density and adds more movement.
- **Overkill** allows more simultaneous notes, faster note jump speed, and more aggressive pattern usage.

The selected preset glows blue in the UI.

### Density

Controls how many notes are allowed overall.

Low density means fewer notes and bigger gaps.
High density means more blocks and more frequent events.

### Stream aggression

Controls how often the generator adds quick follow-up notes or short runs.

For Normal mode, keep this low.
For Overkill, increase it.

### Note Jump Speed / NJS

A Beat Saber setting that controls how fast notes approach the player.

Higher NJS feels faster and more intense.
Lower NJS gives more time to react.

### Jump offset

Controls spawn/read timing. Positive values generally make notes appear earlier/farther away.

### Max simultaneous blocks

Limits how many blocks can exist at the same timestamp.

Normal mode defaults to 1 for readability.
Fun and Overkill can allow doubles or larger stacks.

### Seed

The generator uses randomness. The seed makes generation repeatable.

Same song + same settings + same seed should produce the same general result.

### Direct Instrument Mode

Direct Instrument Mode is an abstract/conductor mode.

Instead of making a standard dense Beat Saber chart, it maps musical roles into gesture-like blocks:

- bass becomes grounded low cues,
- vocal/mid becomes main phrase movement,
- highs become upper flick accents.

This is useful if you want the map to feel more like conducting or playing along with instruments instead of maximizing Beat Saber difficulty.

---

## Three.js preview controls

After a map generates, the preview section appears.

Controls:

- **Play song**: plays the generated `song.egg` audio and syncs note movement to the audio time.
- **Pause song**: pauses the preview.
- **Restart synced**: resets the song and map preview to the beginning.
- **Fly mode**: detaches the camera.

Fly mode controls:

```text
WASD        move around
Mouse       look around
Space       move up
Shift       move down
Ctrl        faster movement
Esc         release mouse pointer
Double Space toggle fly mode
```

The preview is only a visual simulator. The actual exported map is the ZIP generated by the backend.

---

## Output files

Generated maps are saved into:

```text
generated_maps/
```

A generated map folder contains files like:

```text
Info.dat
ExpertStandard.dat
song.egg
```

The downloadable ZIP contains those files.

### What is `song.egg`?

Beat Saber custom maps usually use `.egg` audio. Internally, this is Ogg/Vorbis audio with the `.egg` extension.

The backend uses ffmpeg to convert uploaded audio to this format.

---

## Installing generated maps into Beat Saber

The exact location depends on your Beat Saber install.

Typical PC path:

```text
Beat Saber/Beat Saber_Data/CustomLevels/
```

You can either:

1. unzip the generated ZIP into a new folder inside `CustomLevels`, or
2. use a mod manager/custom songs tool that accepts Beat Saber map ZIPs.

Then launch Beat Saber and check Custom Levels.

---

## API endpoints

### `GET /health`

Checks backend status and model loading.

Example:

```bash
curl http://127.0.0.1:8008/health
```

### `POST /analyze`

Uploads audio and generates a map.

Example:

```bash
curl -F "file=@song.wav" http://127.0.0.1:8008/analyze
```

You can also pass generation settings as form fields:

```bash
curl \
  -F "file=@song.wav" \
  -F "density=0.48" \
  -F "streams=0.18" \
  -F "directInstrument=false" \
  http://127.0.0.1:8008/analyze
```

### `GET /download/{zip_name}`

Downloads a generated map ZIP.

### `GET /audio/{folder_name}`

Serves generated preview audio for the frontend simulation.

---

## Optional: retraining the model

The included model is already trained. You do not need to retrain it to run the app.

If you have a folder of Beat Saber map ZIPs and want to rebuild the learned pattern model, use:

```bash
python3 train_ranked_patterns.py
```

The training script currently expects a ranked map ZIP corpus at:

```text
/home/dad/Desktop/beat/pro/all_ranked_zips
```

If your corpus is somewhere else, edit the `CORPUS` path inside `train_ranked_patterns.py`.

Training writes:

```text
models/ranked_pattern_model.json
models/training_report.json
```

---

## Troubleshooting

### Backend says `modelLoaded: false`

Make sure this file exists:

```text
models/ranked_pattern_model.json
```

If it is missing, either restore it from the ZIP or retrain the model.

### Upload fails

Check the backend terminal for errors.

Common causes:

- ffmpeg is not installed,
- unsupported/corrupt audio file,
- Python dependencies were not installed,
- backend is not running on port `8008`.

### Browser says failed to fetch

Usually means the backend is not running.

Check:

```text
http://127.0.0.1:8008/health
```

### Preview is black or frozen

Try Firefox or a browser with WebGL enabled.

Also check the browser console. The preview uses Three.js/WebGL.

### The generated map is too sparse

Use the Fun preset, increase density, increase streams, or allow max simultaneous blocks of 2 or 3.

### The generated map is too dense

Use Normal preset, lower density, lower streams, and set max simultaneous blocks to 1.

### The map does not appear in Beat Saber

Verify the ZIP contains:

```text
Info.dat
ExpertStandard.dat
song.egg
```

Also verify `Info.dat` references `song.egg` as the song filename.

---

## Development notes

Frontend:

```bash
npm run dev -- --port 5174
```

Backend:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8008
```

Build frontend:

```bash
npm run build
```

The frontend expects the backend at:

```text
http://127.0.0.1:8008
```

---

## License

No license has been chosen yet. Add a `LICENSE` file before publishing publicly if you want others to know what they are allowed to do with the code.
