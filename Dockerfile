FROM python:3.11-slim

# Пакети для збірки psycopg2 (якщо в requirements psycopg2, не psycopg2-binary)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
