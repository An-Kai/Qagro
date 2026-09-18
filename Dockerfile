# Qagro — один образ для api / bot / streamlit (команда задаётся в compose).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# fonts-dejavu нужен reportlab для кириллицы в PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000 8501

# дефолт — API; bot/streamlit переопределяют command в docker-compose.yml
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
