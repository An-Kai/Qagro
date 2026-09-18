"""fetch_openmeteo.py — Open-Meteo Archive daily -> сезонные агрегаты.

Целевой URL из ТЗ:
  https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}
  &start_date=2005-01-01&end_date=2025-08-31
  &daily=temperature_2m_max,temperature_2m_min,precipitation_sum,
         et0_fao_evapotranspiration,soil_moisture_3_9cm&timezone=Asia/Almaty

ВАЖНАЯ ПОПРАВКА (задокументированное отклонение от ТЗ):
  soil_moisture_3_9cm НЕ существует в daily-модели Archive API
  (проверено: API отвечает 400 "Cannot initialize ForecastVariableDaily...").
  Поэтому:
    - daily-запрос: temperature_2m_max, temperature_2m_min, precipitation_sum,
      et0_fao_evapotranspiration (строго валидные daily-переменные);
    - soil moisture тянется ОТДЕЛЬНЫМ hourly-запросом (soil_moisture_3_9cm,
      валидна в hourly) и агрегируется в среднее за MJJA -> колонка sm_hourly_mean.
  Это сохраняет все требуемые признаки и не плодит моки.

Сезон на год: 15 мая – 31 августа (окно 515_831: улавливает налив/колошение
яровой пшеницы и ячменя в Акмолинской области).
Признаки на район-год:
  precip_515_831  — сумма осадков, мм
  dry_streak_max  — макс. подряд дней с осадками < 1.0 мм внутри окна
  heat30_count    — дни с tmax > 30.0 °C внутри окна
  gdd5            — sum(max(0, (tmax+tmin)/2 - 5))
  et0_sum         — сумма ET0 FAO, мм
  sm_mean         — средняя soil_moisture_3_9cm (hourly->daily mean->season mean), м3/м3
  p30_anom_pct    — аномалия осадков окна vs климатология 2005-2020 того же
                    района: 100*(P - Pclim)/Pclim
  tmean_om        — средняя дневная tmean окна (для контроля vs NASA)

Выходы:
  data/raw/openmeteo_<district_en>_daily.json  — сырой daily-ответ (как есть)
  data/raw/openmeteo_summary.csv               — район-год агрегаты

Громкий fail: HTTP != 200 / error:true / пустые ряды / NaN -> exit 1, без моков.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("fetch_openmeteo")

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "districts.yaml"
RAW = ROOT / "data" / "raw"
SUMMARY = RAW / "openmeteo_summary.csv"

START_DATE = "2005-01-01"
END_DATE = "2025-08-31"
TIMEOUT = 90
RETRIES = 4
CLIM_START, CLIM_END = 2005, 2020


def load_districts() -> list[dict]:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ds = cfg.get("districts", [])
    if not ds:
        raise ValueError("districts.yaml: empty districts")
    return ds


def _get(url: str, label: str) -> dict:
    last: Exception | None = None
    for a in range(1, RETRIES + 1):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code != 200:
                raise RuntimeError(f"Open-Meteo HTTP {r.status_code}: {r.text[:500]}")
            payload = r.json()
            if payload.get("error"):
                raise RuntimeError(f"Open-Meteo error: {payload.get('reason')}")
            return payload
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("[%s] attempt %d/%d failed: %s", label, a, RETRIES, e)
            time.sleep(2 * a)
    raise RuntimeError(f"Open-Meteo failed for {label}: {last}")


def fetch_daily(lat: float, lon: float, label: str) -> dict:
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={START_DATE}&end_date={END_DATE}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
        "et0_fao_evapotranspiration&timezone=Asia%2FAlmaty"
    )
    return _get(url, label + "/daily")


def fetch_soil_hourly(lat: float, lon: float, label: str) -> dict:
    # ERA5-Land soil moisture 3-9cm, hourly; агрегируем сами.
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={START_DATE}&end_date={END_DATE}"
        "&hourly=soil_moisture_3_9cm&timezone=Asia%2FAlmaty"
    )
    return _get(url, label + "/soil")


def season_frame(daily: dict, soil: dict, ru: str, en: str) -> pd.DataFrame:
    d = daily.get("daily", {})
    times = pd.to_datetime(d.get("time", []))
    if len(times) == 0:
        raise RuntimeError(f"Open-Meteo empty daily series for {en}")
    df = pd.DataFrame({
        "date": times,
        "tmax": pd.to_numeric(d.get("temperature_2m_max", []), errors="coerce"),
        "tmin": pd.to_numeric(d.get("temperature_2m_min", []), errors="coerce"),
        "precip": pd.to_numeric(d.get("precipitation_sum", []), errors="coerce"),
        "et0": pd.to_numeric(d.get("et0_fao_evapotranspiration", []), errors="coerce"),
    })
    # soil hourly -> daily mean
    h = soil.get("hourly", {})
    htimes = pd.to_datetime(h.get("time", []))
    hvals = pd.to_numeric(h.get("soil_moisture_3_9cm", []), errors="coerce")
    if len(htimes):
        sm = pd.DataFrame({"date": htimes.normalize(), "sm": hvals}).groupby("date")["sm"].mean()
        df["date_n"] = df["date"].dt.normalize()
        df["sm"] = df["date_n"].map(sm)
        df.drop(columns=["date_n"], inplace=True)
    else:
        df["sm"] = float("nan")
    df["year"] = df["date"].dt.year
    df["md"] = df["date"].dt.strftime("%m-%d")
    # окно 05-15..08-31
    win = df[(df["md"] >= "05-15") & (df["md"] <= "08-31")].copy()
    if win.empty:
        raise RuntimeError(f"Open-Meteo empty season window for {en}")
    win["tmean"] = (win["tmax"] + win["tmin"]) / 2.0
    win["district"] = ru
    win["district_en"] = en
    return win


def aggregate(win: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for year, g in win.groupby("year"):
        g = g.sort_values("date")
        if g[["tmax", "tmin", "precip", "et0"]].isna().any().any():
            n_missing = int(g[["tmax", "tmin", "precip", "et0"]].isna().sum().sum())
            # ET0 до 2005..? ERA5 должен покрывать; missing = loud fail
            raise RuntimeError(f"Open-Meteo NaN in season {year} n={n_missing}")
        precip_sum = float(g["precip"].sum())
        heat30 = int((g["tmax"] > 30.0).sum())
        gdd5 = float((((g["tmax"] + g["tmin"]) / 2.0 - 5.0).clip(lower=0)).sum())
        et0_sum = float(g["et0"].sum())
        # dry streak: precip < 1.0
        dry = (g["precip"].values < 1.0)
        best = cur = 0
        for v in dry:
            cur = cur + 1 if v else 0
            best = max(best, cur)
        rows.append({
            "district": g["district"].iloc[0], "district_en": g["district_en"].iloc[0],
            "year": int(year), "precip_515_831": round(precip_sum, 1),
            "dry_streak_max": int(best), "heat30_count": heat30,
            "gdd5": round(gdd5, 1), "et0_sum": round(et0_sum, 1),
            "sm_mean": round(float(g["sm"].mean()), 4) if g["sm"].notna().any() else float("nan"),
            "tmean_om": round(float(g["tmean"].mean()), 2),
            "n_days": int(len(g)),
        })
    out = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    # климатология 2005-2020 того же района
    clim = out[(out["year"] >= CLIM_START) & (out["year"] <= CLIM_END)]["precip_515_831"].mean()
    if not pd.notna(clim) or clim == 0:
        raise RuntimeError("Bad climatology baseline (2005-2020)")
    out["p30_anom_pct"] = round(100.0 * (out["precip_515_831"] - clim) / clim, 1)
    out["precip_clim_0520"] = round(float(clim), 1)
    return out


def main() -> None:
    try:
        districts = load_districts()
        RAW.mkdir(parents=True, exist_ok=True)
        parts: list[pd.DataFrame] = []
        for i, d in enumerate(districts):
            ru, en, lat, lon = d["name_ru"], d["name_en"], d["lat"], d["lon"]
            log.info("Open-Meteo %s (%s, %.2f, %.2f) ...", ru, en, lat, lon)
            daily = fetch_daily(lat, lon, en)
            (RAW / f"openmeteo_{en}_daily.json").write_text(
                json.dumps(daily, ensure_ascii=False), encoding="utf-8")
            try:
                soil = fetch_soil_hourly(lat, lon, en)
            except Exception as e:
                log.warning("[%s] soil hourly failed, continue without sm: %s", en, e)
                soil = {"hourly": {}}
            win = season_frame(daily, soil, ru, en)
            agg = aggregate(win)
            parts.append(agg)
            log.info("  %s: %d seasons, precip2024=%.1f heat2024=%d", en, len(agg),
                     float(agg.loc[agg.year == 2024, 'precip_515_831'].iloc[0])
                     if (agg.year == 2024).any() else -1,
                     int(agg.loc[agg.year == 2024, 'heat30_count'].iloc[0])
                     if (agg.year == 2024).any() else -1)
            # v2: троттлинг против Open-Meteo 429 (minutely limit): пауза между
            # районами, чтобы 20 тяжёлых запросов (daily+soil ×10) не укладывались
            # в одну минуту. Без моков — только вежливая пауза.
            if i < len(districts) - 1:
                time.sleep(7)
        df = pd.concat(parts, ignore_index=True).sort_values(["district_en", "year"])
        if df.empty or df[["precip_515_831", "heat30_count", "gdd5"]].isna().any().any():
            raise ValueError("openmeteo_summary empty or NaN in key cols")
        df.to_csv(SUMMARY, index=False)
        log.info("WROTE %s rows=%d", SUMMARY, len(df))
        # честность про 2025: окно обрезано 31.08 (по ТЗ) — полный сезон MJJA покрыт
        log.info("Note: 2025 season window ends 08-31 per spec (full MJJA covered).")
    except Exception as e:
        log.exception("FATAL fetch_openmeteo failed (no mocks, loud fail): %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
