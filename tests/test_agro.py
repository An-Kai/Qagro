"""test_agro.py — проверки справочных модулей (без pytest-зависимости).

Запуск: python tests/test_agro.py
Проверки:
- lookup('wheat') >= 3
- calc_npk('wheat', 15) -> N ~52 (3.5 кг/ц × 15 ц)
- profit_ha(12, 95000) положительна
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.economics import profit_ha  # noqa: E402
from src.fertilizer import calc_npk  # noqa: E402
from src.guide_data import lookup  # noqa: E402

passed = []


def check(name: str, fn) -> None:
    fn()
    passed.append(name)
    print(f"PASS: {name}")


def t_lookup_wheat():
    items = lookup("wheat")
    assert isinstance(items, list), type(items)
    assert len(items) >= 3, f"lookup('wheat') вернул {len(items)}, нужно >= 3"
    for it in items:
        assert "names" in it and "ru" in it["names"], it.get("id")
        assert len(it["signs"]["ru"]) == 3, it.get("id")
        assert it["danger"] in (1, 2, 3), it.get("id")


def t_calc_npk_wheat15():
    r = calc_npk("wheat", 15)
    assert abs(r["N_kg_ha"] - 52.5) <= 2.0, r
    assert r["P_kg_ha"] > 0 and r["K_kg_ha"] > 0, r
    assert r["message_ru"] and r["message_kz"] and r["message_en"], r


def t_profit_positive():
    r = profit_ha(12, 95000)
    assert r["revenue_kzt_ha"] == 114000.0, r
    assert r["profit_kzt_ha"] > 0, r
    assert r["profitability_pct"] > 0, r


if __name__ == "__main__":
    check("lookup wheat>=3", t_lookup_wheat)
    check("calc_npk wheat 15ц N~52", t_calc_npk_wheat15)
    check("profit 12ц*95000 положительна", t_profit_positive)
    print(f"OK: {len(passed)}/3 — {', '.join(passed)}")
