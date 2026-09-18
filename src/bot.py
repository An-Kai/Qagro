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
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"
CACHE_DB = ROOT / "data" / "cache.db"
RISK_EXAMPLE = ROOT / "reports" / "risk_example.json"
CACHE_TTL = 24 * 3600

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

try:  # пакетный импорт
    from src.approx_crops import ALL_CROPS
    from src.approx_crops import predict_approx
    from src.insurance import insurance_quote
    from src.predict import predict_yield
    from src.recommend import recommend_sowing
    from src.report_pdf import build_report_pdf
except ImportError:  # запуск из папки src/
    from approx_crops import ALL_CROPS  # type: ignore
    from approx_crops import predict_approx  # type: ignore
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
    "choose_district": {"ru": "Выберите район:", "kz": "Ауданды таңдаңыз:",
                        "en": "Choose district:"},
    "choose_crop": {"ru": "Выберите культуру:", "kz": "Дақылды таңдаңыз:",
                    "en": "Choose crop:"},
    "risk_offline": {"ru": "риск офлайн (светофор по p_loss)",
                     "kz": "тәуекел офлайн (p_loss бойынша бағдаршам)",
                     "en": "risk offline (p_loss-based light)"},
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


def _predict(district_en: str, crop: str, weather: dict | None = None) -> dict:
    if crop in ("spring_wheat", "barley"):
        return predict_yield(district_en, crop, weather)
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
    tag = " [APPROX]" if approx else ""
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
    return "\n".join(lines)


# ---------------------------------------------------------------- aiogram app (lazy: только в main)
def create_dispatcher():
    from aiogram import Dispatcher, F
    from aiogram.filters import CommandStart
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.types import CallbackQuery, Message
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    class Form(StatesGroup):
        lang = State()
        district = State()
        crop = State()

    dp = Dispatcher()

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
        for cid in CROP_IDS:
            label = names.get(cid, cid)
            mark = " ~" if cid not in ("spring_wheat", "barley") else ""
            b.button(text=f"{label}{mark}", callback_data=f"crop:{cid}")
        b.adjust(2)
        approx_note = {"ru": " (~ = APPROX-оценка)",
                       "kz": " (~ = APPROX-баға)",
                       "en": " (~ = APPROX estimate)"}[lang]
        b.button(text=f"ℹ️{approx_note}", callback_data="noop")
        b.adjust(2, 1)
        return b.as_markup()

    def _kb_pdf(district_en: str, crop: str, lang: str):
        b = InlineKeyboardBuilder()
        b.button(text={"ru": "📄 PDF-отчёт", "kz": "📄 PDF-есеп",
                       "en": "📄 PDF report"}[lang],
                 callback_data=f"pdf:{district_en}:{crop}:{lang}")
        return b.as_markup()

    @dp.message(CommandStart())
    async def start(m: Message, state: FSMContext):
        await state.clear()
        await state.set_state(Form.lang)
        await m.answer(T["choose_lang"]["ru"], reply_markup=_kb_langs())

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
            await cb.message.answer(T["choose_district"][lang],
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
            await cb.message.answer(f"⚠️ Ошибка: {type(e).__name__}: {e}")
        await cb.answer()

    @dp.callback_query(F.data.startswith("pdf:"))
    async def on_pdf(cb: CallbackQuery, state: FSMContext):
        try:
            _, district, crop, lang = cb.data.split(":")
        except ValueError:
            await cb.answer("bad callback")
            return
        full = cache_get(f"full:{district}:{crop}:{lang}") or \
            await asyncio.to_thread(compute_full, district, crop, lang,
                                    _risk_cached(district))
        cfg = _load_cfg()
        ru = next((d.get("name_ru") for d in cfg.get("districts", [])
                   if d.get("name_en") == district), None)
        pdf = await asyncio.to_thread(
            build_report_pdf, district, crop, lang,
            full.get("pred"), full.get("ins"), full.get("risk"),
            full.get("rec"), ru)
        from aiogram.types import BufferedInputFile

        await cb.message.answer_document(
            BufferedInputFile(pdf, filename=f"qagro_{district}_{crop}.pdf"))
        await cb.answer()

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
