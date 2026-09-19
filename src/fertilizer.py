"""fertilizer.py — ориентировочный расчёт NPK под плановую урожайность (Qagro v4).

Нормы выноса NPK (кг действующего вещества на 1 ц продукции):
  пшеница 3.5/1.2/2.5, ячмень 3.0/1.1/2.2, овес 3.0/1.2/2.6,
  подсолнечник 5.0/2.0/8.0, рапс 5.5/2.5/5.0, лен 4.0/1.5/4.5.
Подпись источника: source="agro-norms" (ориентиры, НЕ лабораторный анализ).

Поправка на фон почвы: low x1.2 / medium x1.0 / high x0.8.
Без брендов удобрений. Точную дозу — только по агрохимобследованию поля.
"""

from __future__ import annotations

SOURCE = "agro-norms"

# (N, P, K) кг д.в. на 1 ц основной продукции
REMOVAL_NPK: dict[str, tuple[float, float, float]] = {
    "wheat": (3.5, 1.2, 2.5),
    "barley": (3.0, 1.1, 2.2),
    "oats": (3.0, 1.2, 2.6),
    "sunflower": (5.0, 2.0, 8.0),
    "rapeseed": (5.5, 2.5, 5.0),
    "flax": (4.0, 1.5, 4.5),
}

_CROP_ALIASES: dict[str, str] = {
    "wheat": "wheat",
    "spring_wheat": "wheat",
    "spring wheat": "wheat",
    "spring_barley": "barley",
    "spring barley": "barley",
    "пшеница": "wheat",
    "бидай": "wheat",
    "barley": "barley",
    "ячмень": "barley",
    "арпа": "barley",
    "oats": "oats",
    "oat": "oats",
    "овес": "oats",
    "овёс": "oats",
    "сұлы": "oats",
    "sunflower": "sunflower",
    "подсолнечник": "sunflower",
    "күнбағыс": "sunflower",
    "rapeseed": "rapeseed",
    "рапс": "rapeseed",
    " rape": "rapeseed",
    "flax": "flax",
    "лен": "flax",
    "лён": "flax",
    "зығыр": "flax",
}

_CROP_RU: dict[str, str] = {
    "wheat": "пшеницы",
    "barley": "ячменя",
    "oats": "овса",
    "sunflower": "подсолнечника",
    "rapeseed": "рапса",
    "flax": "льна",
}

_CROP_KZ: dict[str, str] = {
    "wheat": "бидай",
    "barley": "арпа",
    "oats": "сұлы",
    "sunflower": "күнбағыс",
    "rapeseed": "рапс",
    "flax": "зығыр",
}

_SOIL_ALIASES: dict[str, str] = {
    "low": "low",
    "низкий": "low",
    "низкая": "low",
    "төмен": "low",
    "medium": "medium",
    "средний": "medium",
    "средняя": "medium",
    "орташа": "medium",
    "high": "high",
    "высокий": "high",
    "высокая": "high",
    "жоғары": "high",
}

SOIL_FACTOR: dict[str, float] = {"low": 1.2, "medium": 1.0, "high": 0.8}


def calc_npk(
    crop: str, yield_goal_c_ha: float, soil_level: str = "medium"
) -> dict:
    """Рассчитать ориентировочную норму NPK (кг/га д.в.).

    Формула: норма_выноса(кг/ц) × цель(ц/га) × поправка_почвы.
    """
    key = (crop or "").strip().lower()
    key = _CROP_ALIASES.get(key, key)
    if key not in REMOVAL_NPK:
        raise ValueError(
            f"Unknown crop '{crop}'. Known: {sorted(REMOVAL_NPK)}"
        )
    if yield_goal_c_ha is None or float(yield_goal_c_ha) <= 0:
        raise ValueError("yield_goal_c_ha must be > 0")
    soil = _SOIL_ALIASES.get((soil_level or "").strip().lower(), None)
    if soil is None:
        raise ValueError(
            f"Unknown soil_level '{soil_level}'. Use low/medium/high"
        )
    factor = SOIL_FACTOR[soil]
    n_norm, p_norm, k_norm = REMOVAL_NPK[key]
    goal = float(yield_goal_c_ha)
    n = round(n_norm * goal * factor, 1)
    p = round(p_norm * goal * factor, 1)
    k = round(k_norm * goal * factor, 1)

    crop_ru = _CROP_RU[key]
    crop_kz = _CROP_KZ[key]
    return {
        "crop": key,
        "yield_goal_c_ha": goal,
        "soil_level": soil,
        "soil_factor": factor,
        "N_kg_ha": n,
        "P_kg_ha": p,
        "K_kg_ha": k,
        "source": SOURCE,
        "message_ru": (
            f"Для {crop_ru} при цели {goal:g} ц/га на фоне '{soil}' "
            f"(поправка ×{factor}): N ~{n} кг/га, P ~{p} кг/га, K ~{k} кг/га "
            f"(вынос на центнер × цель). Ориентиры {SOURCE}, "
            f"точную дозу — по агрохимобследованию поля. Без брендов."
        ),
        "message_kz": (
            f"{crop_kz.capitalize()} үшін {goal:g} ц/га мақсатта '{soil}' "
            f"фонында (түзету ×{factor}): N ~{n} кг/га, P ~{p} кг/га, "
            f"K ~{k} кг/га (центнерге шығару × мақсат). {SOURCE} бағдары, "
            f"нақты мөлшер — топырақ талдауы бойынша. Брендсіз."
        ),
        "message_en": (
            f"For {key} at {goal:g} c/ha target on '{soil}' background "
            f"(factor ×{factor}): N ~{n} kg/ha, P ~{p} kg/ha, K ~{k} kg/ha "
            f"(uptake per centner × target). {SOURCE} benchmarks, "
            f"confirm exact rate by soil test. No brands."
        ),
    }


__all__ = ["REMOVAL_NPK", "SOIL_FACTOR", "SOURCE", "calc_npk"]
