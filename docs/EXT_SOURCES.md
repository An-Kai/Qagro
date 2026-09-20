# EXT_SOURCES — внешние источники Qagro (проверка 20.09.2026)

> Только чтение остального репо + этот файл. Панель `data/processed/akmola_panel.csv` / `models/` не тронуты.
> Проверка: веб-просмотр (без логина), PDF-бюллетени, поиск. Скачивание десятков PDF не выполнялось.

## 1. GEOGLAM Crop Monitor — https://cropmonitor.org/

**Доступ:** открыт, без логина. Бюллетени AMIS — HTML + PDF, карты JPG. JS/логин не требуется для чтения.
Интерактив: Crop Monitor Exploring Tool (CMET) — https://cropmonitortools.org/tools/cmet/ (требует JS),
Agmet EO Indicators — https://cropmonitortools.org/tools/agmet/.
Открытого REST API урожайности нет; есть Data Archive — помесячные GeoTIFF по культурам
(Synthesis / Wheat / Maize / Rice / Soybean): https://www.cropmonitor.org/data-archive

**Оценки пшеницы KZ 2024–2025 (для валидации Qagro):**

1. **AMIS No.131, опубл. 04.09.2025, условия на 28.08.2025** — https://www.cropmonitor.org/crop-monitor-for-amis-202509
   > «In **Kazakhstan, spring wheat is under favourable conditions** as winter wheat harvesting wraps up.»
   Смысл: яровая пшеница KZ — favourable в конце августа 2025. Согласуется с нашим якорем 2025 PRELIM
   (рекордный год: 26.4–27.1 млн т зерна, пшеница ~20 млн т, 16.8 ц/га — МСХ/primeminister.kz).
2. **AMIS No.119, опубл. 01.08.2024, условия на 28.07.2024** — https://www.cropmonitor.org/crop-monitor-for-amis-202408
   В секции Wheat Казахстан **не упомянут** среди проблемных зон (проблемы: Франция/Италия poor,
   UK below-average, RF мороз май + жара июнь, Украина восток/юг засуха+война).
   По методологии GEOGLAM неупоминание = favourable (на карте показываются только non-favourable).
   Контекст bumper-2024 подтверждается USDA FAS GAIN KZ2025-0004:
   «After heavy rains and flooding in May 2024 delayed planting, … near perfect weather» —
   согласуется с нашим якорем 2024 (зерновые 15.2 ц/га, пшеница 14.2 ц/га, БНС via APK-Inform).
3. **AMIS No.142, опубл. 03.09.2026, условия на 28.08.2026 (текущий)** — https://www.cropmonitor.org/crop-monitor-for-amis
   > «In **Kazakhstan, spring wheat harvesting is just beginning under favourable conditions**.»
   Полезно как нейтральный сценарий для прогноза 2026 (не засушливый старт уборки).

Классификация AMIS: Exceptional / Favourable / Watch / Poor / Out of season — https://www.cropmonitor.org/amis-classification-system

## 2. КазГидромет — https://www.kazhydromet.kz/

**Декадные агрометобзоры — доступны, открыто, PDF:**

- Хаб: https://www.kazhydromet.kz/ru/agrometeorology/kratkiy-obzor-agrometeorologicheskih-usloviy
- Формат: PDF на каждую декаду (кнопки download + eye-view `/uploads/files_calendar/.../*.pdf`),
  архив-переключатель 2019–2026, 12 мес × 3 декады.
- Содержание (пример — текст 1-й декады сентября 2026 на странице): фенофазы
  (уборка яровой пшеницы/ячменя, созревание подсолнечника, хлопчатник «раскрытие 1-й коробочки»,
  рис восковая спелость), состояние растений (хорошее/отличное/удовлетворительное),
  запасы продуктивной влаги ЗПВ по слоям (пахотный/полуметровый/метровый: оптимальные/
  удовлетворительные/недостаточные по областям).
- Пример 1 файла (не скачан, только URL зафиксирован):
  `.../6aaa7a9a6c180kratkiy-agro-obzor-za-1-dek-sentyabrya-2026-g.pdf` (1-я декада сентября 2026).

**Агрометпрогнозы — доступны, открыто, PDF:**

- Хаб: https://www.kazhydromet.kz/ru/agrometeorology/agrometeorologicheskie-prognozy
- Формат: PDF (предварительный/окончательный): прогноз засухи по месяцам (май–август),
  прогноз запасов влаги в почве, сроков сева, сроков созревания яровых, урожайности
  озимой/яровой пшеницы, подсолнечника, кукурузы, сахарной свёклы, условий уборки.
- Пример: «Прогноз урожайности яровой пшеницы в зерносеющей зоне Казахстана на 2026 год».
- Интерактив: AgroData — https://agrodata.kazhydromet.kz/#/home (браузер, без ключа для просмотра).

Использование в Qagro: кросс-чек декадного риска засухи (`src/risk.py`) по ЗПВ/ГТК и фенофазам;
валидация сроков сева/созревания для `src/recommend.py`. Десятки PDF не качаем (требование задачи).

## 3. МСХ РК / e-АПК — проверка открытых данных урожайности сверх stat.gov.kz

- Портал МСХ: https://www.gov.kz/memleket/entities/moa?lang=ru — пункт «Открытые данные» есть,
  фактически ведёт на data.egov.kz; районных длинных рядов урожайности там нет.
- Оперативные итоги уборки — только пресс-релизы, не датасеты:
  https://www.gov.kz/memleket/entities/moa/press/news/details/1092413
  (зерновые 99% — 15.8 млн га, бобовые рекорд >1 млн т, элеваторы 5.4 млн т/40%);
  сводные цифры — primeminister.kz (2025: 27.1 млн т с 16 млн га, 17 ц/га; пшеница 20.3 млн т с 12.2 млн га).
- e-АПК / субсидирование / карты полей — закрытые системы (требуют ЭЦП/авторизацию),
  открытого API урожайности нет.
- **Вывод:** сверх stat.gov.kz открытых машиночитаемых рядов урожайности у МСХ нет.
  База Qagro остаётся БНС + FAOSTAT/USDA (см. `data/processed/data_card.md`).

## 4. Таблица ресурс → статус → использование в Qagro

| Ресурс | Статус на 20.09.2026 | Использование в Qagro |
|---|---|---|
| GEOGLAM Crop Monitor (https://cropmonitor.org/) | ✅ Открыт (HTML+PDF без логина; API урожайности нет, только CMET-JS + Data Archive GeoTIFF) | Валидация прогнозов: KZ spring wheat favourable 08.2025 и 08.2026; 07.2024 implicit favourable. Ссылки в отчётах/доке, не фича модели |
| КазГидромет (https://www.kazhydromet.kz/ru/agrometeorology/...) | ✅ Открыт (декадные PDF 2019–2026 + прогнозы засухи/ЗПВ/урожайности PDF; AgroData web) | Кросс-чек декадного риска (ЗПВ, фенофазы, состояние растений) для `src/risk.py` / `src/recommend.py`. Скачан 0 PDF, зафиксирован 1 пример |
| МСХ РК / e-АПК (gov.kz/moa) | ⚠️ Частично (пресс-релизы открыты, датасетов урожайности нет; e-АПК закрыт) | Не заменяет БНС. Только оперативные якоря 2024–2025 (6.6/7.6 млн т Акмола, 27.1 млн т KZ) для кросс-чека |
| ERA5-CDS (Copernicus Climate Data Store) | ⚠️ Требует регистрации CDS API; в MVP напрямую не используется | Заменён открытым Open-Meteo Archive (ERA5, CC-BY 4.0) + NASA POWER MERRA-2 — уже в панели (`data/raw/openmeteo_*`, `data/raw/nasa_*`). CDS — опция пилота |
| Landsat (USGS LandsatLook / EarthExplorer) | ✅ Открыт (просмотр без ключа; скачивание после бесплатной регистрации) | Сверка NDVI Sentinel-2 (PC STAC) для 2 демо-полей; ручная проверка в QGIS/Copernicus Browser |
| Natural Earth (https://www.naturalearthdata.com/) | ✅ Public domain (векторы 1:10/50/110m, SHP/SQLite/GeoPackage) | Подложки/границы для карт (Folium/QGIS). Районные границы Акмолы — OSM/Geofabrik, не NE (NE слишком грубо) |
| QGIS | ✅ Открыт (GPL, десктоп) | Ручная проверка GeoJSON полей/элеваторов, NDVI-превью. Не зависимость кода |
| EarthMap FAO (https://earthmap.org/, на GEE) | ✅ Free/open web (браузер, без кода; GEE-слои климата/растительности) | Визуальный кросс-чек климата/NDVI-аномалий, статистика по полигону. Не входит в пайплайн |
| PlantVillage (54k фото листьев, CC-BY 3.0, plantvillage.psu.edu) | ⚠️ **Не наш трек** — датасет классификации болезней листьев (38 классов), не урожайности | НЕ используется. Qagro — Трек 2 (2.1 прогноз, 2.2 засуха, 2.4 страхование) + Трек 1 GIS (NDVI/границы/залежи/гибель). Болезни по фото — чужой трек, фиксируем чтобы не тянуть |

## 5. Вывод для валидации

- GEOGLAM favourable 2025 + bumper-контекст 2024 согласуются с высокими якорями панели
  (2024 зерновые 15.2, 2025 prelim 16.3–16.8 ц/га) — прогнозная модель с R² 0.68 по пшенице не противоречит внешней оценке.
- КазГидромет даёт независимый декадный ЗПВ/фено-контроль для светофора риска — подключить как ручной чек перед релизом прогноза 2026.
- МСХ сверх БНС ничего машиночитаемого не даёт — даунскейлинг область→район остаётся честным ограничением (см. README).

*Проверено: 20.09.2026, веб-просмотр. Цитаты GEOGLAM — перевод не требуется, оставлен оригинал для точности.*

## 6. AgroData API — живая интеграция (NEW_DATA #2, внедрено 20.09.2026)

**Доступ:** открыт, без ключа. Все проверены кодом 200 20.09.2026:

| Endpoint | n | Что отдаёт |
|---|---|---|
| `/api/calendar/towns` | 400 | города `{success, result{count, entities}}` |
| `/api/weather/actual/towns` | 197 | метеостанции |
| `/api/forecasts/drought` | 288 | `{town{district{region}}, value}` — сырой индекс засухи |
| `/api/forecasts/moisture` | 120 | влажность почв по типам (`types[]`) |
| `/api/forecasts/productivity` | 118 | `{nameRu, valueFrom, valueTo, color}` — диапазоны ц/га |

**Покрытие 10 районов Qagro:** drought — 8/10 (нет Целиноградского, Кокшетау);
productivity — 9/10 (нет Кокшетау; Есильский — 2 зоны). Пример: Esil —
drought точка Есиль value −0.14 (08.2026), productivity 9.3–11.3 и 16.3–18.3;
Qagro пшеница 11.39 — внутри объединённого диапазона.

**Код:** `src/fetch_agrodata.py` (`drought_by_district`, `productivity_by_district`,
`compare_agrodata`) + `GET /agrodata?district_en=&crop=&lang=` (`src/api.py`).
Правила: drought.value показываем как есть (шкалу Казгидромета не интерпретируем);
сверка с y_pred — только арифметика внутри/ниже/выше; сеть упала — error-строки,
модель/панель НЕ тронуты. Тест: `t_agrodata` в `tests/test_api.py`.
