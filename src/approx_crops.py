"""approx_crops.py — честный fallback для культур без обучающих данных.

Панель akmola_panel.csv содержит ТОЛЬКО spring_wheat и barley, поэтому LGBM
обучен только для них. Чтобы бот показывал 6 культур (как в
config/districts.yaml), остальные 4 — строго rule-based линейным
масштабированием от прогноза пшеницы, с пометкой APPROX везде:

  APPROX_YIELD_FACTOR — множитель урожайности (ц/га) от spring_wheat:
    oats      x1.02  (овёс: биомасса чуть выше пшеницы на севере КЗ)
    sunflower x0.85  (подсолнечник: масса семян, другая влажность)
    rapeseed  x0.72  (рапс)
    flax      x0.58  (лён масличный)

  APPROX_PRICE_KZT — ориентир цены тг/т (рынок Акмолы 2024-25, НЕ тариф):
    oats 70 000, sunflower 180 000, rapeseed 200 000, flax 220 000.

НЕ обучать для них LGBM без данных — это было бы подлогом. Любой ответ
по этим культурам обязан содержать flag "APPROX".
"""
from __future__ import annotations

from typing import Any

APPROX_YIELD_FACTOR: dict[str, float] = {
    "oats": 1.02,       # APPROX: linear scaling from spring_wheat
    "sunflower": 0.85,  # APPROX: linear scaling from spring_wheat
    "rapeseed": 0.72,   # APPROX: linear scaling from spring_wheat
    "flax": 0.58,       # APPROX: linear scaling from spring_wheat
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
    return crop in APPROX_YIELD_FACTOR


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
