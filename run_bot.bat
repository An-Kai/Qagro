@echo off
REM Qagro bot launcher (CMD). Token ONLY from .env, never hardcoded.
cd /d %~dp0
if not exist .env (
  echo NO .env! Copy .env.example to .env and paste token from @BotFather
  copy .env.example .env
  echo.
  echo IMPORTANT: open .env in Notepad, replace xxx with your @BotFather token, then run again.
  echo Or skip the bot and use the web demo: run_web.bat
  pause
  exit /b 1
)
findstr /C:"TELEGRAM_BOT_TOKEN=xxx" .env >nul
if %errorlevel%==0 (
  echo Token is still xxx - paste your @BotFather token into .env first.
  echo Or skip the bot and use the web demo: run_web.bat
  pause
  exit /b 1
)
python -m pip install -q -r requirements.txt
python -m src.bot
