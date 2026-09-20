"""Streamlit-дашборд Qagro — версия для обычного фермера (v3).

Принципы: 3 шага (район -> культура -> ответ словами), весь интерфейс на
выбранном языке RU/KZ/EN, цифры только понятные (ц/га, тенге/га),
технические детали (MAE/RMSE/SHAP) спрятаны в "Подробно для агронома".

Карты: риски по районам + таблица, поля OSM/demo с фильтром и статистикой,
элеваторы + маршруты район->элеватор, точки NDVI Sentinel-2.

Запуск: python -m streamlit run app/streamlit_app.py (или run_web.bat)
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import streamlit as st
except ImportError:  # pragma: no cover — только для проверок без streamlit
    class _CacheNoop:
        def __call__(self, *a, **k):
            if len(a) == 1 and callable(a[0]) and not k:
                return a[0]

            def deco(f):
                return f

            return deco

    class _RuntimeStub:
        @staticmethod
        def exists() -> bool:
            return False

    class _StStub:
        cache_data = _CacheNoop()
        runtime = _RuntimeStub()

    st = _StStub()  # type: ignore

try:
    _ST_RUN = bool(st.runtime.exists())
except Exception:
    _ST_RUN = False

import pandas as pd
import yaml

try:
    from src.approx_crops import APPROX_YIELD_FACTOR, is_approx
    from src.approx_crops import predict_approx
    from src.alerts import check_alerts
    from src.sowing_calendar import sowing_calendar
    from src.insurance import insurance_quote
    from src.predict import predict_yield
    from src.recommend import recommend_sowing
    from src.report_pdf import build_report_pdf
except ImportError:  # запуск с другой cwd
    from alerts import check_alerts  # type: ignore
    from approx_crops import APPROX_YIELD_FACTOR, is_approx  # type: ignore
    from approx_crops import predict_approx  # type: ignore
    from sowing_calendar import sowing_calendar  # type: ignore
    from insurance import insurance_quote  # type: ignore
    from predict import predict_yield  # type: ignore
    from recommend import recommend_sowing  # type: ignore
    from report_pdf import build_report_pdf  # type: ignore

PANEL = ROOT / "data" / "processed" / "akmola_panel.csv"
PANEL_V3 = ROOT / "data" / "processed" / "akmola_panel_v3.csv"
METRICS = ROOT / "metrics" / "metrics.json"
RISK_EXAMPLE = ROOT / "reports" / "risk_example.json"
FIELDS_GEOJSON = ROOT / "data" / "fields" / "akmola_osm_fields.geojson"
GRANARIES_JSON = ROOT / "data" / "fields" / "granaries.json"
NDVI_JSON = ROOT / "data" / "ndvi" / "ndvi_timeseries.json"

CROP_ORDER = ("spring_wheat", "barley", "oats",
              "sunflower", "rapeseed", "flax")
CROP_ICON = {"spring_wheat": "🌾", "barley": "🌾", "oats": "🌾",
             "sunflower": "🌻", "rapeseed": "🌼", "flax": "🌿"}
WHEAT_PRICE_MIN, WHEAT_PRICE_MAX, WHEAT_PRICE_DEFAULT = 70000, 130000, 95000

UI = {
    "ru": {"title": "🌾 Qagro — помощник фермера",
           "sub": "Выберите район и культуру — получите ответ простыми словами.",
           "step1": "Шаг 1. Ваш район", "step2": "Шаг 2. Культура",
           "step3": "Шаг 3. Ваш ответ", "yield": "Урожай",
           "risk": "Риск засухи", "ins": "Страховка", "todo": "Что делать",
           "detail": "Подробно для агронома (цифры модели)",
           "low": "низкий", "mid": "средний", "high": "высокий",
           "maps": "🗺 Карты", "agro": "📊 Для агронома", "cal": "📅 Календарь и алерты",
           "about": "ℹ О проекте", "price": "Цена зерна (тенге/т)",
           "download": "Скачать отчёт PDF", "csv": "⬇️ CSV история",
           "geo": "⬇️ GeoJSON районы+риски", "no_threat": "✅ Угроз на 7 дней нет.",
           "exp": "⚠️ Пробный прогноз — ориентируйтесь на среднее за 5 лет.",
           "offline": "📡 Интернет слабый — посчитано по сохранённым данным.",
           "step1_hint": "Если не знаете район — отправьте геолокацию в Telegram-боте, он подскажет район.",
           "step2_hint": "Значок 🧪 — пробный прогноз: ориентируйтесь на среднее за 5 лет.",
           "district_help": "Выберите район хозяйства. От него зависят прогноз, риски и элеватор.",
           "crop_help": "Выберите культуру. Страховка считается для пшеницы и ячменя.",
           "price_help": "Влияет только на расчёт страховки и прибыли, прогноз урожая не меняет.",
           "farm": "🚜 Моё хозяйство", "plus": "🔬 Справочник и деньги",
           "risk_tab": "Риски", "fields_tab": "Поля и элеваторы",
           "legend": "🟢<35 🟡35–60 🔴>60 | 🟣 NDVI Sentinel-2 (июнь 2024).",
           "my_fields": "моих полей", "my_empty": "Полей пока нет — добавьте первое ниже 👇",
           "field_name": "Название поля", "field_name_help": "Например: Поле у речки. Видно только вам.",
           "field_area": "Площадь (га)", "field_area_help": "От 1 до 2000 га. Нужно для выплат на всё поле.",
           "field_add": "➕ Добавить поле", "added_ok": "Поле добавлено ✅",
           "pick_field": "Поле", "pick_field_help": "К какому полю относится заметка.",
           "pick_problem": "Проблема", "pick_problem_help": "Тип проблемы — поможет агроному.",
           "note_text": "Заметка", "note_text_help": "Коротко: что увидели и где на поле.",
           "note_add": "📝 Сохранить заметку", "note_added": "Заметка сохранена ✅",
           "need_field_first": "Сначала добавьте поле — тогда можно вести журнал.",
           "del_help": "Удалить поле",
           "km": "км", "ha": "га",
           "spray_offline": "Окно опрыскивания офлайн",
           "goal": "🎯 Цель по урожаю (ц/га)", "goal_help": "Для расчёта NPK под вашу цель.",
            "osm_empty": "В этом районе OSM-полей нет — показаны элеваторы и маршруты.",
            "hist_empty": "История пуста для этого района/культуры.",
            "guide_empty": "Справочник пуст для этой культуры.",
            "risk_empty": "Файл рисков не найден — таблица посчитана из прогноза модели (офлайн).",
            "ndvi_empty": "NDVI-замеров с ndvi_mean пока нет.",
            "fields_file_empty": "Файл полей не найден — показаны только элеваторы.",
            "elev_offline": "Ближайший элеватор не определился.",
            "usual": "Обычно бывает {lo}–{hi}. Среднее за 5 лет: {mean5}.",
            "risk_hint": "Зелёный — спокойно, жёлтый — следите, красный — готовьтесь.",
            "payout_hint": "Шанс не добрать 80%: {pct} из 100. Это ориентир, не тариф.",
            "dcode": "Код района",
            "fields_summary": "полей в районе (OSM: {osm}, demo: {demo}), всего ~{area} га",
            "gis_title": "Мониторинг всходов со спутника (Sentinel-2)",
            "gis_sub": "Зелёный ход — посевы растут; ровный низкий — проверьте поле. Пороги эвристические, не ГОСТ.",
            "gis_manual": "Copernicus Browser / Sentinel Hub / LandsatLook — для ручной проверки.",
            "gis_checked": "Проверено {done} из {total}.",
            "gis_borders": "Границы и площади — OSM (экспорт GeoJSON во вкладке прогноза).",
            "gis_offline": "🛰 Спутник офлайн: {err}",
            "gis_dead": "погибших дат",
            "axis_year": "год", "axis_yield": "ц/га",
            "trace_fact": "факт", "trace_forecast": "прогноз 2026",
            "ndvi_x": "дата", "ndvi_y": "NDVI",
            "field_default": "Поле 1",
            "sow_label": "Посев", "harvest_label": "Уборка",
            "sat_tab": "Со спутника",
            "about1": "**Qagro** — Кайрбек Ансар (данные/ML/API) + Самат Аблайхан, капитан (бот/веб).",
            "about2": "stat.gov.kz · NASA POWER · Open-Meteo · FAOSTAT · OSM · Qoldau · Copernicus/Sentinel-2",
            "th_district": "Район", "th_code": "Код", "th_risk": "Риск (0–100)",
            "compare": "⚖️ Сравнение культур",
            "compare_hint": "Выберите 2–4 культуры — сравним урожай, риск и выплату.",
            "compare_pick": "Культуры для сравнения",
            "compare_need": "Выберите от 2 до 4 культур ☝️",
            "cc_crop": "Культура", "cc_yield": "Урожай, ц/га",
            "cc_risk": "Риск", "cc_payout": "Выплата, ₸/га",
            "cc_verdict": "Вывод",
            "verdict_best": "лучший урожай", "verdict_calm": "самый спокойный",
            "verdict_mid": "средний вариант",
            "compare_chart_title": "Урожай по культурам",
            "compare_chart_yield": "Урожай, ц/га",
            "compare_chart_payout": "Выплата, тыс. ₸/га",
            "season_gdd": "Рост сезона (тепло)",
            "season_gdd_text": "Накоплено ~{fact} из нормы {lo}–{hi} (база {base}°C).",
            "season_spray": "Окна опрыскивания (48 ч)",
            "season_spray_none": "Хороших часов нет — опрыскивание отложить.",
            "alias_src": "Источник", "ms": "м/с",
            "lang_label": "🌍 Язык / Тіл / Language"},
    "kz": {"title": "🌾 Qagro — фермер көмекшісі",
           "sub": "Аудан мен дақылды таңдаңыз — жауапты қарапайым тілде алыңыз.",
           "step1": "1-қадам. Ауданыңыз", "step2": "2-қадам. Дақыл",
           "step3": "3-қадам. Сіздің жауабыңыз", "yield": "Өнім",
           "risk": "Құрғақшылық қаупі", "ins": "Сақтандыру", "todo": "Не істеу керек",
           "detail": "Агрономға арналған сандар",
           "low": "төмен", "mid": "орташа", "high": "жоғары",
           "maps": "🗺 Карталар", "agro": "📊 Агрономға", "cal": "📅 Күнтізбе және дабылдар",
           "about": "ℹ Жоба туралы", "price": "Астық бағасы (теңге/т)",
           "download": "PDF есепті жүктеу", "csv": "⬇️ CSV тарих",
           "geo": "⬇️ GeoJSON аудандар+қауіп", "no_threat": "✅ 7 күнге қауіп жоқ.",
           "exp": "⚠️ Сынақ болжамы — 5 жылдық орташаға сүйеніңіз.",
           "offline": "📡 Интернет нашар — сақталған дерекпен есептелді.",
           "step1_hint": "Ауданды білмесеңіз — Telegram-ботқа геолокация жіберіңіз, ауданды айтады.",
           "step2_hint": "🧪 белгісі — сынақ болжам: 5 жылдық орташаға қараңыз.",
           "district_help": "Шаруашылық ауданын таңдаңыз. Болжам, қауіп және элеватор соған байланысты.",
           "crop_help": "Дақылды таңдаңыз. Сақтандыру бидай мен арпаға есептеледі.",
           "price_help": "Тек сақтандыру мен пайдаға әсер етеді, өнім болжамын өзгертпейді.",
           "farm": "🚜 Менің шаруашылығым", "plus": "🔬 Анықтама және ақша",
           "risk_tab": "Қауіптер", "fields_tab": "Егістік және элеваторлар",
           "legend": "🟢<35 🟡35–60 🔴>60 | 🟣 NDVI Sentinel-2 (маусым 2024).",
           "my_fields": "менің егістігім", "my_empty": "Егістік әзірге жоқ — төменнен біріншісін қосыңыз 👇",
           "field_name": "Егістік атауы", "field_name_help": "Мысалы: Өзен жанындағы егіс. Тек сізге көрінеді.",
           "field_area": "Ауданы (га)", "field_area_help": "1–2000 га. Төлемді бүкіл егіске есептеуге керек.",
           "field_add": "➕ Егістік қосу", "added_ok": "Егістік қосылды ✅",
           "pick_field": "Егістік", "pick_field_help": "Жазба қай егіске қатысты.",
           "pick_problem": "Мәселе", "pick_problem_help": "Мәселе түрі — агрономға көмектеседі.",
           "note_text": "Жазба", "note_text_help": "Қысқаша: не көрдіңіз, егістің қай жерінде.",
           "note_add": "📝 Жазбаны сақтау", "note_added": "Жазба сақталды ✅",
           "need_field_first": "Алдымен егістік қосыңыз — содан кейін журнал жүргізе аласыз.",
           "del_help": "Егістікті жою",
           "km": "км", "ha": "га",
           "spray_offline": "Бүрку терезесі офлайн",
           "goal": "🎯 Өнім мақсаты (ц/га)", "goal_help": "Мақсатыңызға NPK есептеу үшін.",
            "osm_empty": "Бұл ауданда OSM-егістік жоқ — элеваторлар мен бағыттар көрсетілген.",
            "hist_empty": "Бұл аудан/дақыл үшін тарих бос.",
            "guide_empty": "Бұл дақылға анықтама бос.",
            "risk_empty": "Қауіп файлы табылмады — кесте модель болжамынан есептелді (офлайн).",
            "ndvi_empty": "ndvi_mean өлшемдері әзірге жоқ.",
            "fields_file_empty": "Егістік файлы табылмады — тек элеваторлар көрсетілген.",
            "elev_offline": "Жақын элеватор анықталмады.",
            "usual": "Әдетте {lo}–{hi}. 5 жылдық орташа: {mean5}.",
            "risk_hint": "Жасыл — тыныш, сары — бақылаңыз, қызыл — дайындалыңыз.",
            "payout_hint": "80%-ға жетпеу: 100-ден {pct}. Бұл бағдар, тариф емес.",
            "dcode": "Аудан коды",
            "fields_summary": "аудандағы егістік (OSM: {osm}, demo: {demo}), барлығы ~{area} га",
            "gis_title": "Серіктен өскін мониторингі (Sentinel-2)",
            "gis_sub": "Жасыл өсу — егін өсуде; тегіс төмен — егістікті тексеріңіз.",
            "gis_manual": "Copernicus Browser / Sentinel Hub / LandsatLook — қолмен тексеруге.",
            "gis_checked": "Тексерілді {done} / {total}.",
            "gis_borders": "Шекаралар мен аудандар — OSM (болжам қойындысында GeoJSON экспорт).",
            "gis_offline": "🛰 Серік офлайн: {err}",
            "gis_dead": "өлген күндер",
            "axis_year": "жыл", "axis_yield": "ц/га",
            "trace_fact": "факт", "trace_forecast": "болжам 2026",
            "ndvi_x": "күн", "ndvi_y": "NDVI",
            "field_default": "1-егістік",
            "sow_label": "Себу", "harvest_label": "Жинау",
            "sat_tab": "Серіктен",
            "about1": "**Qagro** — Қайырбек Ансар (дерек/ML/API) + Самат Аблайхан, капитан (бот/веб).",
            "about2": "stat.gov.kz · NASA POWER · Open-Meteo · FAOSTAT · OSM · Qoldau · Copernicus/Sentinel-2",
            "th_district": "Аудан", "th_code": "Код", "th_risk": "Қауіп (0–100)",
            "compare": "⚖️ Дақылдарды салыстыру",
            "compare_hint": "2–4 дақыл таңдаңыз — өнім, қауіп және төлемді салыстырамыз.",
            "compare_pick": "Салыстыруға дақылдар",
            "compare_need": "2–4 дақыл таңдаңыз ☝️",
            "cc_crop": "Дақыл", "cc_yield": "Өнім, ц/га",
            "cc_risk": "Қауіп", "cc_payout": "Төлем, ₸/га",
            "cc_verdict": "Қорытынды",
            "verdict_best": "ең жоғары өнім", "verdict_calm": "ең тыныш",
            "verdict_mid": "орташа нұсқа",
            "compare_chart_title": "Дақылдар бойынша өнім",
            "compare_chart_yield": "Өнім, ц/га",
            "compare_chart_payout": "Төлем, мың ₸/га",
            "season_gdd": "Маусым өсуі (жылу)",
            "season_gdd_text": "Жинақталды ~{fact}, норма {lo}–{hi} (база {base}°C).",
            "season_spray": "Бүрку терезелері (48 сағ)",
            "season_spray_none": "Жақсы сағаттар жоқ — бүркуді кейінге қалдырыңыз.",
            "alias_src": "Дереккөз", "ms": "м/с",
            "lang_label": "🌍 Язык / Тіл / Language"},
    "en": {"title": "🌾 Qagro — farmer helper",
           "sub": "Pick your district and crop — get a plain-words answer.",
           "step1": "Step 1. Your district", "step2": "Step 2. Crop",
           "step3": "Step 3. Your answer", "yield": "Yield",
           "risk": "Drought risk", "ins": "Insurance", "todo": "What to do",
           "detail": "Details for the agronomist (model numbers)",
           "low": "low", "mid": "medium", "high": "high",
           "maps": "🗺 Maps", "agro": "📊 For agronomist", "cal": "📅 Calendar & alerts",
           "about": "ℹ About", "price": "Grain price (tenge/t)",
           "download": "Download PDF report", "csv": "⬇️ CSV history",
           "geo": "⬇️ GeoJSON districts+risk", "no_threat": "✅ No threats for 7 days.",
           "exp": "⚠️ Experimental forecast — rely on the 5-year average.",
           "offline": "📡 Weak internet — used saved data.",
           "step1_hint": "Don't know your district? Send geolocation to the Telegram bot, it will tell you.",
           "step2_hint": "🧪 means experimental forecast: rely on the 5-year average.",
           "district_help": "Pick your farm district. Forecast, risks and elevator depend on it.",
           "crop_help": "Pick a crop. Insurance is calculated for wheat and barley.",
           "price_help": "Affects only insurance and profit, not the yield forecast.",
           "farm": "🚜 My farm", "plus": "🔬 Guide & money",
           "risk_tab": "Risks", "fields_tab": "Fields & elevators",
           "legend": "🟢<35 🟡35–60 🔴>60 | 🟣 NDVI Sentinel-2 (June 2024).",
           "my_fields": "my fields", "my_empty": "No fields yet — add the first one below 👇",
           "field_name": "Field name", "field_name_help": "E.g. Field by the river. Visible only to you.",
           "field_area": "Area (ha)", "field_area_help": "1 to 2000 ha. Needed for whole-field payout.",
           "field_add": "➕ Add field", "added_ok": "Field added ✅",
           "pick_field": "Field", "pick_field_help": "Which field this note belongs to.",
           "pick_problem": "Issue", "pick_problem_help": "Issue type — helps the agronomist.",
           "note_text": "Note", "note_text_help": "Briefly: what you saw and where in the field.",
           "note_add": "📝 Save note", "note_added": "Note saved ✅",
           "need_field_first": "Add a field first — then you can keep a journal.",
           "del_help": "Delete field",
           "km": "km", "ha": "ha",
           "spray_offline": "Spray window offline",
           "goal": "🎯 Target yield (c/ha)", "goal_help": "To calculate NPK for your target.",
            "osm_empty": "No OSM fields in this district — elevators and routes shown.",
            "hist_empty": "No history for this district/crop.",
            "guide_empty": "Guide is empty for this crop.",
            "risk_empty": "Risk file missing — table falls back to model forecast (offline).",
            "ndvi_empty": "No NDVI measurements with ndvi_mean yet.",
            "fields_file_empty": "Fields file missing — elevators only.",
            "elev_offline": "Nearest elevator unavailable.",
            "usual": "Usually {lo}–{hi}. 5-year average: {mean5}.",
            "risk_hint": "Green — calm, yellow — watch, red — prepare.",
            "payout_hint": "Below-80% chance: {pct} in 100. Estimate, not a tariff.",
            "dcode": "District code",
            "fields_summary": "fields in district (OSM: {osm}, demo: {demo}), total ~{area} ha",
            "gis_title": "Satellite emergence monitoring (Sentinel-2)",
            "gis_sub": "Rising green — crops grow; flat low — check the field.",
            "gis_manual": "Copernicus Browser / Sentinel Hub / LandsatLook — for manual check.",
            "gis_checked": "Checked {done} of {total}.",
            "gis_borders": "Borders and areas — OSM (GeoJSON export in forecast tab).",
            "gis_offline": "🛰 Satellite offline: {err}",
            "gis_dead": "dead dates",
            "axis_year": "year", "axis_yield": "c/ha",
            "trace_fact": "actual", "trace_forecast": "2026 forecast",
            "ndvi_x": "date", "ndvi_y": "NDVI",
            "field_default": "Field 1",
            "sow_label": "Sowing", "harvest_label": "Harvest",
            "sat_tab": "Satellite",
            "about1": "**Qagro** — Kairbek Ansar (data/ML/API) + Samat Ablayhan, captain (bot/web).",
            "about2": "stat.gov.kz · NASA POWER · Open-Meteo · FAOSTAT · OSM · Qoldau · Copernicus/Sentinel-2",
            "th_district": "District", "th_code": "Code", "th_risk": "Risk (0–100)",
            "compare": "⚖️ Crop comparison",
            "compare_hint": "Pick 2–4 crops — we compare yield, risk and payout.",
            "compare_pick": "Crops to compare",
            "compare_need": "Pick 2 to 4 crops ☝️",
            "cc_crop": "Crop", "cc_yield": "Yield, c/ha",
            "cc_risk": "Risk", "cc_payout": "Payout, ₸/ha",
            "cc_verdict": "Verdict",
            "verdict_best": "best yield", "verdict_calm": "calmest",
            "verdict_mid": "average option",
            "compare_chart_title": "Yield by crop",
            "compare_chart_yield": "Yield, c/ha",
            "compare_chart_payout": "Payout, k ₸/ha",
            "season_gdd": "Season growth (heat)",
            "season_gdd_text": "Accumulated ~{fact} of norm {lo}–{hi} (base {base}°C).",
            "season_spray": "Spray windows (48 h)",
            "season_spray_none": "No good hours — postpone spraying.",
            "alias_src": "Source", "ms": "m/s",
            "lang_label": "🌍 Язык / Тіл / Language"},
}


def _w(p_loss: float, lang: str) -> str:
    if p_loss > 0.4:
        return UI[lang]["high"]
    if p_loss > 0.2:
        return UI[lang]["mid"]
    return UI[lang]["low"]


def recalc_payout_live(ins: dict, wheat_price_kzt_per_t: int) -> dict:
    """Live-пересчёт выплаты под слайдер цены пшеницы."""
    out = dict(ins)
    try:
        sub = float(ins.get("subsidy_rate", 0.8))
        exp_short = float(ins.get("expected_shortfall_c_ha", 0.0))
        point_short = float(ins.get("shortfall_c_ha", 0.0))
    except (TypeError, ValueError):
        return out
    price = float(wheat_price_kzt_per_t)
    out["price_kzt_per_t"] = price
    out["expected_payout_ha"] = round(exp_short / 10.0 * price * sub, 0)
    out["payout_at_pred_ha"] = round(point_short / 10.0 * price * sub, 0)
    out["payout_live"] = True
    return out


def build_metrics_rows(metrics: dict) -> list[dict]:
    rows: list[dict] = []
    for c in CROP_ORDER:
        m = (metrics.get(c) or {})
        lgbm = (m.get("lgbm") or {})
        experimental = bool(m.get("below_baseline") is True)
        rows.append({
            "crop": c,
            "status": "🧪 experimental" if experimental else "✅ LGBM",
            "mae": round(float(lgbm.get("mae", float("nan"))), 2),
            "rmse": round(float(lgbm.get("rmse", float("nan"))), 2),
            "r2": round(float(lgbm.get("r2", float("nan"))), 2),
            "n": int(lgbm.get("n", 0)),
        })
    return rows


def _color(r):
    if r is None:
        return "gray"
    if r < 35:
        return "green"
    if r <= 60:
        return "orange"
    return "red"


def _field_style(feat):
    demo = (feat.get("properties") or {}).get("demo", False)
    if demo:
        return {"color": "orange", "weight": 2, "fillOpacity": 0.15,
                "dashArray": "5, 5"}
    return {"color": "green", "weight": 2, "fillOpacity": 0.25}


import re as _re

_BBOX_RE = _re.compile(
    r"bbox\s*=\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,"
    r"\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)"
)

OSM_ATTR = "© OpenStreetMap contributors"

NDVI_MARK = {
    "ru": {"gps": "GPS из данных",
           "scene-bbox": "📍 центр bbox сцены",
           "district-center": "📍 центроид района ~ (оценочно, bbox нет в данных)"},
    "kz": {"gps": "Деректегі GPS",
           "scene-bbox": "📍 сцена bbox орталығы",
           "district-center": "📍 аудан центроиді ~ (шамамен, bbox жоқ)"},
    "en": {"gps": "GPS from data",
           "scene-bbox": "📍 scene bbox center",
           "district-center": "📍 district centroid ~ (approx, no bbox in data)"},
}


def _parse_bbox_center(status: str | None) -> tuple[float, float] | None:
    """Центр сцены из 'bbox=lon_min,lat_min,lon_max,lat_max' в status.

    Возвращает (lat, lon) или None. Порядок в строке — lon,lat (как в json).
    """
    if not status:
        return None
    m = _BBOX_RE.search(str(status))
    if not m:
        return None
    try:
        lon_min, lat_min, lon_max, lat_max = (float(x) for x in m.groups())
    except ValueError:
        return None
    return ((lat_min + lat_max) / 2.0, (lon_min + lon_max) / 2.0)


def _ndvi_latlon(pt: dict, districts: list[dict]) -> tuple[float, float, str]:
    """Координаты NDVI-точки без молчаливых фейковых дефолтов.

    Приоритет: явные lat/lon в json -> центр bbox из status/bbox ->
    центроид района из districts.yaml. Третий элемент — источник:
    'gps' | 'scene-bbox' | 'district-center' (для пометки в popup).
    """
    try:
        if pt.get("lat") is not None and pt.get("lon") is not None:
            return (float(pt["lat"]), float(pt["lon"]), "gps")
    except (TypeError, ValueError):
        pass
    c = _parse_bbox_center(pt.get("status", ""))
    if c is not None:
        return (c[0], c[1], "scene-bbox")
    b = pt.get("bbox")
    if isinstance(b, (list, tuple)) and len(b) == 4:
        try:
            lon_min, lat_min, lon_max, lat_max = (float(x) for x in b)
            return ((lat_min + lat_max) / 2.0,
                    (lon_min + lon_max) / 2.0, "scene-bbox")
        except (TypeError, ValueError):
            pass
    dname = pt.get("district")
    for d in districts or []:
        if d.get("name_en") == dname:
            return (float(d["lat"]), float(d["lon"]), "district-center")
    if districts:
        return (float(districts[0]["lat"]), float(districts[0]["lon"]),
                "district-center")
    raise ValueError("no districts to anchor NDVI point")


def _risk_bg(v) -> str:
    """CSS-фон ячейки риска: 🟢<35 🟡35–60 🔴>60, None — серый."""
    try:
        r = None if v is None or (isinstance(v, float) and pd.isna(v)) else float(v)
    except (TypeError, ValueError):
        return ""
    if r is None:
        return "background-color: #9e9e9e55"
    if r < 35:
        return "background-color: #c8e6c966"
    if r <= 60:
        return "background-color: #ffecb366"
    return "background-color: #ffcdd266"


def style_risk_df(df: pd.DataFrame):
    """Таблица рисков: цветные строки целиком (по колонке risk)."""
    def _row(row):
        bg = _risk_bg(row.get("risk"))
        return [bg] * len(row)

    try:
        return df.style.apply(_row, axis=1).format({"risk": "{:.1f}"},
                                                   na_rep="offline")
    except Exception:
        return df


@st.cache_data(ttl=3600)
def load_cfg() -> dict:
    with open(ROOT / "config" / "districts.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@st.cache_data(ttl=3600)
def load_panel() -> pd.DataFrame:
    p = PANEL_V3 if PANEL_V3.exists() else PANEL
    return pd.read_csv(p)


@st.cache_data(ttl=3600)
def load_metrics() -> dict:
    if METRICS.exists():
        return json.loads(METRICS.read_text(encoding="utf-8"))
    return {}


@st.cache_data(ttl=3600)
def load_risks() -> dict:
    if RISK_EXAMPLE.exists():
        return json.loads(RISK_EXAMPLE.read_text(encoding="utf-8"))
    return {}


@st.cache_data(ttl=3600)
def load_fields() -> dict:
    if FIELDS_GEOJSON.exists():
        return json.loads(FIELDS_GEOJSON.read_text(encoding="utf-8"))
    return {"type": "FeatureCollection", "features": []}


@st.cache_data(ttl=3600)
def load_granaries() -> dict:
    if GRANARIES_JSON.exists():
        return json.loads(GRANARIES_JSON.read_text(encoding="utf-8"))
    return {"granaries": []}


@st.cache_data(ttl=3600)
def load_ndvi() -> list:
    if NDVI_JSON.exists():
        try:
            data = json.loads(NDVI_JSON.read_text(encoding="utf-8"))
            items = data.get("items", data) if isinstance(data, dict) else data
            return [x for x in items if x.get("ndvi_mean") is not None]
        except Exception:
            return []
    return []


def predict_none(district_en: str, crop: str) -> dict:
    if is_approx(crop):
        return predict_approx(district_en, crop, None)
    return predict_yield(district_en, crop, None)


@st.cache_data(ttl=3600)
def cached_predict(district_en: str, crop: str) -> dict:
    return predict_none(district_en, crop)


@st.cache_data(ttl=3600)
def cached_insurance(district_en: str, crop: str) -> dict:
    return insurance_quote(district_en, crop)


@st.cache_data(ttl=10800)
def cached_alerts(district_en: str) -> dict:
    try:
        items = check_alerts(district_en)
        return {"alerts": items, "error": None}
    except Exception as e:
        return {"alerts": [], "error": f"{type(e).__name__}: {e}"}


def main() -> None:
    import plotly.graph_objects as go

    import folium
    import streamlit.components.v1 as components

    st.set_page_config(page_title="Qagro — farmer helper", layout="wide")

    # Дизайн 50+: крупный шрифт, высокий контраст, большие кнопки/ответы.
    st.markdown(
        """<style>
html, body, [data-testid="stAppViewContainer"] { font-size: 20px; }
[data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] label, [data-testid="stMarkdownContainer"] p {
  font-size: 20px; line-height: 1.55; color: #111111;
}
h1 { font-size: 36px !important; }
h2 { font-size: 30px !important; }
h3 { font-size: 26px !important; }
div[data-testid="stAlert"] p { font-size: 22px !important; }
div[data-testid="stSuccess"] p, div[data-testid="stInfo"] p,
div[data-testid="stWarning"] p { font-size: 24px !important; }
.big-answer { font-size: 46px !important; font-weight: 800; line-height: 1.1; }
div[data-testid="stButton"] > button,
div[data-testid="stDownloadButton"] > button,
div[data-testid="stFormSubmitButton"] > button {
  width: 100%; font-size: 22px !important; font-weight: 700;
  padding: 16px 22px !important; min-height: 60px; border-radius: 12px;
}
div[data-testid="stSelectbox"] label, div[data-testid="stSlider"] label {
  font-size: 21px !important; font-weight: 700; color: #111111;
}
div[data-testid="stCaptionContainer"] small, div[data-testid="stCaptionContainer"] {
  color: #333333 !important; font-size: 18px !important;
}
div[data-testid="stProgress"] > div > div > div { height: 22px !important; border-radius: 11px; }
.district-code small { font-size: 17px !important; color: #333333; }
@media (max-width: 640px) {
  div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
  div[data-testid="column"] { min-width: 100% !important; flex-basis: 100% !important; }
}
div[data-testid="stDownloadButton"] > button { width: 100%; }
div[data-testid="stFormSubmitButton"] > button { width: 100%; }
</style>""",
        unsafe_allow_html=True,
    )

    cfg = load_cfg()
    districts = cfg.get("districts", [])
    crops = cfg.get("crops", [])

    lang = st.sidebar.selectbox(UI["ru"]["lang_label"],
                                options=["ru", "kz", "en"], index=0)
    T = UI[lang]
    wheat_price = st.sidebar.slider(T["price"], min_value=WHEAT_PRICE_MIN,
                                    max_value=WHEAT_PRICE_MAX,
                                    value=WHEAT_PRICE_DEFAULT, step=1000,
                                    help=T["price_help"])

    st.title(T["title"])
    st.write(T["sub"])

    dlabel = {d["name_en"]: f"{d.get(f'name_{lang}', d['name_ru'])}" for d in districts}
    clabel = {c["id"]: f"{CROP_ICON.get(c['id'], '🌱')} {c.get(f'name_{lang}', c['id'])}"
              for c in crops}

    st.header(T["step1"])
    st.caption(T["step1_hint"])
    district_en = st.selectbox("📍", options=list(dlabel.keys()),
                               format_func=lambda k: dlabel[k],
                               index=list(dlabel.keys()).index("Esil")
                               if "Esil" in dlabel else 0,
                               label_visibility="collapsed",
                               help=T["district_help"])
    st.markdown(f"<div class='district-code'><small>{T['dcode']}: <b>{district_en}</b></small></div>",
                unsafe_allow_html=True)
    st.header(T["step2"])
    st.caption(T["step2_hint"])
    crop = st.selectbox("🌱", options=list(clabel.keys()),
                        format_func=lambda k: clabel[k],
                        label_visibility="collapsed",
                        help=T["crop_help"])

    try:
        pred = cached_predict(district_en, crop)
        ins_raw = cached_insurance(district_en, crop)
        rec = recommend_sowing(district_en, crop, lang)
        err = None
    except Exception as e:
        pred = ins_raw = rec = None
        err = f"{type(e).__name__}: {e}"
    if err:
        st.error(f"⚠️ {err}")
        st.stop()

    ins = recalc_payout_live(ins_raw, wheat_price) if crop in ("spring_wheat", "barley") else ins_raw
    panel = load_panel()
    metrics = load_metrics()
    risks = load_risks()
    fdata = load_fields()
    gdata = load_granaries()
    ndvi_pts = load_ndvi()

    risk = (risks.get(f"{district_en}_risk") or {})
    seasonal, light = risk.get("seasonal_risk"), risk.get("seasonal_light", "")
    offline = seasonal is None
    if offline:
        p0 = float(ins["p_loss"])
        light = "🔴" if p0 > 0.4 else ("🟡" if p0 > 0.2 else "🟢")
    experimental = bool(pred.get("experimental") or ins.get("experimental"))

    # ---------- Шаг 3: ответ словами ----------
    st.header(T["step3"])
    y, lo, hi = round(pred["y_pred"], 1), round(pred["lo10"], 1), round(pred["hi90"], 1)
    mean5 = round(float(ins.get("mean5_c_ha") or y), 1)
    p_loss, payout = float(ins["p_loss"]), int(round(float(ins.get("expected_payout_ha") or 0)))

    c1, c2 = st.columns(2)
    with c1:
        st.success(f"<div class='big-answer'>{T['yield']}: ~{y} {T['axis_yield']}</div>\n\n"
                   + T["usual"].format(lo=lo, hi=hi, mean5=mean5),
                   icon="🌾")
    with c2:
        st.info(f"<div class='big-answer'>{light} {T['risk']}: {_w(p_loss, lang)}</div>\n\n"
                + T["risk_hint"], icon="ℹ️")
    c3, c4 = st.columns(2)
    with c3:
        st.warning(f"<div class='big-answer'>{T['ins']}: ~{payout} ₸/{T['ha']}</div>\n\n"
                   + T["payout_hint"].format(pct=round(p_loss * 100)),
                   icon="🛡️")
    with c4:
        st.success(f"<div class='big-answer'>{T['todo']}: {rec['window']}</div>\n\n{rec['message']}",
                   icon="✅")
    if experimental:
        st.warning(T["exp"])
    if offline:
        st.caption(T["offline"])

    d_ru = next((d.get("name_ru") for d in districts if d.get("name_en") == district_en), None)
    _al = cached_alerts(district_en)
    try:
        from src.logistics import nearest_elevator as _ne
    except ImportError:
        try:
            from logistics import nearest_elevator as _ne  # type: ignore
        except ImportError:
            _ne = None
    _elev = None
    if _ne is not None:
        try:
            _elev = _ne(district_en)
        except Exception:
            _elev = None
    try:
        _cal = sowing_calendar(crop, lang)
    except Exception:
        _cal = None
    pdf_bytes = build_report_pdf(
        district_en, crop, lang, pred=pred, ins=ins,
        risk=risk or {"seasonal_risk": None, "error": "offline in demo"},
        rec=rec, district_ru=d_ru, calendar=_cal,
        alerts=_al.get("alerts"), alerts_error=_al.get("error"), elevator=_elev)
    st.download_button(f"📄 {T['download']}", pdf_bytes,
                       file_name=f"qagro_{district_en}_{crop}_{lang}.pdf",
                       mime="application/pdf", type="primary",
                       use_container_width=True)

    with st.expander(f"🔧 {T['detail']}"):
        st.write(f"y_pred={pred['y_pred']}, 80% [{pred['lo10']}, {pred['hi90']}], "
                 f"mean5={ins['mean5_c_ha']}, p_loss={ins['p_loss']}")
        if pred.get("factors"):
            st.write("Top factors:", [(f.get("feature"), round(float(f.get("shap_value", 0)), 3))
                                      for f in pred["factors"][:3]])
        if crop in metrics:
            lm = metrics[crop]["lgbm"]
            st.write(f"{crop}: MAE={lm['mae']:.2f}, RMSE={lm['rmse']:.2f}, R²={lm['r2']:.2f}")

    # ---------- Карты ----------
    st.header(T["maps"])
    tab_risk, tab_fields, tab_gis = st.tabs(
        ["🟢🟡🔴 " + T["risk_tab"],
         "🌾 " + T["fields_tab"],
         "🛰 " + T["sat_tab"]])
    with tab_risk:
        rows = []
        for d in districts:
            en = d["name_en"]
            r = (risks.get(f"{en}_risk") or {}).get("seasonal_risk")
            if r is None:
                try:
                    ii = cached_insurance(en, crop)
                    r = round(float(ii["p_loss"]) * 100, 1)
                except Exception:
                    r = None
            rows.append({"district": d.get(f"name_{lang}", en),
                         "code": en, "risk": r})
        if not risks:
            st.warning(T["risk_empty"])
        m = folium.Map(location=[52.3, 69.0], zoom_start=7,
                       tiles="OpenStreetMap", attr=OSM_ATTR,
                       control_scale=True)
        for d in districts:
            en = d["name_en"]
            r = (risks.get(f"{en}_risk") or {}).get("seasonal_risk")
            folium.CircleMarker(
                location=[d["lat"], d["lon"]], radius=12,
                color=_color(r), fill=True, fill_opacity=0.7,
                popup=f"{d.get(f'name_{lang}', en)}: {r}",
                tooltip=f"{d.get(f'name_{lang}', en)} — {r if r is not None else 'offline'}",
            ).add_to(m)
        # NDVI-точки Sentinel-2: координаты из bbox сцены,
        # иначе центроид района с честной пометкой (без фейковых lat/lon).
        if not ndvi_pts:
            st.caption(T["ndvi_empty"])
        for pt in ndvi_pts[:20]:
            try:
                _lat, _lon, _src = _ndvi_latlon(pt, districts)
                _mark = NDVI_MARK[lang][_src]
                _dist = pt.get("district", "?")
                folium.CircleMarker(
                    location=[_lat, _lon], radius=5,
                    color="purple", fill=True, fill_opacity=0.8,
                    popup=(f"NDVI {pt.get('ndvi_mean')} "
                           f"({pt.get('date')}, {_dist})<br>"
                           f"{_mark}<br>{pt.get('scene_id', '')}"),
                    tooltip=f"NDVI {pt.get('ndvi_mean')} — {_mark}",
                ).add_to(m)
            except Exception:
                pass
        folium.LayerControl().add_to(m)
        components.html(m._repr_html_(), height=480)
        st.caption(T["legend"] + f" {OSM_ATTR}.")
        _rdf = pd.DataFrame(rows).sort_values("risk", ascending=False,
                                              na_position="last")
        if _rdf["risk"].isna().all():
            st.caption(T["risk_empty"])
        _show = _rdf.rename(columns={"district": T["th_district"],
                                     "code": T["th_code"],
                                     "risk": T["th_risk"]})
        # Цветные строки по риску: красим по внутренней колонке, показываем локализованную.
        try:
            _sty = _show.style.apply(
                lambda row: [_risk_bg(_rdf.iloc[row.name]["risk"])] * len(row),
                axis=1).format({T["th_risk"]: "{:.1f}"}, na_rep="offline")
        except Exception:
            _sty = _show
        st.dataframe(_sty, use_container_width=True)

    with tab_fields:
        feats = [f for f in fdata.get("features", [])
                 if (f.get("properties") or {}).get("district_en") == district_en]
        areas = [float((f.get("properties") or {}).get("area_ha") or 0) for f in feats]
        n_demo = sum(1 for f in feats if (f.get("properties") or {}).get("demo"))
        if not fdata.get("features"):
            st.warning(T["fields_file_empty"])
        if not feats:
            st.info(T["osm_empty"])
        st.write(f"🌾 {len(feats)} " +
                 T["fields_summary"].format(osm=len(feats) - n_demo,
                                            demo=n_demo,
                                            area=round(sum(areas))))
        m2 = folium.Map(location=[next(d["lat"] for d in districts if d["name_en"] == district_en),
                                  next(d["lon"] for d in districts if d["name_en"] == district_en)],
                        zoom_start=10, tiles="OpenStreetMap", attr=OSM_ATTR,
                        control_scale=True)
        if feats:
            folium.GeoJson(
                {"type": "FeatureCollection", "features": feats},
                style_function=_field_style,
                tooltip=folium.GeoJsonTooltip(fields=["district_en", "area_ha", "source"],
                                              aliases=[T["th_district"], T["ha"],
                                                       T["alias_src"]]),
            ).add_to(m2)
        for g in gdata.get("granaries", []):
            _gname = g.get(f"name_{lang}", g.get("name_ru"))
            folium.Marker(
                location=[g["lat"], g["lon"]],
                icon=folium.Icon(color="blue", icon="warehouse", prefix="fa"),
                popup=f"🌾 {_gname} (~{g.get('dist_km', '?')} {T['km']})",
                tooltip=f"🌾 {_gname}",
            ).add_to(m2)
        # маршрут: только к ближайшему элеватору — 1 толстая синяя линия
        if _elev:
            try:
                dc = next(d for d in districts if d["name_en"] == district_en)
                folium.PolyLine([[dc["lat"], dc["lon"]],
                                 [_elev["lat"], _elev["lon"]]],
                                color="blue", weight=5, opacity=0.9,
                                tooltip=f"🚚 {_elev.get(f'name_{lang}', _elev.get('name_ru'))}").add_to(m2)
            except Exception:
                pass
        else:
            st.caption(T["elev_offline"])
        folium.LayerControl().add_to(m2)
        components.html(m2._repr_html_(), height=480)
        if _elev:
            _ename = _elev.get(f"name_{lang}", _elev.get("name_ru"))
            st.write(f"🚚 {_ename} — {_elev.get('dist_km')} {T['km']}.")

    with tab_gis:
        # Трек 1: NDVI-мониторинг (1.1), залежи (1.3), гибель (1.4). Границы (1.2) — OSM.
        st.subheader("🛰 " + T["gis_title"])
        st.caption(T["gis_sub"] + " " + T["gis_manual"])
        skey = {"ru": "status_ru", "kz": "status_kz", "en": "status_en"}[lang]
        try:
            # C5-2: сначала свежий файл (<7 дней), иначе живой запрос (медленно).
            import time as _t
            _gis_file = ROOT / "data" / "gis" / f"gis_{district_en}.json"
            g = None
            if _gis_file.exists() and (_t.time() - _gis_file.stat().st_mtime < 7 * 86400):
                try:
                    g = json.loads(_gis_file.read_text(encoding="utf-8"))
                except Exception:
                    g = None
            if not g or not g.get("fields"):
                from src.gis_monitor import run_district as _gis_run
                with st.spinner("🛰 Sentinel-2..."):
                    g = _gis_run(district_en, max_fields=4)
            for fl in g.get("fields", []):
                c = fl.get("classification") or {}
                st.write(f"**{fl.get('field_id')}** ({fl.get('area_ha')} {T['ha']}): "
                         f"{c.get(skey, c.get('status_ru', c.get('status')))} — NDVI max {c.get('ndvi_max')}, "
                         f"{T['gis_dead']} {round(float(c.get('dead_share') or 0) * 100)}%.")
                series = [(p.get("date"), p.get("ndvi_mean")) for p in fl.get("series", [])
                          if p.get("ndvi_mean") is not None]
                if series:
                    fig2 = go.Figure()
                    fig2.add_trace(go.Scatter(x=[s[0] for s in series],
                                              y=[s[1] for s in series],
                                              mode="lines+markers", name="NDVI"))
                    fig2.update_layout(xaxis_title=T["ndvi_x"], yaxis_title=T["ndvi_y"],
                                       height=220, margin=dict(l=10, r=10, t=10, b=10))
                    st.plotly_chart(fig2, use_container_width=True)
            st.caption(T["gis_checked"].format(done=g.get('checked', 0),
                                               total=g.get('total_fields', 0))
                       + " " + T["gis_borders"])
        except Exception as e:
            st.warning(T["gis_offline"].format(err=e))

    # ---------- Агроном / хозяйство / календарь / о проекте ----------
    tab_agro, tab_farm, tab_plus, tab_compare, tab_cal, tab_about = st.tabs(
        [T["agro"], T["farm"], T["plus"], T["compare"], T["cal"], T["about"]])
    with tab_agro:
        hist = panel[(panel["district_en"] == district_en) & (panel["crop"] == crop)].sort_values("year")
        if hist.empty:
            st.caption(T["hist_empty"])
        fig = go.Figure()
        if not hist.empty:
            fig.add_trace(go.Scatter(x=hist["year"].tolist(), y=hist["yield_c_ha"].tolist(),
                                     mode="lines+markers", name=T["trace_fact"]))
        fig.add_trace(go.Scatter(x=[2026], y=[pred["y_pred"]], mode="markers", name=T["trace_forecast"],
                                 error_y=dict(type="data",
                                              array=[pred["hi90"] - pred["y_pred"]],
                                              arrayminus=[pred["y_pred"] - pred["lo10"]])))
        fig.update_layout(xaxis_title=T["axis_year"], yaxis_title=T["axis_yield"])
        st.plotly_chart(fig, use_container_width=True)
        rows = build_metrics_rows(metrics)
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
        slice_df = panel[(panel["district_en"] == district_en) & (panel["crop"] == crop)]
        buf = io.StringIO()
        slice_df.to_csv(buf, index=False)
        st.download_button(T["csv"], buf.getvalue(),
                           file_name=f"qagro_{district_en}_{crop}.csv", mime="text/csv",
                           use_container_width=True)
    with tab_farm:
        # v4: мои поля + журнал + окно опрыскивания (SQLite локально, spray живой).
        try:
            from src.myfields import add_field, delete_field, list_fields
            from src.journal import add_note, list_notes, PROBLEM_TYPES
            from src.spray import check_spray_window
            _farm_ok = True
        except ImportError:
            try:
                from myfields import add_field, delete_field, list_fields  # type: ignore
                from journal import add_note, list_notes, PROBLEM_TYPES  # type: ignore
                from spray import check_spray_window  # type: ignore
                _farm_ok = True
            except ImportError as e:
                st.warning(str(e))
                _farm_ok = False
        if _farm_ok:
            fields = list_fields()
            st.write(f"🌾 {len(fields)} {T['my_fields']}")
            if not fields:
                st.info(T["my_empty"])
            with st.form("add_field"):
                _def_name = T["field_default"]
                fn = st.text_input(T["field_name"], _def_name, help=T["field_name_help"])
                farea = st.number_input(T["field_area"], 10.0, 2000.0, 100.0,
                                        help=T["field_area_help"])
                # st.rerun внутри form не нужен: submit формы и так даёт rerun.
                # st.rerun оставлен только вне form (кнопка удаления ниже).
                if st.form_submit_button(T["field_add"]):
                    try:
                        dc = next(d for d in districts if d["name_en"] == district_en)
                        add_field(fn, float(dc["lat"]), float(dc["lon"]),
                                  float(farea), crop)
                        st.success(T["added_ok"])
                    except Exception as e:
                        st.error(str(e))
            for f in fields:
                c1, c2 = st.columns([4, 1])
                c1.write(f"#{f['id']} {f['name']} — {f['area_ha']} {T['ha']}, {f['crop']}")
                if c2.button("✖", key=f"del_{f['id']}", help=T["del_help"],
                             use_container_width=True):
                    delete_field(int(f["id"]))
                    st.rerun()
            with st.form("add_note"):
                if fields:
                    fid = st.selectbox(T["pick_field"], [f["id"] for f in fields],
                                       help=T["pick_field_help"])
                    ptype_ids = ["weeds", "pests", "disease",
                                 "lodging", "drought", "other"]
                    ptype = st.selectbox(
                        T["pick_problem"], ptype_ids,
                        format_func=lambda p: PROBLEM_TYPES.get(p, {}).get(lang, p),
                        help=T["pick_problem_help"])
                    txt = st.text_input(T["note_text"], "", help=T["note_text_help"])
                    if st.form_submit_button(T["note_add"]):
                        try:
                            add_note(int(fid), ptype, txt)
                            st.success(T["note_added"])
                        except Exception as e:
                            st.error(str(e))
                else:
                    st.caption(T["need_field_first"])
            try:
                sp = check_spray_window(district_en)
                key = {"ru": "verdict_ru", "kz": "verdict_kz", "en": "verdict_en"}[lang]
                st.info(f"🧴 {sp.get(key)}")
            except Exception as e:
                st.caption(f"{T['spray_offline']}: {e}")
    with tab_plus:
        # v4: справочник + NPK + экономика.
        try:
            from src.guide_data import lookup as _lookup
            from src.fertilizer import calc_npk as _npk
            from src.economics import profit_ha as _profit
            items = _lookup(crop)[:4]
            if not items:
                st.info(T["guide_empty"])
            nk, sk, ak = {"ru": ("name_ru", "signs_ru", "action_ru"),
                          "kz": ("name_kz", "signs_kz", "action_kz"),
                          "en": ("name_en", "signs_en", "action_en")}[lang]
            for it in items:
                st.write(f"🔬 **{it.get(nk)}**: {'; '.join(it.get(sk, [])[:2])}. → {it.get(ak)}")
            goal = st.slider(T["goal"], 5.0, 30.0, 15.0, help=T["goal_help"])
            npk = _npk(crop, float(goal), "medium")
            st.write(f"🧪 NPK: N {npk['N_kg_ha']} · P {npk['P_kg_ha']} · K {npk['K_kg_ha']} кг/{T['ha']}")
            pr = _profit(float(pred["y_pred"]), float(wheat_price))
            st.write(f"💰 ~{int(pr['profit_kzt_ha'])} ₸/{T['ha']} "
                     f"({int(pr['revenue_kzt_ha'])} − {int(pr['cost_kzt_ha'])})")
        except Exception as e:
            st.warning(str(e))
    with tab_compare:
        # Фича (a): сравнение 2–4 культур — таблица + групповой bar-chart.
        st.caption(T["compare_hint"])
        _def_cmp = [c for c in ("spring_wheat", "barley") if c in clabel]
        cmp_crops = st.multiselect(T["compare_pick"], options=list(clabel.keys()),
                                   format_func=lambda k: clabel[k],
                                   default=_def_cmp)
        if len(cmp_crops) < 2 or len(cmp_crops) > 4:
            st.info(T["compare_need"])
        else:
            _rows, _y, _pl, _pay = [], [], [], []
            for cc in cmp_crops:
                try:
                    _p = cached_predict(district_en, cc)
                    _i = cached_insurance(district_en, cc)
                    if cc in ("spring_wheat", "barley"):
                        _i = recalc_payout_live(_i, wheat_price)
                    _yy = round(float(_p["y_pred"]), 1)
                    _pp = float(_i["p_loss"])
                    _po = int(round(float(_i.get("expected_payout_ha") or 0)))
                except Exception:
                    continue
                _y.append(_yy)
                _pl.append(_pp)
                _pay.append(_po)
                _rows.append({"_id": cc, T["cc_crop"]: clabel.get(cc, cc),
                              T["cc_yield"]: _yy,
                              T["cc_risk"]: _w(_pp, lang),
                              T["cc_payout"]: _po, "_p": _pp, "_y": _yy})
            if _rows:
                _best = max(_rows, key=lambda r: r["_y"])["_id"]
                _calm = min(_rows, key=lambda r: r["_p"])["_id"]
                for r in _rows:
                    if r["_id"] == _best:
                        r[T["cc_verdict"]] = f"⭐ {T['verdict_best']}"
                    elif r["_id"] == _calm:
                        r[T["cc_verdict"]] = f"🛡️ {T['verdict_calm']}"
                    else:
                        r[T["cc_verdict"]] = T["verdict_mid"]
                    del r["_id"]
                    del r["_p"]
                    del r["_y"]
                _cdf = pd.DataFrame(_rows)
                st.dataframe(_cdf, use_container_width=True)
                _fig = go.Figure()
                _fig.add_trace(go.Bar(x=_cdf[T["cc_crop"]].tolist(),
                                      y=_y, name=T["compare_chart_yield"]))
                _fig.add_trace(go.Bar(
                    x=_cdf[T["cc_crop"]].tolist(),
                    y=[round(p / 1000.0, 1) for p in _pay],
                    name=T["compare_chart_payout"]))
                _fig.update_layout(barmode="group",
                                   title=T["compare_chart_title"],
                                   xaxis_title=T["compare_pick"],
                                   yaxis_title=f"{T['compare_chart_yield']} / {T['compare_chart_payout']}",
                                   height=360,
                                   margin=dict(l=10, r=10, t=40, b=10))
                st.plotly_chart(_fig, use_container_width=True)
    with tab_cal:
        # Фича (b): сезонный календарь — GDD-факт vs норма + spray-окна 48 ч + алерты.
        try:
            cal = sowing_calendar(crop, lang)
            st.write(f"🌱 **{T['sow_label']}: {cal['sowing_window']}**; "
                     f"**{T['harvest_label']}: {cal['harvest_window']}**.")
            st.caption(cal.get("note", ""))
            try:
                _gdd_fact = float((rec.get("gdd_context") or {}).get(
                    "district_gdd5_mean") or 0.0)
            except (TypeError, ValueError):
                _gdd_fact = 0.0
            _norm = cal.get("gdd_norm") or [0, 1]
            _lo, _hi = float(_norm[0]), float(_norm[1]) if len(_norm) > 1 else float(_norm[0])
            _base = cal.get("gdd_base_temp", 5.0)
            _prog = min(max(_gdd_fact / _hi if _hi > 0 else 0.0, 0.0), 1.0)
            st.subheader(f"🌡️ {T['season_gdd']}")
            st.progress(_prog)
            st.write(T["season_gdd_text"].format(fact=round(_gdd_fact),
                                                 lo=round(_lo), hi=round(_hi),
                                                 base=_base))
        except Exception as e:
            st.warning(str(e))
        st.subheader(f"🧴 {T['season_spray']}")
        try:
            try:
                from src.spray import check_spray_window as _spray2
            except ImportError:
                from spray import check_spray_window as _spray2  # type: ignore
            _sp = _spray2(district_en, 48)
            _vk = {"ru": "verdict_ru", "kz": "verdict_kz", "en": "verdict_en"}[lang]
            st.info(f"🧴 {_sp.get(_vk)}")
            _wins = _sp.get("windows") or []
            if _wins:
                for _wn in _wins[:4]:
                    st.write(f"✅ {_wn.get('start')} → {_wn.get('end')}")
            elif not _sp.get("next_good_hours"):
                st.caption(T["season_spray_none"])
            else:
                for _gh in (_sp.get("next_good_hours") or [])[:6]:
                    st.write(f"✅ {_gh.get('time')} — {_gh.get('temp_c')}°C, "
                             f"{_gh.get('wind_ms')} {T['ms']}")
        except Exception as e:
            st.caption(f"{T['spray_offline']}: {e}")
        al = cached_alerts(district_en)
        if al.get("error"):
            st.caption(al["error"])
        elif not al.get("alerts"):
            st.success(T["no_threat"])
        else:
            key = {"ru": "msg_ru", "kz": "msg_kz", "en": "msg_en"}[lang]
            for a in al["alerts"]:
                st.write(a.get(key) or a.get("msg_ru"))
    with tab_about:
        st.write(T["about1"])
        st.write(T["about2"])


if _ST_RUN:
    main()
