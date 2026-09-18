"""insurance.py — индексная страховка (decision support, НЕ тариф).

  mean5      — среднее урожайности за пред. 5 лет (тот же район+культура,
               правило models/baseline.json; для APPROX-культур — mean5 пшеницы
               x APPROX-фактор, с пометкой APPROX).
  y_pred     — LGBM-прогноз 2026 при нейтральном сценарии погоды
               (средний MJJA-климат района за 2016-2025 из панели; детерминировано,
               без выдумок). Для APPROX-культур — масштабирование от пшеницы.
  residual   — residual_std из models/lgbm_{crop}.pkl (для APPROX — std пшеницы
               x фактор). P_loss считается нормальной аппроксимацией разброса
               OOF-остатков: P(Y < 0.8*mean5), Y ~ N(y_pred, resid_std).
  payout     — max(0, 0.8*mean5 - y_pred) * price * subsidy.
               Единицы: урожайность в ц/га -> в тонны делим на 10
               (поле payout_formula показывает оба варианта, чтобы сошлось
               с текстом ТЗ дословно и агрономически корректно).
  price      — config avg_price_kzt_per_t (95 000) для wheat/barley;
               для APPROX — ориентиры из approx_crops.APPROX_PRICE_KZT.
  subsidy    — config subsidy_rate (0.8).

Функция: insurance_quote(district_en, crop) ->
  {p_loss, expected_payout_ha, mean5, y_pred, ...}

Честная подпись везде: "decision support, не тариф".
"""
from __future__ import annotations

import math
import pickle
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "akmola_panel.csv"
MODELS = ROOT / "models"
CONFIG = ROOT / "config" / "districts.yaml"
METRICS = ROOT / "metrics" / "metrics.json"
WIDE_FACTOR = 1.5

TARGET = "yield_c_ha"
WEATHER_KEYS = ("tmean_mjja", "precip_mjja", "gdd5", "heat30",
                "dry_max", "et0", "p30_anom")
DISCLAIMER = ("decision support, не тариф / "
              "шешімді қолдау, тариф емес / "
              "decision support, not a tariff")

try:
    from src.approx_crops import (  # как пакет
        ALL_CROPS, APPROX_PRICE_KZT, APPROX_YIELD_FACTOR, is_approx,
    )
except ImportError:
    try:
        from .approx_crops import (  # noqa: E402
            ALL_CROPS, APPROX_PRICE_KZT, APPROX_YIELD_FACTOR, is_approx,
        )
    except ImportError:  # прямой запуск из папки src/
        from approx_crops import (  # noqa: E402
            ALL_CROPS, APPROX_PRICE_KZT, APPROX_YIELD_FACTOR, is_approx,
        )


def _predict_lgbm(district_en: str, crop: str, weather: dict):
    try:
        from src.predict import predict_yield
    except ImportError:
        try:
            from .predict import predict_yield  # type: ignore
        except ImportError:
            from predict import predict_yield  # type: ignore
    return predict_yield(district_en, crop, weather)


def _predict_approx(district_en: str, crop: str, weather: dict):
    try:
        from src.approx_crops import predict_approx
    except ImportError:
        try:
            from .approx_crops import predict_approx  # type: ignore
        except ImportError:
            from approx_crops import predict_approx  # type: ignore
    return predict_approx(district_en, crop, weather)


def _settings() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    s = cfg.get("settings", {})
    return {
        "threshold": float(s.get("insurance_threshold", 0.8)),
        "subsidy": float(s.get("subsidy_rate", 0.8)),
        "price": float(s.get("avg_price_kzt_per_t", 95000)),
        "window": int(s.get("baseline_window", 5)),
    }


def _panel() -> pd.DataFrame:
    if not PANEL.exists():
        raise FileNotFoundError(f"Панель {PANEL} не найдена.")
    return pd.read_csv(PANEL)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _mean5(df: pd.DataFrame, district_en: str, crop: str, window: int) -> tuple[float, list[int]]:
    """mean5 + годы. Для APPROX — история пшеницы x фактор."""
    if is_approx(crop):
        sub = df[(df["district_en"] == district_en) & (df["crop"] == "spring_wheat")]
        if sub.empty:
            raise ValueError(f"Нет истории пшеницы для {district_en} (нужна для APPROX {crop}).")
        last5 = sub.sort_values("year").tail(window)
        if len(last5) < window or last5[TARGET].isna().any():
            raise ValueError(f"Мало истории пшеницы для {district_en} к APPROX {crop}.")
        return round(float(last5[TARGET].mean() * APPROX_YIELD_FACTOR[crop]), 2), \
            [int(y) for y in last5["year"].tolist()]
    sub = df[(df["district_en"] == district_en) & (df["crop"] == crop)]
    if sub.empty:
        raise ValueError(f"Нет истории для {district_en}/{crop}.")
    last5 = sub.sort_values("year").tail(window)
    if len(last5) < window or last5[TARGET].isna().any():
        raise ValueError(
            f"Бейзлайн: мало истории для {district_en}/{crop} "
            f"({len(last5)} < {window}) — заглушки запрещены.")
    return round(float(last5[TARGET].mean()), 2), [int(y) for y in last5["year"].tolist()]


def _neutral_weather(df: pd.DataFrame, district_en: str) -> dict:
    """Нейтральный сценарий 2026: средний MJJA-климат района за 2016-2025."""
    sub = df[df["district_en"] == district_en]
    if sub.empty:
        raise ValueError(f"district_en={district_en!r} нет в панели.")
    win = sub[sub["year"] >= 2016]
    if win.empty:
        win = sub
    return {k: round(float(win[k].mean()), 2) for k in WEATHER_KEYS}


def _experimental_set() -> set[str]:
    """Культуры с below_baseline=true в metrics/metrics.json."""
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
    return crop in _experimental_set()


def _resid_std(crop: str) -> float:
    base = "spring_wheat" if is_approx(crop) else crop
    p = MODELS / f"lgbm_{base}.pkl"
    if not p.exists():
        raise FileNotFoundError(f"Модель {p} не найдена. Сначала: python src/train.py")
    with open(p, "rb") as f:
        bundle = pickle.load(f)
    std = float(bundle["residual_std"])
    if is_approx(crop):
        std = std * float(APPROX_YIELD_FACTOR[crop])
    if is_experimental(crop):
        std = std * WIDE_FACTOR
    return std


def insurance_quote(district_en: str, crop: str) -> dict:
    """Котировка индексной страховки. Поддерживает 6 культур (4 — APPROX)."""
    if crop not in ALL_CROPS:
        raise ValueError(f"crop={crop!r} неизвестна. Допустимо: {list(ALL_CROPS)}.")
    st = _settings()
    thr, sub_rate, window = st["threshold"], st["subsidy"], st["window"]
    df = _panel()
    if district_en not in sorted(df["district_en"].unique()):
        raise ValueError(f"district_en={district_en!r} нет в панели.")

    mean5, years = _mean5(df, district_en, crop, window)
    weather = _neutral_weather(df, district_en)
    experimental = is_experimental(crop)

    if is_approx(crop):
        pred = _predict_approx(district_en, crop, weather)
        price = float(APPROX_PRICE_KZT[crop])
        method = "APPROX linear scaling from spring_wheat"
    elif experimental:
        # Честный fallback: LGBM хуже бейзлайна -> y_pred = baseline mean5,
        # интервал шире учтён в _resid_std (residual*1.5).
        # predict_yield уже возвращает baseline для experimental культур.
        pred = _predict_lgbm(district_en, crop, weather)
        price = float(APPROX_PRICE_KZT.get(crop, st["price"]))
        method = ("baseline-5y mean (experimental: LGBM below baseline "
                  "on hold-out 2021-2025; interval x1.5)")
    else:
        pred = _predict_lgbm(district_en, crop, weather)
        price = st["price"]
        method = "LGBM + baseline-5y + OOF residual_std"
    y_pred = float(pred["y_pred"])
    std = _resid_std(crop)

    strike = round(thr * mean5, 2)
    if std <= 0 or not math.isfinite(std):
        raise ValueError(f"Некорректный residual_std={std} для {crop}.")
    d = (strike - y_pred) / std
    p_loss = round(_norm_cdf(d), 4)
    # E[max(0, strike - Y)], Y~N(y_pred, std) — актуарное матожидание недобора (ц/га)
    exp_shortfall = std * _norm_pdf(d) + (strike - y_pred) * _norm_cdf(d)
    exp_shortfall = max(0.0, float(exp_shortfall))
    shortfall_point = max(0.0, strike - y_pred)
    # ц/га -> т/га (/10) x цена x субсидия
    expected_payout = round(exp_shortfall / 10.0 * price * sub_rate, 0)
    payout_at_pred = round(shortfall_point / 10.0 * price * sub_rate, 0)
    # дословно по ТЗ без /10 (для сверки):
    literal = round(shortfall_point * price * sub_rate, 0)

    return {
        "district_en": district_en,
        "crop": crop,
        "approx": bool(is_approx(crop)),
        "experimental": bool(experimental),
        "method": method,
        "mean5_c_ha": mean5,
        "mean5_years": years,
        "y_pred_c_ha": round(y_pred, 2),
        "residual_std": round(std, 3),
        "strike_c_ha": strike,
        "threshold": thr,
        "p_loss": p_loss,
        "shortfall_c_ha": round(shortfall_point, 2),
        "expected_shortfall_c_ha": round(exp_shortfall, 2),
        "expected_payout_ha": expected_payout,
        "payout_at_pred_ha": payout_at_pred,
        "payout_literal_no_div10": literal,
        "price_kzt_per_t": price,
        "subsidy_rate": sub_rate,
        "weather_scenario": {"kind": "neutral district MJJA mean 2016-2025", **weather},
        "payout_formula": ("max(0, 0.8*mean5 - y_pred)/10*price*subsidy "
                           "(дословно ТЗ без /10 — см. payout_literal_no_div10)"),
        "disclaimer": DISCLAIMER,
    }


if __name__ == "__main__":
    import json
    import sys

    d = sys.argv[1] if len(sys.argv) > 1 else "Esil"
    c = sys.argv[2] if len(sys.argv) > 2 else "spring_wheat"
    print(json.dumps(insurance_quote(d, c), ensure_ascii=False, indent=2))
