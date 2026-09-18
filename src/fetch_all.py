"""fetch_all.py — оркестратор дата-пайплайна Qagro Track 2.

Порядок:
  1. fetch_stat      -> data/raw/stat_yield.csv
  2. fetch_nasa      -> data/raw/nasa_*.json + nasa_summary.csv
  3. fetch_openmeteo -> data/raw/openmeteo_*_daily.json + openmeteo_summary.csv
  4. features.build_panel -> data/processed/akmola_panel.csv
  5. проверки: строк > 50, без NaN в yield, схема колонок
  6. data_card.md (источники, покрытие, честность про 2025/даунскейлинг)

Запуск (чистая машина, Windows PowerShell):
  pip install -q pandas numpy requests pyyaml openmeteo-requests requests-cache retry-requests
  python src/fetch_all.py

Любая ошибка API/сети/схемы — громкий fail (traceback + exit 1), без моков.
"""
from __future__ import annotations

import logging
import runpy
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("fetch_all")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
PANEL = PROC / "akmola_panel.csv"
CARD = PROC / "data_card.md"

EXPECTED_COLS = ["year", "district", "district_en", "lat", "lon", "crop", "yield_c_ha",
                 "tmean_mjja", "precip_mjja", "gdd5", "heat30", "dry_max", "et0", "p30_anom"]


def run_step(name: str, script: Path) -> None:
    log.info("=" * 70)
    log.info("STEP: %s (%s)", name, script.name)
    runpy.run_path(str(script), run_name="__main__")
    log.info("STEP OK: %s", name)


def write_data_card(panel: pd.DataFrame) -> None:
    n_rows = len(panel)
    n_years = panel["year"].nunique()
    n_dist = panel["district"].nunique()
    crops = sorted(panel["crop"].unique())
    y0, y1 = int(panel["year"].min()), int(panel["year"].max())
    miss = panel.isna().sum()
    miss_txt = "\n".join(f"| {c} | {int(miss[c])} |" for c in panel.columns)
    try:
        sample = panel.head(5).to_markdown(index=False)
    except Exception:
        sample = "```\n" + panel.head(5).to_string(index=False) + "\n```"

    card = f"""# Data Card — akmola_panel.csv (Qagro Track 2, AgriTech AI Hackathon)

## Что это
Панель «район × год × культура» для Акмолинской области: урожайность + сезонные
агроклиматические признаки (май–август). Назначение — MVP прогноза урожайности /
триггеров засухи и агро-дашборда.

## Файл
- `data/processed/akmola_panel.csv` — {n_rows} строк, годы {y0}–{y1},
  районов: {n_dist}, культуры: {', '.join(crops)} (строк на культуру: {n_rows // max(len(crops),1)}).
- Схема: `year,district,district_en,lat,lon,crop,yield_c_ha,tmean_mjja,precip_mjja,gdd5,heat30,dry_max,et0,p30_anom`
- Единицы: yield — ц/га (вес после доработки); tmean — °C (MJJA); precip — мм;
  gdd5 — °C·сут (base 5); heat30 — дни tmax>30; dry_max — дни (осадки<1мм);
  et0 — мм (FAO); p30_anom — % к норме 2005–2020.

## Источники (без выдуманных данных)
1. **Урожайность пшеница/ячмень — Бюро национальной статистики РК (stat.gov.kz)**:
   динамические таблицы Акмолинской области
   (`/ru/region/akmola/dynamic-tables/1485`, раздел зерновых) и публикация
   валового сбора 2024 (вес после доработки, 04.02.2025): зерновые 25 204.8 тыс.т,
   пшеница 18 576.7 тыс.т, ячмень 3.8 млн т; урожайность зерновых 15.2 ц/га
   (пересказ ElDala.kz / grainunion.kz со ссылкой на БНС).
   Национальные якоря пшеницы: 2022 — 12.8, 2023 — 9.2, 2024 — 14.2 ц/га;
   зерновые: 2022 — 13.8, 2023 — 10.3, 2024 — 15.2 ц/га (APK-Inform, 03.02.2025).
2. **Акимат Акмолинской области / primeminister.kz**: 2024 — 6.6 млн т зерна
   (margin.kz 20.10.2024); 2025 — 7.6 млн т, 16.3 ц/га, >70% 3 класс
   (primeminister.kz 02.12.2025; tengrinews.kz 26.10.2025).
3. **FAOSTAT QCL + USDA FAS GAIN (валидация формы ряда 2005–2021)**:
   засухи 2010/2012/2019 (~1.01 т/га)/2021, рекорд 2011; USDA PSD barley
   10-yr avg 1.445 т/га. Портал: fao.org/faostat.
4. **v2 новые культуры — областные якоря (см. src/fetch_stat.py, колонка source)**:
   oats — BNS via CEIC KZ.B019 (2016 16.0, 2017 13.3, 2011 max 18.0) + GAIN
   KZ2023-0002 (2022 11.6) / KZ2024-0002 (2023 7.9) + Interfax/Минсельхоз
   30.09.2024 (2024 15.8) + 2025 PRELIM 16.9;
   sunflower — BNS via CEIC (2016 9.3, 2017 10.2) + OCL 2025 avg 7.9
   + GAIN KZ2025-0010 + APK-Inform/BNS 2024 14.6 / 2025 13.9;
   rapeseed — Helgi/FAOSTAT (2021 12.34, 2022 14.15) + OCL avg 12.2
   + APK/BNS 2022 14.2 / 2023 13.3 / 2024 19.2 / 2025 19.5;
   flax — OCL avg 6.6 + APK/BNS 2022 6.3 / 2023 5.0 / 2024 8.7 + 2025 PRELIM 8.3.
   Форма 2005–2021 — засушливый профиль FAOSTAT (2010/2012/2021 низко, 2011 высоко).
5. **NASA POWER Monthly Point (реанализ MERRA-2)**: T2M/T2M_MAX/T2M_MIN/
   PRECTOTCORR/RH2M/ALLSKY_SFC_SW_DWN/WS2M/GWETTOP, community=AG, 2005–2025.
   Сырые ответы: `data/raw/nasa_<EN>.json`; агрегаты: `data/raw/nasa_summary.csv`.
6. **Open-Meteo Archive (ERA5)**: daily tmax/tmin/precip/ET0 FAO 2005-01-01–2025-08-31,
   hourly soil_moisture_3_9cm; timezone Asia/Almaty. Сырое: `data/raw/openmeteo_*_daily.json`;
   агрегаты: `data/raw/openmeteo_summary.csv`.
7. **Координаты районов** — `config/districts.yaml` (центроиды WGS84).
8. **v2 NDVI Sentinel-2 (пилот, только список сцен, БЕЗ выдуманных чисел)**:
   `data/ndvi/ndvi_timeseries.json` (Esil/Zerenda, июнь–август 2024–2025,
   cloud<20%, collection sentinel-2-l2a, Planetary Computer STAC без ключа;
   `python src/sentinel_ndvi.py`); все `ndvi_mean=None` (MISSING).
   Ручной источник: Copernicus Browser https://browser.dataspace.copernicus.eu/
   + Sentinel Hub https://www.sentinel-hub.com/. Модель работает без NDVI
   (optional join `src/features_ndvi.py`: `ndvi_max` только при настоящих NDVI).

## Честные ограничения (прочитай перед моделированием)
- **2025 yield — ПРЕДВАРИТЕЛЬНЫЙ** (пшеница/ячмень 15.8/16.8; oats 16.9; flax 8.3;
  подсолнечник/рапс 2025 — офиц. БНС/APK-Inform: 13.9/19.5).
  Район = областной якорь × агрокоэф.; в модели 2025 лучше держать флагом.
- **Подсолнечник/рапс/лён 2024–2025 — структурный сдвиг** (гибриды, площади:
  подсолнечник 1.5 т/га в 2024 vs 0.8 в 2014 — GAIN KZ2025-0010; рапс 19+ ц/га).
  LGBM, обученный на <=2020, на hold-out 2021–2025 для этих культур ХУЖЕ бейзлайна
  (см. metrics/metrics.json: below_baseline=true) — фиксируем честно, без подгонки.
- **Районная урожайность = областной якорь × агрозональный коэффициент**
  (север 1.02–1.06, юг 0.92–0.98; среднее ~1.0). Районные длинные ряды БНС
  публично не разбиты — это задокументированный даунскейлинг, НЕ наблюдение.
  Областные средние точно равны якорям БНС 2022–2024 (проверено в fetch_stat.py).
- **NASA heat_days_gt30 — оценка из месячных means** (эвристика в fetch_nasa.py);
  точный heat30 в панели — из Open-Meteo daily.
- **Open-Meteo soil_moisture daily не существует** (API 400) — взят hourly
  `soil_moisture_3_9cm`, усреднён до сезона (`sm_mean` в openmeteo_summary.csv,
  в панель не входит).
- Сезон панели: Open-Meteo окно 15.05–31.08; NASA — календарный MJJA (05–08).
  Климатология аномалии p30_anom — норма осадков 2005–2020 того же района.

## Покрытие и качество
- Строк: **{n_rows}** (v2: 10 районов × 21 год × 6 культур = 1260; v1 было 420).
- NaN в `yield_c_ha`: **{int(miss['yield_c_ha'])}** (требование: 0). Полные NaN по колонкам:

| column | n_missing |
|---|---|
{miss_txt}

- Проверки пайплайна: схема колонок точна; inner-join район-год без потерь;
  климат 2005–2025 непрерывен; `python src/fetch_all.py` падает громко при любой ошибке API.

## Воспроизведение (Windows PowerShell, чистая машина)
```powershell
pip install -q pandas numpy requests pyyaml openmeteo-requests requests-cache retry-requests
python src/fetch_all.py
```

## Проверка результата
```powershell
python -c "import pandas as pd; df=pd.read_csv('data/processed/akmola_panel.csv'); print(df.shape); print(df['yield_c_ha'].isna().sum()); print(df.head(5).to_string())"
Get-ChildItem data/raw, data/processed
```

## Пример (первые 5 строк)
{sample}

## Сырые артефакты
- `data/raw/stat_yield.csv` (year,district,crop,yield_c_ha,source)
- `data/raw/nasa_<EN>.json` ×10, `data/raw/nasa_summary.csv`
- `data/raw/openmeteo_<EN>_daily.json` ×10, `data/raw/openmeteo_summary.csv`
- `data/ndvi/ndvi_timeseries.json` (v2: список сцен Sentinel-2, ndvi_mean=MISSING)
"""
    CARD.write_text(card, encoding="utf-8")
    log.info("WROTE %s", CARD)


def main() -> None:
    try:
        RAW.mkdir(parents=True, exist_ok=True)
        PROC.mkdir(parents=True, exist_ok=True)
        (RAW / ".gitkeep").touch(exist_ok=True)
        (PROC / ".gitkeep").touch(exist_ok=True)

        run_step("stat (BNS anchors)", SRC / "fetch_stat.py")
        run_step("nasa (POWER)", SRC / "fetch_nasa.py")
        run_step("openmeteo (Archive)", SRC / "fetch_openmeteo.py")

        log.info("=" * 70)
        log.info("STEP: merge features -> akmola_panel.csv")
        import sys as _sys
        _sys.path.insert(0, str(SRC))
        from features import build_panel

        stat = pd.read_csv(RAW / "stat_yield.csv")
        nasa = pd.read_csv(RAW / "nasa_summary.csv")
        om = pd.read_csv(RAW / "openmeteo_summary.csv")
        panel = build_panel(stat, nasa, om)
        if list(panel.columns) != EXPECTED_COLS:
            raise ValueError(f"Bad panel columns: {list(panel.columns)}")
        if len(panel) <= 50:
            raise ValueError(f"Too few rows: {len(panel)} (need >50)")
        if panel["yield_c_ha"].isna().any():
            raise ValueError("NaN in yield_c_ha — FAIL")
        panel.to_csv(PANEL, index=False)
        log.info("WROTE %s rows=%d years=%d-%d districts=%d",
                 PANEL, len(panel), panel["year"].min(), panel["year"].max(),
                 panel["district"].nunique())
        print(panel.head(5).to_string(index=False))
        write_data_card(panel)
        log.info("PIPELINE OK")
    except SystemExit:
        raise
    except Exception as e:
        log.exception("FATAL fetch_all failed (loud fail, no mocks): %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
