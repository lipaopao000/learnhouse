"""Regression coverage for opt-in email verification on the self-hosted site."""
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.events.database import get_db_session
from src.db.users import AnonymousUser, User, UserCreate
from src.routers.auth import router
from src.services.users.users import create_user, create_user_without_org


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("LEARNHOUSE_REQUIRE_EMAIL_VERIFICATION", "true")
    monkeypatch.setenv("LEARNHOUSE_EMAIL_VERIFICATION_REQUIRED_SINCE", "2026-11-05T00:00:00+00:00")


@pytest.mark.parametrize("with_org", [True, False])
async def test_selfhost_signup_waits_for_verification(enabled, mock_request, db, org, with_org):
    user = UserCreate(username="verify-new", email="verify-new@test.com", password="ValidPassword123!")
    with ExitStack() as stack:
        for name in ["rbac_check", "track", "dispatch_webhooks"]:
            stack.enter_context(patch("src.services.users.users." + name, new_callable=AsyncMock))
        for name in ["check_limits_with_usage", "increase_feature_usage"]:
            stack.enter_context(patch("src.services.users.users." + name))
        stack.enter_context(patch("src.services.users.users.get_deployment_mode", return_value="oss"))
        send = stack.enter_context(patch("src.services.users.email_verification.send_verification_email", new_callable=AsyncMock))
        welcome = stack.enter_context(patch("src.services.users.users.send_account_creation_email"))
        if with_org:
            result = await create_user(mock_request, db, AnonymousUser(), user, org.id)
        else:
            result = await create_user_without_org(mock_request, db, AnonymousUser(), user)
    assert result.email_verified is False
    send.assert_awaited_once()
    welcome.assert_not_called()


@pytest.mark.parametrize("created,verified,expected", [
    ("2026-11-05 01:00:00", False, 403),
    ("2026-11-05 01:00:00", True, 200),
    ("2026-11-04 10:00:00", False, 200),
])
async def test_password_login_requires_new_accounts_to_verify(enabled, db, created, verified, expected):
    user = SimpleNamespace(id=11, email="verify@test.com", email_verified=verified, creation_date=created)
    app = FastAPI()
    app.include_router(router, prefix="/auth")
    app.dependency_overrides[get_db_session] = lambda: db
    with ExitStack() as stack:
        stack.enter_context(patch("src.routers.auth.check_login_rate_limit", return_value=(True, None)))
        stack.enter_context(patch("src.routers.auth.check_account_locked", return_value=(False, None)))
        stack.enter_context(patch("src.routers.auth.authenticate_user", new_callable=AsyncMock, return_value=user))
        stack.enter_context(patch("src.routers.auth.get_deployment_mode", return_value="oss"))
        # Stop at the verified gate's successor: no fake cookies or tokens are
        # accepted as evidence that the account passed the gate.
        from fastapi import HTTPException
        stack.enter_context(patch("src.services.orgs.auth_policy.enforce_login_auth_method", new_callable=AsyncMock))
        next_step = stack.enter_context(patch("src.routers.auth._bind_session_to_custom_domain", new_callable=AsyncMock, side_effect=HTTPException(status_code=200, detail="verification gate passed")))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/auth/login", data={"username": user.email, "password": "ValidPassword123!"})
    assert response.status_code == expected
    if expected == 403:
        assert response.json()["detail"]["code"] == "EMAIL_NOT_VERIFIED"
        next_step.assert_not_awaited()
    else:
        next_step.assert_awaited_once()


@pytest.mark.parametrize("mode,flag,created,expected", [
    ("oss", "", "2026-11-05 01:00:00", False),
    ("ee", "false", "2026-11-05 01:00:00", False),
    ("saas", "", "2026-11-04 10:00:00", True),
    ("oss", "true", "2026-11-04 10:00:00", False),
    ("oss", "true", "2026-11-05 00:00:00", True),
    ("oss", "true", "2026-11-05T08:00:00+08:00", True),
    ("oss", "true", "malformed", True),
])
def test_policy_cutoff_and_modes(monkeypatch, mode, flag, created, expected):
    from src.core.email_verification_policy import requires_email_verification
    monkeypatch.setenv("LEARNHOUSE_REQUIRE_EMAIL_VERIFICATION", flag)
    monkeypatch.setenv("LEARNHOUSE_EMAIL_VERIFICATION_REQUIRED_SINCE", "2026-11-05T00:00:00+00:00")
    assert requires_email_verification(mode, user=SimpleNamespace(creation_date=created)) is expected


def test_new_signup_and_invalid_cutoff_require_verification(enabled, monkeypatch):
    from src.core.email_verification_policy import requires_email_verification
    assert requires_email_verification("oss") is True
    monkeypatch.setenv("LEARNHOUSE_EMAIL_VERIFICATION_REQUIRED_SINCE", "invalid")
    assert requires_email_verification("oss", user=SimpleNamespace(creation_date="2026-11-04 10:00:00")) is True


async def test_unverified_new_user_cannot_request_magic_login(enabled, db):
    user = User(username="verify-magic", first_name="Verify", last_name="Test", email="verify-magic@test.com", password="hashed", user_uuid="user_verify_magic", email_verified=False, creation_date="2026-11-05 01:00:00", update_date="2026-11-05 01:00:00")
    db.add(user)
    await db.commit()
    app = FastAPI()
    app.include_router(router, prefix="/auth")
    app.dependency_overrides[get_db_session] = lambda: db
    with patch("src.routers.auth.check_login_rate_limit", return_value=(True, None)), patch("src.routers.auth.check_rate_limit", return_value=(True, 0, 0)), patch("src.routers.auth.get_deployment_mode", return_value="oss"), patch("src.services.auth.magic_login.send_magic_login_email") as send:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/auth/magic-link/request", json={"email": user.email})
    assert response.status_code == 200
    send.assert_not_called()
