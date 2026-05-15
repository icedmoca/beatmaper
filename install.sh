#!/usr/bin/env bash
# Beatmaper installer — sets up Python venv, pulls model files from the
# Hugging Face dataset icedmoca/beatmapmaker (same paths as ./models/), then Node deps.
# Re-runnable; idempotent.
# Env: BEATMAPER_SKIP_HF_MODELS=1 skip download; BEATMAPER_SYNC_HF_MODELS=1 force re-download;
#      BEATMAPER_HF_DATASET=user/repo override dataset id.
set -euo pipefail

cd "$(dirname "$0")"

say() { printf "\033[1;36m▶ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m! %s\033[0m\n" "$*"; }
err() { printf "\033[1;31m✗ %s\033[0m\n" "$*"; }

# --- Prereqs ---
need() {
  command -v "$1" >/dev/null 2>&1 || { err "Missing dependency: $1"; MISSING=1; }
}
MISSING=0
need python3
need node
need npm
need ffmpeg || true
if [ "${MISSING}" -eq 1 ]; then
  err "Install the missing tools above, then re-run ./install.sh"
  echo
  echo "Hints:"
  echo "  Arch:    sudo pacman -S python nodejs npm ffmpeg"
  echo "  Debian:  sudo apt install python3 python3-venv nodejs npm ffmpeg"
  echo "  macOS:   brew install python node ffmpeg"
  exit 1
fi
if ! command -v ffmpeg >/dev/null 2>&1; then
  warn "ffmpeg not found. The app still works, but song.egg conversion will fall back to a WAV-renamed file."
fi

# --- Python venv ---
say "Creating Python venv at .venv"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
say "Installing Python dependencies"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# --- Pre-trained models (Hugging Face dataset; repo paths match ./models/) ---
# https://huggingface.co/datasets/icedmoca/beatmapmaker
mkdir -p models/brain
HF_DATASET_REPO="${BEATMAPER_HF_DATASET:-icedmoca/beatmapmaker}"
if [[ "${BEATMAPER_SKIP_HF_MODELS:-}" == "1" ]]; then
  warn "BEATMAPER_SKIP_HF_MODELS=1: skipping Hugging Face download (you must supply models/ yourself)."
elif [[ "${BEATMAPER_SYNC_HF_MODELS:-}" != "1" ]] && [[ -f models/ranked_pattern_model.json ]] && [[ -f models/ranked_spacing_profile.json ]] && [[ -f models/brain/dataset_brain.json ]]; then
  say "Model files already under models/ (set BEATMAPER_SYNC_HF_MODELS=1 to re-download from ${HF_DATASET_REPO})"
else
  say "Downloading model files from Hugging Face dataset ${HF_DATASET_REPO}"
  hf download "${HF_DATASET_REPO}" \
    ranked_pattern_model.json \
    ranked_spacing_profile.json \
    training_report.json \
    training.log \
    brain/dataset_brain.json \
    --repo-type dataset \
    --local-dir models
fi

# --- Node deps ---
say "Installing Node dependencies (this can take a minute)"
npm install --no-audit --no-fund

say "Install complete."
echo
echo "Next: run ./run.sh    (or see SETUP.md)"
