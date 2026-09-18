"""alerts.py — агроалерты по прогнозу Open-Meteo (C8).

Источники: живой Open-Meteo forecast (16 дней максимум, берём 7):
  https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..
  &daily=temperature_2m_max,temperature_2m_min,precipitation_sum,
         wind_speed_10m_max,relative_humidity_2m_mean
  &timezone=Asia/Almaty&forecast_days=7

Правила (только факты, без спама — максимум 1 алерт типа на день):
  * frost      — tmin < 0 °C                    (level high)
  * heat       — tmax > 35 °C                   (level high)
  * heavy_rain — precip > 20 мм/сутки           (level medium)
  * dry_wind   — wind > 12 м/с И rh_mean < 30%  (level medium, суховей)

check_alerts(district_en, days=7) -> list[{type, level, date, value,
msg_ru, msg_kz, msg_en}]. Без моков: недоступность API -> RuntimeError.

Без БД/Celery/подписок: только синхронная проверка по запросу.
"""
from __future__ import annotations

from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 20

FROST_TMIN = 0.0
HEAT_TMAX = 35.0
RAIN_MM = 20.0
WIND_MS = 12.0
RH_PCT = 30.0


def _load_district(district_en: str) -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for d in cfg.get("districts", []):
        if d.get("name_en") == district_en:
            return d
    known = sorted(x.get("name_en") for x in cfg.get("districts", []))
    raise ValueError(f"district_en={district_en!r} неизвестен. Допустимо: {known}.")


def _fetch_forecast(lat: float, lon: float, days: int = 7) -> dict:
    days = max(1, min(int(days), 16))
    url = (
        f"{FORECAST_URL}?latitude={lat}&longitude={lon}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
        "wind_speed_10m_max,relative_humidity_2m_mean"
        f"&timezone=Asia%2FAlmaty&forecast_days={days}"
    )
    try:
        r = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(f"Open-Meteo forecast недоступен: {e}.") from e
    if r.status_code != 200:
        raise RuntimeError(
            f"Open-Meteo forecast недоступен: HTTP {r.status_code}: {r.text[:300]}."
        )
    try:
        payload = r.json()
    except ValueError as e:
        raise RuntimeError("Open-Meteo forecast вернул не-JSON.") from e
    if payload.get("error"):
        raise RuntimeError(f"Open-Meteo forecast error: {payload.get('reason')}.")
    daily = payload.get("daily") or {}
    if not daily.get("time"):
        raise RuntimeError("Open-Meteo forecast вернул пустой ряд.")
    return daily


def _msgs(alert_type: str, date_s: str, value_s: str) -> tuple[str, str, str]:
    if alert_type == "frost":
        return (
            f"❄️ Заморозок {date_s}: tmin {value_s} °C. Укройте всходы, отложите обработки.",
            f"❄️ Үсік {date_s}: tmin {value_s} °C. Өскіндерді қорғаңыз, өңдеуді кейінге қалдырыңыз.",
            f"❄️ Frost {date_s}: tmin {value_s} °C. Protect seedlings, postpone spraying.",
        )
    if alert_type == "heat":
        return (
            f"🔥 Жара {date_s}: tmax {value_s} °C. Сдвиньте работы на утро/вечер, следите за влагой.",
            f"🔥 Ыстық {date_s}: tmax {value_s} °C. Жұмысты таңға/кешке жылжытыңыз, ылғалды бақылаңыз.",
            f"🔥 Heat {date_s}: tmax {value_s} °C. Shift fieldwork to morning/evening.",
        )
    if alert_type == "heavy_rain":
        return (
            f"🌧 Ливень {date_s}: осадки {value_s} мм/сут. Отложите опрыскивание и выезд техники.",
            f"🌧 Нөсер {date_s}: жауын {value_s} мм/тәул. Бүркуді және техника шығаруды кейінге қалдырыңыз.",
            f"🌧 Downpour {date_s}: {value_s} mm/day. Postpone spraying and field traffic.",
        )
    # dry_wind
    return (
        f"💨 Суховей {date_s}: ветер {value_s}. Закройте влагу, отложите опрыскивание.",
        f"💨 Қуаң жел {date_s}: жел {value_s}. Ылғал жабыңыз, бүркуді кейінге қалдырыңыз.",
        f"💨 Dry wind {date_s}: wind {value_s}. Seal moisture, postpone spraying.",
    )


def check_alerts(district_en: str, days: int = 7) -> list[dict]:
    """Проверить прогноз на days дней. Только факты, без спама."""
    meta = _load_district(district_en)
    daily = _fetch_forecast(float(meta["lat"]), float(meta["lon"]), days)
    times = daily.get("time", [])
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    wind = daily.get("wind_speed_10m_max", [])
    rh = daily.get("relative_humidity_2m_mean", [None] * len(times))

    alerts: list[dict] = []
    for i, day in enumerate(times):
        try:
            tx = float(tmax[i]) if tmax[i] is not None else None
            tn = float(tmin[i]) if tmin[i] is not None else None
            pr = float(precip[i]) if precip[i] is not None else None
            wn = float(wind[i]) if wind and wind[i] is not None else None
            hu = float(rh[i]) if rh and rh[i] is not None else None
        except (TypeError, ValueError, IndexError):
            continue
        if tn is not None and tn < FROST_TMIN:
            ru, kz, en = _msgs("frost", day, f"{tn:.1f}")
            alerts.append({"type": "frost", "level": "high", "date": day,
                           "value": round(tn, 1), "unit": "°C",
                           "msg_ru": ru, "msg_kz": kz, "msg_en": en})
        if tx is not None and tx > HEAT_TMAX:
            ru, kz, en = _msgs("heat", day, f"{tx:.1f}")
            alerts.append({"type": "heat", "level": "high", "date": day,
                           "value": round(tx, 1), "unit": "°C",
                           "msg_ru": ru, "msg_kz": kz, "msg_en": en})
        if pr is not None and pr > RAIN_MM:
            ru, kz, en = _msgs("heavy_rain", day, f"{pr:.1f}")
            alerts.append({"type": "heavy_rain", "level": "medium", "date": day,
                           "value": round(pr, 1), "unit": "mm",
                           "msg_ru": ru, "msg_kz": kz, "msg_en": en})
        if wn is not None and wn > WIND_MS and hu is not None and hu < RH_PCT:
            ru, kz, en = _msgs("dry_wind", day, f"{wn:.1f} м/с, RH {hu:.0f}%")
            alerts.append({"type": "dry_wind", "level": "medium", "date": day,
                           "value": {"wind_ms": round(wn, 1), "rh_pct": round(hu, 1)},
                           "unit": "m/s+%RH",
                           "msg_ru": ru, "msg_kz": kz, "msg_en": en})
    return alerts


if __name__ == "__main__":
    import json
    import sys

    _d = sys.argv[1] if len(sys.argv) > 1 else "Esil"
    print(json.dumps(check_alerts(_d), ensure_ascii=False, indent=2))
