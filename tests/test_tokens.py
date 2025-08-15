import uproot.types as t


def test_tokens_return():
    value = t.tokens([], 42)

    assert isinstance(value, list)
    assert len(value) == 42


def test_tokens_mostly_unique(outlen: int = 1_000):
    value = t.tokens([], outlen)

    assert len(value) == outlen
