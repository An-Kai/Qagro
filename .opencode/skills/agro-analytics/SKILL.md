---
name: agro-analytics
description: Honest crop-yield analytics for the Qagro project — leakage-free features, train-only selection, hold-out discipline, conformal intervals, no-mock data policy. Use when training, evaluating, or changing any yield model, panel, or metric in Qagro.
---

# Agro-Analytics (Qagro)

Rules distilled from `docs/MODEL_AUDIT.md`. Violating any of them silently
invalidates the hackathon metrics.

## 1. No leakage, ever

- Lag/rolling features (`yield_lag1`, `yield_roll3`) only via `shift(1)`
  inside `(district, crop)`. Area gaps: `ffill` (past) + same-year oblast
  value — never `bfill`.
- Calendar features (`year_trend`) are fine. Static features (soil) are fine.
- New NDVI/soil/area columns must have zero NaN on train or be excluded by
  `_usable_candidates` — never impute with future means.

## 2. Selection on train only

- Feature/weight selection: `SelectKBest` + blend-weight search on
  `TimeSeriesSplit` over `year <= 2020` ONLY (`src/train.py`).
- `src/evaluate.py` NEVER refits on hold-out. `below_baseline` is a flag,
  not a trigger for retuning. Hold-out 2021–2025 is read once, for reporting.

## 3. Intervals, not point worship

- Publish `lo10/hi90` from `metrics/conformal.json` (OOF quantiles), never
  symmetric sigma, unless the file is missing (documented fallback).
- Report empirical coverage next to every interval. Nominal 0.80 is never
  claimed — only measured coverage from `metrics/intervals.json`.
- Experimental crops (rapeseed): baseline mean5 + volatility-based width,
  flag `experimental:true`.

## 4. No mocks, loud failures

- Missing district/crop/weather/history/model → `ValueError`/`FileNotFoundError`,
  never invented numbers. Missing API data → `None` + reason string.
- Structural breaks (rapeseed 2024) are documented in `data_card.md`, not
  smoothed away.

## 5. After any model change, in order

1. `python src/train.py` → 2. `python src/evaluate.py` →
   3. `python src/intervals.py` → 4. all `tests/test_*.py` →
   5. update README metrics table + SUBMISSION key numbers to match
   `metrics/metrics.json` exactly.
