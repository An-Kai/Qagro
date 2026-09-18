"""train.py — обучение LGBM per-crop + бейзлайн (среднее пред. 5 лет по району).

Схема данных: data/processed/akmola_panel.csv
  year,district,district_en,lat,lon,crop,yield_c_ha,
  tmean_mjja,precip_mjja,gdd5,heat30,dry_max,et0,p30_anom

Метод (per crop in {spring_wheat, barley}):
  * Бейзлайн (обязательно по ТЗ): прогноз на год Y = mean(yield за Y-5..Y-1
    того же района и той же культуры). Параметров нет, правило фиксируется
    в models/baseline.json (window=5).
  * Модель: LightGBMRegressor (деревья — StandardScaler не нужен и не используется).
  * Фичи: tmean_mjja, precip_mjja, gdd5, heat30, dry_max, et0, p30_anom,
    lat, lon + yield_lag1 (лаг урожайности внутри (район, культура), shift(1)).
  * Валидация: TimeSeriesSplit(n_splits=5) на train (<=2020) +
    leave-one-year-out 2020-2025 в expanding-window постановке
    (для тестового года Y обучаемся только на годах < Y — без утечек).
  * Финальная модель обучается на 2006-2020 (2005 уходит под лаг),
    hold-out 2021-2025 НЕ трогаем — его считает src/evaluate.py.

Артефакты:
  models/lgbm_{crop}.pkl  — dict(model, features, residual_std, meta)
  models/baseline.json    — правило бейзлайна (window=5)

Референс подхода (градиентный бустинг на MJJA-агроклимате): UniCrop, MIT license.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - exotic streams
    pass

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "processed" / "akmola_panel.csv"
MODELS = ROOT / "models"

# v2: 6 культур. Обучаем каждую, где достаточно строк (MIN_TRAIN_ROWS);
# иначе — пропускаем и оставляем APPROX (см. src/approx_crops.py), без выдумок.
CROPS = ["spring_wheat", "barley", "oats", "sunflower", "rapeseed", "flax"]
MIN_TRAIN_ROWS = 40
BASELINE_WINDOW = 5
HOLDOUT_FROM = 2021  # hold-out 2021-2025 считает evaluate.py, сюда не заглядываем
LOYO_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]

CLIMATE_FEATURES = [
    "tmean_mjja", "precip_mjja", "gdd5", "heat30",
    "dry_max", "et0", "p30_anom",
]
GEO_FEATURES = ["lat", "lon"]
BASE_FEATURES = CLIMATE_FEATURES + GEO_FEATURES + ["yield_lag1"]
# v2: ndvi_max — optional (только если features_ndvi нашёл настоящие NDVI
# без NaN; иначе молча пропускаем — модель работает без NDVI).
OPTIONAL_NDVI = ["ndvi_max"]
TARGET = "yield_c_ha"

LGBM_PARAMS = dict(
    n_estimators=500,
    learning_rate=0.05,
    num_leaves=15,
    min_child_samples=10,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=1,
    lambda_l2=1.0,
    random_state=42,
    verbose=-1,
    deterministic=True,
)


def _resolve_features(df: pd.DataFrame) -> tuple[list[str], bool]:
    """Базовые фичи + optional ndvi_max (только если есть настоящие NDVI без NaN)."""
    try:
        try:
            from src.features_ndvi import NDVI_COL, add_ndvi_features
        except ImportError:
            try:
                from .features_ndvi import NDVI_COL, add_ndvi_features  # type: ignore
            except ImportError:
                from features_ndvi import NDVI_COL, add_ndvi_features  # type: ignore
        _, has_ndvi = add_ndvi_features(df.drop(columns=["yield_lag1"], errors="ignore"))
        if has_ndvi and NDVI_COL in df.columns:
            return BASE_FEATURES + [NDVI_COL], True
        # add_ndvi_features проверяет покрытие сама; если False — без NDVI
        # (проверяем ещё раз наличие колонки, чтобы не сломать wheat/barley)
        return list(BASE_FEATURES), False
    except Exception as e:
        print(f"[train] NDVI optional join пропущен ({type(e).__name__}: {e}) — "
              f"обучаем на базовых фичах.")
        return list(BASE_FEATURES), False


def load_panel() -> pd.DataFrame:
    if not PANEL.exists():
        raise FileNotFoundError(f"Нет панели данных: {PANEL}")
    df = pd.read_csv(PANEL)
    need = {"year", "district", "district_en", "lat", "lon", "crop",
            TARGET, *CLIMATE_FEATURES}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"В панели нет колонок: {sorted(missing)}")
    if df.empty:
        raise ValueError("Панель пустая — обучать не на чем (мок не делаем, падаем).")
    bad_crops = set(df["crop"].unique()) - set(CROPS)
    if bad_crops:
        raise ValueError(f"Неизвестные культуры в панели: {sorted(bad_crops)}")
    df = df.sort_values(["crop", "district_en", "year"]).reset_index(drop=True)
    # лаг урожайности строго внутри (район, культура) — без утечек между районами
    df["yield_lag1"] = df.groupby(["district_en", "crop"])[TARGET].shift(1)
    # optional NDVI join (без NaN-заглушек; при отсутствии — пропускаем)
    try:
        try:
            from src.features_ndvi import add_ndvi_features
        except ImportError:
            try:
                from .features_ndvi import add_ndvi_features  # type: ignore
            except ImportError:
                from features_ndvi import add_ndvi_features  # type: ignore
        df_joined, has_ndvi = add_ndvi_features(df)
        if has_ndvi:
            df = df_joined
            print("[train] NDVI: ndvi_max найден и присоединён (optional).")
        else:
            print("[train] NDVI: нет настоящих NDVI — обучаем без ndvi_max.")
    except Exception as e:
        print(f"[train] NDVI join пропущен ({type(e).__name__}: {e}).")
    return df


def baseline_pred(series: pd.Series, window: int = BASELINE_WINDOW) -> pd.Series:
    """Среднее пред. `window` лет. Ожидает серию, отсортированную по году."""
    return series.shift(1).rolling(window, min_periods=window).mean()


def make_model() -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(**LGBM_PARAMS)


# Backward-compat alias (wheat/barley без NDVI используют именно его)
FEATURES = BASE_FEATURES


def _active_features(df_crop: pd.DataFrame) -> list[str]:
    """Активный набор фич: базовые + ndvi_max, если колонка реально есть без NaN."""
    feats = list(BASE_FEATURES)
    if "ndvi_max" in df_crop.columns and not df_crop["ndvi_max"].isna().any():
        feats = feats + ["ndvi_max"]
    return feats


def cv_report(df_crop: pd.DataFrame, crop: str) -> tuple[np.ndarray, dict]:
    """TimeSeriesSplit(5) на train(<=2020) + expanding LOYO 2020-2025. Возвращает OOF-предсказания train."""
    feats = _active_features(df_crop.dropna(subset=["yield_lag1"]))
    train = df_crop[df_crop["year"] < HOLDOUT_FROM].dropna(subset=["yield_lag1", *feats]).reset_index(drop=True)
    if len(train) < MIN_TRAIN_ROWS:
        raise ValueError(f"[{crop}] мало train-строк для CV: {len(train)} < {MIN_TRAIN_ROWS}")
    X = train[feats].to_numpy()
    y = train[TARGET].to_numpy()

    tss = TimeSeriesSplit(n_splits=5)
    oof = np.full_like(y, np.nan, dtype=float)
    fold_rows = []
    for i, (tr, te) in enumerate(tss.split(X)):
        m = make_model()
        m.fit(X[tr], y[tr])
        p = m.predict(X[te])
        oof[te] = p
        fold_rows.append({
            "fold": i,
            "n_train": int(len(tr)), "n_test": int(len(te)),
            "mae": float(mean_absolute_error(y[te], p)),
            "rmse": float(np.sqrt(mean_squared_error(y[te], p))),
        })
    oof_mask = ~np.isnan(oof)
    oof_mae = float(mean_absolute_error(y[oof_mask], oof[oof_mask]))
    oof_rmse = float(np.sqrt(mean_squared_error(y[oof_mask], oof[oof_mask])))
    print(f"[{crop}] TimeSeriesSplit(5) on <=2020: OOF MAE={oof_mae:.3f} RMSE={oof_rmse:.3f}")
    for r in fold_rows:
        print(f"  fold {r['fold']}: n_train={r['n_train']} n_test={r['n_test']} "
              f"MAE={r['mae']:.3f} RMSE={r['rmse']:.3f}")

    # Expanding-window LOYO: тест года Y обучается только на годах < Y
    print(f"[{crop}] leave-one-year-out (expanding, no leakage):")
    loyo_rows = []
    full = df_crop.dropna(subset=["yield_lag1", *feats]).reset_index(drop=True)
    for yr in LOYO_YEARS:
        tr = full[full["year"] < yr]
        te = full[full["year"] == yr]
        if tr.empty or te.empty:
            raise ValueError(f"[{crop}] LOYO год {yr}: пустой train ({len(tr)}) или test ({len(te)})")
        m = make_model()
        m.fit(tr[feats].to_numpy(), tr[TARGET].to_numpy())
        p = m.predict(te[feats].to_numpy())
        yt = te[TARGET].to_numpy()
        # бейзлайн на тот же год (честный, только прошлое)
        te_sorted = te.sort_values(["district_en", "year"])
        bl = []
        for d, g in df_crop[df_crop["district_en"].isin(te_sorted["district_en"].unique())].groupby("district_en"):
            s = g[g["crop"] == crop].sort_values("year").set_index("year")[TARGET]
            past = s[s.index < yr].tail(BASELINE_WINDOW)
            if len(past) < BASELINE_WINDOW:
                raise ValueError(f"[{crop}] бейзлайн: мало истории для {d} к {yr} ({len(past)} < {BASELINE_WINDOW})")
            bl.append({"district_en": d, "bl": float(past.mean())})
        bl = te_sorted.merge(pd.DataFrame(bl), on="district_en", how="left")
        row = {
            "year": yr,
            "lgbm_mae": float(mean_absolute_error(yt, p)),
            "lgbm_rmse": float(np.sqrt(mean_squared_error(yt, p))),
            "bl_mae": float(mean_absolute_error(yt, bl["bl"].to_numpy())),
        }
        loyo_rows.append(row)
        print(f"  {yr}: LGBM MAE={row['lgbm_mae']:.3f} RMSE={row['lgbm_rmse']:.3f} | BL MAE={row['bl_mae']:.3f}")
    resid_std = float(np.nanstd(y[oof_mask] - oof[oof_mask]))
    return oof, {"folds": fold_rows, "loyo": loyo_rows, "resid_std_oof": resid_std}


def train_crop(df_crop: pd.DataFrame, crop: str) -> dict:
    feats = _active_features(df_crop.dropna(subset=["yield_lag1"]))
    cv_report(df_crop, crop)
    train = df_crop[(df_crop["year"] < HOLDOUT_FROM)].dropna(subset=["yield_lag1", *feats])
    X = train[feats]
    y = train[TARGET]
    model = make_model()
    model.fit(X.to_numpy(), y.to_numpy())
    # ширина интервала: std OOF-остатков (честная, из CV), пересчёт для артефакта
    tss = TimeSeriesSplit(n_splits=5)
    oof = np.full(len(train), np.nan)
    Xa, ya = X.to_numpy(), y.to_numpy()
    for tr, te in tss.split(Xa):
        m = make_model()
        m.fit(Xa[tr], ya[tr])
        oof[te] = m.predict(Xa[te])
    resid_std = float(np.nanstd(ya - oof))
    bundle = {
        "model": model,
        "features": feats,
        "target": TARGET,
        "crop": crop,
        "residual_std": resid_std,
        "train_years": [int(train["year"].min()), int(train["year"].max())],
        "n_train": int(len(train)),
        "baseline_window": BASELINE_WINDOW,
        "lgbm_params": LGBM_PARAMS,
    }
    out = MODELS / f"lgbm_{crop}.pkl"
    with open(out, "wb") as f:
        pickle.dump(bundle, f)
    print(f"[{crop}] saved {out} (n_train={len(train)}, resid_std={resid_std:.3f}, "
          f"features={feats})")
    return bundle


def main() -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    df = load_panel()
    print(f"panel: {len(df)} rows, years {int(df.year.min())}-{int(df.year.max())}, "
          f"districts {df.district_en.nunique()}, crops {sorted(df.crop.unique())}")
    trained: list[str] = []
    approx_left: list[str] = []
    for crop in CROPS:
        df_crop = df[df["crop"] == crop].sort_values(["district_en", "year"]).reset_index(drop=True)
        if len(df_crop) < MIN_TRAIN_ROWS:
            print(f"[{crop}] строк {len(df_crop)} < {MIN_TRAIN_ROWS} — пропускаем, "
                  f"остаётся APPROX (см. src/approx_crops.py).")
            approx_left.append(crop)
            continue
        train_crop(df_crop, crop)
        trained.append(crop)
    if approx_left:
        print(f"APPROX без обучения (мало строк): {approx_left}")
    baseline_spec = {
        "rule": "mean of previous 5 years, same district + same crop",
        "rule_ru": "среднее за предыдущие 5 лет по тому же району и той же культуре",
        "window": BASELINE_WINDOW,
        "crops": trained,
        "approx_crops": approx_left,
        "target": TARGET,
        "note": "Параметров нет: прогноз на год Y = mean(yield[Y-5..Y-1] | district, crop). "
                "Требуется полная 5-летняя история, иначе ошибка (без заглушек).",
    }
    with open(MODELS / "baseline.json", "w", encoding="utf-8") as f:
        json.dump(baseline_spec, f, ensure_ascii=False, indent=2)
    print(f"saved {MODELS / 'baseline.json'}")
    print("DONE train.py")


if __name__ == "__main__":
    main()
