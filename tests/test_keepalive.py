import pytest

import uproot.deployment as d
from uproot import server


@pytest.mark.parametrize("value", [0, 0.5, -1, 1e9, "30", float("nan")])
def test_invalid_keepalive_interval_is_rejected(monkeypatch, value):
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", value)

    with pytest.raises(SystemExit):
        server.validate_keepalive_interval()
