from decimal import Decimal

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t

d.DATABASE.reset()
u.CONFIGS["test"] = []
u.CONFIGS_PPATHS["test"] = []

with s.Admin() as admin:
    c.create_admin(admin)
    sid = c.create_session(admin, "test")

with sid() as session:
    pid = c.create_player(session)


def test_int():
    pid().x = -42

    with pid() as player:
        assert player.x == -42
        assert type(player.x) is int


def test_float():
    pid().f = 3.14159

    with pid() as player:
        assert player.f == 3.14159
        assert type(player.f) is float


def test_str():
    pid().s = "hello world"

    with pid() as player:
        assert player.s == "hello world"
        assert type(player.s) is str


def test_tuple():
    pid().t = (1, 2, "three", 4.0)

    with pid() as player:
        result = player.t

    assert result == (1, 2, "three", 4.0)
    assert type(result) is tuple
    assert type(result[0]) is int
    assert type(result[1]) is int
    assert type(result[2]) is str
    assert type(result[3]) is float


def test_bytes():
    pid().b = b"binary data"

    with pid() as player:
        assert player.b == b"binary data"
        assert type(player.b) is bytes


def test_bool():
    pid().bool_true = True
    pid().bool_false = False

    with pid() as player:
        assert player.bool_true is True
        assert player.bool_false is False
        assert type(player.bool_true) is bool
        assert type(player.bool_false) is bool


def test_complex():
    pid().c = 3 + 4j

    with pid() as player:
        assert player.c == 3 + 4j
        assert type(player.c) is complex


def test_none():
    pid().n = None

    with pid() as player:
        assert player.n is None
        assert type(player.n) is type(None)


def test_decimal():
    pid().d = Decimal("123.456789")

    with pid() as player:
        result = player.d

    assert result == Decimal("123.456789")
    assert type(result) is Decimal


def test_frozenset():
    pid().fs = frozenset([1, 2, 3, "a", "b"])

    with pid() as player:
        result = player.fs

    assert result == frozenset([1, 2, 3, "a", "b"])
    assert type(result) is frozenset
    # Check element types
    assert 1 in result and type(1) is int
    assert "a" in result and type("a") is str


def test_player_identifier():
    pid().pi = t.PlayerIdentifier("session1", "user1")

    with pid() as player:
        result = player.pi

    assert result == t.PlayerIdentifier("session1", "user1")
    assert type(result) is t.PlayerIdentifier
    assert result.sname == "session1"
    assert result.uname == "user1"


def test_session_identifier():
    pid().si = t.SessionIdentifier("session1")

    with pid() as player:
        result = player.si

    assert result == t.SessionIdentifier("session1")
    assert type(result) is t.SessionIdentifier
    assert result.sname == "session1"


def test_group_identifier():
    pid().gi = t.GroupIdentifier("session1", "group1")

    with pid() as player:
        result = player.gi

    assert result == t.GroupIdentifier("session1", "group1")
    assert type(result) is t.GroupIdentifier
    assert result.sname == "session1"
    assert result.gname == "group1"


def test_model_identifier():
    pid().mi = t.ModelIdentifier("session1", "model1")

    with pid() as player:
        result = player.mi

    assert result == t.ModelIdentifier("session1", "model1")
    assert type(result) is t.ModelIdentifier
    assert result.sname == "session1"
    assert result.mname == "model1"


def test_list():
    l = [1, 2.5, "three", [4, 5]]
    pid().l = l
    with pid() as player:
        result = player.l
        assert result == l
        assert type(result) is list
        assert type(result[0]) is int
        assert type(result[1]) is float
        assert type(result[2]) is str
        assert type(result[3]) is list
        assert type(result[3][0]) is int


def test_dict():
    d_ = dict(abc="abc", defg=4.1)
    pid().d = d_
    with pid() as player:
        result = player.d
        assert result == d_
        assert type(result) is dict
        assert type(result["abc"]) is str
        assert type(result["defg"]) is float


def test_bytearray():
    ba = bytearray(b"mutable bytes")
    pid().ba = ba
    with pid() as player:
        result = player.ba
        assert result == ba
        assert type(result) is bytearray


def test_set():
    s = {1, 2, 3, "a", "b"}
    pid().s = s
    with pid() as player:
        result = player.s
        assert result == s
        assert type(result) is set
        # Check element types preserved
        for elem in result:
            if elem in [1, 2, 3]:
                assert type(elem) is int
            else:
                assert type(elem) is str


def test_bunch():
    bunch = t.Bunch(
        [
            t.PlayerIdentifier("session1", "user1"),
            t.PlayerIdentifier("session1", "user2"),
            t.PlayerIdentifier("session2", "user3"),
        ]
    )
    pid().bunch = bunch
    with pid() as player:
        result = player.bunch
        assert list(result) == list(bunch)
        assert type(result) is list  # t.Bunch is a list
        # Check all elements are PlayerIdentifiers
        for elem in result:
            assert type(elem) is t.PlayerIdentifier
