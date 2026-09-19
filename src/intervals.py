"""intervals.py — конформные интервалы из OOF-остатков (Qagro v4).

Метод (честный, без утечек hold-out):
  * Для каждой культуры берём её обученный бандл models/lgbm_{crop}.pkl
    (фичи — из бандла, те же что в train.py v3).
  * На train (year <= 2020) считаем OOF-прогнозы бленда через
    TimeSeriesSplit(n_splits=5) — та же схема, что residual_std в train.py.
  * Остатки OOF: r = y_true - y_pred. Квантили q10, q90 остатков —
    границы конформного 80% интервала (split-conformal на OOF-фолдах).
  * conformal_interval(y_pred, crop) -> (lo, hi) =
    (y_pred + q10, y_pred + q90). Асимметрия сохраняется:
    если модель систематически завышает/занижает, интервал сдвинут.
  * Покрытие считаем ТОЛЬКО на hold-out 2021-2025 (доля факта внутри
    интервала). Ширина/квантили hold-out НЕ видят — утечки нет.

Сравнение: текущий интервал predict.py — симметричный ±1.2816*residual_std
(гауссово предположение, 80% при нормальных остатках).

Артефакты:
  metrics/conformal.json — {crop: {q10, q90, n_oof, resid_std_oof}}
  metrics/intervals.json — покрытие hold-out: conformal vs gauss + ширины.

Никаких моков: нет бандла — loud-ошибка, а не выдуманные квантили.
"""
from __future__ import annotations

import json
import os as _os
import sys as _sys

# BOOTSTRAP (первым, до import pandas): проектный src/calendar.py затеняет
# stdlib `calendar` при `python src/*.py` и роняет импорт pandas через _strptime.
try:
    import calendar as _cal_probe  # noqa: F401
    if not hasattr(_cal_probe, "day_abbr"):
        raise ImportError("stdlib calendar shadowed by src/calendar.py")
    del _cal_probe
except Exception:
    import importlib.util as _ilu
    _stdlib_cal = _os.path.join(_os.path.dirname(_os.__file__), "calendar.py")
    _spec = _ilu.spec_from_file_location("calendar", _stdlib_cal)
    _mod = _ilu.module_from_spec(_spec)
    _sys.modules["calendar"] = _mod
    _spec.loader.exec_module(_mod)
    del _ilu, _spec, _mod, _stdlib_cal

import pickle
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

try:
    from src.train import blend_predict, make_model, make_ridge
except ImportError:
    try:
        from .train import blend_predict, make_model, make_ridge  # type: ignore
    except ImportError:
        from train import blend_predict, make_model, make_ridge  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
PANEL_V3 = ROOT / "data" / "processed" / "akmola_panel_v3.csv"
PANEL_V2 = ROOT / "data" / "processed" / "akmola_panel.csv"
PANEL = PANEL_V3 if PANEL_V3.exists() else PANEL_V2
MODELS = ROOT / "models"
METRICS = ROOT / "metrics"

CROPS = ["spring_wheat", "barley", "oats", "sunflower", "rapeseed", "flax"]
HOLDOUT_FROM = 2021
TARGET = "yield_c_ha"
N_SPLITS = 5
Z80 = 1.2816  # сравнение с текущим гауссовым интервалом predict.py


def load_bundle(crop: str) -> dict:
    p = MODELS / f"lgbm_{crop}.pkl"
    if not p.exists():
        raise FileNotFoundError(f"Нет бандла {p}: сначала python src/train.py")
    with open(p, "rb") as f:
        return pickle.load(f)


def load_panel() -> pd.DataFrame:
    if not PANEL.exists():
        raise FileNotFoundError(f"Нет панели: {PANEL}")
    df = pd.read_csv(PANEL)
    df = df.sort_values(["crop", "district_en", "year"]).reset_index(drop=True)
    df["yield_lag1"] = df.groupby(["district_en", "crop"])[TARGET].shift(1)
    if "yield_roll3" not in df.columns:
        df["yield_roll3"] = (
            df.groupby(["district_en", "crop"])[TARGET]
            .transform(lambda s: s.shift(1).rolling(3, min_periods=3).mean())
        )
    return df


def oof_residuals(df_crop: pd.DataFrame, feats: list[str]) -> np.ndarray:
    """OOF-остатки бленда на train (<=2020), TimeSeriesSplit(5)."""
    train = (df_crop[df_crop["year"] < HOLDOUT_FROM]
             .dropna(subset=["yield_lag1", *feats]).reset_index(drop=True))
    if len(train) < 40:
        raise ValueError(f"Мало train-строк для OOF: {len(train)} < 40")
    X = train[feats]
    y = train[TARGET].to_numpy()
    oof = np.full_like(y, np.nan, dtype=float)
    tss = TimeSeriesSplit(n_splits=N_SPLITS)
    for tr, te in tss.split(X):
        lgbm = make_model()
        lgbm.fit(X.iloc[tr].to_numpy(), y[tr])
        ridge = make_ridge()
        ridge.fit(X.iloc[tr], pd.Series(y[tr]))
        b = {"model": lgbm, "ridge_model": ridge,
             "blend_weights": {"lgbm": 0.7, "ridge": 0.3}}
        oof[te] = blend_predict(b, X.iloc[te])
    mask = ~np.isnan(oof)
    return y[mask] - oof[mask]


def build_conformal() -> dict:
    """Квантили OOF-остатков per-crop -> metrics/conformal.json."""
    df = load_panel()
    out: dict = {}
    for crop in CROPS:
        bundle = load_bundle(crop)
        feats: list = bundle["features"]
        resid = oof_residuals(df[df["crop"] == crop], feats)
        q10, q90 = float(np.quantile(resid, 0.10)), float(np.quantile(resid, 0.90))
        out[crop] = {"q10": round(q10, 3), "q90": round(q90, 3),
                     "n_oof": int(len(resid)),
                     "resid_std_oof": round(float(np.std(resid, ddof=1)), 3)}
        print(f"[{crop}] OOF n={len(resid)} q10={q10:.3f} q90={q90:.3f} "
              f"(ширина {q90 - q10:.3f}; gauss {2 * Z80 * float(np.std(resid, ddof=1)):.3f})")
    METRICS.mkdir(parents=True, exist_ok=True)
    path = METRICS / "conformal.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {path}")
    return out


@lru_cache(maxsize=1)
def _conformal_table() -> dict:
    path = METRICS / "conformal.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Нет {path}: сначала python src/intervals.py (main) или build_conformal().")
    return json.loads(path.read_text(encoding="utf-8"))


def conformal_interval(y_pred: float, crop: str) -> tuple[float, float]:
    """80% конформный интервал для точечного прогноза.

    Границы из OOF-квантилей train (hold-out их не видел).
    """
    table = _conformal_table()
    if crop not in table:
        raise ValueError(f"crop={crop!r} нет в conformal.json. Допустимо: {sorted(table)}.")
    q10 = float(table[crop]["q10"])
    q90 = float(table[crop]["q90"])
    return (round(float(y_pred) + q10, 2), round(float(y_pred) + q90, 2))


def holdout_coverage() -> dict:
    """Покрытие hold-out 2021-2025: conformal vs gauss ±1.28σ."""
    df = load_panel()
    out: dict = {}
    for crop in CROPS:
        bundle = load_bundle(crop)
        feats: list = bundle["features"]
        resid_std = float(bundle["residual_std"])
        sub = df[df["crop"] == crop].sort_values(["district_en", "year"])
        hold = sub[sub["year"] >= HOLDOUT_FROM].dropna(subset=["yield_lag1", *feats])
        y = hold[TARGET].to_numpy()
        p = blend_predict(bundle, hold[feats])
        lo_c, hi_c = p + _conformal_table()[crop]["q10"], p + _conformal_table()[crop]["q90"]
        lo_g, hi_g = p - Z80 * resid_std, p + Z80 * resid_std
        cov_c = float(np.mean((y >= lo_c) & (y <= hi_c)))
        cov_g = float(np.mean((y >= lo_g) & (y <= hi_g)))
        out[crop] = {"n": int(len(y)),
                     "conformal_coverage": round(cov_c, 3),
                     "conformal_width": round(float(np.mean(hi_c - lo_c)), 3),
                     "gauss_coverage": round(cov_g, 3),
                     "gauss_width": round(float(2 * Z80 * resid_std), 3)}
        print(f"[{crop}] n={len(y)} conformal cov={cov_c:.3f} (шир {np.mean(hi_c - lo_c):.2f}) | "
              f"gauss cov={cov_g:.3f} (шир {2 * Z80 * resid_std:.2f})")
    path = METRICS / "intervals.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {path}")
    return out


def main() -> None:
    build_conformal()
    _conformal_table.cache_clear()
    holdout_coverage()
    print("DONE intervals.py")


if __name__ == "__main__":
    main()
