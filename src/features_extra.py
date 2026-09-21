"""features_extra.py — v3 extra-фичи из УЖЕ СКАЧАННЫХ raw (новых долгих загрузок нет).

Входы (все локальные, скачаны fetch_nasa.py / fetch_openmeteo.py / fetch_stat.py):
  data/raw/nasa_summary.csv                 — MJJA-агрегаты NASA POWER monthly
  data/raw/nasa_{district_en}.json          — сырые monthly POWER (fallback)
  data/raw/openmeteo_{district_en}_daily.json — сырые daily Open-Meteo Archive
  data/raw/stat_yield.csv                   — через data/processed/akmola_panel.csv
  data/processed/akmola_panel.csv           — базовая панель v2 (совместимость)
  data/ndvi/ndvi_timeseries.json            — 5 реальных NDVI (Esil/Zerenda 2024)

Выход: data/processed/akmola_panel_v3.csv — все колонки v2 + новые:
  precip_spring — сумма осадков март-май (мм), запас весенней влаги перед MJJA.
      Источник/формула: Open-Meteo Archive daily `precipitation_sum` (ERA5,
      мм; доки: https://open-meteo.com/en/docs/historical-weather-api ,
      daily-переменные; тот же ответ, что качает src/fetch_openmeteo.py).
      Сумма по дням 03-01..05-31 каждого года и района. Fallback (если daily
      нет): NASA POWER monthly PRECTOTCORR (мм/день; доки:
      https://power.larc.nasa.gov/docs/ ) за месяцы 3,4,5 × дни месяца.
  tmax_july — средняя дневная Tmax июля (°C), жара в критический месяц
      (цветение/налив). Источник: Open-Meteo daily `temperature_2m_max`,
      среднее 07-01..07-31. Fallback: NASA POWER monthly T2M_MAX за июль.
  dtr — суточная амплитуда MJJA (°C): T2M_MAX − T2M_MIN (средние MJJA
      из nasa_summary.csv). Источник переменных: NASA POWER monthly
      (тот же запрос, что в src/fetch_nasa.py). DTR — стандартный
      агростресс-прокси (большая амплитуда = ясные жаркие дни/холодные ночи).
  vpd_proxy — дефицит давления пара MJJA (кПа), уже посчитан в
      nasa_summary.csv формулой Магнуса из T2M и RH2M:
      es = 0.6108*exp(17.27*T/(T+237.3)); ea = es*RH/100; VPD = es − ea
      (FAO-56, Allen et al. 1998 — та же формула, что в src/fetch_nasa.py;
      здесь колонку переиспользуем как есть, источник: NASA POWER docs).
  spei_proxy — водный баланс сезона (мм): precip_mjja − et0.
      Концептуальный прокси члена D = P − PET индекса SPEI
      (Vicente-Serrano et al. 2010); PET≈ET0 FAO-56 Penman-Monteith
      (Allen et al. 1998) — колонка et0 из Open-Meteo `et0_fao_evapotranspiration`
      (см. src/fetch_openmeteo.py). НЕ стандартизирован — потому "proxy".
  year_trend — year − 2005. Линейный календарный тренд как фича (таргет БЕЗ
      преобразований): ловит структурный сдвиг уровня масличных 2024–2025
      (гибриды/площади; форма якорей — FAOSTAT QCL methodology: разрывы рядов
      из-за смены методологии/охвата — здесь аналогичный разрыв в stat_yield).
  yield_roll3 — среднее урожайности 3 ПРЕДЫДУЩИХ лет того же района+культуры
      (только прошлое: shift(1).rolling(3) — без утечек; короткий аналог
      бейзлайна window=5 из models/baseline.json, быстрее адаптируется).
  ndvi_max — сезонный максимум реальных Sentinel-2 NDVI
      (data/ndvi/ndvi_timeseries.json, только конечные ndvi_mean; агрегация —
      та же, что в src/features_ndvi.py). Где сцен нет — NaN + ndvi_flag=0.
      Никаких средних-заглушек.

Честность: все фичи на год Y используют только данные года Y (климат) и
строго Y−k (урожаи). Будущее не используется. NaN запрещены везде, кроме
ndvi_max (с флагом) и yield_roll3 за 2005–2007 (нет 3 лет истории — такие
строки train.py/evaluate.py дропают, как раньше дропали yield_lag1-2005).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd

# NOTE: дни месяца — вручную (без import calendar, чтобы не зависеть от cwd).
_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        return 29
    return _DAYS_IN_MONTH[month - 1]

if "PYTEST_CURRENT_TEST" not in os.environ:  # не трогаем capture pytest
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
PANEL_V2 = PROC / "akmola_panel.csv"
PANEL_V3 = PROC / "akmola_panel_v3.csv"
NASA_SUMMARY = RAW / "nasa_summary.csv"
NDVI_JSON = ROOT / "data" / "ndvi" / "ndvi_timeseries.json"

BASE_COLS = ["year", "district", "district_en", "lat", "lon", "crop",
             "yield_c_ha", "tmean_mjja", "precip_mjja", "gdd5", "heat30",
             "dry_max", "et0", "p30_anom"]
NEW_COLS = ["precip_spring", "tmax_july", "dtr", "vpd_proxy", "spei_proxy",
            "year_trend", "yield_roll3", "ndvi_max", "ndvi_flag"]


def _daily_frame(district_en: str) -> pd.DataFrame | None:
    """Daily-ряды Open-Meteo из локального raw-json (без сети)."""
    p = RAW / f"openmeteo_{district_en}_daily.json"
    if not p.exists():
        return None
    payload = json.loads(p.read_text(encoding="utf-8"))
    d = payload.get("daily", {})
    times = pd.to_datetime(d.get("time", []), errors="coerce")
    if len(times) == 0:
        return None
    df = pd.DataFrame({
        "date": times,
        "tmax": pd.to_numeric(d.get("temperature_2m_max", []), errors="coerce"),
        "precip": pd.to_numeric(d.get("precipitation_sum", []), errors="coerce"),
    })
    df = df[df["date"].notna()].copy()
    df["year"] = df["date"].dt.year.astype(int)
    df["md"] = df["date"].dt.strftime("%m-%d")
    return df


def _nasa_monthly(district_en: str) -> dict[tuple[int, int], dict[str, float]]:
    """Сырые monthly NASA POWER из локального raw-json (fallback без сети)."""
    p = RAW / f"nasa_{district_en}.json"
    if not p.exists():
        return {}
    payload = json.loads(p.read_text(encoding="utf-8"))
    params = payload.get("properties", {}).get("parameter", {})
    monthly: dict[tuple[int, int], dict[str, float]] = {}
    for pname, series in params.items():
        if not isinstance(series, dict):
            continue
        for k, v in series.items():
            if len(k) != 6 or not k.isdigit():
                continue
            y, m = int(k[:4]), int(k[4:])
            if m == 13:  # годовая строка POWER — пропускаем
                continue
            try:
                monthly.setdefault((y, m), {})[pname] = float(v)
            except (TypeError, ValueError):
                continue
    return monthly


def spring_and_july(district_en: str, years: list[int]) -> pd.DataFrame:
    """precip_spring (03–05 сумма) + tmax_july (средняя Tmax июля).

    Первично — Open-Meteo daily (ERA5); fallback — NASA POWER monthly.
    """
    daily = _daily_frame(district_en)
    monthly = _nasa_monthly(district_en) if daily is None else None
    rows: list[dict] = []
    for y in years:
        ps, tj, src = None, None, None
        if daily is not None:
            g = daily[daily["year"] == y]
            spr = g[(g["md"] >= "03-01") & (g["md"] <= "05-31")]["precip"]
            jul = g[(g["md"] >= "07-01") & (g["md"] <= "07-31")]["tmax"]
            if spr.notna().any() and jul.notna().any() and len(spr) >= 80 and len(jul) >= 25:
                ps = round(float(spr.sum()), 1)
                tj = round(float(jul.mean()), 2)
                src = "openmeteo-daily"
        if ps is None:  # fallback: NASA POWER monthly (без сети, из raw-json)
            if not monthly:
                monthly = _nasa_monthly(district_en)
            if not monthly:
                raise ValueError(f"[{district_en}] нет ни daily, ни NASA-monthly за {y}")
            tot = 0.0
            for m in (3, 4, 5):
                rec = monthly.get((y, m), {})
                pr = rec.get("PRECTOTCORR")
                if pr is None or pr <= -900:
                    raise ValueError(f"[{district_en}] NASA fill/missing PRECTOTCORR {y}-{m:02d}")
                tot += pr * _days_in_month(y, m)
            rec7 = monthly.get((y, 7), {})
            tx7 = rec7.get("T2M_MAX")
            if tx7 is None or tx7 <= -900:
                raise ValueError(f"[{district_en}] NASA fill/missing T2M_MAX {y}-07")
            ps, tj, src = round(tot, 1), round(float(tx7), 2), "nasa-monthly-fallback"
        rows.append({"district_en": district_en, "year": y,
                     "precip_spring": ps, "tmax_july": tj, "_spring_src": src})
    out = pd.DataFrame(rows)
    n_fb = int((out["_spring_src"] == "nasa-monthly-fallback").sum())
    print(f"  [{district_en}] precip_spring/tmax_july: {len(out)} лет "
          f"(fallback NASA: {n_fb})")
    return out.drop(columns=["_spring_src"])


def ndvi_season_max() -> pd.DataFrame | None:
    """Сезонный максимум реальных NDVI (district_en, year). Только числа."""
    if not NDVI_JSON.exists():
        print("  NDVI: файла нет — ndvi_max везде NaN + флаг 0.")
        return None
    try:
        raw = json.loads(NDVI_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  NDVI: битый json ({e}) — ndvi_max везде NaN + флаг 0.")
        return None
    if not raw:
        return None
    df = pd.DataFrame(raw)
    df["ndvi_mean"] = pd.to_numeric(df.get("ndvi_mean"), errors="coerce")
    real = df[df["ndvi_mean"].notna()].copy()
    if real.empty:
        return None
    real["district_en"] = real["district"].astype(str)
    real["date"] = pd.to_datetime(real.get("date"), errors="coerce")
    real = real[real["date"].notna()]
    real["year"] = real["date"].dt.year.astype(int)
    agg = real.groupby(["district_en", "year"], as_index=False)["ndvi_mean"].max()
    agg = agg.rename(columns={"ndvi_mean": "ndvi_max"})
    agg = agg[(agg["ndvi_max"] >= -1.0) & (agg["ndvi_max"] <= 1.0)]
    if agg.empty:
        return None
    print(f"  NDVI: {len(agg)} реальных (district,year)-максимумов: "
          + ", ".join(f"{r.district_en}/{int(r.year)}={r.ndvi_max:.4f}"
                      for r in agg.itertuples()))
    return agg


def main() -> None:
    if not PANEL_V2.exists():
        raise FileNotFoundError(f"Нет базовой панели: {PANEL_V2}")
    panel = pd.read_csv(PANEL_V2)
    missing = set(BASE_COLS) - set(panel.columns)
    if missing:
        raise ValueError(f"В панели v2 нет колонок: {sorted(missing)}")
    nasa = pd.read_csv(NASA_SUMMARY)

    districts = sorted(panel["district_en"].unique())
    years = sorted(int(y) for y in panel["year"].unique())

    # 1) precip_spring + tmax_july из daily (fallback NASA-monthly)
    parts = [spring_and_july(d, years) for d in districts]
    sj = pd.concat(parts, ignore_index=True)

    # 2) dtr + vpd_proxy из NASA MJJA (переиспользуем nasa_summary как есть)
    nv = nasa[["district_en", "year", "tmax_mjja", "tmin_mjja",
               "vpd_proxy"]].copy()
    nv["dtr"] = (nv["tmax_mjja"] - nv["tmin_mjja"]).round(2)  # NASA POWER MJJA
    nv = nv[["district_en", "year", "dtr", "vpd_proxy"]]

    out = panel.merge(sj, on=["district_en", "year"], how="left")
    out = out.merge(nv, on=["district_en", "year"], how="left")

    # 3) spei_proxy = P − ET0 (водный баланс сезона; SPEI-концепция, без стандартизации)
    out["spei_proxy"] = (out["precip_mjja"] - out["et0"]).round(1)

    # 4) year_trend = year − 2005 (структурный сдвиг масличных как фича)
    out["year_trend"] = (out["year"] - 2005).astype(int)

    # 5) yield_roll3 — среднее 3 ПРЕДЫДУЩИХ лет (район, культура), только прошлое
    out = out.sort_values(["crop", "district_en", "year"]).reset_index(drop=True)
    out["yield_roll3"] = (
        out.groupby(["district_en", "crop"])["yield_c_ha"]
        .transform(lambda s: s.shift(1).rolling(3, min_periods=3).mean())
        .round(2)
    )

    # 6) ndvi_max + флаг (реальные сцены, иначе NaN/0)
    agg = ndvi_season_max()
    if agg is not None:
        out = out.merge(agg, on=["district_en", "year"], how="left")
    else:
        out["ndvi_max"] = float("nan")
    out["ndvi_flag"] = out["ndvi_max"].notna().astype(int)

    # --- QC (громко, без заглушек) ---
    for c in ["precip_spring", "tmax_july", "dtr", "vpd_proxy",
              "spei_proxy", "year_trend", "ndvi_flag"]:
        n_nan = int(out[c].isna().sum())
        if n_nan:
            raise ValueError(f"NaN в новой фиче {c}: {n_nan} строк — заглушки запрещены.")
    # yield_roll3 NaN合法 только там, где нет 3 лет истории (2005–2007)
    bad_roll = out[out["yield_roll3"].isna() & (out["year"] > 2007)]
    if not bad_roll.empty:
        raise ValueError(f"yield_roll3 NaN при year>2007:\n{bad_roll.head()}")
    n_roll_nan = int(out["yield_roll3"].isna().sum())
    print(f"  yield_roll3: NaN={n_roll_nan} (все — годы 2005–2007 без 3-летней истории, ok)")
    n_ndvi = int(out["ndvi_flag"].sum())
    print(f"  ndvi_max: покрытие {n_ndvi}/{len(out)} строк "
          f"(остальное NaN+флаг 0 — честно, без средних-заглушек)")

    cols = BASE_COLS + NEW_COLS + (["ndvi_flag"] if "ndvi_flag" not in NEW_COLS else [])
    # NEW_COLS уже без ndvi_flag? — держим флаг отдельной колонкой совместимости
    if "ndvi_flag" not in NEW_COLS:
        cols = BASE_COLS + NEW_COLS + ["ndvi_flag"]
    else:
        cols = BASE_COLS + NEW_COLS
    out = out[cols].sort_values(["year", "district_en", "crop"]).reset_index(drop=True)
    out.to_csv(PANEL_V3, index=False)
    print(f"WROTE {PANEL_V3} rows={len(out)} cols={len(out.columns)} "
          f"(v2 {len(BASE_COLS)} + новые {[c for c in out.columns if c not in BASE_COLS]})")


if __name__ == "__main__":
    main()
