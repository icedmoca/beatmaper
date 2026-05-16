---
language:
- en
pretty_name: "Beat Saber ranked maps — derived statistics & pattern priors"
license: other
tags:
- beatsaber
- beat-saber
- rhythm-game
- game-data
- json
- procedural-generation
---

# Dataset / model card (Beat Saber ranked maps)

This folder holds **dataset-style artifacts** produced by a **Python** training / aggregation pipeline over **3,000+ different Beat Saber song maps** (ranked community maps, parsed from many map archives). This README is the **Hugging Face dataset card**; it explains what each file is, how it was built, and what consumers should expect.

> **Scope:** These files summarize **note timing, density, co-note patterns, and style priors** derived from real ranked maps—not raw audio or full map zips. Downstream tools can treat them as a **compact statistical prior** for generation, analysis, or evaluation.

> **In this Git repository:** the large JSON outputs and training logs are **not committed** (see the repo root `.gitignore`). After clone, generate them locally with `analyze_ranked_spacing.py` / `train_ranked_patterns.py`, or ship them via releases / Git LFS as you prefer.

> **License:** YAML uses `license: other` because rights depend on **original map / platform terms**. This repo holds **derived statistics and models** only. Replace with a concrete SPDX id (for example `MIT` for your scripts) after your own legal review.

---

## Training context

| Item | Detail |
|------|--------|
| **Pipeline** | Python |
| **Domain** | Beat Saber **ranked** maps (standard difficulties) |
| **Scale** | **3,000+** distinct song maps worth of parsed chart data (see `training_report.json` for exact zip / map / note counts from the run that produced these files) |
| **Purpose** | Capture how ranked mappers space notes, stack simultaneous hits, and chain local patterns so generators or evaluators can stay “on distribution.” |

---

## File reference

### `ranked_spacing_profile.json`

**What it is:** A **per-difficulty spacing and density profile** built from many ranked maps.

**Contents (high level):** For difficulties such as `normal`, `expert`, and `expertplus`, you get:

- **`maps`** — how many charts contributed to that bucket  
- **`gap_p25` … `gap_p90`** — quantiles of **time gaps** between notes (beat-spacing style stats)  
- **`nps_p25` … `nps_p75`** — quantiles of **notes per second**–style density  
- **`simul_distribution`** — how often **1, 2, … simultaneous** notes appear (left/right stacks)  
- **`createdFromMaps`** — total map count feeding the profile  

**Use case:** Conditioning or validation (“does this map’s spacing look like ranked Normal / Expert+?”).

---

### `ranked_pattern_model.json`

**What it is:** The main **learned pattern / n-gram style model** (large JSON). It encodes **conditional structure** of note tokens and transitions observed across the corpus.

**Contents (high level):** Includes metadata such as:

- **`version`**, **`createdAt`**, **`source`** (input archive path used for that run)  
- **`stats`** — aggregate counts (`zips_seen`, `standard_maps`, `notes`, etc.)  
- **`global`** — **starters** and continuation statistics (tokens like `line:row:…` with `count` and probability `p`)  
- Additional sections (not fully listed here) drive **pattern continuation** from context; the file can be **very large** because it stores many n-grams / transitions.  

**Use case:** Sampling or scoring local note sequences to match ranked-map style.

---

### `brain/dataset_brain.json`

**What it is:** A **higher-level “brain”** bundle that combines **spacing priors** and the **trained pattern model** into something easier to ship to a generator or dataset consumer.

**Contents (high level):**

- **`version`** (e.g. `dataset-brain-v1`), **`createdAt`**, **`source`** description  
- **`styles`** — named **procedural style priors** (e.g. “ranked tech”, “flowy dance”, “speed map”) each with a **`vector`** of knobs (density, streams, `maxSimultaneous`, dots, walls, flow/tech bias) and a short **`description`**  
- **`retrievalIndex`** — index entries keyed by difficulty / regime (e.g. `expert`) for **retrieval-style** use alongside the vectors  

**Use case:** One file to load for “style + ranked stats + retrieval hints” without wiring every low-level JSON by hand.

---

### `training_report.json`

**What it is:** A **small JSON summary** of the training / ingestion run that produced `ranked_pattern_model.json` (and related outputs).

**Typical fields:**

- **`zips_seen`** — map archives processed  
- **`zips_without_standard_maps`** — archives skipped or without standard diffs  
- **`standard_maps`** — individual **Standard** difficulty charts parsed  
- **`notes`** — total **block / note** events counted  
- **`elapsed_sec`** — wall time for the run  
- **`model`** — path or name of the written pattern model  

**Use case:** Reproducibility, Hugging Face dataset **README stats**, or sanity checks after retraining.

---

### `training.log`

**What it is:** **Plain-text log** from the Python training run (progress + final summary).

**Contents:** Lines such as `KCODE_PROGRESS {…}` with incremental **`zips`**, **`parsed_maps`**, **`notes`**, **`elapsed_sec`**, plus a trailing **`DONE`** and optional JSON echo of final counts.

**Use case:** Debugging failed runs, comparing two trainings, or attaching evidence to a dataset card without opening huge JSON.

---

### `training.pid`

**What it is:** A single **process ID** (text file, one number) for the training job that wrote these artifacts.

**Use case:** Operational only—e.g. stopping or monitoring the process on the machine that produced the dataset. **Not** required for Hugging Face upload unless you document your local workflow.

---

### `mog.md`

**What it is:** A **local duplicate** of the narrative card (same kind of content as this README). The **Hub only renders `README.md`** as the dataset card, so keep the YAML header here and treat `mog.md` as optional documentation in clones.

---

## Hugging Face upload notes

1. Link or describe the **legal source** of ranked maps (community licenses, BeatSaver / similar policies).  
2. Paste key numbers from **`training_report.json`** into this README if you want them visible without opening JSON.  
3. **`ranked_pattern_model.json`** may exceed normal Git limits—use **Git LFS** or split delivery via the `datasets` library if needed.  
4. State clearly: **Python-trained** on **3,000+** Beat Saber **song maps**; artifacts are **derived statistics**, not the original maps.

---

## Directory layout

```
models/
├── README.md                   ← Hub dataset card (YAML + body)
├── mog.md                      ← optional copy of narrative
├── ranked_spacing_profile.json
├── ranked_pattern_model.json
├── training_report.json
├── training.log
├── training.pid
└── brain/
    └── dataset_brain.json
```
