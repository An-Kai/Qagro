@echo off
REM Qagro bot launcher (CMD). Token ONLY from .env, never hardcoded.
cd /d %~dp0
if not exist .env (
  echo NO .env! Copy .env.example to .env and paste token from @BotFather
  copy .env.example .env
  pause
  exit /b 1
)
python -m pip install -q -r requirements.txt
python -m src.bot
