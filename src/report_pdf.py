"""report_pdf.py — общий PDF-билдер для API (/report) и Telegram-бота (кнопка PDF).

Вход: готовый full-результат (см. src/api.py::_full_result) + метаданные.
Выход: bytes PDF (reportlab, таблица + риски).

Кириллица: пробуем зарегистрировать DejaVuSans/Arial (есть на Windows и
в python:3.12-slim при установленном fonts-dejavu), иначе Helvetica
(тогда кириллица может не отобразиться — латинские fallback-метки всё
равно дадут валидный PDF).
"""
from __future__ import annotations

import io
from pathlib import Path
from xml.sax.saxutils import escape as _esc


def _register_font() -> str:
    """Возвращает имя шрифта с кириллицей, если найден, иначе Helvetica."""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return "Helvetica"
    candidates = [
        Path(r"C:\Windows\Fonts\DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    ]
    bold_candidates = [
        Path(r"C:\Windows\Fonts\DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
    ]
    for p in candidates:
        if p.exists():
            try:
                pdfmetrics.registerFont(TTFont("QagroFont", str(p)))
                for bp in bold_candidates:
                    if bp.exists():
                        try:
                            pdfmetrics.registerFont(TTFont("QagroFont-Bold", str(bp)))
                        except Exception:
                            pass
                        break
                return "QagroFont"
            except Exception:
                continue
    return "Helvetica"


def build_report_pdf(
    district_en: str,
    crop: str,
    lang: str = "ru",
    pred: dict | None = None,
    ins: dict | None = None,
    risk: dict | None = None,
    rec: dict | None = None,
    district_ru: str | None = None,
) -> bytes:
    """Собрать PDF-отчёт. Все аргументы кроме district_en/crop опциональны.

    Возвращает bytes PDF. Не ходит в сеть, только форматирует переданное.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    font = _register_font()
    # reportlab font name for bold: use same if bold variant missing
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Qagro report {district_en}/{crop}")
    styles = getSampleStyleSheet()
    for s in styles.byName.values():
        s.fontName = font
        s.leading = 14
    story = []

    title = f"Qagro — {district_ru or district_en} / {crop} (2026)"
    story.append(Paragraph(_esc(title), styles["Title"]))
    story.append(Spacer(1, 8))
    approx = bool((pred or {}).get("approx") or (ins or {}).get("approx"))
    if approx:
        story.append(Paragraph(
            "APPROX: культура без обучающих данных, масштабирование от пшеницы. "
            "Decision support, не тариф.", styles["Normal"]))
        story.append(Spacer(1, 6))

    def _kv_table(rows: list[tuple[str, str]], col_widths=(220, 260)) -> Table:
        data = [[Paragraph(f"<b>{_esc(str(k))}</b>", styles["Normal"]),
                 Paragraph(_esc(str(v)), styles["Normal"])] for k, v in rows]
        t = Table(data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f2f2f2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    # 1) Прогноз
    story.append(Paragraph("1. Yield forecast 2026 (LGBM, ц/га)", styles["Heading2"]))
    if pred:
        story.append(_kv_table([
            ("y_pred", pred.get("y_pred")),
            ("80% interval [lo10, hi90]", f"{pred.get('lo10')} .. {pred.get('hi90')}"),
            ("yield_lag1 (2025)", (pred.get("meta") or {}).get("yield_lag1")),
            ("residual_std", (pred.get("meta") or {}).get("residual_std")),
            ("weather", (pred.get("meta") or {}).get("weather_source", "provided")),
            ("APPROX", (pred.get("meta") or {}).get("method", pred.get("approx", False))),
        ]))
        story.append(Spacer(1, 6))
        factors = pred.get("factors") or []
        if factors:
            fdata = [[Paragraph("<b>feature</b>", styles["Normal"]),
                      Paragraph("<b>value</b>", styles["Normal"]),
                      Paragraph("<b>SHAP</b>", styles["Normal"])]]
            for f in factors[:3]:
                fdata.append([Paragraph(_esc(str(f.get("feature"))), styles["Normal"]),
                              Paragraph(_esc(str(f.get("value"))), styles["Normal"]),
                              Paragraph(_esc(str(f.get("shap_value"))), styles["Normal"])])
            ft = Table(fdata, colWidths=(160, 160, 160))
            ft.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8"))]))
            story.append(ft)
    else:
        story.append(Paragraph("No prediction data.", styles["Normal"]))
    story.append(Spacer(1, 8))

    # 2) Страховка
    story.append(Paragraph("2. Index insurance (decision support, NOT a tariff)", styles["Heading2"]))
    if ins:
        story.append(_kv_table([
            ("mean5 (ц/га)", f"{ins.get('mean5_c_ha')} {ins.get('mean5_years')}"),
            ("strike 0.8*mean5", ins.get("strike_c_ha")),
            ("P_loss P(Y<strike)", ins.get("p_loss")),
            ("expected payout/ha (KZT)", ins.get("expected_payout_ha")),
            ("payout at y_pred/ha (KZT)", ins.get("payout_at_pred_ha")),
            ("price KZT/t", ins.get("price_kzt_per_t")),
            ("formula", ins.get("payout_formula", "")),
        ]))
        story.append(Spacer(1, 4))
        story.append(Paragraph(_esc(str(ins.get("disclaimer", ""))), styles["Normal"]))
    else:
        story.append(Paragraph("No insurance data.", styles["Normal"]))
    story.append(Spacer(1, 8))

    # 3) Риски
    story.append(Paragraph("3. Decade drought/heat risk (Open-Meteo)", styles["Heading2"]))
    if risk and risk.get("seasonal_risk") is not None:
        story.append(_kv_table([
            ("seasonal risk", f"{risk.get('seasonal_risk')} {risk.get('seasonal_light', '')}"),
            ("stages", str(risk.get("stages"))),
            ("formula", str(risk.get("formula", ""))[:200]),
            ("traffic light", str(risk.get("traffic_light", "green<35 yellow35-60 red>60"))),
        ]))
        story.append(Spacer(1, 6))
        decades = risk.get("decades") or []
        if decades:
            rdata = [[Paragraph("<b>decade</b>", styles["Normal"]),
                      Paragraph("<b>precip anom%</b>", styles["Normal"]),
                      Paragraph("<b>dry/heat</b>", styles["Normal"]),
                      Paragraph("<b>risk</b>", styles["Normal"])]]
            for d in decades:
                rdata.append([
                    Paragraph(_esc(str(d.get("label", d.get("decade")))), styles["Normal"]),
                    Paragraph(_esc(str(d.get("precip_anom_pct"))), styles["Normal"]),
                    Paragraph(_esc(f"{d.get('dry_streak')}/{d.get('heat_days')}"), styles["Normal"]),
                    Paragraph(_esc(f"{d.get('risk_index')} {d.get('light', '')}"), styles["Normal"]),
                ])
            rt = Table(rdata, colWidths=(220, 90, 70, 100))
            rt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8"))]))
            story.append(rt)
    else:
        err = (risk or {}).get("error", "risk offline (Open-Meteo unavailable)")
        story.append(Paragraph(_esc(f"Risk offline: {err}. Светофор см. в боте/API по p_loss."),
                               styles["Normal"]))
    story.append(Spacer(1, 8))

    # 4) Рекомендация
    story.append(Paragraph("4. Sowing recommendation", styles["Heading2"]))
    if rec:
        story.append(_kv_table([
            ("window", rec.get("window")),
            ("message", rec.get("message")),
            ("actions", "; ".join(rec.get("actions") or [])),
            ("reason", rec.get("reason")),
            ("lang/branch", f"{rec.get('lang')}/{rec.get('branch')}"),
        ]))
    else:
        story.append(Paragraph("No recommendation data.", styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        "Disclaimer: APPROX-культуры (oats/sunflower/rapeseed/flax) — линейное "
        "масштабирование от пшеницы, без обучающих данных. Районы — даунскейлинг "
        "областной статистики на центроиды (см. config/districts.yaml). "
        "Decision support, не тариф / шешімді қолдау, тариф емес / decision support, not a tariff.",
        styles["Normal"]))
    doc.build(story)
    return buf.getvalue()
