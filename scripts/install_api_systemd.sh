#!/usr/bin/env bash
# install_api_systemd.sh
#
# Install and start the SES S3 Mailbox API/Dashboard as a systemd service.

set -euo pipefail

SERVICE_NAME="ses-s3-mailbox-api"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SOURCE_FILE="$(dirname "$(readlink -f "$0")")/../systemd/${SERVICE_NAME}.service"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root (sudo)"
    exit 1
fi

echo "=== Installing $SERVICE_NAME systemd service ==="

if [ ! -f "$SOURCE_FILE" ]; then
    echo "ERROR: unit file not found: $SOURCE_FILE"
    exit 1
fi

echo "[1/4] Copying unit file..."
cp "$SOURCE_FILE" "$UNIT_FILE"
echo "      $UNIT_FILE"

echo "[2/4] Reloading systemd..."
systemctl daemon-reload

echo "[3/4] Enabling and starting service..."
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo "[4/4] Service status:"
echo ""
systemctl status "$SERVICE_NAME" --no-pager || true

echo ""
echo "=== Done ==="
echo ""
echo "Useful commands:"
echo "  journalctl -u $SERVICE_NAME -f          # follow logs"
echo "  journalctl -u $SERVICE_NAME -n 50       # last 50 lines"
echo "  sudo systemctl stop $SERVICE_NAME       # stop"
echo "  sudo systemctl restart $SERVICE_NAME    # restart"
echo "  curl http://127.0.0.1:8000/dashboard    # test"
