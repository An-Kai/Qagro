# Qagro — прогноз урожайности и агрориски (Акмолинская область, 2026)

> Трек 2 (AgriTech AI): задачи **2.1** (прогноз урожайности), **2.2** (риски засухи / декадный мониторинг), **2.4** (страхование и рекомендации + интерфейсы: API / Telegram-бот / веб).

## Описание

Qagro — MVP decision-support системы для фермеров и агроаналитиков Акмолинской области:
прогноз урожайности 2026 на уровне района, декадный индекс риска засухи (светофор 🟢🟡🔴),
индексное страхование (P_loss, ожидаемая выплата) и рекомендации по севу — на 3 языках (RU/KZ/EN).

Покрытие MVP: **10 районов** Акмолинской области × **6 культур**
(пшеница яровая, ячмень — обученные LGBM-модели; овёс, подсолнечник, рапс, лён — APPROX),
годы панели 2005–2025, прогноз — 2026.

Интерфейсы: **FastAPI** (`POST /predict`, `POST /report` → PDF), **Telegram-бот** (aiogram 3.x),
**Streamlit-дашборд** (Plotly + Folium, выгрузка CSV/GeoJSON/PDF).

## Стек

Python 3.12, FastAPI + Uvicorn, aiogram 3.x, Streamlit, pandas / numpy / scikit-learn,
LightGBM, SHAP, Open-Meteo API + NASA POWER (MERRA-2), PyYAML, ReportLab (PDF),
Matplotlib / Plotly / Folium, Docker + docker-compose, SQLite-кэш (`data/cache.db`, TTL 24 ч).

## Быстрый старт (Windows PowerShell)

```powershell
cd "C:\Users\ansar\Documents\Default Project\Qagro"
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Проверка без сети и без бота:

```powershell
python -m py_compile src/api.py src/bot.py app/streamlit_app.py
python -c "from src.predict import predict_yield; print(predict_yield('Esil','spring_wheat',None))"
python src/train.py
python src/evaluate.py
```

### API

```powershell
uvicorn src.api:app --host 127.0.0.1 --port 8000
# GET  http://127.0.0.1:8000/health
# POST http://127.0.0.1:8000/predict  {"district_en":"Esil","crop":"spring_wheat"}
# POST http://127.0.0.1:8000/predict  {"district_en":"Esil","crop":"oats"}  # APPROX
# POST http://127.0.0.1:8000/report   {"district_en":"Esil","crop":"spring_wheat"} -> PDF
```

### Telegram-бот (токен ТОЛЬКО из env!)

```powershell
Copy-Item .env.example .env  # вписать токен от BotFather в .env
$env:TELEGRAM_BOT_TOKEN="вставь_токен_сюда"  # или export в shell; в коде токена нет
python -m src.bot
# /start -> язык (RU/KZ/EN) -> район (10) -> культура (6) -> прогноз + риск + страховка + PDF
```

> Никаких токенов в коде и в README. Единственный источник — переменная окружения `TELEGRAM_BOT_TOKEN` (см. `.env.example`).

### Streamlit

```powershell
streamlit run app/streamlit_app.py
# селекты район/культура/язык, Plotly факт vs прогноз, Folium-карта рисков,
# CSV / GeoJSON / PDF, дисклеймер APPROX + даунскейлинг
```

### Docker

```powershell
docker compose up --build
# api:        http://localhost:8000/health
# streamlit:  http://localhost:8501
# bot читает .env (TELEGRAM_BOT_TOKEN); том ./data:/app/data хранит SQLite-кэш
```

## Источники данных и права

| Источник | Что взято | Права / доступ |
|---|---|---|
| Бюро национальной статистики РК (stat.gov.kz), динамические таблицы Акмолинской области + валовой сбор 2024 | Областные якоря урожайности зерновых/пшеницы/ячменя; нац. якоря 2022–2024 | Открытые официальные данные; использование с указанием источника |
| Акимат Акмолинской области / primeminister.kz, ElDala.kz, APK-Inform, margin.kz, tengrinews.kz | Кросс-чек 2024–2025: 6.6 млн т (2024), 7.6 млн т / 16.3 ц/га (2025) | Открытые публикации; ссылки в `data/processed/data_card.md` |
| FAOSTAT QCL + USDA FAS GAIN PSD | Валидация формы ряда 2005–2021 (засухи 2010/2012/2019/2021, рекорд 2011; barley 10-yr avg 1.445 т/га) | Открытые данные FAO/USDA |
| NASA POWER Monthly Point (MERRA-2, community=AG), 2005–2025 | T2M/T2M_MAX/T2M_MIN/PRECTOTCORR/RH2M/ALLSKY_SFC_SW_DWN/WS2M/GWETTOP; сырое `data/raw/nasa_*.json` | Открытый API NASA; некоммерческое/исследовательское использование |
| Open-Meteo Archive (ERA5) + Forecast 16d, timezone Asia/Almaty | Daily tmax/tmin/precip/ET0 FAO 2005-01-01–2025-08-31, hourly soil_moisture_3_9cm; сырое `data/raw/openmeteo_*` | Открытый API Open-Meteo (CC-BY 4.0, требуется атрибуция) |
| `config/districts.yaml` (центроиды WGS84, OpenStreetMap) | Координаты 10 районов, 6 культур, пороги страховки/рекомендаций | ODbL (OSM) — указаны центроиды, не границы |

Панель: `data/processed/akmola_panel.csv` — 420 строк (10 районов × 21 год × 2 культуры), 0 NaN в `yield_c_ha`. Детали и честные оговорки — `data/processed/data_card.md`.

## Команда

- **Команда: Qagro**
- **Kairbek Ansar** — data pipeline / ML / API
- **Samat Ablayhan (капитан)** — бот / веб / интеграция / сдача

## Что сделано на хакатоне 18–21.09.2026

- [x] Панель `akmola_panel.csv` (БНС + NASA POWER + Open-Meteo ERA5), `src/fetch_all.py` с громкими ошибками API.
- [x] Фичи MJJA (tmean/precip/GDD5/heat30/dry_max/ET0/p30_anom + lat/lon/yield_lag1), `src/features.py`.
- [x] Бейзлайн (среднее 5 лет) + LightGBM per-crop (TimeSeriesSplit 5 + LOO 2020–2025), `src/train.py`; hold-out 2021–2025 + scatter + SHAP top-3, `src/evaluate.py`.
- [x] Прогноз 2026 с 80% интервалом + топ-3 SHAP-фактора, `src/predict.py`.
- [x] Декадный риск засухи Open-Meteo (15 декад, формула 0.4*precip_deficit+0.35*heat+0.25*dry, светофор 🟢<35 🟡35–60 🔴>60), `src/risk.py`.
- [x] Страховка decision support (mean5, strike 0.8, P_loss через N(y_pred, resid_std), payout), `src/insurance.py`.
- [x] Рекомендации сева RU/KZ/EN (GDD + p30/heat пороги), `src/recommend.py`.
- [x] APPROX для 4 культур без обучения (масштаб от пшеницы + цены-индикаторы), `src/approx_crops.py`.
- [x] FastAPI `/predict` + `/report` (PDF ReportLab с кириллицей), Telegram-бот (язык→район→культура→карточки+PDF), Streamlit (Plotly+Folium+CSV/GeoJSON/PDF).
- [x] Кэш SQLite 24 ч, Docker (api+bot+streamlit), `reports/risk_example.json` (Esil/Zerenda × риски/страховка/рекомендации).
- [x] Доки: README, `data/processed/data_card.md`, `docs/demo_script.md`, `docs/presentation_outline.md`, `docs/SUBMISSION.md`.

## Сторонние OSS (использованы как образец, код Qagro — оригинальный)

- **UniCrop** (MIT) — MJJA-фичи + LightGBM-пайплайн + SHAP — https://github.com/CoDIS-Lab/UniCrop
- **gsanaev / crop-yield-prediction-climate-change** (MIT) — регрессия урожайности по климату (temperature/precipitation/soil) — https://github.com/gsanaev/crop-yield-prediction-climate-change
- **WeatherWatch-паттерн** — декадный мониторинг погоды/засухи (архив + forecast-добивка, открытые API) — паттерн по докам Open-Meteo: https://open-meteo.com/en/docs
- **CropBot / mishagrol/CropBot** (MIT) — Telegram-бот + crop-модель (WOFOST) как UX-образец — https://github.com/mishagrol/CropBot

Лицензии соблюдены: указаны авторы/ссылки, чужой код не копировался, заимствованы только подходы.

## Метрики (hold-out 2021–2025, n=50 на культуру)

| Культура | Бейзлайн (среднее 5 лет) | LGBM (Qagro) |
|---|---|---|
| Пшеница яровая | MAE **2.68**, RMSE 2.89, R² **-0.26** | MAE **1.46**, RMSE 1.72, R² **0.55** |
| Ячмень | MAE **2.78**, RMSE 3.00, R² **-0.25** | MAE **1.52**, RMSE 1.81, R² **0.54** |

Источники: `metrics/metrics.json`, графики `metrics/plots/scatter_spring_wheat.png`, `metrics/plots/scatter_barley.png`, SHAP `metrics/shap_*.json`.
Oats/sunflower/rapeseed/flax — без метрик (APPROX, обучающих данных нет).

Пример эффекта (нейтральный сценарий MJJA 2016–2025, `reports/risk_example.json`):
Esil/пшеница — expected payout **1558 тг/га** (p_loss 0.23); Zerenda/пшеница — **150 тг/га** (p_loss 0.03).

## Ограничения (честно)

- **Район = даунскейлинг области.** Районных длинных рядов БНС в открытом доступе нет; районная урожайность = областной якорь × агрозональный коэффициент (север 1.02–1.06, юг 0.92–0.98). Центроиды из `config/districts.yaml` — не границы и не поля.
- **APPROX для 4 культур.** Oats ×1.02 / sunflower ×0.85 / rapeseed ×0.72 / flax ×0.58 от пшеницы; цены-индикаторы (70/180/200/220 тыс. тг/т). Это заглушка, не обученная модель — в API/боте/вебе помечена флагом `approx`.
- **Страховка — decision support, не тариф.** Цена 95 000 тг/т (пшеница/ячмень) и subsidy 0.8 из конфига; формула `max(0, 0.8*mean5 - y_pred)/10*price*subsidy`.
- **2025 yield — предварительный** (якорь 15.8/16.8 ц/га); soil_moisture ERA5 для Акмолы в Archive API = null (проверено 18.09.2026) — в панель не входит, риск от soil не зависит.
- Офлайн-демо: прогноз по умолчанию — нейтральный сценарий (средний MJJA 2016–2025 района); живой Open-Meteo — best-effort.

## Воспроизводимость

```powershell
pip install -q pandas numpy requests pyyaml openmeteo-requests requests-cache retry-requests
python src/fetch_all.py   # тянет NASA + Open-Meteo + БНС-якоря -> data/raw + data/processed/akmola_panel.csv
python src/train.py       # -> models/lgbm_*.pkl + models/baseline.json
python src/evaluate.py    # -> metrics/metrics.json + metrics/plots/*.png + metrics/shap_*.json
python -c "import pandas as pd; df=pd.read_csv('data/processed/akmola_panel.csv'); print(df.shape, df['yield_c_ha'].isna().sum())"
```

Ожидается: `(420, 14)`, NaN в yield — 0.

## Структура репо

```
Qagro/
  src/            api/bot/predict/risk/insurance/recommend/train/evaluate/fetch_*/approx_crops/report_pdf/features.py
  app/            streamlit_app.py (Plotly + Folium + выгрузки)
  config/         districts.yaml (10 районов, 6 культур, пороги)
  data/           raw/ (nasa_*/openmeteo_*/stat_yield.csv) + processed/akmola_panel.csv + data_card.md + cache.db
  models/         lgbm_{crop}.pkl + baseline.json
  metrics/        metrics.json + plots/scatter_*.png + shap_*.json
  reports/        risk_example.json (Esil/Zerenda демо)
  docs/           demo_script.md + presentation_outline.md + SUBMISSION.md
  Dockerfile + docker-compose.yml (api/bot/streamlit) + requirements.txt + .env.example
```

## In English (brief)

Qagro (Track 2: 2.1/2.2/2.4) — Akmola district-level 2026 yield forecast (LightGBM vs 5y-mean baseline),
decade drought-risk traffic light (Open-Meteo), index-insurance decision support + sowing advice (RU/KZ/EN)
via FastAPI, Telegram bot (`TELEGRAM_BOT_TOKEN` from env only, never hardcoded) and Streamlit.
Wheat: baseline MAE 2.68/R² -0.26 → LGBM MAE 1.46/R² 0.55; barley: 2.78/-0.25 → 1.52/0.54 (hold-out 2021–2025).
Limits: districts = downscaled oblast stats (centroids, not fields); 4 crops APPROX-scaled from wheat;
insurance is decision support, not a tariff.
