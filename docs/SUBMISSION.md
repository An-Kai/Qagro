# Qagro — заготовка формы сдачи (SUBMISSION, v3 от 19.09.2026)

## Название
Qagro — прогноз урожайности и агрориски (Акмолинская область, 2026)

## Трек / задачи
- Трек 2 (AgriTech AI)
- 2.1 — прогноз урожайности (бленд LightGBM+Ridge 0.7/0.3 vs бейзлайн-5y, hold-out 2021–2025 n=50, прогноз 2026 с интервалом + SHAP; 5/6 strong, рапс experimental)
- 2.2 — риски засухи (декадный индекс Open-Meteo, светофор 🟢🟡🔴, Folium-карта 10 районов + 115 полей + NDVI-точки)
- 2.4 — страхование + рекомендации + интерфейсы + платформа v4 (P_loss/payout decision support, советы RU/KZ/EN, API/бот/веб/PDF; Мои поля/журнал/spray/NPK/экономика)

## Состав
- Команда: Qagro
- Kairbek Ansar — data pipeline / ML / API
- Samat Ablayhan (капитан) — бот / веб / интеграция / сдача

## Ключевые числа v4 (источник правды)
- Панель `akmola_panel_v4.csv`: 1260 строк (10×21×6), 33 колонки (v3 + площади stat.gov.kz, ГТК, SoilGrids)
- Поля `akmola_osm_fields.geojson`: 115 полигонов (109 OSM real ODbL + 6 demo-fallback)
- NDVI Sentinel-2 `ndvi_timeseries.json`: 22 real (Esil+Zerenda, June+July, июнь 2024) из 62 сцен + Landsat cross-check
- Метрики hold-out 2021–2025: пшеница 2.68/−0.26 → 1.20/0.66; ячмень 2.78/−0.26 → 1.27/0.65; овёс 3.59/−0.33 → 1.37/0.74; 5/6 strong, рапс experimental (3.79/−1.06, below_baseline)
- Демо-якоря: Esil/пшеница 🟡 35.0, payout 1558 тг/га; Zerenda 🟢 28.5, 150 тг/га
- Платформа v4: `src/myfields.py` + `src/journal.py` + `src/spray.py` + `src/fertilizer.py` + `src/economics.py` + `src/platform_api.py` (`/myfields`, `/journal`, `/spray`, `/fertilizer`)

## Ссылки
- Repo: https://github.com/An-Kai/Qagro.git
- Video (2:30): TODO_VIDEO — ИНСТРУКЦИЯ: запишите экран (бот + веб) по `docs/demo_script.md` v3 (Esil 1558 тг/га vs Zerenda 150 тг/га + spray-окно + Мои поля + NPK), залейте на YouTube/RuTube, замените эту строку ссылкой вида `https://...`
- Deploy: TODO_DEPLOY — ИНСТРУКЦИЯ: поднимите `docker compose up --build`, вставьте сюда 3 строки: `API health http://.../health`, `Streamlit http://...`, `Telegram @username_бота`; токен только из `TELEGRAM_BOT_TOKEN`, в код не класть
- PDF-пример: `reports/risk_example.json` + генерация через `POST /report` (раздел 6 Farm&money: NPK + экономика + spray)
- Презентация: `docs/presentation_outline.md` v3 (10 слайдов, числа выше) — актуальный текст; `docs/Qagro_presentation_v2.pdf` (10 слайдов, ~349 КБ, ReportLab) — бинарь ЗАМОРОЖЕН, не пересобирать в C9; `docs/Qagro_presentation.pdf` — старая ASCII-версия без кириллицы
- Демо-сценарий: `docs/demo_script.md` v3 (2:30 по секундам, со spray + Мои поля + NPK)

## Чек-лист ТЗ (отметить перед отправкой)
- [x] Название + трек + задачи 2.1/2.2/2.4 указаны в README (включая платформу v4)
- [x] Описание + стек + запуск (pip / API / бот / streamlit / docker)
- [x] Источники данных с правами (БНС, FAOSTAT/USDA, NASA POWER, Open-Meteo, OSM ODbL, Sentinel-2 Copernicus, SoilGrids)
- [x] Команда (Qagro, Kairbek Ansar, Samat Ablayhan — капитан)
- [x] Что сделано на хакатоне 18–21.09.2026 (панель v4 1260×33 → бленд 5/6 strong → платформа v4)
- [x] Сторонние OSS с ссылками и лицензиями (UniCrop MIT, gsanaev MIT, WeatherWatch-паттерн, CropBot MIT)
- [x] Метрики таблицей v4 (пшеница 2.68/−0.26 → 1.20/0.66; ячмень 2.78/−0.26 → 1.27/0.65; овёс 3.59/−0.33 → 1.37/0.74; 5/6 strong, рапс experimental) + `metrics/plots/` + `metrics/METRICS.md`
- [x] Ограничения честно (даунскейлинг район=область×коэф; рапс EXPERIMENTAL below_baseline, структурный сдвиг 2024–2025; страховка decision support; SoilGrids 10/10 в фичах v4; конформные интервалы покрытие 0.66 факт vs 0.80 номинал; NDVI 22 real из 62 + Landsat cross-check)
- [x] Воспроизводимость (`src/fetch_all.py → train.py → evaluate.py`; поля `src/fields_osm.py`; NDVI `src/sentinel_ndvi.py`)
- [x] Структура репо
- [x] Токена нет в коде/README; только `TELEGRAM_BOT_TOKEN` из env (`.env.example`)
- [x] `data/processed/data_card.md` в UTF-8 без кракозябр (FFFD=0)
- [x] `docs/demo_script.md` v3 (2:30 по секундам, spray + Мои поля + NPK)
- [x] `docs/presentation_outline.md` v4 (10 слайдов, 1260 / 115 / 22 NDVI / R2 0.66-0.74 / 5-6 strong / платформа v4)
- [x] Все .md UTF-8 без FFFD (проверено 19.09.2026: `read_bytes().decode('utf-8')`, count FFFD=0)
- [ ] Видео записано и ссылка вставлена (ждёт TODO_VIDEO выше)
- [ ] Деплой поднят и ссылки вставлены (ждёт TODO_DEPLOY выше)
- [x] Репо публичное, `.env` в `.gitignore`, токен не утёк в историю git (проверено 18.09.2026: `git check-ignore .env` OK, `git log -- .env` пуст, `.env.example` содержит только `xxx`)
