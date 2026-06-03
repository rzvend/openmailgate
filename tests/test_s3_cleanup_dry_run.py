"""Tests for S3 cleanup dry-run — pure functions only, no AWS calls."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.s3_cleanup_dry_run import (
    build_report,
    format_bytes,
    is_candidate,
    warning_for_prefix,
)


def test_format_bytes():
    assert format_bytes(0) == "0.00 B"
    assert format_bytes(500) == "500.00 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1536) == "1.50 KB"
    assert format_bytes(1048576) == "1.00 MB"


def test_is_candidate():
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=60)
    recent = now - timedelta(days=5)
    cutoff = now - timedelta(days=30)
    assert is_candidate(old, cutoff) is True
    assert is_candidate(recent, cutoff) is False


def test_build_report():
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = [{"Key": "processed/old.eml", "Size": 5000, "LastModified": old}]
    lines = build_report("test-bucket", "processed/", 30, candidates, 100, 10)
    report = "\n".join(lines)
    assert "No objects were deleted." in lines[-1]
    assert "test-bucket" in report
    assert "processed/old.eml" in report
    assert "5000" in report or "4.88 KB" in report


def test_warns_for_incoming_prefix():
    assert warning_for_prefix("incoming/") is not None
    assert "unprocessed" in warning_for_prefix("incoming/").lower()


def test_warns_for_failed_prefix():
    assert warning_for_prefix("failed/") is not None
    assert "manual review" in warning_for_prefix("failed/").lower()


def test_no_warning_for_processed():
    assert warning_for_prefix("processed/") is None


def test_dry_run_report_never_mentions_delete():
    """Build report must not suggest destructive operations."""
    lines = build_report("b", "processed/", 30, [], 0, 10)
    report = " ".join(lines)
    # The words "No objects were deleted" is OK (affirmative).
    # "delete_object" / "delete_objects" / "Delete" as command must NOT appear.
    assert "delete_object" not in report.lower()
    assert "delete_objects" not in report.lower()

