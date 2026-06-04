FROM python:3.12-slim

ARG TOFU_VERSION=1.12.1

WORKDIR /app

# Install system deps: curl (for tofu download), dovecot-core (for doveadm pw)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    dovecot-core \
    && rm -rf /var/lib/apt/lists/*

# Install OpenTofu from official GitHub releases (pinned version, checksum verified)
RUN TOFU_ARCH="linux_amd64" \
    && TOFU_URL="https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_${TOFU_ARCH}.zip" \
    && TOFU_SUMS="https://github.com/opentofu/opentofu/releases/download/v${TOFU_VERSION}/tofu_${TOFU_VERSION}_SHA256SUMS" \
    && curl -fsSL "$TOFU_URL" -o /tmp/tofu.zip \
    && curl -fsSL "$TOFU_SUMS" -o /tmp/SHA256SUMS \
    && EXPECTED=$(grep "${TOFU_ARCH}.zip" /tmp/SHA256SUMS | awk '{print $1}') \
    && ACTUAL=$(sha256sum /tmp/tofu.zip | awk '{print $1}') \
    && test "$EXPECTED" = "$ACTUAL" \
    && python3 -c "import zipfile; zipfile.ZipFile('/tmp/tofu.zip').extractall('/tmp/tofu-bin')" \
    && mv /tmp/tofu-bin/tofu /usr/local/bin/tofu \
    && chmod +x /usr/local/bin/tofu \
    && rm -rf /tmp/tofu.zip /tmp/tofu-bin /tmp/SHA256SUMS

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Align IAC_WORKDIR with the actual Terraform files location
RUN ln -s /app/terraform /app/iac

RUN mkdir -p /app/data/maildir /app/data/raw-emails /app/data/raw-outbound /app/logs /app/state/iac

EXPOSE 8000

# Override per service via docker-compose command:
#   api:          uvicorn api.main:app --host 0.0.0.0 --port 8000
#   worker-sqs:   python3 -m worker.sqs_worker
#   smtp-sender:  python3 -m sender.smtp_server
CMD ["python3", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
