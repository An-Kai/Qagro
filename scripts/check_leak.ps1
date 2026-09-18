# check_leak.ps1 — Qagro C1: проверка отсутствия токена в git.
# Проверяет фрагмент "8816408969" (часть токена, сам токен нигде не печатаем):
#  1) git ls-files не должен содержать ".env" (только ".env.example")
#  2) git grep по трекаемым файлам должен быть пуст
#  3) grep по рабочей копии *.py/*.md (без .git/__pycache__/.venv) должен быть пуст
#  4) история git (git log -S) не должна содержать фрагмент
# Успех: "CHECK_LEAK OK", exit 0. Утечка: сообщение + exit 1.
# Запуск:  powershell -ExecutionPolicy Bypass -File scripts/check_leak.ps1

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$ROOT = Split-Path -Parent $PSScriptRoot
if (-not $ROOT -or $ROOT -eq "") { $ROOT = (Get-Location).Path }
Set-Location -LiteralPath $ROOT

$FRAG = "8816408969"
$failed = $false

Write-Host "=== 1/4 git ls-files | .env ==="
$envTracked = git ls-files | Select-String -Pattern "^\.env$" -SimpleMatch
# Точное совпадение ".env" запрещено; ".env.example" — разрешён и ожидаем.
$exactEnv = git ls-files | Where-Object { $_ -eq ".env" }
if ($exactEnv) {
  Write-Host "FAIL: tracked .env found: $exactEnv"
  $failed = $true
} else {
  Write-Host "OK: .env not tracked"
}
$exampleTracked = git ls-files | Where-Object { $_ -eq ".env.example" }
if ($exampleTracked) { Write-Host "OK: .env.example tracked" }
else { Write-Host "WARN: .env.example NOT tracked" }

Write-Host "=== 2/4 git grep fragment in tracked files ==="
git grep -n --break --heading $FRAG -- . 2>$null | Out-String -OutVariable gitGrepOut | Out-Null
if ($gitGrepOut -and $gitGrepOut.Trim() -ne "") {
  Write-Host "FAIL: fragment found in git grep:"
  Write-Host $gitGrepOut
  $failed = $true
} else {
  Write-Host "OK: git grep empty"
}

Write-Host "=== 3/4 filesystem grep *.py/*.md (excl. .git/__pycache__/.venv) ==="
$fsHits = Get-ChildItem -Recurse -Include *.py,*.md -Force -File |
  Where-Object { $_.FullName -notmatch "\\\.git\\" -and $_.FullName -notmatch "__pycache__" -and $_.FullName -notmatch "\\\.venv\\" } |
  Select-String -Pattern $FRAG -SimpleMatch |
  Select-Object Path, LineNumber
if ($fsHits) {
  Write-Host "FAIL: fragment found in worktree:"
  $fsHits | Format-Table -AutoSize | Out-String | Write-Host
  $failed = $true
} else {
  Write-Host "OK: worktree grep empty"
}

Write-Host "=== 4/4 git history (git log -S) ==="
$hist = git log --all --oneline -S $FRAG -- . 2>$null | Out-String
if ($hist -and $hist.Trim() -ne "") {
  Write-Host "FAIL: fragment found in git history:"
  Write-Host $hist
  $failed = $true
} else {
  Write-Host "OK: git history clean"
}

Write-Host "=== bonus: .env ignored? ==="
$ign = git check-ignore -v .env 2>$null | Out-String
if ($ign -and $ign.Trim() -ne "") { Write-Host "OK: .env ignored ($($ign.Trim()))" }
else { Write-Host "WARN: .env NOT ignored (check .gitignore)" }

if ($failed) {
  Write-Host "CHECK_LEAK FAIL"
  exit 1
} else {
  Write-Host "CHECK_LEAK OK"
  exit 0
}
