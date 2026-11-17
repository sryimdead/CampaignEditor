FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data \
    && chown app:app /data

WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Код и общий config.yaml (без секретов). local_config.yaml монтируется снаружи.
COPY app ./app
COPY config.yaml ./

# Конфиги читаются из /app, а база SQLite (относительный путь) создаётся в /data (volume).
ENV CAMPAIGN_EDITOR_CONFIG_DIR=/app
USER app
WORKDIR /data

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "8000"]
