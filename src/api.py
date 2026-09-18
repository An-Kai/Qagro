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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]

try:  # пакетный запуск (uvicorn src.api:app из корня)
    from src.alerts import check_alerts
    from src.approx_crops import ALL_CROPS, is_approx
    from src.approx_crops import predict_approx
    from src.calendar import sowing_calendar
    from src.insurance import insurance_quote
    from src.predict import predict_yield
    from src.recommend import recommend_sowing
    from src.report_pdf import build_report_pdf
except ImportError:  # прямое использование из папки src/
    from alerts import check_alerts  # type: ignore
    from approx_crops import ALL_CROPS, is_approx  # type: ignore
    from approx_crops import predict_approx  # type: ignore
    from calendar import sowing_calendar  # type: ignore
    from insurance import insurance_quote  # type: ignore
    from predict import predict_yield  # type: ignore
    from recommend import recommend_sowing  # type: ignore
    from report_pdf import build_report_pdf  # type: ignore

app = FastAPI(title="Qagro API", version="0.1.0")

# CORS: фронт/бот/Streamlit ходят с других origin — разрешаем без авторизации.
# БД/авторизацию не добавляем (C2: hardening без усложнения).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Кэш predict в памяти 5 мин: dict + time, без БД/Redis.
_PREDICT_CACHE: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 300  # секунд


@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    # Любой необработанный ValueError -> 422 с понятным RU/EN сообщением.
    return JSONResponse(
        status_code=422,
        content={"detail": f"Некорректный запрос / Invalid request: {exc}"},
    )


def _err422(exc: Exception) -> str:
    return f"Некорректный запрос / Invalid request: {exc}"


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
def _known_districts() -> list[str]:
    """Допустимые district_en из config/districts.yaml (fallback — панель)."""
    try:
        import yaml

        with open(ROOT / "config" / "districts.yaml", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        names = sorted(
            d.get("name_en") for d in cfg.get("districts", []) if d.get("name_en")
        )
        if names:
            return names
    except Exception:
        pass
    return ["Atbasar", "Bulandy", "Burabay", "Esil", "Kokshetau",
            "Sandyktau", "Shortandy", "Tselinograd", "Zerenda", "Zhaksy"]


def _model_count() -> int:
    return sum(1 for c in ALL_CROPS if (ROOT / "models" / f"lgbm_{c}.pkl").exists())


def _validate_inputs(district_en: str, crop: str, lang: str = "ru") -> None:
    known_d = _known_districts()
    if district_en not in known_d:
        raise ValueError(
            f"district_en={district_en!r} неизвестен / unknown. "
            f"Допустимо / allowed: {known_d}."
        )
    if crop not in ALL_CROPS:
        raise ValueError(
            f"crop={crop!r} неизвестна / unknown crop. "
            f"Допустимо / allowed: {list(ALL_CROPS)}."
        )
    if (lang or "ru").lower() not in ("ru", "kz", "en"):
        raise ValueError(
            f"lang={lang!r} недопустим / invalid. Допустимо / allowed: ru, kz, en."
        )


def _cache_key(district_en: str, crop: str, lang: str,
               weather: dict | None, year: int, include_risk: bool) -> str:
    import json as _json

    w = _json.dumps(weather or {}, sort_keys=True, default=str, ensure_ascii=False)
    return f"{district_en}|{crop}|{lang}|{w}|{year}|{int(bool(include_risk))}"


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
    _validate_inputs(district_en, crop, lang)
    lang = (lang or "ru").lower()
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
        "experimental": bool(pred.get("experimental") or ins.get("experimental")),
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
    known_d = _known_districts()
    return {
        "status": "ok",
        "service": "qagro-api",
        "crops": list(ALL_CROPS),
        "districts": known_d,
        "counts": {
            "districts": len(known_d),
            "crops": len(list(ALL_CROPS)),
            "models": _model_count(),
        },
    }


@app.get("/metrics")
def metrics() -> dict:
    """metrics/metrics.json обрезанно: без абсолютных scatter-путей."""
    import json

    p = ROOT / "metrics" / "metrics.json"
    if not p.exists():
        raise HTTPException(status_code=500, detail="metrics/metrics.json не найден")
    data = json.loads(p.read_text(encoding="utf-8"))
    trimmed: dict[str, Any] = {}
    for crop, m in data.items():
        if not isinstance(m, dict):
            trimmed[crop] = m
            continue
        trimmed[crop] = {k: v for k, v in m.items() if k != "scatter"}
    return {"crops": trimmed, "counts": {"crops": len(trimmed)}}


@app.get("/version")
def version() -> dict:
    """git sha + дата сборки. Без внешних зависимостей, offline-safe."""
    import subprocess
    from datetime import datetime, timezone

    sha = "unknown"
    git_date = "unknown"
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=str(ROOT),
        ).stdout.strip() or "unknown"
    except Exception:
        pass
    try:
        git_date = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=iso"],
            capture_output=True, text=True, timeout=5, cwd=str(ROOT),
        ).stdout.strip() or "unknown"
    except Exception:
        pass
    return {
        "service": "qagro-api",
        "api_version": app.version,
        "git_sha": sha,
        "git_date": git_date,
        "build_date": datetime.now(timezone.utc).isoformat(),
    }


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


@app.get("/calendar")
def calendar(crop: str = "spring_wheat", lang: str = "ru") -> dict:
    """C8: посевной календарь Акмолы (справочник, source=agro-practice)."""
    try:
        return sowing_calendar(crop, lang)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=_err422(e)) from e


@app.get("/alerts")
def alerts(district_en: str = "Esil", days: int = 7) -> dict:
    """C8: агроалерты по прогнозу Open-Meteo (best-effort, без моков).

    При недоступности сети — 200 с {"alerts": [], "error": ...}, а не выдумка.
    """
    known_d = _known_districts()
    if district_en not in known_d:
        raise HTTPException(status_code=422, detail=_err422(
            f"district_en={district_en!r} неизвестен. Допустимо: {known_d}."))
    try:
        items = check_alerts(district_en, days)
    except Exception as e:
        return {"district_en": district_en, "alerts": [],
                "count": 0, "error": f"{type(e).__name__}: {e}"}
    return {"district_en": district_en, "alerts": items, "count": len(items)}


@app.post("/predict")
def predict(req: PredictRequest) -> dict:
    import time as _time

    key = _cache_key(req.district_en, req.crop, req.lang,
                     req.weather, req.year, req.include_risk)
    now = _time.time()
    hit = _PREDICT_CACHE.get(key)
    if hit and (now - hit[0]) < CACHE_TTL:
        return hit[1]
    try:
        res = _full_result(req.district_en, req.crop, req.lang,
                           req.weather, req.year, req.include_risk)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=_err422(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    _PREDICT_CACHE[key] = (now, res)
    return res


@app.post("/report")
def report(req: ReportRequest) -> Response:
    """PDF-отчёт: таблица (прогноз/страховка) + риски + рекомендация + C8."""
    try:
        full = _full_result(req.district_en, req.crop, req.lang, req.weather)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=_err422(e)) from e
    import yaml

    with open(ROOT / "config" / "districts.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ru = next((d.get("name_ru") for d in cfg.get("districts", [])
               if d.get("name_en") == req.district_en), None)
    # C8 best-effort: календарь/элеватор офлайн, алерты онлайн (без моков).
    try:
        cal = sowing_calendar(req.crop, req.lang)
    except Exception:
        cal = None
    try:
        alerts_items = check_alerts(req.district_en)
        alerts_err = None
    except Exception as e:
        alerts_items, alerts_err = None, f"{type(e).__name__}: {e}"
    try:
        try:
            from src.logistics import nearest_elevator
        except ImportError:
            from logistics import nearest_elevator  # type: ignore
        elev = nearest_elevator(req.district_en)
    except Exception:
        elev = None
    pdf = build_report_pdf(req.district_en, req.crop, req.lang,
                           pred=full["pred"], ins=full["insurance"],
                           risk=full["risk"], rec=full["rec"],
                           district_ru=ru, calendar=cal,
                           alerts=alerts_items, alerts_error=alerts_err,
                           elevator=elev)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f"attachment; filename=qagro_{req.district_en}_{req.crop}.pdf"})


if __name__ == "__main__":  # python -m src.api
    import uvicorn

    uvicorn.run("src.api:app", host="127.0.0.1", port=8000)
