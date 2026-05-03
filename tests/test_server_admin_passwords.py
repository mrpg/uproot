import uproot.deployment as d
import uproot.server as server
from uproot.services.auth import PASSWORD_HASH_SCHEME, verify_admin_password


def test_normalize_admin_passwords_hashes_plaintext_once(monkeypatch):
    monkeypatch.setattr(server, "ADMINS_PASSWORDS_HASHED", False)
    monkeypatch.setattr(d, "ADMINS", {"alice": "secret", "admin": ...})

    server.normalize_admin_passwords()

    assert isinstance(d.ADMINS["alice"], str)
    assert d.ADMINS["alice"].startswith(f"{PASSWORD_HASH_SCHEME}$")
    assert verify_admin_password("alice", "secret", d.ADMINS["alice"])
    assert not verify_admin_password("alice", "wrong", d.ADMINS["alice"])
    assert d.ADMINS["admin"] is ...


def test_normalize_admin_passwords_is_idempotent(monkeypatch):
    monkeypatch.setattr(server, "ADMINS_PASSWORDS_HASHED", False)
    monkeypatch.setattr(d, "ADMINS", {"alice": "secret"})

    server.normalize_admin_passwords()
    first_hash = d.ADMINS["alice"]

    server.normalize_admin_passwords()

    assert d.ADMINS["alice"] == first_hash
