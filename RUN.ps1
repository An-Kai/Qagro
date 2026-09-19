# Qagro launchers (PowerShell) — use python -m so console-script PATH is not needed
# Web:
#   cd Qagro; python -m pip install -r requirements.txt; python -m streamlit run app/streamlit_app.py
# API:
#   cd Qagro; python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
# Bot (.env required):
#   cd Qagro; Copy-Item .env.example .env  # paste token once
#   python -m src.bot
