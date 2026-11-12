import sys

import click
import pytest
from argon2 import PasswordHasher, Type

import uproot.deployment as d
from uproot import defaultcli, server
from uproot.passwords import DUMMY_HASH, Argon2id, hash_password
from uproot.services import auth

# Cheap parameters keep the tests fast and cover hashes made elsewhere
CHEAP = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)


def test_hash_password_round_trip():
    stored = hash_password("correct horse")

    assert stored.phc.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert stored.verify("correct horse")
    assert not stored.verify("correct horsf")
    assert not stored.verify("")
    assert not stored.verify("\ud800")


def test_argon2id_accepts_foreign_hashes():
    assert Argon2id(CHEAP.hash("secret")).verify("secret")


@pytest.mark.parametrize(
    "phc",
    [
        "",
        "secret",
        CHEAP.hash("secret").replace("$argon2id$", "$argon2i$"),
        PasswordHasher(type=Type.D).hash("secret"),
        CHEAP.hash("secret").replace("v=19", "v=16"),
        CHEAP.hash("secret").replace("m=8,", "m=7,"),
        CHEAP.hash("secret").replace("t=1,", "t=0,"),
        CHEAP.hash("secret").replace(",p=1$", ",p=0$"),
        CHEAP.hash("secret") + "!",
        CHEAP.hash("secret") + "\n",
        CHEAP.hash("secret") + "AA",  # 45 base64 characters cannot be decoded
        "$argon2id$v=19$m=8,t=1,p=1$c2FsdA$aGFzaGhhc2g",  # 4-byte salt
        # What a shell makes of an unquoted hash
        "=19=8,t=1,p=1$c2FsdHNhbHQ$aGFzaA",
    ],
)
def test_argon2id_rejects_invalid_hashes(phc):
    with pytest.raises(ValueError, match="single quotes"):
        Argon2id(phc)


@pytest.fixture
def admin_env(monkeypatch):
    monkeypatch.delenv("UPROOT_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("UPROOT_ADMIN_PASSWORD_ARGON2ID", raising=False)

    return monkeypatch


def test_auto_login_without_password(admin_env):
    assert d.auto_login() is ...

    admin_env.setenv("UPROOT_ADMIN_PASSWORD", "")
    admin_env.setenv("UPROOT_ADMIN_PASSWORD_ARGON2ID", "")
    assert d.auto_login() is ...


def test_auto_login_with_plaintext(admin_env):
    admin_env.setenv("UPROOT_ADMIN_PASSWORD", "$argon2id$ is just text here")
    admin_env.setenv("UPROOT_ADMIN_PASSWORD_ARGON2ID", "")

    assert d.auto_login() == "$argon2id$ is just text here"


def test_auto_login_with_hash(admin_env):
    phc = CHEAP.hash("secret")
    admin_env.setenv("UPROOT_ADMIN_PASSWORD", "")
    admin_env.setenv("UPROOT_ADMIN_PASSWORD_ARGON2ID", f"{phc}\n")

    assert d.auto_login() == Argon2id(phc)


def test_auto_login_rejects_both(admin_env):
    admin_env.setenv("UPROOT_ADMIN_PASSWORD", "secret")
    admin_env.setenv("UPROOT_ADMIN_PASSWORD_ARGON2ID", CHEAP.hash("secret"))

    with pytest.raises(SystemExit, match="not both"):
        d.auto_login()


def test_auto_login_rejects_invalid_hash(admin_env):
    admin_env.setenv("UPROOT_ADMIN_PASSWORD_ARGON2ID", "=19=8,t=1,p=1$x$y")

    with pytest.raises(SystemExit, match="Invalid UPROOT_ADMIN_PASSWORD_ARGON2ID"):
        d.auto_login()


@pytest.fixture
def configure_admins(monkeypatch):
    """Configure admins as main.py does, then let auth take them over."""
    monkeypatch.setattr(d, "ADMINS", {}, raising=False)
    monkeypatch.setattr(auth, "ADMINS", {})
    monkeypatch.setattr(auth, "ADMINS_HASH", None)
    monkeypatch.setattr(auth, "ADMINS_SECRET_KEY", None)

    def configure(admins):
        d.ADMINS = admins
        auth.ADMINS_HASH = None
        auth.ensure_globals()

    return configure


async def test_admin_credentials_valid(configure_admins):
    configure_admins(
        {"admin": ..., "alice": "plaintext", "bob": Argon2id(CHEAP.hash("hashed"))}
    )

    assert await auth.admin_credentials_valid("alice", "plaintext")
    assert await auth.admin_credentials_valid("bob", "hashed")
    assert not await auth.admin_credentials_valid("alice", "hashed")
    assert not await auth.admin_credentials_valid("bob", "plaintext")
    assert not await auth.admin_credentials_valid("bob", CHEAP.hash("hashed"))
    assert not await auth.admin_credentials_valid("admin", "")
    assert not await auth.admin_credentials_valid("carol", "plaintext")


async def test_login_attempts_cost_one_verification(configure_admins, monkeypatch):
    bob = Argon2id(CHEAP.hash("hashed"))
    configure_admins({"admin": ..., "alice": "plaintext", "bob": bob})
    verified = []
    verify = Argon2id.verify

    def spy(self, password):
        verified.append(self)
        return verify(self, password)

    monkeypatch.setattr(Argon2id, "verify", spy)

    for user in ("admin", "alice", "bob", "carol"):
        assert not await auth.admin_credentials_valid(user, "wrong")

    alice = auth.ADMINS["alice"]
    assert verified == [DUMMY_HASH, alice, bob, DUMMY_HASH]
    # The dummy costs as much as hashes from hash_password, such as alice's
    assert DUMMY_HASH.phc.split("$")[3] == alice.phc.split("$")[3]


def test_secret_key_survives_restarts(configure_admins):
    configure_admins({"alice": "plaintext"})
    key = auth.ADMINS_SECRET_KEY
    configure_admins({"alice": "plaintext"})

    assert auth.ADMINS_SECRET_KEY == key


def test_password_length_check_skips_hashes(monkeypatch):
    monkeypatch.setattr(d, "ADMINS", {"bob": Argon2id(CHEAP.hash("abc"))})

    server.validate_admin_password_lengths()


def test_hash_password_command(monkeypatch, capsys):
    answers = iter(["abc", "long enough"])
    monkeypatch.setattr(click, "prompt", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(sys, "argv", ["uproot", "hash-password"])

    defaultcli.main()

    captured = capsys.readouterr()
    assert "Use at least 5 characters." in captured.err

    line = next(
        line.strip()
        for line in captured.out.splitlines()
        if "UPROOT_ADMIN_PASSWORD_ARGON2ID='" in line
    )
    phc = line.removeprefix("UPROOT_ADMIN_PASSWORD_ARGON2ID='").removesuffix("'")
    assert Argon2id(phc).verify("long enough")
    assert f'upd.Argon2id("{phc}")' in captured.out
