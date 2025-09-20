from decimal import Decimal
from uuid import NAMESPACE_DNS, UUID, uuid1, uuid3, uuid4, uuid5

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


def test_uuid_v1():
    """Test UUID version 1 (MAC address and timestamp based)"""
    original_uuid = uuid1()
    pid().uuid_v1 = original_uuid

    with pid() as player:
        result = player.uuid_v1

    assert result == original_uuid
    assert type(result) is UUID
    assert result.version == 1
    assert result.variant == original_uuid.variant
    assert result.bytes == original_uuid.bytes
    assert str(result) == str(original_uuid)


def test_uuid_v3():
    """Test UUID version 3 (MD5 hash based)"""
    original_uuid = uuid3(NAMESPACE_DNS, "example.com")
    pid().uuid_v3 = original_uuid

    with pid() as player:
        result = player.uuid_v3

    assert result == original_uuid
    assert type(result) is UUID
    assert result.version == 3
    assert result.variant == original_uuid.variant
    assert result.bytes == original_uuid.bytes
    assert str(result) == str(original_uuid)


def test_uuid_v4():
    """Test UUID version 4 (random)"""
    original_uuid = uuid4()
    pid().uuid_v4 = original_uuid

    with pid() as player:
        result = player.uuid_v4

    assert result == original_uuid
    assert type(result) is UUID
    assert result.version == 4
    assert result.variant == original_uuid.variant
    assert result.bytes == original_uuid.bytes
    assert str(result) == str(original_uuid)


def test_uuid_v5():
    """Test UUID version 5 (SHA-1 hash based)"""
    original_uuid = uuid5(NAMESPACE_DNS, "example.com")
    pid().uuid_v5 = original_uuid

    with pid() as player:
        result = player.uuid_v5

    assert result == original_uuid
    assert type(result) is UUID
    assert result.version == 5
    assert result.variant == original_uuid.variant
    assert result.bytes == original_uuid.bytes
    assert str(result) == str(original_uuid)


def test_uuid_from_string():
    """Test UUID created from string"""
    uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    original_uuid = UUID(uuid_str)
    pid().uuid_from_str = original_uuid

    with pid() as player:
        result = player.uuid_from_str

    assert result == original_uuid
    assert type(result) is UUID
    assert result.variant == original_uuid.variant
    assert result.bytes == original_uuid.bytes
    assert str(result) == str(original_uuid)


def test_uuid_from_bytes():
    """Test UUID created from bytes"""
    uuid_bytes = b"\x55\x0e\x84\x00\xe2\x9b\x41\xd4\xa7\x16\x44\x66\x55\x44\x00\x00"
    original_uuid = UUID(bytes=uuid_bytes)
    pid().uuid_from_bytes = original_uuid

    with pid() as player:
        result = player.uuid_from_bytes

    assert result == original_uuid
    assert type(result) is UUID
    assert result.variant == original_uuid.variant
    assert result.bytes == original_uuid.bytes
    assert result.bytes == uuid_bytes
    assert str(result) == str(original_uuid)


def test_uuid_from_hex():
    """Test UUID created from hex"""
    uuid_hex = "550e8400e29b41d4a716446655440000"
    original_uuid = UUID(hex=uuid_hex)
    pid().uuid_from_hex = original_uuid

    with pid() as player:
        result = player.uuid_from_hex

    assert result == original_uuid
    assert type(result) is UUID
    assert result.variant == original_uuid.variant
    assert result.bytes == original_uuid.bytes
    assert str(result) == str(original_uuid)


def test_uuid_from_int():
    """Test UUID created from integer"""
    uuid_int = 113059749145936325711455712000
    original_uuid = UUID(int=uuid_int)
    pid().uuid_from_int = original_uuid

    with pid() as player:
        result = player.uuid_from_int

    assert result == original_uuid
    assert type(result) is UUID
    assert result.variant == original_uuid.variant
    assert result.bytes == original_uuid.bytes
    assert result.int == uuid_int
    assert str(result) == str(original_uuid)


def test_uuid_nil():
    """Test nil UUID (all zeros)"""
    original_uuid = UUID("00000000-0000-0000-0000-000000000000")
    pid().uuid_nil = original_uuid

    with pid() as player:
        result = player.uuid_nil

    assert result == original_uuid
    assert type(result) is UUID
    assert result.variant == original_uuid.variant
    assert result.bytes == original_uuid.bytes
    assert str(result) == str(original_uuid)


def test_uuid_variant_preservation():
    """Test that different UUID variants are preserved"""
    # Create UUIDs with different variants by manipulating bytes
    variants_to_test = [
        # Standard RFC 4122 variant
        UUID("550e8400-e29b-41d4-a716-446655440000"),  # variant 2 (10 binary)
        # Microsoft GUID variant (variant 1 - 0 binary)
        UUID(bytes=b"\x55\x0e\x84\x00\xe2\x9b\x41\xd4\x27\x16\x44\x66\x55\x44\x00\x00"),
        # Reserved variant (variant 3 - 11 binary)
        UUID(bytes=b"\x55\x0e\x84\x00\xe2\x9b\x41\xd4\xf7\x16\x44\x66\x55\x44\x00\x00"),
    ]

    for i, original_uuid in enumerate(variants_to_test):
        attr_name = f"uuid_variant_{i}"
        setattr(pid(), attr_name, original_uuid)

        with pid() as player:
            result = getattr(player, attr_name)

        assert result == original_uuid
        assert type(result) is UUID
        assert result.variant == original_uuid.variant
        assert result.bytes == original_uuid.bytes
        assert str(result) == str(original_uuid)
