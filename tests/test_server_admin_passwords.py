import uproot.deployment as d
import uproot.server as server
from uproot.types import sha256


def test_normalize_admin_passwords_hashes_plaintext_once(monkeypatch):
    monkeypatch.setattr(server, "ADMINS_PASSWORDS_HASHED", False)
    monkeypatch.setattr(d, "ADMINS", {"alice": "secret", "admin": ...})

    server.normalize_admin_passwords()

    assert d.ADMINS["alice"] == sha256("alice\nsecret")
    assert d.ADMINS["admin"] is ...


def test_normalize_admin_passwords_is_idempotent(monkeypatch):
    monkeypatch.setattr(server, "ADMINS_PASSWORDS_HASHED", False)
    monkeypatch.setattr(d, "ADMINS", {"alice": "secret"})

    server.normalize_admin_passwords()
    first_hash = d.ADMINS["alice"]

    server.normalize_admin_passwords()

    assert d.ADMINS["alice"] == first_hash
