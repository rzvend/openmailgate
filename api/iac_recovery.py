"""IaC recovery helpers — conflict detection and guided import/adopt."""

import os
import re
import subprocess


def _get_tofu_state_resources():
    """Return a set of resource addresses tracked in the current tofu state."""
    workdir = os.getenv("IAC_WORKDIR", "/app/iac")
    try:
        result = subprocess.run(
            ["tofu", "state", "list"],
            capture_output=True, text=True, timeout=30,
            cwd=workdir, shell=False,
        )
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        return set()


def _masked(value):
    """Short masked representation for safe display."""
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def detect_preapply_conflicts():
    """Return list of conflict dicts comparing expected resources against
    tofu state and remote AWS/Cloudflare existence.

    Each dict has keys:
      resource, provider, expected_name, status, message, in_state, remote_exists
    """
    from api.routes.dashboard import _iac_resource_names

    names = _iac_resource_names()
    state = _get_tofu_state_resources()
    region = os.getenv("AWS_REGION", "us-east-1")
    domain = os.getenv("DEFAULT_FROM_DOMAIN", "")
    cf_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    cf_zone = os.getenv("CLOUDFLARE_ZONE_ID", "")
    mail_prefix = domain.split(".")[0] if domain else ""

    conflicts = []

    def _in_state(addr):
        return addr in state

    # ── AWS checks ─────────────────────────────────────────────────────
    try:
        import boto3  # noqa: F811

        # S3 bucket
        bucket = names.get("mail_bucket_name", "")
        if bucket:
            in_st = _in_state("aws_s3_bucket.mail_bucket")
            remote = False
            try:
                s3 = boto3.client("s3", region_name=region)
                s3.head_bucket(Bucket=bucket)
                remote = True
            except Exception:
                pass
            status = _classify(in_st, remote)
            conflicts.append({
                "resource": "aws_s3_bucket.mail_bucket",
                "provider": "AWS",
                "expected_name": bucket,
                "status": status,
                "message": _status_message(status, "S3 bucket"),
                "in_state": in_st,
                "remote_exists": remote,
            })

        # SQS queue
        queue = names.get("sqs_queue_name", "")
        if queue:
            in_st = _in_state("aws_sqs_queue.mail_queue")
            remote = False
            try:
                sqs = boto3.client("sqs", region_name=region)
                sqs.get_queue_url(QueueName=queue)
                remote = True
            except Exception:
                pass
            status = _classify(in_st, remote)
            conflicts.append({
                "resource": "aws_sqs_queue.mail_queue",
                "provider": "AWS",
                "expected_name": queue,
                "status": status,
                "message": _status_message(status, "SQS queue"),
                "in_state": in_st,
                "remote_exists": remote,
            })

        # SES domain identity
        if domain:
            in_st = _in_state("aws_ses_domain_identity.domain")
            remote = False
            try:
                ses = boto3.client("ses", region_name=region)
                attrs = ses.get_identity_verification_attributes(Identities=[domain])
                if attrs.get("VerificationAttributes", {}).get(domain):
                    remote = True
            except Exception:
                pass
            status = _classify(in_st, remote)
            conflicts.append({
                "resource": "aws_ses_domain_identity.domain",
                "provider": "AWS",
                "expected_name": domain,
                "status": status,
                "message": _status_message(status, "SES domain identity"),
                "in_state": in_st,
                "remote_exists": remote,
            })

        # SES receipt rule set
        rule_set = names.get("rule_set_name", "")
        if rule_set:
            in_st = _in_state("aws_ses_receipt_rule_set.main")
            remote = False
            try:
                ses = boto3.client("ses", region_name=region)
                ses.describe_receipt_rule_set(RuleSetName=rule_set)
                remote = True
            except Exception:
                pass
            status = _classify(in_st, remote)
            conflicts.append({
                "resource": "aws_ses_receipt_rule_set.main",
                "provider": "AWS",
                "expected_name": rule_set,
                "status": status,
                "message": _status_message(status, "SES receipt rule set"),
                "in_state": in_st,
                "remote_exists": remote,
            })

        # IAM user SMTP
        smtp_user = names.get("smtp_iam_user", "")
        if smtp_user:
            in_st = _in_state("aws_iam_user.ses_smtp_sender")
            remote = False
            try:
                iam = boto3.client("iam", region_name="us-east-1")
                iam.get_user(UserName=smtp_user)
                remote = True
            except Exception:
                pass
            status = _classify(in_st, remote)
            conflicts.append({
                "resource": "aws_iam_user.ses_smtp_sender",
                "provider": "AWS",
                "expected_name": smtp_user,
                "status": status,
                "message": _status_message(status, "IAM user SMTP"),
                "in_state": in_st,
                "remote_exists": remote,
            })

    except Exception as e:
        conflicts.append({
            "resource": "aws_*",
            "provider": "AWS",
            "expected_name": "-",
            "status": "error",
            "message": f"AWS detection failed: {e}",
            "in_state": False,
            "remote_exists": False,
        })

    # ── Cloudflare DNS checks ─────────────────────────────────────────────
    if cf_token and cf_zone and mail_prefix:
        try:
            import httpx2 as httpx  # noqa: F811

            # MX record
            in_st = _in_state("cloudflare_dns_record.mx_inbox")
            remote = False
            cf_status = "missing"
            try:
                r = httpx.get(
                    f"https://api.cloudflare.com/client/v4/zones/{cf_zone}/dns_records"
                    f"?type=MX&name={domain}",
                    headers={"Authorization": f"Bearer {cf_token}"},
                    timeout=10,
                )
                if r.status_code == 200 and r.json().get("success"):
                    records = r.json().get("result", [])
                    if len(records) == 1:
                        remote = True
                        cf_status = "exists_outside_state" if not in_st else "ok"
                    elif len(records) > 1:
                        cf_status = "ambiguous"
            except Exception:
                cf_status = "error"
            if not in_st and not remote:
                cf_status = "missing"
            elif in_st and remote:
                cf_status = "ok"
            conflicts.append({
                "resource": "cloudflare_dns_record.mx_inbox",
                "provider": "Cloudflare",
                "expected_name": domain,
                "status": cf_status,
                "message": _cf_status_message(cf_status, "MX record"),
                "in_state": in_st,
                "remote_exists": remote,
            })

            # TXT SES verification
            in_st = _in_state("cloudflare_dns_record.ses_verification")
            remote = False
            cf_status = "missing"
            try:
                r = httpx.get(
                    f"https://api.cloudflare.com/client/v4/zones/{cf_zone}/dns_records"
                    f"?type=TXT&name=_amazonses.{domain}",
                    headers={"Authorization": f"Bearer {cf_token}"},
                    timeout=10,
                )
                if r.status_code == 200 and r.json().get("success"):
                    records = r.json().get("result", [])
                    if len(records) == 1:
                        remote = True
                        cf_status = "exists_outside_state" if not in_st else "ok"
                    elif len(records) > 1:
                        cf_status = "ambiguous"
            except Exception:
                cf_status = "error"
            if not in_st and not remote:
                cf_status = "missing"
            elif in_st and remote:
                cf_status = "ok"
            conflicts.append({
                "resource": "cloudflare_dns_record.ses_verification",
                "provider": "Cloudflare",
                "expected_name": f"_amazonses.{domain}",
                "status": cf_status,
                "message": _cf_status_message(cf_status, "SES verification TXT"),
                "in_state": in_st,
                "remote_exists": remote,
            })

            # DKIM CNAMEs
            in_st_0 = _in_state("cloudflare_dns_record.ses_dkim[0]")
            in_st_1 = _in_state("cloudflare_dns_record.ses_dkim[1]")
            in_st_2 = _in_state("cloudflare_dns_record.ses_dkim[2]")
            in_st_any = in_st_0 and in_st_1 and in_st_2
            remote = False
            cf_status = "missing"
            try:
                r = httpx.get(
                    f"https://api.cloudflare.com/client/v4/zones/{cf_zone}/dns_records"
                    "?type=CNAME&content=dkim.amazonses.com&per_page=10",
                    headers={"Authorization": f"Bearer {cf_token}"},
                    timeout=10,
                )
                if r.status_code == 200 and r.json().get("success"):
                    records = r.json().get("result", [])
                    if len(records) == 3:
                        remote = True
                        cf_status = "exists_outside_state" if not in_st_any else "ok"
                    elif len(records) > 3:
                        cf_status = "ambiguous"
            except Exception:
                cf_status = "error"
            if not in_st_any and not remote:
                cf_status = "missing"
            elif in_st_any and remote:
                cf_status = "ok"
            conflicts.append({
                "resource": "cloudflare_dns_record.ses_dkim[0..2]",
                "provider": "Cloudflare",
                "expected_name": f"*._domainkey.{domain}",
                "status": cf_status,
                "message": _cf_status_message(cf_status, "DKIM CNAME records"),
                "in_state": in_st_any,
                "remote_exists": remote,
            })

        except Exception as e:
            conflicts.append({
                "resource": "cloudflare_*",
                "provider": "Cloudflare",
                "expected_name": "-",
                "status": "error",
                "message": f"Cloudflare detection failed: {e}",
                "in_state": False,
                "remote_exists": False,
            })

    return conflicts


def _classify(in_state, remote_exists):
    """Return a status string based on state and remote existence."""
    if in_state and remote_exists:
        return "ok"
    if in_state and not remote_exists:
        return "missing"
    if not in_state and remote_exists:
        return "exists_outside_state"
    return "missing"


def _status_message(status, resource_label):
    """Return a human-readable message for a conflict status."""
    messages = {
        "ok": f"{resource_label} is tracked in state and exists remotely.",
        "missing": f"{resource_label} not found in state or remotely.",
        "exists_outside_state": f"{resource_label} exists remotely but is not tracked by OpenTofu state.",
        "ambiguous": f"Multiple matching {resource_label}s found — review manually.",
        "error": f"Could not check {resource_label} — AWS/API error.",
    }
    return messages.get(status, str(status))


def _cf_status_message(status, resource_label):
    """Return a human-readable message for Cloudflare DNS conflicts."""
    messages = {
        "ok": f"{resource_label} is tracked and exists.",
        "missing": f"{resource_label} not found in DNS or state.",
        "exists_outside_state": f"{resource_label} exists in Cloudflare DNS but is not tracked by OpenTofu state.",
        "ambiguous": f"Multiple matching {resource_label}s found in DNS — review manually before importing.",
        "error": f"Could not check {resource_label} — Cloudflare API error.",
    }
    return messages.get(status, str(status))
