#!/usr/bin/env bash
# install_sent_dedupe_systemd.sh
#
# Install and start the Sent mailbox deduplicator timer.

set -euo pipefail

PROJECT_DIR="$(dirname "$(readlink -f "$0")")/.."
SYSTEMD_DIR="$PROJECT_DIR/systemd"
SERVICE_NAME="ses-s3-mailbox-sent-dedupe"

echo "=== Installing $SERVICE_NAME systemd timer ==="

echo "[1/3] Copying unit files..."
sudo cp "$SYSTEMD_DIR/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
sudo cp "$SYSTEMD_DIR/$SERVICE_NAME.timer"   "/etc/systemd/system/$SERVICE_NAME.timer"
echo "      /etc/systemd/system/$SERVICE_NAME.service"
echo "      /etc/systemd/system/$SERVICE_NAME.timer"

echo "[2/3] Reloading systemd..."
sudo systemctl daemon-reload

echo "[3/3] Enabling and starting timer..."
sudo systemctl enable --now "$SERVICE_NAME.timer"

echo ""
echo "=== Done ==="
echo ""
systemctl list-timers | grep sent-dedupe || true
echo ""
echo "Useful commands:"
echo "  systemctl status $SERVICE_NAME.timer"
echo "  journalctl -u $SERVICE_NAME.service -n 20 --no-pager"
echo "  python3 -m sender.dedupe_sent              # run manually"
echo "  sudo systemctl stop $SERVICE_NAME.timer    # stop"
