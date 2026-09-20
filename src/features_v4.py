"""features_v4.py — фичи v4 из открытых источников хакатона (новых долгих загрузок нет).

Входы (все локальные):
  data/processed/akmola_panel_v3.csv — панель v3 (23 колонки)
  data/raw/sown_area.csv             — посевные площади stat.gov.kz
      (year,district_en,crop_group,area_ha,source; группы grain/oilseeds/sunflower)
  data/processed/soil.csv            — SoilGrids REST (nitrogen/ph/soc/clay,
      10/10 районов: centroid + arable-offset)

Новые колонки v4:
  oilseeds_area_ha / sunflower_area_ha / grain_area_ha — площади района на год
      (га). Пропуски (ранние годы подсолнечника, Кокшетау): ffill+bfill внутри
      района с флагом area_filled=1 (иначе 0). Источник: stat.gov.kz
      dynamic-tables 1485 (см. docs/AREA_FEASIBILITY.md, src/fetch_area.py).
  oilseeds_share — доля масличных: oilseeds/(grain+oilseeds). Ловит сдвиг
      структуры посевов 2005 (1%) → 2024 (существенно) без утечек (площади
      года Y известны к севу).
  htc_mjja — ГТК Селянинова за MJJA: 10*precip_mjja/(tmean_mjja*123).
      Классический агрометеорологический индекс зоны рискованного земледелия
      (методология КазГидромет декадных обзоров: ГТК<0.7 засуха, >1.0 влажно).
      Считается из колонок панели, новых загрузок нет.
  soil_N / soil_pH / soil_SOC / soil_clay — статичные свойства почвы района
      (SoilGrids v2.0 REST, среднее 0–5 + 5–15 см). Источник: ISRIC SoilGrids.

Выход: data/processed/akmola_panel_v4.csv (v3 + 9 колонок).
Честность: площади/почва года Y (площади известны к севу, почва статична);
будущее не используется.

NEW_DATA #1 (regime): структурный сдвиг 2024–2025 ловим ТОЛЬКО идентифицируемыми
на train (<=2020) календарными фичами:
  trend_sq — year_trend^2 (ускорение тренда; year_trend = year−2005 из v3);
  trend_recent — max(0, year−2015) (излом темпа с 2015, экстраполируется на 2021+);
  oilshare_trend — oilseeds_share × year_trend (доля масличных × время).
А dummy post2020=(year>=2021) СОЗНАТЕЛЬНО НЕ добавляем: на train<=2020 он
тождественный 0 (константа, _usable_candidates его исключит), коэффициент
неидентифицируем без подглядывания в hold-out. Отбор — train-only SelectKBest
в src/train.py; evaluate.py hold-out не трогает.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL_V3 = ROOT / "data" / "processed" / "akmola_panel_v3.csv"
AREA_CSV = ROOT / "data" / "raw" / "sown_area.csv"
SOIL_CSV = ROOT / "data" / "processed" / "soil.csv"
OUT = ROOT / "data" / "processed" / "akmola_panel_v4.csv"

MJJA_DAYS = 123  # май(31)+июнь(30)+иуль(31)+август(31)


def main() -> None:
    df = pd.read_csv(PANEL_V3)
    print(f"[v4] panel v3: {df.shape}")

    # --- площади ---
    area = pd.read_csv(AREA_CSV)
    piv = area.pivot_table(index=["year", "district_en"], columns="crop_group",
                           values="area_ha", aggfunc="first").reset_index()
    piv = piv.rename(columns={"grain": "grain_area_ha",
                              "oilseeds": "oilseeds_area_ha",
                              "sunflower": "sunflower_area_ha"})
    # Кокшетау-город и ранние годы: ffill внутри района (только прошлое),
    # остаток — областное значение ТОГО ЖЕ года (пространство, не будущее).
    for c in ("grain_area_ha", "oilseeds_area_ha", "sunflower_area_ha"):
        if c not in piv.columns:
            piv[c] = float("nan")
    piv = piv.sort_values(["district_en", "year"])
    filled_flag = piv[["grain_area_ha", "oilseeds_area_ha",
                       "sunflower_area_ha"]].isna().any(axis=1)
    for c in ("grain_area_ha", "oilseeds_area_ha", "sunflower_area_ha"):
        piv[c] = piv.groupby("district_en")[c].transform(lambda s: s.ffill())
    oblast = piv[piv["district_en"] == "Akmola_oblast"].set_index("year")
    for c in ("grain_area_ha", "oilseeds_area_ha", "sunflower_area_ha"):
        piv[c] = piv.apply(
            lambda r: (oblast[c].get(r["year"]) if pd.isna(r[c]) and r["year"] in oblast.index
                       else r[c]), axis=1)
    piv["area_filled"] = filled_flag.astype(int)
    # районы без своих площадей (нет в sown_area) — областной якорь невозможен
    # попиксельно: оставляем NaN->0 с флагом (таких нет: все 10 районов есть)
    df = df.merge(piv, on=["year", "district_en"], how="left")
    for c in ("grain_area_ha", "oilseeds_area_ha", "sunflower_area_ha"):
        df[c] = df[c].fillna(0.0)
    df["area_filled"] = df["area_filled"].fillna(1).astype(int)
    tot = df["grain_area_ha"] + df["oilseeds_area_ha"]
    df["oilseeds_share"] = (df["oilseeds_area_ha"] / tot.replace(0, float("nan"))
                            ).fillna(0.0).round(4)

    # --- ГТК Селянинова ---
    df["htc_mjja"] = (10.0 * df["precip_mjja"]
                      / (df["tmean_mjja"] * MJJA_DAYS)).round(3)

    # --- NEW_DATA #1: режимные календарные фичи (без утечек) ---
    if "year_trend" not in df.columns:  # fallback для панели v2
        df["year_trend"] = (df["year"] - 2005).astype(int)
    df["trend_sq"] = (df["year_trend"] ** 2).astype(int)
    df["trend_recent"] = (df["year"] - 2015).clip(lower=0).astype(int)
    df["oilshare_trend"] = (df["oilseeds_share"] * df["year_trend"]).round(4)

    # --- почва (статика района) ---
    soil = pd.read_csv(SOIL_CSV)
    colmap = {}
    for c in soil.columns:
        cl = c.lower()
        if "nitrogen" in cl or cl in ("n", "nitro"):
            colmap[c] = "soil_N"
        elif "ph" in cl:
            colmap[c] = "soil_pH"
        elif "soc" in cl or "carbon" in cl or "oc" in cl:
            colmap[c] = "soil_SOC"
        elif "clay" in cl:
            colmap[c] = "soil_clay"
    soil = soil.rename(columns=colmap)
    keep = ["district_en", "soil_N", "soil_pH", "soil_SOC", "soil_clay"]
    keep = [c for c in keep if c in soil.columns or c == "district_en"]
    df = df.merge(soil[keep], on="district_en", how="left")
    print(f"[v4] soil cols: {[c for c in keep if c != 'district_en']}, "
          f"NaN: {int(df[[c for c in keep if c != 'district_en']].isna().sum().sum())}")

    df.to_csv(OUT, index=False)
    print(f"[v4] saved {OUT}: {df.shape}")
    print(f"[v4] new cols: oilseeds_area_ha, sunflower_area_ha, grain_area_ha, "
           f"area_filled, oilseeds_share, htc_mjja, trend_sq, trend_recent, "
           f"oilshare_trend, "
           f"{[c for c in keep if c != 'district_en']}")


if __name__ == "__main__":
    main()
