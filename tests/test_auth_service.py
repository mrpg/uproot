from time import monotonic
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
from uproot.services import auth


@pytest.fixture
def clean_auth(monkeypatch):
    d.DATABASE.reset()
    monkeypatch.setattr(u, "KEY", "test-auth-key")
    monkeypatch.setattr(d, "ADMINS", {"admin": ...}, raising=False)
    monkeypatch.setattr(auth, "ADMINS", {})
    monkeypatch.setattr(auth, "ADMINS_HASH", None)
    monkeypatch.setattr(auth, "ADMINS_SECRET_KEY", None)

    with s.Admin() as admin:
        c.create_admin(admin)

    yield


@pytest.fixture(autouse=True)
def clean_rate_limit():
    auth.FAILED_ATTEMPTS.clear()
    auth.BANNED_IPS.clear()
    auth.LAST_CLEANUP = 0.0
    yield
    auth.FAILED_ATTEMPTS.clear()
    auth.BANNED_IPS.clear()
    auth.LAST_CLEANUP = 0.0


def test_auth_token_lifecycle_requires_active_token(clean_auth):
    token = auth.create_auth_token_for_user("admin")
    assert token is not None

    assert auth.from_cookie(token) == {"user": "admin", "token": token}
    assert auth.verify_auth_token("admin", token) == "admin"

    assert auth.revoke_auth_token(token) is True
    assert auth.from_cookie(token) == {"user": "", "token": ""}
    assert auth.verify_auth_token("admin", token) is None


def test_auth_token_creation_rejects_unknown_user(clean_auth):
    assert auth.create_auth_token_for_user("missing") is None


def test_bearer_token_validation_uses_exact_bearer_scheme(monkeypatch):
    monkeypatch.setattr(d, "API_KEYS", ["secret"])

    assert auth.verify_bearer_token("Bearer secret") is True
    assert auth.verify_bearer_token("Bearer wrong") is False
    assert auth.verify_bearer_token("Basic secret") is False
    assert auth.verify_bearer_token(None) is False

    with pytest.raises(HTTPException) as excinfo:
        auth.require_bearer_token("Bearer wrong")

    assert excinfo.value.status_code == 401


def test_is_localhost():
    assert auth.is_localhost("127.0.0.1") is True
    assert auth.is_localhost("127.0.0.2") is True
    assert auth.is_localhost("127.255.255.255") is True
    assert auth.is_localhost("::1") is True
    assert auth.is_localhost("192.168.1.1") is False
    assert auth.is_localhost("10.0.0.1") is False
    assert auth.is_localhost("not-an-ip") is False


def test_get_client_ip_uses_resolved_request_client():
    request = SimpleNamespace(
        headers={"x-forwarded-for": "1.2.3.4"},
        client=SimpleNamespace(host="9.8.7.6"),
    )
    assert auth.get_client_ip(request) == "9.8.7.6"


def test_get_client_ip_normalizes_ip_address():
    request = SimpleNamespace(
        headers={},
        client=SimpleNamespace(host="2001:0db8:0000:0000:0000:0000:0000:0001"),
    )
    assert auth.get_client_ip(request) == "2001:db8::1"


def test_get_client_ip_falls_back_to_client_host():
    request = SimpleNamespace(
        headers={},
        client=SimpleNamespace(host="9.8.7.6"),
    )
    assert auth.get_client_ip(request) == "9.8.7.6"


def test_get_client_ip_no_client():
    request = SimpleNamespace(headers={}, client=None)
    assert auth.get_client_ip(request) == ""


def test_record_failed_login_bans_after_threshold():
    ip = "10.20.30.40"
    for attempted_ip in [ip] * (auth.MAX_FAILED_ATTEMPTS - 1):
        auth.record_failed_login(attempted_ip)
    assert auth.is_ip_banned(ip) is False

    auth.record_failed_login(ip)
    assert auth.is_ip_banned(ip) is True


def test_ban_expires(monkeypatch):
    ip = "10.20.30.40"
    for attempted_ip in [ip] * auth.MAX_FAILED_ATTEMPTS:
        auth.record_failed_login(attempted_ip)
    assert auth.is_ip_banned(ip) is True

    auth.BANNED_IPS[ip] = monotonic() - 1
    assert auth.is_ip_banned(ip) is False


def test_localhost_never_banned():
    for ip in ["127.0.0.1"] * (auth.MAX_FAILED_ATTEMPTS + 10):
        auth.record_failed_login(ip)
    assert auth.is_ip_banned("127.0.0.1") is False

    for ip in ["::1"] * (auth.MAX_FAILED_ATTEMPTS + 10):
        auth.record_failed_login(ip)
    assert auth.is_ip_banned("::1") is False


def test_empty_ip_never_banned():
    for ip in [""] * (auth.MAX_FAILED_ATTEMPTS + 10):
        auth.record_failed_login(ip)
    assert auth.is_ip_banned("") is False


def test_sweep_removes_stale_attempts():
    auth.FAILED_ATTEMPTS["1.1.1.1"] = [monotonic() - auth.ATTEMPT_WINDOW - 1]
    auth.FAILED_ATTEMPTS["2.2.2.2"] = [monotonic()]
    auth.LAST_CLEANUP = monotonic() - auth.CLEANUP_INTERVAL - 1
    auth.sweep_stale_entries()
    assert "1.1.1.1" not in auth.FAILED_ATTEMPTS
    assert "2.2.2.2" in auth.FAILED_ATTEMPTS


def test_sweep_removes_expired_bans():
    auth.BANNED_IPS["1.1.1.1"] = monotonic() - 1
    auth.BANNED_IPS["2.2.2.2"] = monotonic() + 9999
    auth.LAST_CLEANUP = monotonic() - auth.CLEANUP_INTERVAL - 1
    auth.sweep_stale_entries()
    assert "1.1.1.1" not in auth.BANNED_IPS
    assert "2.2.2.2" in auth.BANNED_IPS


def test_sweep_skipped_when_recent():
    auth.FAILED_ATTEMPTS["1.1.1.1"] = [monotonic() - auth.ATTEMPT_WINDOW - 1]
    auth.LAST_CLEANUP = monotonic()
    auth.sweep_stale_entries()
    assert "1.1.1.1" in auth.FAILED_ATTEMPTS


def test_max_tracked_ips_cap(monkeypatch):
    monkeypatch.setattr(auth, "MAX_TRACKED_IPS", 3)
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        auth.record_failed_login(ip)
    assert len(auth.FAILED_ATTEMPTS) == auth.MAX_TRACKED_IPS

    auth.record_failed_login("99.99.99.99")
    assert "99.99.99.99" not in auth.FAILED_ATTEMPTS


def test_existing_ip_still_tracked_beyond_cap(monkeypatch):
    monkeypatch.setattr(auth, "MAX_TRACKED_IPS", 3)
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        auth.record_failed_login(ip)

    auth.record_failed_login("10.0.0.1")
    assert "10.0.0.1" in auth.FAILED_ATTEMPTS
    assert len(auth.FAILED_ATTEMPTS["10.0.0.1"]) == 2


def test_banned_ips_count_toward_tracking_cap(monkeypatch):
    monkeypatch.setattr(auth, "MAX_FAILED_ATTEMPTS", 1)
    monkeypatch.setattr(auth, "MAX_TRACKED_IPS", 2)

    auth.record_failed_login("10.0.0.1")
    auth.record_failed_login("10.0.0.2")
    auth.record_failed_login("10.0.0.3")

    assert set(auth.BANNED_IPS) == {"10.0.0.1", "10.0.0.2"}
    assert "10.0.0.3" not in auth.FAILED_ATTEMPTS


def test_clear_failed_logins():
    ip = "10.20.30.40"
    auth.FAILED_ATTEMPTS[ip] = [monotonic()]
    auth.BANNED_IPS[ip] = monotonic() + auth.BAN_DURATION

    auth.clear_failed_logins(ip)

    assert ip not in auth.FAILED_ATTEMPTS
    assert ip not in auth.BANNED_IPS
