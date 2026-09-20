# Qagro — outline презентации v4 (10 слайдов, 20.09.2026)

Источник правды: `metrics/metrics.json` (hold-out 2021–2025, n=50), `metrics/METRICS.md`,
`data/processed/akmola_panel_v4.csv` (1260×33), `data/fields/akmola_osm_fields.geojson` (115),
`data/ndvi/ndvi_timeseries.json` (41 real: June+July+Aug), `src/platform_api.py` + `src/spray.py` + `src/fertilizer.py` + `src/economics.py`.
PDF-бинарь `docs/Qagro_presentation_v2.pdf` НЕ пересобирается в этом цикле (заморожен, отдельный цикл шрифтов).

## Слайд 1. Проблема
- Акмола — житница KZ: засухи 2010/2012/2019/2021 роняли урожай вдвое; решения — постфактум.
- Фермеру не хватает: локального прогноза, раннего сигнала засухи, честной страховки.
- Цена ошибки — −30–50% выручки за сезон.
- Картинка: карта Акмолинской области + мини-график просадок урожайности из панели.

## Слайд 2. Решение
- Qagro: прогноз 2026 по району + декадный светофор риска + страховка + совет по севу (RU/KZ/EN).
- Три входа: Telegram-бот, FastAPI, Streamlit-дашборд с PDF/CSV/GeoJSON.
- Decision support, не «чёрный ящик»: интервал + SHAP-факторы + формула риска.
- Платформа v4: Мои поля + журнал + spray-окно + NPK + экономика (подробно — слайд 8).
- Картинка: схема «данные → модель → риск → страховка → платформа → бот/веб/PDF».

## Слайд 3. Демо
- Путь за 30 сек: /start → язык → Есильский → пшеница → прогноз + 🟡 + 51 тг/га + PDF.
- Живой пример Esil vs Zerenda (🟡 35.0 vs 🟢 28.5).
- Платформа за 20 сек: /spray (окно 48ч), Мои поля + журнал, NPK под цель + прибыль/га.
- QR на бота + ссылка на Streamlit.
- Картинка: скриншоты бота (язык/район/карточка прогноза/spray) + `reports/risk_example.json`.

## Слайд 4. Данные
- Панель v4 `akmola_panel_v4.csv`: **1260 строк** (10 районов × 21 год × 6 культур), **33 колонки** (v3 + площади stat.gov.kz + ГТК + SoilGrids); БНС-якоря + NASA POWER + Open-Meteo ERA5.
- Фичи MJJA: tmean/precip/GDD5/heat30/dry_max/ET0/p30_anom + lat/lon/yield_lag1 + v3 (dtr/vpd_proxy/spei_proxy/year_trend/yield_roll3) + v4 (oilseeds_share/площади/htc_mjja/soil_N/pH/SOC/clay) + ndvi_max/ndvi_flag (optional join).
- Поля: **115 полигонов** (`akmola_osm_fields.geojson`): **109 OSM real** (ODbL, Overpass `landuse=farmland`) + 6 demo-fallback `demo:true` (Esil 3, Kokshetau 3).
- NDVI Sentinel-2: **22 NDVI real (June+July)** + 19 августовских (стало 41/62; PC TiTiler B08/B04) + Landsat cross-check (июль delta +0.004); остальное `ndvi_mean=None` (MISSING, без выдумок).
- Честно: район = даунскейлинг области на центроиды `config/districts.yaml`.
- Картинка: схема панели + таблица первых строк из `data/processed/data_card.md` + мини-карта полей.

## Слайд 5. Модель
- Бейзлайн = среднее 5 лет; модель v4 = бленд LightGBM+Ridge, веса per-crop по train-CV (hold-out 2021–2025, n=50, ключ `lgbm` сохранён для совместимости).
- Прогноз 2026: y_pred + 80% интервал из эмпирических квантилей OOF (conformal q10/q90; experimental ×1.5) + топ-3 SHAP; факт. покрытие wheat 0.66 (номинал 0.80 не заявляем).
- **5/6 strong + 1 experimental (лён)**: честный EXPERIMENTAL baseline-5y только при `below_baseline=true`; APPROX — только если модели нет вообще (legacy, не используется для 6 культур).
- SoilGrids: retry по точкам пашни закрыл 10/10 → soil-фичи в модели v4 (вклад малый, климат+тренд несут сигнал).
- Картинка: блок-схема `src/train.py → src/predict.py` + SHAP топ-3 (`metrics/shap_*.json`).

## Слайд 6. Метрики
- Пшеница v4: бейзлайн MAE 2.68 / R² −0.26 → бленд **MAE 1.20 / R² 0.66**.
- Ячмень v4: бейзлайн 2.78 / −0.26 → бленд **1.27 / 0.65**; овёс: 3.59 / −0.33 → **1.37 / 0.74** (hold-out 2021–2025, n=50).
- 5/6 strong (пшеница, ячмень, овёс, подсолнечник MAE 2.01<2.52 при R² 0.21, рапс MAE 3.31<3.70 при R² −0.79 с оговоркой); только лён — EXPERIMENTAL baseline (MAE 1.33, R² −0.42, `below_baseline:true`, структурный сдвиг 2024–2025).
- Картинка: `metrics/plots/scatter_spring_wheat.png` + `metrics/plots/scatter_barley.png` + `metrics/plots/scatter_oats.png` + таблица метрик.

## Слайд 7. Эффект (тг/га)
- Esil/пшеница: P_loss 0.02, expected payout **51 тг/га**; Zerenda/пшеница: 0.02, **52 тг/га**.
- Ранний сигнал (🟡/🔴 декады июля) → сдвиг сева 12–18 мая + влагосбережение.
- Экономика v4 (`src/economics.py`): выручка = ц/га/10 × цена; прибыль = выручка − себестоимость (default 65000 тг/га, editable); рентабельность %.
- NPK v4 (`src/fertilizer.py`, `source=agro-norms`): вынос кг д.в./ц (пшеница 3.5/1.2/2.5 и др.) × цель + поправка на фон low×1.2/med×1.0/high×0.8, без брендов.
- Картинка: карточки `Esil_insurance_wheat` vs `Zerenda_insurance_wheat` из `reports/risk_example.json` + формула прибыли.

## Слайд 8. Масштаб / платформа v4
- Сегодня: 10 районов Акмолы, 6 культур, 3 языка, Docker (api+bot+web).
- Поля и карты: 115 полей на Folium (фильтр OSM/demo + статистика га), элеваторы `granaries.json` + маршруты, точки NDVI 🟣 (июнь 2024).
- Платформа фермера v4 (без сети-моков, только живые API + SQLite):
  - Мои поля (`src/myfields.py`, `data/myfields.db`, lat 50–54 lon 65–72, 1–2000 га);
  - журнал (`src/journal.py`, таблица notes: weeds/pests/disease/lodging/drought/other);
  - spray-окно 48ч (`src/spray.py`, живой Open-Meteo: wind<5 м/с + precip==0 + 10–25°C);
  - NPK + экономика (см. слайд 7);
  - API: `GET/POST /myfields`, `GET/POST /journal`, `GET /spray`, `GET /fertilizer`, бот `/spray` + кнопка 🧴Spray, Streamlit «🚜 Моё хозяйство» + «🔬 Справочник и деньги», PDF раздел 6 Farm&money.
- Завтра: все области KZ (тот же пайплайн `src/fetch_all.py`), официальные поля map.iaqmola.kz вместо OSM-fallback.
- Картинка: Folium-карта рисков + полей (10 центроидов, 115 полигонов) из Streamlit + стрелка «Акмола → весь KZ».

## Слайд 9. Команда
- Команда **Qagro**: Kairbek Ansar (data/ML/API) + Samat Ablayhan, капитан (бот/веб/сдача).
- Хакатон 18–21.09.2026: панель v4 (1260×33) → бленд 5/6 strong → риски → страховка → платформа v4 (поля/журнал/spray/NPK/экономика) → 3 интерфейса → доки.
- OSS-подход: UniCrop, gsanaev, WeatherWatch-паттерн, CropBot — с атрибуцией, код свой; данные OSM ODbL, Sentinel-2 Copernicus.
- Картинка: фото/аватары + логотип Qagro + таймлайн хакатона.

## Слайд 10. Планы
- **ERA5-Land + почва**: SoilGrids сейчас 5/10 (Atbasar/Esil/Shortandy/Bulandy/Kokshetau — genuine null-маска) → добирать покрытие (пашня-смещение центроида с фиксацией / альтернативный источник), только потом честная v4-панель и переобучение.
- **Sentinel-2 NDVI**: сейчас 41 real (июнь–август 2024–2025) как триггер/фича-пилот → декадный ряд по всем районам + вегетационный триггер выплат.
- **e-АПК интеграция**: официальные поля map.iaqmola.kz (`akmola_official_fields.geojson`) + посевы/господдержка + пилоты со страховщиками (индексное страхование) + калибровка интервалов до номинала 80%.
- Картинка: roadmap Q4 2026 → 2027 (почва → NDVI-ряд → e-АПК → пилоты).
