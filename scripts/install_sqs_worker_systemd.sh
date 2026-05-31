#!/usr/bin/env bash
# install_sqs_worker_systemd.sh
#
# Install and start the SES S3 Mailbox SQS worker as a systemd service.
#
# Does NOT touch the legacy timer-based worker (ses-s3-mailbox-worker.timer).

set -euo pipefail

SERVICE_NAME="ses-s3-mailbox-sqs-worker"
UNIT_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SOURCE_FILE="$(dirname "$(readlink -f "$0")")/../systemd/${SERVICE_NAME}.service"

echo "=== Installing $SERVICE_NAME systemd service ==="

if [ ! -f "$SOURCE_FILE" ]; then
    echo "ERROR: unit file not found: $SOURCE_FILE"
    exit 1
fi

echo "[1/4] Copying unit file..."
sudo cp "$SOURCE_FILE" "$UNIT_FILE"
echo "      $UNIT_FILE"

echo "[2/4] Reloading systemd..."
sudo systemctl daemon-reload

echo "[3/4] Enabling and starting service..."
sudo systemctl enable --now "$SERVICE_NAME"

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
echo "  sudo systemctl disable --now $SERVICE_NAME  # disable"
