# IaC Troubleshooting — Dashboard Setup

Guide for common OpenTofu/Terraform errors during `/dashboard/setup/iac`.

All commands below run inside the API container:

```bash
docker compose exec api sh -lc '<command>'
```

---

## 1. OpenTofu missing in container

**Symptoms:**
```
tofu: not found
FileNotFoundError: tofu
ERROR: tofu binary not found
```

**Cause:** The API container image does not include OpenTofu.

**Fix:**
```bash
docker compose build api
docker compose up -d api
docker compose exec api sh -lc 'which tofu && tofu --version'
```

Expected output:
```
/usr/local/bin/tofu
OpenTofu v1.12.1
```

---

## 2. IAC_WORKDIR missing

**Symptoms:**
```
/app/iac: No such file or directory
```

**Cause:** `IAC_WORKDIR` points to a directory that does not exist inside the container.

**Check:**
```bash
docker compose exec api sh -lc 'ls -la /app/iac /app/terraform 2>/dev/null || true'
docker compose exec api sh -lc 'env | grep ^IAC_'
```

**Expected:**
- `/app/iac` → `/app/terraform` (symlink)
- `IAC_WORKDIR=/app/iac`
- Terraform files visible at both paths

If the symlink is missing, rebuild:
```bash
docker compose build api && docker compose up -d api
```

---

## 3. DNS / registry failure during tofu init

**Symptoms:**
```
Failed to query available provider packages
could not resolve host: registry.opentofu.org
i/o timeout
context deadline exceeded
```

**Cause:** Container DNS cannot resolve or reach the OpenTofu registry.

**Check:**
```bash
docker compose exec api sh -lc 'cat /etc/resolv.conf'
docker compose exec api sh -lc 'getent hosts registry.opentofu.org || true'
```

**Fix — DNS fallback in compose:**
```yaml
# docker-compose.yml
services:
  api:
    dns:
      - 8.8.8.8
```

Already included in the default compose file. If you use a private network, VPN, or split DNS, adjust the DNS server accordingly.

---

## 4. Resource already exists outside state

**Symptoms:**
```
EntityAlreadyExists
AlreadyExists
User already exists
Rule set already exists
BucketAlreadyOwnedByYou
QueueAlreadyExists
```

**Cause:** The resource exists in AWS/Cloudflare but is not tracked in the current OpenTofu state.

This commonly happens when:
- Setup was run before,
- Resources were created manually,
- State was lost,
- A previous apply partially succeeded.

**Do not delete resources blindly.**

**Fix — check current state:**
```bash
docker compose exec api sh -lc 'cd /app/iac && tofu state list'
```

**Fix — import existing resources:**
```bash
# IAM user for SMTP
docker compose exec api sh -lc 'cd /app/iac && tofu import aws_iam_user.ses_smtp_sender ses-s3-mailbox-smtp-sender'

# SES receipt rule set
docker compose exec api sh -lc 'cd /app/iac && tofu import aws_ses_receipt_rule_set.main ses-s3-mailbox-rules'
```

Then run plan again to confirm it is safe:
```bash
docker compose exec api sh -lc 'cd /app/iac && tofu plan -var="domain=openmailgate.ricardo.vc" -var="mail_bucket_name=ses-openmailgate-mailbox" -var="sqs_queue_name=ses-openmailgate-incoming"'
```

Only apply if the plan shows:
- 0 resources to destroy
- No unexpected changes

---

## 5. Access denied / invalid AWS credentials

**Symptoms:**
```
AccessDenied
UnauthorizedOperation
InvalidClientTokenId
SignatureDoesNotMatch
NoCredentialProviders
could not find credentials
```

**Cause:** AWS credentials are missing, invalid, expired, or lack required permissions.

**Check (masks secret):**
```bash
docker compose exec api sh -lc 'env | grep -E "^AWS_REGION|^AWS_ACCESS_KEY_ID"'
```

**Required IAM permissions:**
- S3: `ListBucket`, `GetObject`, `PutObject`, `DeleteObject`
- SQS: `ReceiveMessage`, `DeleteMessage`, `GetQueueAttributes`, `ChangeMessageVisibility`
- SES: `SendRawEmail`, `SendEmail`, domain identity management, DKIM
- IAM: create user, policy, access key for SES SMTP sender

---

## 6. Cloudflare token or Zone ID problems

**Symptoms:**
```
Cloudflare 403
Unauthorized
Invalid zone identifier
```

**Cause:** Wrong Zone ID, Account ID used instead of Zone ID, or token lacks DNS edit permission.

**Fix:**
- Use **Zone ID** for the DNS zone (e.g. `0237441...`), not the Account ID.
- The token must have permission to **edit DNS records** for the zone.
- Get your Zone ID from Cloudflare Dashboard → domain → Overview → API section.

---

## 7. SES sandbox

**Symptoms:**
```
Outbound email works only to verified recipients.
Message rejected: Email address is not verified.
```

**Cause:** The AWS SES account/region is still in sandbox mode.

**Fix:**
- Verify individual recipient email addresses for testing, or
- Request SES production access via AWS Support.

See [AWS SES sandbox documentation](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html).

---

## 8. Sensitive state

OpenTofu state (`terraform.tfstate`) may contain:
- SES SMTP credentials (username and password)
- Access key IDs and secret keys
- Domain verification tokens

**Rules:**
- Treat `terraform.tfstate` and `*.tfstate.*` as sensitive files.
- Never commit state files to version control.
- Back up state files securely.
- State in this project is stored at `/app/state/iac` (Docker volume).
