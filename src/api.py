"""api.py — FastAPI для Qagro.

GET  /health  -> {"status": "ok", ...}
GET  /metrics /version /districts /fields /granaries /calendar /agrodata
     /alerts /guide /fertilizer /economy /soil /intervals /gis /compare /season
     + platform_api: /myfields /journal /spray (см. src/platform_api.py)
POST /predict {district_en, crop, [lang, weather, year, include_risk]} ->
     {y_pred, lo, hi, factors, p_loss, payout, risk, rec,
      approx, experimental, insurance, meta}
     Кэш 5 мин; query ?fresh=true = пересчёт мимо кэша (по умолчанию
     ?fresh=false — брать кэш; заголовок ответа X-Qagro-Cache: HIT/MISS).
POST /report  {district_en, crop, [lang, weather]} -> application/pdf bytes
     (таблица + риски через reportlab, см. src/report_pdf.py).

Прогноз с weather=None берёт климат-норму района (средний MJJA 2016-2025).
Культуры: 6 моделей-блендов LightGBM+Ridge (models/lgbm_*.pkl); культуры с
below_baseline=true в metrics/metrics.json (сейчас: flax, rapeseed) идут
через честный experimental fallback (baseline mean5, интервал ×1.5,
флаг experimental:true); APPROX-масштаб от пшеницы — только если .pkl
модели нет вообще (см. src/approx_crops.py, src/predict.py).
Риск (Open-Meteo) — best-effort: при недоступности API возвращается
{"error": ..., "seasonal_risk": None} вместо выдуманных цифр.

Режимы (env, без новых обязательных переменных для локали):
  QAGRO_ENV=local (дефолт): CORS *, без rate-limit — для демо/CLI/тестов.
  QAGRO_ENV=production: требует QAGRO_CORS_ORIGINS (список через запятую,
  "*" запрещён — fail-fast), включает rate-limit и лимит тела запроса.
  QAGRO_RATE_LIMIT_PER_MIN (дефолт 0=выкл; в prod рекомендуется 60),
  QAGRO_MAX_BODY_BYTES (дефолт 262144), QAGRO_LOG_LEVEL (дефолт INFO).

Запуск (Windows PowerShell):
  uvicorn src.api:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import logging
import os
import time as _time_mod
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

log = logging.getLogger("qagro.api")
logging.basicConfig(level=os.getenv("QAGRO_LOG_LEVEL", "INFO").upper())

ROOT = Path(__file__).resolve().parents[1]

try:  # пакетный запуск (uvicorn src.api:app из корня)
    from src.alerts import check_alerts
    from src.approx_crops import ALL_CROPS, is_approx
    from src.approx_crops import predict_approx
    from src.sowing_calendar import sowing_calendar
    from src.insurance import insurance_quote
    from src.predict import predict_yield
    from src.recommend import recommend_sowing
    from src.report_pdf import build_report_pdf
except ImportError:  # прямое использование из папки src/
    from alerts import check_alerts  # type: ignore
    from approx_crops import ALL_CROPS, is_approx  # type: ignore
    from approx_crops import predict_approx  # type: ignore
    from sowing_calendar import sowing_calendar  # type: ignore
    from insurance import insurance_quote  # type: ignore
    from predict import predict_yield  # type: ignore
    from recommend import recommend_sowing  # type: ignore
    from report_pdf import build_report_pdf  # type: ignore

app = FastAPI(title="Qagro API", version="0.1.0")

# --- режимы local/production (без новых обязательных переменных для локали) ---
QAGRO_ENV = os.getenv("QAGRO_ENV", "local").strip().lower()
_QAGRO_ORIGINS_RAW = os.getenv("QAGRO_CORS_ORIGINS", "*").strip()
QAGRO_RATE_LIMIT_PER_MIN = int(os.getenv("QAGRO_RATE_LIMIT_PER_MIN", "0") or 0)
QAGRO_MAX_BODY_BYTES = int(os.getenv("QAGRO_MAX_BODY_BYTES", "262144") or 262144)
if QAGRO_ENV == "production" and _QAGRO_ORIGINS_RAW == "*":
    raise RuntimeError(
        "QAGRO_ENV=production требует явный QAGRO_CORS_ORIGINS "
        "(список origin через запятую, '*' запрещён).")
_CORS_ORIGINS = (["*"] if _QAGRO_ORIGINS_RAW == "*"
                 else [o.strip() for o in _QAGRO_ORIGINS_RAW.split(",") if o.strip()])
log.info("Qagro API mode=%s cors=%s rate_limit/min=%s max_body=%s",
         QAGRO_ENV, ("*" if _QAGRO_ORIGINS_RAW == "*" else f"{len(_CORS_ORIGINS)} origins"),
         QAGRO_RATE_LIMIT_PER_MIN, QAGRO_MAX_BODY_BYTES)

# CORS: локально — открыто для бота/Streamlit/демо; в production — только явные origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"] if _QAGRO_ORIGINS_RAW == "*" else ["GET", "POST", "OPTIONS"],
    allow_headers=["*"] if _QAGRO_ORIGINS_RAW == "*" else ["Content-Type", "Authorization"],
)


@app.middleware("http")
async def _budget_middleware(request: Request, call_next):
    """Request budget: лимит тела + rate-limit (только production)."""
    if QAGRO_ENV == "production":
        try:
            clen = int(request.headers.get("content-length") or 0)
        except (TypeError, ValueError):
            clen = 0
        if clen > QAGRO_MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={
                "detail": f"Тело запроса > {QAGRO_MAX_BODY_BYTES} байт / Body too large."})
        if (QAGRO_RATE_LIMIT_PER_MIN > 0
                and request.url.path in ("/predict", "/report")):
            ip = (request.client.host if request.client else "?")
            now = _time_mod.time()
            bucket = _RATE_BUCKET.setdefault(ip, [])
            bucket[:] = [t for t in bucket if now - t < 60.0]
            if len(bucket) >= QAGRO_RATE_LIMIT_PER_MIN:
                return JSONResponse(status_code=429, content={
                    "detail": "Слишком много запросов / Too many requests. Подождите минуту."})
            bucket.append(now)
    return await call_next(request)


# Кэш predict в памяти 5 мин: dict + time, без БД/Redis.
_RATE_BUCKET: dict[str, list[float]] = {}
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
    year: int = Field(default=2026, ge=2005, le=2030,
                      description="Год для декадного риска")
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
        log.warning("districts.yaml unreadable, using hardcoded fallback", exc_info=True)
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
        log.warning("decade_risk failed for %s/%s: %s", district_en, year, e)
        return {"district_en": district_en, "year": year,
                "seasonal_risk": None, "seasonal_light": None,
                "decades": [], "stages": {},
                "error": f"{type(e).__name__}: {e}"}


_INTERVALS_CACHE: dict | None = None


def _interval_coverage(crop: str) -> float | None:
    """Фактическое покрытие conformal-интервала на hold-out (n=50).

    metrics/intervals.json; нет файла — None (не выдумываем).
    Номинал «80%» НИКОГДА не заявляется без этого числа.
    """
    global _INTERVALS_CACHE
    if _INTERVALS_CACHE is None:
        try:
            import json as _json

            p = ROOT / "metrics" / "intervals.json"
            _INTERVALS_CACHE = _json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except Exception as e:
            log.warning("intervals.json unreadable: %s", e)
            _INTERVALS_CACHE = {}
    try:
        return float(_INTERVALS_CACHE.get(crop, {}).get("conformal_coverage"))
    except (TypeError, ValueError):
        return None


def _calibration_notes(lang: str, coverage: float | None) -> dict[str, str]:
    """Честные строки про интервал/даунскейлинг/страховку на языке ответа."""
    cov = "—" if coverage is None else f"{coverage:.2f}"
    warn = ""
    if coverage is not None and coverage < 0.5:
        warn = {
            "ru": " Внимание: интервал занижен — ориентируйтесь на среднее.",
            "kz": " Назар аударыңыз: аралық тарылған — орташа мәнге сүйеніңіз.",
            "en": " Warning: interval is too narrow — rely on the average.",
        }.get(lang, "")
    return {
        "coverage_note": {
            "ru": f"Интервал «80%» — номинал; факт. покрытие {cov} (n=50, metrics/intervals.json).{warn}",
            "kz": f"«80%» аралық — номинал; іс жүзінде жабу {cov} (n=50).{warn}",
            "en": f"“80%” interval is nominal; actual coverage {cov} (n=50).{warn}",
        }.get(lang, ""),
        "downscaling": {
            "ru": "Район — даунскейлинг областной статистики на центроиды (config/districts.yaml), не замеры полей.",
            "kz": "Аудан — облыстық статистиканың центроидтарға даунскейлингі, егістік өлшемі емес.",
            "en": "District downscales oblast stats onto centroids (config/districts.yaml), not field measurements.",
        }.get(lang, ""),
        "insurance_note": {
            "ru": "Страховка — decision support (ориентир), не тариф.",
            "kz": "Сақтандыру — decision support (бағдар), тариф емес.",
            "en": "Insurance is decision support (estimate), not a tariff.",
        }.get(lang, ""),
    }


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
    cov = _interval_coverage(crop)
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
                 "year": year,
                 "mode": QAGRO_ENV,
                 "interval_nominal": "80%",
                 "interval_coverage": cov,
                 **_calibration_notes(lang, cov)},
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

    try:
        with open(ROOT / "config" / "districts.yaml", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        log.warning("districts.yaml unreadable: %s", e)
        raise HTTPException(status_code=500, detail=(
            "config/districts.yaml не читается.")) from e


@app.get("/fields")
def fields(district_en: str | None = None) -> dict:
    """Оцифрованные поля: data/fields/akmola_osm_fields.geojson.

    Query ?district_en=Esil — фильтр по району. Без моков: если файла нет —
    500 с честной ошибкой (сначала python src/fields_osm.py).
    Полигоны с demo:true — примерные 1×2 км (не OSM); настоящие — ODbL.
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


@app.get("/agrodata")
def agrodata(district_en: str = "Esil", crop: str = "spring_wheat",
             lang: str = "ru") -> dict:
    """NEW_DATA #2: сверка с Казгидромет AgroData (best-effort, без моков).

    drought (сырой индекс, без вердикта) + productivity (ц/га) +
    арифметика согласия с Qagro-прогнозом. При недоступности сети —
    200 с error-строками в рубриках, а не выдумка.
    """
    lang = (lang or "ru").lower()
    try:
        _validate_inputs(district_en, crop, lang)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=_err422(e)) from e
    try:
        try:
            from src.fetch_agrodata import compare_agrodata
        except ImportError:
            from fetch_agrodata import compare_agrodata  # type: ignore
        pred = _predict(district_en, crop, None)
        q = {"y_pred": pred.get("y_pred"), "lo10": pred.get("lo10"),
             "hi90": pred.get("hi90")}
        return compare_agrodata(district_en, q, lang)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=_err422(e)) from e
    except Exception as e:
        return {"district_en": district_en, "source": "agrodata.kazhydromet.kz",
                "drought": {"count": 0, "entries": [], "error": f"{type(e).__name__}: {e}"},
                "productivity": {"count": 0, "entries": [], "error": f"{type(e).__name__}: {e}"},
                "qagro": None, "agreement": f"{type(e).__name__}: {e}"}


@app.get("/alerts")
def alerts(district_en: str = "Esil",
           days: int = Query(default=7, ge=1, le=16)) -> dict:
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
def predict(
    req: PredictRequest,
    response: Response,
    fresh: bool = Query(
        default=False,
        description="true = мимо кэша (пересчёт), false = кэш predict 5 мин (для офлайн-демо)",
    ),
) -> dict:
    import time as _time

    key = _cache_key(req.district_en, req.crop, req.lang,
                     req.weather, req.year, req.include_risk)
    now = _time.time()
    if not fresh:
        hit = _PREDICT_CACHE.get(key)
        if hit and (now - hit[0]) < CACHE_TTL:
            response.headers["X-Qagro-Cache"] = "HIT"
            return hit[1]
    try:
        res = _full_result(req.district_en, req.crop, req.lang,
                           req.weather, req.year, req.include_risk)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=_err422(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    _PREDICT_CACHE[key] = (now, res)
    response.headers["X-Qagro-Cache"] = "MISS"
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
    except Exception as e:
        log.warning("/report calendar failed for %s: %s", req.crop, e)
        cal = None
    try:
        alerts_items = check_alerts(req.district_en)
        alerts_err = None
    except Exception as e:
        log.warning("/report alerts failed for %s: %s", req.district_en, e)
        alerts_items, alerts_err = None, f"{type(e).__name__}: {e}"
    try:
        try:
            from src.logistics import nearest_elevator
        except ImportError:
            from logistics import nearest_elevator  # type: ignore
        elev = nearest_elevator(req.district_en)
    except Exception as e:
        log.warning("/report elevator failed for %s: %s", req.district_en, e)
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


# ---- v4 platform: мои поля / журнал / опрыскивание / справочник / NPK / экономика ----
try:
    from src.platform_api import router as _platform_router
except ImportError:
    try:
        from platform_api import router as _platform_router  # type: ignore
    except ImportError:
        _platform_router = None
if _platform_router is not None:
    app.include_router(_platform_router)


@app.get("/guide")
def api_guide(crop: str = "spring_wheat", lang: str = "ru", q: str | None = None):
    try:
        from src.guide_data import lookup, search_guide
    except ImportError:
        from guide_data import lookup, search_guide  # type: ignore
    if lang not in ("ru", "kz", "en"):
        lang = "ru"
    if (q or "").strip():
        # Жалоба словами: релевантный совет вместо первых N справочника.
        return {"crop": crop, "lang": lang, "q": q.strip(),
                "items": search_guide(q, lang)[:3]}
    return {"crop": crop, "lang": lang, "items": lookup(crop)}


@app.get("/fertilizer")
def api_fertilizer(crop: str = "spring_wheat", yield_goal: float = 15.0,
                   soil: str = "medium", lang: str = "ru"):
    try:
        from src.fertilizer import calc_npk
    except ImportError:
        from fertilizer import calc_npk  # type: ignore
    return calc_npk(crop, float(yield_goal), soil)


@app.get("/economy")
def api_economy(yield_c_ha: float = 12.0, price_kzt_t: float = 95000.0,
                cost_kzt_ha: float = 65000.0, lang: str = "ru"):
    try:
        from src.economics import profit_ha
    except ImportError:
        from economics import profit_ha  # type: ignore
    return profit_ha(float(yield_c_ha), float(price_kzt_t), float(cost_kzt_ha))


@app.get("/soil")
def api_soil(district_en: str | None = None) -> dict:
    """C3: почва SoilGrids из data/processed/soil.csv (только чтение).

    Query ?district_en=Esil — фильтр по району. Файла нет —
    404 с честным текстом (сначала python src/soil.py).
    """
    import csv

    p = ROOT / "data" / "processed" / "soil.csv"
    if not p.exists():
        raise HTTPException(status_code=404, detail=(
            "data/processed/soil.csv не найден. "
            "Запустите: python src/soil.py"))
    with open(p, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("nitrogen", "ph", "soc", "clay"):
            if k in r and r[k] not in (None, ""):
                try:
                    r[k] = float(r[k])  # type: ignore[assignment]
                except (TypeError, ValueError):
                    pass
    if district_en:
        rows = [r for r in rows if r.get("district_en") == district_en]
    return {"rows": rows, "count": len(rows),
            "source": "data/processed/soil.csv"}


@app.get("/intervals")
def api_intervals() -> dict:
    """C3: конформные интервалы из metrics/intervals.json (только чтение)."""
    import json

    p = ROOT / "metrics" / "intervals.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail=(
            "metrics/intervals.json не найден. "
            "Запустите: python src/intervals.py"))
    data = json.loads(p.read_text(encoding="utf-8"))
    return {"crops": data, "counts": {"crops": len(data)}}


@app.get("/gis")
def api_gis(district_en: str = "Esil", max_fields: int = 6) -> dict:
    """Трек 1: NDVI-мониторинг полей (1.1), залежи (1.3), гибель (1.4).

    Читает готовые data/gis/gis_{district}.json; если нет — считает
    наживую через src.gis_monitor.run_district (до 6 полей, ~1-2 мин).
    Границы/площади (1.2) — из OSM-полигонов с area_ha.
    """
    import json

    try:
        from src.gis_monitor import run_district
    except ImportError:
        from gis_monitor import run_district  # type: ignore
    if max_fields < 1 or max_fields > 6:
        raise HTTPException(status_code=422, detail="max_fields 1..6")
    try:
        return run_district(district_en, max_fields=max_fields)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"GIS offline: {e}")


@app.get("/compare")
def api_compare(district_en: str = "Esil", crops: str = "spring_wheat,barley",
                lang: str = "ru", price_kzt_t: float | None = None) -> dict:
    """Сравнение 2–4 культур: урожай/риск-слово/выплата/вывод (для UI-таба).

    Query crops — список через запятую. Модели не меняет: только читает
    predict/insurance. Цена опциональна: для пшеницы/ячменя выплата
    пересчитывается как в Streamlit (live-слайдер).
    """
    crop_list = [c.strip() for c in (crops or "").split(",") if c.strip()]
    if len(crop_list) < 2 or len(crop_list) > 4:
        raise HTTPException(status_code=422, detail="crops: нужно 2–4 через запятую")
    lang = (lang or "ru").lower()
    items: list[dict] = []
    for c in crop_list:
        try:
            _validate_inputs(district_en, c, lang)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=_err422(e)) from e
        pred = _predict(district_en, c, None)
        try:
            ins = insurance_quote(district_en, c)
        except Exception as e:
            raise HTTPException(status_code=422, detail=_err422(e)) from e
        if price_kzt_t and c in ("spring_wheat", "barley"):
            try:
                sub = float(ins.get("subsidy_rate", 0.8))
                exp_short = float(ins.get("expected_shortfall_c_ha", 0.0))
                point_short = float(ins.get("shortfall_c_ha", 0.0))
                if not (0 < float(price_kzt_t) <= 1_000_000):
                    raise ValueError(f"price_kzt_t={price_kzt_t!r} вне (0, 1000000].")
                ins = dict(ins, price_kzt_per_t=float(price_kzt_t),
                           expected_payout_ha=round(exp_short / 10.0 * float(price_kzt_t) * sub, 0),
                           payout_at_pred_ha=round(point_short / 10.0 * float(price_kzt_t) * sub, 0))
            except (TypeError, ValueError) as e:
                log.warning("/compare price recalc failed for %s: %s", c, e)
        p_loss = float(ins["p_loss"])
        risk_word = ("high" if p_loss > 0.4 else ("medium" if p_loss > 0.2 else "low"))
        items.append({"crop": c, "y_pred": round(float(pred["y_pred"]), 1),
                      "p_loss": p_loss, "risk_word": risk_word,
                      "payout_ha": int(round(float(ins.get("expected_payout_ha") or 0))),
                      "mean5_c_ha": ins.get("mean5_c_ha")})
    best = max(items, key=lambda r: r["y_pred"])["crop"]
    calm = min(items, key=lambda r: r["p_loss"])["crop"]
    return {"district_en": district_en, "lang": lang, "items": items,
            "best_yield": best, "calmest": calm, "count": len(items)}


@app.get("/season")
def api_season(district_en: str = "Esil", crop: str = "spring_wheat",
               lang: str = "ru") -> dict:
    """Сезонный календарь: GDD-факт vs норма + spray-окна 48 ч (best-effort).

    GDD-факт — средний GDD района из панели (gdd_context recommend_sowing),
    норма — sowing_calendar. Spray офлайн -> {"error": ...}, а не выдумка.
    """
    lang = (lang or "ru").lower()
    try:
        _validate_inputs(district_en, crop, lang)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=_err422(e)) from e
    cal = sowing_calendar(crop, lang)
    try:
        rec = recommend_sowing(district_en, crop, lang)
        fact = float((rec.get("gdd_context") or {}).get("district_gdd5_mean") or 0.0)
        gdd_warn = None
    except Exception as e:
        log.warning("/season gdd failed for %s/%s: %s", district_en, crop, e)
        fact, rec, gdd_warn = None, None, f"{type(e).__name__}: {e}"
    norm = cal.get("gdd_norm") or [0, 1]
    hi = float(norm[1]) if len(norm) > 1 else float(norm[0])
    progress = None if fact is None else min(max(fact / hi if hi > 0 else 0.0, 0.0), 1.0)
    try:
        try:
            from src.spray import check_spray_window
        except ImportError:
            from spray import check_spray_window  # type: ignore
        spray = check_spray_window(district_en, 48)
    except Exception as e:
        spray = {"district_en": district_en, "windows": [],
                 "next_good_hours": [], "good_count": 0,
                 "error": f"{type(e).__name__}: {e}"}
    return {"district_en": district_en, "crop": crop, "lang": lang,
            "calendar": cal, "gdd_fact": None if fact is None else round(fact, 1),
            "gdd_progress": progress if progress is None else round(progress, 3),
            "gdd_warning": gdd_warn, "spray": spray,
            "sowing_window": (rec or {}).get("window")}
