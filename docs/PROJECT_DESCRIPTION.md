# Qagro — описание проекта

> Источник правды по числам: `metrics/metrics.json`, `metrics/intervals.json`,
> `metrics/summary.csv`. Остальные числа — из файлов, указанных в скобках.
> Если число не удалось проверить — стоит пометка «см. \<файл\>».

## 1. Что такое Qagro

Qagro — MVP системы поддержки решений для фермеров и агроаналитиков
Акмолинской области: прогноз урожайности на 2026 год на уровне района,
декадный индекс риска засухи (светофор 🟢🟡🔴), индексное страхование
(P_loss, ожидаемая выплата) и рекомендации по севу — на 3 языках (RU/KZ/EN)
(см. `README.md`, `docs/SUBMISSION.md`).

Треки и задачи (см. `README.md`, `docs/SUBMISSION.md`):

- **Трек 2 (AgriTech AI): 2.1** — прогноз урожайности (бленд LightGBM+Ridge
  против бейзлайна «среднее 5 лет», hold-out 2021–2025, прогноз 2026
  с интервалом + SHAP); **2.2** — риски засухи (декадный индекс Open-Meteo,
  светофор, карта); **2.4** — страхование + рекомендации + интерфейсы
  (API / Telegram-бот / веб / PDF) + платформа v4 (Мои поля, журнал, spray,
  NPK, экономика).
- **Трек 1 (GIS): 1.1** — NDVI-мониторинг всходов по контуру поля;
  **1.2** — границы/площади из OSM с экспортом; **1.3** — залежи (amplitude);
  **1.4** — гибель (dead_share) — Sentinel-2 через PC STAC, Copernicus Browser /
  Sentinel Hub для ручной проверки, LandsatLook/USGS для сверки.

Карта покрытия MVP: **10 районов × 6 культур**, панель 2005–2025, прогноз — 2026
(см. `config/districts.yaml`, `data/processed/data_card.md`).
Районы: Зерендинский (Zerenda), Бурабайский (Burabay), Атбасарский (Atbasar),
Есильский (Esil), Жаксынский (Zhaksy), Шортандинский (Shortandy),
Целиноградский (Tselinograd), Сандыктауский (Sandyktau),
Буландынский (Bulandy), Кокшетау (Kokshetau).
Культуры: spring_wheat (пшеница яровая), barley (ячмень), oats (овёс),
sunflower (подсолнечник), rapeseed (рапс), flax (лён масличный).

## 2. Архитектура

```text
Источники (БНС, NASA POWER,           Панель                       Модель
 Open-Meteo ERA5, FAOSTAT,            район × год × культура        бленд
 OSM, SoilGrids, Sentinel-2,          2005–2025                     LightGBM+Ridge
 AgroData, Qoldau)                    (см. data_card.md)
      |                                    |                            |
      | src/fetch_*.py                     | src/features*.py           | src/train.py
      | (fetch_all оркестратор)            | (features → extra → v4)    | src/evaluate.py
      v                                    v                            | src/intervals.py
+----------------+              +------------------+                    v
| data/raw/*.json| ───────────▶ | akmola_panel_v4  | ───────▶ models/lgbm_*.pkl
| config/*.yaml  |   громкие    | .csv (1260 строк,|  hold-out      + metrics/*.json
+----------------+   ошибки,    | 0 NaN в yield)   |  2021–2025
                     без моков  +------------------+  (read-once)
                                                        |
                          +-----------------------------+-----------------------------+
                          |                             |                             |
                          | src/api.py                  | src/bot.py                  | app/streamlit_app.py
                          v                             v                             v
                   ┌─────────────┐              ┌──────────────┐              ┌──────────────────┐
                   │ FastAPI     │              │ Telegram-бот │              │ Streamlit-дашборд│
                   │ /predict    │              │ aiogram 3.x  │              │ Plotly + Folium  │
                   │ /report→PDF │              │ + кнопка PDF │              │ CSV/GeoJSON/PDF  │
                   └─────────────┘              └──────────────┘              └──────────────────┘
```

Файлы на стрелках: `src/fetch_all.py` (источники → raw → панель),
`src/features.py` + `src/features_extra.py` + `src/features_v4.py`
(фичи панели), `src/train.py` → `models/lgbm_*.pkl`,
`src/predict.py` + `src/risk.py` + `src/insurance.py` + `src/recommend.py`
(модель → ответы трёх интерфейсов), `src/report_pdf.py` (PDF для API и бота).

## 3. Функции по модулям

| Модуль | Назначение | Вход → выход |
|---|---|---|
| `src/fetch_stat.py` | Урожайность БНС 2005–2025 (6 культур, якоря + source) | stat.gov.kz → `data/raw/stat_yield.csv` |
| `src/fetch_nasa.py` | NASA POWER Monthly (MERRA-2) → сезонные агрегаты MJJA | lat/lon → `data/raw/nasa_*.json` |
| `src/fetch_openmeteo.py` | Open-Meteo Archive daily → сезонные агрегаты + soil hourly | lat/lon → `data/raw/openmeteo_*_daily.json` |
| `src/fetch_area.py` | Посевные площади stat.gov.kz 2005–2025 | API БНС → `data/raw/sown_area.csv` |
| `src/fetch_all.py` | Оркестратор пайплайна, громкие ошибки API | запуск шагов → `akmola_panel.csv` + data_card |
| `src/features.py` | Слияние stat + NASA + Open-Meteo в панель | raw → `akmola_panel.csv` |
| `src/features_extra.py` | v3 extra-фичи из скачанных raw (без новых загрузок) | панель v2 → `akmola_panel_v3.csv` |
| `src/features_v4.py` | Фичи v4: площади, ГТК Селянинова, SoilGrids, trend_sq/trend_recent/oilshare_trend | панель v3 → `akmola_panel_v4.csv` |
| `src/features_ndvi.py` | Optional NDVI-join (только настоящие NDVI без NaN) | панель + ndvi json → +`ndvi_max` или пропуск |
| `src/train.py` | Обучение бленда LightGBM+Ridge per-crop + бейзлайн (train ≤2020) | панель v4 → `models/lgbm_*.pkl`, `baseline.json` |
| `src/evaluate.py` | Hold-out 2021–2025: бейзлайн vs бленд + scatter + SHAP top-3 | бандлы → `metrics/metrics.json`, plots, shap |
| `src/intervals.py` | Конформные интервалы из OOF-остатков | бандлы → `conformal.json`, `intervals.json` |
| `src/predict.py` | Прогноз 2026: `predict_yield(district, crop, weather)` + 80% интервал + SHAP top-3 | район/культура/погода MJJA → `{y_pred, lo10, hi90, factors}` (+`experimental:true` для below_baseline) |
| `src/risk.py` | Декадный индекс засухи (15 декад, май–сентябрь; 0.4·precip_deficit+0.35·heat+0.25·dry; 🟢<35 🟡35–60 🔴>60) | Open-Meteo live → `{decades, seasonal_risk}`; офлайн — RuntimeError |
| `src/insurance.py` | Индексная страховка decision support (strike 0.8·mean5, P_loss через N(y_pred, resid_std), payout; НЕ тариф) | район/культура → `{p_loss, expected_payout_ha, mean5, y_pred}` |
| `src/recommend.py` | Окно сева RU/KZ/EN (пороги p30<−20%, heat30>15; окна 8–15 / 12–18 / 12–20 / 15–25 мая) | район/культура/lang → `{window, message}` |
| `src/approx_crops.py` | APPROX-fallback: масштаб от пшеницы + цены-индикаторы, флаг `approx` | район/культура без модели → прогноз-приближение |
| `src/api.py` | FastAPI: GET/POST endpoints (см. §8), кэш predict 5 мин | HTTP → JSON / PDF |
| `src/bot.py` | Telegram-бот aiogram 3.x (токен только из `TELEGRAM_BOT_TOKEN`), SQLite-кэш 24 ч | команды/кнопки/геолокация → прогноз + PDF |
| `src/gis_monitor.py` | Трек 1: NDVI-серии полей через PC TiTiler; классы cultivated/likely_fallow/sparse; dead_share | OSM-поля + сцены → `data/gis/gis_*.json` |
| `src/sentinel_ndvi.py` | Поиск сцен Sentinel-2 L2A через PC STAC (без ключа), keep-механика C7/C8/C9 | STAC → `data/ndvi/ndvi_timeseries.json` |
| `src/report_pdf.py` | Общий PDF-билдер для API и бота (ReportLab, кириллица DejaVu/Arial) | full-результат → bytes PDF |
| `src/spray.py` | Окно опрыскивания по живому Open-Meteo (час хорош: ветер<5 м/с, осадки=0, 10–25 °C) | район → `{next_good_hours, verdict_*}` |
| `src/fetch_agrodata.py` | Сверка с Казгидромет AgroData (drought сырьём без вердикта, productivity диапазоны) | live AgroData → `compare_agrodata` |
| `src/fields_osm.py` | Реальные поля через Overpass API (+6 честных demo 1×2 км) | Overpass → `data/fields/akmola_osm_fields.geojson` |
| `src/soil.py` | SoilGrids v2.0: N/pH/SOC/clay по 10 районам | SoilGrids API → `data/processed/soil.csv` |
| `src/sowing_calendar.py` | Посевной календарь Акмолы (справочник, source=agro-practice) | культура/lang → `{окна, gdd_norm}` |
| `src/guide_data.py` | Справочник + жалобы словами (`lookup`/`search_guide`/`ABIOTIC`) | культура или текст → записи (`/guide <саранча|засуха|…>`) |
| `src/logistics.py` | Ближайший элеватор (haversine) | район → элеватор + км |
| `src/alerts.py` | Агроалерты по прогнозу Open-Meteo (заморозки/жара/ливни, 7 дней) | район → список алертов |
| `src/myfields.py` | «Мои поля» фермера (CRUD, платформа v4) | имя/lat/lon/площадь → запись поля |
| `src/journal.py` | Журнал наблюдений (проблемы из PROBLEM_TYPES) | field_id/текст → заметка |
| `src/fertilizer.py` | Ориентировочный NPK под плановую урожайность | культура/цель/почва → `{N,P,K}` |
| `src/economics.py` | Прибыль с гектара | урожай/цена/затраты → profit_ha |
| `src/platform_api.py` | Роутер платформы: `/myfields`, `/journal`, `/spray` | HTTP → JSON |
| `app/streamlit_app.py` | Веб-дашборд: 3 шага + вкладки (см. §8), токены `DESIGN.md` | клики → прогноз/карты/PDF |
| `scripts/build_presentation.py` | Сборка `docs/Qagro_presentation.pdf` (10 слайдов) из проверяемых данных | metrics + risk_example → PDF |
| `scripts/regen_risk_example.py` | Обновление МОДЕЛЬНЫХ записей `reports/risk_example.json` | insurance/recommend → json |
| `scripts/fetch_ndvi_district.py` | Добрать настоящие NDVI района (самое большое OSM-поле → STAC → TiTiler, дедуп) | район → допись в ndvi json |

## 4. Принципы

- **no-mock / loud-fail.** Неизвестный район/культура, неполная погода,
  недоступность API — это `ValueError`/`RuntimeError`/`FileNotFoundError`,
  а не выдуманные цифры (см. `src/predict.py`, `src/risk.py`, `src/fetch_all.py`).
- **Hold-out дисциплина.** Train — годы ≤2020 (финальные бандлы; зерновые
  n_train=150 за 2006–2020, масличные n_train=130 за 2008–2020 — лаги съедают
  ранние годы), hold-out 2021–2025 (n=50 на культуру) читается один раз
  в `src/evaluate.py` (см. `docs/MODEL_AUDIT.md`).
- **Train-only отбор.** `SelectKBest(f_regression, k=10)` per-crop + веса бленда
  по train-CV `TimeSeriesSplit(5)` — только на ≤2020; `year_trend`
  принудительно в наборе (см. `src/train.py`).
- **Conformal-интервалы + эмпирическое покрытие.** Интервал прогноза —
  эмпирические квантили OOF-остатков (`metrics/conformal.json`: lo=y_pred+q10,
  hi=y_pred+q90); фактическое покрытие на hold-out — только факт
  из `metrics/intervals.json` (см. §6). **Номинал 0.80 не заявляется.**
- **experimental-флаг.** Культуры с `below_baseline:true` в `metrics.json`
  (только лён): прогноз = baseline mean5 за 5 лет, интервал ×1.5
  (`WIDE_FACTOR`), флаг `experimental:true` в `predict.py`/`insurance.py`.
- **Офлайн-first.** Прогноз по умолчанию — нейтральный сценарий (средний MJJA
  2016–2025 района из панели); живой Open-Meteo — best-effort; SQLite-кэш 24 ч,
  кэш predict API 5 мин (см. `src/api.py`, `src/bot.py`).
- **Трилингва RU/KZ/EN.** Все видимые строки — через словари `UI[lang]` /
  `T[...]` с паритетом ключей; техкоды (`Esil`, `P_loss`) — только мелким
  капшеном (см. `DESIGN.md`, `app/streamlit_app.py`, `src/bot.py`).
- **DESIGN.md-токены.** Единственный акцент `--qagro-accent: #1B7A3D`;
  текст `#111111`, подписи `#333333`, фон `#FFFFFF`, карточки `#F2F5F1`;
  риск красный `#C0392B` / янтарь `#D48806`; радиус 12px; шрифт
  Inter / Segoe UI; отступы кратны 8; кнопки min-height 60px width 100%;
  шаги H1 36 / H2 30 / H3 26 / текст 20 / подпись 18; цифры ответа 46 bold
  tabular-nums; без градиентов и теней (см. `DESIGN.md`).

## 5. Данные и ресурсы

| Источник | Что взято | Права / лицензия | Файл в репо |
|---|---|---|---|
| БНС РК stat.gov.kz (динамические таблицы Акмолы + валовой сбор 2024) | Областные якоря урожайности зерновых/пшеницы/ячменя; нац. якоря 2022–2024 | Открытые официальные данные, с указанием источника | `data/raw/stat_yield.csv` → `data/processed/akmola_panel_v4.csv` |
| NASA POWER Monthly Point (MERRA-2, community=AG), 2005–2025 | T2M/T2M_MAX/T2M_MIN/PRECTOTCORR/RH2M/ALLSKY_SFC_SW_DWN/WS2M/GWETTOP | Открытый API NASA | `data/raw/nasa_*.json` |
| Open-Meteo Archive (ERA5) + Forecast 16d, Asia/Almaty | Daily tmax/tmin/precip/ET0 FAO 2005-01-01–2025-08-31, hourly soil_moisture_3_9cm | Открытый API, CC-BY 4.0, атрибуция | `data/raw/openmeteo_*_daily.json` |
| FAOSTAT QCL + USDA FAS GAIN PSD | Валидация формы ряда 2005–2021 (засухи 2010/2012/2019/2021, рекорд 2011; barley avg 1.445 т/га) | Открытые данные FAO/USDA | сверка (колонка source в stat_yield), см. `data_card.md` |
| OSM / Geofabrik Kazakhstan | Центроиды 10 районов; 109 реальных полигонов `landuse=farmland` | ODbL | `config/districts.yaml`, `data/fields/akmola_osm_fields.geojson` |
| Sentinel-2: PC STAC (L2A, без ключа) + Copernicus Browser / Sentinel Hub | Поиск сцен cloud<20%; ручной B04/B08, NDVI=(B08−B04)/(B08+B04) | Открытый STAC; скачивание после бесплатной регистрации | `data/ndvi/ndvi_timeseries.json` |
| SoilGrids v2.0 | N/pH/SOC/clay по 10 районам (статика, без времени) | Открытый API | `data/processed/soil.csv` |
| Казгидромет AgroData (без ключа) | drought (сырой индекс), moisture, productivity (диапазоны ц/га); towns/stations справочно | Открытый API | live-сверка, файла нет (см. `src/fetch_agrodata.py`) |
| Qoldau granaries-map | Перечень 12 элеваторов (координаты оценочные по OSM) | Публичная карта | `data/fields/granaries.json` |
| Акимат Акмолы / primeminister.kz / ElDala / APK-Inform / margin.kz | Кросс-чек 2024–2025: 6.6 млн т (2024), 7.6 млн т / 16.3 ц/га (2025) | Открытые публикации | ссылки в `data/processed/data_card.md` |

Сторонний OSS (только подходы, код Qagro оригинальный; см. `README.md`):
UniCrop (MIT, MJJA-фичи + LightGBM + SHAP), gsanaev/crop-yield-prediction
(MIT, регрессия по климату), WeatherWatch-паттерн (доки Open-Meteo, декадный
мониторинг), CropBot/mishagrol (MIT, UX-образец Telegram-бота).
ИИ-ассистенты (указаны в `README.md` по ТЗ): код написан командой с помощью
OpenCode на модели Muse Spark (планирование, кодогенерация, ревью) и web-поиска;
ML-логика и метрики — оригинальные, на реальных данных.

## 6. Модель и метрики

Модель v4: per-crop бленд LightGBM+Ridge (веса по train-CV; ключ `lgbm`
в `metrics.json` = метрики бленда). Бейзлайн: среднее пред. 5 лет
по району+культуре (только прошлое). Hold-out 2021–2025, n=50 на культуру.
Цифры — только из `metrics/metrics.json` и `metrics/intervals.json`:

| Культура | Бейзлайн MAE / RMSE / R² | Бленд MAE / RMSE / R² | n | Статус | Покрытие conformal / gauss |
|---|---|---|---|---|---|
| Пшеница яровая | 2.68 / 2.89 / −0.26 | 1.20 / 1.49 / 0.66 | 50 | ✅ strong | 0.66 / 0.64 |
| Ячмень | 2.78 / 3.00 / −0.26 | 1.27 / 1.58 / 0.65 | 50 | ✅ strong | 0.60 / 0.62 |
| Овёс | 3.59 / 4.00 / −0.33 | 1.37 / 1.79 / 0.74 | 50 | ✅ strong | 0.58 / 0.60 |
| Подсолнечник | 2.52 / 3.69 / −0.35 | 2.01 / 2.83 / 0.21 | 50 | ✅ strong (по MAE) | 0.48 / 0.48 |
| Рапс | 3.70 / 4.26 / −0.85 | 3.31 / 4.18 / −0.79 | 50 | ✅ strong (по MAE; оговорка: R² слабый, покрытие 0.04) | 0.04 / 0.08 |
| Лён | 1.22 / 1.44 / −0.05 | 1.32 / 1.67 / −0.42 | 50 | 🧪 experimental (`below_baseline:true`) | 0.24 / 0.26 |

Итого: 5/6 strong, лён — честный EXPERIMENTAL baseline-5y (см. `metrics/METRICS.md`,
`metrics/summary.csv`). Покрытие интервалов — факт hold-out; номинал 0.80
не заявляется (см. `metrics/intervals.json`). Графики: `metrics/plots/scatter_*.png`,
SHAP: `metrics/shap_*.json`.

## 7. NDVI-подсистема

Цепочка: **PC STAC-поиск** (`src/sentinel_ndvi.py`: сцены Sentinel-2 L2A,
июнь–август, cloud<20%) → **PC TiTiler** (`src/gis_monitor.py`: POST
`/item/statistics`, assets B04&B08, expression `(B08−B04)/(B08+B04)` по bbox поля)
→ **`data/ndvi/ndvi_timeseries.json`** — записи
`{district, date, ndvi_mean, scene_id, status}` (`status`: `listed…` —
сцена найдена, `error:…` — STAC недоступен; `ndvi_mean=None` = MISSING,
число не выдумывается).

Keep-механика (`src/sentinel_ndvi.py`, `scripts/fetch_ndvi_district.py`):
**C7** — ранее полученные настоящие `ndvi_mean` при перезапуске не затираются
в None (дописываются как есть, `| kept on rerun`); **C8** — записи районов
вне `DEMO_FIELDS` (напр. Zhaksy) дописываются (`| kept (district not in
DEMO_FIELDS)`); **C9** — ключ дедупа **(district, scene_id)**, а не голый
scene_id: один тайл покрывает несколько районов, а NDVI посчитан по bbox
конкретного района — перенос чужого значения запрещён.
Фактические counts — см. `data/ndvi/ndvi_timeseries.json` (в `README.md` /
`docs/SUBMISSION.md` зафиксированы более ранние срезы 62 сцены / 41 real).
Район без сцен = честный `no_data` («все запросы неуспешны», см. `gis_monitor.py`;
в вебе — «Нет данных NDVI», `T["gis_no_data"]`).
Модель обязана работать без NDVI: optional join в `src/features_ndvi.py`
(`ndvi_max` добавляется только при настоящих NDVI без NaN; на train≤2020 —
100% NaN, фичи корректно исключены отбором — см. `docs/MODEL_AUDIT.md`).

## 8. Интерфейсы

**API** (`src/api.py` + `src/platform_api.py`):
`GET /health`, `/metrics`, `/version`, `/districts`, `/fields`, `/granaries`,
`/calendar`, `/agrodata`, `/alerts`, `/guide`, `/fertilizer`, `/economy`,
`/soil`, `/intervals`, `/gis`, `/compare`, `/season`;
`POST /predict` (`{district_en, crop, [lang, weather, year, include_risk]}` →
`{y_pred, lo, hi, factors, p_loss, payout, risk, rec, approx, insurance, meta}`;
кэш 5 мин, `?fresh=true` — мимо кэша, заголовок `X-Qagro-Cache: HIT/MISS`);
`POST /report` (→ PDF); платформа: `GET/POST /myfields`,
`DELETE /myfields/{field_id}`, `GET/POST /journal`, `GET /spray`.

**Бот** (`src/bot.py`): `/start` → язык (RU/KZ/EN) → район (10 кнопок) →
культура (6) → прогноз + интервал + светофор + страховка + рекомендация +
кнопки 📄 PDF / 🔄 Новый прогноз; дополнительно `/help`, `/about`, `/more`,
`/gis` (поля со спутника), `/spray` (окно 48 ч), `/guide <жалоба>` (совет),
`/fields` (115 полей), `/elevators` (12), `/alerts` (угрозы 7 дней),
`/compare` (2 культуры рядом); кнопка геолокации → ближайший район (haversine);
токен только из `TELEGRAM_BOT_TOKEN`.

**Веб** (`app/streamlit_app.py`): 3 шага (1. район → 2. культура → 3. ответ
простыми словами; техдетали только в «Подробно для агронома») + сравнение
культур + сезонный календарь + выгрузки CSV / GeoJSON / PDF.
Вкладки: 🟢🟡🔴 «Риски», «Поля и элеваторы», «Со спутника»;
«Для агронома», «Моё хозяйство», «Справочник и деньги»,
«Сравнение культур», «Календарь и алерты», «О проекте».

## 9. Ограничения

- **Район = даунскейлинг области.** Районных длинных рядов БНС в открытом
  доступе нет; районная урожайность = областной якорь × агрозональный
  коэффициент (север 1.02–1.06, юг 0.92–0.98). Центроиды из
  `config/districts.yaml` — не границы и не поля (см. `README.md`, `data_card.md`).
- **Рапс: strong по MAE с оговоркой.** MAE-критерий пройден (3.31<3.70),
  но R² −0.79 и покрытие интервала 0.04 — систематическое недопредсказание
  (bias +3.3), интервалы занижены (см. `metrics/`, `docs/MODEL_AUDIT.md`).
- **Лён — experimental.** Структурный сдвиг 2024–2025, бленд хуже бейзлайна:
  прогноз = mean5, интервал ×1.5, флаг `experimental:true` (см. `metrics.json`).
- **NDVI-покрытие по районам.** Настоящие `ndvi_mean` есть не для всех районов;
  район без сцен = честный no_data; модель работает без NDVI (см. §7).
- **Страховка — decision support, не тариф.** Цены-ориентиры (пшеница/ячмень
  95 000 тг/т из конфига; овёс/подсолнечник/рапс/лён — индикаторы
  из `src/approx_crops.py`); формула
  `max(0, 0.8·mean5 − y_pred)/10·price·subsidy`, subsidy 0.8
  (см. `src/insurance.py`).
- **Покрытие интервала ниже номинала.** Факт hold-out 0.04–0.66 против
  номинала 0.80 — номинал не заявляем (см. `metrics/intervals.json`).
- **2025 yield — предварительный** (якорь 15.8/16.8 ц/га); soil_moisture ERA5
  для Акмолы в Archive API = null — в панель не входит (см. `data_card.md`).
- **Поля/элеваторы.** 115 полей: 109 реальных OSM (ODbL) + 6 demo (`demo:true`);
  12 элеваторов — координаты оценочные (см. `README.md`).
