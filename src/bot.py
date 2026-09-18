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
    from src.calendar import sowing_calendar
    from src.insurance import insurance_quote
    from src.predict import predict_yield
    from src.recommend import recommend_sowing
    from src.report_pdf import build_report_pdf
except ImportError:  # запуск из папки src/
    from alerts import check_alerts  # type: ignore
    from approx_crops import ALL_CROPS  # type: ignore
    from approx_crops import predict_approx  # type: ignore
    from calendar import sowing_calendar  # type: ignore
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
    "exp_note": {"ru": "* — экспериментальный прогноз (мало данных), ориентируйся на среднее.",
                 "kz": "* — эксперименттік болжам (дерек аз), орташа мәнге қараңыз.",
                 "en": "* — experimental forecast (little data), rely on the average."},
    "btn_new": {"ru": "🔄 Новый прогноз", "kz": "🔄 Жаңа болжам",
                "en": "🔄 New forecast"},
    "btn_pdf": {"ru": "📄 PDF отчет", "kz": "📄 PDF есеп",
                "en": "📄 PDF report"},
    # C8: алерты (только факты Open-Meteo, без подписок)
    "btn_alerts": {"ru": "⚠️ Алерты", "kz": "⚠️ Дабылдар",
                   "en": "⚠️ Alerts"},
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
           "3. Выбери культуру (пшеница, ячмень, овёс, подсолнечник*, рапс*, лён*)\n"
           "4. Получи прогноз + риск 🟢🟡🔴 + кнопки 📄 PDF отчет / 🔄 Новый прогноз\n"
           "\nПримеры:\n"
           "• Есильский → Пшеница яровая\n"
           "• Отправь 📍 геолокацию — сам найду ближайший район\n"
           "• /about — о команде и источниках\n"
           "\n* — экспериментальный прогноз (мало данных), ориентируйся на среднее.\n"
           "~ — оценка от пшеницы (мало данных)."),
    "kz": ("🌾 Болжамды қалай алуға болады:\n"
           "1. /start → тілді таңдаңыз\n"
           "2. Ауданды батырмамен таңдаңыз 👇 (Ақмоланың 10 ауданы)\n"
           "3. Дақылды таңдаңыз (бидай, арпа, сұлы, күнбағыс*, рапс*, зығыр*)\n"
           "4. Болжам + тәуекел 🟢🟡🔴 + 📄 PDF есеп / 🔄 Жаңа болжам батырмаларын алыңыз\n"
           "\nМысалдар:\n"
           "• Есіл → Жаздық бидай\n"
           "• 📍 Геолокация жіберіңіз — жақын ауданды өзім табамын\n"
           "• /about — команда мен дереккөздер туралы\n"
           "\n* — эксперименттік болжам (дерек аз), орташа мәнге қараңыз.\n"
           "~ — бидайдан есептелген бағалау."),
    "en": ("🌾 How to get a forecast:\n"
           "1. /start → choose language\n"
           "2. Choose district with a button 👇 (10 Akmola districts)\n"
           "3. Choose crop (wheat, barley, oats, sunflower*, rapeseed*, flax*)\n"
           "4. Get forecast + risk 🟢🟡🔴 + 📄 PDF report / 🔄 New forecast buttons\n"
           "\nExamples:\n"
           "• Esil → Spring wheat\n"
           "• Send 📍 location — I'll find the nearest district\n"
           "• /about — team & sources\n"
           "\n* — experimental forecast (little data), rely on the average.\n"
           "~ — wheat-based estimate (little data)."),
}

ABOUT_TEXT: dict[str, str] = {
    "ru": ("🌾 Qagro — помощник фермера Акмолинской области (прогноз-2026).\n"
           "\nКоманда: Kairbek Ansar (данные / ML / API) и Samat Ablayhan, капитан (бот / веб).\n"
           "\nИсточники: Бюро нацстатистики РК, NASA POWER, Open-Meteo (ERA5), "
           "FAOSTAT, OpenStreetMap, Qoldau (элеваторы).\n"
           "\n⚠️ Дисклеймер: это decision support, не гарантия урожая и не страховой тариф. "
           "Проверяй с агрономом."),
    "kz": ("🌾 Qagro — Ақмола облысы фермерінің көмекшісі (2026 болжам).\n"
           "\nКоманда: Kairbek Ansar (деректер / ML / API) және Samat Ablayhan, капитан (бот / веб).\n"
           "\nДереккөздер: ҚР Ұлттық статистика бюросы, NASA POWER, Open-Meteo (ERA5), "
           "FAOSTAT, OpenStreetMap, Qoldau (элеваторлар).\n"
           "\n⚠️ Дисклеймер: бұл decision support — өнім кепілдігі де, сақтандыру тарифі де емес. "
           "Агрономмен тексеріңіз."),
    "en": ("🌾 Qagro — farmer assistant for Akmola region (2026 forecast).\n"
           "\nTeam: Kairbek Ansar (data / ML / API) & Samat Ablayhan, captain (bot / web).\n"
           "\nSources: Bureau of National Statistics (KZ), NASA POWER, Open-Meteo (ERA5), "
           "FAOSTAT, OpenStreetMap, Qoldau (elevators).\n"
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
    except Exception:
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
    except Exception:
        pass
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


def format_answer(district_en: str, crop: str, lang: str, full: dict) -> str:
    pred, ins, rec, risk = full["pred"], full["ins"], full["rec"], full.get("risk") or {}
    approx = bool(pred.get("approx") or ins.get("approx"))
    experimental = bool(pred.get("experimental") or ins.get("experimental"))
    tag = " [APPROX]" if approx else (" [EXPERIMENTAL baseline]" if experimental else "")
    light = risk.get("seasonal_light")
    srisk = risk.get("seasonal_risk")
    if light is None:  # offline-fallback: светофор по p_loss, честно помечаем
        light = _light_from_ploss(float(ins["p_loss"]))
        srisk = f"~{round(float(ins['p_loss']) * 100, 1)} ({T['risk_offline'][lang]})"
    head = {"ru": f"🌾 {district_en} / {crop}{tag} (2026)",
            "kz": f"🌾 {district_en} / {crop}{tag} (2026)",
            "en": f"🌾 {district_en} / {crop}{tag} (2026)"}[lang]
    lines = [
        head,
        f"📈 {pred['y_pred']} ц/га (80%: {pred['lo10']}–{pred['hi90']})",
        f"{light} риск: {srisk}",
        f"🛡 P_loss={ins['p_loss']}, payout≈{ins['expected_payout_ha']} ₸/га",
        f"🌱 {rec['window']}: {rec['message']}",
    ]
    if approx:
        lines.append("⚠️ APPROX: без обучающих данных (масштаб от пшеницы).")
    if experimental:
        lines.append("⚠️ EXPERIMENTAL baseline-5y: LGBM хуже бейзлайна на hold-out, интервал x1.5.")
        # C3: понятная фермеру подпись experimental
        lines.append(T["exp_note"].get(lang, T["exp_note"]["ru"]))
    if risk.get("error"):
        # C3: API offline — дружелюбно, без технического жаргона
        lines.append(T["err_offline"].get(lang, T["err_offline"]["ru"]))
    return "\n".join(lines)


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

    def _kb_location():
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Share Location",
                                      request_location=True)]],
            resize_keyboard=True, one_time_keyboard=True)

    def _kb_langs():
        b = InlineKeyboardBuilder()
        b.button(text="🇬🇧 EN", callback_data="lang:en")
        b.button(text="🇷🇺 RU", callback_data="lang:ru")
        b.button(text="🇰🇿 KZ", callback_data="lang:kz")
        b.adjust(3)
        return b.as_markup()

    def _kb_districts():
        b = InlineKeyboardBuilder()
        for d in _districts():
            b.button(text=f"{d['name_ru']} ({d['name_en']})",
                     callback_data=f"dist:{d['name_en']}")
        b.adjust(1)
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
                if is_approx(cid):
                    mark = " ~"
                elif is_experimental(cid):
                    mark = " *"
                else:
                    mark = ""
            except Exception:
                mark = ""
            b.button(text=f"{label}{mark}", callback_data=f"crop:{cid}")
        b.adjust(2)
        # C3: короткая подсказка про * и ~ (полная — в /help и в ответе)
        approx_note = {"ru": "ℹ️ * — мало данных, ~ — от пшеницы",
                       "kz": "ℹ️ * — дерек аз, ~ — бидайдан",
                       "en": "ℹ️ * — little data, ~ — from wheat"}[lang]
        b.button(text=f"{approx_note}", callback_data="noop")
        b.adjust(2, 1)
        return b.as_markup()

    def _kb_pdf(district_en: str, crop: str, lang: str):
        # C3: две кнопки — PDF отчет + Новый прогноз; C8: + Алерты
        b = InlineKeyboardBuilder()
        b.button(text=T["btn_pdf"].get(lang, T["btn_pdf"]["ru"]),
                 callback_data=f"pdf:{district_en}:{crop}:{lang}")
        b.button(text=T["btn_alerts"].get(lang, T["btn_alerts"]["ru"]),
                 callback_data=f"alerts:{district_en}:{lang}")
        b.button(text=T["btn_new"].get(lang, T["btn_new"]["ru"]),
                 callback_data="new")
        b.adjust(1)
        return b.as_markup()

    @dp.message(CommandStart())
    async def start(m: Message, state: FSMContext):
        await state.clear()
        await state.set_state(Form.lang)
        # C3: приветствие сразу на 3 языках + подсказка /help
        await m.answer(T["start_hello"]["ru"])
        await m.answer("📍 Отправь геолокацию — найду район сам / "
                       "Геолокация жіберіңіз — ауданды өзім табамын / "
                       "Send geolocation — I'll find the district:",
                       reply_markup=_kb_location())
        await m.answer(T["choose_lang"]["ru"], reply_markup=_kb_langs())

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

    @dp.message(Command("fields"))
    async def on_fields(m: Message, state: FSMContext):
        try:
            s = await asyncio.to_thread(fields_summary)
            per = ", ".join(f"{k}:{v}" for k, v in sorted(s["per_district"].items()))
            await m.answer(f"🌾 Fields: total {s['total']} "
                           f"(OSM {s['osm']}, demo {s['demo']})\n{per}")
        except Exception as e:
            data = await state.get_data()
            lang = data.get("lang", "ru")
            if lang not in ("ru", "kz", "en"):
                lang = "ru"
            await m.answer(f"{T['err_generic'][lang]}\n⚠️ {type(e).__name__}: {e}")

    @dp.message(Command("elevators"))
    async def on_elevators(m: Message, state: FSMContext):
        try:
            s = await asyncio.to_thread(elevators_summary)
            names = "; ".join(
                f"{g.get('name_en')} ({g.get('district_en')})"
                for g in s["elevators"])
            await m.answer(f"🏭 Elevators: {s['total']}\n{names}\n"
                           f"(coords estimated, Qoldau granaries-map)")
        except Exception as e:
            data = await state.get_data()
            lang = data.get("lang", "ru")
            if lang not in ("ru", "kz", "en"):
                lang = "ru"
            await m.answer(f"{T['err_generic'][lang]}\n⚠️ {type(e).__name__}: {e}")

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
                           reply_markup=_kb_districts())
            return
        try:
            items = await asyncio.to_thread(check_alerts, district)
            await m.answer(f"⚠️ {district} (7d):\n{format_alerts(items, lang)}")
        except Exception as e:
            await m.answer(f"{T['err_generic'][lang]}\n⚠️ {type(e).__name__}: {e}")

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
            await state.update_data(district=hit["district_en"])
            await state.set_state(Form.crop)
            await m.answer(
                f"📍 Nearest district: {hit['district_ru']} ({hit['district_en']}), "
                f"~{hit['dist_km']} km\n"
                f"🏭 Nearest elevator: {elev['name_en']} (~{elev['dist_km']} km)",
                reply_markup=_kb_crops(lang))
        except Exception as e:
            log.exception("on_location failed")
            data = await state.get_data()
            lang = data.get("lang", "ru")
            if lang not in ("ru", "kz", "en"):
                lang = "ru"
            await m.answer(f"{T['err_generic'][lang]}\n⚠️ {type(e).__name__}: {e}")

    @dp.callback_query(F.data.startswith("lang:"))
    async def on_lang(cb: CallbackQuery, state: FSMContext):
        lang = cb.data.split(":", 1)[1]
        await state.update_data(lang=lang)
        await state.set_state(Form.district)
        await cb.message.answer(T["choose_district"][lang],
                                reply_markup=_kb_districts())
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

    @dp.callback_query(F.data == "noop")
    async def on_noop(cb: CallbackQuery):
        await cb.answer()

    @dp.callback_query(F.data.startswith("crop:"))
    async def on_crop(cb: CallbackQuery, state: FSMContext):
        t0 = time.time()
        data = await state.get_data()
        lang = data.get("lang", "ru")
        district = data.get("district")
        crop = cb.data.split(":", 1)[1]
        if not district:
            # C3: дружелюбно — район не выбран
            await cb.message.answer(f"{T['err_no_district'][lang]}",
                                    reply_markup=_kb_districts())
            await cb.answer()
            return
        try:
            full_local = await asyncio.to_thread(compute_full, district, crop, lang)
            risk = await _risk_bounded(district, 2026, timeout=3.5)
            full = {**full_local, "risk": risk}
            cache_set(f"full:{district}:{crop}:{lang}", full)
            text = format_answer(district, crop, lang, full)
            dt = time.time() - t0
            text += f"\n⏱ {dt:.1f}s"
            await cb.message.answer(text, reply_markup=_kb_pdf(district, crop, lang))
        except Exception as e:
            log.exception("on_crop failed")
            await cb.message.answer(f"{T['err_generic'][lang]}\n⚠️ {type(e).__name__}: {e}")
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
            await cb.message.answer(f"⚠️ {district} (7d):\n{format_alerts(items, lang)}")
        except Exception as e:
            log.exception("on_alerts_cb failed")
            await cb.message.answer(f"{T['err_generic'][lang]}\n⚠️ {type(e).__name__}: {e}")
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
                                reply_markup=_kb_districts())
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
        except Exception as e:
            log.exception("on_pdf failed")
            if lang not in ("ru", "kz", "en"):
                lang = "ru"
            await cb.message.answer(f"{T['err_generic'][lang]}\n⚠️ {type(e).__name__}: {e}")
        await cb.answer()

    @dp.message()
    async def on_unknown(m: Message, state: FSMContext):
        # C3: fallback для неизвестного текста/района — дружелюбно, без ломки логики
        data = await state.get_data()
        lang = data.get("lang", "ru")
        if lang not in ("ru", "kz", "en"):
            lang = "ru"
        await m.answer(f"{T['err_no_district'][lang]}",
                       reply_markup=_kb_districts())

    return dp


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token == "xxx":
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN: задайте env "
                         "(см. .env.example). Хардкод токена запрещён.")
    from aiogram import Bot

    dp = create_dispatcher()
    bot = Bot(token=token)
    log.info("Qagro bot polling…")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
