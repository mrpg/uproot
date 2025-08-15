import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t

# s.CACHE_ENABLED = False


def setup():
    s.CACHE_ENABLED = True
    d.DATABASE.reset()
    u.CONFIGS["test"] = []
    u.CONFIGS_PPATHS["test"] = []

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test")

    with sid() as session:
        pid = c.create_player(session)

    return sid, pid


def test_storage_constructors():
    admin = s.Admin()
    assert admin.__path__ == "admin"
    assert admin.__trail__ == ("admin",)

    session = s.Session("test_session")
    assert session.__path__ == "session/test_session"
    assert session.__trail__ == ("session", "test_session")

    player = s.Player("test_session", "test_user")
    assert player.__path__ == "player/test_session/test_user"
    assert player.__trail__ == ("player", "test_session", "test_user")

    group = s.Group("test_session", "test_group")
    assert group.__path__ == "group/test_session/test_group"
    assert group.__trail__ == ("group", "test_session", "test_group")

    model = s.Model("test_session", "test_model")
    assert model.__path__ == "model/test_session/test_model"
    assert model.__trail__ == ("model", "test_session", "test_model")


def test_field_access():
    sid, pid = setup()

    # Set and get field
    pid().x = 42
    assert pid().x == 42

    # Field doesn't exist
    try:
        _ = pid().nonexistent
        assert False, "Should raise AttributeError"
    except AttributeError:
        pass


def test_field_deletion():
    sid, pid = setup()

    pid().to_delete = "value"
    assert pid().to_delete == "value"

    del pid().to_delete

    try:
        _ = pid().to_delete
        assert False, "Should raise AttributeError after deletion"
    except AttributeError:
        pass


def test_fields_method():
    sid, pid = setup()

    pid().field1 = 1
    pid().field2 = 2
    pid().field3 = 3

    fields = pid().__fields__()
    assert type(fields) is list
    assert "field1" in fields
    assert "field2" in fields
    assert "field3" in fields


def test_bool_method():
    sid, pid = setup()

    # Empty storage should be falsy
    empty_player = s.Player("test", "empty_user")
    assert not empty_player

    # Storage with fields should be truthy
    pid().some_field = "value"
    assert pid()


def test_context_manager():
    sid, pid = setup()

    # Immutable access without context manager
    pid().immutable = 42
    assert pid().immutable == 42

    # Mutable access requires context manager
    pid().mutable_list = [1, 2, 3]

    try:
        _ = pid().mutable_list
        assert False, "Should raise ValueError without context manager"
    except ValueError as e:
        assert "context manager" in str(e)

    # Access with context manager
    with pid() as player:
        assert player.mutable_list == [1, 2, 3]
        player.mutable_list.append(4)
        assert player.mutable_list == [1, 2, 3, 4]


def test_storage_equality():
    sid, pid = setup()

    # Same path should be equal
    player1 = s.Player("test", "user1")
    player2 = s.Player("test", "user1")
    assert player1 == player2

    # Different paths should not be equal
    player3 = s.Player("test", "user2")
    assert player1 != player3


def test_identifier_conversion():
    sid, pid = setup()

    # Test ~ operator
    session = s.Session("test")
    session_id = ~session
    assert type(session_id) is t.SessionIdentifier
    assert session_id.sname == "test"

    player = s.Player("test", "user")
    player_id = ~player
    assert type(player_id) is t.PlayerIdentifier
    assert player_id.sname == "test"
    assert player_id.uname == "user"


def test_history():
    sid, pid = setup()

    # Set field multiple times
    pid().counter = 1
    pid().counter = 2
    pid().counter = 3

    history = list(pid().__history__())
    assert len(history) >= 3

    # History should contain field names and values
    counter_history = [h for h in history if h[0] == "counter"]
    assert len(counter_history) >= 3


def test_within_basic():
    sid, pid = setup()

    # Set up data with different contexts
    pid().score = 10
    pid().level = 1

    # Access within specific context
    with pid() as player:
        within_ctx = player.within(score=10)
        assert within_ctx.score == 10
        assert within_ctx.level == 1


def test_within_nonexistent():
    sid, pid = setup()

    pid().x = 1

    with pid() as player:
        within_ctx = player.within(y=2)
        # Accessing non-existent field in context returns None
        assert within_ctx.x is None


def test_along_iteration():
    sid, pid = setup()

    # Create history for a field
    pid().state = "init"
    pid().state = "running"
    pid().state = "complete"

    with pid() as player:
        states = []
        contexts = []

        for value, ctx in player.along("state"):
            states.append(value)
            contexts.append(ctx)

        assert "init" in states
        assert "running" in states
        assert "complete" in states
        assert len(contexts) == len(states)


def test_flush_method():
    sid, pid = setup()

    with pid() as player:
        player.data = {"key": "value"}
        player.data["key"] = "modified"
        # Flush should persist changes
        player.flush()

    # Verify change persisted
    with pid() as player:
        assert player.data["key"] == "modified"


def test_mkpath_mktrail():
    # Test path construction
    path = s.mkpath("player", "session1", "user1")
    assert path == "player/session1/user1"

    # Test trail extraction
    trail = s.mktrail("player/session1/user1:field")
    assert trail == ("player", "session1", "user1", "field")


def test_field_from_paths():
    sid, pid = setup()

    # Create multiple players with same field
    pid().score = 100

    with sid() as session:
        pid2 = c.create_player(session)
        pid2().score = 200

    paths = [pid().__path__, pid2().__path__]
    scores = s.field_from_paths(paths, "score")

    assert type(scores) is dict
    assert len(scores) == 2
    assert 100 in [v.data for v in scores.values()]
    assert 200 in [v.data for v in scores.values()]


def test_storage_repr():
    admin = s.Admin()
    assert repr(admin) == "Admin()"

    session = s.Session("test")
    assert repr(session) == "Session(*('test',))"

    player = s.Player("test", "user")
    assert repr(player) == "Player(*('test', 'user'))"
