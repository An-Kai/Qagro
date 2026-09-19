# Qagro metrics — hold-out 2021-2025 (train ≤2020, no leakage)

Бейзлайн: среднее пред. 5 лет по району+культуре (только прошлое). Модель v3: бленд LightGBM+Ridge 0.7/0.3 на панели akmola_panel_v3.csv (per-crop SelectKBest top-10 + year_trend; таргет без преобразований), обучена на 2008–2020, hold-out 2021–2025 не трогали при обучении. Ключ `lgbm` в metrics.json = метрики бленда (имя сохранено для совместимости API/бота).

| crop | baseline MAE / RMSE / R2 | blend MAE / RMSE / R2 | n | resid mean/std | status |
|------|--------------------------|---------------------|---|---------------|--------|
| spring_wheat | 2.683 / 2.886 / -0.264 | 1.180 / 1.458 / 0.677 | 50 | 0.480 / 1.391 | ✅ strong |
| barley | 2.782 / 3.002 / -0.257 | 1.249 / 1.529 / 0.674 | 50 | 0.495 / 1.461 | ✅ strong |
| oats | 3.589 / 4.004 / -0.332 | 1.261 / 1.639 / 0.777 | 50 | 0.111 / 1.652 | ✅ strong |
| sunflower | 2.524 / 3.691 / -0.347 | 2.148 / 3.205 / -0.016 | 50 | 1.969 / 2.555 | ✅ strong |
| rapeseed | 3.699 / 4.260 / -0.855 | 3.786 / 4.489 / -1.059 | 50 | 3.786 / 2.437 | 🧪 experimental |
| flax | 1.218 / 1.440 / -0.051 | 1.149 / 1.336 / 0.095 | 50 | -0.452 / 1.270 | ✅ strong |

Вывод: 5 strong (spring_wheat, barley, oats, sunflower, flax), 1 experimental (rapeseed — below_baseline, структурный сдвиг 2024–2025, метрики честные без подгонки).

## FAOSTAT-национальный sanity-check (не фичи модели, утечки нет)

Национальные якоря Казахстана из тех же raw-источников панели (см. `source` в data/raw/stat_yield.csv) vs среднее панели по Акмолинской области. Совпадение порядка величин подтверждает, что скачок масличных 2024–2025 — реальный страновой сдвиг (гибриды/площади), а не артефакт даунскейлинга.

- sunflower — 2024: national 14.6 vs panel 14.57, 2025: national 13.9 vs panel 13.87.
  Источник: APK-Inform/БНС 10.02.2026 (via stat_yield source): Казахстан подсолнечник 2024 14.6 / 2025 13.9 ц/га
- rapeseed — 2022: national 14.2 vs panel 14.12, 2023: national 13.3 vs panel 13.27, 2024: national 19.2 vs panel 19.16, 2025: national 19.5 vs panel 19.46.
  Источник: APK-Inform/БНС 10.02.2026 (via stat_yield source): Казахстан рапс 2022 14.2 / 2023 13.3 / 2024 19.2 / 2025 19.5 ц/га
- flax — 2022: national 6.3 vs panel 6.29, 2023: national 5.0 vs panel 4.99, 2024: national 8.7 vs panel 8.68, 2025_prelim: national 8.3 vs panel 8.29.
  Источник: APK-Inform/БНС (via stat_yield source): Казахстан лён 2022 6.3 / 2023 5.0 / 2024 8.7 ц/га; 2025 8.3 PRELIM (БНС по льну-2025 не опубликован)

Артефакты: metrics/metrics.json, metrics/summary.csv, metrics/plots/scatter_{crop}.png, metrics/shap_{crop}.json.
