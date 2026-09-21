"""bot.py — Telegram-бот Qagro (aiogram 3.x).

Флоу: /start -> язык (EN/RU/KZ, inline) -> район (10 кнопок из
config/districts.yaml) -> культура (6) -> ответ <5 сек:
прогноз + интервал + светофор + страховка + рекомендация + кнопка PDF.

Токен ТОЛЬКО из env TELEGRAM_BOT_TOKEN (см. .env.example), хардкода нет.
Кэш: SQLite data/cache.db (риски Open-Meteo + готовые ответы, TTL 24ч).
Поллинг запускается только в main() — импорт модуля безопасен
(требование: только import-тест, без вечного поллинга).

Запуск (Windows PowerShell):
  $env:TELEGRAM_BOT_TOKEN="123:ABC"; python -m src.bot
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"
CACHE_DB = ROOT / "data" / "cache.db"
RISK_EXAMPLE = ROOT / "reports" / "risk_example.json"
FIELDS_GEOJSON = ROOT / "data" / "fields" / "akmola_osm_fields.geojson"
GRANARIES_JSON = ROOT / "data" / "fields" / "granaries.json"
CACHE_TTL = 24 * 3600
EARTH_R_KM = 6371.0088

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

try:  # пакетный импорт
    from src.alerts import check_alerts
    from src.approx_crops import ALL_CROPS
    from src.approx_crops import predict_approx
    from src.sowing_calendar import sowing_calendar
    from src.insurance import insurance_quote
    from src.predict import predict_yield
    from src.recommend import recommend_sowing
    from src.report_pdf import build_report_pdf
except ImportError:  # запуск из папки src/
    from alerts import check_alerts  # type: ignore
    from approx_crops import ALL_CROPS  # type: ignore
    from approx_crops import predict_approx  # type: ignore
    from sowing_calendar import sowing_calendar  # type: ignore
    from insurance import insurance_quote  # type: ignore
    from predict import predict_yield  # type: ignore
    from recommend import recommend_sowing  # type: ignore
    from report_pdf import build_report_pdf  # type: ignore

log = logging.getLogger("qagro.bot")

# ---------------------------------------------------------------- config
import yaml


def _load_cfg() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _districts() -> list[dict]:
    return _load_cfg().get("districts", [])


def _crops() -> list[dict]:
    return _load_cfg().get("crops", [])


CROP_IDS = ("spring_wheat", "barley", "oats", "sunflower", "rapeseed", "flax")

T: dict[str, dict[str, str]] = {
    "choose_lang": {"ru": "Выберите язык / Тілді таңдаңыз / Choose language:",
                    "kz": "Тілді таңдаңыз / Выберите язык / Choose language:",
                    "en": "Choose language / Выберите язык / Тілді таңдаңыз:"},
    "choose_district": {"ru": "Выберите район:",
                        "kz": "Ауданды таңдаңыз:",
                        "en": "Choose district:"},
    "choose_crop": {"ru": "Выберите культуру:",
                    "kz": "Дақылды таңдаңыз:",
                    "en": "Choose crop:"},
    "risk_offline": {"ru": "риск офлайн (светофор по p_loss)",
                     "kz": "тәуекел офлайн (p_loss бойынша бағдаршам)",
                     "en": "risk offline (p_loss-based light)"},
    # C3: дружелюбные тексты без смены логики
    "start_hello": {
        "ru": "🌾 Привет! Я Qagro — подскажу прогноз урожая в Акмолинской области.\n"
              "🌾 Сәлем! Мен Qagro — Ақмола облысы бойынша өнім болжамын беремін.\n"
              "🌾 Hello! I'm Qagro — yield forecast for Akmola region.\n"
              "Нажми /help для примеров 👇",
        "kz": "🌾 Сәлем! Мен Qagro — Ақмола облысы бойынша өнім болжамын беремін.\n"
              "🌾 Привет! Я Qagro — подскажу прогноз урожая в Акмолинской области.\n"
              "🌾 Hello! I'm Qagro — yield forecast for Akmola region.\n"
              "/help басыңыз 👇",
        "en": "🌾 Hello! I'm Qagro — yield forecast for Akmola region.\n"
              "🌾 Привет! Я Qagro — подскажу прогноз урожая в Акмолинской области.\n"
              "🌾 Сәлем! Мен Qagro — Ақмола облысы бойынша өнім болжамын беремін.\n"
              "Tap /help for examples 👇",
    },
    "err_no_district": {"ru": "Не нашел район, выбери кнопкой 👇",
                        "kz": "Аудан табылмады, батырмамен таңдаңыз 👇",
                        "en": "District not found, please choose with a button 👇"},
    "err_generic": {"ru": "😔 Что-то пошло не так. Попробуй ещё раз или нажми 🔄 Новый прогноз.",
                    "kz": "😔 Бірдеңе дұрыс болмады. Қайталап көріңіз немесе 🔄 Жаңа болжам басыңыз.",
                    "en": "😔 Something went wrong. Try again or tap 🔄 New forecast."},
    "err_offline": {"ru": "📡 Погода офлайн — показываю сохранённый прогноз. Риск примерный.",
                    "kz": "📡 Ауа райы офлайн — сақталған болжамды көрсетемін. Тәуекел шамамен.",
                    "en": "📡 Weather offline — showing saved forecast. Risk is approximate."},
    "exp_note": {"ru": "🧪 — пробный прогноз (мало данных), ориентируйся на среднее.",
                 "kz": "🧪 — сынақ болжам (дерек аз), орташа мәнге қараңыз.",
                 "en": "🧪 — trial forecast (little data), rely on the average."},
    "btn_new": {"ru": "🔄 Новый прогноз", "kz": "🔄 Жаңа болжам",
                "en": "🔄 New forecast"},
    "btn_pdf": {"ru": "📄 PDF отчет", "kz": "📄 PDF есеп",
                "en": "📄 PDF report"},
    # C8: алерты (только факты Open-Meteo, без подписок)
    "btn_alerts": {"ru": "⚠️ Алерты", "kz": "⚠️ Дабылдар",
                   "en": "⚠️ Alerts"},
    # C2: окно опрыскивания (кнопка в ответе прогноза) — локализовано
    "btn_spray": {"ru": "🧴 Опрыскивание", "kz": "🧴 Бүрку",
                  "en": "🧴 Spray"},
    "spray_hours": {"ru": "Хороших часов: {good} из {checked}.",
                    "kz": "Жақсы сағаттар: {checked} ішінен {good}.",
                    "en": "Good hours: {good} of {checked}."},
    "btn_sat": {"ru": "🛰 Спутник", "kz": "🛰 Серік",
                 "en": "🛰 Satellite"},
    "guide_hint": {"ru": "Опиши проблему словами: /guide саранча (можно: засуха, жара, заморозки, ржавчина)",
                   "kz": "Мәселені сөзбен жаз: /guide шегіртке (болады: құрғақшылық, ыстық, үсік, тат)",
                   "en": "Describe the issue: /guide locust (try: drought, heat, frost, rust)"},
    "btn_location": {"ru": "📍 Отправить местоположение",
                     "kz": "📍 Геолокацияны жіберу",
                     "en": "📍 Share Location"},
    "geo_ask": {"ru": "📍 Отправь геолокацию — найду район сам 👇",
                "kz": "📍 Геолокация жіберіңіз — ауданды өзім табамын 👇",
                "en": "📍 Send location — I'll find the district 👇"},
    "loc_district": {"ru": "📍 Ближайший район: {name} (~{km} км)",
                     "kz": "📍 Жақын аудан: {name} (~{km} км)",
                     "en": "📍 Nearest district: {name} (~{km} km)"},
    "loc_elev": {"ru": "🏭 Ближайший элеватор: {name} (~{km} км)",
                 "kz": "🏭 Жақын элеватор: {name} (~{km} км)",
                 "en": "🏭 Nearest elevator: {name} (~{km} km)"},
    "fields_res": {"ru": "🌾 Мои поля: всего {total} (проверено {osm}, пример {demo})\n{per}",
                   "kz": "🌾 Менің егістіктерім: барлығы {total} (тексерілген {osm}, үлгі {demo})\n{per}",
                   "en": "🌾 My fields: total {total} (verified {osm}, sample {demo})\n{per}"},
    "elevators_res": {"ru": "🏭 Элеваторы: {total}\n{names}\n(координаты примерные, карта Qoldau)",
                      "kz": "🏭 Элеваторлар: {total}\n{names}\n(координаттар шамамен, Qoldau картасы)",
                      "en": "🏭 Elevators: {total}\n{names}\n(coords approximate, Qoldau map)"},
    "alerts_none": {"ru": "✅ Угроз на 7 дней нет (заморозки/жара/ливни/суховей не найдены).",
                    "kz": "✅ 7 күнге қауіп жоқ (үсік/ыстық/нөсер/қуаң жел табылмады).",
                    "en": "✅ No threats for 7 days (no frost/heat/downpour/dry wind)."},
    "alerts_need": {"ru": "Сначала выбери район кнопкой 👇, потом /alerts.",
                    "kz": "Алдымен ауданды батырмамен таңдаңыз 👇, сосын /alerts.",
                    "en": "Choose district with a button 👇 first, then /alerts."},
}

HELP_TEXT: dict[str, str] = {
    "ru": ("🌾 Как получить прогноз:\n"
           "1. /start → выбери язык\n"
           "2. Выбери район кнопкой 👇 (10 районов Акмолы)\n"
           "3. Выбери культуру (пшеница, ячмень, овёс, подсолнечник, рапс🧪, лён🧪)\n"
           "4. Получи прогноз + риск 🟢🟡🔴 + кнопки 📄 PDF отчет / 🔄 Новый прогноз\n"
           "\nПримеры:\n"
           "• Есильский → Пшеница яровая\n"
           "• Отправь 📍 геолокацию — сам найду ближайший район\n"
           "• /about — о команде и источниках\n"
           "\nЕщё команды: /more\n"
           "\n🧪 — пробный прогноз (мало данных), ориентируйся на среднее."),
    "kz": ("🌾 Болжамды қалай алуға болады:\n"
           "1. /start → тілді таңдаңыз\n"
           "2. Ауданды батырмамен таңдаңыз 👇 (Ақмоланың 10 ауданы)\n"
           "3. Дақылды таңдаңыз (бидай, арпа, сұлы, күнбағыс, рапс🧪, зығыр🧪)\n"
           "4. Болжам + тәуекел 🟢🟡🔴 + 📄 PDF есеп / 🔄 Жаңа болжам батырмаларын алыңыз\n"
           "\nМысалдар:\n"
           "• Есіл → Жаздық бидай\n"
           "• 📍 Геолокация жіберіңіз — жақын ауданды өзім табамын\n"
           "• /about — команда мен дереккөздер туралы\n"
           "\nҚосымша командалар: /more\n"
           "\n🧪 — сынақ болжам (дерек аз), орташа мәнге қараңыз."),
    "en": ("🌾 How to get a forecast:\n"
           "1. /start → choose language\n"
           "2. Choose district with a button 👇 (10 Akmola districts)\n"
           "3. Choose crop (wheat, barley, oats, sunflower, rapeseed🧪, flax🧪)\n"
           "4. Get forecast + risk 🟢🟡🔴 + 📄 PDF report / 🔄 New forecast buttons\n"
           "\nExamples:\n"
           "• Esil → Spring wheat\n"
           "• Send 📍 location — I'll find the nearest district\n"
           "• /about — team & sources\n"
           "\nMore commands: /more\n"
           "\n🧪 — trial forecast (little data), rely on the average."),
}

MORE_TEXT: dict[str, str] = {
    "ru": ("🛠 Ещё команды:\n"
           "• /gis — поля со спутника (NDVI, залежи)\n"
           "• /spray — окно опрыскивания (ветер/дождь, 48ч)\n"
           "• /guide — опиши проблему: /guide саранча (засуха, жара, заморозки)\n"
           "• /fields — мои поля, /elevators — элеваторы\n"
           "• /alerts — угрозы 7 дней (заморозки/жара/ливни)\n"
           "• /compare — сравнить 2 культуры в районе\n"
           "• /about — о команде и источниках"),
    "kz": ("🛠 Қосымша командалар:\n"
           "• /gis — серіктен егістіктер (NDVI, тыңайған жер)\n"
           "• /spray — бүрку терезесі (жел/жаңбыр, 48с)\n"
           "• /guide — мәселені жаз: /guide шегіртке (құрғақшылық, ыстық, үсік)\n"
           "• /fields — менің егістіктерім, /elevators — элеваторлар\n"
           "• /alerts — 7 күндік қауіптер (үсік/ыстық/нөсер)\n"
           "• /compare — ауданда 2 дақылды салыстыру\n"
           "• /about — команда мен дереккөздер туралы"),
    "en": ("🛠 More commands:\n"
           "• /gis — satellite fields (NDVI, fallow)\n"
           "• /spray — spray window (wind/rain, 48h)\n"
           "• /guide — describe the issue: /guide locust (drought, heat, frost)\n"
           "• /fields — my fields, /elevators — elevators\n"
           "• /alerts — 7-day threats (frost/heat/downpour)\n"
           "• /compare — compare 2 crops in the district\n"
           "• /about — team & sources"),
}

ABOUT_TEXT: dict[str, str] = {
    "ru": ("🌾 Qagro — помощник фермера Акмолинской области (прогноз-2026).\n"
           "\nКоманда: Kairbek Ansar (данные / ML / API) и Samat Ablayhan, капитан (бот / веб).\n"
           "\nИсточники: Бюро нацстатистики РК, NASA POWER, Open-Meteo (ERA5), "
           "FAOSTAT, OpenStreetMap, Qoldau (элеваторы).\n"
           "\nПлатформа v4: мои поля, журнал работ, NPK-баланс, экономика.\n"
           "\n⚠️ Дисклеймер: это decision support, не гарантия урожая и не страховой тариф. "
           "Проверяй с агрономом."),
    "kz": ("🌾 Qagro — Ақмола облысы фермерінің көмекшісі (2026 болжам).\n"
           "\nКоманда: Kairbek Ansar (деректер / ML / API) және Samat Ablayhan, капитан (бот / веб).\n"
           "\nДереккөздер: ҚР Ұлттық статистика бюросы, NASA POWER, Open-Meteo (ERA5), "
           "FAOSTAT, OpenStreetMap, Qoldau (элеваторлар).\n"
           "\nv4 платформасы: менің егістіктерім, жұмыс журналы, NPK-баланс, экономика.\n"
           "\n⚠️ Дисклеймер: бұл decision support — өнім кепілдігі де, сақтандыру тарифі де емес. "
           "Агрономмен тексеріңіз."),
    "en": ("🌾 Qagro — farmer assistant for Akmola region (2026 forecast).\n"
           "\nTeam: Kairbek Ansar (data / ML / API) & Samat Ablayhan, captain (bot / web).\n"
           "\nSources: Bureau of National Statistics (KZ), NASA POWER, Open-Meteo (ERA5), "
           "FAOSTAT, OpenStreetMap, Qoldau (elevators).\n"
           "\nPlatform v4: my fields, work journal, NPK balance, economics.\n"
           "\n⚠️ Disclaimer: decision support only, not a yield guarantee nor an insurance tariff. "
           "Check with your agronomist."),
}

# ---------------------------------------------------------------- cache (SQLite)
def _db() -> sqlite3.Connection:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(CACHE_DB))
    con.execute("CREATE TABLE IF NOT EXISTS kv "
                "(key TEXT PRIMARY KEY, value TEXT, updated_at REAL)")
    return con


def cache_get(key: str, ttl: float = CACHE_TTL) -> Any | None:
    try:
        con = _db()
        row = con.execute("SELECT value, updated_at FROM kv WHERE key=?",
                          (key,)).fetchone()
        con.close()
        if not row:
            return None
        val, ts = row
        if time.time() - float(ts) > ttl:
            return None
        return json.loads(val)
    except Exception as e:
        log.debug("cache_get failed for %s: %s", key, e)
        return None


def cache_set(key: str, value: Any) -> None:
    try:
        con = _db()
        con.execute("INSERT OR REPLACE INTO kv(key,value,updated_at) VALUES(?,?,?)",
                    (key, json.dumps(value, ensure_ascii=False), time.time()))
        con.commit()
        con.close()
    except Exception as e:
        log.warning("cache_set failed: %s", e)


def _example_risk(district_en: str) -> dict | None:
    """Мгновенный fallback без сети: кэш из reports/risk_example.json."""
    try:
        if not RISK_EXAMPLE.exists():
            return None
        data = json.loads(RISK_EXAMPLE.read_text(encoding="utf-8"))
        r = data.get(f"{district_en}_risk")
        if r:
            return {**r, "cached": "risk_example.json"}
    except Exception as e:
        log.debug("example_risk failed for %s: %s", district_en, e)
    return None


def _risk_cached(district_en: str, year: int = 2026) -> dict | None:
    hit = cache_get(f"risk:{district_en}:{year}")
    if isinstance(hit, dict) and hit.get("seasonal_risk") is not None:
        return {**hit, "cached": True}
    return _example_risk(district_en)


def _risk_live(district_en: str, year: int = 2026) -> dict:
    from src.risk import decade_risk  # локальный импорт: без сети тоже импортируется
    return decade_risk(district_en, year)


async def _risk_bounded(district_en: str, year: int = 2026,
                        timeout: float = 3.5) -> dict:
    """Риск за <=timeout сек: сначала кэш, иначе 1 попытка live, иначе offline."""
    hit = await asyncio.to_thread(_risk_cached, district_en, year)
    if hit:
        return hit
    try:
        live = await asyncio.wait_for(
            asyncio.to_thread(_risk_live, district_en, year), timeout)
        cache_set(f"risk:{district_en}:{year}", live)
        return live
    except Exception as e:
        return {"district_en": district_en, "year": year,
                "seasonal_risk": None, "seasonal_light": None,
                "decades": [], "stages": {},
                "error": f"offline after {timeout}s: {type(e).__name__}: {e}"}


def _light_from_ploss(p_loss: float) -> str:
    if p_loss > 0.4:
        return "🔴"
    if p_loss > 0.2:
        return "🟡"
    return "🟢"


_COV: dict | None = None


def _coverage(crop: str) -> float | None:
    """Фактическое покрытие conformal-интервала (metrics/intervals.json, n=50)."""
    global _COV
    if _COV is None:
        try:
            _COV = json.loads((ROOT / "metrics" / "intervals.json").read_text(encoding="utf-8"))
        except Exception:
            _COV = {}
    try:
        return float(_COV.get(crop, {}).get("conformal_coverage"))
    except (TypeError, ValueError):
        return None


def _cov_line(crop: str, lang: str) -> str:
    cov = _coverage(crop)
    c = "—" if cov is None else f"{cov:.2f}"
    warn = ""
    if cov is not None and cov < 0.5:
        warn = {"ru": " Ориентируйтесь на среднее.",
                "kz": " Орташа мәнге сүйеніңіз.",
                "en": " Rely on the average."}.get(lang, "")
    return {"ru": f"Интервал «80%» — номинал; факт. покрытие {c} (n=50).{warn}",
            "kz": f"«80%» аралық — номинал; іс жүзінде {c} (n=50).{warn}",
            "en": f"“80%” interval is nominal; actual coverage {c} (n=50).{warn}"}.get(lang, "")


def _downscale_line(lang: str) -> str:
    return {"ru": "Район — даунскейлинг области на центроиды, не замеры полей.",
            "kz": "Аудан — облыстың центроидтарға даунскейлингі.",
            "en": "District downscales oblast stats onto centroids."}.get(lang, "")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def nearest_district(lat: float, lon: float) -> dict:
    """Ближайший район к (lat, lon) по центроидам districts.yaml (haversine)."""
    best: dict | None = None
    best_d = float("inf")
    for d in _districts():
        dist = haversine_km(lat, lon, float(d["lat"]), float(d["lon"]))
        if dist < best_d:
            best_d = dist
            best = d
    if best is None:
        raise ValueError("Нет районов в config/districts.yaml.")
    return {"district_en": best["name_en"], "district_ru": best.get("name_ru"),
            "dist_km": round(best_d, 1),
            "lat": best["lat"], "lon": best["lon"]}


def fields_summary() -> dict:
    """Число OSM полей: всего / OSM / demo. Без моков: нет файла — ошибка."""
    if not FIELDS_GEOJSON.exists():
        raise FileNotFoundError(
            f"{FIELDS_GEOJSON} не найден. Запустите: python src/fields_osm.py")
    fc = json.loads(FIELDS_GEOJSON.read_text(encoding="utf-8"))
    feats = fc.get("features", [])
    n_osm = sum(1 for f in feats if not (f.get("properties") or {}).get("demo"))
    n_demo = len(feats) - n_osm
    per: dict[str, int] = {}
    for f in feats:
        d = (f.get("properties") or {}).get("district_en", "?")
        per[d] = per.get(d, 0) + 1
    return {"total": len(feats), "osm": n_osm, "demo": n_demo, "per_district": per}


def elevators_summary() -> dict:
    """12 элеваторов: список + координаты (оценочные, Qoldau granaries-map)."""
    if not GRANARIES_JSON.exists():
        raise FileNotFoundError(f"{GRANARIES_JSON} не найден.")
    data = json.loads(GRANARIES_JSON.read_text(encoding="utf-8"))
    items = data.get("granaries", data) if isinstance(data, dict) else data
    return {"total": len(items), "elevators": items}


def nearest_elevator_for(lat: float, lon: float) -> dict:
    items = elevators_summary()["elevators"]
    best: dict | None = None
    best_d = float("inf")
    for g in items:
        d = haversine_km(lat, lon, float(g["lat"]), float(g["lon"]))
        if d < best_d:
            best_d = d
            best = g
    assert best is not None
    return {"name_ru": best.get("name_ru"), "name_en": best.get("name_en"),
            "dist_km": round(best_d, 1), "estimated": bool(best.get("estimated", True))}


def _predict(district_en: str, crop: str, weather: dict | None = None) -> dict:
    """v2: предпочитаем настоящий LGBM, если модель обучена; иначе APPROX."""
    try:
        return predict_yield(district_en, crop, weather)
    except FileNotFoundError:
        return predict_approx(district_en, crop, weather)


def compute_full(district_en: str, crop: str, lang: str = "ru",
                 risk: dict | None = None) -> dict:
    """Быстрые локальные вычисления (без сети): прогноз+страховка+совет."""
    pred = _predict(district_en, crop, None)  # климат-норма
    ins = insurance_quote(district_en, crop)
    rec = recommend_sowing(district_en, crop, lang)
    return {"pred": pred, "ins": ins, "rec": rec, "risk": risk or {}}


def _crop_name(crop: str, lang: str) -> str:
    """Локализованное название культуры из districts.yaml (без tech-id)."""
    try:
        for c in _crops():
            if c.get("id") == crop:
                return str(c.get(f"name_{lang}") or c.get("name_ru") or crop)
    except Exception:
        pass
    return crop


def _district_name(district_en: str, lang: str) -> str:
    """Локализованное название района (без tech-id)."""
    try:
        for d in _districts():
            if d.get("name_en") == district_en:
                return str(d.get(f"name_{lang}") or d.get("name_ru") or district_en)
    except Exception:
        pass
    return district_en


def _risk_word(light: str | None, lang: str) -> str:
    m = {"ru": {"🔴": "Высокий", "🟡": "Средний", "🟢": "Низкий"},
         "kz": {"🔴": "Жоғары", "🟡": "Орташа", "🟢": "Төмен"},
         "en": {"🔴": "High", "🟡": "Medium", "🟢": "Low"}}
    return m.get(lang, m["ru"]).get(light or "", "")


def _ploss_word(p_loss: float, lang: str) -> str:
    if p_loss > 0.4:
        return {"ru": "высокий", "kz": "жоғары", "en": "high"}[lang]
    if p_loss > 0.2:
        return {"ru": "средний", "kz": "орташа", "en": "medium"}[lang]
    return {"ru": "низкий", "kz": "төмен", "en": "low"}[lang]


def format_answer(district_en: str, crop: str, lang: str, full: dict) -> str:
    """Ответ простым языком для фермера на его языке (без жаргона).

    Структура: заголовок -> урожай -> риск -> страховка -> что делать.
    Никаких SHAP/residual/P_loss=0.23 в сыром виде, только слова и 1 цифра.
    """
    if lang not in ("ru", "kz", "en"):
        lang = "ru"
    pred, ins, rec, risk = full["pred"], full["ins"], full["rec"], full.get("risk") or {}
    experimental = bool(pred.get("experimental") or ins.get("experimental"))
    dname, cname = _district_name(district_en, lang), _crop_name(crop, lang)

    y = round(float(pred["y_pred"]), 1)
    lo, hi = round(float(pred["lo10"]), 1), round(float(pred["hi90"]), 1)
    mean5 = round(float(ins.get("mean5_c_ha") or y), 1)

    light = risk.get("seasonal_light")
    if light is None:  # офлайн: светофор по p_loss, честно помечаем ниже
        light = _light_from_ploss(float(ins["p_loss"]))
        offline = True
    else:
        offline = bool(risk.get("error") or risk.get("cached"))

    p_loss = float(ins["p_loss"])
    payout = int(round(float(ins.get("expected_payout_ha") or 0)))

    if lang == "kz":
        lines = [
            f"🌾 {dname} — {cname}, 2026",
            "",
            f"📈 Өнім: шамамен {y} ц/га (әдетте {lo}–{hi}).",
            f"{_cov_line(crop, lang)}",
            f"Соңғы 5 жылда орташа: {mean5} ц/га.",
            f"{'⚠️ Бұл әзірше тәжірибелік болжам — орташа мәнге сүйеніңіз.' if experimental else ''}",
            "",
            f"{light} Қауіпсіздік: {_risk_word(light, lang).lower()}." if light else "",
            f"{'📡 Интернет нашар — ескі дерекпен есептедім.' if offline else ''}",
            "",
            f"🛡 Сақтандыру: 80% өнім жинай алмау қаупі — {_ploss_word(p_loss, lang)} "
            f"(100-ден {round(p_loss * 100)} жағдай шамамен).",
            f"Осындай жағдайда төлем шамамен {payout} теңге/га. Бұл бағдар, тариф емес.",
            "",
            f"🌱 Себу: {rec['window']}. {rec['message']}",
            f"{_downscale_line(lang)}",
        ]
    elif lang == "en":
        lines = [
            f"🌾 {dname} — {cname}, 2026",
            "",
            f"📈 Yield: about {y} c/ha (usually {lo}–{hi}).",
            f"{_cov_line(crop, lang)}",
            f"5-year average: {mean5} c/ha.",
            f"{'⚠️ Experimental forecast — rely on the average.' if experimental else ''}",
            "",
            f"{light} Drought risk: {_risk_word(light, lang).lower()}." if light else "",
            f"{'📡 Weak internet — used saved data.' if offline else ''}",
            "",
            f"🛡 Insurance: risk of falling below 80% of average — {_ploss_word(p_loss, lang)} "
            f"(about {round(p_loss * 100)} in 100).",
            f"If it happens, payout ≈ {payout} tenge/ha. Estimate, not a tariff.",
            "",
            f"🌱 Sowing: {rec['window']}. {rec['message']}",
            f"{_downscale_line(lang)}",
        ]
    else:
        lines = [
            f"🌾 {dname} — {cname}, 2026",
            "",
            f"📈 Урожай: ждите около {y} ц/га (обычно бывает {lo}–{hi}).",
            f"{_cov_line(crop, lang)}",
            f"Среднее за 5 лет: {mean5} ц/га.",
            f"{'⚠️ Пока это пробный прогноз — ориентируйтесь на среднее.' if experimental else ''}",
            "",
            f"{light} Риск засухи: {_risk_word(light, lang).lower()}." if light else "",
            f"{'📡 Интернет слабый — посчитал по сохранённым данным.' if offline else ''}",
            "",
            f"🛡 Страховка: риск не добрать 80% среднего — {_ploss_word(p_loss, lang)} "
            f"(около {round(p_loss * 100)} случаев из 100).",
            f"Если случится — выплата примерно {payout} тенге/га. Это ориентир, не тариф.",
            "",
            f"🌱 Сев: {rec['window']}. {rec['message']}",
            f"{_downscale_line(lang)}",
        ]
    return "\n".join([ln for ln in lines if ln != ""]).strip()


def format_alerts(alerts: list, lang: str) -> str:
    """C8: текст алертов на языке lang (только факты, без спама)."""
    key = {"ru": "msg_ru", "kz": "msg_kz", "en": "msg_en"}.get(lang, "msg_ru")
    if not alerts:
        return T["alerts_none"].get(lang, T["alerts_none"]["ru"])
    return "\n".join(str(a.get(key) or a.get("msg_ru")) for a in alerts[:10])


# ---------------------------------------------------------------- aiogram app (lazy: только в main)
def create_dispatcher():
    from aiogram import Dispatcher, F
    from aiogram.filters import Command, CommandStart
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.types import (CallbackQuery, KeyboardButton, Message,
                               ReplyKeyboardMarkup)
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    class Form(StatesGroup):
        lang = State()
        district = State()
        crop = State()

    dp = Dispatcher()

    def _kb_location(lang: str = "ru"):
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=T["btn_location"].get(lang, T["btn_location"]["ru"]),
                                      request_location=True)]],
            resize_keyboard=True, one_time_keyboard=True)

    def _kb_langs():
        b = InlineKeyboardBuilder()
        b.button(text="🇬🇧 EN", callback_data="lang:en")
        b.button(text="🇷🇺 RU", callback_data="lang:ru")
        b.button(text="🇰🇿 KZ", callback_data="lang:kz")
        b.adjust(3)
        return b.as_markup()

    def _kb_districts(lang: str = "ru"):
        # UX: только имя на языке пользователя, 2 колонки (10 районов).
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        key = f"name_{lang}"
        b = InlineKeyboardBuilder()
        for d in _districts():
            b.button(text=str(d.get(key) or d.get("name_ru") or d.get("name_en")),
                     callback_data=f"dist:{d['name_en']}")
        b.adjust(2)
        return b.as_markup()

    def _kb_crops(lang: str):
        names = {c["id"]: c.get(f"name_{lang}", c.get("name_en", c["id"]))
                 for c in _crops()}
        b = InlineKeyboardBuilder()
        try:
            try:
                from src.approx_crops import is_approx
            except ImportError:
                from approx_crops import is_approx  # type: ignore
        except Exception:
            def is_approx(cid: str) -> bool:  # fallback v1
                return cid not in ("spring_wheat", "barley")
        try:
            try:
                from src.predict import is_experimental
            except ImportError:
                from predict import is_experimental  # type: ignore
        except Exception:
            def is_experimental(cid: str) -> bool:
                return False
        for cid in CROP_IDS:
            label = names.get(cid, cid)
            try:
                if is_approx(cid) or is_experimental(cid):
                    mark = " 🧪"
                else:
                    mark = ""
            except Exception:
                mark = ""
            b.button(text=f"{label}{mark}", callback_data=f"crop:{cid}")
        b.adjust(2)
        return b.as_markup()

    def _kb_pdf(district_en: str, crop: str, lang: str):
        # PDF + Алерты + Spray + Спутник + Новый прогноз
        b = InlineKeyboardBuilder()
        b.button(text=T["btn_pdf"].get(lang, T["btn_pdf"]["ru"]),
                 callback_data=f"pdf:{district_en}:{crop}:{lang}")
        b.button(text=T["btn_alerts"].get(lang, T["btn_alerts"]["ru"]),
                 callback_data=f"alerts:{district_en}:{lang}")
        b.button(text=T["btn_spray"].get(lang, T["btn_spray"]["ru"]),
                 callback_data=f"spray:{district_en}:{lang}")
        b.button(text=T["btn_sat"].get(lang, T["btn_sat"]["ru"]),
                 callback_data=f"sat:{district_en}:{lang}")
        b.button(text=T["btn_new"].get(lang, T["btn_new"]["ru"]),
                 callback_data="new")
        b.adjust(1)
        return b.as_markup()

    def _ndvi_verdict(n: float | None, lang: str) -> str:
        """Слово-вердикт к голому NDVI (аудит #10): число без вывода — не ответ."""
        if n is None:
            return {"ru": "нет данных", "kz": "дерек жоқ",
                    "en": "no data"}.get(lang, "нет данных")
        if n >= 0.5:
            return {"ru": "хорошо — проверять не надо",
                    "kz": "жақсы — тексеру қажет емес",
                    "en": "good — no need to check"}.get(lang, "")
        if n >= 0.35:
            return {"ru": "средне — посмотрите при случае",
                    "kz": "орташа — мүмкіндік болса қараңыз",
                    "en": "average — check if passing by"}.get(lang, "")
        return {"ru": "слабо — стоит съездить",
                "kz": "нашар — барған жөн",
                "en": "poor — worth a visit"}.get(lang, "")

    def _demo_mark(fl: dict, lang: str) -> str:
        if fl.get("demo"):
            return {"ru": " (пример)", "kz": " (үлгі)",
                    "en": " (sample)"}.get(lang, "")
        return ""

    def _render_gis(district_en: str, lang: str, g: dict, top_n: int = 3) -> str:
        """Общий текст топ-полей для /gis и кнопки 🛰 Спутник (max_fields=3)."""
        fields = sorted(g.get("fields", []),
                        key=lambda f: ((f.get("classification") or {}).get("ndvi_max")
                                       if (f.get("classification") or {}).get("ndvi_max") is not None else 9))

        def _nm(fl):
            c = fl.get("classification") or {}
            if lang == "kz":
                s = c.get("status_kz", c.get("status_ru", c.get("status")))
            elif lang == "en":
                s = c.get("status_en", c.get("status"))
            else:
                s = c.get("status_ru", c.get("status"))
            n = c.get("ndvi_max")
            v = _ndvi_verdict(n, lang)
            mark = _demo_mark(fl, lang)
            nn = "—" if n is None else round(float(n), 2)
            return (fl.get("field_id"), fl.get("area_ha"), s, nn, v, mark)
        dname = _district_name(district_en, lang)
        _no = {"ru": "Нет данных NDVI (все запросы неуспешны).",
               "kz": "NDVI дерегі жоқ (барлық сұрау сәтсіз).",
               "en": "No NDVI data (all requests failed)."}.get(lang, "")
        _fld = {"ru": "Поле", "kz": "Егістік", "en": "Field"}.get(lang, "Поле")

        def _line(num, i, a, s, n, v, dm, unit):
            if n == "—":
                return f"• {_fld} {num} ({i}{dm}, {a} {unit}): {_no}"
            return f"• {_fld} {num} ({i}{dm}, {a} {unit}): {s}, NDVI {n} — {v}"

        if lang == "kz":
            head = f"🛰 {dname}: {g.get('checked', 0)} егістік тексерілді."
            worst = [_line(num, i, a, s, n, v, dm, "га")
                     for num, (i, a, s, n, v, dm) in
                     enumerate((_nm(fl) for fl in fields[:top_n]), start=1)]
            tail = "Толығырақ — қосымшада «Карталар»."
        elif lang == "en":
            head = f"🛰 {dname}: {g.get('checked', 0)} fields checked."
            worst = [_line(num, i, a, s, n, v, dm, "ha")
                     for num, (i, a, s, n, v, dm) in
                     enumerate((_nm(fl) for fl in fields[:top_n]), start=1)]
            tail = "More — in the app Maps tab."
        else:
            head = f"🛰 {dname}: проверено полей — {g.get('checked', 0)}."
            worst = [_line(num, i, a, s, n, v, dm, "га")
                     for num, (i, a, s, n, v, dm) in
                     enumerate((_nm(fl) for fl in fields[:top_n]), start=1)]
            tail = "Подробнее — во вкладке «Карты» приложения."
        return "\n".join([head, "", *worst, "", tail])

    @dp.message(CommandStart())
    async def start(m: Message, state: FSMContext):
        await state.clear()
        await state.set_state(Form.lang)
        # 1 сообщение: привет (уже 3 языка по 1 строке) + выбор языка (inline).
        # 2 сообщение: reply-клавиатура геолокации (ограничение Telegram:
        # inline и reply нельзя в одном сообщении).
        await m.answer(f"{T['start_hello']['ru']}\n\n{T['choose_lang']['ru']}",
                       reply_markup=_kb_langs())
        await m.answer(f"{T['geo_ask']['ru']}\n{T['geo_ask']['kz']}\n{T['geo_ask']['en']}",
                       reply_markup=_kb_location("ru"))

    @dp.message(Command("help"))
    async def on_help(m: Message, state: FSMContext):
        # C3: новая команда, только тексты (язык из FSM, по умолчанию ru)
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in HELP_TEXT:
            lang = "ru"
        await m.answer(HELP_TEXT[lang])

    @dp.message(Command("about"))
    async def on_about(m: Message, state: FSMContext):
        # C3: новая команда, только тексты
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ABOUT_TEXT:
            lang = "ru"
        await m.answer(ABOUT_TEXT[lang])

    @dp.message(Command("more"))
    async def on_more(m: Message, state: FSMContext):
        # UX #7: полный список команд — отдельно, HELP остаётся коротким.
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in MORE_TEXT:
            lang = "ru"
        await m.answer(MORE_TEXT[lang])

    @dp.message(Command("fields"))
    async def on_fields(m: Message, state: FSMContext):
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        try:
            s = await asyncio.to_thread(fields_summary)
            per = ", ".join(f"{k}:{v}" for k, v in sorted(s["per_district"].items()))
            await m.answer(T["fields_res"][lang].format(
                total=s["total"], osm=s["osm"], demo=s["demo"], per=per))
        except Exception:
            log.exception("on_fields failed")
            await m.answer(f"{T['err_generic'][lang]} (код: E1)")

    @dp.message(Command("elevators"))
    async def on_elevators(m: Message, state: FSMContext):
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        try:
            s = await asyncio.to_thread(elevators_summary)
            name_key = {"ru": "name_ru", "kz": "name_ru", "en": "name_en"}[lang]
            names = "; ".join(
                f"{g.get(name_key) or g.get('name_en')} ({g.get('district_en')})"
                for g in s["elevators"])
            await m.answer(T["elevators_res"][lang].format(
                total=s["total"], names=names))
        except Exception:
            log.exception("on_elevators failed")
            await m.answer(f"{T['err_generic'][lang]} (код: E2)")

    @dp.message(Command("alerts"))
    async def on_alerts(m: Message, state: FSMContext):
        # C8: алерты по последнему району из FSM (без подписок/БД).
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        district = data.get("district")
        if not district:
            await m.answer(T["alerts_need"][lang],
                           reply_markup=_kb_districts(lang))
            return
        try:
            items = await asyncio.to_thread(check_alerts, district)
            dname = _district_name(district, lang)
            days = {"ru": "7 дней", "kz": "7 күн", "en": "7 days"}[lang]
            await m.answer(f"⚠️ {dname} ({days}):\n{format_alerts(items, lang)}")
        except Exception:
            log.exception("on_alerts failed")
            await m.answer(f"{T['err_generic'][lang]} (код: E3)")

    @dp.message(F.location)
    async def on_location(m: Message, state: FSMContext):
        try:
            loc = m.location
            hit = await asyncio.to_thread(
                nearest_district, float(loc.latitude), float(loc.longitude))
            elev = await asyncio.to_thread(
                nearest_elevator_for, float(loc.latitude), float(loc.longitude))
            data = await state.get_data()
            lang = data.get("lang", "ru")
            if lang not in ("ru", "kz", "en"):
                lang = "ru"
            await state.update_data(district=hit["district_en"])
            await state.set_state(Form.crop)
            dname = _district_name(hit["district_en"], lang)
            ename = elev.get("name_ru") if lang in ("ru", "kz") else elev.get("name_en")
            ename = ename or elev.get("name_en")
            _eest = {"ru": " (координаты примерные, Qoldau)",
                     "kz": " (координаттар шамамен, Qoldau)",
                     "en": " (coords approximate, Qoldau)"}[lang]
            await m.answer(
                f"{T['loc_district'][lang].format(name=dname, km=hit['dist_km'])}\n"
                f"{T['loc_elev'][lang].format(name=ename, km=elev['dist_km'])}{_eest}",
                reply_markup=_kb_crops(lang))
        except Exception:
            log.exception("on_location failed")
            data = await state.get_data()
            lang = data.get("lang", "ru")
            if lang not in ("ru", "kz", "en"):
                lang = "ru"
            await m.answer(f"{T['err_generic'][lang]} (код: E4)")

    @dp.callback_query(F.data.startswith("lang:"))
    async def on_lang(cb: CallbackQuery, state: FSMContext):
        lang = cb.data.split(":", 1)[1]
        await state.update_data(lang=lang)
        await state.set_state(Form.district)
        await cb.message.answer(T["choose_district"][lang],
                                reply_markup=_kb_districts(lang))
        await cb.answer()

    @dp.callback_query(F.data.startswith("dist:"))
    async def on_dist(cb: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        lang = data.get("lang", "ru")
        district = cb.data.split(":", 1)[1]
        await state.update_data(district=district)
        await state.set_state(Form.crop)
        await cb.message.answer(T["choose_crop"][lang],
                                reply_markup=_kb_crops(lang))
        await cb.answer()

    @dp.callback_query(F.data.startswith("crop:"))
    async def on_crop(cb: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        lang = data.get("lang", "ru")
        district = data.get("district")
        crop = cb.data.split(":", 1)[1]
        if not district:
            # C3: дружелюбно — район не выбран
            await cb.message.answer(f"{T['err_no_district'][lang]}",
                                    reply_markup=_kb_districts(lang))
            await cb.answer()
            return
        try:
            full_local = await asyncio.to_thread(compute_full, district, crop, lang)
            risk = await _risk_bounded(district, 2026, timeout=3.5)
            full = {**full_local, "risk": risk}
            cache_set(f"full:{district}:{crop}:{lang}", full)
            await state.update_data(crop=crop)
            text = format_answer(district, crop, lang, full)
            await cb.message.answer(text, reply_markup=_kb_pdf(district, crop, lang))
        except Exception:
            log.exception("on_crop failed")
            await cb.message.answer(f"{T['err_generic'][lang]} (код: E5)")
        await cb.answer()

    @dp.callback_query(F.data.startswith("alerts:"))
    async def on_alerts_cb(cb: CallbackQuery):
        # C8: кнопка ⚠️ Алерты из ответа прогноза.
        try:
            _, district, lang = cb.data.split(":")
        except ValueError:
            await cb.answer("bad callback")
            return
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        try:
            items = await asyncio.to_thread(check_alerts, district)
            dname = _district_name(district, lang)
            days = {"ru": "7 дней", "kz": "7 күн", "en": "7 days"}[lang]
            await cb.message.answer(f"⚠️ {dname} ({days}):\n{format_alerts(items, lang)}")
        except Exception:
            log.exception("on_alerts_cb failed")
            await cb.message.answer(f"{T['err_generic'][lang]} (код: E6)")
        await cb.answer()

    @dp.callback_query(F.data.startswith("spray:"))
    async def on_spray_cb(cb: CallbackQuery):
        # C2: кнопка из ответа прогноза.
        try:
            _, district, lang = cb.data.split(":")
        except ValueError:
            await cb.answer("bad callback")
            return
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        try:
            try:
                from src.spray import check_spray_window
            except ImportError:
                from spray import check_spray_window  # type: ignore
            r = await asyncio.to_thread(check_spray_window, district)
            key = {"ru": "verdict_ru", "kz": "verdict_kz", "en": "verdict_en"}[lang]
            dname = _district_name(district, lang)
            hours = T["spray_hours"][lang].format(
                good=r.get("good_count", "?"), checked=r.get("hours_checked", "?"))
            await cb.message.answer(f"🧴 {dname}: {r.get(key)}\n{hours}")
        except Exception:
            log.exception("on_spray_cb failed")
            await cb.message.answer(f"{T['err_generic'][lang]} (код: E7)")
        await cb.answer()

    @dp.callback_query(F.data.startswith("sat:"))
    async def on_sat_cb(cb: CallbackQuery):
        # Кнопка 🛰 Спутник из ответа прогноза: топ-3 поля района.
        try:
            _, district, lang = cb.data.split(":")
        except ValueError:
            await cb.answer("bad callback")
            return
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        try:
            try:
                from src.gis_monitor import run_district
            except ImportError:
                from gis_monitor import run_district  # type: ignore
            g = await asyncio.to_thread(run_district, district, 3)
            await cb.message.answer(_render_gis(district, lang, g, top_n=3))
        except Exception:
            log.exception("on_sat_cb failed")
            await cb.message.answer(f"{T['err_generic'][lang]} (код: E13)")
        await cb.answer()

    @dp.callback_query(F.data == "new")
    async def on_new(cb: CallbackQuery, state: FSMContext):
        # C3: кнопка 🔄 Новый прогноз — возврат к выбору района (логика не меняется)
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        await state.set_state(Form.district)
        await cb.message.answer(T["choose_district"][lang],
                                reply_markup=_kb_districts(lang))
        await cb.answer()

    @dp.callback_query(F.data.startswith("pdf:"))
    async def on_pdf(cb: CallbackQuery, state: FSMContext):
        try:
            _, district, crop, lang = cb.data.split(":")
        except ValueError:
            await cb.answer("bad callback")
            return
        try:
            full = cache_get(f"full:{district}:{crop}:{lang}") or \
                await asyncio.to_thread(compute_full, district, crop, lang,
                                        _risk_cached(district))
            cfg = _load_cfg()
            ru = next((d.get("name_ru") for d in cfg.get("districts", [])
                       if d.get("name_en") == district), None)
            # C8 best-effort: календарь/элеватор офлайн, алерты с таймаутом.
            try:
                cal = sowing_calendar(crop, lang)
            except Exception:
                cal = None
            try:
                items = await asyncio.wait_for(
                    asyncio.to_thread(check_alerts, district), timeout=8.0)
                a_err = None
            except Exception as e:
                items, a_err = None, f"{type(e).__name__}: {e}"
            try:
                cfg_d = next(d for d in _districts() if d["name_en"] == district)
                elev = nearest_elevator_for(float(cfg_d["lat"]), float(cfg_d["lon"]))
            except Exception:
                elev = None
            pdf = await asyncio.to_thread(
                build_report_pdf, district, crop, lang,
                full.get("pred"), full.get("ins"), full.get("risk"),
                full.get("rec"), ru, cal, items, a_err, elev)
            from aiogram.types import BufferedInputFile

            await cb.message.answer_document(
                BufferedInputFile(pdf, filename=f"qagro_{district}_{crop}.pdf"))
        except Exception:
            log.exception("on_pdf failed")
            if lang not in ("ru", "kz", "en"):
                lang = "ru"
            await cb.message.answer(f"{T['err_generic'][lang]} (код: E8)")
        await cb.answer()

    @dp.message(Command("spray"))
    async def on_spray(m: Message, state: FSMContext):
        # v4: окно опрыскивания по последнему району (живой Open-Meteo).
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        district = data.get("district")
        if not district:
            await m.answer(T["alerts_need"][lang], reply_markup=_kb_districts(lang))
            return
        try:
            try:
                from src.spray import check_spray_window
            except ImportError:
                from spray import check_spray_window  # type: ignore
            r = await asyncio.to_thread(check_spray_window, district)
            key = {"ru": "verdict_ru", "kz": "verdict_kz", "en": "verdict_en"}[lang]
            dname = _district_name(district, lang)
            hours = T["spray_hours"][lang].format(
                good=r.get("good_count", "?"), checked=r.get("hours_checked", "?"))
            await m.answer(f"🧴 {dname}: {r.get(key)}\n{hours}")
        except Exception:
            log.exception("on_spray failed")
            await m.answer(f"{T['err_generic'][lang]} (код: E9)")

    @dp.message(Command("guide"))
    async def on_guide(m: Message, state: FSMContext):
        # v4: справочник болезней/вредителей по последней культуре.
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        crop = data.get("crop", "spring_wheat")
        query = " ".join((m.text or "").split()[1:]).strip()
        try:
            try:
                from src.guide_data import lookup, search_guide, text_of
            except ImportError:
                from guide_data import lookup, search_guide, text_of  # type: ignore

            def _fmt(items: list) -> str:
                parts = []
                for it in items[:3]:
                    nm = text_of(it, "names", lang) or "—"
                    sg = text_of(it, "signs", lang) or []
                    ac = text_of(it, "action", lang) or "—"
                    parts.append(f"🔬 {nm}: {'; '.join(sg[:2])}. → {ac}")
                return "\n\n".join(parts)

            if query:
                # Жалоба словами: ищем релевантное, а не первые N справочника.
                found = search_guide(query, lang)
                if found:
                    await m.answer(_fmt(found))
                else:
                    await m.answer(f"{T['err_generic'][lang]}\n{T['guide_hint'][lang]}")
            else:
                items = lookup(crop)[:4]
                txt = _fmt(items)
                await m.answer(f"{txt}\n\n{T['guide_hint'][lang]}" if txt
                               else T["err_generic"][lang])
        except Exception:
            log.exception("on_guide failed")
            await m.answer(f"{T['err_generic'][lang]} (код: E10)")
        except Exception:
            log.exception("on_guide failed")
            await m.answer(f"{T['err_generic'][lang]} (код: E10)")

    @dp.message(Command("gis"))
    async def on_gis(m: Message, state: FSMContext):
        # Трек 1: топ проблемных полей района простым языком.
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        district = data.get("district")
        if not district:
            await m.answer(T["alerts_need"][lang], reply_markup=_kb_districts(lang))
            return
        try:
            try:
                from src.gis_monitor import run_district
            except ImportError:
                from gis_monitor import run_district  # type: ignore
            g = await asyncio.to_thread(run_district, district, 4)
            await m.answer(_render_gis(district, lang, g, top_n=3))
        except Exception:
            log.exception("on_gis failed")
            await m.answer(f"{T['err_generic'][lang]} (код: E11)")

    @dp.message(Command("compare"))
    async def on_compare(m: Message, state: FSMContext):
        # /compare: сравнение прогноза 2 культур в выбранном районе.
        # Без БД: переиспользуем _predict + insurance_quote (быстро, офлайн).
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        district = data.get("district")
        if not district:
            await m.answer(T["alerts_need"][lang], reply_markup=_kb_districts(lang))
            return
        aliases: dict[str, list[str]] = {
            "spring_wheat": ["spring_wheat", "пшеница", "пшеница яровая", "бидай",
                             "жаздық бидай", "wheat"],
            "barley": ["barley", "ячмень", "арпа"],
            "oats": ["oats", "овес", "овёс", "сұлы", "сулы"],
            "sunflower": ["sunflower", "подсолнечник", "күнбағыс", "кунбагыс"],
            "rapeseed": ["rapeseed", "рапс"],
            "flax": ["flax", "лен", "лён", "лен масличный", "зығыр"],
        }
        alias_to_crop = {a: cid for cid, lst in aliases.items() for a in lst}
        parts = (m.text or "").split()[1:]
        found: list[str] = []
        for p in parts:
            c = alias_to_crop.get(p.strip().lower())
            if c and c not in found:
                found.append(c)
        if len(found) == 0:
            found = ["spring_wheat", "barley"]
        elif len(found) == 1:
            other = "barley" if found[0] != "barley" else "spring_wheat"
            found = [found[0], other]
        else:
            found = found[:2]
        try:
            rows = []
            for cid in found:
                pred = await asyncio.to_thread(_predict, district, cid, None)
                ins = await asyncio.to_thread(insurance_quote, district, cid)
                y = round(float(pred["y_pred"]), 1)
                p = float(ins["p_loss"])
                light = _light_from_ploss(p)
                rows.append((cid, y, light, _ploss_word(p, lang), bool(
                    pred.get("experimental") or ins.get("experimental"))))
            dname = _district_name(district, lang)
            if lang == "kz":
                head = f"⚖️ {dname}: 2 дақылды салыстыру:"
                lines = [f"• {_crop_name(c, lang)} — ~{y} ц/га, қауіп {w} {lg}"
                         + (" 🧪" if exp else "")
                         for c, y, lg, w, exp in rows]
            elif lang == "en":
                head = f"⚖️ {dname}: compare 2 crops:"
                lines = [f"• {_crop_name(c, lang)} — ~{y} c/ha, risk {w} {lg}"
                         + (" 🧪" if exp else "")
                         for c, y, lg, w, exp in rows]
            else:
                head = f"⚖️ {dname}: сравнение 2 культур:"
                lines = [f"• {_crop_name(c, lang)} — ~{y} ц/га, риск {w} {lg}"
                         + (" 🧪" if exp else "")
                         for c, y, lg, w, exp in rows]
            best = max(rows, key=lambda r: r[1])
            if lang == "kz":
                tail = f"Қорытынды: {_crop_name(best[0], lang)} өнімі жоғары (~{best[1]} ц/га)."
            elif lang == "en":
                tail = f"Verdict: {_crop_name(best[0], lang)} yields more (~{best[1]} c/ha)."
            else:
                tail = f"Вывод: {_crop_name(best[0], lang)} выше (~{best[1]} ц/га)."
            await m.answer("\n".join([head, *lines, tail]))
        except Exception:
            log.exception("on_compare failed")
            await m.answer(f"{T['err_generic'][lang]} (код: E12)")

    @dp.message()
    async def on_unknown(m: Message, state: FSMContext):
        # C3: fallback для неизвестного текста/района — дружелюбно, без ломки логики
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        await m.answer(f"{T['err_no_district'][lang]}",
                       reply_markup=_kb_districts(lang))

    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token == "xxx":
        print("🌾 Qagro: токена бота нет — бот не запущен, это нормально.\n"
              "🌾 Qagro: бот токені жоқ — бот іске қосылмады, бұл қалыпты.\n"
              "🌾 Qagro: no bot token — bot not started, that's fine.\n"
              "\nRU: Возьми токен у @BotFather, скопируй .env.example в .env "
              "и вставь токен в TELEGRAM_BOT_TOKEN. Либо смотри веб-демо.\n"
              "KZ: @BotFather-ден токен алыңыз, .env.example-ді .env-ге көшіріп, "
              "TELEGRAM_BOT_TOKEN-ге қойыңыз. Немесе веб-демоны қараңыз.\n"
              "EN: Get a token from @BotFather, copy .env.example to .env "
              "and set TELEGRAM_BOT_TOKEN. Or try the web demo.")
        return
    try:
        from aiogram import Bot
    except ImportError:
        print("🌾 Qagro: нет пакета aiogram — поставь зависимости.\n"
              "🌾 Qagro: aiogram пакеті жоқ — тәуелділіктерді орнатыңыз.\n"
              "🌾 Qagro: aiogram package missing — install dependencies.\n"
              "\nRU: Запусти: pip install -r requirements.txt (нужен aiogram 3.x).\n"
              "KZ: Орындаңыз: pip install -r requirements.txt (aiogram 3.x керек).\n"
              "EN: Run: pip install -r requirements.txt (needs aiogram 3.x).")
        return

    dp = create_dispatcher()
    bot = Bot(token=token)
    log.info("Qagro bot polling…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
