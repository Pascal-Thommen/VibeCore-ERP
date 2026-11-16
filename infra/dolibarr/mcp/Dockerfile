FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DOLIBARR_API_URL=http://dolibarr-web:80/api/index.php \
    DOLIBARR_API_KEY=orokui-dolibarr-api-key-2026 \
    DOLIBARR_API_TIMEOUT=10.0

COPY pyproject.toml README.md server.py ./
COPY dolibarr_mcp ./dolibarr_mcp

RUN pip install --no-cache-dir .

EXPOSE 8091

CMD ["python", "/app/server.py", "--transport", "sse", "--host", "0.0.0.0", "--port", "8091"]
