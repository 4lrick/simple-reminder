FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -r -u 1000 botuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY simple_reminder.py .

RUN mkdir -p /app/data && \
    chown -R botuser:botuser /app && \
    chmod -R 555 /app/src && \
    chmod 555 /app/simple_reminder.py && \
    chmod 777 /app/data

USER botuser
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "simple_reminder.py"]