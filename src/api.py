"""api.py — FastAPI для Qagro.

GET  /health  -> {"status": "ok", ...}
POST /predict {district_en, crop, [lang, weather, year, include_risk]} ->
     {y_pred, lo, hi, factors, p_loss, payout, risk, rec,
      approx, insurance, meta}
POST /report  {district_en, crop, [lang, weather]} -> application/pdf bytes
     (таблица + риски через reportlab, см. src/report_pdf.py).

Прогноз с weather=None берёт климат-норму района (средний MJJA 2016-2025).
Культуры: spring_wheat/barley (LGBM) + oats/sunflower/rapeseed/flax (APPROX).
Риск (Open-Meteo) — best-effort: при недоступности API возвращается
{"error": ..., "seasonal_risk": None} вместо выдуманных цифр.

Запуск (Windows PowerShell):
  uvicorn src.api:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]

try:  # пакетный запуск (uvicorn src.api:app из корня)
    from src.approx_crops import ALL_CROPS, is_approx
    from src.approx_crops import predict_approx
    from src.insurance import insurance_quote
    from src.predict import predict_yield
    from src.recommend import recommend_sowing
    from src.report_pdf import build_report_pdf
except ImportError:  # прямое использование из папки src/
    from approx_crops import ALL_CROPS, is_approx  # type: ignore
    from approx_crops import predict_approx  # type: ignore
    from insurance import insurance_quote  # type: ignore
    from predict import predict_yield  # type: ignore
    from recommend import recommend_sowing  # type: ignore
    from report_pdf import build_report_pdf  # type: ignore

app = FastAPI(title="Qagro API", version="0.1.0")


# ---------------------------------------------------------------- models
class PredictRequest(BaseModel):
    district_en: str = Field(examples=["Esil"])
    crop: str = Field(examples=["spring_wheat"])
    lang: str = Field(default="ru", examples=["ru"])
    weather: dict[str, Any] | None = Field(
        default=None,
        description="MJJA-агроклимат 2026 или None = климат-норма района",
    )
    year: int = Field(default=2026, description="Год для декадного риска")
    include_risk: bool = Field(default=True)


class ReportRequest(BaseModel):
    district_en: str = Field(examples=["Esil"])
    crop: str = Field(examples=["spring_wheat"])
    lang: str = Field(default="ru", examples=["ru"])
    weather: dict[str, Any] | None = None


# ---------------------------------------------------------------- helpers
def _predict(district_en: str, crop: str, weather: dict | None) -> dict:
    if crop not in ALL_CROPS:
        raise ValueError(f"crop={crop!r} неизвестна. Допустимо: {list(ALL_CROPS)}.")
    if is_approx(crop):
        return predict_approx(district_en, crop, weather)
    return predict_yield(district_en, crop, weather)


def _safe_risk(district_en: str, year: int = 2026) -> dict:
    """Декадный риск best-effort: при ошибке сети — dict с error, без моков."""
    try:
        try:
            from src.risk import decade_risk
        except ImportError:
            from risk import decade_risk  # type: ignore
        return decade_risk(district_en, year)
    except Exception as e:  # RuntimeError сети / ValueError района
        return {"district_en": district_en, "year": year,
                "seasonal_risk": None, "seasonal_light": None,
                "decades": [], "stages": {},
                "error": f"{type(e).__name__}: {e}"}


def _full_result(district_en: str, crop: str, lang: str = "ru",
                 weather: dict | None = None, year: int = 2026,
                 include_risk: bool = True) -> dict:
    lang = (lang or "ru").lower()
    if lang not in ("ru", "kz", "en"):
        raise ValueError(f"lang={lang!r} недопустим. Допустимо: ru, kz, en.")
    pred = _predict(district_en, crop, weather)
    try:
        ins = insurance_quote(district_en, crop)
    except Exception as e:
        raise ValueError(f"insurance: {e}") from e
    try:
        rec = recommend_sowing(district_en, crop, lang)
    except Exception as e:
        raise ValueError(f"recommend: {e}") from e
    risk: dict | None = _safe_risk(district_en, year) if include_risk else None
    payout = {"expected_payout_ha": ins["expected_payout_ha"],
              "payout_at_pred_ha": ins["payout_at_pred_ha"],
              "mean5_c_ha": ins["mean5_c_ha"],
              "strike_c_ha": ins["strike_c_ha"],
              "price_kzt_per_t": ins["price_kzt_per_t"]}
    return {
        "district_en": district_en, "crop": crop, "lang": lang,
        "approx": bool(pred.get("approx") or ins.get("approx")),
        "y_pred": pred["y_pred"], "lo": pred["lo10"], "hi": pred["hi90"],
        "factors": pred.get("factors", []),
        "p_loss": ins["p_loss"], "payout": payout,
        "risk": risk, "rec": rec,
        "insurance": ins, "pred": pred,
        "meta": {"weather_source": (pred.get("meta") or {}).get("weather_source"),
                 "year": year},
    }


# ---------------------------------------------------------------- routes
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "qagro-api", "crops": list(ALL_CROPS)}


@app.get("/districts")
def districts() -> dict:
    import yaml

    with open(ROOT / "config" / "districts.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.get("/fields")
def fields(district_en: str | None = None) -> dict:
    """Оцифрованные поля: data/fields/akmola_osm_fields.geojson.

    Query ?district_en=Esil — фильтр по району. Без моков: если файла нет —
    500 с честной ошибкой (сначала python src/fields_osm.py).
    """
    import json

    p = ROOT / "data" / "fields" / "akmola_osm_fields.geojson"
    if not p.exists():
        raise HTTPException(status_code=500, detail=(
            "akmola_osm_fields.geojson не найден. "
            "Запустите: python src/fields_osm.py"))
    fc = json.loads(p.read_text(encoding="utf-8"))
    if district_en:
        fc = dict(fc, features=[
            f for f in fc.get("features", [])
            if (f.get("properties") or {}).get("district_en") == district_en])
    return fc


@app.get("/granaries")
def granaries() -> dict:
    """12 элеваторов Акмолы (координаты оценочные, см. granaries.json)."""
    import json

    p = ROOT / "data" / "fields" / "granaries.json"
    if not p.exists():
        raise HTTPException(status_code=500,
                            detail="granaries.json не найден")
    return json.loads(p.read_text(encoding="utf-8"))


@app.post("/predict")
def predict(req: PredictRequest) -> dict:
    try:
        return _full_result(req.district_en, req.crop, req.lang,
                            req.weather, req.year, req.include_risk)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/report")
def report(req: ReportRequest) -> Response:
    """PDF-отчёт: таблица (прогноз/страховка) + риски + рекомендация."""
    try:
        full = _full_result(req.district_en, req.crop, req.lang, req.weather)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    import yaml

    with open(ROOT / "config" / "districts.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ru = next((d.get("name_ru") for d in cfg.get("districts", [])
               if d.get("name_en") == req.district_en), None)
    pdf = build_report_pdf(req.district_en, req.crop, req.lang,
                           pred=full["pred"], ins=full["insurance"],
                           risk=full["risk"], rec=full["rec"],
                           district_ru=ru)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f"attachment; filename=qagro_{req.district_en}_{req.crop}.pdf"})


if __name__ == "__main__":  # python -m src.api
    import uvicorn

    uvicorn.run("src.api:app", host="127.0.0.1", port=8000)
