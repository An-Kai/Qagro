"""economics.py — прибыль с гектара (Qagro v4).

Формулы:
  выручка   = урожайность_ц_га / 10 × цена_тг_т   (ц/га -> т/га)
  прибыль   = выручка − себестоимость_тг_га
  рентабельность% = прибыль / себестоимость × 100

ASSUMPTION: DEFAULT_COST_KZT_HA = 65000 тг/га — усреднённая себестоимость,
РЕДАКТИРУЕТСЯ под хозяйство (топливо, семена, СЗР, аренда, зарплата).
"""

from __future__ import annotations

# --- assumption (редактируется под хозяйство) ---
DEFAULT_COST_KZT_HA: float = 65000.0

EXPLAIN: dict[str, str] = {
    "ru": (
        "Выручка = урожай (ц/га) / 10 × цена (тг/т). "
        "Прибыль = выручка − себестоимость (по умолчанию 65000 тг/га, "
        "значение редактируется). Рентабельность = прибыль / себестоимость × 100%."
    ),
    "kz": (
        "Түсім = өнім (ц/га) / 10 × баға (тг/т). "
        "Пайда = түсім − өзіндік құн (әдепкі 65000 тг/га, "
        "шаруашылыққа қарай түзетіледі). Рентабельділік = пайда / өзіндік құн × 100%."
    ),
    "en": (
        "Revenue = yield (c/ha) / 10 × price (KZT/t). "
        "Profit = revenue − cost (default 65000 KZT/ha, editable). "
        "Profitability = profit / cost × 100%."
    ),
}


def profit_ha(
    y_pred_c_ha: float, price_kzt_t: float, cost_kzt_ha: float = DEFAULT_COST_KZT_HA
) -> dict:
    """Посчитать выручку, прибыль и рентабельность с гектара."""
    y = float(y_pred_c_ha)
    price = float(price_kzt_t)
    cost = float(cost_kzt_ha)
    if y < 0:
        raise ValueError("y_pred_c_ha must be >= 0")
    if price < 0:
        raise ValueError("price_kzt_t must be >= 0")
    if cost < 0:
        raise ValueError("cost_kzt_ha must be >= 0")
    revenue = round(y / 10.0 * price, 2)
    profit = round(revenue - cost, 2)
    profitability = round(profit / cost * 100.0, 2) if cost > 0 else 0.0
    return {
        "yield_c_ha": y,
        "price_kzt_t": price,
        "cost_kzt_ha": cost,
        "revenue_kzt_ha": revenue,
        "profit_kzt_ha": profit,
        "profitability_pct": profitability,
        "assumption": f"cost {cost:g} KZT/ha editable (default {DEFAULT_COST_KZT_HA:g})",
    }


__all__ = ["DEFAULT_COST_KZT_HA", "EXPLAIN", "profit_ha"]
