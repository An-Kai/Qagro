"""features.py — слияние stat + NASA + Open-Meteo в панель akmola_panel.csv.

Целевая схема:
  year,district,district_en,lat,lon,crop,yield_c_ha,
  tmean_mjja,precip_mjja,gdd5,heat30,dry_max,et0,p30_anom

Правила слияния (приоритеты задокументированы):
  tmean_mjja  <- NASA POWER T2M MJJA (месячный реанализ, стабилен 2005-2025)
  precip_mjja <- Open-Meteo precip_515_831 (дневные суммы ERA5; точнее месячного
                 POWER для засух/ливней)
  gdd5        <- Open-Meteo gdd5 (дневной; base 5 °C — совпадает с base_temp
                 пшеницы/ячменя из districts.yaml)
  heat30      <- Open-Meteo heat30_count (дневной подсчёт; точный)
                 (NASA heat_days_gt30 остаётся в nasa_summary.csv как оценка)
  dry_max     <- Open-Meteo dry_streak_max
  et0         <- Open-Meteo et0_sum
  p30_anom    <- Open-Meteo p30_anom_pct (vs климатология 2005-2020)
  yield_c_ha  <- stat_yield.csv (БНС-якоря + даунскейлинг, см. fetch_stat.py)

Контроль качества: inner-join по (district, year); если для пары нет климата —
loud fail (никаких NaN-заглушек). Итог: районы(10) x годы(21) x культуры(2).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CONFIG = ROOT / "config" / "districts.yaml"


def load_latlon() -> pd.DataFrame:
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    rows = [{"district": d["name_ru"], "district_en": d["name_en"],
             "lat": d["lat"], "lon": d["lon"]} for d in cfg["districts"]]
    return pd.DataFrame(rows)


def build_panel(stat: pd.DataFrame, nasa: pd.DataFrame, om: pd.DataFrame) -> pd.DataFrame:
    geo = load_latlon()
    # климат на район-год (один набор на обе культуры)
    clim = pd.merge(
        nasa[["district", "district_en", "year", "tmean_mjja"]],
        om[["district", "district_en", "year", "precip_515_831", "gdd5",
            "heat30_count", "dry_streak_max", "et0_sum", "p30_anom_pct"]],
        on=["district", "district_en", "year"], how="inner",
    )
    clim = clim.rename(columns={
        "precip_515_831": "precip_mjja",
        "heat30_count": "heat30",
        "dry_streak_max": "dry_max",
        "et0_sum": "et0",
        "p30_anom_pct": "p30_anom",
    })
    panel = pd.merge(stat, clim, on=["district", "year"], how="left",
                     suffixes=("", "_clim"))
    # район-английское имя и координаты — из конфига (single source of truth)
    panel = panel.drop(columns=[c for c in ["district_en_clim"] if c in panel.columns])
    panel = pd.merge(panel, geo, on="district", how="left", suffixes=("", "_geo"))
    # resolve district_en: из stat-merge (nasa/om) vs geo — должны совпадать
    if "district_en_geo" in panel.columns:
        mismatch = panel[panel["district_en"] != panel["district_en_geo"]]
        if not mismatch.empty:
            raise ValueError(f"district_en mismatch:\n{mismatch.head()}")
        panel = panel.drop(columns=["district_en_geo"])
    cols = ["year", "district", "district_en", "lat", "lon", "crop", "yield_c_ha",
            "tmean_mjja", "precip_mjja", "gdd5", "heat30", "dry_max", "et0", "p30_anom"]
    panel = panel[cols].sort_values(["year", "district", "crop"]).reset_index(drop=True)
    # финальный QC
    if panel.empty:
        raise ValueError("panel is empty")
    if panel["yield_c_ha"].isna().any():
        raise ValueError(f"NaN in yield_c_ha:\n{panel[panel.yield_c_ha.isna()].head()}")
    clim_cols = ["tmean_mjja", "precip_mjja", "gdd5", "heat30", "dry_max", "et0", "p30_anom"]
    if panel[clim_cols].isna().any().any():
        raise ValueError(f"NaN in climate cols:\n{panel[panel[clim_cols].isna().any(axis=1)].head()}")
    return panel
