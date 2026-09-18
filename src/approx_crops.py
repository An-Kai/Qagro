"""approx_crops.py — честный fallback для культур без обучающих данных (v2).

v1: панель содержала ТОЛЬКО spring_wheat и barley, поэтому LGBM был только
для них, а oats/sunflower/rapeseed/flax — строго rule-based масштабированием
от пшеницы с пометкой APPROX.

v2: панель содержит 6 культур (см. src/fetch_stat.py). train.py обучает LGBM
для каждой культуры, где строк >= 40. После обучения is_approx(crop) == False
для обученных культур (модель существует) — API/бот/страховка автоматически
переходят на LGBM. APPROX остаётся ТОЛЬКО как fallback, если модели нет:

  APPROX_YIELD_FACTOR — множитель урожайности (ц/га) от spring_wheat:
    oats      x1.02
    sunflower x0.85
    rapeseed  x0.72
    flax      x0.58

  APPROX_PRICE_KZT — ориентир цены тг/т (рынок Акмолы 2024-25, НЕ тариф):
    oats 70 000, sunflower 180 000, rapeseed 200 000, flax 220 000.

Любой ответ по fallback-культуре обязан содержать flag "APPROX".
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

APPROX_YIELD_FACTOR: dict[str, float] = {
    "oats": 1.02,       # APPROX fallback: linear scaling from spring_wheat
    "sunflower": 0.85,  # APPROX fallback
    "rapeseed": 0.72,   # APPROX fallback
    "flax": 0.58,       # APPROX fallback
}

APPROX_PRICE_KZT: dict[str, int] = {
    "oats": 70_000,       # APPROX: indicative, not a tariff
    "sunflower": 180_000,  # APPROX
    "rapeseed": 200_000,   # APPROX
    "flax": 220_000,       # APPROX
}

LGBM_CROPS = ("spring_wheat", "barley")
APPROX_CROPS = tuple(APPROX_YIELD_FACTOR.keys())
ALL_CROPS = LGBM_CROPS + APPROX_CROPS  # 6 культур для бота

_ROOT = Path(__file__).resolve().parents[1]
_MODELS = _ROOT / "models"


def _model_exists(crop: str) -> bool:
    return (_MODELS / f"lgbm_{crop}.pkl").exists()


def _wheat_predict(district_en: str, weather_2026_dict: dict[str, Any]) -> dict[str, Any]:
    try:  # как пакет src.*
        from src.predict import predict_yield
    except ImportError:
        try:  # относительный импорт
            from .predict import predict_yield  # type: ignore
        except ImportError:  # прямой запуск из папки src/
            from predict import predict_yield  # type: ignore
    return predict_yield(district_en, "spring_wheat", weather_2026_dict)


def is_approx(crop: str) -> bool:
    """True — только если это fallback-культура И LGBM-модели для неё нет.

    v2: после обучения lgbm_oats.pkl и др. is_approx('oats') == False,
    и весь стек (API/бот/страховка) использует настоящий LGBM.
    """
    return crop in APPROX_YIELD_FACTOR and not _model_exists(crop)


def predict_approx(district_en: str, crop: str,
                   weather_2026_dict: dict[str, Any] | None = None) -> dict[str, Any]:
    """APPROX-прогноз: берём LGBM-прогноз пшеницы и масштабируем.

    weather_2026_dict=None -> климат-норма района (см. src/predict.py).
    Возвращает тот же формат, что predict_yield, + method="APPROX linear scaling".
    """
    if crop not in APPROX_YIELD_FACTOR:
        raise ValueError(f"crop={crop!r} не APPROX-культура. APPROX: {list(APPROX_YIELD_FACTOR)}.")
    base = _wheat_predict(district_en, weather_2026_dict)
    f = APPROX_YIELD_FACTOR[crop]
    scaled = {k: round(base[k] * f, 2) for k in ("y_pred", "lo10", "hi90")}
    return {
        **scaled,
        "factors": base["factors"],
        "meta": {**base["meta"], "crop": crop, "base_crop": "spring_wheat",
                 "method": "APPROX linear scaling",
                 "yield_factor": f,
                 "warning": "APPROX: без обучающих данных, масштабирование от пшеницы. "
                            "Decision support, не тариф."},
        "approx": True,
    }
