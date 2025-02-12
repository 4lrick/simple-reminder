FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -r -u 1000 botuser

COPY requirements.txt .
RUN pip install --no-deps discord.py>=2.4.0 && \
    pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY simple_reminder.py .

RUN mkdir -p /app/data && \
    chown -R botuser:botuser /app

USER botuser

CMD ["python", "simple_reminder.py"]