# S3 Lifecycle and Cleanup

## Prefixes

| Prefix | Purpose |
|---|---|
| `incoming/` | New emails from SES Receiving (processed by worker) |
| `processed/` | Successfully processed emails |
| `failed/` | Emails that encountered errors during processing |

## Recommended Retention

- `processed/` can usually be expired after 30-90 days.
- `failed/` should be retained longer — it may contain messages that need manual review.
- `incoming/` should not be deleted automatically unless you fully understand the processing flow.

## Dry-run

Estimate what would be cleaned without deleting anything:

```bash
python3 scripts/s3_cleanup_dry_run.py --prefix processed/ --older-than-days 30 --limit 20
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--bucket` | From `.env` (`S3_BUCKET`) | S3 bucket name |
| `--prefix` | `processed/` | Object key prefix |
| `--older-than-days` | `30` | Minimum age in days |
| `--limit` | `20` | Sample candidates to show |

This command does **not** delete objects.

## AWS Lifecycle Policy

A lifecycle rule can be configured in the AWS Console or Terraform to automatically expire old `processed/` objects:

```json
{
  "Rules": [{
    "Id": "expire-processed",
    "Status": "Enabled",
    "Filter": {"Prefix": "processed/"},
    "Expiration": {"Days": 30}
  }]
}
```

## Safety Notes

- Do not delete objects without confirming they were processed.
- `failed/` objects may represent undelivered email — review before deleting.
- Never store AWS credentials in the repository.
- Never commit `.env` or Terraform state.
