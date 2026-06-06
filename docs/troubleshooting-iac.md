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

## 3b. Pre-apply conflict detection

The dashboard can detect resources that already exist in AWS/Cloudflare but
are not tracked in the current OpenTofu state. This helps prevent `AlreadyExists`
errors before running `apply`.

**How it works:**
1. The expected resource names are computed from the current configuration.
2. `tofu state list` shows which resources are already tracked.
3. AWS and Cloudflare APIs are queried to check if resources exist remotely.
4. If a resource exists remotely but is not in the state, it is flagged as
   `exists_outside_state`.

**Use from the dashboard:**
1. Open `/dashboard/setup/iac`.
2. Click **Check conflicts**.
3. Review the conflict table.
4. If any resource shows `outside state`, the Apply button is blocked.

**Status meanings:**
- `ok` — resource is tracked and exists remotely.
- `missing` — resource is neither in state nor exists remotely (safe to create).
- `exists_outside_state` — exists remotely but NOT in state (apply would fail with AlreadyExists).
- `ambiguous` — multiple matching resources found (review manually).
- `error` — API check failed (re-run or check credentials).

**Next step**: If conflicts are found, use the guided import/adopt recovery flow,
change resource names, or clean up the existing resources manually.

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

### 4a. Plan keeps recreating resources after import / state not persistent

**Symptoms:**
```
Plan shows all resources as new even after importing them.
After docker compose rebuild, state appears empty.
Plan: X to add, 0 to change, 0 to destroy (every time after restart).
```

**Cause:** OpenTofu state was being written to `/app/terraform/terraform.tfstate`, which lives inside the container image (from `COPY . .` in the Dockerfile). That path is rebuilt on every `docker compose build` and lost on container restart. The persistent volume is at `/app/state/iac`.

**Confirm:**
```bash
docker compose exec api sh -lc 'find /app -name "terraform.tfstate*"'
docker compose exec api sh -lc 'ls -la /app/state/iac/'
```

The state file should be under `/app/state/iac/`, not under `/app/terraform/`.

**Fix — ensure state is stored in the persistent volume:**
```bash
# The alpha default now uses backend "local" with path /app/state/iac/terraform.tfstate.
# If your state is missing, reinit and reimport:
docker compose exec api sh -lc 'cd /app/iac && tofu init -reconfigure'

# Reimport any resources that already exist in AWS/Cloudflare:
docker compose exec api sh -lc 'cd /app/iac && tofu import aws_iam_user.ses_smtp_sender ses-s3-mailbox-smtp-sender'
docker compose exec api sh -lc 'cd /app/iac && tofu import aws_ses_receipt_rule_set.main ses-s3-mailbox-rules'
```

Then run plan again. It should now show only the missing resources.

### 4b. Recovering from a partial apply

**Symptoms:** Some resources were created by a previous `tofu apply` that failed
midway. The state file tracks only the resources that were fully applied.
Running apply again fails with `AlreadyExists` or `EntityAlreadyExists` for
resources that already exist in AWS/Cloudflare but are not in the state.

**Do not delete resources blindly.** S3 buckets, SES receipt rule sets, and DNS
records may already be in use and referenced by other services.

**Recovery flow:**

1. Check what is already tracked in the state:
   ```bash
   docker compose exec api sh -lc 'cd /app/iac && tofu state list'
   ```

2. Import each missing resource into the state. Examples:
   ```bash
   # IAM user for SMTP
   docker compose exec api sh -lc 'cd /app/iac && tofu import aws_iam_user.ses_smtp_sender ses-s3-mailbox-smtp-sender'

   # SES receipt rule set
   docker compose exec api sh -lc 'cd /app/iac && tofu import aws_ses_receipt_rule_set.main ses-s3-mailbox-rules'

   # S3 bucket (adjust name for your setup)
   docker compose exec api sh -lc 'cd /app/iac && tofu import aws_s3_bucket.mail_bucket ses-openmailgate-mailbox'

   # SQS queue
   docker compose exec api sh -lc 'cd /app/iac && tofu import aws_sqs_queue.mail_queue ses-openmailgate-incoming'

   # Cloudflare DNS records require the record ID from the Cloudflare API
   ```

3. Run plan again to verify that only the truly missing resources are shown:
   ```bash
   docker compose exec api sh -lc 'cd /app/iac && tofu plan -var="domain=..." -var="mail_bucket_name=..." -var="sqs_queue_name=..."'
   ```

4. Only apply when the plan shows no unexpected destroys and a safe number of additions.

You can also use the **Show state** button on the `/dashboard/setup/iac` page
to inspect the current state from the dashboard.

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
