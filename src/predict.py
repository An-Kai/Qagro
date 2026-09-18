"""predict.py — прогноз урожайности на 2026: predict_yield(district_en, crop, weather_2026_dict).

Вход:
  district_en        — англ. имя района (одно из 10 в панели, см. config/districts.yaml)
  crop               — 'spring_wheat' | 'barley'
  weather_2026_dict  — MJJA-агроклимат 2026:
    {tmean_mjja, precip_mjja, gdd5, heat30, dry_max, et0, p30_anom}

Выход: dict(y_pred, lo10, hi90, factors)
  y_pred  — точечный прогноз LGBM (ц/га)
  lo10/hi90 — 80% интервал: y_pred ± 1.2816 * residual_std
    (residual_std — std OOF-остатков из CV в train.py, хранится в модели)
  factors — top-3 SHAP-вклада для ЭТОГО прогноза (feature, value, shap_value)

Никаких моков: неизвестный район/культура, неполная погода, отсутствие
yield_lag1 (урожая 2025 для пары район+культура) или отсутствие модели —
это loud-ошибки (ValueError/FileNotFoundError), а не выдуманные цифры.

Референс подхода: UniCrop, MIT license.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "akmola_panel.csv"
MODELS = ROOT / "models"
METRICS = ROOT / "metrics" / "metrics.json"

# v2: 6 культур с LGBM (если обучены, см. src/train.py MIN_TRAIN_ROWS);
# если модели нет — используйте src/approx_crops.predict_approx (APPROX fallback).
CROPS = ("spring_wheat", "barley", "oats", "sunflower", "rapeseed", "flax")
WEATHER_KEYS = ("tmean_mjja", "precip_mjja", "gdd5", "heat30",
                "dry_max", "et0", "p30_anom")
TARGET = "yield_c_ha"
Z80 = 1.2816  # z для 80% интервала (10/90 перцентили) при нормальных остатках
BASELINE_WINDOW = 5
WIDE_FACTOR = 1.5  # experimental: интервал шире (residual*1.5)


def _experimental_crops() -> set[str]:
    """Культуры с below_baseline=true в metrics/metrics.json.

    Для них LGBM хуже среднего-5-лет на hold-out 2021-2025
    (sunflower/rapeseed/flax: структурный сдвиг 2024-2025),
    поэтому прогноз = baseline mean5, интервал шире, флаг experimental:true.
    Wheat/barley/oats остаются LGBM.
    """
    import json

    try:
        if not METRICS.exists():
            return set()
        data = json.loads(METRICS.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {c for c, m in data.items()
            if isinstance(m, dict) and m.get("below_baseline") is True}


def is_experimental(crop: str) -> bool:
    return crop in _experimental_crops()


def _baseline_mean5(df: pd.DataFrame, district_en: str, crop: str,
                    window: int = BASELINE_WINDOW) -> tuple[float, list[int]]:
    sub = df[(df["district_en"] == district_en) & (df["crop"] == crop)]
    sub = sub.sort_values("year")
    last = sub.tail(window)
    if len(last) < window or last[TARGET].isna().any():
        raise ValueError(
            f"Бейзлайн: мало истории для {district_en}/{crop} "
            f"({len(last)} < {window}) — заглушки запрещены.")
    return round(float(last[TARGET].mean()), 2), [int(y) for y in last["year"].tolist()]


def _load_bundle(crop: str) -> dict:
    import pickle

    p = MODELS / f"lgbm_{crop}.pkl"
    if not p.exists():
        raise FileNotFoundError(
            f"Модель {p} не найдена. Сначала: python src/train.py "
            f"(если строк<40 — культура остаётся APPROX, используйте "
            f"src/approx_crops.predict_approx).")
    with open(p, "rb") as f:
        return pickle.load(f)


def _load_panel() -> pd.DataFrame:
    if not PANEL.exists():
        raise FileNotFoundError(f"Панель {PANEL} не найдена.")
    return pd.read_csv(PANEL)


def _neutral_weather(df: pd.DataFrame, district_en: str) -> dict[str, float]:
    """Климат-норма района: средний MJJA-климат за 2016-2025 (детерминировано).

    Используется когда weather_2026_dict=None. Та же логика, что в
    src/insurance.py::_neutral_weather — без выдумок, только среднее панели.
    """
    sub = df[df["district_en"] == district_en]
    if sub.empty:
        raise ValueError(f"district_en={district_en!r} нет в панели.")
    win = sub[sub["year"] >= 2016]
    if win.empty:
        win = sub
    return {k: round(float(win[k].mean()), 2) for k in WEATHER_KEYS}


def predict_yield(district_en: str, crop: str,
                  weather_2026_dict: dict[str, Any] | None = None) -> dict[str, Any]:
    """Прогноз урожайности на 2026 для (район, культура).

    weather_2026_dict=None означает климат-норму: средний MJJA-климат
    района за 2016-2025 из панели (см. _neutral_weather). Удобно для
    API/бота/Streamlit, где погоду сезона заранее не знают.
    """
    if crop not in CROPS:
        raise ValueError(f"crop={crop!r} неизвестна. Допустимо: {list(CROPS)}.")

    df = _load_panel()
    known = sorted(df["district_en"].unique())
    if district_en not in known:
        raise ValueError(f"district_en={district_en!r} неизвестен. Допустимо: {known}.")

    weather_source = "provided"
    if weather_2026_dict is None:
        weather_2026_dict = _neutral_weather(df, district_en)
        weather_source = "neutral district MJJA mean 2016-2025 (climate norm)"
    if not isinstance(weather_2026_dict, dict):
        raise ValueError("weather_2026_dict должен быть dict с ключами "
                         f"{list(WEATHER_KEYS)} или None (климат-норма).")
    missing = [k for k in WEATHER_KEYS if k not in weather_2026_dict]
    if missing:
        raise ValueError(f"В weather_2026_dict нет ключей: {missing}. "
                         "Додумывать погоду запрещено.")
    vals: dict[str, float] = {}
    for k in WEATHER_KEYS:
        try:
            v = float(weather_2026_dict[k])
        except (TypeError, ValueError) as e:
            raise ValueError(f"weather[{k}]={weather_2026_dict[k]!r} не число.") from e
        if not np.isfinite(v):
            raise ValueError(f"weather[{k}] не конечно ({v}). Заглушки запрещены.")
        vals[k] = v

    geo = df[df["district_en"] == district_en][["lat", "lon"]].iloc[0]
    hist = df[(df["district_en"] == district_en) & (df["crop"] == crop)].sort_values("year")
    if hist.empty:
        raise ValueError(f"Нет истории для {district_en}/{crop}.")
    last_year = int(hist["year"].max())
    lag = hist[hist["year"] == last_year]
    if lag.empty or not np.isfinite(float(lag[TARGET].iloc[0])):
        raise ValueError(f"Нет {TARGET} за {last_year} для {district_en}/{crop} — "
                         "yield_lag1 взять неоткуда, прогноз невозможен.")
    yield_lag1 = float(lag[TARGET].iloc[0])

    bundle = _load_bundle(crop)
    resid_std = float(bundle["residual_std"])

    # --- experimental fallback: LGBM хуже бейзлайна на hold-out ---
    if is_experimental(crop):
        mean5, years = _baseline_mean5(df, district_en, crop, BASELINE_WINDOW)
        wide = float(resid_std * WIDE_FACTOR)
        lo10 = float(mean5 - Z80 * wide)
        hi90 = float(mean5 + Z80 * wide)
        return {"y_pred": round(mean5, 2), "lo10": round(lo10, 2),
                "hi90": round(hi90, 2), "factors": [],
                "experimental": True,
                "method": "baseline-5y mean (experimental: LGBM below baseline on hold-out)",
                "meta": {"district_en": district_en, "crop": crop, "year": 2026,
                         "yield_lag1": round(yield_lag1, 2),
                         "residual_std": round(wide, 3),
                         "lgbm_residual_std": round(resid_std, 3),
                         "wide_factor": WIDE_FACTOR,
                         "baseline_mean5": round(mean5, 2),
                         "baseline_years": years,
                         "weather_source": weather_source,
                         "weather": vals}}

    feats: list = bundle["features"]
    row: dict[str, float] = {**vals, "lat": float(geo["lat"]),
                             "lon": float(geo["lon"]), "yield_lag1": yield_lag1}
    absent = [c for c in feats if c not in row]
    if absent:
        raise ValueError(f"Модели нужны фичи {absent}, которых нет во входе.")
    X = pd.DataFrame([{c: row[c] for c in feats}])[feats]
    y_pred = float(bundle["model"].predict(X.to_numpy())[0])
    lo10 = float(y_pred - Z80 * resid_std)
    hi90 = float(y_pred + Z80 * resid_std)

    # Per-row SHAP top-3 для этого прогноза
    try:
        import shap
        explainer = shap.TreeExplainer(bundle["model"])
        sv = np.asarray(explainer.shap_values(X.to_numpy())).ravel()
        order = list(np.argsort(-np.abs(sv))[:3])
        factors = [{"feature": feats[i], "value": float(X.iloc[0, i]),
                    "shap_value": float(sv[i])} for i in order]
    except ImportError as e:
        raise ImportError("Для factors нужен пакет shap: pip install shap.") from e

    return {"y_pred": round(y_pred, 2), "lo10": round(lo10, 2),
            "hi90": round(hi90, 2), "factors": factors,
            "experimental": False,
            "meta": {"district_en": district_en, "crop": crop, "year": 2026,
                     "yield_lag1": round(yield_lag1, 2),
                     "residual_std": round(resid_std, 3),
                     "weather_source": weather_source,
                     "weather": vals}}


if __name__ == "__main__":  # демо-пример
    import json

    demo_weather = {"tmean_mjja": 18.0, "precip_mjja": 180.0, "gdd5": 1450.0,
                    "heat30": 10.0, "dry_max": 14.0, "et0": 490.0, "p30_anom": 0.0}
    for demo_crop in CROPS:
        print(json.dumps(predict_yield("Esil", demo_crop, demo_weather),
                         ensure_ascii=False, indent=2))
