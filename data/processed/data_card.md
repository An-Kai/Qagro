# Data Card — akmola_panel.csv (Qagro, Трек 2)

Панель «район × год × культура» для Акмолинской области:
урожайность + сезонные агроклиматические признаки (май–август).
Назначение — MVP прогноза урожайности, триггеров засухи и агро-дашборда.

Файл: `data/processed/akmola_panel.csv` — **420 строк**, 2005–2025,
10 районов, 2 культуры (barley, spring_wheat — по 210 строк).
Схема: `year,district,district_en,lat,lon,crop,yield_c_ha,tmean_mjja,precip_mjja,gdd5,heat30,dry_max,et0,p30_anom`.
Единицы: yield — ц/га (вес после доработки); tmean — °C (MJJA);
precip — мм; gdd5 — °C·сут (base 5); heat30 — дни tmax>30;
dry_max — дни (осадки<1мм); et0 — мм (FAO); p30_anom — % к норме 2005–2020.

Источники (без выдуманных данных):
1. Урожайность — Бюро нацстатистики РК (stat.gov.kz): таблицы Акмолы
   + валовой сбор 2024 (зерновые 25 204.8 тыс.т, 15.2 ц/га). Якоря пшеницы:
   2022 — 12.8, 2023 — 9.2, 2024 — 14.2 ц/га (APK-Inform).
2. Акимат Акмолы / primeminister.kz: 2024 — 6.6 млн т; 2025 — 7.6 млн т,
   16.3 ц/га, >70% 3 класс.
3. FAOSTAT QCL + USDA FAS GAIN: валидация ряда 2005–2021
   (засухи 2010/2012/2019/2021, рекорд 2011; barley avg 1.445 т/га).
4. NASA POWER Monthly (MERRA-2, AG), 2005–2025: T2M/PRECTOTCORR и др.
   Сырое: `data/raw/nasa_<EN>.json`, агрегаты: `nasa_summary.csv`.
5. Open-Meteo Archive (ERA5): daily tmax/tmin/precip/ET0,
   2005-01-01–2025-08-31, Asia/Almaty. Сырое: `openmeteo_*_daily.json`.
6. Координаты — `config/districts.yaml` (центроиды WGS84, OSM).

Ограничения (читать перед моделированием):
- 2025 yield — предварительный (якорь 15.8/16.8 ц/га × агрокоэф.).
- Районная урожайность = областной якорь × коэффициент
  (север 1.02–1.06, юг 0.92–0.98). Это даунскейлинг, НЕ наблюдение.
- heat30 в панели — из Open-Meteo daily (точный); NASA-оценка — эвристика.
- Open-Meteo soil_moisture для Акмолы вернул null (проверено 18.09.2026),
  в панель не входит, на риск не влияет (только precip/heat/dry).
- Окно: Open-Meteo 15.05–31.08; NASA — MJJA (05–08).

Качество: NaN в `yield_c_ha` — **0**; все колонки без пропусков;
схема точна; join район-год без потерь; климат 2005–2025 непрерывен.

Воспроизведение: `pip install -q pandas numpy requests pyyaml openmeteo-requests requests-cache retry-requests`
затем `python src/fetch_all.py`.
Проверка: `python -c "import pandas as pd; df=pd.read_csv('data/processed/akmola_panel.csv'); print(df.shape)"`
Ожидается `(420, 14)`.

Сырые артефакты: `data/raw/stat_yield.csv`, `nasa_*.json`, `nasa_summary.csv`,
`openmeteo_*_daily.json`, `openmeteo_summary.csv`.
