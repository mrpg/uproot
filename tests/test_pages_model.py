"""Check uproot's page handler against its specification in uproot-proofs
(UprootProofs/Pages.lean).

Not run by default. Opt in with UPROOT_MODEL_TESTS=1, and set
UPROOT_PAGE_CASES to the cases that the model computes (in uproot-proofs:
lake exe page-cases > page-cases.jsonl), e.g.:

    UPROOT_DATABASE=sqlite3 UPROOT_SQLITE3=:memory: UPROOT_MODEL_TESTS=1 UPROOT_PAGE_CASES=page-cases.jsonl \\
        uv run pytest tests/test_pages_model.py

UPROOT_FORMAL_SHARD=k/n replays every n-th case starting with the k-th.

Each case is one request: a page order whose pages' hooks return fixed results
and record their calls, a player, and a request. The test replays it through
server1.show_page and compares what happens (hook calls, the start, saves, and
the page displayed, in order) and the player afterwards (position, started, the
hooks that ran where, and deadlines) with what the model computed.

A hook that moves the player uses move_to_page() or move_to_end() through
another Storage instance. Saved ordinary values, cleared optional fields,
and preservation of manual and unrelated fields are compared as well.
"""

import json
import os
import types
from typing import Any

import pytest
from starlette.datastructures import FormData

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t
from uproot import pages, server1
from uproot.fields import IntegerField, StringField
from uproot.pages import page2path
from uproot.smithereens import move_to_end, move_to_page

pytestmark = pytest.mark.skipif(
    not os.getenv("UPROOT_MODEL_TESTS"),
    reason="model tests are opt-in: set UPROOT_MODEL_TESTS=1",
)

SNAME = "modelsession"
LOG: list[list[Any]] = []
FORM_FIELDS = ("a", "s")


class GetRequest:
    method = "GET"
    app = None


class PostRequest:
    method = "POST"
    app = None

    def __init__(self, data: dict[str, str]) -> None:
        self.data = data

    async def form(self) -> FormData:
        return FormData(self.data)


def move(player: Any, target: int, classes: list[type[t.Page]]) -> None:
    """Move forward only, as move_to_page() and move_to_end() do (the model
    ignores other moves)."""
    with s.Player(*t.identify(player)) as other:
        if 0 <= other.show_page < target:
            if target == len(classes):
                move_to_end(other, reload_=False)
            else:
                move_to_page(other, classes[target], reload_=False)


def make_hook(position: int, hook: str, result: bool, mover: Any, classes: list) -> Any:
    def run(page: Any, player: Any, **kwargs: Any) -> Any:
        LOG.append(["call", position, hook, result])

        if mover is not None and mover[0] == hook:
            move(player, mover[1], classes)

        if hook in ("validate", "handle_stealth_fields"):
            return None if result else "Rejected"

        return result

    return run


def fields(page: Any, player: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"a": IntegerField(label="A", optional=True)}

    if page.stealth_fields:
        result["s"] = StringField(label="S")

    return result


def make_page(
    position: int, spec: dict[str, Any], classes: list, base: type = t.Page
) -> type[t.Page]:
    attrs: dict[str, Any] = {"__module__": __name__}

    for hook, result in spec["hooks"]:
        attrs[hook] = classmethod(
            make_hook(position, hook, result, spec["mover"], classes)
        )

    if spec["form"] is not None:
        attrs["fields"] = classmethod(fields)
        attrs["stealth_fields"] = ("s",) if spec["form"]["stealth"] else ()

    if spec["timeout"] is not None:
        attrs["timeout"] = spec["timeout"]

    if base is t.InternalPage:
        attrs |= {"show": True, "template": "End.html"}

    return type(f"P{position}", (base,), attrs)


def shown(formdata: Any, custom_errors: Any, field_errors: Any) -> str:
    if formdata is None:
        return "fresh"
    elif custom_errors or field_errors:
        return "errors"
    else:
        return "kept"


async def render_spy(
    app, request, player, page, formdata, custom_errors, metadata, uauth, field_errors
) -> str:
    LOG.append(
        ["display", player.show_page, shown(formdata, custom_errors, field_errors)]
    )

    return page.__name__


def events(position: int) -> list[list[Any]]:
    """LOG, with the writes of a form's fields merged into one save event."""
    result: list[list[Any]] = []

    for event in LOG:
        if event[0] == "field":
            if result and result[-1][0] == "save":
                result[-1][2].append(event[1])
            else:
                result.append(["save", position, [event[1]]])
        else:
            result.append(event)

    return result


def request_for(case: dict[str, Any]) -> Any:
    spec = case["request"]

    if spec["method"] == "GET":
        return GetRequest()

    return PostRequest({})


def form_data(case: dict[str, Any], player: Any) -> dict[str, str]:
    spec = case["request"]
    data: dict[str, str] = {}

    if spec["from"] is not None:
        data["_uproot_from"] = spec["from"]

    key = f"{player._uproot_session}+{player.name}+{player._uproot_key}"
    data["_uproot_csrf"] = key if spec["token"] else "bad"

    position = case["state"]["pos"]

    if 0 <= position < len(case["pages"]):
        form = case["pages"][position]["form"]

        if form is not None:
            if not form["valid"]:
                data["a"] = "x"
            elif spec["value"] is not None:
                data["a"] = str(spec["value"])

            if form["stealth"]:
                data["s"] = "ok"

    return data


def state(player: Any, npages: int) -> dict[str, Any]:
    ran = []

    for marker in player.get("_uproot_what_ran", frozenset()):
        position, hook = marker.split(":")
        ran.append([int(position), hook])

    deadlines = [
        [int(position), deadline]
        for position, deadline in player._uproot_timeouts_until.items()
    ]

    return {
        "pos": player.show_page,
        "started": player.started,
        "ran": sorted(ran),
        "deadlines": sorted(deadlines),
        "values": {name: player.get(name) for name in ("a", "s", "untouched")},
    }


def normalized(spec: dict[str, Any]) -> dict[str, Any]:
    return spec | {"ran": sorted(spec["ran"]), "deadlines": sorted(spec["deadlines"])}


async def replay(index: int, case: dict[str, Any], env: Any) -> tuple[Any, Any]:
    classes: list[type[t.Page]] = []
    classes.extend(make_page(i, spec, classes) for i, spec in enumerate(case["pages"]))
    n = len(classes)
    end = make_page(n, case["end"], classes, base=t.InternalPage)

    for cls in classes:
        u.PAGES[page2path(cls)] = cls

    u.PAGES["End.html"] = end
    env.barriers = {
        page2path(cls) for cls, spec in zip(classes, case["pages"]) if spec["barrier"]
    }
    env.now = case["now"]

    pid = t.PlayerIdentifier(SNAME, f"p{index}")
    c.initialize_player(pid, 0, "model")
    initial = case["state"]

    with s.Player(*pid) as player:
        player.page_order = [page2path(cls) for cls in classes]
        player.show_page = initial["pos"]
        player.started = initial["started"]
        player._uproot_what_ran = frozenset(f"{p}:{h}" for p, h in initial["ran"])
        player._uproot_timeouts_until = {
            str(p): float(deadline) for p, deadline in initial["deadlines"]
        }
        for name, value in initial["values"].items():
            setattr(player, name, value)
        request = request_for(case)

        if isinstance(request, PostRequest):
            request.data = form_data(case, player)

    env.player = pid
    LOG.clear()

    with s.Player(*pid) as player:
        await server1.show_page(request, player)

    with s.Player(*pid) as player:
        return events(initial["pos"]), state(player, n)


@pytest.fixture
def model_env(monkeypatch):
    env = types.SimpleNamespace(barriers=set(), now=0, player=None)
    on_change = d.STORE.on_change

    def record(namespace: tuple[str, ...], field: str, value: Any) -> None:
        if (
            env.player is not None
            and namespace == ("player", *env.player)
            and field in FORM_FIELDS
        ):
            LOG.append(["field", field])

        if on_change is not None:
            on_change(namespace, field, value)

    monkeypatch.setattr(u, "PAGES", dict(u.PAGES))
    monkeypatch.setattr(u, "APPS", {}, raising=False)
    monkeypatch.setattr(d, "TIMEOUT_TOLERANCE", 1.0)
    monkeypatch.setattr(d.STORE, "on_change", record)
    monkeypatch.setattr(server1, "render", render_spy)
    monkeypatch.setattr(server1, "initialize", lambda player: LOG.append(["init"]))
    monkeypatch.setattr(server1, "starts_segment", lambda path: path in env.barriers)
    monkeypatch.setattr(
        pages,
        "time",
        types.SimpleNamespace(time=lambda: float(env.now), time_ns=pages.time.time_ns),
    )
    monkeypatch.setattr(t, "time", lambda: float(env.now))

    return env


def cases(shard: int, nshards: int) -> list[tuple[int, dict[str, Any]]]:
    with open(os.environ["UPROOT_PAGE_CASES"], encoding="utf-8") as f:
        return [
            (index, json.loads(line))
            for index, line in enumerate(f)
            if index % nshards == shard
        ]


@pytest.mark.skipif(not os.getenv("UPROOT_PAGE_CASES"), reason="set UPROOT_PAGE_CASES")
async def test_page_cases(model_env):
    shard, nshards = (
        int(x) for x in os.getenv("UPROOT_FORMAL_SHARD", "0/1").split("/")
    )
    total, mismatches = 0, []

    for index, case in cases(shard, nshards):
        if total % 1000 == 0:
            d.DATABASE.reset()
            d.STORE.load()  # DATABASE.reset() clears the driver, not the cache

        log, after = await replay(index, case, model_env)
        total += 1

        if log != case["log"] or after != normalized(case["after"]):
            mismatches.append((index, case, log, after))

    assert total > 0
    assert not mismatches, f"{len(mismatches)}/{total} mismatches, e.g. " + "\n".join(
        json.dumps({"index": i, "case": case, "log": log, "after": after})
        for i, case, log, after in mismatches[:3]
    )
