#!/usr/bin/env bash
# install.sh — SES S3 Mailbox initial setup helper
#
# Prepares the environment for Docker deployment.
# Does NOT create cloud resources or run Terraform/OpenTofu apply.

set -euo pipefail

echo "=== SES S3 Mailbox — Setup ==="
echo ""

# Check Docker
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is not installed."
    echo "Install: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    echo "ERROR: Docker Compose is not available."
    echo "Install Docker Compose plugin or standalone."
    exit 1
fi

echo "[1/4] Checking .env..."
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "      Created .env from .env.example"
        echo ""
        echo "      IMPORTANT: Edit .env and fill in required values before proceeding:"
        echo "      - AWS_ACCESS_KEY_ID"
        echo "      - AWS_SECRET_ACCESS_KEY"
        echo "      - SES_BUCKET"
        echo "      - SQS_QUEUE_URL"
        echo "      - CLOUDFLARE_API_TOKEN"
        echo "      - CLOUDFLARE_ZONE_ID"
        echo "      - SESSION_SECRET (run: openssl rand -hex 32)"
        echo "      - SES_SMTP_USERNAME"
        echo "      - SES_SMTP_PASSWORD"
        echo ""
        echo "      Then re-run this script."
        exit 0
    else
        echo "ERROR: .env.example not found."
        exit 1
    fi
else
    echo "      .env already exists"
fi

echo "[2/4] Validating Docker Compose..."
docker compose config > /dev/null
echo "      OK"

echo "[3/4] Building images..."
docker compose build
echo "      Build complete"

echo "[4/4] Running migrations..."
docker compose run --rm api python3 worker/migrate.py
echo "      Migrations applied"

echo "[5/5] Bootstrapping initial admin operator..."
if docker compose run --rm api python3 scripts/bootstrap_admin.py; then
    echo ""
    echo "      IMPORTANT: Save the admin password shown above."
    echo "      It will not be displayed again."
else
    echo "      Bootstrap skipped or failed. You may need to create an operator manually."
fi

echo ""
echo "=== Ready ==="
echo ""
echo "Start the stack:"
echo "  docker compose up -d"
echo ""
echo "Access the dashboard:"
echo "  http://localhost:8000/dashboard"
echo ""
echo "Setup workflow:"
echo "  1. /dashboard/setup — check env vars"
echo "  2. /dashboard/setup/credentials — validate AWS/Cloudflare"
echo "  3. /dashboard/setup/iac — run Terraform/OpenTofu"
echo "  4. /dashboard/setup/validate — verify resources"
echo "  5. /dashboard/setup/first-mailbox — create first mailbox"
echo ""
echo "See docs/deploy-docker.md for details."
echo ""
echo "IMPORTANT: Review Terraform/OpenTofu plans before applying."
echo "           This is alpha software."
