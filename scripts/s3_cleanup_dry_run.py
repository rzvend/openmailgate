#!/usr/bin/env python3
"""S3 cleanup dry-run — list candidates without deleting anything.

Estimates how many objects in an S3 bucket prefix could be cleaned up
based on age.  Never calls delete_object / delete_objects.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import S3_BUCKET, S3_FAILED_PREFIX, S3_INCOMING_PREFIX, S3_PROCESSED_PREFIX  # noqa: E402


# ── pure helpers (testable without AWS) ──────────────────────────────────


def format_bytes(size):
    """Return a human-readable size string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.2f} {unit}"
        size /= 1024


def is_candidate(obj_last_modified, cutoff):
    """True if obj_last_modified is older than cutoff."""
    return obj_last_modified < cutoff


def warning_for_prefix(prefix):
    """Return a warning string for dangerous prefixes, or None."""
    in_prefix = S3_INCOMING_PREFIX.rstrip("/")
    fa_prefix = S3_FAILED_PREFIX.rstrip("/")
    pr_prefix = S3_PROCESSED_PREFIX.rstrip("/")
    clean = prefix.rstrip("/")
    if clean == in_prefix:
        return "WARNING: incoming/ may contain unprocessed messages. Do not delete blindly."
    if clean == fa_prefix:
        return "WARNING: failed/ may contain messages that need manual review."
    if clean == pr_prefix:
        return None  # safe default
    return None


def build_report(bucket, prefix, older_than_days, candidates, scanned, limit):
    """Return a list of report lines (no AWS calls)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    total_size = sum(c["Size"] for c in candidates)
    lines = []
    lines.append("S3 cleanup dry-run")
    lines.append(f"Bucket: {bucket}")
    lines.append(f"Prefix: {prefix}")
    lines.append(f"Older than days: {older_than_days}")
    lines.append(f"Cutoff: {cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append("")
    lines.append(f"Objects scanned: {scanned}")
    lines.append(f"Candidates: {len(candidates)}")
    lines.append(f"Total candidate size: {format_bytes(total_size)}")
    lines.append("")
    warning = warning_for_prefix(prefix)
    if warning:
        lines.append(warning)
        lines.append("")
    if candidates:
        lines.append("Sample candidates:")
        for c in candidates[:limit]:
            lines.append(
                f"- {c['Key']} | {c['LastModified'].strftime('%Y-%m-%dT%H:%M:%SZ')} | {format_bytes(c['Size'])}"
            )
        lines.append("")
    lines.append("No objects were deleted.")
    return lines


# ── main ─────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="S3 cleanup dry-run")
    parser.add_argument("--bucket", default=S3_BUCKET)
    parser.add_argument("--prefix", default=S3_PROCESSED_PREFIX)
    parser.add_argument("--older-than-days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than_days)

    try:
        import boto3
        s3 = boto3.client("s3")
    except Exception as e:
        print(f"ERROR: cannot create S3 client: {e}", file=sys.stderr)
        sys.exit(1)

    candidates = []
    scanned = 0

    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=args.bucket, Prefix=args.prefix):
            for obj in page.get("Contents", []):
                scanned += 1
                lm = obj.get("LastModified")
                if lm and is_candidate(lm, cutoff):
                    candidates.append(
                        {"Key": obj["Key"], "Size": obj.get("Size", 0), "LastModified": lm}
                    )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    for line in build_report(args.bucket, args.prefix, args.older_than_days,
                             candidates, scanned, args.limit):
        print(line)


if __name__ == "__main__":
    main()
