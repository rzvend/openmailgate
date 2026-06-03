FROM python:3.12-slim

WORKDIR /app

# Install system deps for Dovecot password tools (doveadm pw) used by the app
RUN apt-get update && apt-get install -y --no-install-recommends \
    dovecot-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data/maildir /app/data/raw-emails /app/data/raw-outbound /app/logs /app/state/iac

EXPOSE 8000

# Override per service via docker-compose command:
#   api:          uvicorn api.main:app --host 0.0.0.0 --port 8000
#   worker-sqs:   python3 -m worker.sqs_worker
#   smtp-sender:  python3 -m sender.smtp_server
CMD ["python3", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
