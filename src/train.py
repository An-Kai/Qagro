"""train.py — обучение бленда LightGBM+Ridge per-crop + бейзлайн (v3).

Схема данных: data/processed/akmola_panel_v3.csv (fallback: akmola_panel.csv)
  v2-колонки + precip_spring, tmax_july, dtr, vpd_proxy, spei_proxy,
  year_trend, yield_roll3, ndvi_max, ndvi_flag (см. src/features_extra.py).

Метод (per crop in 6 культур):
  * Бейзлайн (обязательно по ТЗ, логика wheat/barley сохранена как бэкап):
    прогноз на год Y = mean(yield за Y-5..Y-1 того же района и той же
    культуры). Параметров нет, правило фиксируется в models/baseline.json.
  * Отбор фич per-crop: SelectKBest(f_regression, k=10) на train (<=2020),
    year_trend принудительно в наборе (структурный сдвиг масличных 2024-2025,
    таргет БЕЗ преобразований). Кандидаты с >30% NaN или <2 уникальных
    значений на train исключаются до отбора (сюда попадает ndvi_max/ndvi_flag:
    все 5 реальных NDVI — 2024 год, т.е. hold-out; на train сигнала нет —
    честно исключаем, колонки остаются в panel_v3 для будущего).
  * Модель: бленд LightGBMRegressor (те же параметры, что раньше для
    wheat/barley — StandardScaler не нужен) + Ridge(alpha=1.0) на
    median-impute + StandardScaler (Ridge хорошо держится на малых выборках
    масличных, n~130). Веса 0.7/0.3. predict = 0.7*LGBM + 0.3*Ridge.
  * Валидация: TimeSeriesSplit(n_splits=5) на train (<=2020) +
    leave-one-year-out 2020-2025 в expanding-window постановке
    (для тестового года Y обучаемся только на годах < Y — без утечек).
    OOF-считается для БЛЕНДА; residual_std — std OOF-остатков бленда.
  * Финальная модель обучается на 2008-2020 (2005-2007 уходят под
    yield_roll3, 2005 — под yield_lag1), hold-out 2021-2025 НЕ трогаем.

Артефакты:
  models/lgbm_{crop}.pkl  — dict(model=LGBM, ridge_model, blend_weights,
    features, residual_std, meta). Имя lgbm_* сохранено для обратной
    совместимости (api.py считает файлы, predict_yield читает bundle).
    blend_predict(bundle, X): 0.7*LGBM + 0.3*Ridge, если ridge_model есть.
  models/baseline.json    — правило бейзлайна (window=5).

Референс подхода (градиентный бустинг на MJJA-агроклимате): UniCrop, MIT license.
"""
from __future__ import annotations

import json

import pickle
import os
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.feature_selection import SelectKBest, f_regression
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

if "PYTEST_CURRENT_TEST" not in os.environ:  # не трогаем capture pytest
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - exotic streams
        pass

ROOT = Path(__file__).resolve().parents[1]
PANEL_V4 = ROOT / "data" / "processed" / "akmola_panel_v4.csv"
PANEL_V3 = ROOT / "data" / "processed" / "akmola_panel_v3.csv"
PANEL_V2 = ROOT / "data" / "processed" / "akmola_panel.csv"
PANEL = (PANEL_V4 if PANEL_V4.exists()
         else PANEL_V3 if PANEL_V3.exists() else PANEL_V2)
MODELS = ROOT / "models"

# v3: 6 культур. Обучаем каждую, где достаточно строк (MIN_TRAIN_ROWS).
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
# Бэкап логики wheat/barley (v2): базовый набор сохранён без изменений.
BASE_FEATURES = CLIMATE_FEATURES + GEO_FEATURES + ["yield_lag1"]
# v3 extra (см. src/features_extra.py). ndvi_max/ndvi_flag — кандидаты только
# если есть покрытие на train (правило _usable_candidates; сейчас их нет —
# все реальные NDVI 2024 года, честно исключаются).
EXTRA_FEATURES = [
    "precip_spring", "tmax_july", "dtr", "vpd_proxy", "spei_proxy",
    "year_trend", "yield_roll3",
]
# v4 (см. src/features_v4.py): площади stat.gov.kz, ГТК Селянинова
# (методология КазГидромет), SoilGrids-статика. Все — прошлое/статика, без утечек.
V4_FEATURES = [
    "oilseeds_area_ha", "sunflower_area_ha", "grain_area_ha",
    "oilseeds_share", "htc_mjja",
    "soil_N", "soil_pH", "soil_SOC", "soil_clay",
]
# NEW_DATA #1 (regime, см. features_v4.py): календарные фичи сдвига,
# идентифицируемые на train<=2020 (post2020-dummy сознательно исключён —
# константа на train, см. features_v4.py). Отбор — train-only SelectKBest.
REGIME_FEATURES = [
    "trend_sq", "trend_recent", "oilshare_trend",
]
OPTIONAL_NDVI = ["ndvi_max", "ndvi_flag"]
CANDIDATE_FEATURES = (BASE_FEATURES + EXTRA_FEATURES + V4_FEATURES
                      + REGIME_FEATURES + OPTIONAL_NDVI)
TARGET = "yield_c_ha"

SELECT_K = 10  # per-crop top-K по SelectKBest(f_regression) на train
BLEND_W_LGBM = 0.7  # дефолт бленда LightGBM+Ridge (переопределяется per-crop ниже)
BLEND_W_RIDGE = 0.3
# Кандидаты весов per-crop: выбор ТОЛЬКО по train-CV (TimeSeriesSplit на <=2020),
# hold-out 2021-2025 в выборе не участвует — подглядывания нет.
WEIGHT_OPTIONS = [(0.7, 0.3), (0.5, 0.5), (0.3, 0.7)]
RIDGE_ALPHA = 1.0

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

# Backward-compat alias (wheat/barley без отбора используют именно его)
FEATURES = BASE_FEATURES


def blend_predict(bundle: dict, X) -> np.ndarray:
    """0.7*LGBM + 0.3*Ridge; если ridge нет (старый бандл) — чистый LGBM."""
    lgbm_pred = np.asarray(bundle["model"].predict(X), dtype=float)
    ridge = bundle.get("ridge_model")
    if ridge is None:
        return lgbm_pred
    w = bundle.get("blend_weights", {"lgbm": BLEND_W_LGBM, "ridge": BLEND_W_RIDGE})
    X_df = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X)
    ridge_pred = np.asarray(ridge.predict(X_df), dtype=float)
    return float(w.get("lgbm", BLEND_W_LGBM)) * lgbm_pred \
        + float(w.get("ridge", BLEND_W_RIDGE)) * ridge_pred


def load_panel() -> pd.DataFrame:
    if not PANEL.exists():
        raise FileNotFoundError(f"Нет панели данных: {PANEL}")
    print(f"[train] панель: {PANEL.name}")
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
    # yield_roll3 уже посчитан в features_extra.py (строго прошлое); если панели
    # v2 без него — пересчитать той же формулой (shift(1).rolling(3)) как fallback
    if "yield_roll3" not in df.columns:
        df["yield_roll3"] = (
            df.groupby(["district_en", "crop"])[TARGET]
            .transform(lambda s: s.shift(1).rolling(3, min_periods=3).mean())
        )
        print("[train] yield_roll3 пересчитан локально (панель v2, та же формула).")
    return df


def baseline_pred(series: pd.Series, window: int = BASELINE_WINDOW) -> pd.Series:
    """Среднее пред. `window` лет. Ожидает серию, отсортированную по году."""
    return series.shift(1).rolling(window, min_periods=window).mean()


def make_model() -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(**LGBM_PARAMS)


def make_ridge() -> Pipeline:
    # median-impute (только train-медианы) + scaler: Ridge устойчив на n~130
    return Pipeline([
        ("imp", SimpleImputer(strategy="median")),
        ("sc", StandardScaler()),
        ("rg", Ridge(alpha=RIDGE_ALPHA)),
    ])


def _usable_candidates(df_train: pd.DataFrame) -> list[str]:
    """Кандидаты без дыр: >30% NaN или <2 уникальных на train — исключаем.

    Сюда честно попадают ndvi_max/ndvi_flag: все 5 реальных NDVI — 2024 год
    (hold-out), на train<=2020 только NaN/нули без сигнала. Если NDVI-бэкфилл
    появится — колонки подхватятся автоматически.
    """
    usable = []
    for c in CANDIDATE_FEATURES:
        if c not in df_train.columns:
            continue
        s = df_train[c]
        if s.isna().mean() > 0.30:
            print(f"  [select] {c}: пропуск (NaN {s.isna().mean():.0%} на train)")
            continue
        if s.nunique(dropna=True) < 2:
            print(f"  [select] {c}: пропуск (константа на train)")
            continue
        usable.append(c)
    return usable


def select_features(df_train: pd.DataFrame, crop: str) -> tuple[list[str], dict]:
    """Per-crop SelectKBest(f_regression, k=10) на train + year_trend принудительно."""
    usable = _usable_candidates(df_train)
    need_rows = df_train.dropna(subset=["yield_lag1", *usable])
    if len(need_rows) < MIN_TRAIN_ROWS:
        raise ValueError(f"[{crop}] мало train-строк для отбора: "
                         f"{len(need_rows)} < {MIN_TRAIN_ROWS}")
    X = need_rows[usable]
    # импутация медианой ТОЛЬКО для скоринга отбора (модели импутят сами)
    med = X.median()
    Xi = X.fillna(med)
    k = min(SELECT_K, len(usable))
    kb = SelectKBest(f_regression, k=k).fit(Xi.to_numpy(), need_rows[TARGET].to_numpy())
    sel = [usable[i] for i in kb.get_support(indices=True)]
    scores = {c: float(s) for c, s in zip(usable, kb.scores_)}
    forced = False
    if "year_trend" in usable and "year_trend" not in sel:
        # структурный сдвиг масличных обязаны ловить: меняем худшую на year_trend
        order = sorted(sel, key=lambda c: scores.get(c, float("nan")))
        sel = [c for c in sel if c != order[0]] + ["year_trend"]
        forced = True
    print(f"  [select] {crop}: top-{k} = {sel}" + (" (year_trend forced)" if forced else ""))
    meta = {"candidates": usable, "k": k, "scores": scores, "forced_year_trend": forced}
    return sel, meta


def _fit_pair(X: pd.DataFrame, y: pd.Series) -> tuple:
    lgbm = make_model()
    lgbm.fit(X.to_numpy(), y.to_numpy())
    ridge = make_ridge()
    ridge.fit(X, y)
    return lgbm, ridge


def select_blend_weights(X: pd.DataFrame, y: np.ndarray, crop: str) -> dict:
    """Per-crop веса бленда по train-CV (TimeSeriesSplit, только train<=2020).

    Честно: hold-out 2021-2025 не видит выбор. При равенстве — ближе к 0.7/0.3.
    """
    from sklearn.model_selection import TimeSeriesSplit as _TSS

    tss = _TSS(n_splits=5)
    oof_lgbm = np.full_like(y, np.nan, dtype=float)
    oof_ridge = np.full_like(y, np.nan, dtype=float)
    for tr, te in tss.split(X):
        lgbm, ridge = _fit_pair(X.iloc[tr], pd.Series(y[tr]))
        oof_lgbm[te] = np.asarray(lgbm.predict(X.iloc[te].to_numpy()), dtype=float)
        oof_ridge[te] = np.asarray(ridge.predict(X.iloc[te]), dtype=float)
    mask = ~(np.isnan(oof_lgbm) | np.isnan(oof_ridge))
    best, best_mae = {"lgbm": BLEND_W_LGBM, "ridge": BLEND_W_RIDGE}, float("inf")
    for wl, wr in WEIGHT_OPTIONS:
        mae = float(mean_absolute_error(y[mask], wl * oof_lgbm[mask] + wr * oof_ridge[mask]))
        if mae < best_mae - 1e-9:
            best_mae, best = mae, {"lgbm": wl, "ridge": wr}
    print(f"  [weights] {crop}: train-CV OOF MAE -> {best} (mae={best_mae:.3f})")
    return best


def cv_report(df_crop: pd.DataFrame, crop: str, feats: list[str],
              weights: dict | None = None) -> tuple[np.ndarray, dict]:
    """TimeSeriesSplit(5) на train(<=2020) + expanding LOYO 2020-2025 для БЛЕНДА."""
    if weights is None:
        weights = {"lgbm": BLEND_W_LGBM, "ridge": BLEND_W_RIDGE}
    full = df_crop.dropna(subset=["yield_lag1", *feats]).reset_index(drop=True)
    train = full[full["year"] < HOLDOUT_FROM].reset_index(drop=True)
    if len(train) < MIN_TRAIN_ROWS:
        raise ValueError(f"[{crop}] мало train-строк для CV: {len(train)} < {MIN_TRAIN_ROWS}")
    X = train[feats]
    y = train[TARGET].to_numpy()

    tss = TimeSeriesSplit(n_splits=5)
    oof = np.full_like(y, np.nan, dtype=float)
    fold_rows = []
    for i, (tr, te) in enumerate(tss.split(X)):
        lgbm, ridge = _fit_pair(X.iloc[tr], pd.Series(y[tr]))
        b = {"model": lgbm, "ridge_model": ridge, "blend_weights": weights}
        p = blend_predict(b, X.iloc[te])
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
    print(f"[{crop}] TimeSeriesSplit(5) on <=2020 (blend): "
          f"OOF MAE={oof_mae:.3f} RMSE={oof_rmse:.3f}")
    for r in fold_rows:
        print(f"  fold {r['fold']}: n_train={r['n_train']} n_test={r['n_test']} "
              f"MAE={r['mae']:.3f} RMSE={r['rmse']:.3f}")

    # Expanding-window LOYO: тест года Y обучается только на годах < Y
    print(f"[{crop}] leave-one-year-out (expanding, no leakage, blend vs baseline):")
    loyo_rows = []
    for yr in LOYO_YEARS:
        tr = full[full["year"] < yr]
        te = full[full["year"] == yr]
        if tr.empty or te.empty:
            raise ValueError(f"[{crop}] LOYO год {yr}: пустой train ({len(tr)}) или test ({len(te)})")
        lgbm, ridge = _fit_pair(tr[feats], tr[TARGET])
        b = {"model": lgbm, "ridge_model": ridge, "blend_weights": weights}
        p = blend_predict(b, te[feats])
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
            "blend_mae": float(mean_absolute_error(yt, p)),
            "blend_rmse": float(np.sqrt(mean_squared_error(yt, p))),
            "bl_mae": float(mean_absolute_error(yt, bl["bl"].to_numpy())),
        }
        loyo_rows.append(row)
        print(f"  {yr}: BLEND MAE={row['blend_mae']:.3f} RMSE={row['blend_rmse']:.3f} | BL MAE={row['bl_mae']:.3f}")
    resid_std = float(np.nanstd(y[oof_mask] - oof[oof_mask]))
    return oof, {"folds": fold_rows, "loyo": loyo_rows, "resid_std_oof": resid_std}


def train_crop(df_crop: pd.DataFrame, crop: str) -> dict:
    df_train = df_crop[df_crop["year"] < HOLDOUT_FROM].reset_index(drop=True)
    feats, sel_meta = select_features(df_train, crop)
    train = df_crop[(df_crop["year"] < HOLDOUT_FROM)].dropna(subset=["yield_lag1", *feats])
    X = train[feats]
    y = train[TARGET]
    weights = select_blend_weights(X, y.to_numpy(), crop)
    cv_report(df_crop, crop, feats, weights)
    lgbm, ridge = _fit_pair(X, y)
    # ширина интервала: std OOF-остатков БЛЕНДА (честная, из CV, с per-crop весами)
    tss = TimeSeriesSplit(n_splits=5)
    oof = np.full(len(train), np.nan)
    Xa, ya = X, y.to_numpy()
    for tr, te in tss.split(Xa):
        lgbm_f, ridge_f = _fit_pair(Xa.iloc[tr], pd.Series(ya[tr]))
        b = {"model": lgbm_f, "ridge_model": ridge_f, "blend_weights": weights}
        oof[te] = blend_predict(b, Xa.iloc[te])
    resid_std = float(np.nanstd(ya - oof))
    bundle = {
        "model": lgbm,  # LGBM-компонент (TreeExplainer/SHAP-совместимость)
        "ridge_model": ridge,  # Ridge-компонент бленда
        "blend_weights": weights,
        "model_kind": f"blend_lgbm_ridge_{int(weights['lgbm']*100)}_{int(weights['ridge']*100)}",
        "features": feats,
        "feature_selection": sel_meta,
        "target": TARGET,
        "target_transform": None,  # таргет без преобразований (требование v3)
        "crop": crop,
        "residual_std": resid_std,
        "train_years": [int(train["year"].min()), int(train["year"].max())],
        "n_train": int(len(train)),
        "baseline_window": BASELINE_WINDOW,
        "lgbm_params": LGBM_PARAMS,
        "ridge_alpha": RIDGE_ALPHA,
        "panel": PANEL.name,
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
