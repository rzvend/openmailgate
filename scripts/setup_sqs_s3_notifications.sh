#!/usr/bin/env bash
# setup_sqs_s3_notifications.sh
#
# Configure S3 Event Notification so that every ObjectCreated event in the
# incoming/ prefix is delivered to the SQS queue ses-s3-mailbox-incoming.
#
# This script also creates the IAM policy on the SQS queue that allows S3
# to send messages to it.
#
# Prerequisites:
#   - AWS CLI installed and configured (aws configure or IAM role)
#   - SQS queue ses-s3-mailbox-incoming already created
#   - S3 bucket ricardo-vc-ses-mailbox already exists

set -euo pipefail

AWS_REGION="us-east-1"
BUCKET_NAME="ricardo-vc-ses-mailbox"
QUEUE_NAME="ses-s3-mailbox-incoming"
NOTIFICATION_ID="ses-s3-mailbox-incoming-to-sqs"

echo "=== Region:       $AWS_REGION"
echo "=== Bucket:       $BUCKET_NAME"
echo "=== Queue:        $QUEUE_NAME"
echo "=== Notification: $NOTIFICATION_ID"
echo ""

# ── Account ID ────────────────────────────────────────────────────────────
echo "[1/6] Getting AWS Account ID..."
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --region "$AWS_REGION")"
echo "      Account:  $ACCOUNT_ID"

# ── Queue URL & ARN ───────────────────────────────────────────────────────
echo "[2/6] Getting SQS Queue URL and ARN..."
QUEUE_URL="$(aws sqs get-queue-url \
  --queue-name "$QUEUE_NAME" \
  --region "$AWS_REGION" \
  --query 'QueueUrl' \
  --output text)"
echo "      URL:      $QUEUE_URL"

QUEUE_ARN="$(aws sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names QueueArn \
  --region "$AWS_REGION" \
  --query 'Attributes.QueueArn' \
  --output text)"
echo "      ARN:      $QUEUE_ARN"

# ── SQS Policy ────────────────────────────────────────────────────────────
echo "[3/6] Setting SQS Queue Policy (allow S3 to send messages)..."

POLICY_FILE="/tmp/sqs-policy-ses-s3-mailbox.json"

cat > "$POLICY_FILE" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3SendMessage",
      "Effect": "Allow",
      "Principal": {
        "Service": "s3.amazonaws.com"
      },
      "Action": "sqs:SendMessage",
      "Resource": "$QUEUE_ARN",
      "Condition": {
        "ArnLike": {
          "aws:SourceArn": "arn:aws:s3:::$BUCKET_NAME"
        },
        "StringEquals": {
          "aws:SourceAccount": "$ACCOUNT_ID"
        }
      }
    }
  ]
}
EOF

python3 -c "
import boto3, json

with open('$POLICY_FILE') as f:
    policy = json.load(f)

sqs = boto3.client('sqs', region_name='$AWS_REGION')
sqs.set_queue_attributes(
    QueueUrl='$QUEUE_URL',
    Attributes={'Policy': json.dumps(policy)}
)
print('      Policy applied.')
" || { echo "ERROR: Failed to set SQS policy"; exit 1; }

rm -f "$POLICY_FILE"

# ── Snapshot existing notification config ──────────────────────────────────
echo "[4/6] Checking existing S3 notification configuration..."
BACKUP_FILE="/tmp/s3-notification-before-ses-s3-mailbox.json"

if aws s3api get-bucket-notification-configuration \
      --bucket "$BUCKET_NAME" \
      --region "$AWS_REGION" \
      --output json > "$BACKUP_FILE" 2>/dev/null; then
  echo "      Existing config backed up to: $BACKUP_FILE"
  echo "      (saved for reference — will be replaced below)"
else
  echo "      No existing notification configuration."
fi

# ── S3 Notification ───────────────────────────────────────────────────────
echo "[5/6] Setting S3 Event Notification..."

NOTIFICATION_FILE="/tmp/s3-notification-ses-s3-mailbox.json"

cat > "$NOTIFICATION_FILE" <<EOF
{
  "QueueConfigurations": [
    {
      "Id": "$NOTIFICATION_ID",
      "QueueArn": "$QUEUE_ARN",
      "Events": [
        "s3:ObjectCreated:*"
      ],
      "Filter": {
        "Key": {
          "FilterRules": [
            {
              "Name": "prefix",
              "Value": "incoming/"
            }
          ]
        }
      }
    }
  ]
}
EOF

aws s3api put-bucket-notification-configuration \
  --bucket "$BUCKET_NAME" \
  --notification-configuration "file://$NOTIFICATION_FILE" \
  --region "$AWS_REGION"

echo "      Notification configured."
rm -f "$NOTIFICATION_FILE"

# ── Verificação ────────────────────────────────────────────────────────────
echo "[6/6] Verifying configuration..."
echo ""
echo "S3 Bucket Notification:"
aws s3api get-bucket-notification-configuration \
  --bucket "$BUCKET_NAME" \
  --region "$AWS_REGION"

echo ""
echo "SQS Queue Policy:"
aws sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names Policy \
  --region "$AWS_REGION" \
  --query 'Attributes.Policy' \
  --output text | python3 -m json.tool 2>/dev/null || true

echo ""
echo "=== Done ==="
echo "S3 events for s3://$BUCKET_NAME/incoming/ are now sent to SQS $QUEUE_NAME."
echo ""
echo "Start the worker:"
echo "  python3 -m worker.sqs_worker"
echo ""
echo "Or via systemd (after install_sqs_worker_systemd.sh):"
echo "  sudo systemctl start ses-s3-mailbox-sqs-worker"
echo "  journalctl -u ses-s3-mailbox-sqs-worker -f"
