# Qagro — один образ для api / bot / streamlit (команда задаётся в compose).
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Не root: api/bot/streamlit работают обычным пользователем.
RUN useradd -m -u 1000 appuser

WORKDIR /app

# fonts-dejavu нужен reportlab для кириллицы в PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=25s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# дефолт — API; bot/streamlit переопределяют command в docker-compose.yml
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
