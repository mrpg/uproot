import uproot.deployment as d
from uproot import server


def test_validate_admin_password_lengths_accepts_long_passwords(monkeypatch):
    monkeypatch.setattr(d, "ADMINS", {"alice": "secret", "admin": ...})
    server.validate_admin_password_lengths()


def test_validate_admin_password_lengths_rejects_short_passwords(monkeypatch):
    monkeypatch.setattr(d, "ADMINS", {"alice": "abc"})

    try:
        server.validate_admin_password_lengths()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("Expected SystemExit")
