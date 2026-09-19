@echo off
REM Qagro web launcher (CMD): uses python -m so PATH issues don't matter
cd /d %~dp0
python -m pip install -q -r requirements.txt
python -m streamlit run app\streamlit_app.py
