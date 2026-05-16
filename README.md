# Beatmaper

> Beatmaper is a local web app that turns an uploaded audio file into a Beat Saber custom map ZIP. It includes:

[![Hugging Face Dataset](https://img.shields.io/badge/HuggingFace-BeatMapMaker-yellow?logo=huggingface&logoColor=white)](https://huggingface.co/datasets/icedmoca/beatmapmaker)


- A React/Vite frontend.
- A FastAPI Python backend.
- Audio analysis for tempo, beat peaks, bass peaks, vocal/mid peaks, and high-frequency accents.
- A learned ranked-pattern model trained from ranked Beat Saber maps.
- Multiple generation modes: Normal, Fun, Overkill, and Direct Instrument Mode.
- A Three.js preview that simulates blocks moving toward sabers in sync with the generated song audio.
- Exported Beat Saber map files: `Info.dat`, `ExpertStandard.dat`, and `song.egg`.

This project is designed to run locally on your own computer. It does not require an online API once dependencies are installed.

## What the app does

When you upload a song:

1. The backend receives the audio file.
2. If the file is not already WAV, the backend uses **ffmpeg** to convert it to WAV for analysis.
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
5. The backend converts the song to **song.egg**, which is an Ogg/Vorbis audio file with the `.egg` extension used by Beat Saber maps.
6. The backend writes a Beat Saber map folder and ZIP.
7. The frontend shows the generated stats and a Three.js gameplay preview.
8. You can download the generated ZIP and put it into your Beat Saber custom levels folder.

## Important limitation

This is an **experimental** generator. It can create valid Beat Saber-style files, but it is not guaranteed to make perfect human-authored maps. Beat Saber mapping is artistic and technical. You should still test maps in-game and refine them if you want polished results.

The current generator tries to be readable by default in **Normal** mode, then lets you increase complexity through **Fun** and **Overkill** settings.

---

Source: [github.com/icedmoca/beatmaper](https://github.com/icedmoca/beatmaper)

## Quick start

### One command (paste in Terminal)

**macOS, Linux, or [Git Bash](https://git-scm.com/downloads) on Windows** — clones/updates the app under `~/beatmaper` and runs **`npm start`** (install + Hugging Face models + **TUI** to pick browser or Electron):

```bash
curl -fsSL https://raw.githubusercontent.com/icedmoca/beatmaper/main/install.sh | bash
```

The installer reopens your **keyboard** as stdin for `npm start` (via `/dev/tty`), so the **1 / 2 / 0** menu still works when the script is piped from `curl`—otherwise stdin would be the script stream and the menu would exit immediately.

Optional: install somewhere else (directory must be empty or already this repo):

```bash
export BEATMAPER_DIR="$HOME/code/beatmaper"
curl -fsSL https://raw.githubusercontent.com/icedmoca/beatmaper/main/install.sh | bash
```

If you already cloned the repo, you can run the same script from any directory (it detects a checkout in the current folder) or:

```bash
bash install.sh
```

---

You need:

- [Node.js](https://nodejs.org/) (LTS includes `npm`)
- [Python](https://www.python.org/) **3.10+** with `pip`
- [**ffmpeg**](https://ffmpeg.org/) on your `PATH` (used to decode/convert audio)

The first time you run **`npm start`**, it creates a **local `.venv`**, then runs **`pip install -r requirements.txt`** inside it when FastAPI / uvicorn are missing (PEP 668 / “externally managed” systems like Arch are handled this way). You can still install manually anytime:

```bash
pip install -r requirements.txt
```

On Windows, if `python3` is missing, use `py -3 -m pip install -r requirements.txt`. The dev scripts try `python3`, then `python`, then `py -3`.

If you prefer not to use `install.sh`, clone and start manually:

```bash
git clone https://github.com/icedmoca/beatmaper.git && cd beatmaper && npm start
```

If you already cloned into `beatmaper`:

```bash
cd beatmaper && npm start
```

`npm start` runs `npm install`, installs Python API dependencies into **`.venv`** when needed, downloads the **Hugging Face** dataset [`icedmoca/beatmapmaker`](https://huggingface.co/datasets/icedmoca/beatmapmaker) into `models/` (skipped if files are already there), then shows a short **terminal menu**: pick **local website** (Vite in the browser) or **Electron** (desktop). **Both options start the FastAPI backend** on [http://127.0.0.1:8008](http://127.0.0.1:8008) together with the UI, so uploads work. Follow the URL or window it starts.

To re-download model files (for example after a dataset update): `npm run fetch-dataset`. Override repo/revision with `BEATMAPER_HF_DATASET` and `BEATMAPER_HF_REV`. Force refresh: `BEATMAPER_FORCE_DATASET=1 npm run fetch-dataset`.

| Command | What it does |
|--------|----------------|
| `npm run fetch-dataset` | Download / refresh `models/` from Hugging Face (`icedmoca/beatmapmaker`) |
| `npm run backend:dev` | FastAPI only at [http://127.0.0.1:8008](http://127.0.0.1:8008) (uses `scripts/run-backend.mjs` to pick `python3` / `python` / `py -3`) |
| `npm run dev` | **Vite + FastAPI** (browser UI + API for uploads) |
| `npm run electron:dev` | **Vite + FastAPI + Electron** (desktop) |

## Build

```bash
npm run build
```

Preview the production build:

```bash
npm run preview
```

## Python backend and map models

The FastAPI server under `backend/` reads **derived** JSON under `models/` (spacing profile, pattern model, `brain/dataset_brain.json`). Those files are **not** committed to Git; a fresh clone gets them automatically from Hugging Face when you run **`npm start`** (dataset [`icedmoca/beatmapmaker`](https://huggingface.co/datasets/icedmoca/beatmapmaker)) or anytime via **`npm run fetch-dataset`**.

To rebuild from your own ranked map zips (that you have the rights to use) instead of HF:

1. Drop `*.zip` archives into `data/ranked_zips/`, or set `BEATMAPER_RANKED_ZIPS` to a folder of zips.
2. Run `python3 analyze_ranked_spacing.py` then `python3 train_ranked_patterns.py` (after `pip install -r requirements.txt` in a venv if you use one).

Details: `data/README.md`.
