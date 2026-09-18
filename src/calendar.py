"""calendar.py — посевной календарь Акмолинской области (C8).

6 культур x окна сева/уборки + GDD-нормы. Данные захардкожены из опыта
региона (стандартные акмолинские сроки для яровых + раннеспелых
масличных), поэтому source=agro-practice, а не статистика/ML.

Ядро (прогноз+риск+страховка) не трогаем: этот модуль только справочник.

sowing_calendar(crop, lang="ru") -> dict
"""
from __future__ import annotations

CROPS = ("spring_wheat", "barley", "oats", "sunflower", "rapeseed", "flax")

SOURCE = "agro-practice"

# Окна — календарные ориентиры Северного Казахстана (Акмола):
# яровые зерновые сеют после прогрева почвы и закрытия влаги (май),
# убирают в августе–начале сентября; масличные (подсолнечник раннеспелый,
# рапс, лён) — сев в первой половине мая, уборка август–сентябрь.
_CALENDAR: dict[str, dict] = {
    "spring_wheat": {
        "base_temp": 5.0,
        "gdd_norm": [1300, 1500],
        "sowing": {"ru": "15–25 мая", "kz": "15–25 мамыр", "en": "15–25 May"},
        "harvest": {"ru": "20 августа – 10 сентября",
                    "kz": "20 тамыз – 10 қыркүйек",
                    "en": "20 Aug – 10 Sep"},
        "note": {
            "ru": "Оптимум при прогреве почвы +8…+10 °C; поздний сев теряет влагу.",
            "kz": "Топырақ +8…+10 °C жылығанда оңтайлы; кеш себу ылғал жоғалтады.",
            "en": "Best when soil reaches +8…+10 °C; late sowing loses moisture.",
        },
    },
    "barley": {
        "base_temp": 5.0,
        "gdd_norm": [1200, 1400],
        "sowing": {"ru": "12–25 мая", "kz": "12–25 мамыр", "en": "12–25 May"},
        "harvest": {"ru": "10 августа – 5 сентября",
                    "kz": "10 тамыз – 5 қыркүйек",
                    "en": "10 Aug – 5 Sep"},
        "note": {
            "ru": "Ячмень терпит ранний сев лучше пшеницы; не затягивать уборку.",
            "kz": "Арпа ерте себуге төзімді; жинауды созбаңыз.",
            "en": "Barley tolerates early sowing better than wheat; harvest in time.",
        },
    },
    "oats": {
        "base_temp": 5.0,
        "gdd_norm": [1100, 1300],
        "sowing": {"ru": "10–25 мая", "kz": "10–25 мамыр", "en": "10–25 May"},
        "harvest": {"ru": "10–30 августа",
                    "kz": "10–30 тамыз",
                    "en": "10–30 Aug"},
        "note": {
            "ru": "Влаголюбив: ранний сев за весенней влагой предпочтителен.",
            "kz": "Ылғал сүйгіш: көктемгі ылғалға ерте себу жақсы.",
            "en": "Moisture-loving: early sowing into spring moisture is preferred.",
        },
    },
    "sunflower": {
        "base_temp": 8.0,
        "gdd_norm": [1300, 1500],
        "sowing": {"ru": "10–20 мая", "kz": "10–20 мамыр", "en": "10–20 May"},
        "harvest": {"ru": "5–25 сентября",
                    "kz": "5–25 қыркүйек",
                    "en": "5–25 Sep"},
        "note": {
            "ru": "Сев при +8…+10 °C почвы; только раннеспелые гибриды для Акмолы.",
            "kz": "Топырақ +8…+10 °C кезінде себу; Ақмолаға тек ерте пісетін будандар.",
            "en": "Sow at soil +8…+10 °C; only early hybrids suit Akmola.",
        },
    },
    "rapeseed": {
        "base_temp": 5.0,
        "gdd_norm": [1100, 1300],
        "sowing": {"ru": "10–25 мая", "kz": "10–25 мамыр", "en": "10–25 May"},
        "harvest": {"ru": "15–30 августа",
                    "kz": "15–30 тамыз",
                    "en": "15–30 Aug"},
        "note": {
            "ru": "Мелкосемянный: важен ровный сев и защита от крестоцветных блошек.",
            "kz": "Ұсақ тұқымды: біркелкі себу және бүргелерден қорғау маңызды.",
            "en": "Small-seeded: even placement and flea-beetle control matter.",
        },
    },
    "flax": {
        "base_temp": 5.0,
        "gdd_norm": [1200, 1400],
        "sowing": {"ru": "10–25 мая", "kz": "10–25 мамыр", "en": "10–25 May"},
        "harvest": {"ru": "15 августа – 5 сентября",
                    "kz": "15 тамыз – 5 қыркүйек",
                    "en": "15 Aug – 5 Sep"},
        "note": {
            "ru": "Лён масличный: ранний сев, мелкая заделка 2–3 см.",
            "kz": "Майбұршақ зығыр: ерте себу, 2–3 см тайыз сіңіру.",
            "en": "Oilseed flax: early sowing, shallow 2–3 cm placement.",
        },
    },
}


def sowing_calendar(crop: str, lang: str = "ru") -> dict:
    """Справочное окно сева/уборки + GDD-норма для культуры.

    Возвращает dict: {crop, lang, sowing_window, harvest_window,
    gdd_norm, base_temp, note, source="agro-practice"}.
    Сеть/БД не используются.
    """
    lang = (lang or "ru").lower()
    if lang not in ("ru", "kz", "en"):
        raise ValueError(f"lang={lang!r} недопустим. Допустимо: ru, kz, en.")
    if crop not in _CALENDAR:
        raise ValueError(f"crop={crop!r} неизвестна. Допустимо: {sorted(_CALENDAR)}.")
    c = _CALENDAR[crop]
    return {
        "crop": crop,
        "lang": lang,
        "sowing_window": c["sowing"][lang],
        "harvest_window": c["harvest"][lang],
        "gdd_norm": list(c["gdd_norm"]),
        "gdd_base_temp": c["base_temp"],
        "note": c["note"][lang],
        "source": SOURCE,
    }


def all_calendars(lang: str = "ru") -> dict[str, dict]:
    """Весь справочник (6 культур) на языке lang."""
    return {c: sowing_calendar(c, lang) for c in CROPS}


if __name__ == "__main__":
    import json
    import sys

    _crop = sys.argv[1] if len(sys.argv) > 1 else "spring_wheat"
    _lang = sys.argv[2] if len(sys.argv) > 2 else "ru"
    print(json.dumps(sowing_calendar(_crop, _lang), ensure_ascii=False, indent=2))
