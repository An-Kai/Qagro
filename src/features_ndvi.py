"""features_ndvi.py — v2 optional NDVI join (модель работает БЕЗ NDVI).

Вход: панель akmola_panel.csv (DataFrame) + data/ndvi/ndvi_timeseries.json
  [{district, date, ndvi_mean|None, scene_id, status}].

Логика (честная):
  - Если файла нет, он пуст, все ndvi_mean None/NaN, или покрытие <2 районов —
    возвращаем панель БЕЗ изменений + has_ndvi=False. train.py / predict.py
    тогда используют базовые фичи (wheat/barley метрики не ломаются).
  - Если есть настоящие (конечные, не-None) ndvi_mean — считаем сезонный
    максимум ndvi_max на (district_en, год из date) и left-join к панели
    как колонку ndvi_max. Возвращаем has_ndvi=True только если колонка
    полностью без NaN на train-периоде; иначе тоже пропускаем (False),
    чтобы не плодить заглушки.

Никаких выдуманных NDVI: None/NaN никогда не заполняем средними.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
NDVI_JSON = ROOT / "data" / "ndvi" / "ndvi_timeseries.json"

NDVI_COL = "ndvi_max"


def load_ndvi_timeseries() -> pd.DataFrame | None:
    """Прочитать ndvi_timeseries.json -> DataFrame или None (нет файла/пусто)."""
    if not NDVI_JSON.exists():
        return None
    try:
        raw = json.loads(NDVI_JSON.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not raw:
        return None
    df = pd.DataFrame(raw)
    if df.empty or "ndvi_mean" not in df.columns:
        return None
    return df


def seasonal_ndvi_max(ndvi_df: pd.DataFrame) -> pd.DataFrame | None:
    """Сезонный максимум NDVI на (district_en, year). Только реальные числа.

    Возвращает DataFrame[district_en, year, ndvi_max] или None, если
    настоящих значений нет (<1 конечного ndvi_mean).
    """
    df = ndvi_df.copy()
    df["ndvi_mean"] = pd.to_numeric(df.get("ndvi_mean"), errors="coerce")
    real = df[df["ndvi_mean"].notna()].copy()
    if real.empty:
        return None
    # district -> district_en (в json лежит district уже как EN-код демо-полей)
    real["district_en"] = real["district"].astype(str)
    real["date"] = pd.to_datetime(real.get("date"), errors="coerce")
    real = real[real["date"].notna()]
    if real.empty:
        return None
    real["year"] = real["date"].dt.year.astype(int)
    # честная агрегация: максимум по всем сценам сезона района-года
    agg = real.groupby(["district_en", "year"], as_index=False)["ndvi_mean"].max()
    agg = agg.rename(columns={"ndvi_mean": NDVI_COL})
    # NDVI вне [-1, 1] — мусор, отбрасываем
    agg = agg[(agg[NDVI_COL] >= -1.0) & (agg[NDVI_COL] <= 1.0)]
    if agg.empty:
        return None
    return agg


def add_ndvi_features(panel: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Optional join ndvi_max к панели. Возвращает (panel_out, has_ndvi).

    has_ndvi=True только если ndvi_max добавлен И без NaN (иначе False
    и панель возвращается без изменений — без заглушек).
    """
    if panel.empty:
        return panel, False
    ndvi_df = load_ndvi_timeseries()
    if ndvi_df is None:
        return panel, False
    agg = seasonal_ndvi_max(ndvi_df)
    if agg is None or agg.empty:
        return panel, False
    # Покрытие: требуем хотя бы 2 района с NDVI, иначе join бессмысленен
    if agg["district_en"].nunique() < 2:
        return panel, False
    out = panel.merge(agg, on=["district_en", "year"], how="left")
    if out[NDVI_COL].isna().any():
        # Частичное покрытие (демо 2 поля) — не тянем NaN в модель, пропускаем
        return panel, False
    return out, True
