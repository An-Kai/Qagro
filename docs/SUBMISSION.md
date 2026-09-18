# Qagro — заготовка формы сдачи (SUBMISSION)

## Название
Qagro — прогноз урожайности и агрориски (Акмолинская область, 2026)

## Трек / задачи
- Трек 2 (AgriTech AI)
- 2.1 — прогноз урожайности (LGBM vs бейзлайн, hold-out 2021–2025, прогноз 2026 с интервалом + SHAP)
- 2.2 — риски засухи (декадный индекс Open-Meteo, светофор 🟢🟡🔴, Folium-карта)
- 2.4 — страхование + рекомендации + интерфейсы (P_loss/payout decision support, советы RU/KZ/EN, API/бот/веб/PDF)

## Состав
- Команда: Qagro
- Kairbek Ansar — data pipeline / ML / API
- Samat Ablayhan (капитан) — бот / веб / интеграция / сдача

## Ссылки
- Repo: https://github.com/An-Kai/Qagro.git
- Video (2:30): TODO_VIDEO — ИНСТРУКЦИЯ: запишите экран (бот + веб) по `docs/demo_script.md` (Esil 1558 тг/га vs Zerenda 150 тг/га), залейте на YouTube/RuTube, замените эту строку ссылкой вида `https://...`
- Deploy: TODO_DEPLOY — ИНСТРУКЦИЯ: поднимите `docker compose up --build`, вставьте сюда 3 строки: `API health http://.../health`, `Streamlit http://...`, `Telegram @username_бота`; токен только из `TELEGRAM_BOT_TOKEN`, в код не класть
- PDF-пример: `reports/risk_example.json` + генерация через `POST /report`
- Презентация C9: `docs/Qagro_presentation_v2.pdf` (10 слайдов, landscape A4, кириллица Arial TTF, scatter wheat/barley/oats, ~341 КБ) — финальная; `docs/Qagro_presentation.pdf` — старая ASCII-версия без кириллицы

## Чек-лист ТЗ (отметить перед отправкой)
- [x] Название + трек + задачи 2.1/2.2/2.4 указаны в README
- [x] Описание + стек + запуск (pip / API / бот / streamlit / docker)
- [x] Источники данных с правами (БНС, FAOSTAT/USDA, NASA POWER, Open-Meteo, OSM)
- [x] Команда (Qagro, Kairbek Ansar, Samat Ablayhan — капитан)
- [x] Что сделано на хакатоне 18–21.09.2026
- [x] Сторонние OSS с ссылками и лицензиями (UniCrop MIT, gsanaev MIT, WeatherWatch-паттерн, CropBot MIT)
- [x] Метрики таблицей (пшеница 2.68/−0.26 → 1.46/0.55; ячмень 2.78/−0.25 → 1.52/0.54) + `metrics/plots/`
- [x] Ограничения честно (даунскейлинг, APPROX 4 культуры, страховка decision support)
- [x] Воспроизводимость (`src/fetch_all.py → train.py → evaluate.py`)
- [x] Структура репо
- [x] Токена нет в коде/README; только `TELEGRAM_BOT_TOKEN` из env (`.env.example`)
- [x] `data/processed/data_card.md` в UTF-8 без кракозябр
- [x] `docs/demo_script.md` (2:30 по секундам)
- [x] `docs/presentation_outline.md` (10 слайдов)
- [ ] Видео записано и ссылка вставлена (ждёт TODO_VIDEO выше)
- [ ] Деплой поднят и ссылки вставлены (ждёт TODO_DEPLOY выше)
- [x] Репо публичное, `.env` в `.gitignore`, токен не утёк в историю git (проверено 18.09.2026: `git check-ignore .env` OK, `git log -- .env` пуст, `.env.example` содержит только `xxx`)
