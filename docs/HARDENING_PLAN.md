# Qagro Hardening Plan (ведущий инженер, 21.09.2026)

Источники: ТЗ AgriTech AI Hackathon §4/§6/§10 (25 баллов, дедлайн 21.09 23:59),
аудит 6 критических фактов. Baseline до правок: suites 45/45 (standalone),
`python -m pytest -q` падает (capture teardown), метрики см. metrics/.

## 1. Dependency map (упрощённо)

```
config/districts.yaml ──┬──> все geo-вычисления (центроиды, имена, культуры)
                        └──> бот/веб/API валидация входов
data/raw/* ── fetch_*.py ──> data/processed/akmola_panel{,_v3,_v4}.csv
panel_v4 ── train.py ──> models/lgbm_*.pkl + baseline.json
models + panel ── evaluate.py ──> metrics/metrics.json (+plots, shap)
models ── intervals.py ──> metrics/conformal.json + intervals.json
models + metrics(below_baseline) ── predict.py / insurance.py ──> api.py / bot.py / streamlit_app.py / report_pdf.py
fields geojson + ndvi JSON ── gis_monitor.py ──> data/gis/*.json ──> api/bot/web
live: Open-Meteo (risk/alerts/spray), PC STAC/TiTiler (NDVI), AgroData (сверка)
tests/test_*.py — standalone scripts (python tests/test_x.py), pytest НЕ работает
scripts/reproduce.{ps1,sh} — полный rebuild (ПЕРЕЗАПИСЫВАЕТ данные/модели/метрики)
scripts/check_leak.ps1 — 4-gate скан фрагмента токена (tracked/worktree/history/ignore)
```

## 2. Приоритеты (MoSCoW к дедлайну)

- P0 безопасность: секреты (rotation — ручной шаг, без доступа не выдумываем),
  CORS/mode-guard, rate-limit local/prod, pickle-policy, Docker non-root note.
- P0 честность ML: multi-metric gate (MAE + R²<0) в evaluate.py → рапс experimental;
  coverage+warning в API/UI/PDF (не «80%» без evidence).
- P0 тесты: pytest-архитектура (conftest, markers live/unit, mocks, timeouts,
  temp-output), stdout-хаки убрать без потери кириллицы (ASCII-safe принты).
- P1 воспроизводимость: verify/rebuild split, manifest+checksums, registry-sync
  (docstring api.py:12-15 + APPROX-fallback карта).
- P2 API/UI polish: error-contract (error+source, без немых except), logging,
  лимиты запросов, docs-sync.

## 3. Risk register

| # | Риск | S×L | Митигация |
|---|---|---|---|
| R1 | Токен в .env скомпрометирован (был в рабочей копии) | high×med | rotation вручную у BotFather (шаг для капитана); сканирование в CI; токен нигде не печатаем |
| R2 | CORS * + нет auth/rate-limit на публичном деплое | high×med | QAGRO_ENV=local/production; prod требует origins + лимиты; дефолт local не ломает демо |
| R3 | Рапс «strong» при R²−0.79/coverage 0.04 вводит жюри в заблуждение | high×high | multi-metric gate в коде + rerun evaluate/intervals + доки/тесты |
| R4 | pytest падает; live-тесты висят/пишут tracked data | med×high | новая pytest-архитектура; старые скрипты не трогаем (совместимость) |
| R5 | reproduce.* перезаписывают артефакты (комиссия/CI) | med×med | verify (read-only+manifest) vs rebuild (явный флаг, output-dir) |
| R6 | Pickle-бандлы из недоверенного источника (теория) | low×low | policy: грузим только свои бандлы; manifest sha256 в verify |
| R7 | Сетевые флейки (STAC/TiTiler/Open-Meteo/AgroData) | med×med | best-effort + error-строки; live-маркер opt-in; моки в unit |
| R8 | Правки ломают demo-сценарий за день до дедлайна | high×low | каждый этап: suites + smoke; решения фиксируются в отчёте |

## 4. Acceptance gate (минимум)

secret-scan чист; `pytest -q` зелёный; offline не требует сети и не пишет tracked;
live отдельно с timeout; compile + `pip check`; API smoke (health/predict wheat+flax+rapeseed/metrics/report);
рапс experimental; интервалы с coverage; provenance-статусы в API/UI/PDF;
`docker compose config` (Docker в CI); verify не меняет дерево.

## 5. Оркестрация

Субагенты (read-only recon): A security/secrets, B tests, C ML-validation,
D API/deployment, E UI/provenance. Главный агент сверяет каждое утверждение
с файлами (file:line) перед реализацией; неподтверждённое — в риски, не в код.
