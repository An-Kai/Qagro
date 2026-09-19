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
           "offline": "📡 Интернет слабый — посчитано по сохранённым данным."},
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
           "offline": "📡 Интернет нашар — сақталған дерекпен есептелді."},
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
           "offline": "📡 Weak internet — used saved data."},
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

    cfg = load_cfg()
    districts = cfg.get("districts", [])
    crops = cfg.get("crops", [])

    lang = st.sidebar.selectbox("🌍 Язык / Тіл / Language",
                                options=["ru", "kz", "en"], index=0)
    T = UI[lang]
    wheat_price = st.sidebar.slider(T["price"], min_value=WHEAT_PRICE_MIN,
                                    max_value=WHEAT_PRICE_MAX,
                                    value=WHEAT_PRICE_DEFAULT, step=1000)

    st.title(T["title"])
    st.write(T["sub"])

    dlabel = {d["name_en"]: f"{d.get(f'name_{lang}', d['name_ru'])}" for d in districts}
    clabel = {c["id"]: f"{CROP_ICON.get(c['id'], '🌱')} {c.get(f'name_{lang}', c['id'])}"
              for c in crops}

    st.header(T["step1"])
    district_en = st.selectbox("📍", options=list(dlabel.keys()),
                               format_func=lambda k: dlabel[k],
                               index=list(dlabel.keys()).index("Esil")
                               if "Esil" in dlabel else 0,
                               label_visibility="collapsed")
    st.header(T["step2"])
    crop = st.selectbox("🌱", options=list(clabel.keys()),
                        format_func=lambda k: clabel[k],
                        label_visibility="collapsed")

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
        st.success(f"### {T['yield']}: ~{y} ц/га\n\n"
                   + ({"ru": f"Обычно бывает {lo}–{hi}. Среднее за 5 лет: {mean5}.",
                       "kz": f"Әдетте {lo}–{hi}. 5 жылдық орташа: {mean5}.",
                       "en": f"Usually {lo}–{hi}. 5-year average: {mean5}."}[lang]))
    with c2:
        st.info(f"### {light} {T['risk']}: {_w(p_loss, lang)}\n\n"
                + ({"ru": "Зелёный — спокойно, жёлтый — следите, красный — готовьтесь.",
                    "kz": "Жасыл — тыныш, сары — бақылаңыз, қызыл — дайындалыңыз.",
                    "en": "Green — calm, yellow — watch, red — prepare."}[lang]))
    c3, c4 = st.columns(2)
    with c3:
        st.warning(f"### {T['ins']}: ~{payout} ₸/га\n\n"
                   + ({"ru": f"Шанс не добрать 80%: {round(p_loss*100)} из 100. Это ориентир, не тариф.",
                       "kz": f"80%-ға жетпеу: 100-ден {round(p_loss*100)}. Бұл бағдар, тариф емес.",
                       "en": f"Below-80% chance: {round(p_loss*100)} in 100. Estimate, not a tariff."}[lang]))
    with c4:
        st.success(f"### {T['todo']}: {rec['window']}\n\n{rec['message']}")
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
                       mime="application/pdf", type="primary")

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
    tab_risk, tab_fields = st.tabs(
        ["🟢🟡🔴 " + ({"ru": "Риски", "kz": "Қауіптер", "en": "Risks"}[lang]),
         "🌾 " + ({"ru": "Поля и элеваторы", "kz": "Егістік және элеваторлар", "en": "Fields & elevators"}[lang])])
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
            rows.append({"district": d.get(f"name_{lang}", en), "risk": r})
        m = folium.Map(location=[52.3, 69.0], zoom_start=7)
        for d in districts:
            en = d["name_en"]
            r = (risks.get(f"{en}_risk") or {}).get("seasonal_risk")
            folium.CircleMarker(
                location=[d["lat"], d["lon"]], radius=12,
                color=_color(r), fill=True, fill_opacity=0.7,
                popup=f"{d.get(f'name_{lang}', en)}: {r}",
                tooltip=f"{d.get(f'name_{lang}', en)} — {r if r is not None else 'offline'}",
            ).add_to(m)
        # NDVI-точки Sentinel-2 (5 реальных)
        for pt in ndvi_pts[:20]:
            try:
                folium.CircleMarker(
                    location=[pt.get("lat", 51.95), pt.get("lon", 66.40)], radius=5,
                    color="purple", fill=True, fill_opacity=0.8,
                    popup=f"NDVI {pt.get('ndvi_mean')} ({pt.get('date')})",
                    tooltip=f"NDVI {pt.get('ndvi_mean')}",
                ).add_to(m)
            except Exception:
                pass
        folium.LayerControl().add_to(m)
        components.html(m._repr_html_(), height=480)
        st.caption("🟢<35 🟡35–60 🔴>60 | 🟣 NDVI Sentinel-2 (5 точек, июнь 2024).")
        st.dataframe(pd.DataFrame(rows).sort_values("risk", ascending=False),
                     use_container_width=True)

    with tab_fields:
        feats = [f for f in fdata.get("features", [])
                 if (f.get("properties") or {}).get("district_en") == district_en]
        areas = [float((f.get("properties") or {}).get("area_ha") or 0) for f in feats]
        n_demo = sum(1 for f in feats if (f.get("properties") or {}).get("demo"))
        st.write(f"🌾 {len(feats)} " +
                 ({"ru": f"полей в районе (OSM: {len(feats)-n_demo}, demo: {n_demo}), "
                         f"всего ~{round(sum(areas))} га",
                   "kz": f"аудандағы егістік (OSM: {len(feats)-n_demo}, demo: {n_demo}), "
                         f"барлығы ~{round(sum(areas))} га",
                   "en": f"fields in district (OSM: {len(feats)-n_demo}, demo: {n_demo}), "
                         f"total ~{round(sum(areas))} ha"}[lang]))
        m2 = folium.Map(location=[next(d["lat"] for d in districts if d["name_en"] == district_en),
                                  next(d["lon"] for d in districts if d["name_en"] == district_en)],
                        zoom_start=10)
        if feats:
            folium.GeoJson(
                {"type": "FeatureCollection", "features": feats},
                style_function=_field_style,
                tooltip=folium.GeoJsonTooltip(fields=["district_en", "area_ha", "source"],
                                              aliases=["District", "ha", "Source"]),
            ).add_to(m2)
        for g in gdata.get("granaries", []):
            folium.Marker(
                location=[g["lat"], g["lon"]],
                icon=folium.Icon(color="blue", icon="warehouse", prefix="fa"),
                popup=f"🌾 {g.get('name_ru')} (~{g.get('dist_km', '?')} км)",
                tooltip=f"🌾 {g.get('name_ru')}",
            ).add_to(m2)
            # маршрут район -> элеватор
            try:
                dc = next(d for d in districts if d["name_en"] == district_en)
                folium.PolyLine([[dc["lat"], dc["lon"]], [g["lat"], g["lon"]]],
                                color="blue", weight=1, opacity=0.3).add_to(m2)
            except Exception:
                pass
        folium.LayerControl().add_to(m2)
        components.html(m2._repr_html_(), height=480)
        if _elev:
            st.write(f"🚚 {_elev.get('name_ru')} — {_elev.get('dist_km')} км.")

    # ---------- Агроном / хозяйство / календарь / о проекте ----------
    farm_label = {"ru": "🚜 Моё хозяйство", "kz": "🚜 Менің шаруашылығым",
                  "en": "🚜 My farm"}[lang]
    plus_label = {"ru": "🔬 Справочник и деньги", "kz": "🔬 Анықтама және ақша",
                  "en": "🔬 Guide & money"}[lang]
    tab_agro, tab_farm, tab_plus, tab_cal, tab_about = st.tabs(
        [T["agro"], farm_label, plus_label, T["cal"], T["about"]])
    with tab_agro:
        hist = panel[(panel["district_en"] == district_en) & (panel["crop"] == crop)].sort_values("year")
        fig = go.Figure()
        if not hist.empty:
            fig.add_trace(go.Scatter(x=hist["year"].tolist(), y=hist["yield_c_ha"].tolist(),
                                     mode="lines+markers", name="fact"))
        fig.add_trace(go.Scatter(x=[2026], y=[pred["y_pred"]], mode="markers", name="2026",
                                 error_y=dict(type="data",
                                              array=[pred["hi90"] - pred["y_pred"]],
                                              arrayminus=[pred["y_pred"] - pred["lo10"]])))
        fig.update_layout(xaxis_title="year", yaxis_title="c/ha")
        st.plotly_chart(fig, use_container_width=True)
        rows = build_metrics_rows(metrics)
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
        slice_df = panel[(panel["district_en"] == district_en) & (panel["crop"] == crop)]
        buf = io.StringIO()
        slice_df.to_csv(buf, index=False)
        st.download_button(T["csv"], buf.getvalue(),
                           file_name=f"qagro_{district_en}_{crop}.csv", mime="text/csv")
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
            st.write(f"🌾 {len(fields)} " +
                     ({"ru": "моих полей", "kz": "менің егістігім", "en": "my fields"}[lang]))
            with st.form("add_field"):
                fn = st.text_input("Название / Атауы / Name", "Поле 1")
                farea = st.number_input("га / ha", 10.0, 2000.0, 100.0)
                if st.form_submit_button("➕"):
                    try:
                        dc = next(d for d in districts if d["name_en"] == district_en)
                        add_field(fn, float(dc["lat"]), float(dc["lon"]),
                                  float(farea), crop)
                        st.success("OK")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            for f in fields:
                c1, c2 = st.columns([4, 1])
                c1.write(f"#{f['id']} {f['name']} — {f['area_ha']} га, {f['crop']}")
                if c2.button("✖", key=f"del_{f['id']}"):
                    delete_field(int(f["id"]))
                    st.rerun()
            with st.form("add_note"):
                if fields:
                    fid = st.selectbox("Поле", [f["id"] for f in fields])
                    ptype = st.selectbox("Проблема", ["weeds", "pests", "disease",
                                                      "lodging", "drought", "other"])
                    txt = st.text_input("Заметка", "")
                    if st.form_submit_button("📝"):
                        try:
                            add_note(int(fid), ptype, txt)
                            st.success("OK")
                        except Exception as e:
                            st.error(str(e))
            try:
                sp = check_spray_window(district_en)
                key = {"ru": "verdict_ru", "kz": "verdict_kz", "en": "verdict_en"}[lang]
                st.info(f"🧴 {sp.get(key)}")
            except Exception as e:
                st.caption(f"Spray offline: {e}")
    with tab_plus:
        # v4: справочник + NPK + экономика.
        try:
            from src.guide_data import lookup as _lookup
            from src.fertilizer import calc_npk as _npk
            from src.economics import profit_ha as _profit
            items = _lookup(crop)[:4]
            nk, sk, ak = {"ru": ("name_ru", "signs_ru", "action_ru"),
                          "kz": ("name_kz", "signs_kz", "action_kz"),
                          "en": ("name_en", "signs_en", "action_en")}[lang]
            for it in items:
                st.write(f"🔬 **{it.get(nk)}**: {'; '.join(it.get(sk, [])[:2])}. → {it.get(ak)}")
            goal = st.slider("🎯 Цель ц/га / Мақсат / Goal", 5.0, 30.0, 15.0)
            npk = _npk(crop, float(goal), "medium")
            st.write(f"🧪 NPK: N {npk['N_kg_ha']} · P {npk['P_kg_ha']} · K {npk['K_kg_ha']} кг/га")
            pr = _profit(float(pred["y_pred"]), float(wheat_price))
            st.write(f"💰 ~{int(pr['profit_kzt_ha'])} ₸/га "
                     f"({int(pr['revenue_kzt_ha'])} − {int(pr['cost_kzt_ha'])})")
        except Exception as e:
            st.warning(str(e))
    with tab_cal:
        try:
            cal = sowing_calendar(crop, lang)
            st.write(f"🌱 **{cal['sowing_window']}**; уборка: **{cal['harvest_window']}**.")
        except Exception as e:
            st.warning(str(e))
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
        st.write("**Qagro** — Kairbek Ansar (data/ML/API) + Samat Ablayhan, captain (bot/web).")
        st.write("stat.gov.kz · NASA POWER · Open-Meteo · FAOSTAT · OSM · Qoldau · Copernicus/Sentinel-2")


if _ST_RUN:
    main()
