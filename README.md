# beatmaper

Source: [github.com/icedmoca/beatmaper](https://github.com/icedmoca/beatmaper)

## Quick start

You need [Node.js](https://nodejs.org/) (LTS includes `npm`). Then run **one** command:

```bash
git clone https://github.com/icedmoca/beatmaper.git && cd beatmaper && npm start
```

`npm start` runs `npm install`, then shows a short **terminal menu**: pick **local website** (Vite in the browser) or **Electron** (desktop). Follow the URL or window it starts.

If you already have the repo:

```bash
cd beatmaper && npm start
```

## Other scripts

| Command | What it does |
|--------|----------------|
| `npm run dev` | Vite only (browser) |
| `npm run electron:dev` | Vite + Electron desktop |

## Build

```bash
npm run build
```

Preview the production build:

```bash
npm run preview
```

## Python backend and map models

The FastAPI server under `backend/` can use **derived** JSON under `models/` (spacing profile, pattern model, optional `brain/` bundle). Those files are **not** committed: they are large or machine-specific. See `models/README.md` for what each file is.

To rebuild from your own ranked map zips (that you have the rights to use):

1. Drop `*.zip` archives into `data/ranked_zips/`, or set `BEATMAPER_RANKED_ZIPS` to a folder of zips.
2. Run `python3 analyze_ranked_spacing.py` then `python3 train_ranked_patterns.py` (after `pip install -r requirements.txt` in a venv if you use one).

Details: `data/README.md`.

