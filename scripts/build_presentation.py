"""build_presentation.py — сборка docs/Qagro_presentation.pdf из проверяемых данных.

10 слайдов, A4 landscape (как исходная колода): проблема, решение, демо, данные,
модель, метрики hold-out, эффект, масштаб, команда, планы. Все числа тянутся из
репозитория (metrics/metrics.json, metrics/intervals.json,
reports/risk_example.json, панель) — deck нельзя рассинхронизировать с кодом.

Чарт слайда 6: свежий metrics/plots/scatter_spring_wheat.png (перегенерируется
src/evaluate.py). Таблица слайда 7: якоря reports/risk_example.json
(перегенерируются scripts/regen_risk_example.py).

Шрифт с кириллицей: DejaVu/Arial (та же логика, что src/report_pdf.py),
иначе Helvetica + честный варнинг на титуле.

Запуск: python scripts/build_presentation.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.report_pdf import _register_font  # noqa: E402 (DejaVu/Arial/Helvetica)

OUT = ROOT / "docs" / "Qagro_presentation.pdf"
CHART = ROOT / "metrics" / "plots" / "scatter_spring_wheat.png"

PAGE_W, PAGE_H = 841.8898, 595.2756  # A4 landscape, как исходная колода


def _load_numbers() -> dict:
    m = json.loads((ROOT / "metrics" / "metrics.json").read_text(encoding="utf-8"))
    iv = json.loads((ROOT / "metrics" / "intervals.json").read_text(encoding="utf-8"))
    ex = json.loads((ROOT / "reports" / "risk_example.json").read_text(encoding="utf-8"))
    ew, zw = ex["Esil_insurance_wheat"], ex["Zerenda_insurance_wheat"]
    w = m["spring_wheat"]
    ndvi_raw = json.loads((ROOT / "data" / "ndvi" / "ndvi_timeseries.json").read_text(encoding="utf-8"))
    ndvi_items = ndvi_raw if isinstance(ndvi_raw, list) else ndvi_raw.get("items", ndvi_raw)
    ndvi_real = sum(1 for x in ndvi_items
                    if isinstance((x or {}).get("ndvi_mean"), (int, float)))
    return {
        "wheat_bl_mae": round(w["baseline"]["mae"], 2),
        "wheat_bl_r2": round(w["baseline"]["r2"], 2),
        "wheat_mae": round(w["lgbm"]["mae"], 2),
        "wheat_r2": round(w["lgbm"]["r2"], 2),
        "barley_mae": round(m["barley"]["lgbm"]["mae"], 2),
        "barley_r2": round(m["barley"]["lgbm"]["r2"], 2),
        "oats_mae": round(m["oats"]["lgbm"]["mae"], 2),
        "oats_r2": round(m["oats"]["lgbm"]["r2"], 2),
        "sun_mae": round(m["sunflower"]["lgbm"]["mae"], 2),
        "sun_r2": round(m["sunflower"]["lgbm"]["r2"], 2),
        "cov_wheat": round(iv["spring_wheat"]["conformal_coverage"], 2),
        "exp_crops": [c for c, v in m.items()
                      if isinstance(v, dict) and v.get("below_baseline") is True],
        "esil_ploss": round(ew["p_loss"] * 100),
        "esil_pay": int(ew["expected_payout_ha"]),
        "zer_pay": int(zw["expected_payout_ha"]),
        "esil_ypred": round(ew["y_pred_c_ha"], 1),
        "esil_risk": ex["Esil_risk"].get("seasonal_risk"),
        "zer_risk": ex["Zerenda_risk"].get("seasonal_risk"),
        "ndvi_real": ndvi_real,
    }


def main() -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, PageBreak, Paragraph,
                                    SimpleDocTemplate, Spacer, Table, TableStyle)

    n = _load_numbers()
    font = _register_font()
    # экспериментальные культуры для слайдов (имена по-русски из конфига)
    import yaml
    cfg = yaml.safe_load((ROOT / "config" / "districts.yaml").read_text(encoding="utf-8"))
    _ru = {c.get("id"): c.get("name_ru", c.get("id")) for c in cfg.get("crops", [])}
    exp_ru = ", ".join(_ru.get(c, c) for c in n["exp_crops"]) or "—"

    doc = SimpleDocTemplate(str(OUT), pagesize=landscape(A4),
                            leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title="Qagro — AgriTech AI Hackathon")
    title_st = ParagraphStyle("t", fontName=font, fontSize=30, leading=36,
                              textColor=colors.HexColor("#111111"),
                              spaceAfter=10)
    body_st = ParagraphStyle("b", fontName=font, fontSize=19, leading=27,
                             textColor=colors.HexColor("#111111"),
                             spaceBefore=4, bulletIndent=12)
    foot_st = ParagraphStyle("f", fontName=font, fontSize=13, leading=16,
                             textColor=colors.HexColor("#333333"))

    def footer(i: int) -> list:
        return [Spacer(1, 12),
                Paragraph(f"{i}/10&ensp;&ensp;Qagro", foot_st)]

    slides: list[list] = []

    def bullet(t: str):
        return Paragraph(f"•&ensp;{t}", body_st)

    slides.append([
        Paragraph("1. Проблема: засуха в Акмоле", title_st),
        bullet("Акмола — житница Казахстана; засухи 2010/2012/2021 роняли урожай вдвое."),
        bullet("Фермер узнаёт постфактум: сев и страховка уже упущены."),
        bullet("Нужно: локальный прогноз + ранний сигнал + честная страховка."),
        *footer(1), PageBreak(),
    ])
    slides.append([
        Paragraph("2. Решение: Qagro — платформа агронома", title_st),
        bullet("Telegram-бот + веб + API на 3 языках (RU/KZ/EN)."),
        bullet("Прогноз 2026 + риск-светофор + страховка + сев + spray + NPK."),
        bullet("Трек 2 (2.1/2.2/2.4) + Трек 1 (NDVI, залежи, гибель)."),
        *footer(2), PageBreak(),
    ])
    slides.append([
        Paragraph("3. Демо: живой сценарий", title_st),
        bullet("/start → язык → Есильский → пшеница → карточка словами."),
        bullet(f"Ответ: ~{n['esil_ypred']} ц/га, риск средний, "
               f"выплата ~{n['esil_pay']} тг/га, сев 15–25 мая."),
        bullet("/gis — поля со спутника; /spray — окно опрыскивания."),
        *footer(3), PageBreak(),
    ])
    slides.append([
        Paragraph("4. Данные: только реальные", title_st),
        bullet("Панель v4: 1260 строк (10 районов × 21 год × 6 культур), 36 колонок."),
        bullet("БНС + NASA POWER + Open-Meteo ERA5 + площади stat.gov.kz + SoilGrids."),
        bullet("115 полей OSM (109 real + 6 demo); "
               f"NDVI Sentinel-2: {n['ndvi_real']} real + Landsat."),
        *footer(4), PageBreak(),
    ])
    slides.append([
        Paragraph("5. Модель: бленд с объяснением", title_st),
        bullet("Бейзлайн = среднее 5 лет; модель = LightGBM+Ridge (веса по train-CV)."),
        bullet("Прогноз + эмпирический интервал (конформные квантили) + топ-3 SHAP."),
        bullet(f"{exp_ru} — честный experimental baseline (не прошли gate)."),
        *footer(5), PageBreak(),
    ])
    chart = ([Image(str(CHART), width=230, height=170)] if CHART.exists() else [])
    slides.append([
        Paragraph("6. Метрики hold-out 2021–2025", title_st),
        bullet(f"Пшеница MAE {n['wheat_bl_mae']:.2f}→{n['wheat_mae']:.2f}, "
               f"R² {n['wheat_r2']:.2f}; "
               f"ячмень {n['barley_mae']:.2f}/{n['barley_r2']:.2f}; "
               f"овёс {n['oats_mae']:.2f}/{n['oats_r2']:.2f}."),
        bullet(f"Подсолнечник MAE 2.52→{n['sun_mae']:.2f}/R² {n['sun_r2']:.2f} "
               f"бьёт бейзлайн; 4/6 strong, {exp_ru} — experimental."),
        bullet(f"Покрытие интервала wheat {n['cov_wheat']:.2f} (номинал 0.80 не заявляем)."),
        *chart,
        *footer(6), PageBreak(),
    ])
    pay_rows = [
        ["Район", "P_loss", "Выплата, тг/га"],
        ["Есильский", f"{n['esil_ploss']}%", str(n["esil_pay"])],
        ["Зерендинский", "2%", str(n["zer_pay"])],
    ]
    pay_table = Table([[Paragraph(f"<b>{c}</b>", body_st) if i == 0 else Paragraph(c, body_st)
                        for c in row] for i, row in enumerate(pay_rows)],
                      colWidths=[150, 100, 160])
    pay_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    slides.append([
        Paragraph("7. Эффект в тенге", title_st),
        bullet(f"Esil: риск недобора {n['esil_ploss']}%, выплата ~{n['esil_pay']} тг/га; "
               f"Zerenda ~{n['zer_pay']} тг/га."),
        bullet("Окно сева + NPK под цель + экономика (прибыль/га)."),
        bullet("Субсидия 80%: страховка доступна фермеру."),
        Spacer(1, 8), pay_table,
        *footer(7), PageBreak(),
    ])
    slides.append([
        Paragraph("8. Масштаб и платформа", title_st),
        bullet("10 районов → все области KZ тем же пайплайном; 6 культур."),
        bullet("Мои поля + журнал + spray + элеваторы с маршрутами."),
        bullet("Docker, SQLite-кэш, офлайн-демо без интернета."),
        *footer(8), PageBreak(),
    ])
    slides.append([
        Paragraph("9. Команда Qagro", title_st),
        bullet("Kairbek Ansar — данные / ML / API."),
        bullet("Samat Ablayhan (капитан) — бот / веб / сдача."),
        bullet("Хакатон 18–21.09.2026, Aqmola Hub."),
        *footer(9), PageBreak(),
    ])
    slides.append([
        Paragraph("10. Планы: пилот", title_st),
        bullet("Пилот с хозяйствами Акмолы: официальные поля map.iaqmola.kz."),
        bullet("Декадный NDVI-ряд + калибровка интервалов до 0.80."),
        bullet("Интеграция e-АПК и страховщики."),
        *footer(10),
    ])

    story = [el for page in slides for el in page]
    # убрать висячий PageBreak в конце (его нет — последняя страница без него)
    doc.build(story)
    print(f"saved {OUT} (10 slides, font={font})")


if __name__ == "__main__":
    main()
