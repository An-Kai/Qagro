# Demo Day без интернета — инструкция (C8)

Интернет на Demo Day может пропасть. План: демо идёт **строго из локального
кэша**, сеть не нужна. Жюри видит те же цифры, что и с сетью (снапшоты
накануне), плюс заранее записанное видео как страховка.

## 0. Что откуда берётся (факты)

| Путь | Внешние вызовы | Офлайн-поведение |
|---|---|---|
| `POST /predict` `include_risk=False` | **0** (панель CSV + pickle + yaml) | работает всегда, быстро |
| `POST /predict` `include_risk=True` | до **5 GET** Open-Meteo (`risk.py`, каждый `TIMEOUT=60с`) | HTTP 200 с `risk.error` + `seasonal_risk: null`, но **первый** холодный вызов при висящей сети может ждать до ~5×60с — поэтому на демо только прогрев + `?fresh=false` |
| `GET /alerts`, `GET /spray` | 1 GET Open-Meteo (`TIMEOUT=20с`) | 200 с `alerts: []` + `error` / 502 с честной ошибкой |
| `GET /soil`, `/fields`, `/calendar`, `/metrics` | **0** (локальные файлы) | работают всегда |
| Бот: прогноз | 0 (локально) | всегда |
| Бот: риск | кэш → 1 live-попытка ≤**3.5с** → офлайн-заглушка | светофор по `p_loss` + пометка «офлайн», не падает |
| Бот: PDF-кнопка, алерты | алерты ≤**8с** | `alerts_error` в PDF, не падает |

Таймауты **не меняем** (`risk.py=60`, `alerts/spray/soil=20`, бот `3.5/8.0`).
Скорость демо даёт кэш, а не урезание таймаутов.

Кэши:

- API: `_PREDICT_CACHE` в памяти, **TTL 5 мин** (`src/api.py`), флаг `?fresh=false`
  (по умолчанию) — повтор того же запроса отвечает `<1с` без сети.
- Бот: `data/cache.db` (SQLite, TTL 24ч): `risk:{район}:2026`, `full:{район}:{культура}:{язык}`.
- Файл: `reports/risk_example.json` — fallback без сети (внимание: сейчас там
  только `Esil_risk` + `Zerenda_risk`; прогон `warm_cache.py` с интернетом
  добивает остальные 8 районов).

## 1. Подготовка накануне (с интернетом, 15 минут)

```powershell
cd "C:\Users\ansar\Documents\Default Project\Qagro"
python scripts/warm_cache.py
# ожидаемо: risk HIT+LIVE=10, full cached=10 (spring_wheat/ru по умолчанию)

# Проверка: все 10 районов — HIT без сети
python -c "import sys; sys.path.insert(0,'.'); from src.bot import _risk_cached; ds=['Zerenda','Burabay','Atbasar','Esil','Zhaksy','Shortandy','Tselinograd','Sandyktau','Bulandy','Kokshetau']; print([bool(_risk_cached(d)) for d in ds])"

# Прогрев API-кэша (2 вызова: 1-й ~5с SHAP, 2-й <1с из кэша)
python -c "import sys; sys.path.insert(0,'.'); from fastapi.testclient import TestClient; from src.api import app; c=TestClient(app); print(c.post('/predict', json={'district_en':'Esil','crop':'spring_wheat','lang':'ru','include_risk':False}).status_code); print(c.post('/predict', json={'district_en':'Esil','crop':'spring_wheat','lang':'ru','include_risk':False}).status_code)"

# Локальные PDF для раздачи (2–3 шт, кладутся рядом с ноутбуком)
python -c "import sys; sys.path.insert(0,'.'); from src.api import _full_result; from src.report_pdf import build_report_pdf; f=_full_result('Esil','spring_wheat','ru',None,2026,False); open('reports/demo_Esil_wheat.pdf','wb').write(build_report_pdf('Esil','spring_wheat','ru',f['pred'],f['insurance'],f['risk'],f['rec']))"

# Запись видео-страховки (2–3 мин, телефон + захват экрана):
#   1) бот: /start -> Esil -> spring_wheat (ответ с ⏱),
#   2) API: POST /predict в Swagger,
#   3) PDF-отчёт. Файл: reports/demo_video.mp4 (или ссылка на телефон).
```

Чеклист файлов на ноутбуке: `data/cache.db` (свежий, проверь дату),
`reports/risk_example.json` (10 `*_risk` после warm), `reports/demo_*.pdf`,
видео, этот файл.

## 2. Сценарий демо без интернета (5 минут)

1. **Заранее:** отключи Wi-Fi сам (честно покажи иконку «без сети»).
2. **Бот (главное):** `/start` → язык → **Esil** → **spring_wheat**.
   Ответ приходит из SQLite (`full:Esil:spring_wheat:ru`, риск-снапшот) —
   внизу `⏱ ~0.xс`. Риск с пометкой `cached`/`офлайн` — проговорить вслух:
   «риск — вчерашний снапшот, светофор дублируется по страховке».
3. **API (скорость):** `POST /predict` тот же запрос дважды —
   1-й может быть ~5с (SHAP), **2-й <1с** (`X-Qagro-Cache: HIT`, `?fresh=false`).
   Спросят «а если данные старые?» — `?fresh=true` идёт мимо кэша (с сетью).
4. **PDF:** заранее сгенерированные `reports/demo_*.pdf` — открыть локально.
5. **Запасной парашют:** если упадёт хоть что-то — включить записанное видео
   (там тот же сценарий с интернетом). Фраза: «живое демо — из кэша,
   полное — на видео».

Что **не** показывать без сети: `/alerts`, `/spray`, живой декадный риск
(`include_risk=True` на холодном кэше) — они честно вернут ошибку вместо цифр.

## 3. Если что-то пошло не так

| Симптом | Причина | Действие |
|---|---|---|
| Бот отвечает «риск офлайн (светофор по p_loss)» | нет `risk:` в SQLite и нет `*_risk` в example | нормально для 8/10 районов до warm; проговорить fallback, показать Esil/Zerenda |
| `/predict` 2-й вызов всё равно медленный | разные тела запросов (кэш-ключ включает weather/lang/year/include_risk) | слать **байт-в-байт** тот же JSON + `?fresh=false` |
| `X-Qagro-Cache: MISS` | TTL 5 мин истёк / другой ключ / `?fresh=true` | повторить запрос — станет HIT |
| `soil` показывает 5 районов | `data/processed/soil.csv` неполный (5/10) | честно сказать: «почва — 5 районов, шаг v4 пропускается для остальных» |
| Всё красное | паника | включить видео, раздать PDF |

## 4. После Demo Day

Кэш бота живёт 24ч, API — 5 мин: перед следующим показом повторить раздел 1.
Таймауты и формулы риска не трогать (зафиксированы: `risk 60с`, `alerts 20с`,
бот `3.5с/8.0с`).
