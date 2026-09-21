"""verify.py — read-only проверка консистентности артефактов Qagro.

НЕ пишет ничего (в отличие от reproduce.*): только читает и сверяет.
Проверяет:
  1. required files (панель, модели, метрики, интервалы, NDVI, поля, конфиг);
  2. bundle features in panel columns; таргет без NaN;
  3. below_baseline-флаги соответствуют multi-metric gate (G1 MAE + G2 R²>0),
     пересчитанному из metrics.json (политика, не подгонка);
  4. intervals.json: культуры совпадают, coverage в [0,1];
  5. ndvi_timeseries.json валиден; считает real/MISSING;
  6. risk_example anchors: свежий insurance_quote == файлу (иначе
     scripts/regen_risk_example.py);
  7. .env не в git-индексе (секрет не утёк в сдачу).

Запуск: python scripts/verify.py
Выход: 0 + VERIFY OK, иначе 1 + первая причина.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}: {name}" + (f" - {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _fix_console() -> None:
    try:
        import sys

        if getattr(sys.stdout, "encoding", "utf-8").lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:
        pass


def main() -> int:
    _fix_console()
    import pandas as pd

    # 1. файлы
    required = [
        "data/processed/akmola_panel_v4.csv", "config/districts.yaml",
        "data/fields/akmola_osm_fields.geojson", "data/fields/granaries.json",
        "data/processed/soil.csv", "data/ndvi/ndvi_timeseries.json",
        "metrics/metrics.json", "metrics/intervals.json", "metrics/conformal.json",
        "reports/risk_example.json",
    ]
    for rel in required:
        check(f"exists {rel}", (ROOT / rel).exists())
    for crop in ("spring_wheat", "barley", "oats", "sunflower", "rapeseed", "flax"):
        check(f"exists models/lgbm_{crop}.pkl", (ROOT / "models" / f"lgbm_{crop}.pkl").exists())
    check("exists models/baseline.json", (ROOT / "models" / "baseline.json").exists())
    if FAILS:
        print(f"VERIFY FAIL ({len(FAILS)}): missing files first")
        return 1

    # 2. панель vs бандлы
    import pickle

    df = pd.read_csv(ROOT / "data/processed/akmola_panel_v4.csv")
    check("panel shape 1260 rows", len(df) == 1260, f"got {len(df)}")
    check("yield NaN=0", int(df["yield_c_ha"].isna().sum()) == 0)
    bundles = {}
    for crop in ("spring_wheat", "barley", "oats", "sunflower", "rapeseed", "flax"):
        with open(ROOT / "models" / f"lgbm_{crop}.pkl", "rb") as f:
            bundles[crop] = pickle.load(f)
    # yield_lag1/yield_roll3 вычисляются в runtime через shift(1) внутри
    # (district, crop) — см. train.load_panel; в CSV их может не быть.
    RUNTIME_FEATS = {"yield_lag1", "yield_roll3"}
    for crop, b in bundles.items():
        missing = [c for c in b["features"]
                   if c not in df.columns and c not in RUNTIME_FEATS]
        check(f"bundle {crop} features-in-panel", not missing, f"missing {missing}")

    # 3. gate из metrics.json (G1 MAE + G2 R²>0) == флаги
    m = json.loads((ROOT / "metrics" / "metrics.json").read_text(encoding="utf-8"))
    for crop, v in m.items():
        if not isinstance(v, dict) or "lgbm" not in v:
            continue
        bl, lb = v["baseline"], v["lgbm"]
        expect_flag = bool(lb["mae"] >= bl["mae"] or not lb["r2"] > 0.0)
        got_flag = v.get("below_baseline") is True
        check(f"gate {crop} flag={got_flag}", expect_flag == got_flag,
              f"MAE {lb['mae']:.3f} vs {bl['mae']:.3f}, R2 {lb['r2']:.3f}")

    # 4. intervals
    iv = json.loads((ROOT / "metrics" / "intervals.json").read_text(encoding="utf-8"))
    check("intervals crops match", set(iv) == {c for c in m if isinstance(m[c], dict)},
          f"{sorted(iv)}")
    for crop, v in iv.items():
        cov = v.get("conformal_coverage")
        check(f"coverage {crop} in [0,1]",
              isinstance(cov, (int, float)) and 0.0 <= cov <= 1.0, f"{cov}")

    # 5. NDVI
    nd = json.loads((ROOT / "data/ndvi/ndvi_timeseries.json").read_text(encoding="utf-8"))
    items = nd if isinstance(nd, list) else nd.get("items", nd)
    real = [x for x in items if isinstance((x or {}).get("ndvi_mean"), (int, float))]
    bad = [x for x in real if not -1.0 <= float(x["ndvi_mean"]) <= 1.0 or not x.get("scene_id")]
    check("ndvi valid", not bad, f"{len(bad)} bad")
    print(f"INFO: ndvi total={len(items)} real={len(real)} "
          f"districts={len({x.get('district') for x in real})}")

    # 6. risk_example anchors свежие (пересчёт текущим кодом)
    from src.insurance import insurance_quote

    ex = json.loads((ROOT / "reports" / "risk_example.json").read_text(encoding="utf-8"))
    for d in ("Esil", "Zerenda"):
        fresh = insurance_quote(d, "spring_wheat")
        filed = ex.get(f"{d}_insurance_wheat", {})
        same = (abs(float(fresh["y_pred_c_ha"]) - float(filed.get("y_pred_c_ha", -1))) < 1e-9
                and abs(float(fresh["expected_payout_ha"]) - float(filed.get("expected_payout_ha", -1))) < 1e-9)
        check(f"anchor {d}/wheat fresh", same,
              "run scripts/regen_risk_example.py then rebuild PDF if needed")

    # 7. .env не в индексе
    r = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=str(ROOT))
    tracked = r.stdout.split() if r.returncode == 0 else []
    check(".env not tracked", ".env" not in tracked)

    if FAILS:
        print(f"VERIFY FAIL: {len(FAILS)} — {FAILS}")
        return 1
    print("VERIFY OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
