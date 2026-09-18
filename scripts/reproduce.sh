#!/usr/bin/env bash
# reproduce.sh — Qagro C1: воспроизводимость пайплайна (Linux/macOS/Git-Bash).
# Без ломки логики: только последовательный прогон зафиксированных шагов.
# Шаги: deps -> fetch_all -> train -> evaluate -> py_compile -> predict smoke.
# Запуск из корня репо:  bash scripts/reproduce.sh
set -euo pipefail
cd "$(dirname "$0")/.."
echo "ROOT=$(pwd)"

echo "=== 1/6 pip install -r requirements.txt ==="
pip install -r requirements.txt

echo "=== 2/6 python src/fetch_all.py ==="
python3 src/fetch_all.py

echo "=== 3/6 python src/train.py ==="
python3 src/train.py

echo "=== 4/6 python src/evaluate.py ==="
python3 src/evaluate.py

echo "=== 5/6 python -m py_compile src/*.py ==="
python3 -m py_compile src/*.py

echo "=== 6/6 predict smoke (offline, без сети) ==="
python3 -c "from src.predict import predict_yield; w={'tmean_mjja':18.0,'precip_mjja':180.0,'gdd5':1450.0,'heat30':10.0,'dry_max':14.0,'et0':490.0,'p30_anom':0.0}; r=predict_yield('Esil','spring_wheat',w); print('SMOKE OK:', r['y_pred'], r['lo10'], r['hi90'], 'experimental='+str(r['experimental'])); assert isinstance(r['y_pred'], float)"

echo "REPRODUCE OK"
