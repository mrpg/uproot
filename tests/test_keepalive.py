import pytest

import uproot.deployment as d
import uproot.jobs as j
from uproot import server


@pytest.mark.parametrize("value", [0, 0.5, -1, 1e9, "30", float("nan")])
def test_invalid_keepalive_interval_is_rejected(monkeypatch, value):
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", value)

    with pytest.raises(SystemExit):
        server.validate_keepalive_interval()


def test_short_dropout_tolerance_is_clamped(monkeypatch):
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", 60.0)

    assert j.effective_tolerance(30.0) == 63.0
    assert j.effective_tolerance(120.0) == 120.0
