# Local data (not committed)

Put **Beat Saber ranked map archives** (`*.zip`) that you have the rights to use into:

`data/ranked_zips/`

Training and analysis scripts read from there by default. You can point elsewhere instead:

```bash
export BEATMAPER_RANKED_ZIPS=/path/to/your/zips
python3 analyze_ranked_spacing.py
python3 train_ranked_patterns.py
```

The `data/ranked_zips/` directory itself is gitignored so binaries never land on GitHub.
