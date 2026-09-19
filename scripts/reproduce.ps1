# reproduce.ps1 — Qagro C1: воспроизводимость пайплайна (Windows PowerShell).
# Без ломки логики: только последовательный прогон зафиксированных шагов.
# Шаги: deps -> fetch_all -> features_extra -> train -> evaluate -> metrics-check -> py_compile -> predict smoke -> tests.
# Запуск из корня репо:  powershell -ExecutionPolicy Bypass -File scripts/reproduce.ps1

$ErrorActionPreference = "Stop"
# UTF-8 для вывода кириллицы
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$ROOT = Split-Path -Parent $PSScriptRoot
if (-not $ROOT -or $ROOT -eq "") { $ROOT = (Get-Location).Path }
Set-Location -LiteralPath $ROOT
Write-Host "ROOT=$ROOT"

Write-Host "=== 1/9 pip install -r requirements.txt ==="
pip install -r requirements.txt

Write-Host "=== 2/9 python src/fetch_all.py ==="
python src/fetch_all.py

Write-Host "=== 3/9 python src/features_extra.py (если есть) ==="
if (Test-Path -LiteralPath (Join-Path $ROOT "src/features_extra.py")) {
  python src/features_extra.py
} else {
  Write-Host "SKIP: src/features_extra.py нет"
}

Write-Host "=== 4/9 python src/train.py ==="
python src/train.py

Write-Host "=== 5/9 python src/evaluate.py ==="
python src/evaluate.py

Write-Host "=== 6/9 проверка метрик wheat R2>=0.60 ==="
python -c "import json; m=json.load(open('metrics/metrics.json', encoding='utf-8')); k=m.get('spring_wheat') or m.get('wheat'); r2=(k.get('lgbm') or {}).get('r2'); print('wheat R2=', r2); assert r2 is not None and r2>=0.60, 'wheat R2 < 0.60'"

Write-Host "=== 7/9 python -m py_compile src/*.py app/*.py ==="
Get-ChildItem -LiteralPath (Join-Path $ROOT "src") -Filter "*.py" | ForEach-Object {
  Write-Host ("compile: src/" + $_.Name)
  python -m py_compile $_.FullName
}
Get-ChildItem -LiteralPath (Join-Path $ROOT "app") -Filter "*.py" | ForEach-Object {
  Write-Host ("compile: app/" + $_.Name)
  python -m py_compile $_.FullName
}

Write-Host "=== 8/9 predict smoke (offline, без сети) ==="
python -c "from src.predict import predict_yield; w={'tmean_mjja':18.0,'precip_mjja':180.0,'gdd5':1450.0,'heat30':10.0,'dry_max':14.0,'et0':490.0,'p30_anom':0.0}; r=predict_yield('Esil','spring_wheat',w); print('SMOKE OK:', r['y_pred'], r['lo10'], r['hi90'], 'experimental='+str(r['experimental'])); assert isinstance(r['y_pred'], float)"

Write-Host "=== 9/9 тесты test_api / test_platform / test_agro ==="
python tests/test_api.py
python tests/test_platform.py
python tests/test_agro.py

Write-Host "REPRODUCE OK"
