"""risk.py — декадный индекс засушливо-теплового риска (Open-Meteo, без моков).

Источники (оба — Open-Meteo, живые запросы):
  * archive-api.open-meteo.com — факт сезона `year` (05-01..09-30) + климатология
    осадков 2005-2020 для тех же декад того же района;
  * api.open-meteo.com (forecast, 16 дней) — добивка будущих дат сезона
    (напр. конец сентября), + hourly soil_moisture_3_9cm как soil_proxy.

Декады: 3 на месяц (01-10, 11-20, 21-конец), май-сентябрь = 15 декад.
ТЗ просит декады "май-август", но веса стадий включают сентябрь
(май 0.2, июнь-август 0.5, сентябрь 0.3, сумма 1.0) — поэтому сентябрь
тоже тянем из API и показываем; иначе вес 0.3 повис бы в воздухе.

Метрики декады:
  precip_anom_pct — 100*(P - Pclim)/Pclim, Pclim = среднее сумм тех же
                   дат за 2005-2020 (тот же район);
  dry_streak     — макс. подряд дней с осадками < 1.0 мм внутри декады;
  heat_days      — дни с tmax > 30.0 °C внутри декады;
  soil_proxy     — среднее soil_moisture_3_9cm (м3/м3) за декаду
                   (archive-hourly для прошлого + forecast-hourly для будущего;
                   если данных нет — None, без выдумок).

Индекс 0-100 (строго по ТЗ):
  precip_deficit = clip(-precip_anom_pct, 0, 100)   # surplus -> 0
  heat_score     = heat_days / n_days * 100
  dry_score      = dry_streak / n_days * 100
  risk = 0.4*precip_deficit + 0.35*heat_score + 0.25*dry_score

Светофор: 🟢 < 35, 🟡 35-60, 🔴 > 60.
Сезонный риск = 0.2*mean(май) + 0.5*mean(июнь-август) + 0.3*mean(сентябрь).

Без моков: любая недоступность API (HTTP != 200, timeout, пустые ряды) —
RuntimeError с понятным текстом, а не синтетика.
"""
from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 60
CLIM_START, CLIM_END = 2005, 2020
MONTHS = (5, 6, 7, 8, 9)
STAGE_WEIGHTS = {"may": 0.2, "jun_aug": 0.5, "sep": 0.3}
MONTH_RU = {5: "май", 6: "июнь", 7: "июль", 8: "август", 9: "сентябрь"}


# ---------------------------------------------------------------- helpers
def _load_district(district_en: str) -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for d in cfg.get("districts", []):
        if d.get("name_en") == district_en:
            return d
    known = sorted(x.get("name_en") for x in cfg.get("districts", []))
    raise ValueError(f"district_en={district_en!r} неизвестен. Допустимо: {known}.")


def _get_json(url: str, label: str) -> dict:
    try:
        r = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(
            f"Open-Meteo недоступен ({label}): {e}. "
            "Проверьте интернет/DNS. Данные не выдуманы — исключение вместо мока."
        ) from e
    if r.status_code != 200:
        raise RuntimeError(
            f"Open-Meteo недоступен ({label}): HTTP {r.status_code}: {r.text[:400]}. "
            "Повторите позже. Данные не выдуманы — исключение вместо мока."
        )
    try:
        payload = r.json()
    except ValueError as e:
        raise RuntimeError(
            f"Open-Meteo вернул не-JSON ({label}). Повторите позже."
        ) from e
    if payload.get("error"):
        raise RuntimeError(
            f"Open-Meteo вернул ошибку ({label}): {payload.get('reason')}. "
            "Повторите позже."
        )
    return payload


def _archive_daily(lat: float, lon: float, start: str, end: str) -> pd.DataFrame:
    url = (
        f"{ARCHIVE_URL}?latitude={lat}&longitude={lon}"
        f"&start_date={start}&end_date={end}"
        "&daily=temperature_2m_max,precipitation_sum"
        "&timezone=Asia%2FAlmaty"
    )
    p = _get_json(url, f"archive {start}..{end}")
    d = p.get("daily", {})
    times = pd.to_datetime(d.get("time", []))
    if len(times) == 0:
        raise RuntimeError(
            f"Open-Meteo archive вернул пустой ряд за {start}..{end}. "
            "Повторите позже (мок не подставляем)."
        )
    df = pd.DataFrame({
        "date": times,
        "tmax": pd.to_numeric(d.get("temperature_2m_max", []), errors="coerce"),
        "precip": pd.to_numeric(d.get("precipitation_sum", []), errors="coerce"),
    })
    if df[["tmax", "precip"]].isna().any().any():
        raise RuntimeError(
            f"Open-Meteo archive: NaN в tmax/precip за {start}..{end} "
            f"(n={int(df[['tmax','precip']].isna().sum().sum())}). Мок не подставляем."
        )
    df["src"] = "archive"
    return df


def _forecast_daily(lat: float, lon: float) -> pd.DataFrame:
    url = (
        f"{FORECAST_URL}?latitude={lat}&longitude={lon}"
        "&daily=temperature_2m_max,precipitation_sum"
        "&timezone=Asia%2FAlmaty&forecast_days=16"
    )
    p = _get_json(url, "forecast 16d")
    d = p.get("daily", {})
    times = pd.to_datetime(d.get("time", []))
    if len(times) == 0:
        raise RuntimeError("Open-Meteo forecast вернул пустой ряд. Повторите позже.")
    df = pd.DataFrame({
        "date": times,
        "tmax": pd.to_numeric(d.get("temperature_2m_max", []), errors="coerce"),
        "precip": pd.to_numeric(d.get("precipitation_sum", []), errors="coerce"),
    })
    df["src"] = "forecast"
    return df


def _soil_for_season(lat: float, lon: float, year: int) -> pd.Series:
    """Среднедневная soil_moisture_3_9cm на сезон year-05-01..year-09-30.

    Склейка: archive-hourly (прошлое) + forecast-hourly (будущие 16 дней).
    Возвращает Series date->sm. Пустая Series = данных нет (не мок).
    """
    out: dict = {}
    arch_soil_end = min(f"{year}-09-30", date.today().isoformat())
    # 1) archive hourly (прошлое; может отсутствовать для будущих дат — ок)
    try:
        url = (
            f"{ARCHIVE_URL}?latitude={lat}&longitude={lon}"
            f"&start_date={year}-05-01&end_date={arch_soil_end}"
            "&hourly=soil_moisture_3_9cm&timezone=Asia%2FAlmaty"
        )
        p = _get_json(url, f"archive-soil {year}")
        h = p.get("hourly", {})
        ht = pd.to_datetime(h.get("time", []))
        hv = pd.to_numeric(h.get("soil_moisture_3_9cm", []), errors="coerce")
        if len(ht):
            s = (pd.DataFrame({"dt": ht, "sm": hv})
                   .assign(date=lambda x: x["dt"].dt.normalize())
                   .groupby("date")["sm"].mean())
            for k, v in s.items():
                if pd.notna(v):
                    out[pd.Timestamp(k)] = float(v)
    except RuntimeError:
        pass  # soil из архива необязателен; ниже — forecast; если оба пустые -> None
    # 2) forecast hourly (будущее)
    try:
        url = (
            f"{FORECAST_URL}?latitude={lat}&longitude={lon}"
            "&hourly=soil_moisture_3_9cm&timezone=Asia%2FAlmaty&forecast_days=16"
        )
        p = _get_json(url, "forecast-soil 16d")
        h = p.get("hourly", {})
        ht = pd.to_datetime(h.get("time", []))
        hv = pd.to_numeric(h.get("soil_moisture_3_9cm", []), errors="coerce")
        if len(ht):
            s = (pd.DataFrame({"dt": ht, "sm": hv})
                   .assign(date=lambda x: x["dt"].dt.normalize())
                   .groupby("date")["sm"].mean())
            for k, v in s.items():
                if pd.notna(v):
                    out.setdefault(pd.Timestamp(k), float(v))
    except RuntimeError:
        pass
    if not out:
        return pd.Series(dtype=float)
    return pd.Series(out).sort_index()


def _decade_bounds(year: int, month: int, part: int) -> tuple[str, str]:
    last = calendar.monthrange(year, month)[1]
    if part == 1:
        return f"{year}-{month:02d}-01", f"{year}-{month:02d}-10"
    if part == 2:
        return f"{year}-{month:02d}-11", f"{year}-{month:02d}-20"
    return f"{year}-{month:02d}-21", f"{year}-{month:02d}-{last}"


def _light(v: float) -> str:
    if v < 35:
        return "🟢"
    if v <= 60:
        return "🟡"
    return "🔴"


# ---------------------------------------------------------------- main
def decade_risk(district_en: str, year: int = 2026) -> dict:
    """Декадный риск засухи/жары для района и года. См. docstring модуля."""
    meta = _load_district(district_en)
    lat, lon = float(meta["lat"]), float(meta["lon"])
    year = int(year)

    # 1) климатология осадков по декадам 2005-2020 (один запрос)
    clim = _archive_daily(lat, lon, f"{CLIM_START}-05-01", f"{CLIM_END}-09-30")
    clim["ymd"] = clim["date"].dt.strftime("%m-%d")

    # 2) факт сезона year (archive; для текущего года — по сегодня,
    #    остаток сентября добиваем forecast; archive не отдаёт будущие даты).
    season_end = date(year, 9, 30)
    today = date.today()
    if season_end <= today:
        arch_end = season_end.isoformat()
    elif date(year, 5, 1) > today:
        raise RuntimeError(
            f"Сезон {year} целиком в будущем для {district_en}: archive его не покрывает, "
            "а forecast даёт только 16 дней. Полный декадный риск посчитать нельзя. "
            "Мок не подставляем — укажите прошедший/текущий год."
        )
    else:
        arch_end = today.isoformat()
    season = _archive_daily(lat, lon, f"{year}-05-01", arch_end)

    # 3) прогноз на будущее (добивка сентября и хвостов) — если API молчит
    #    для прошлых сезонов, forecast просто не перекроет archive.
    try:
        fc = _forecast_daily(lat, lon)
    except RuntimeError as e:
        # forecast критичен только если archive не покрыл весь сезон;
        # проверяем покрытие ниже и кидаем понятную ошибку там.
        fc = pd.DataFrame(columns=["date", "tmax", "precip", "src"])
        _fc_err = str(e)
    else:
        _fc_err = ""

    # склейка дневных рядов: archive в приоритете, forecast добивает
    base = pd.concat([season, fc], ignore_index=True)
    base["day"] = base["date"].dt.normalize()
    base = base.sort_values(["day", "src"]).drop_duplicates("day", keep="first")
    base = base.set_index("day").sort_index()

    # покрытие сезона
    need = pd.date_range(f"{year}-05-01", f"{year}-09-30", freq="D")
    missing = [d for d in need if d not in base.index]
    if missing:
        raise RuntimeError(
            f"Open-Meteo не покрыл сезон {year} для {district_en}: "
            f"нет {len(missing)} дней (напр. {missing[0].date()}..{missing[-1].date()}). "
            f"Archive + forecast недоступны полностью. {_fc_err} "
            "Мок не подставляем — повторите позже."
        )

    soil = _soil_for_season(lat, lon, year)

    decades: list[dict] = []
    for m in MONTHS:
        for part in (1, 2, 3):
            s, e = _decade_bounds(year, m, part)
            days = pd.date_range(s, e, freq="D")
            g = base.loc[days]
            n = len(g)
            p_sum = round(float(g["precip"].sum()), 1)
            heat = int((g["tmax"] > 30.0).sum())
            dry_flags = (g["precip"].values < 1.0)
            best = cur = 0
            for v in dry_flags:
                cur = cur + 1 if v else 0
                best = max(best, cur)
            # климатология: те же месяц-числа за 2005-2020
            mds = [d.strftime("%m-%d") for d in days]
            sums = []
            for y in range(CLIM_START, CLIM_END + 1):
                sub = clim[(clim["date"].dt.year == y) & (clim["ymd"].isin(mds))]
                if len(sub) == len(days):
                    sums.append(float(sub["precip"].sum()))
            if not sums:
                raise RuntimeError(
                    f"Нет климатологии 2005-2020 для декады {s}..{e} ({district_en})."
                )
            p_clim = sum(sums) / len(sums)
            if p_clim <= 0.5:
                raise RuntimeError(
                    f"Климатология осадков ~0 для декады {s}..{e} — аномалию считать нельзя."
                )
            anom = round(100.0 * (p_sum - p_clim) / p_clim, 1)
            sm_vals = [soil[d] for d in days if d in soil.index]
            sm = round(float(sum(sm_vals) / len(sm_vals)), 4) if sm_vals else None

            deficit = max(0.0, min(100.0, -anom))
            heat_score = heat / n * 100.0
            dry_score = best / n * 100.0
            risk = round(0.4 * deficit + 0.35 * heat_score + 0.25 * dry_score, 1)
            risk = max(0.0, min(100.0, risk))
            decades.append({
                "decade": f"{year}-{m:02d}-D{part}",
                "label": f"{MONTH_RU[m]} D{part} ({s[5:]}..{e[5:]})",
                "month": m,
                "dates": f"{s}..{e}",
                "n_days": n,
                "precip_sum_mm": p_sum,
                "precip_clim_mm": round(p_clim, 1),
                "precip_anom_pct": anom,
                "dry_streak": int(best),
                "heat_days": heat,
                "soil_proxy": sm,
                "risk_index": risk,
                "light": _light(risk),
            })

    def _mean(ms: list[int]) -> float:
        vals = [d["risk_index"] for d in decades if d["month"] in ms]
        return round(sum(vals) / len(vals), 1)

    may = _mean([5])
    jja = _mean([6, 7, 8])
    sep = _mean([9])
    seasonal = round(STAGE_WEIGHTS["may"] * may
                     + STAGE_WEIGHTS["jun_aug"] * jja
                     + STAGE_WEIGHTS["sep"] * sep, 1)
    return {
        "district_en": district_en,
        "district_ru": meta.get("name_ru"),
        "lat": lat, "lon": lon, "year": year,
        "decades": decades,
        "stages": {"may": may, "jun_jul_aug": jja, "sep": sep},
        "stage_weights": {"may": 0.2, "jun_jul_aug": 0.5, "sep": 0.3},
        "seasonal_risk": seasonal,
        "seasonal_light": _light(seasonal),
        "formula": "0.4*precip_deficit + 0.35*heat + 0.25*dry; "
                   "deficit=clip(-precip_anom_pct,0,100), "
                   "heat=heat_days/n*100, dry=dry_streak/n*100",
        "traffic_light": "🟢<35 🟡35-60 🔴>60",
        "sources": ["Open-Meteo archive (факт+климатология 2005-2020)",
                    "Open-Meteo forecast 16d (добивка будущих дат)"],
        "note": "Живые данные Open-Meteo. Сентябрь включён ради весов 0.2/0.5/0.3 "
                "(сумма 1.0): декады ТЗ 'май-август' + сентябрь для веса 0.3. "
                "soil_proxy=None там, где ERA5-Land ещё не опубликован для 2026 "
                "(задержка реанализа, в архиве null) — моки не подставляем; "
                "индекс риска от soil_proxy не зависит (только precip/heat/dry).",
    }


if __name__ == "__main__":
    import json
    import sys

    d = sys.argv[1] if len(sys.argv) > 1 else "Esil"
    y = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    print(json.dumps(decade_risk(d, y), ensure_ascii=False, indent=2))
