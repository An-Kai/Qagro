"""recommend.py — окно сева по GDD + прогнозу (RU/KZ/EN словари).

Правило (строго по ТЗ + честные пороги):
  если p30_anom < -20% И heat высокий (heat30 > 15 дней за MJJA) ->
      "сдвинуть сев на 12-18 мая, влагосбережение"
      (закрытие влаги, мелкая заделка, засухоустойчивый сорт, кущение под запас).

Прочие ветки (документированы, не выдуманы под факт):
  * сухо без жары (p30 < -20, heat <= 15) -> ранний сев 8-15 мая (уйти за весенней
    влагой) + влагосбережение;
  * жара без засухи (p30 >= -20, heat > 15) -> окно 12-20 мая, жаростойкий сорт;
  * норма -> 15-25 мая (стандарт Акмолы для яровых).

GDD: base_temp берётся из config/districts.yaml на культуру
(wheat/barley/oats/rapeseed/flax=5 °C, sunflower=8 °C); средний GDD района
из панели показывается как контекст, окно сева — календарное с поправкой
на прогноз (выше).

Источники p30_anom/heat30: caller может передать (напр. из risk.py или
прогноза); по умолчанию — факт 2025 того же района из панели как
proxy-прогноз с честной пометкой (без API-моков).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "akmola_panel.csv"
CONFIG = ROOT / "config" / "districts.yaml"

DRY_THR = -20.0   # p30_anom_pct < -20% = сухо (по ТЗ)
HEAT_THR = 15     # heat30 > 15 дней MJJA = "heat высокий" (медиана панели ~10-12)

I18N: dict[str, dict[str, dict[str, str]]] = {
    # ключ ветки -> lang -> {window, message}
    "dry_heat": {
        "ru": {"window": "12–18 мая",
               "message": "Сдвинуть сев на 12–18 мая, влагосбережение: закрытие влаги, "
                          "мелкая заделка, засухоустойчивый сорт."},
        "kz": {"window": "12–18 мамыр",
               "message": "Себуді 12–18 мамырға жылжыту, ылғал үнемдеу: ылғал жабу, "
                          "тайыз сіңіру, құрғақшылыққа төзімді сорт."},
        "en": {"window": "12–18 May",
               "message": "Shift sowing to 12–18 May, moisture saving: harrowing, "
                          "shallow placement, drought-tolerant variety."},
    },
    "dry": {
        "ru": {"window": "8–15 мая",
               "message": "Ранний сев 8–15 мая — уйти за весенней влагой + влагосбережение."},
        "kz": {"window": "8–15 мамыр",
               "message": "Ерте себу 8–15 мамыр — көктемгі ылғалды пайдалану + ылғал үнемдеу."},
        "en": {"window": "8–15 May",
               "message": "Early sowing 8–15 May to catch spring moisture + moisture saving."},
    },
    "heat": {
        "ru": {"window": "12–20 мая",
               "message": "Сев 12–20 мая, жаростойкий сорт, контроль глубины заделки."},
        "kz": {"window": "12–20 мамыр",
               "message": "Себу 12–20 мамыр, ыстыққа төзімді сорт, сіңіру тереңдігін бақылау."},
        "en": {"window": "12–20 May",
               "message": "Sow 12–20 May, heat-tolerant variety, watch placement depth."},
    },
    "normal": {
        "ru": {"window": "15–25 мая",
               "message": "Стандартное окно 15–25 мая, оптимальная норма высева."},
        "kz": {"window": "15–25 мамыр",
               "message": "Стандартты мерзім 15–25 мамыр, оңтайлы себу нормасы."},
        "en": {"window": "15–25 May",
               "message": "Standard window 15–25 May, optimal seeding rate."},
    },
}

ACTIONS: dict[str, dict[str, list[str]]] = {
    "dry_heat": {
        "ru": ["Закрытие влаги боронованием", "Мелкая заделка семян",
               "Засухоустойчивый сорт", "Стартовая доза NPK под запас влаги"],
        "kz": ["Тырмалаумен ылғал жабу", "Тайыз сіңіру",
               "Құрғақшылыққа төзімді сорт", "Ылғал қорына NPK старты"],
        "en": ["Harrowing to seal moisture", "Shallow seed placement",
               "Drought-tolerant variety", "Starter NPK for moisture reserve"],
    },
    "dry": {
        "ru": ["Ранний сев", "Закрытие влаги", "Прикатывание"],
        "kz": ["Ерте себу", "Ылғал жабу", "Таптау"],
        "en": ["Early sowing", "Seal moisture", "Rolling"],
    },
    "heat": {
        "ru": ["Жаростойкий сорт", "Контроль глубины", "Сев в утренние часы"],
        "kz": ["Ыстыққа төзімді сорт", "Тереңдікті бақылау", "Таңертең себу"],
        "en": ["Heat-tolerant variety", "Depth control", "Sow in morning hours"],
    },
    "normal": {
        "ru": ["Оптимальная норма высева", "Протравливание семян"],
        "kz": ["Оңтайлы себу нормасы", "Тұқымды дәрілеу"],
        "en": ["Optimal seeding rate", "Seed treatment"],
    },
}


def _crop_base_temp(crop: str) -> float:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for c in cfg.get("crops", []):
        if c.get("id") == crop:
            return float(c.get("base_temp", 5.0))
    raise ValueError(f"crop={crop!r} нет в config/districts.yaml.")


def _proxy_from_panel(district_en: str) -> tuple[float, float, float, int]:
    """proxy (p30_anom, heat30, gdd5, year) — факт последнего года района."""
    if not PANEL.exists():
        raise FileNotFoundError(f"Панель {PANEL} не найдена.")
    df = pd.read_csv(PANEL)
    sub = df[df["district_en"] == district_en]
    if sub.empty:
        raise ValueError(f"district_en={district_en!r} нет в панели.")
    last_year = int(sub["year"].max())
    row = sub[sub["year"] == last_year].iloc[0]
    gdd_mean = round(float(sub["gdd5"].mean()), 1)
    return (float(row["p30_anom"]), float(row["heat30"]),
            gdd_mean, last_year)


def recommend_sowing(district_en: str, crop: str = "spring_wheat",
                     lang: str = "ru",
                     p30_anom: float | None = None,
                     heat30: float | None = None) -> dict:
    """Окно сева. lang: ru|kz|en. Возвращает dict с window/message/actions."""
    lang = (lang or "ru").lower()
    if lang not in ("ru", "kz", "en"):
        raise ValueError(f"lang={lang!r} недопустим. Допустимо: ru, kz, en.")
    base_temp = _crop_base_temp(crop)

    src_note = "переданы вызывающим (напр. из risk.py/прогноза)"
    if p30_anom is None or heat30 is None:
        pp, hh, gdd_mean, py = _proxy_from_panel(district_en)
        p30_anom = pp if p30_anom is None else float(p30_anom)
        heat30 = hh if heat30 is None else float(heat30)
        src_note = (f"proxy-прогноз = факт {py} того же района из панели "
                    f"(p30_anom={pp}, heat30={hh}); передайте свежие p30_anom/heat30 "
                    f"из risk.py для точного совета")
    else:
        _, _, gdd_mean, _ = _proxy_from_panel(district_en)
        p30_anom, heat30 = float(p30_anom), float(heat30)

    dry = p30_anom < DRY_THR
    hot = heat30 > HEAT_THR
    if dry and hot:
        branch = "dry_heat"
        reason = f"p30_anom={p30_anom}% < -20% и heat30={heat30} > {HEAT_THR}: засуха+жара."
    elif dry:
        branch = "dry"
        reason = f"p30_anom={p30_anom}% < -20% при умеренной жаре (heat30={heat30})."
    elif hot:
        branch = "heat"
        reason = f"heat30={heat30} > {HEAT_THR} при достаточных осадках (p30={p30_anom}%)."
    else:
        branch = "normal"
        reason = f"Условия близки к норме (p30={p30_anom}%, heat30={heat30})."

    t = I18N[branch][lang]
    return {
        "district_en": district_en,
        "crop": crop,
        "lang": lang,
        "branch": branch,
        "window": t["window"],
        "message": t["message"],
        "actions": ACTIONS[branch][lang],
        "reason": reason,
        "inputs": {"p30_anom": p30_anom, "heat30": float(heat30),
                   "source": src_note},
        "gdd_context": {"base_temp": base_temp, "district_gdd5_mean": gdd_mean},
        "thresholds": {"dry_p30_lt": DRY_THR, "heat_gt": HEAT_THR},
    }


# алиас для бота
recommend = recommend_sowing


if __name__ == "__main__":
    import json
    import sys

    d = sys.argv[1] if len(sys.argv) > 1 else "Esil"
    c = sys.argv[2] if len(sys.argv) > 2 else "spring_wheat"
    l = sys.argv[3] if len(sys.argv) > 3 else "ru"
    print(json.dumps(recommend_sowing(d, c, l), ensure_ascii=False, indent=2))
