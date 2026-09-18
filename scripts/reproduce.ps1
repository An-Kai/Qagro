# reproduce.ps1 — Qagro C1: воспроизводимость пайплайна (Windows PowerShell).
# Без ломки логики: только последовательный прогон зафиксированных шагов.
# Шаги: deps -> fetch_all -> train -> evaluate -> py_compile -> predict smoke.
# Запуск из корня репо:  powershell -ExecutionPolicy Bypass -File scripts/reproduce.ps1

$ErrorActionPreference = "Stop"
# UTF-8 для вывода кириллицы
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
try { $OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$ROOT = Split-Path -Parent $PSScriptRoot
if (-not $ROOT -or $ROOT -eq "") { $ROOT = (Get-Location).Path }
Set-Location -LiteralPath $ROOT
Write-Host "ROOT=$ROOT"

Write-Host "=== 1/6 pip install -r requirements.txt ==="
pip install -r requirements.txt

Write-Host "=== 2/6 python src/fetch_all.py ==="
python src/fetch_all.py

Write-Host "=== 3/6 python src/train.py ==="
python src/train.py

Write-Host "=== 4/6 python src/evaluate.py ==="
python src/evaluate.py

Write-Host "=== 5/6 python -m py_compile src/*.py ==="
Get-ChildItem -LiteralPath (Join-Path $ROOT "src") -Filter "*.py" | ForEach-Object {
  Write-Host ("compile: " + $_.Name)
  python -m py_compile $_.FullName
}

Write-Host "=== 6/6 predict smoke (offline, без сети) ==="
python -c "from src.predict import predict_yield; w={'tmean_mjja':18.0,'precip_mjja':180.0,'gdd5':1450.0,'heat30':10.0,'dry_max':14.0,'et0':490.0,'p30_anom':0.0}; r=predict_yield('Esil','spring_wheat',w); print('SMOKE OK:', r['y_pred'], r['lo10'], r['hi90'], 'experimental='+str(r['experimental'])); assert isinstance(r['y_pred'], float)"

Write-Host "REPRODUCE OK"
