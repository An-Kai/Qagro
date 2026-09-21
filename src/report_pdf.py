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
           "farm": "6. Хозяйство и деньги (NPK, экономика, опрыскивание)",
           "no_data": "Нет данных.", "disc": "Это подсказка, а не гарантия. Проверьте с агрономом."},
    "kz": {"summary": "Фермерге қысқаша", "yield": "1. 2026 өнім болжамы (ц/га)",
           "ins": "2. Сақтандыру (бағдар, тариф ЕМЕС)", "risk": "3. Декадалар бойынша құрғақшылық қаупі",
           "rec": "4. Қашан себу керек", "cal": "5. Күнтізбе, дабылдар және элеватор",
           "farm": "6. Шаруашылық және ақша (NPK, экономика, бүрку)",
           "no_data": "Дерек жоқ.", "disc": "Бұл кеңес, кепілдік емес. Агрономмен тексеріңіз."},
    "en": {"summary": "Short version for the farmer", "yield": "1. 2026 yield forecast (c/ha)",
           "ins": "2. Insurance (estimate, NOT a tariff)", "risk": "3. Decade drought risk",
           "rec": "4. When to sow", "cal": "5. Calendar, alerts & elevator",
           "farm": "6. Farm & money (NPK, economy, spraying)",
           "no_data": "No data.", "disc": "Advice only, not a guarantee. Check with your agronomist."},
}

# Человеческие подписи строк таблиц (аудит #9): техно-id убран из подписей,
# коды district_en/crop остаются только в заголовке мелким текстом.
PDF_LBL: dict[str, dict[str, str]] = {
    "ru": {"y": "Прогноз (ц/га)", "interval": "Интервал 80% [низ – верх]",
           "lag": "Урожай прошлого года (2025)", "spread": "Разброс модели",
           "weather": "Погода", "method": "Метод",
           "f_factor": "Фактор", "f_value": "Значение", "f_effect": "Влияние",
           "mean5": "Среднее за 5 лет (ц/га)", "strike": "Порог 80% от среднего",
           "ploss": "Риск недобора P(Y<порог)", "payout": "Ожидаемая выплата/га (тенге)",
           "payout_at": "Выплата при прогнозе/га (тенге)", "price": "Цена (тенге/т)",
           "formula": "Формула",
           "formula_txt": "max(0, 80% среднего − прогноз) / 10 × цена × 0.8 (субсидия)",
           "literal": "Выплата дословно по ТЗ (без /10)",
           "window": "Окно", "message": "Совет", "actions": "Действия", "reason": "Почему",
           "sow": "Окно сева", "harvest": "Окно уборки", "gdd": "Норма тепла (GDD)",
           "note": "Заметка", "source": "Источник",
           "elev": "Ближайший элеватор", "dist": "Расстояние",
           "coords": "Координаты",
           "npk_goal": "Цель NPK (ц/га)",
           "eco_yield": "Урожай (ц/га)", "eco_price": "Цена (тенге/т)",
           "eco_rev": "Выручка (тенге/га)", "eco_profit": "Прибыль (тенге/га)",
           "eco_pct": "Рентабельность %", "eco_cost": "Про затраты"},
    "kz": {"y": "Болжам (ц/га)", "interval": "80% аралық [төмен – жоғары]",
           "lag": "Өткен жылғы өнім (2025)", "spread": "Модель шашырауы",
           "weather": "Ауа райы", "method": "Әдіс",
           "f_factor": "Фактор", "f_value": "Мәні", "f_effect": "Әсері",
           "mean5": "5 жылдық орташа (ц/га)", "strike": "Орташаның 80% шегі",
           "ploss": "Жетпеу қаупі P(Y<шег)", "payout": "Күтілетін төлем/га (теңге)",
           "payout_at": "Болжамдағы төлем/га (теңге)", "price": "Баға (теңге/т)",
           "formula": "Формула",
           "formula_txt": "max(0, орташаның 80% − болжам) / 10 × баға × 0.8 (субсидия)",
           "literal": "ТЗ бойынша тура төлем (/10-сыз)",
           "window": "Терезе", "message": "Кеңес", "actions": "Әрекеттер", "reason": "Неге",
           "sow": "Себу терезесі", "harvest": "Жинау терезесі", "gdd": "Жылу нормасы (GDD)",
           "note": "Ескертпе", "source": "Дереккөз",
           "elev": "Жақын элеватор", "dist": "Қашықтық",
           "coords": "Координаттар",
           "npk_goal": "NPK мақсаты (ц/га)",
           "eco_yield": "Өнім (ц/га)", "eco_price": "Баға (теңге/т)",
           "eco_rev": "Түсім (теңге/га)", "eco_profit": "Пайда (теңге/га)",
           "eco_pct": "Рентабельділік %", "eco_cost": "Шығын туралы"},
    "en": {"y": "Forecast (c/ha)", "interval": "80% interval [low – high]",
           "lag": "Last year yield (2025)", "spread": "Model spread",
           "weather": "Weather", "method": "Method",
           "f_factor": "Factor", "f_value": "Value", "f_effect": "Effect",
           "mean5": "5-year average (c/ha)", "strike": "80%-of-average trigger",
           "ploss": "Shortfall risk P(Y<trigger)", "payout": "Expected payout/ha (tenge)",
           "payout_at": "Payout at forecast/ha (tenge)", "price": "Price (tenge/t)",
           "formula": "Formula",
           "formula_txt": "max(0, 80% of average − forecast) / 10 × price × 0.8 (subsidy)",
           "literal": "Literal payout per ToR (no /10)",
           "window": "Window", "message": "Advice", "actions": "Actions", "reason": "Why",
           "sow": "Sowing window", "harvest": "Harvest window", "gdd": "Heat norm (GDD)",
           "note": "Note", "source": "Source",
           "elev": "Nearest elevator", "dist": "Distance",
           "coords": "Coordinates",
           "npk_goal": "NPK target (c/ha)",
           "eco_yield": "Yield (c/ha)", "eco_price": "Price (tenge/t)",
           "eco_rev": "Revenue (tenge/ha)", "eco_profit": "Profit (tenge/ha)",
           "eco_pct": "Profitability %", "eco_cost": "About costs"},
}


# Человеческие названия фич для SHAP-таблицы (id -> слова; нет в мапе — как есть).
PDF_FEAT: dict[str, dict[str, str]] = {
    "ru": {"year_trend": "Тренд года", "yield_lag1": "Урожай прошлого года",
           "yield_roll3": "Среднее за 3 года", "tmean_mjja": "Температура MJJA",
           "precip_mjja": "Осадки MJJA", "gdd5": "Теплосумма GDD5",
           "heat30": "Жара 30°+ (дней)", "dry_max": "Сухая серия (дней)",
           "et0": "Испаряемость ET0", "p30_anom": "Аномалия осадков",
           "precip_spring": "Осадки весны", "tmax_july": "Макс. июля",
           "dtr": "Суточный ход (DTR)", "vpd_proxy": "Дефицит влаги (VPD)",
           "spei_proxy": "Индекс засухи (SPEI)", "htc_mjja": "ГТК Селянинова",
           "oilseeds_share": "Доля масличных", "trend_sq": "Ускорение тренда",
           "trend_recent": "Тренд после 2015", "oilshare_trend": "Масличные × время",
           "lat": "Широта", "lon": "Долгота"},
    "kz": {"year_trend": "Жыл тренді", "yield_lag1": "Өткен жылғы өнім",
           "yield_roll3": "3 жылдық орташа", "tmean_mjja": "MJJA температурасы",
           "precip_mjja": "MJJA жауын-шашын", "gdd5": "GDD5 жылу қосындысы",
           "heat30": "30°+ ыстық (күн)", "dry_max": "Құрғақ кезең (күн)",
           "et0": "Булану ET0", "p30_anom": "Жауын ауытқуы",
           "precip_spring": "Көктем жауыны", "tmax_july": "Шілде максимумы",
           "dtr": "Тәуліктік жүріс (DTR)", "vpd_proxy": "Ылғал тапшылығы (VPD)",
           "spei_proxy": "Құрғақшылық индексі (SPEI)", "htc_mjja": "Селянинов ГТК",
           "oilseeds_share": "Майды дақыл үлесі", "trend_sq": "Тренд үдеуі",
           "trend_recent": "2015 жылдан кейінгі тренд", "oilshare_trend": "Майды × уақыт",
           "lat": "Ендік", "lon": "Бойлық"},
    "en": {"year_trend": "Year trend", "yield_lag1": "Last year yield",
           "yield_roll3": "3-year average", "tmean_mjja": "MJJA temperature",
           "precip_mjja": "MJJA precipitation", "gdd5": "GDD5 heat sum",
           "heat30": "Heat 30°+ (days)", "dry_max": "Dry spell (days)",
           "et0": "Evapotranspiration ET0", "p30_anom": "Precipitation anomaly",
           "precip_spring": "Spring precipitation", "tmax_july": "July maximum",
           "dtr": "Diurnal range (DTR)", "vpd_proxy": "Moisture deficit (VPD)",
           "spei_proxy": "Drought index (SPEI)", "htc_mjja": "Selyaninov HTC",
           "oilseeds_share": "Oilseeds share", "trend_sq": "Trend acceleration",
           "trend_recent": "Post-2015 trend", "oilshare_trend": "Oilseeds × time",
           "lat": "Latitude", "lon": "Longitude"},
}

# Погода и метод — словами, а не tech-строками ("False", английский source).
PDF_WS: dict[str, dict[str, str]] = {
    "provided": {"ru": "заданная пользователем", "kz": "пайдаланушы берген",
                 "en": "user-provided"},
    "neutral district MJJA mean 2016-2025 (climate norm)":
        {"ru": "климат-норма района (средний MJJA 2016–2025)",
         "kz": "ауданның климат-нормасы (орташа MJJA 2016–2025)",
         "en": "district climate norm (mean MJJA 2016–2025)"},
}


def _method_str(pred: dict | None, lang: str) -> str:
    p = pred or {}
    if p.get("approx"):
        return {"ru": "APPROX: масштаб от пшеницы (модели нет)",
                "kz": "APPROX: бидайдан масштаб (модель жоқ)",
                "en": "APPROX: scaled from wheat (no model)"}.get(lang, "")
    if p.get("experimental"):
        return {"ru": "среднее за 5 лет (пробный: модель хуже бейзлайна)",
                "kz": "5 жылдық орташа (сынақ: модель бейзлайннан нашар)",
                "en": "5-year mean (trial: model below baseline)"}.get(lang, "")
    return {"ru": "бленд LightGBM+Ridge (веса по train-CV)",
            "kz": "LightGBM+Ridge бленд (салмақ train-CV)",
            "en": "LightGBM+Ridge blend (train-CV weights)"}.get(lang, "")


def _names(district_en: str, crop: str, lang: str) -> tuple[str, str]:
    """Локализованные имена района/культуры из config/districts.yaml (офлайн).

    Фолбэк — tech-id, если конфига нет: заголовок всё равно собирается.
    """
    dname, cname = district_en, crop
    try:
        import yaml

        cfg_path = Path(__file__).resolve().parents[1] / "config" / "districts.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        for d in cfg.get("districts", []):
            if d.get("name_en") == district_en:
                dname = str(d.get(f"name_{lang}") or d.get("name_ru") or district_en)
                break
        for c in cfg.get("crops", []):
            if c.get("id") == crop:
                cname = str(c.get(f"name_{lang}") or c.get("name_ru") or crop)
                break
    except Exception:
        pass
    return dname, cname


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

    lang = lang if lang in PDF_TXT else "ru"
    B = PDF_LBL.get(lang, PDF_LBL["ru"])
    dname, cname = _names(district_en, crop, lang)
    title = f"Qagro — {dname} / {cname} ({district_en}/{crop}, 2026)"
    story.append(Paragraph(_esc(title), styles["Title"]))
    story.append(Spacer(1, 8))
    if font == "Helvetica":
        # Честно предупреждаем: без DejaVu/Arial кириллица превращается в точки.
        story.append(Paragraph(_esc(
            "⚠ Нет шрифта с кириллицей — русский/казахский текст может "
            "отображаться неверно (Windows: Arial/DejaVu, Docker: fonts-dejavu)."),
            styles["Normal"]))
        story.append(Spacer(1, 4))
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
        _ws = (pred.get("meta") or {}).get("weather_source", "provided")
        _ws_txt = PDF_WS.get(str(_ws), {}).get(lang, str(_ws))
        story.append(_kv_table([
            (B["y"], pred.get("y_pred")),
            (B["interval"], f"{pred.get('lo10')} .. {pred.get('hi90')}"),
            (B["lag"], (pred.get("meta") or {}).get("yield_lag1")),
            (B["spread"], (pred.get("meta") or {}).get("residual_std")),
            (B["weather"], _ws_txt),
            (B["method"], _method_str(pred, lang)),
        ]))
        story.append(Spacer(1, 6))
        factors = pred.get("factors") or []
        if factors:
            _fm = PDF_FEAT.get(lang, PDF_FEAT["ru"])
            fdata = [[Paragraph(f"<b>{_esc(B['f_factor'])}</b>", styles["Normal"]),
                      Paragraph(f"<b>{_esc(B['f_value'])}</b>", styles["Normal"]),
                      Paragraph(f"<b>{_esc(B['f_effect'])}</b>", styles["Normal"])]]

            def _r3(v) -> str:
                try:
                    return str(round(float(v), 3))
                except (TypeError, ValueError):
                    return str(v)

            for f in factors[:3]:
                fdata.append([Paragraph(_esc(str(_fm.get(f.get("feature"), f.get("feature")))),
                                        styles["Normal"]),
                              Paragraph(_esc(_r3(f.get("value"))), styles["Normal"]),
                              Paragraph(_esc(_r3(f.get("shap_value"))), styles["Normal"])])
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
            (B["mean5"], f"{ins.get('mean5_c_ha')} {ins.get('mean5_years')}"),
            (B["strike"], ins.get("strike_c_ha")),
            (B["ploss"], ins.get("p_loss")),
            (B["payout"], ins.get("expected_payout_ha")),
            (B["payout_at"], ins.get("payout_at_pred_ha")),
            (B["price"], ins.get("price_kzt_per_t")),
            (B["formula"], B["formula_txt"]),
            (B["literal"], ins.get("payout_literal_no_div10")),
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
            (B["window"], rec.get("window")),
            (B["message"], rec.get("message")),
            (B["actions"], "; ".join(rec.get("actions") or [])),
            (B["reason"], rec.get("reason")),
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
                from src.sowing_calendar import sowing_calendar as _cal
            except ImportError:
                from sowing_calendar import sowing_calendar as _cal  # type: ignore
            cal = _cal(crop, lang if lang in ("ru", "kz", "en") else "ru")
        except Exception:
            cal = None
    if cal:
        gdd = cal.get("gdd_norm") or []
        story.append(_kv_table([
            (B["sow"], cal.get("sowing_window")),
            (B["harvest"], cal.get("harvest_window")),
            (B["gdd"], f"{gdd} (base {cal.get('gdd_base_temp')} °C)"
             if gdd else str(cal.get("gdd_base_temp"))),
            (B["note"], cal.get("note")),
            (B["source"], cal.get("source", "agro-practice")),
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
            (B["elev"], f"{elev.get('name_ru')} ({elev.get('name')})"),
            (B["dist"], f"{elev.get('dist_km')} km"),
            (B["coords"], "оценочные (Qoldau granaries-map, уточнить)"),
        ]))
    else:
        story.append(Paragraph("No elevator data.", styles["Normal"]))
    story.append(Spacer(1, 8))

    # 6) C7: хозяйство и деньги — NPK + экономика + spray-вердикт из alerts.
    # Best-effort офлайн: только форматируем переданное (pred/ins/alerts),
    # в сеть не ходим; любая ошибка гасится, PDF не роняем.
    story.append(Paragraph(_esc(L["farm"]), styles["Heading2"]))
    _msg_key = {"ru": "message_ru", "kz": "message_kz", "en": "message_en"}.get(lang, "message_ru")
    _alert_key = {"ru": "msg_ru", "kz": "msg_kz", "en": "msg_en"}.get(lang, "msg_ru")
    try:
        _y_goal = float((pred or {}).get("y_pred") or 0)
    except (TypeError, ValueError):
        _y_goal = 0
    # 6a) NPK для цели = y_pred
    try:
        if _y_goal > 0:
            try:
                from src.fertilizer import calc_npk as _calc_npk
            except ImportError:
                from fertilizer import calc_npk as _calc_npk  # type: ignore
            _npk = _calc_npk(crop, _y_goal)
            story.append(_kv_table([
                (B["npk_goal"], _npk.get("yield_goal_c_ha")),
                ("N kg/ha", _npk.get("N_kg_ha")),
                ("P kg/ha", _npk.get("P_kg_ha")),
                ("K kg/ha", _npk.get("K_kg_ha")),
                (B["source"], f"{_npk.get('soil_level')} / {_npk.get('source')}"),
            ]))
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                _esc(str(_npk.get(_msg_key) or _npk.get("message_ru") or "")),
                styles["Normal"]))
        else:
            story.append(Paragraph(_esc("NPK: " + L["no_data"]), styles["Normal"]))
    except Exception:
        story.append(Paragraph(_esc("NPK: " + L["no_data"]), styles["Normal"]))
    story.append(Spacer(1, 4))
    # 6b) экономика profit_ha(y_pred, price)
    try:
        _price = (ins or {}).get("price_kzt_per_t")
        if _y_goal > 0 and _price:
            try:
                from src.economics import EXPLAIN as _EXPLAIN
                from src.economics import profit_ha as _profit_ha
            except ImportError:
                from economics import EXPLAIN as _EXPLAIN  # type: ignore
                from economics import profit_ha as _profit_ha  # type: ignore
            _eco = _profit_ha(float(_y_goal), float(_price))
            story.append(_kv_table([
                (B["eco_yield"], _eco.get("yield_c_ha")),
                (B["eco_price"], _eco.get("price_kzt_t")),
                (B["eco_rev"], _eco.get("revenue_kzt_ha")),
                (B["eco_profit"], _eco.get("profit_kzt_ha")),
                (B["eco_pct"], _eco.get("profitability_pct")),
                (B["eco_cost"], _eco.get("assumption", "")),
            ]))
            story.append(Spacer(1, 4))
            _e_msg = _eco.get(_msg_key)  # будущие message_ru/kz/en, если появятся
            if not _e_msg:
                try:
                    _e_msg = (_EXPLAIN or {}).get(lang) or (_EXPLAIN or {}).get("ru", "")
                except Exception:
                    _e_msg = ""
            if _e_msg:
                story.append(Paragraph(_esc(str(_e_msg)), styles["Normal"]))
        else:
            story.append(Paragraph(_esc("Economy: " + L["no_data"]), styles["Normal"]))
    except Exception:
        story.append(Paragraph(_esc("Economy: " + L["no_data"]), styles["Normal"]))
    story.append(Spacer(1, 4))
    # 6c) spray-вердикт из переданных alerts (первые 2), без сети
    try:
        if alerts:
            for _a in list(alerts)[:2]:
                _m = (_a or {}).get(_alert_key) or (_a or {}).get("msg_ru") or ""
                story.append(Paragraph(
                    _esc(f"{(_a or {}).get('date', '')} "
                         f"{(_a or {}).get('type', '')}/{(_a or {}).get('level', '')}: {_m}"),
                    styles["Normal"]))
        else:
            story.append(Paragraph(_esc("Spray: " + L["no_data"]), styles["Normal"]))
    except Exception:
        story.append(Paragraph(_esc("Spray: " + L["no_data"]), styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        "Disclaimer: APPROX-культуры (oats/sunflower/rapeseed/flax) — линейное "
        "масштабирование от пшеницы, без обучающих данных. Районы — даунскейлинг "
        "областной статистики на центроиды (см. config/districts.yaml). "
        "Decision support, не тариф / шешімді қолдау, тариф емес / decision support, not a tariff.",
        styles["Normal"]))
    doc.build(story)
    return buf.getvalue()
