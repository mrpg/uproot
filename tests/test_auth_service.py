import hashlib

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
    auth.POW_USED.clear()

    with s.Admin() as admin:
        c.create_admin(admin)

    yield

    auth.POW_USED.clear()


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


def test_pow_challenge_is_single_use(clean_auth, monkeypatch):
    monkeypatch.setattr(auth, "POW_DIFFICULTY", "0")
    challenge, difficulty = auth.make_pow_challenge()

    solution = 0
    while True:
        digest = hashlib.sha256(f"{challenge}:admin:{solution}".encode()).hexdigest()
        if digest.endswith(difficulty):
            break
        solution += 1

    assert auth.verify_pow(challenge, str(solution), "admin") is True
    assert auth.verify_pow(challenge, str(solution), "admin") is False
