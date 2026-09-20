"""spray.py — окно опрыскивания по живому прогнозу Open-Meteo (Qagro v4).

check_spray_window(district_en, hours=48) -> dict:
    живой Open-Meteo forecast API, hourly:
        temperature_2m, precipitation, wind_speed_10m, relative_humidity_2m
    координаты района — из config/districts.yaml.

Правило хорошего часа:
    wind < 5 м/с И precip == 0 И 10 <= temp <= 25.

Возвращает:
    {district_en, lat, lon, hours, hours_checked,
     next_good_hours: [{time, temp_c, wind_ms, precip_mm, rh_pct}],
     good_count, verdict_ru, verdict_kz, verdict_en}

Офлайн / HTTP != 200 / пустой ряд -> RuntimeError (без моков).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import ceil
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 20

WIND_MAX = 5.0      # м/с, строго меньше
TEMP_MIN, TEMP_MAX = 10.0, 25.0


def _load_district(district_en: str) -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for d in cfg.get("districts", []):
        if d.get("name_en") == district_en:
            return d
    known = sorted(x.get("name_en") for x in cfg.get("districts", []))
    raise ValueError(f"district_en={district_en!r} неизвестен. Допустимо: {known}.")


def _fetch_hourly(lat: float, lon: float, hours: int) -> dict:
    days = max(1, min(16, ceil(int(hours) / 24) + 1))
    url = (
        f"{FORECAST_URL}?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,precipitation,wind_speed_10m,relative_humidity_2m"
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
    hourly = payload.get("hourly") or {}
    if not hourly.get("time"):
        raise RuntimeError("Open-Meteo forecast вернул пустой hourly-ряд.")
    return payload


def _is_good(temp: float, precip: float, wind: float) -> bool:
    return (
        wind < WIND_MAX
        and abs(precip) < 1e-9
        and TEMP_MIN <= temp <= TEMP_MAX
    )


def _windows(times: list[str]) -> list[tuple[str, str]]:
    """Сгруппировать соседние часы в окна [(start, end)]."""
    if not times:
        return []
    fmt = "%Y-%m-%dT%H:%M"
    dts = [datetime.strptime(t, fmt) for t in times]
    out: list[tuple[str, str]] = []
    start = prev = dts[0]
    for cur in dts[1:]:
        if cur - prev == timedelta(hours=1):
            prev = cur
        else:
            out.append((start.strftime(fmt), prev.strftime(fmt)))
            start = prev = cur
    out.append((start.strftime(fmt), prev.strftime(fmt)))
    return out


def _fmt_window(start: str, end: str, lang: str = "ru") -> str:
    s = datetime.strptime(start, "%Y-%m-%dT%H:%M")
    e = datetime.strptime(end, "%Y-%m-%dT%H:%M")
    if s == e:  # окно в один час: "с X до X" — бессмыслица, показываем факт
        one = {"ru": "час", "kz": "сағат", "en": "hour"}.get(lang, "час")
        at = {"ru": "в", "kz": "сағ.", "en": "at"}.get(lang, "в")
        return f"{s.strftime('%d.%m')} {at} {s.strftime('%H:%M')} (1 {one})"
    if s.date() == e.date():
        return f"{s.strftime('%d.%m')} с {s.strftime('%H:%M')} до {e.strftime('%H:%M')}"
    return f"с {s.strftime('%d.%m %H:%M')} до {e.strftime('%d.%m %H:%M')}"


def check_spray_window(district_en: str, hours: int = 48) -> dict:
    """Ближайшие `hours` часов: хорошие часы для опрыскивания + вердикт."""
    hours = int(hours)
    if not (1 <= hours <= 384):
        raise ValueError(f"hours={hours} вне диапазона 1..384.")
    meta = _load_district(district_en)
    lat, lon = float(meta["lat"]), float(meta["lon"])
    payload = _fetch_hourly(lat, lon, hours)
    hourly = payload["hourly"]
    offset = int(payload.get("utc_offset_seconds", 6 * 3600))

    now_utc = datetime.now(timezone.utc)
    now_local = (now_utc + timedelta(seconds=offset)).replace(
        minute=0, second=0, microsecond=0, tzinfo=None
    )

    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    precs = hourly.get("precipitation", [])
    winds = hourly.get("wind_speed_10m", [])
    rhs = hourly.get("relative_humidity_2m", [None] * len(times))
    n = min(len(times), len(temps), len(precs), len(winds))
    if n == 0:
        raise RuntimeError("Open-Meteo forecast вернул пустой hourly-ряд.")

    # Ближайшие `hours` часов начиная с текущего часа (Asia/Almaty).
    future: list[dict] = []
    for i in range(n):
        try:
            t = datetime.strptime(times[i], "%Y-%m-%dT%H:%M")
            temp = float(temps[i])
            pr = float(precs[i])
            wn = float(winds[i])
            rh = hourly_rh(rhs[i])
        except (TypeError, ValueError, IndexError):
            continue
        if t < now_local:
            continue
        future.append({"time": times[i], "temp": temp, "pr": pr,
                       "wn": wn, "rh": rh})
        if len(future) >= hours:
            break
    if not future:
        raise RuntimeError("Open-Meteo forecast: нет будущих часов в ответе.")

    good: list[dict] = []
    n_wind = n_rain = n_temp = 0
    for h in future:
        ok = _is_good(h["temp"], h["pr"], h["wn"])
        if h["wn"] >= WIND_MAX:
            n_wind += 1
        if abs(h["pr"]) >= 1e-9:
            n_rain += 1
        if not (TEMP_MIN <= h["temp"] <= TEMP_MAX):
            n_temp += 1
        if ok:
            good.append({
                "time": h["time"],
                "temp_c": round(h["temp"], 1),
                "wind_ms": round(h["wn"], 1),
                "precip_mm": round(h["pr"], 1),
                "rh_pct": None if h["rh"] is None else round(h["rh"], 0),
            })

    checked = len(future)
    good_times = [g["time"] for g in good]
    wins = _windows(good_times)

    if good:
        w0_ru = _fmt_window(*wins[0], lang="ru")
        w0_kz = _fmt_window(*wins[0], lang="kz")
        w0_en = _fmt_window(*wins[0], lang="en")
        verdict_ru = (
            f"{w0_ru} — хорошо "
            f"(ветер <5 м/с, без дождя, 10–25°C). "
            f"Всего хороших часов: {len(good)} из {checked}."
        )
        verdict_kz = (
            f"{w0_kz} — жақсы "
            f"(жел <5 м/с, жауынсыз, 10–25°C). "
            f"Жақсы сағаттар: {checked} ішінен {len(good)}."
        )
        verdict_en = (
            f"{w0_en} — good "
            f"(wind <5 m/s, no rain, 10–25°C). "
            f"Good hours: {len(good)} of {checked}."
        )
    else:
        causes_ru, causes_kz, causes_en = [], [], []
        if n_wind:
            causes_ru.append(f"ветер ≥5 м/с ({n_wind} ч)")
            causes_kz.append(f"жел ≥5 м/с ({n_wind} сағ)")
            causes_en.append(f"wind ≥5 m/s ({n_wind}h)")
        if n_rain:
            causes_ru.append(f"дождь ({n_rain} ч)")
            causes_kz.append(f"жауын ({n_rain} сағ)")
            causes_en.append(f"rain ({n_rain}h)")
        if n_temp:
            causes_ru.append(f"температура вне 10–25°C ({n_temp} ч)")
            causes_kz.append(f"температура 10–25°C сыртында ({n_temp} сағ)")
            causes_en.append(f"temp outside 10–25°C ({n_temp}h)")
        reason_ru = ", ".join(causes_ru) or "нет данных"
        reason_kz = ", ".join(causes_kz) or "дерек жоқ"
        reason_en = ", ".join(causes_en) or "no data"
        verdict_ru = (
            f"Ближайшие {checked}ч плохие: {reason_ru}. "
            f"Хороших часов: 0 — опрыскивание отложить."
        )
        verdict_kz = (
            f"Алдағы {checked} сағат қолайсыз: {reason_kz}. "
            f"Жақсы сағаттар: 0 — бүркуді кейінге қалдырыңыз."
        )
        verdict_en = (
            f"Next {checked}h are bad: {reason_en}. "
            f"Good hours: 0 — postpone spraying."
        )

    return {
        "district_en": district_en,
        "lat": lat,
        "lon": lon,
        "hours": hours,
        "hours_checked": checked,
        "next_good_hours": good,
        "good_count": len(good),
        "windows": [{"start": s, "end": e} for s, e in wins],
        "verdict_ru": verdict_ru,
        "verdict_kz": verdict_kz,
        "verdict_en": verdict_en,
    }


def hourly_rh(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    import json
    import sys

    _d = sys.argv[1] if len(sys.argv) > 1 else "Esil"
    print(json.dumps(check_spray_window(_d), ensure_ascii=False, indent=2))
