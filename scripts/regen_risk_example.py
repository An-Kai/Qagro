"""regen_risk_example.py — обновить МОДЕЛЬНЫЕ записи reports/risk_example.json.

Проблема: insurance/predict-записи протухают при каждом переобучении
(y_pred зависит от бандлов). *_risk — погодные снапшоты, их НЕ трогаем.
dry_scenario_demo — статичное демо правила, НЕ трогаем.

Что обновляет: Esil/Zerenda_insurance_wheat, Esil_insurance_6crops,
Esil/Zerenda_recommend_{ru,kz,en} + meta.generated_*. Всё — текущим кодом
(src.insurance / src.recommend), сценарий — нейтральный MJJA 2016–2025
(внутри insurance_quote, как раньше).

Запуск: python scripts/regen_risk_example.py
После: обновить якоря 1558/150 в README/SUBMISSION/demo_script/
presentation_outline на свежие expected_payout_ha из файла.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.insurance import insurance_quote  # noqa: E402
from src.recommend import recommend_sowing  # noqa: E402

OUT = ROOT / "reports" / "risk_example.json"
CROPS_6 = ("spring_wheat", "barley", "oats", "sunflower", "rapeseed", "flax")


def main() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    data["Esil_insurance_wheat"] = insurance_quote("Esil", "spring_wheat")
    data["Zerenda_insurance_wheat"] = insurance_quote("Zerenda", "spring_wheat")
    six = {}
    for c in CROPS_6:
        try:
            six[c] = insurance_quote("Esil", c)
        except Exception as e:
            six[c] = {"crop": c, "error": f"{type(e).__name__}: {e}"}
    data["Esil_insurance_6crops"] = six
    for d in ("Esil", "Zerenda"):
        for lang in ("ru", "kz", "en"):
            data[f"{d}_recommend_{lang}"] = recommend_sowing(
                d, "spring_wheat", lang)
    meta = data.get("meta") or {}
    meta["generated_at"] = datetime.now(timezone.utc).isoformat()
    meta["generated_by"] = "scripts/regen_risk_example.py (model entries only)"
    data["meta"] = meta
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    ew = data["Esil_insurance_wheat"]
    zw = data["Zerenda_insurance_wheat"]
    print(f"Esil wheat: y_pred={ew['y_pred_c_ha']} p_loss={ew['p_loss']} "
          f"payout={ew['expected_payout_ha']}")
    print(f"Zerenda wheat: y_pred={zw['y_pred_c_ha']} p_loss={zw['p_loss']} "
          f"payout={zw['expected_payout_ha']}")
    print(f"saved {OUT}")


if __name__ == "__main__":
    main()
