FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY pyproject.toml README.md openapi.json ./
COPY sifen/ ./sifen/

RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "sifen.main:app", "--host", "0.0.0.0", "--port", "8000"]
