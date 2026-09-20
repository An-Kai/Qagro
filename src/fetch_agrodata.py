"""fetch_agrodata.py — сверка с Казгидромет AgroData (NEW_DATA #2).

Источники (проверены 20.09.2026, все GET без ключа):
  /api/calendar/towns        — 400 городов (200)
/appi/weather/actual/towns   — 197 метеостанций (200)
/api/forecasts/drought       — 288 точек засухи: {town{...}, value} (200)
/api/forecasts/moisture      — 120 точек влажности почв (200)
/api/forecasts/productivity  — 118 полигонов урожайности: {nameRu, valueFrom, valueTo} (200)

Покрытие наших 10 районов (nameRu из config/districts.yaml):
  drought      — 8/10 (нет Целиноградского и Кокшетау)
  productivity — 9/10 (нет Кокшетау; Есильский — 2 зоны)

Честность:
  - drought.value — сырой индекс Казгидромета, шкалу не интерпретируем
    (отрицательные значения показываем как есть, без вердикта "сухо").
  - productivity valueFrom/valueTo — диапазоны ц/га; сверка с y_pred —
    чистая арифметика (внутри/ниже/выше), без подгонки модели.
  - Сеть недоступна -> RuntimeError (громко, без моков). Частичные данные
    сохраняются: каждая рубрика ловит свою ошибку отдельно.
  - Модуль НЕ трогает train/evaluate: только чтение + сравнение.

Использование:
  python -m src.fetch_agrodata Esil
  -> JSON: drought + productivity + сверка с Qagro-прогнозом пшеницы.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"

BASE = "https://agrodata.kazhydromet.kz"
TIMEOUT = 25


def _get_json(path: str):
    """GET JSON с AgroData. Ошибка сети/HTTP/JSON -> RuntimeError (громко)."""
    url = f"{BASE}{path}"
    try:
        r = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(f"AgroData недоступен: {e}.") from e
    if r.status_code != 200:
        raise RuntimeError(
            f"AgroData {path}: HTTP {r.status_code}: {r.text[:200]}.")
    try:
        payload = r.json()
    except ValueError as e:
        raise RuntimeError(f"AgroData {path} вернул не-JSON.") from e
    if isinstance(payload, dict) and payload.get("success") is False:
        raise RuntimeError(f"AgroData {path}: success=false.")
    if isinstance(payload, dict) and "result" in payload:
        return payload["result"]
    return payload


def _districts() -> list[dict]:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("districts", [])


def _district_ru(district_en: str) -> str:
    for d in _districts():
        if d.get("name_en") == district_en:
            return str(d.get("name_ru"))
    known = sorted(d.get("name_en") for d in _districts() if d.get("name_en"))
    raise ValueError(
        f"district_en={district_en!r} неизвестен. Допустимо: {known}.")


def _is_akmola(entity: dict) -> bool:
    town = entity.get("town") or {}
    dist = town.get("district") or {}
    region = dist.get("region") or {}
    return "Акмолин" in str(region.get("nameRu", ""))


def drought_by_district(district_en: str) -> list[dict]:
    """Точки drought-прогноза Казгидромета для района (пусто = нет покрытия)."""
    want = _district_ru(district_en)
    out = []
    for e in _get_json("/api/forecasts/drought") or []:
        if not isinstance(e, dict):
            continue
        town = e.get("town") or {}
        dist = town.get("district") or {}
        if not _is_akmola(e):
            continue
        if str(dist.get("nameRu", "")) != want:
            continue
        out.append({
            "town_ru": town.get("nameRu"),
            "town_kz": town.get("nameKk"),
            "value": e.get("value"),
            "modified": e.get("modified"),
        })
    return out


def productivity_by_district(district_en: str) -> list[dict]:
    """Полигоны productivity-прогноза Казгидромета для района (ц/га)."""
    want = _district_ru(district_en)
    out = []
    for e in _get_json("/api/forecasts/productivity") or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("nameRu", "")) != want:
            continue
        try:
            vf = None if e.get("valueFrom") is None else float(e["valueFrom"])
            vt = None if e.get("valueTo") is None else float(e["valueTo"])
        except (TypeError, ValueError):
            vf, vt = None, None
        out.append({"valueFrom": vf, "valueTo": vt,
                    "color": e.get("color"), "nameKk": e.get("nameKk")})
    return out


def _agreement(qagro: dict | None, prod: list[dict], lang: str = "ru") -> str:
    """Сверка y_pred с диапазоном Казгидромета — только арифметика."""
    if not qagro or not prod:
        return {"ru": "Сравнить не с чем: нет Qagro-прогноза или покрытия Казгидромета.",
                "kz": "Салыстыратын ештеңе жоқ: Qagro болжамы немесе Қазгидромет қамтуы жоқ.",
                "en": "Nothing to compare: no Qagro forecast or Kazhydromet coverage."}[lang]
    try:
        y = float(qagro["y_pred"])
    except (TypeError, ValueError, KeyError):
        return {"ru": "Qagro-прогноз без числа — сравнение невозможно.",
                "kz": "Qagro болжамында сан жоқ — салыстыру мүмкін емес.",
                "en": "Qagro forecast has no number — cannot compare."}[lang]
    lo = min(p["valueFrom"] for p in prod if p.get("valueFrom") is not None)
    hi = max(p["valueTo"] for p in prod if p.get("valueTo") is not None)
    pos = {"ru": ("внутри диапазона", "ниже диапазона", "выше диапазона"),
           "kz": ("ауқым ішінде", "ауқымнан төмен", "ауқымнан жоғары"),
           "en": ("inside the range", "below the range", "above the range")}[lang]
    where = pos[0] if lo <= y <= hi else (pos[1] if y < lo else pos[2])
    return {"ru": f"Qagro {y} ц/га — {where} Казгидромета ({lo}–{hi}). Шкалы независимы.",
            "kz": f"Qagro {y} ц/га — Қазгидромет ауқымы ({lo}–{hi}) {where}. Шкалалар тәуелсіз.",
            "en": f"Qagro {y} c/ha — {where} Kazhydromet ({lo}–{hi}). Scales are independent."}[lang]


def compare_agrodata(district_en: str, qagro: dict | None = None,
                     lang: str = "ru") -> dict:
    """Сверка района с AgroData: drought + productivity + арифметика согласия.

    Неизвестный район -> ValueError. Сеть упала -> error-строки в рубриках,
    исключение наружу НЕ летит (частичные данные лучше пустоты).
    """
    _district_ru(district_en)  # громкая проверка района
    if lang not in ("ru", "kz", "en"):
        lang = "ru"
    drought, prod = [], []
    d_err = p_err = None
    try:
        drought = drought_by_district(district_en)
    except Exception as e:
        d_err = f"{type(e).__name__}: {e}"
    try:
        prod = productivity_by_district(district_en)
    except Exception as e:
        p_err = f"{type(e).__name__}: {e}"
    return {
        "district_en": district_en,
        "source": "agrodata.kazhydromet.kz",
        "drought": {"count": len(drought), "entries": drought, "error": d_err,
                    "note": "value — сырой индекс Казгидромета, вердикт не ставим"},
        "productivity": {"count": len(prod), "entries": prod, "error": p_err,
                         "unit": "ц/га (valueFrom–valueTo)"},
        "qagro": qagro,
        "agreement": _agreement(qagro, prod, lang),
    }


if __name__ == "__main__":
    _d = sys.argv[1] if len(sys.argv) > 1 else "Esil"
    try:
        try:
            from src.predict import predict_yield as _py
        except ImportError:
            from predict import predict_yield as _py  # type: ignore
        _q = _py(_d, "spring_wheat", None)
        _q = {"y_pred": _q.get("y_pred"), "lo10": _q.get("lo10"),
              "hi90": _q.get("hi90")}
    except Exception as e:
        _q = None
        print(f"Qagro-прогноз недоступен: {e}", file=sys.stderr)
    print(json.dumps(compare_agrodata(_d, _q), ensure_ascii=False, indent=2))
