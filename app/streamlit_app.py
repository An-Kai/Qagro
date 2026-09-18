"""Streamlit-дашборд Qagro.

Селекты района/культуры/языка, метрики, график Plotly (факт vs прогноз),
карта Folium с рисками, выгрузка CSV/GeoJSON/PDF, дисклеймер про APPROX
и даунскейлинг районов.

C4 (веб-приятности, без переписывания логики):
  st.cache_data(ttl=3600) на predict/insurance + загрузку fields/granaries,
  sidebar (язык RU/KZ/EN + слайдер цены пшеницы для live-пересчёта payout),
  вкладки: Прогноз / Поля и элеваторы / Метрики / О проекте.

Запуск (Windows PowerShell):
  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# streamlit опционален для мок-рендера: без него файл импортируется
# (stub даёт cache_data-noop + runtime.exists()->False, UI не выполняется).
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
    from src.calendar import sowing_calendar
    from src.insurance import insurance_quote
    from src.predict import predict_yield
    from src.recommend import recommend_sowing
    from src.report_pdf import build_report_pdf
except ImportError:  # запуск с другой cwd
    from alerts import check_alerts  # type: ignore
    from approx_crops import APPROX_YIELD_FACTOR, is_approx  # type: ignore
    from approx_crops import predict_approx  # type: ignore
    from calendar import sowing_calendar  # type: ignore
    from insurance import insurance_quote  # type: ignore
    from predict import predict_yield  # type: ignore
    from recommend import recommend_sowing  # type: ignore
    from report_pdf import build_report_pdf  # type: ignore

PANEL = ROOT / "data" / "processed" / "akmola_panel.csv"
METRICS = ROOT / "metrics" / "metrics.json"
RISK_EXAMPLE = ROOT / "reports" / "risk_example.json"
FIELDS_GEOJSON = ROOT / "data" / "fields" / "akmola_osm_fields.geojson"
GRANARIES_JSON = ROOT / "data" / "fields" / "granaries.json"

CROP_ORDER = ("spring_wheat", "barley", "oats",
              "sunflower", "rapeseed", "flax")
WHEAT_PRICE_MIN, WHEAT_PRICE_MAX, WHEAT_PRICE_DEFAULT = 70000, 130000, 95000


# ---------- чистые хелперы (без streamlit — для мок-рендера/тестов) ----------

def recalc_payout_live(ins: dict, wheat_price_kzt_per_t: int) -> dict:
    """Live-пересчёт выплаты под слайдер цены пшеницы.

    Чистая функция: payout = shortfall/10 * price * subsidy.
    """
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
    """Строки таблицы Метрик: 6 культур + бейдж ✅ LGBM / 🧪 experimental."""
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


# ---------- кэшированные загрузки/расчёты (ttl=3600) ----------

@st.cache_data(ttl=3600)
def load_cfg() -> dict:
    with open(ROOT / "config" / "districts.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@st.cache_data(ttl=3600)
def load_panel() -> pd.DataFrame:
    return pd.read_csv(PANEL)


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
    """C8 best-effort: алерты Open-Meteo, при офлайне — error без моков."""
    try:
        items = check_alerts(district_en)
        return {"alerts": items, "error": None}
    except Exception as e:
        return {"alerts": [], "error": f"{type(e).__name__}: {e}"}


# ---------- UI (выполняется только под `streamlit run`) ----------

def main() -> None:
    import plotly.graph_objects as go

    import folium
    import streamlit.components.v1 as components

    st.set_page_config(page_title="Qagro — Akmola yield & risk", layout="wide")

    cfg = load_cfg()
    districts = cfg.get("districts", [])
    crops = cfg.get("crops", [])
    panel = load_panel()
    metrics = load_metrics()
    risks = load_risks()
    fdata = load_fields()
    gdata = load_granaries()

    dlabel = {d["name_en"]: f"{d['name_ru']} ({d['name_en']})" for d in districts}
    clabel = {c["id"]: f"{c.get('name_ru', c['id'])} ({c['id']})" for c in crops}

    st.title("Qagro — прогноз урожайности и риски (Акмола, 2026)")

    # ---- sidebar: язык + цена пшеницы (live-пересчёт payout) ----
    st.sidebar.header("⚙️ Параметры / Параметрлер / Settings")
    lang = st.sidebar.selectbox("Язык / Тіл / Language",
                                options=["ru", "kz", "en"], index=0)
    wheat_price = st.sidebar.slider(
        "Цена пшеницы (KZT/т) — live-пересчёт выплаты",
        min_value=WHEAT_PRICE_MIN, max_value=WHEAT_PRICE_MAX,
        value=WHEAT_PRICE_DEFAULT, step=1000)
    st.sidebar.caption("Слайдер влияет на пшеницу/ячмень; "
                       "у APPROX-культур цена фиксирована "
                       "(см. src/approx_crops.py).")

    col1, col2 = st.columns(2)
    with col1:
        district_en = st.selectbox("Район / Аудан / District",
                                   options=list(dlabel.keys()),
                                   format_func=lambda k: dlabel[k],
                                   index=list(dlabel.keys()).index("Esil")
                                   if "Esil" in dlabel else 0)
    with col2:
        crop = st.selectbox("Культура / Дақыл / Crop",
                            options=list(clabel.keys()),
                            format_func=lambda k: clabel[k])

    # ---- вычисления (локальные, без сети; predict/insurance кэшированы) ----
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

    # live-пересчёт payout слайдером (только пшеница/ячмень — config-цена)
    if crop in ("spring_wheat", "barley"):
        ins = recalc_payout_live(ins_raw, wheat_price)
        price_note = (f"live: цена {wheat_price} KZT/т (слайдер), "
                      f"база конфига {ins_raw['price_kzt_per_t']} KZT/т.")
    else:
        ins = ins_raw
        price_note = (f"фиксированная цена {crop}: "
                      f"{ins['price_kzt_per_t']} KZT/т "
                      f"(слайдер {wheat_price} — только пшеница/ячмень).")

    risk = (risks.get(f"{district_en}_risk") or {})
    seasonal = risk.get("seasonal_risk")
    light = risk.get("seasonal_light", "")
    if seasonal is None:
        # офлайн-фолбэк: светофор по p_loss, честно помечаем
        p = float(ins["p_loss"])
        light = "🔴" if p > 0.4 else ("🟡" if p > 0.2 else "🟢")
        seasonal_txt = f"~{round(p * 100, 1)} (p_loss-proxy, риск офлайн)"
    else:
        seasonal_txt = f"{seasonal} {light}"

    approx = bool(pred.get("approx") or ins.get("approx"))

    tab_forecast, tab_cal, tab_map, tab_metrics, tab_about = st.tabs(
        ["Прогноз", "Календарь и алерты", "Поля и элеваторы", "Метрики", "О проекте"])

    # ================= Прогноз =================
    with tab_forecast:
        if approx:
            st.warning("⚠️ APPROX: культура без обучающих данных — "
                       "масштабирование от пшеницы (см. src/approx_crops.py). "
                       "Decision support, не тариф.")
        if ins.get("experimental"):
            st.warning("🧪 EXPERIMENTAL: LGBM хуже бейзлайна на hold-out "
                       "2021–2025 — прогноз = baseline mean5, интервал ×1.5.")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("y_pred 2026 (ц/га)", pred["y_pred"])
        m2.metric("80% интервал", f"{pred['lo10']}–{pred['hi90']}")
        m3.metric("Сезонный риск", seasonal_txt)
        m4.metric("P_loss", ins["p_loss"])
        m5.metric("Выплата live (KZT/га)", ins["expected_payout_ha"])

        st.subheader("Страховка и рекомендация")
        st.write(f"mean5={ins['mean5_c_ha']} {ins['mean5_years']}, "
                 f"strike={ins['strike_c_ha']}, price={ins['price_kzt_per_t']} KZT/t. "
                 f"{ins['disclaimer']}")
        st.caption(price_note)
        st.write(f"🌱 {rec['window']}: {rec['message']} "
                 f"({' / '.join(rec.get('actions', []))})")

        # ---- график Plotly: факт vs прогноз ----
        st.subheader("Факт vs прогноз")
        hist = panel[(panel["district_en"] == district_en)]
        if is_approx(crop):
            # истории APPROX-культур нет: показываем пшеницу x фактор + пометка
            f = APPROX_YIELD_FACTOR[crop]
            hw = hist[hist["crop"] == "spring_wheat"].sort_values("year")
            y_hist = (hw["yield_c_ha"] * f).tolist()
            years = hw["year"].tolist()
            st.caption(f"APPROX: история = пшеница × {f} (обучающих данных по {crop} нет).")
        else:
            hc = hist[hist["crop"] == crop].sort_values("year")
            years = hc["year"].tolist()
            y_hist = hc["yield_c_ha"].tolist()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=years, y=y_hist, mode="lines+markers", name="факт"))
        fig.add_trace(go.Scatter(x=[2026], y=[pred["y_pred"]], mode="markers",
                                 name="прогноз 2026",
                                 error_y=dict(type="data",
                                              array=[pred["hi90"] - pred["y_pred"]],
                                              arrayminus=[pred["y_pred"] - pred["lo10"]])))
        fig.update_layout(xaxis_title="год", yaxis_title="ц/га",
                          title=f"{district_en} / {crop}: факт + прогноз 2026")
        st.plotly_chart(fig, use_container_width=True)

        # ---- метрики модели (кратко, полно — во вкладке Метрики) ----
        st.subheader("Качество модели (hold-out 2021–2025)")
        if crop in metrics:
            lm = metrics[crop]["lgbm"]
            badge = ("🧪 experimental" if metrics[crop].get("below_baseline")
                     else "✅ LGBM")
            st.write(f"{badge} {crop}: MAE={lm['mae']:.2f}, RMSE={lm['rmse']:.2f}, "
                     f"R²={lm['r2']:.2f}, n={lm['n']}")
        else:
            st.write(f"{crop}: обученной модели нет (APPROX). "
                     f"Метрики пшеницы: {metrics.get('spring_wheat', {}).get('lgbm', {})}")

        # ---- выгрузки ----
        st.subheader("Выгрузка")

        # CSV: срез панели + строка прогноза
        slice_df = panel[(panel["district_en"] == district_en)]
        if not is_approx(crop):
            slice_df = slice_df[slice_df["crop"] == crop]
        csv_buf = io.StringIO()
        slice_df.to_csv(csv_buf, index=False)
        st.download_button("⬇️ CSV (история района)", csv_buf.getvalue(),
                           file_name=f"qagro_{district_en}_{crop}.csv",
                           mime="text/csv")

        # GeoJSON: районы + риск-пропсы
        features = []
        for d in districts:
            en = d["name_en"]
            r = (risks.get(f"{en}_risk") or {}).get("seasonal_risk")
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [d["lon"], d["lat"]]},
                "properties": {"name_en": en, "name_ru": d.get("name_ru"),
                               "seasonal_risk": r,
                               "cached": bool(risks.get(f"{en}_risk"))},
            })
        geojson = {"type": "FeatureCollection", "features": features,
                   "note": "Точки-центроиды (даунскейлинг областной статистики), не границы."}
        st.download_button("⬇️ GeoJSON (районы+риски)",
                           json.dumps(geojson, ensure_ascii=False, indent=2),
                           file_name="qagro_districts.geojson",
                           mime="application/geo+json")

        # PDF (C8: календарь+алерты+элеватор внутри отчёта)
        d_ru = next((d.get("name_ru") for d in districts
                     if d.get("name_en") == district_en), None)
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
            risk=risk or {"seasonal_risk": None,
                          "error": "offline in Streamlit demo"},
            rec=rec, district_ru=d_ru, calendar=_cal,
            alerts=_al.get("alerts"), alerts_error=_al.get("error"),
            elevator=_elev)
        st.download_button("⬇️ PDF-отчёт", pdf_bytes,
                           file_name=f"qagro_{district_en}_{crop}.pdf",
                           mime="application/pdf")

    # ================= Календарь и алерты (C8) =================
    with tab_cal:
        st.subheader("Посевной календарь Акмолы (справочник, agro-practice)")
        try:
            cal = sowing_calendar(crop, lang)
            st.write(f"🌱 Сев {crop}: **{cal['sowing_window']}**; "
                     f"уборка: **{cal['harvest_window']}**.")
            st.write(f"GDD-норма: {cal['gdd_norm']} "
                     f"(база {cal['gdd_base_temp']} °C). {cal['note']}")
            st.caption(f"Источник: {cal['source']} (опыт региона, не ML-тариф).")
        except Exception as e:
            st.warning(f"Календарь недоступен: {e}")
        st.subheader(f"Агроалерты: {district_en} (прогноз 7 дней, Open-Meteo)")
        al = cached_alerts(district_en)
        key = {"ru": "msg_ru", "kz": "msg_kz", "en": "msg_en"}.get(lang, "msg_ru")
        if al.get("error"):
            st.caption(f"Алерты офлайн: {al['error']}. Показан только календарь.")
        elif not al.get("alerts"):
            st.success("✅ Угроз на 7 дней нет "
                       "(заморозки/жара/ливни/суховей не найдены).")
        else:
            for a in al["alerts"]:
                st.write(f"{a.get('type')}/{a.get('level')} {a.get('date')}: "
                         f"{(a.get(key) or a.get('msg_ru'))}")

    # ================= Поля и элеваторы =================
    with tab_map:
        st.subheader("Карта: риски, поля и элеваторы")
        st.markdown("🟩 **OSM-реальные поля** — зелёный контур | "
                    "🟧 **demo 1×2 км** — оранжевый пунктир (не выдаются за OSM) | "
                    "🔵 элеваторы | "
                    "светофор риска: 🟢<35 🟡35–60 🔴>60.")

        m = folium.Map(location=[52.3, 69.0], zoom_start=7)
        for d in districts:
            en = d["name_en"]
            r = (risks.get(f"{en}_risk") or {}).get("seasonal_risk")
            folium.CircleMarker(
                location=[d["lat"], d["lon"]], radius=9,
                color=_color(r), fill=True, fill_opacity=0.7,
                popup=(f"{d['name_ru']} ({en})<br>risk: {r}<br>"
                       f"{'кэш risk_example.json' if r is not None else 'риск офлайн'}"),
                tooltip=f"{d['name_ru']} — {r if r is not None else 'offline'}",
            ).add_to(m)

        # слой полей (OSM-реальные зелёные, demo-оранжевые пунктирные)
        if FIELDS_GEOJSON.exists():
            n_demo = sum(1 for f in fdata.get("features", [])
                         if (f.get("properties") or {}).get("demo"))
            n_real = len(fdata.get("features", [])) - n_demo
            folium.GeoJson(
                fdata,
                name=f"Поля OSM (реальных {n_real}, demo {n_demo})",
                style_function=_field_style,
                tooltip=folium.GeoJsonTooltip(
                    fields=["district_en", "area_ha", "source"],
                    aliases=["Район", "Площадь, га", "Источник"]),
                popup=folium.GeoJsonPopup(
                    fields=["district_en", "area_ha", "source"],
                    aliases=["Район", "Площадь, га", "Источник"]),
            ).add_to(m)
            st.caption(f"Поля: всего {len(fdata.get('features', []))} "
                       f"(реальных OSM: {n_real}, demo 1×2 км: {n_demo}). "
                       f"Демо — оранжевый пунктир, не выдаются за OSM.")
        else:
            st.warning("⚠️ data/fields/akmola_osm_fields.geojson нет — "
                       "запустите: python src/fields_osm.py")

        # слой элеваторов
        if GRANARIES_JSON.exists():
            for g in gdata.get("granaries", []):
                folium.Marker(
                    location=[g["lat"], g["lon"]],
                    icon=folium.Icon(color="blue", icon="warehouse",
                                     prefix="fa"),
                    popup=(f"🌾 {g.get('name_ru')} ({g.get('name_en')})<br>"
                           f"район: {g.get('district_en')}<br>"
                           f"координаты оценочные (Qoldau-карта, уточнить)"),
                    tooltip=f"🌾 {g.get('name_ru')}",
                ).add_to(m)
            st.caption("Элеваторы: 12 точек, координаты оценочные по "
                       "Qoldau granaries-map (подлежат уточнению).")

        folium.LayerControl().add_to(m)
        components.html(m._repr_html_(), height=520)

        # ближайший элеватор к выбранному району
        try:
            try:
                from src.logistics import nearest_elevator
            except ImportError:
                from logistics import nearest_elevator  # type: ignore
            ne = nearest_elevator(district_en)
            st.write(f"🚚 Ближайший элеватор к {district_en}: "
                     f"{ne['name_ru']} ({ne['name']}) — {ne['dist_km']} км. "
                     f"Координаты оценочные.")
        except Exception as e:
            st.caption(f"Логистика недоступна: {e}")

    # ================= Метрики =================
    with tab_metrics:
        st.subheader("Метрики 6 культур (hold-out 2021–2025, n=50)")
        rows = build_metrics_rows(metrics)
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
        st.caption("✅ LGBM — модель лучше бейзлайна среднего-5-лет; "
                   "🧪 experimental — LGBM хуже бейзлайна "
                   "(подсолнечник/рапс/лён: структурный сдвиг 2024–2025), "
                   "прогноз = baseline mean5, интервал ×1.5. "
                   "Источник: metrics/metrics.json, честно без подгонки.")

    # ================= О проекте =================
    with tab_about:
        st.subheader("О проекте Qagro")
        st.markdown(
            "**Команда Qagro:**\n"
            "- **Kairbek Ansar** — data pipeline / ML / API\n"
            "- **Samat Ablayhan (капитан)** — бот / веб / интеграция / сдача\n\n"
            "Трек 2 (AgriTech AI): прогноз урожайности 2026 по 10 районам "
            "Акмолы × 6 культур, декадный риск засухи, индексная страховка "
            "(decision support, не тариф) и рекомендации сева RU/KZ/EN.")
        st.markdown(
            "**Источники данных:**\n"
            "- [Бюро нацстатистики РК (stat.gov.kz)](https://stat.gov.kz/) — "
            "областные якоря урожайности\n"
            "- [NASA POWER (MERRA-2)](https://power.larc.nasa.gov/) — климат 2005–2025\n"
            "- [Open-Meteo (CC-BY 4.0)](https://open-meteo.com/en/docs) — "
            "ERA5 архив + прогноз 16 дней\n"
            "- [Geofabrik Kazakhstan (ODbL)](https://download.geofabrik.de/asia/kazakhstan.html) — "
            "запасной OSM-дамп полей\n"
            "- [Qoldau granaries-map](https://p-grain-receipt.qoldau.kz/ru/gr-info/granaries-map) — "
            "перечень 12 элеваторов (координаты оценочные)\n"
            "- [Copernicus Browser](https://browser.dataspace.copernicus.eu/) / "
            "[Sentinel Hub](https://www.sentinel-hub.com/) — Sentinel-2 для пилота NDVI")
        st.markdown(
            "**Методология (OSS-образцы, код оригинальный):**\n"
            "- [UniCrop (MIT)](https://github.com/CoDIS-Lab/UniCrop) — "
            "MJJA-фичи + LightGBM + SHAP\n"
            "- [crop-yield-prediction (MIT)](https://github.com/gsanaev/crop-yield-prediction-climate-change) — "
            "регрессия урожайности по климату\n"
            "- [Open-Meteo docs](https://open-meteo.com/en/docs) — декадный мониторинг\n"
            "- [CropBot (MIT)](https://github.com/mishagrol/CropBot) — UX-образец Telegram-бота")

    st.divider()
    st.caption("Дисклеймер: APPROX-культуры (oats/sunflower/rapeseed/flax) — линейное "
               "масштабирование от пшеницы, без обучающих данных. Районы — даунскейлинг "
               "областной статистики на центроиды из config/districts.yaml (не границы, "
               "не поля). Страховка — decision support, не тариф / "
               "шешімді қолдау, тариф емес / decision support, not a tariff.")


if _ST_RUN:
    main()
