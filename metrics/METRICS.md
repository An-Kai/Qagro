# Qagro metrics — hold-out 2021-2025 (train ≤2020, no leakage)

Бейзлайн: среднее пред. 5 лет по району+культуре (только прошлое). LGBM обучен на 2006-2020, hold-out 2021-2025 не трогали при обучении.

| crop | baseline MAE / RMSE / R2 | LGBM MAE / RMSE / R2 | n | resid mean/std | status |
|------|--------------------------|----------------------|---|---------------|--------|
| spring_wheat | 2.683 / 2.886 / -0.264 | 1.464 / 1.718 / 0.552 | 50 | 1.024 / 1.394 | ✅ strong |
| barley | 2.782 / 3.002 / -0.257 | 1.522 / 1.815 / 0.541 | 50 | 1.117 / 1.444 | ✅ strong |
| oats | 3.589 / 4.004 / -0.332 | 1.649 / 1.918 / 0.694 | 50 | 0.065 / 1.937 | ✅ strong |
| sunflower | 2.524 / 3.691 / -0.347 | 2.800 / 3.852 / -0.467 | 50 | 2.753 / 2.722 | 🧪 experimental |
| rapeseed | 3.699 / 4.260 / -0.855 | 5.253 / 5.920 / -2.582 | 50 | 5.253 / 2.758 | 🧪 experimental |
| flax | 1.218 / 1.440 / -0.051 | 1.653 / 2.019 / -1.068 | 50 | 1.514 / 1.349 | 🧪 experimental |

Вывод: 3 strong (spring_wheat, barley, oats — LGBM лучше бейзлайна), 3 experimental (sunflower, rapeseed, flax — below_baseline, структурный сдвиг 2024-2025, метрики честные без подгонки).

Артефакты: metrics/metrics.json, metrics/summary.csv, metrics/plots/scatter_{crop}.png, metrics/shap_{crop}.json.
