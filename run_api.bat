@echo off
REM Qagro API launcher (CMD)
cd /d %~dp0
python -m pip install -q -r requirements.txt
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
