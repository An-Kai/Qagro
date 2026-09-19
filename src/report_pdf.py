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


PDF_TXT: dict[str, dict[str, str]] = {
    "ru": {"summary": "Коротко для фермера", "yield": "1. Прогноз урожая 2026 (ц/га)",
           "ins": "2. Страховка (ориентир, НЕ тариф)", "risk": "3. Риск засухи по декадам",
           "rec": "4. Когда сеять", "cal": "5. Календарь, алерты и элеватор",
           "no_data": "Нет данных.", "disc": "Это подсказка, а не гарантия. Проверьте с агрономом."},
    "kz": {"summary": "Фермерге қысқаша", "yield": "1. 2026 өнім болжамы (ц/га)",
           "ins": "2. Сақтандыру (бағдар, тариф ЕМЕС)", "risk": "3. Декадалар бойынша құрғақшылық қаупі",
           "rec": "4. Қашан себу керек", "cal": "5. Күнтізбе, дабылдар және элеватор",
           "no_data": "Дерек жоқ.", "disc": "Бұл кеңес, кепілдік емес. Агрономмен тексеріңіз."},
    "en": {"summary": "Short version for the farmer", "yield": "1. 2026 yield forecast (c/ha)",
           "ins": "2. Insurance (estimate, NOT a tariff)", "risk": "3. Decade drought risk",
           "rec": "4. When to sow", "cal": "5. Calendar, alerts & elevator",
           "no_data": "No data.", "disc": "Advice only, not a guarantee. Check with your agronomist."},
}


def _farmer_summary(lang: str, pred: dict | None, ins: dict | None,
                    risk: dict | None, rec: dict | None) -> str:
    """2-3 предложения простым языком: урожай, риск, выплата, сев."""
    if lang not in PDF_TXT:
        lang = "ru"
    if not pred or not ins:
        return PDF_TXT[lang]["no_data"]
    y, lo, hi = pred.get("y_pred"), pred.get("lo10"), pred.get("hi90")
    light = (risk or {}).get("seasonal_light") or ""
    p = round(float(ins.get("p_loss", 0)) * 100)
    pay = ins.get("expected_payout_ha")
    win = (rec or {}).get("window", "")
    msg = (rec or {}).get("message", "")
    if lang == "kz":
        return (f"Күтілетін өнім: {y} ц/га (әдетте {lo}–{hi}). "
                f"Құрғақшылық қаупі {light}. 80%-ға жетпеу қаупі {p}/100, "
                f"төлем шамамен {pay} теңге/га (тариф емес). Себу: {win}. {msg}")
    if lang == "en":
        return (f"Expected yield: {y} c/ha (usually {lo}–{hi}). "
                f"Drought risk {light}. Below-80% risk {p}/100, "
                f"payout ≈ {pay} tenge/ha (not a tariff). Sowing: {win}. {msg}")
    return (f"Ждите около {y} ц/га (обычно {lo}–{hi}). "
            f"Риск засухи {light}. Недобор 80% — {p} лет из 100, "
            f"выплата примерно {pay} тенге/га (не тариф). Сев: {win}. {msg}")


def build_report_pdf(
    district_en: str,
    crop: str,
    lang: str = "ru",
    pred: dict | None = None,
    ins: dict | None = None,
    risk: dict | None = None,
    rec: dict | None = None,
    district_ru: str | None = None,
    calendar: dict | None = None,
    alerts: list | None = None,
    alerts_error: str | None = None,
    elevator: dict | None = None,
) -> bytes:
    """Собрать PDF-отчёт. Все аргументы кроме district_en/crop опциональны.

    C8: calendar/alerts/elevator опциональны; если не переданы — календарь
    и элеватор подтягиваются best-effort офлайн (без сети), алерты только
    из аргумента (онлайн их кладёт вызывающий: API/бот). Возвращает bytes.
    Не ходит в сеть, только форматирует переданное.
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
    L = PDF_TXT.get(lang, PDF_TXT["ru"])
    story.append(Paragraph(_esc(L["summary"]), styles["Heading2"]))
    story.append(Paragraph(_esc(_farmer_summary(lang, pred, ins, risk, rec)),
                           styles["Normal"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(_esc(L["disc"]), styles["Normal"]))
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
    story.append(Paragraph(_esc(L["yield"]), styles["Heading2"]))
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
    story.append(Paragraph(_esc(L["ins"]), styles["Heading2"]))
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
    story.append(Paragraph(_esc(L["risk"]), styles["Heading2"]))
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
    story.append(Paragraph(_esc(L["rec"]), styles["Heading2"]))
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
    story.append(Spacer(1, 8))

    # 5) C8: календарь + алерты + ближайший элеватор
    story.append(Paragraph(_esc(L["cal"]), styles["Heading2"]))
    cal = calendar
    if cal is None:  # офлайн-фолбэк без сети
        try:
            try:
                from src.calendar import sowing_calendar as _cal
            except ImportError:
                from calendar import sowing_calendar as _cal  # type: ignore
            cal = _cal(crop, lang if lang in ("ru", "kz", "en") else "ru")
        except Exception:
            cal = None
    if cal:
        gdd = cal.get("gdd_norm") or []
        story.append(_kv_table([
            ("sowing window", cal.get("sowing_window")),
            ("harvest window", cal.get("harvest_window")),
            ("GDD norm", f"{gdd} (base {cal.get('gdd_base_temp')} °C)"
             if gdd else str(cal.get("gdd_base_temp"))),
            ("note", cal.get("note")),
            ("source", cal.get("source", "agro-practice")),
        ]))
    else:
        story.append(Paragraph("No calendar data.", styles["Normal"]))
    story.append(Spacer(1, 4))
    if alerts:
        adata = [[Paragraph("<b>date</b>", styles["Normal"]),
                  Paragraph("<b>type/level</b>", styles["Normal"]),
                  Paragraph("<b>message</b>", styles["Normal"])]]
        key = {"ru": "msg_ru", "kz": "msg_kz", "en": "msg_en"}.get(lang, "msg_ru")
        for a in alerts[:10]:
            adata.append([
                Paragraph(_esc(str(a.get("date"))), styles["Normal"]),
                Paragraph(_esc(f"{a.get('type')}/{a.get('level')}"), styles["Normal"]),
                Paragraph(_esc(str(a.get(key) or a.get("msg_ru"))), styles["Normal"]),
            ])
        at = Table(adata, colWidths=(90, 100, 290))
        at.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8"))]))
        story.append(at)
    else:
        _a_err = alerts_error or (
            "нет свежих алертов (прогноз Open-Meteo недоступен или угроз нет)")
        story.append(Paragraph(
            _esc("Alerts offline: " + str(_a_err) + " — проверьте /alerts при сети."),
            styles["Normal"]))
    story.append(Spacer(1, 4))
    elev = elevator
    if elev is None:  # офлайн-фолбэк без сети
        try:
            try:
                from src.logistics import nearest_elevator as _ne
            except ImportError:
                from logistics import nearest_elevator as _ne  # type: ignore
            elev = _ne(district_en)
        except Exception:
            elev = None
    if elev:
        story.append(_kv_table([
            ("nearest elevator", f"{elev.get('name_ru')} ({elev.get('name')})"),
            ("distance", f"{elev.get('dist_km')} km"),
            ("coords note", "оценочные (Qoldau granaries-map, уточнить)"),
        ]))
    else:
        story.append(Paragraph("No elevator data.", styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        "Disclaimer: APPROX-культуры (oats/sunflower/rapeseed/flax) — линейное "
        "масштабирование от пшеницы, без обучающих данных. Районы — даунскейлинг "
        "областной статистики на центроиды (см. config/districts.yaml). "
        "Decision support, не тариф / шешімді қолдау, тариф емес / decision support, not a tariff.",
        styles["Normal"]))
    doc.build(story)
    return buf.getvalue()
