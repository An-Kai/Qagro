"""Streamlit-дашборд Qagro.

Селекты района/культуры/языка, метрики, график Plotly (факт vs прогноз),
карта Folium с рисками, выгрузка CSV/GeoJSON/PDF, дисклеймер про APPROX
и даунскейлинг районов.

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

import pandas as pd
import streamlit as st
import yaml

try:
    from src.approx_crops import APPROX_YIELD_FACTOR, is_approx
    from src.approx_crops import predict_approx
    from src.insurance import insurance_quote
    from src.predict import predict_yield
    from src.recommend import recommend_sowing
    from src.report_pdf import build_report_pdf
except ImportError:  # запуск с другой cwd
    from approx_crops import APPROX_YIELD_FACTOR, is_approx  # type: ignore
    from approx_crops import predict_approx  # type: ignore
    from insurance import insurance_quote  # type: ignore
    from predict import predict_yield  # type: ignore
    from recommend import recommend_sowing  # type: ignore
    from report_pdf import build_report_pdf  # type: ignore

PANEL = ROOT / "data" / "processed" / "akmola_panel.csv"
METRICS = ROOT / "metrics" / "metrics.json"
RISK_EXAMPLE = ROOT / "reports" / "risk_example.json"

st.set_page_config(page_title="Qagro — Akmola yield & risk", layout="wide")


@st.cache_data
def load_cfg() -> dict:
    with open(ROOT / "config" / "districts.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@st.cache_data
def load_panel() -> pd.DataFrame:
    return pd.read_csv(PANEL)


@st.cache_data
def load_metrics() -> dict:
    if METRICS.exists():
        return json.loads(METRICS.read_text(encoding="utf-8"))
    return {}


@st.cache_data
def load_risks() -> dict:
    if RISK_EXAMPLE.exists():
        return json.loads(RISK_EXAMPLE.read_text(encoding="utf-8"))
    return {}


def predict_none(district_en: str, crop: str) -> dict:
    if is_approx(crop):
        return predict_approx(district_en, crop, None)
    return predict_yield(district_en, crop, None)


cfg = load_cfg()
districts = cfg.get("districts", [])
crops = cfg.get("crops", [])
panel = load_panel()
metrics = load_metrics()
risks = load_risks()

dlabel = {d["name_en"]: f"{d['name_ru']} ({d['name_en']})" for d in districts}
clabel = {c["id"]: f"{c.get('name_ru', c['id'])} ({c['id']})" for c in crops}

st.title("Qagro — прогноз урожайности и риски (Акмола, 2026)")

col1, col2, col3 = st.columns(3)
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
with col3:
    lang = st.selectbox("Язык / Тіл / Language",
                        options=["ru", "kz", "en"], index=0)

# ---- вычисления (локальные, без сети) ----
try:
    pred = predict_none(district_en, crop)
    ins = insurance_quote(district_en, crop)
    rec = recommend_sowing(district_en, crop, lang)
    err = None
except Exception as e:
    pred = ins = rec = None
    err = f"{type(e).__name__}: {e}"

if err:
    st.error(f"⚠️ {err}")
    st.stop()

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
if approx:
    st.warning("⚠️ APPROX: культура без обучающих данных — "
               "масштабирование от пшеницы (см. src/approx_crops.py). "
               "Decision support, не тариф.")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("y_pred 2026 (ц/га)", pred["y_pred"])
m2.metric("80% интервал", f"{pred['lo10']}–{pred['hi90']}")
m3.metric("Сезонный риск", seasonal_txt)
m4.metric("P_loss", ins["p_loss"])
m5.metric("Выплата (KZT/га)", ins["expected_payout_ha"])

st.subheader("Страховка и рекомендация")
st.write(f"mean5={ins['mean5_c_ha']} {ins['mean5_years']}, "
         f"strike={ins['strike_c_ha']}, price={ins['price_kzt_per_t']} KZT/t. "
         f"{ins['disclaimer']}")
st.write(f"🌱 {rec['window']}: {rec['message']} "
         f"({' / '.join(rec.get('actions', []))})")

# ---- график Plotly: факт vs прогноз ----
st.subheader("Факт vs прогноз")
import plotly.graph_objects as go

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

# ---- метрики модели ----
st.subheader("Качество модели (hold-out 2021–2025)")
if crop in metrics:
    lm = metrics[crop]["lgbm"]
    st.write(f"LGBM {crop}: MAE={lm['mae']:.2f}, RMSE={lm['rmse']:.2f}, "
             f"R²={lm['r2']:.2f}, n={lm['n']}")
else:
    st.write(f"{crop}: обученной модели нет (APPROX). "
             f"Метрики пшеницы: {metrics.get('spring_wheat', {}).get('lgbm', {})}")

# ---- карта Folium: риски + поля OSM + элеваторы ----
st.subheader("Карта: риски, поля и элеваторы")
import folium
import streamlit.components.v1 as components

FIELDS_GEOJSON = ROOT / "data" / "fields" / "akmola_osm_fields.geojson"
GRANARIES_JSON = ROOT / "data" / "fields" / "granaries.json"


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
    fdata = json.loads(FIELDS_GEOJSON.read_text(encoding="utf-8"))
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
    gdata = json.loads(GRANARIES_JSON.read_text(encoding="utf-8"))
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

# PDF
d_ru = next((d.get("name_ru") for d in districts
             if d.get("name_en") == district_en), None)
pdf_bytes = build_report_pdf(district_en, crop, lang, pred=pred, ins=ins,
                             risk=risk or {"seasonal_risk": None,
                                           "error": "offline in Streamlit demo"},
                             rec=rec, district_ru=d_ru)
st.download_button("⬇️ PDF-отчёт", pdf_bytes,
                   file_name=f"qagro_{district_en}_{crop}.pdf",
                   mime="application/pdf")

st.divider()
st.caption("Дисклеймер: APPROX-культуры (oats/sunflower/rapeseed/flax) — линейное "
           "масштабирование от пшеницы, без обучающих данных. Районы — даунскейлинг "
           "областной статистики на центроиды из config/districts.yaml (не границы, "
           "не поля). Страховка — decision support, не тариф / "
           "шешімді қолдау, тариф емес / decision support, not a tariff.")
