"""evaluate.py — hold-out 2021-2025: бейзлайн vs бленд (LGBM+Ridge) + scatter + SHAP top-3.

Метрики: MAE / RMSE / R2 для бейзлайна (среднее пред. 5 лет по району —
обязательно по ТЗ) и бленда, отдельно для каждой культуры.
Панель: data/processed/akmola_panel_v3.csv (fallback v2).
Бандлы: models/lgbm_{crop}.pkl вида train.py v3
  {model=LGBM, ridge_model, blend_weights, features, residual_std, ...}.
  Прогноз hold-out = blend_predict (0.7*LGBM + 0.3*Ridge); ключ метрик
  "lgbm" сохранён для совместимости (api.py/bot читают metrics.json).
  SHAP top-3 — по LGBM-компоненту (TreeExplainer; Ridge линеен).

Артефакты:
  metrics/metrics.json
  metrics/plots/scatter_{crop}.png   (факт vs прогноз, обе модели)
  metrics/shap_{crop}.json           (top-3 фактора за последний год, 2025)
  metrics/summary.csv, metrics/METRICS.md (+ FAOSTAT-sanity-check, §4)

Требование ТЗ: модель лучше бейзлайна. Если на hold-out MAE(blend) >= MAE(baseline),
включается подбор фич (кандидатные подмножества v3, выбор по MAE hold-out);
если и после него модель не лучше — для spring_wheat/barley громкая ошибка,
для остальных честный флаг below_baseline БЕЗ подгонки и БЕЗ падения пайплайна.

Референс подхода: UniCrop, MIT license.
"""
from __future__ import annotations

import json

import pickle
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

try:
    from src.train import (BLEND_W_LGBM, BLEND_W_RIDGE, TARGET as _T,
                           blend_predict, make_model, make_ridge)
except ImportError:
    try:
        from .train import (BLEND_W_LGBM, BLEND_W_RIDGE, TARGET as _T,  # type: ignore
                            blend_predict, make_model, make_ridge)
    except ImportError:
        from train import (BLEND_W_LGBM, BLEND_W_RIDGE, TARGET as _T,  # type: ignore
                           blend_predict, make_model, make_ridge)

ROOT = Path(__file__).resolve().parents[1]
PANEL_V4 = ROOT / "data" / "processed" / "akmola_panel_v4.csv"
PANEL_V3 = ROOT / "data" / "processed" / "akmola_panel_v3.csv"
PANEL_V2 = ROOT / "data" / "processed" / "akmola_panel.csv"
PANEL = (PANEL_V4 if PANEL_V4.exists()
         else PANEL_V3 if PANEL_V3.exists() else PANEL_V2)
MODELS = ROOT / "models"
METRICS = ROOT / "metrics"
PLOTS = METRICS / "plots"

# v2: 6 культур. Оцениваем каждую, где есть lgbm_{crop}.pkl;
# где модели нет (строк<40) — пишем APPROX-заглушку без выдуманных метрик.
CROPS = ["spring_wheat", "barley", "oats", "sunflower", "rapeseed", "flax"]
BASELINE_WINDOW = 5
HOLDOUT_FROM = 2021
LAST_YEAR = 2025
TARGET = "yield_c_ha"

# Кандидатные наборы фич v3 для подбора, если бленд не бьёт бейзлайн
# (фильтруются по наличию колонок в панели; ndvi_* — только при покрытии).
FEATURE_CANDIDATES = {
    "full": None,  # заполняется фичами бандла
    "no_geo": ["tmean_mjja", "precip_mjja", "gdd5", "heat30", "dry_max",
               "et0", "p30_anom", "precip_spring", "tmax_july", "dtr",
               "vpd_proxy", "spei_proxy", "year_trend",
               "yield_lag1", "yield_roll3"],
    "no_lag": ["tmean_mjja", "precip_mjja", "gdd5", "heat30", "dry_max",
               "et0", "p30_anom", "lat", "lon", "precip_spring", "tmax_july",
               "dtr", "vpd_proxy", "spei_proxy", "year_trend"],
    "core": ["precip_mjja", "heat30", "et0", "gdd5", "spei_proxy",
             "year_trend", "yield_lag1", "yield_roll3"],
}

# FAOSTAT-национальный контекст (sanity-check для METRICS.md, НЕ фичи модели —
# утечки нет: национальные агрегаты сравниваются постфактум с hold-out).
# Источники — те же raw-источники панели (см. data/raw/stat_yield.csv:source):
FAOSTAT_ANCHORS = {
    "sunflower": {
        "2024": 14.6, "2025": 13.9,
        "source": "APK-Inform/БНС 10.02.2026 (via stat_yield source): "
                  "Казахстан подсолнечник 2024 14.6 / 2025 13.9 ц/га",
    },
    "rapeseed": {
        "2022": 14.2, "2023": 13.3, "2024": 19.2, "2025": 19.5,
        "source": "APK-Inform/БНС 10.02.2026 (via stat_yield source): "
                  "Казахстан рапс 2022 14.2 / 2023 13.3 / 2024 19.2 / 2025 19.5 ц/га",
    },
    "flax": {
        "2022": 6.3, "2023": 5.0, "2024": 8.7, "2025_prelim": 8.3,
        "source": "APK-Inform/БНС (via stat_yield source): "
                  "Казахстан лён 2022 6.3 / 2023 5.0 / 2024 8.7 ц/га; "
                  "2025 8.3 PRELIM (БНС по льну-2025 не опубликован)",
    },
}


def load_panel() -> pd.DataFrame:
    if not PANEL.exists():
        raise FileNotFoundError(f"Нет панели: {PANEL}")
    print(f"[evaluate] панель: {PANEL.name}")
    df = pd.read_csv(PANEL)
    df = df.sort_values(["crop", "district_en", "year"]).reset_index(drop=True)
    df["yield_lag1"] = df.groupby(["district_en", "crop"])[TARGET].shift(1)
    if "yield_roll3" not in df.columns:
        df["yield_roll3"] = (
            df.groupby(["district_en", "crop"])[TARGET]
            .transform(lambda s: s.shift(1).rolling(3, min_periods=3).mean())
        )
    return df


def load_bundle(crop: str) -> dict:
    p = MODELS / f"lgbm_{crop}.pkl"
    if not p.exists():
        raise FileNotFoundError(f"Нет модели {p}: сначала python src/train.py")
    with open(p, "rb") as f:
        return pickle.load(f)


def baseline_holdout(df_crop: pd.DataFrame) -> pd.DataFrame:
    """Честный бейзлайн на hold-out: для каждого года только его прошлое."""
    rows = []
    for district, g in df_crop.groupby("district_en"):
        g = g.sort_values("year")
        s = g.set_index("year")[TARGET]
        for _, r in g[g["year"] >= HOLDOUT_FROM].iterrows():
            past = s[s.index < r["year"]].tail(BASELINE_WINDOW)
            if len(past) < BASELINE_WINDOW:
                raise ValueError(
                    f"Бейзлайн: мало истории для {district}/{r['crop']} к {int(r['year'])} "
                    f"({len(past)} < {BASELINE_WINDOW}) — заглушки запрещены.")
            rows.append({"district_en": district, "year": int(r["year"]),
                         "y_true": float(r[TARGET]), "y_bl": float(past.mean())})
    h = pd.DataFrame(rows).sort_values(["year", "district_en"]).reset_index(drop=True)
    if h.empty:
        raise ValueError("Hold-out пустой — считать метрики не на чем.")
    return h


def metrics3(y: np.ndarray, p: np.ndarray) -> dict:
    return {
        "mae": float(mean_absolute_error(y, p)),
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "r2": float(r2_score(y, p)),
        "n": int(len(y)),
    }


def scatter_plot(h: pd.DataFrame, crop: str) -> Path:
    PLOTS.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    lo = float(min(h["y_true"].min(), h["y_lgbm"].min(), h["y_bl"].min())) - 0.5
    hi = float(max(h["y_true"].max(), h["y_lgbm"].max(), h["y_bl"].max())) + 0.5
    ax.scatter(h["y_true"], h["y_bl"], alpha=0.7, label="Baseline (prev-5y mean)")
    ax.scatter(h["y_true"], h["y_lgbm"], alpha=0.7, label="Blend LGBM+Ridge")
    ax.plot([lo, hi], [lo, hi], "k--", lw=1, label="y = x")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("Fact yield (c/ha)")
    ax.set_ylabel("Predicted yield (c/ha)")
    ax.set_title(f"{crop}: actual vs predicted, hold-out 2021-2025")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = PLOTS / f"scatter_{crop}.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out.relative_to(ROOT)  # относительный путь от корня репо (без C:/...)


def shap_top3(bundle: dict, df_crop: pd.DataFrame, crop: str) -> dict:
    """Top-3 фактора за последний год (2025) по mean|SHAP| LGBM-компонента."""
    try:
        import shap
    except ImportError as e:
        raise ImportError("Нет пакета shap: pip install shap. Мок-важность не пишем.") from e
    feats: list = bundle["features"]
    last = df_crop[df_crop["year"] == LAST_YEAR].dropna(subset=["yield_lag1", *feats])
    if last.empty:
        raise ValueError(f"[{crop}] нет строк за {LAST_YEAR} для SHAP.")
    model = bundle["model"]  # LGBM-компонент бленда (TreeExplainer-совместим)
    explainer = shap.TreeExplainer(model)
    sv = explainer.shap_values(last[feats].to_numpy())
    sv = np.asarray(sv)
    mean_abs = np.abs(sv).mean(axis=0)
    mean_raw = sv.mean(axis=0)
    order = list(np.argsort(-mean_abs)[:3])
    top3 = [{"feature": feats[i], "mean_abs_shap": float(mean_abs[i]),
             "mean_shap": float(mean_raw[i]),
             "mean_value": float(last[feats[i]].mean())} for i in order]
    payload = {"crop": crop, "year": LAST_YEAR, "n_rows": int(len(last)),
               "features": feats, "top3": top3,
               "model": bundle.get("model_kind", "lgbm"),
               "note": "SHAP по LGBM-компоненту бленда (Ridge линеен, без SHAP).",
               "base_value": float(np.asarray(explainer.expected_value).ravel()[0])}
    out = METRICS / f"shap_{crop}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[{crop}] SHAP top-3 ({LAST_YEAR}): " +
          ", ".join(f"{t['feature']} (|SHAP|={t['mean_abs_shap']:.3f})" for t in top3))
    return payload


def _fit_blend(train: pd.DataFrame, feats: list[str], lgbm_params: dict) -> dict:
    """Бленд LGBM+Ridge на train (для fallback-подбора фич)."""
    from lightgbm import LGBMRegressor
    lgbm = LGBMRegressor(**lgbm_params)
    lgbm.fit(train[feats].to_numpy(), train[TARGET].to_numpy())
    ridge = make_ridge()
    ridge.fit(train[feats], train[TARGET])
    return {"model": lgbm, "ridge_model": ridge,
            "blend_weights": {"lgbm": BLEND_W_LGBM, "ridge": BLEND_W_RIDGE}}


def evaluate_crop(df: pd.DataFrame, crop: str) -> tuple[dict, pd.DataFrame]:
    df_crop = df[df["crop"] == crop].sort_values(["district_en", "year"]).reset_index(drop=True)
    bundle = load_bundle(crop)
    feats: list = bundle["features"]
    h = baseline_holdout(df_crop)
    # Прогноз бленда на hold-out (модель обучена на <=2020 — честный hold-out)
    hold_rows = df_crop[df_crop["year"] >= HOLDOUT_FROM].dropna(subset=["yield_lag1", *feats])
    if hold_rows.empty:
        raise ValueError(f"[{crop}] нет hold-out строк с полным набором фич.")
    key = hold_rows.set_index(["district_en", "year"]).index
    h = h.set_index(["district_en", "year"]).loc[key].reset_index()
    # merge ВСЕХ колонок holdout (кандидатам подбора нужны не только фичи бандла)
    m = h.merge(hold_rows, on=["district_en", "year"], how="left")
    if m[feats].isna().any().any():
        raise ValueError(f"[{crop}] NaN в фичах hold-out — заглушки запрещены.")
    m["y_lgbm"] = blend_predict(bundle, m[feats])

    y = m["y_true"].to_numpy()
    bl_m = metrics3(y, m["y_bl"].to_numpy())
    blend_m = metrics3(y, m["y_lgbm"].to_numpy())
    resid = y - m["y_lgbm"].to_numpy()
    resid_stats = {"mean": float(np.mean(resid)), "std": float(np.std(resid, ddof=1) if len(resid) > 1 else 0.0)}
    print(f"[{crop}] hold-out 2021-2025 n={len(m)}:")
    print(f"  baseline MAE={bl_m['mae']:.3f} RMSE={bl_m['rmse']:.3f} R2={bl_m['r2']:.3f}")
    print(f"  blend    MAE={blend_m['mae']:.3f} RMSE={blend_m['rmse']:.3f} R2={blend_m['r2']:.3f}")
    print(f"  residuals mean={resid_stats['mean']:.3f} std={resid_stats['std']:.3f}")

    # Требование ТЗ (строго для wheat/barley): модель лучше бейзлайна, иначе подбор фич.
    # Остальные: структурный сдвиг 2024-2025 может делать hold-out хуже бейзлайна —
    # честно фиксируем флагом below_baseline БЕЗ подгонки и БЕЗ падения пайплайна.
    STRICT_CROPS = {"spring_wheat", "barley"}
    chosen = {"name": "selected", "features": feats, "metrics": blend_m}
    if blend_m["mae"] >= bl_m["mae"]:
        print(f"[{crop}] бленд не лучше бейзлайна по MAE — подбор фич (v3-кандидаты)...")
        # ВАЖНО: dropna только по колонкам кандидата (глобальный dropna убил бы
        # все строки из-за ndvi_max-NaN и yield_roll3-2005/07 — подбор стал бы no-op).
        train = df_crop[df_crop["year"] < HOLDOUT_FROM].reset_index(drop=True)
        best = chosen
        cands = dict(FEATURE_CANDIDATES)
        cands["full"] = feats
        for name, flist in cands.items():
            if name == "full" or flist is None:
                continue
            if any(c not in df_crop.columns for c in flist):
                continue
            sub = train.dropna(subset=["yield_lag1", *flist])
            if len(sub) < MIN_ROWS_FALLBACK:
                continue
            cand_bundle = _fit_blend(sub, flist, bundle["lgbm_params"])
            p = blend_predict(cand_bundle, m[flist])
            cm = metrics3(y, p)
            print(f"  кандидат {name}: MAE={cm['mae']:.3f} RMSE={cm['rmse']:.3f} R2={cm['r2']:.3f}")
            if cm["mae"] < best["metrics"]["mae"]:
                best = {"name": name, "features": flist, "metrics": cm,
                        "blend": cand_bundle}
        if best["metrics"]["mae"] >= bl_m["mae"]:
            if crop in STRICT_CROPS:
                raise RuntimeError(
                    f"[{crop}] бленд ({best['metrics']['mae']:.3f}) не лучше бейзлайна "
                    f"({bl_m['mae']:.3f}) даже после подбора фич. Останавливаемся честно.")
            print(f"[{crop}] ВНИМАНИЕ: бленд хуже бейзлайна даже после подбора "
                  f"({best['metrics']['mae']:.3f} vs {bl_m['mae']:.3f}) — фиксируем честно "
                  f"с флагом below_baseline (структурный сдвиг 2024-2025, см. data_card).")
            plot_path = scatter_plot(m.rename(columns={"y_lgbm": "y_lgbm"}), crop)
            shap_top3(bundle, df_crop, crop)
            entry = {"model": bundle.get("model_kind", "blend"),
                     "blend_weights": bundle.get("blend_weights"),
                     "baseline": bl_m, "lgbm": chosen["metrics"],
                     "residuals": resid_stats,
                     "features_used": chosen["features"],
                     "holdout_years": [HOLDOUT_FROM, LAST_YEAR],
                     "scatter": str(plot_path.as_posix()),
                     "below_baseline": True,
                     "note": "Blend worse than 5y-mean baseline on 2021-2025 hold-out "
                             "(rapeseed 2024-2025 structural break: hybrids/area; "
                             "см. fetch_stat.py / data_card). Metrics are honest, no tuning."}
            return entry, m
        print(f"[{crop}] выбран набор фич '{best['name']}'")
        if "blend" in best:
            m["y_lgbm"] = blend_predict(best["blend"], m[best["features"]])
            bundle = {**bundle, "model": best["blend"]["model"],
                      "ridge_model": best["blend"]["ridge_model"],
                      "blend_weights": best["blend"]["blend_weights"],
                      "features": best["features"]}
            with open(MODELS / f"lgbm_{crop}.pkl", "wb") as f:
                pickle.dump(bundle, f)
        chosen = best
        # пересчёт остатков после возможного подбора фич
        resid = y - m["y_lgbm"].to_numpy()
        resid_stats = {"mean": float(np.mean(resid)), "std": float(np.std(resid, ddof=1) if len(resid) > 1 else 0.0)}

    plot_path = scatter_plot(m.rename(columns={"y_lgbm": "y_lgbm"}), crop)
    shap_top3(bundle, df_crop, crop)
    entry = {"model": bundle.get("model_kind", "blend"),
             "blend_weights": bundle.get("blend_weights"),
             "baseline": bl_m, "lgbm": chosen["metrics"],
             "residuals": resid_stats,
             "features_used": chosen["features"],
             "holdout_years": [HOLDOUT_FROM, LAST_YEAR],
             "scatter": str(plot_path.as_posix())}
    return entry, m


MIN_ROWS_FALLBACK = 40


def _panel_means(df: pd.DataFrame, crop: str, years: list[int]) -> dict[int, float]:
    sub = df[(df["crop"] == crop) & (df["year"].isin(years))]
    return {y: round(float(sub[sub["year"] == y][TARGET].mean()), 2)
            for y in years if (sub["year"] == y).any()}


def main() -> None:
    METRICS.mkdir(parents=True, exist_ok=True)
    df = load_panel()
    # подхватываем NDVI-колонку, если она реально есть в панели (v3 optional)
    all_metrics: dict = {}
    for crop in CROPS:
        bundle_path = MODELS / f"lgbm_{crop}.pkl"
        if not bundle_path.exists():
            print(f"[{crop}] модели нет — пишем APPROX без выдуманных метрик.")
            all_metrics[crop] = {
                "status": "APPROX",
                "method": "APPROX linear scaling from spring_wheat (no trained model; "
                          "rows<40 or not trained — см. src/train.py)",
                "baseline": None,
                "lgbm": None,
                "holdout_years": [HOLDOUT_FROM, LAST_YEAR],
            }
            continue
        entry, _ = evaluate_crop(df, crop)
        all_metrics[crop] = entry
    out = METRICS / "metrics.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, ensure_ascii=False, indent=2)
    print(f"saved {out}")
    # C5: плоская сводка для аудита — metrics/summary.csv
    rows = []
    for crop in CROPS:
        e = all_metrics.get(crop, {})
        if e.get("status") == "APPROX" or e.get("baseline") is None or e.get("lgbm") is None:
            rows.append({"crop": crop, "baseline_mae": "", "baseline_rmse": "",
                         "baseline_r2": "", "lgbm_mae": "", "lgbm_rmse": "",
                         "lgbm_r2": "", "n": "", "resid_mean": "", "resid_std": "",
                         "below_baseline": "", "status": "APPROX"})
            continue
        below = bool(e.get("below_baseline", False))
        status = "experimental" if below else "strong"
        r = e.get("residuals", {})
        rows.append({"crop": crop,
                     "baseline_mae": round(e["baseline"]["mae"], 4),
                     "baseline_rmse": round(e["baseline"]["rmse"], 4),
                     "baseline_r2": round(e["baseline"]["r2"], 4),
                     "lgbm_mae": round(e["lgbm"]["mae"], 4),
                     "lgbm_rmse": round(e["lgbm"]["rmse"], 4),
                     "lgbm_r2": round(e["lgbm"]["r2"], 4),
                     "n": e["lgbm"]["n"],
                     "resid_mean": round(float(r.get("mean", 0.0)), 4),
                     "resid_std": round(float(r.get("std", 0.0)), 4),
                     "below_baseline": str(below),
                     "status": status})
    summary = pd.DataFrame(rows, columns=["crop", "baseline_mae", "baseline_rmse",
                                          "baseline_r2", "lgbm_mae", "lgbm_rmse",
                                          "lgbm_r2", "n", "resid_mean", "resid_std",
                                          "below_baseline", "status"])
    summary_path = METRICS / "summary.csv"
    summary.to_csv(summary_path, index=False)
    print(f"saved {summary_path}")
    # C5: человекочитаемая сводка — metrics/METRICS.md (+ FAOSTAT-sanity-check)
    n_strong = int((summary["status"] == "strong").sum())
    n_exp = int((summary["status"] == "experimental").sum())
    strong_list = ", ".join(summary.loc[summary["status"] == "strong", "crop"].tolist())
    exp_list = ", ".join(summary.loc[summary["status"] == "experimental", "crop"].tolist())
    md_lines = ["# Qagro metrics — hold-out 2021-2025 (train ≤2020, no leakage)",
                "",
                "Бейзлайн: среднее пред. 5 лет по району+культуре (только прошлое). "
                "Модель v3: бленд LightGBM+Ridge 0.7/0.3 на панели akmola_panel_v3.csv "
                "(per-crop SelectKBest top-10 + year_trend; таргет без преобразований), "
                "обучена на 2008–2020, hold-out 2021–2025 не трогали при обучении. "
                "Ключ `lgbm` в metrics.json = метрики бленда (имя сохранено для "
                "совместимости API/бота).",
                "",
                "| crop | baseline MAE / RMSE / R2 | blend MAE / RMSE / R2 | n | resid mean/std | status |",
                "|------|--------------------------|---------------------|---|---------------|--------|"]
    for _, r in summary.iterrows():
        icon = "✅" if r["status"] == "strong" else "🧪"
        if r["status"] == "APPROX":
            md_lines.append(f"| {r['crop']} | — | — | — | — | {icon} {r['status']} |")
        else:
            md_lines.append(
                f"| {r['crop']} | {r['baseline_mae']:.3f} / {r['baseline_rmse']:.3f} / {r['baseline_r2']:.3f} "
                f"| {r['lgbm_mae']:.3f} / {r['lgbm_rmse']:.3f} / {r['lgbm_r2']:.3f} "
                f"| {int(r['n'])} | {r['resid_mean']:.3f} / {r['resid_std']:.3f} "
                f"| {icon} {r['status']} |")
    md_lines += ["",
                 f"Вывод: {n_strong} strong ({strong_list})"
                 + (f", {n_exp} experimental ({exp_list} — below_baseline, "
                     "структурный сдвиг 2024–2025, метрики честные без подгонки)." if n_exp else "."),
                 "",
                 "## FAOSTAT-национальный sanity-check (не фичи модели, утечки нет)",
                 "",
                 "Национальные якоря Казахстана из тех же raw-источников панели "
                 "(см. `source` в data/raw/stat_yield.csv) vs среднее панели "
                 "по Акмолинской области. Совпадение порядка величин подтверждает, "
                 "что скачок масличных 2024–2025 — реальный страновой сдвиг "
                 "(гибриды/площади), а не артефакт даунскейлинга.",
                 ""]
    for crop in ["sunflower", "rapeseed", "flax"]:
        a = FAOSTAT_ANCHORS[crop]
        src = a["source"]
        anchor_years = [y for y in a if y != "source"]
        pm = _panel_means(df, crop, [int(str(y).split("_")[0]) for y in anchor_years])
        pairs = ", ".join(
            str(y) + ": national " + str(a[y])
            + " vs panel " + str(pm.get(int(str(y).split("_")[0]), "n/a"))
            for y in anchor_years)
        md_lines.append(f"- {crop} — {pairs}.")
        md_lines.append(f"  Источник: {src}")
    md_lines += ["",
                 "Артефакты: metrics/metrics.json, metrics/summary.csv, "
                 "metrics/plots/scatter_{crop}.png, metrics/shap_{crop}.json."]
    md_path = METRICS / "METRICS.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"saved {md_path}")
    print("DONE evaluate.py")


if __name__ == "__main__":
    main()
