"""IaC recovery helpers — conflict detection and guided import/adopt."""

import os
import re
import subprocess

from api.iac_config import is_placeholder, env_or_none, iac_mail_domain


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
    domain = iac_mail_domain()
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


# ── Guided import/adopt ───────────────────────────────────────────────────


def _discover_aws_import_id(resource_addr, region=None):
    """Return the tofu import ID for an AWS resource, or None if not discoverable."""
    from api.routes.dashboard import _iac_resource_names

    names = _iac_resource_names()
    region = region or os.getenv("AWS_REGION", "us-east-1")

    try:
        import boto3

        if resource_addr == "aws_s3_bucket.mail_bucket":
            return names.get("mail_bucket_name", "")

        if resource_addr == "aws_sqs_queue.mail_queue":
            sqs = boto3.client("sqs", region_name=region)
            queue_name = names.get("sqs_queue_name", "")
            if queue_name:
                resp = sqs.get_queue_url(QueueName=queue_name)
                return resp.get("QueueUrl", "")

        if resource_addr == "aws_ses_domain_identity.domain":
            return iac_mail_domain()

        if resource_addr == "aws_ses_receipt_rule_set.main":
            return names.get("rule_set_name", "")

        if resource_addr == "aws_iam_user.ses_smtp_sender":
            return names.get("smtp_iam_user", "")

    except Exception:
        pass
    return None


def _discover_cf_record_id(zone_id, token, record_type, name_filter):
    """Return the Cloudflare DNS record ID for type+name, or None."""
    try:
        import httpx2 as httpx
        r = httpx.get(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records"
            f"?type={record_type}&name={name_filter}&per_page=10",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if r.status_code == 200 and r.json().get("success"):
            records = r.json().get("result", [])
            if len(records) == 1:
                return records[0]["id"]
    except Exception:
        pass
    return None


def _get_dkim_tokens(domain, region):
    """Return the 3 DKIM tokens in Terraform order, or None."""
    # 1. Try tofu state (most accurate — same order as aws_ses_domain_dkim)
    workdir = os.getenv("IAC_WORKDIR", "/app/iac")
    try:
        result = subprocess.run(
            ["tofu", "state", "show", "aws_ses_domain_dkim.domain"],
            capture_output=True, text=True, timeout=30,
            cwd=workdir, shell=False,
        )
        if result.returncode == 0:
            tokens = re.findall(r'"([a-z0-9]{32})"', result.stdout)
            if len(tokens) == 3:
                return tokens
    except Exception:
        pass

    # 2. Fallback: AWS SES API (same order as aws_ses_domain_dkim)
    try:
        import boto3
        ses = boto3.client("ses", region_name=region)
        dkim = ses.get_identity_dkim_attributes(Identities=[domain])
        tokens = dkim.get("DkimAttributes", {}).get(domain, {}).get("DkimTokens", [])
        if len(tokens) == 3:
            return tokens
    except Exception:
        pass

    return None


def _discover_dkim_import_ids(domain, region):
    """Return list of (resource_addr, import_id) for all 3 DKIM records,
    or None if any token is ambiguous, missing, or lookups fail.
    """
    tokens = _get_dkim_tokens(domain, region)
    if not tokens or len(tokens) != 3:
        return None

    zone_id = os.getenv("CLOUDFLARE_ZONE_ID", "")
    cf_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    ids = []

    for i, token in enumerate(tokens):
        name = f"{token}._domainkey.{domain}"
        record_id = _discover_cf_record_id(zone_id, cf_token, "CNAME", name)
        if not record_id:
            return None
        ids.append((f"cloudflare_dns_record.ses_dkim[{i}]", record_id))

    return ids


def build_import_plan():
    """Return a list of (resource_addr, import_id, provider) tuples for
    resources that exist outside state and can be safely imported.
    """
    conflicts = detect_preapply_conflicts()
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID", "")
    cf_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    domain = iac_mail_domain()
    region = os.getenv("AWS_REGION", "us-east-1")

    plan = []
    skipped = []

    # DKIM — safe lookup with unambiguous matching
    dkim_ids = _discover_dkim_import_ids(domain, region)
    if dkim_ids is not None:
        for addr, record_id in dkim_ids:
            plan.append((addr, record_id, "Cloudflare"))
    else:
        skipped.append({
            "resource": "cloudflare_dns_record.ses_dkim[0..2]",
            "reason": "DKIM tokens ambiguous, incomplete, or missing — import manually.",
            "manual_required": True,
        })

    for c in conflicts:
        if c.get("status") != "exists_outside_state":
            continue

        addr = c.get("resource", "")
        provider = c.get("provider", "")

        # DKIM already handled above — skip here
        if "ses_dkim" in addr:
            continue

        import_id = None

        if provider == "AWS":
            import_id = _discover_aws_import_id(addr, region)
        elif provider == "Cloudflare":
            if addr == "cloudflare_dns_record.mx_inbox":
                import_id = _discover_cf_record_id(zone_id, cf_token, "MX", domain)
            elif addr == "cloudflare_dns_record.ses_verification":
                import_id = _discover_cf_record_id(zone_id, cf_token, "TXT", f"_amazonses.{domain}")

        if import_id:
            plan.append((addr, import_id, provider))
        else:
            skipped.append({
                "resource": addr,
                "reason": "Could not discover import ID.",
                "manual_required": True,
            })

    return plan, skipped


def adopt_existing_resources():
    """Run tofu import for each adoptable resource. Returns (results, skipped, errors)."""
    from api.routes.dashboard import _run_iac_command

    plan, skipped = build_import_plan()
    results = []
    errors = []
    workdir = os.getenv("IAC_WORKDIR", "/app/iac")
    env = os.environ.copy()

    for resource_addr, import_id, provider in plan:
        # Re-check: is resource already in state?
        state = _get_tofu_state_resources()
        if resource_addr in state:
            results.append({
                "resource": resource_addr,
                "provider": provider,
                "import_id": _masked(import_id),
                "success": True,
                "output": "Already in state — skipped.",
            })
            continue

        cmd_args = ["import", resource_addr, import_id]
        code, output = _run_iac_command("tofu", cmd_args, workdir, env, timeout=60)

        result = {
            "resource": resource_addr,
            "provider": provider,
            "import_id": _masked(import_id),
            "success": code == 0,
            "output": output[:1000],
        }
        results.append(result)

        if code != 0:
            errors.append(f"{resource_addr}: import failed (exit {code})")
            break  # Stop on first error

    return results, skipped, errors
