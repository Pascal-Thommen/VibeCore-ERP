FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY sifen ./sifen
COPY openapi.json ./
COPY README.md ./

EXPOSE 8001

CMD ["uvicorn", "sifen.server:app", "--host", "0.0.0.0", "--port", "8001"]
