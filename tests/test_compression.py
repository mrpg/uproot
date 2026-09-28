import gzip

import brotli
import pytest

import uproot.deployment as d
from uproot import server
from uproot.compression import compress, negotiate


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("gzip, deflate, br", "br"),
        ("gzip, deflate", "gzip"),
        ("br;q=0, gzip", "gzip"),
        ("BR;Q=0.5", "br"),
        ("br;q=0, gzip;q=0", None),
        ("identity", None),
    ],
)
def test_negotiate(header, expected):
    assert negotiate(header) == expected


def test_compress():
    data = b"compress me" * 100
    assert brotli.decompress(compress(data, "br")) == data
    assert gzip.decompress(compress(data, "gzip")) == data


@pytest.mark.parametrize("value", [0, 0.5, -1, 1e9, "30", float("nan")])
def test_invalid_keepalive_interval_is_rejected(monkeypatch, value):
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", value)

    with pytest.raises(SystemExit):
        server.validate_keepalive_interval()
