"""Opt-in email verification for self-hosted deployments.

The deployment mode remains unchanged. An optional UTC cutoff preserves
existing accounts when verification is enabled on an established instance.
"""
import os
from src.security.account_identity import trusted_unbound
from datetime import datetime, timezone


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def requires_email_verification(deployment_mode: str, *, user=None) -> bool:
    if deployment_mode == "saas":
        return True
    if trusted_unbound(user):
        return False
    if os.environ.get("LEARNHOUSE_REQUIRE_EMAIL_VERIFICATION", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    since = os.environ.get("LEARNHOUSE_EMAIL_VERIFICATION_REQUIRED_SINCE", "").strip()
    if user is None or not since:
        return True
    try:
        return _utc(user.creation_date) >= _utc(since)
    except (AttributeError, TypeError, ValueError):
        # A malformed timestamp must not silently exempt a new account.
        return True
