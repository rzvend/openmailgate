# Docker Deployment

> Alpha software. Review OpenTofu plans before applying. Protect your `.env` file and backup your data/state.

This guide describes the Docker Compose deployment flow for OpenMailGate `v0.1.0-alpha`.

The validated alpha flow is:

```text
Docker Compose → dashboard first-run → AWS/Cloudflare validation → IAM preflight
→ OpenTofu init/plan/apply → runtime env sync → post-apply validation
→ first mailbox → IMAP/SMTP client
```

## Requirements

### Host

* Linux VM or server.
* Docker Engine.
* Docker Compose plugin.
* Git.
* Recommended: at least 2 vCPU, 2 GB RAM and 20 GB disk.

### AWS

You need an AWS account and an IAM access key for the setup wizard.

Required values:

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_iam_access_key_id
AWS_SECRET_ACCESS_KEY=your_iam_secret_access_key
```

Do not use AWS root account access keys.

For alpha testing, create a dedicated IAM user for OpenMailGate setup.

Simplest alpha option:

```text
AdministratorAccess
```

More restricted alpha option:

```text
AmazonSESFullAccess
AmazonS3FullAccess
AmazonSQSFullAccess
IAMFullAccess
```

These policies allow the setup flow to create and validate SES, S3, SQS and IAM resources used by OpenMailGate.

For long-term or production-like deployments, replace broad policies with a least-privilege customer-managed policy after reviewing the OpenTofu resources.

### AWS SES production access

If your AWS SES account is still in sandbox mode, outbound email may only be allowed to verified recipients.

For real email sending, request SES production access in the AWS region used by OpenMailGate, for example:

```env
AWS_REGION=us-east-1
```

OpenMailGate can create and validate SES identities, DKIM records, receipt rules and Custom MAIL FROM records, but SES account sending limits and sandbox/production status are controlled by AWS.

### Cloudflare

The alpha setup path assumes a Cloudflare-managed DNS zone.

Required values:

```env
CLOUDFLARE_ZONE_ID=your_cloudflare_zone_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token
```

Minimum expected Cloudflare token permissions:

```text
Zone: Read
DNS: Read
DNS: Edit
```

OpenMailGate uses this token to create or validate:

* MX records for SES receiving;
* TXT records for SPF;
* TXT records for SES domain verification;
* CNAME records for SES DKIM;
* MX/TXT records for SES Custom MAIL FROM.

### Domain

Use a domain or subdomain dedicated to OpenMailGate.

For alpha testing, a subdomain is recommended:

```env
MAIL_DOMAIN=alpha.example.com
```

This will create mail-related DNS records for that domain/subdomain.

## 1. Clone the repository

```bash
git clone https://github.com/rzvend/openmailgate.git
cd openmailgate
```

Check repository status:

```bash
git status
git log --oneline -5
```

Expected:

```text
nothing to commit, working tree clean
```

## 2. Create and edit `.env`

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

Fill the minimum required values:

```env
SESSION_SECRET=replace_with_a_long_random_secret

MAIL_DOMAIN=alpha.example.com

AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=replace_me
AWS_SECRET_ACCESS_KEY=replace_me

CLOUDFLARE_ZONE_ID=replace_me
CLOUDFLARE_API_TOKEN=replace_me

API_BIND=YOUR_VM_IP
IMAP_BIND=YOUR_VM_IP
SMTP_BIND=YOUR_VM_IP
```

Do not manually fill these before the infrastructure setup:

```env
S3_BUCKET=
SQS_QUEUE_URL=
SES_SMTP_USERNAME=
SES_SMTP_PASSWORD=
```

They are created by OpenTofu and synced later through the dashboard.

The SES SMTP credentials are different from the setup AWS credentials:

```text
AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
  → used by the dashboard/OpenTofu setup

SES_SMTP_USERNAME / SES_SMTP_PASSWORD
  → generated for outbound mail through Amazon SES SMTP
```

## 3. Validate Docker Compose

```bash
docker compose config
```

Expected:

```text
No rendering errors
No obsolete "version" warning
MAIL_DOMAIN rendered correctly
API/IMAP/SMTP binds rendered correctly
```

If Docker returns a permission error for `/var/run/docker.sock`, add your user to the Docker group and reopen the session:

```bash
sudo usermod -aG docker "$USER"
exit
```

Then SSH again and retry:

```bash
docker ps
```

## 4. Start the stack

```bash
docker compose up -d --build
docker compose ps
```

Expected services:

```text
api
dovecot
smtp-sender
worker-sqs
```

Check the API:

```bash
curl -i http://YOUR_VM_IP:8000/health
```

Expected:

```text
HTTP/1.1 200 OK
```

## 5. First-run dashboard setup

Open:

```text
http://YOUR_VM_IP:8000
```

On a fresh install, the dashboard redirects to the first-run setup flow.

Create the first admin user:

```text
/setup
→ create first admin
→ login
```

Manual admin bootstrap scripts are not part of the normal Docker alpha flow.

Migrations are applied automatically by the Docker entrypoint during API startup.

## 6. Validate AWS and Cloudflare credentials

In the dashboard:

```text
Setup → Credentials
→ Validate AWS/Cloudflare
```

Expected:

```text
AWS STS OK
Cloudflare zone OK
```

If validation fails, check:

* AWS access key ID;
* AWS secret access key;
* AWS region;
* Cloudflare zone ID;
* Cloudflare API token;
* token permissions.

## 7. IAM preflight

In the dashboard:

```text
Setup → IAM Preflight
```

Expected:

```text
ready
```

The IAM preflight checks whether the setup can safely create or reuse the IAM user/access keys needed for SES SMTP sending.

If the IAM user already has the maximum number of access keys, follow the dashboard guidance before continuing.

## 8. Run OpenTofu init/plan/apply

In the dashboard:

```text
Infrastructure Setup
→ Run init
```

Expected:

```text
OpenTofu has been successfully initialized
```

Then run:

```text
Run plan
```

For a fresh alpha install, the expected plan is usually:

```text
Plan: 23 to add, 0 to change, 0 to destroy
```

Review the plan carefully before applying.

Expected resources include:

* SES domain identity;
* SES DKIM;
* SES Custom MAIL FROM;
* SES receipt rule set/rule;
* S3 bucket;
* S3 bucket notification;
* SQS queue;
* SQS queue policy;
* IAM user/access key/policy for SES SMTP relay;
* Cloudflare MX/SPF/DKIM/verification records;
* Custom MAIL FROM DNS records.

Do not apply if there are unexpected destroys.

Then:

```text
Run apply
```

Expected:

```text
Apply complete
```

## 9. Sync runtime environment

After OpenTofu apply, use the dashboard action to update the runtime `.env`.

Expected updated keys:

```text
DEFAULT_FROM_DOMAIN
S3_BUCKET
SQS_QUEUE_URL
SES_SMTP_USERNAME
SES_SMTP_PASSWORD
```

Docker Compose loads `env_file` values when containers are created, not when they are only restarted.

Recreate the services that need the new runtime values:

```bash
docker compose up -d --force-recreate api worker-sqs smtp-sender
```

Then check:

```bash
docker compose ps
curl -i http://YOUR_VM_IP:8000/health
```

You can validate the environment inside containers without exposing secrets:

```bash
docker compose exec worker-sqs sh -lc 'echo "S3_BUCKET=$S3_BUCKET"; echo "SQS_QUEUE_URL=$SQS_QUEUE_URL"; echo "MAIL_DOMAIN=$MAIL_DOMAIN"'
```

```bash
docker compose exec smtp-sender sh -lc 'echo "SES_SMTP_USERNAME=$SES_SMTP_USERNAME"; echo "SES_SMTP_HOST=$SES_SMTP_HOST"; echo "SES_SMTP_PORT=$SES_SMTP_PORT"; test -n "$SES_SMTP_PASSWORD" && echo "SES_SMTP_PASSWORD=<set>" || echo "SES_SMTP_PASSWORD=<empty>"'
```

## 10. Post-apply validation

In the dashboard:

```text
Post-apply validation
→ Run validation
```

Expected checks:

```text
AWS STS OK
S3 bucket OK
S3 notification OK
SQS queue OK
SES identity OK
SES DKIM OK
SES receipt rule OK
SES MAIL FROM OK
Cloudflare DNS OK
MAIL FROM MX OK
MAIL FROM SPF OK
```

The validated alpha target is:

```text
Warnings: 0
Errors: 0
```

If OpenTofu outputs appear as skipped but all resources are OK and `.env` was synced correctly, document the result and continue. This is a known non-blocking validation display issue.

## 11. Create the first mailbox

In the dashboard:

```text
First mailbox
```

Create an address such as:

```text
user@alpha.example.com
```

The dashboard should:

* create the mailbox;
* create the email address;
* create the Maildir structure;
* write `/app/dovecot/users`;
* show IMAP/SMTP settings.

Restart Dovecot when instructed:

```bash
docker compose restart dovecot
```

## 12. Validate Dovecot and Maildir

Replace the email address with the one created in the dashboard:

```bash
docker compose exec dovecot doveadm user user@alpha.example.com
```

List mailboxes:

```bash
docker compose exec dovecot doveadm mailbox list -u user@alpha.example.com
```

Check `Sent`:

```bash
docker compose exec dovecot doveadm mailbox status -u user@alpha.example.com messages Sent
```

Test writing to `Sent`:

```bash
printf "From: test@example.com\nSubject: append test\n\nok\n" | \
  docker compose exec -T dovecot doveadm save -u user@alpha.example.com -m Sent
```

Check again:

```bash
docker compose exec dovecot doveadm mailbox status -u user@alpha.example.com messages Sent
```

Expected:

```text
No Permission denied
Sent messages increases
```

## 13. Thunderbird settings

Use the settings shown by the dashboard.

Typical alpha settings:

| Field               | Value              |
| ------------------- | ------------------ |
| IMAP Server         | Host IP            |
| IMAP Port           | 143                |
| IMAP Security       | None               |
| IMAP Authentication | Normal password    |
| IMAP Username       | Full email address |
| SMTP Server         | Host IP            |
| SMTP Port           | 2525               |
| SMTP Security       | None               |
| SMTP Authentication | None               |
| SMTP Username       | Blank              |

The alpha deployment does not provide IMAP/SMTP TLS yet. Use only in trusted networks, lab environments or behind your own secure access layer.

## 14. Test outbound and inbound email

From Thunderbird, send an email to an external mailbox.

Expected:

```text
Email is delivered
Copy is saved in Sent
No "Copying to Sent" error
```

Reply from the external mailbox.

Expected:

```text
Reply is received in Thunderbird
Message is stored locally through Maildir/Dovecot
```

Useful logs:

```bash
docker compose logs --tail=100 smtp-sender
docker compose logs --tail=200 worker-sqs
docker compose logs --tail=100 dovecot
```

## Services

| Service     | Default host binding        | Description                    |
| ----------- | --------------------------- | ------------------------------ |
| API         | `${API_BIND}:${API_PORT}`   | Dashboard and JSON API         |
| Dovecot     | `${IMAP_BIND}:${IMAP_PORT}` | IMAP server                    |
| SMTP sender | `${SMTP_BIND}:${SMTP_PORT}` | Local SMTP relay to Amazon SES |
| Worker SQS  | no public port              | Consumes SQS events from S3    |

Example alpha ports:

```text
API: 8000
IMAP: 143
SMTP: 2525
```

## Day-to-day commands

```bash
docker compose up -d
docker compose ps
docker compose logs -f api
docker compose logs -f worker-sqs
docker compose logs -f smtp-sender
docker compose logs -f dovecot
docker compose restart api
docker compose restart dovecot
docker compose down
```

Recreate services after `.env` runtime sync:

```bash
docker compose up -d --force-recreate api worker-sqs smtp-sender
```

## Backup notes

Important persistent data:

```text
Docker volume: app_data
Docker volume: dovecot_data
Docker volume: iac_state
.env
```

Important files inside volumes:

```text
/app/data/mailbox.db
/app/data/maildir/
/app/state/iac/
```

Backup before major changes.

See:

```text
docs/backup-restore.md
```

## Security

Protect `.env`:

```bash
chmod 600 .env
```

Never commit:

```text
.env
data/
OpenTofu state
backups
secrets
```

Never expose:

```text
AWS_SECRET_ACCESS_KEY
CLOUDFLARE_API_TOKEN
SES_SMTP_PASSWORD
SESSION_SECRET
```

Review OpenTofu plans before applying.

The setup creates or updates cloud resources and may generate AWS costs.

For production-like use, add your own security layer, such as VPN, Tailnet, reverse proxy with HTTPS, firewall rules, and TLS for mail protocols when available.

## Alpha limitations

* Not production-ready.
* Dashboard HTTPS is not provided by default.
* IMAP runs without TLS in the alpha Docker flow.
* SMTP sender runs without local SMTP authentication in the alpha Docker flow.
* Use only in trusted networks or behind your own secure access layer.
* OpenTofu automation is alpha; review plans before applying.
* Automated tests currently need triage.
* PostgreSQL, RBAC, metrics and hardening are future work.
* AWS and Cloudflare are assumed for the automated setup path.

## Troubleshooting

### Docker socket permission denied

```text
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

Fix:

```bash
sudo usermod -aG docker "$USER"
exit
```

Then SSH again and test:

```bash
docker ps
```

### Runtime env values do not appear inside containers

After syncing OpenTofu outputs to `.env`, recreate services:

```bash
docker compose up -d --force-recreate api worker-sqs smtp-sender
```

### Thunderbird sends but cannot save to Sent

Check Dovecot/Maildir:

```bash
docker compose exec dovecot doveadm mailbox list -u user@alpha.example.com
docker compose logs --tail=100 dovecot
```

If you see `Permission denied`, confirm you are running a version that includes the Maildir ownership fix.

Expected commit:

```text
f595f3d fix: ensure Maildir subfolder ownership for Dovecot
```

### SES MAIL FROM fails during apply

Confirm you are running a version that includes the SES identity wait fix.

Expected commit:

```text
ee557b1 fix: wait for SES identity before custom MAIL FROM
```

## Related documents

```text
docs/operations.md
docs/backup-restore.md
docs/s3-lifecycle.md
docs/troubleshooting-iac.md
docs/validation-g26.md
docs/validation-g27.md
```
