#!/usr/bin/env bash
# reproduce.sh — Qagro C1: воспроизводимость пайплайна (Linux/macOS/Git-Bash).
# Без ломки логики: только последовательный прогон зафиксированных шагов.
# Шаги: deps -> fetch_all -> features_extra -> train -> evaluate -> metrics-check -> py_compile -> predict smoke -> tests.
# Запуск из корня репо:  bash scripts/reproduce.sh
set -euo pipefail
cd "$(dirname "$0")/.."
echo "ROOT=$(pwd)"

echo "=== 1/9 pip install -r requirements.txt ==="
pip install -r requirements.txt

echo "=== 2/9 python src/fetch_all.py ==="
python3 src/fetch_all.py

echo "=== 3/9 python src/features_extra.py (если есть) ==="
if [ -f "src/features_extra.py" ]; then
  python3 src/features_extra.py
else
  echo "SKIP: src/features_extra.py нет"
fi

echo "=== 4/9 python src/train.py ==="
python3 src/train.py

echo "=== 5/9 python src/evaluate.py ==="
python3 src/evaluate.py

echo "=== 6/9 проверка метрик wheat R2>=0.60 ==="
python3 -c "import json; m=json.load(open('metrics/metrics.json', encoding='utf-8')); k=m.get('spring_wheat') or m.get('wheat'); r2=(k.get('lgbm') or {}).get('r2'); print('wheat R2=', r2); assert r2 is not None and r2>=0.60, 'wheat R2 < 0.60'"

echo "=== 7/9 python -m py_compile src/*.py app/*.py ==="
python3 -m py_compile src/*.py app/*.py

echo "=== 8/9 predict smoke (offline, без сети) ==="
python3 -c "from src.predict import predict_yield; w={'tmean_mjja':18.0,'precip_mjja':180.0,'gdd5':1450.0,'heat30':10.0,'dry_max':14.0,'et0':490.0,'p30_anom':0.0}; r=predict_yield('Esil','spring_wheat',w); print('SMOKE OK:', r['y_pred'], r['lo10'], r['hi90'], 'experimental='+str(r['experimental'])); assert isinstance(r['y_pred'], float)"

echo "=== 9/9 тесты test_api / test_platform / test_agro ==="
python3 tests/test_api.py
python3 tests/test_platform.py
python3 tests/test_agro.py

echo "REPRODUCE OK"
