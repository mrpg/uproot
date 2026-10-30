import os
import re
import signal
import socket
import subprocess
import sys
import time

import httpx2
import orjson
import pytest

from uproot import examples


@pytest.fixture(
    params=[("run", signal.SIGINT), ("start", signal.SIGTERM)], ids=["run", "start"]
)
def running_server(tmp_path, request):
    examples.new_minimal_app(tmp_path)
    app = tmp_path / "my_app" / "__init__.py"
    app.write_text(
        app.read_text().replace(
            "class FirstPage(Page):\n    pass",
            """class FirstPage(Page):
    @live
    def increment(page, player):
        player.counter += 1
        send_to(player, {"counter": player.counter}, event="CounterUpdated")
        return player.counter
""",
        )
        + """

def new_player(player):
    player.counter = 0
""",
        encoding="utf-8",
    )
    (tmp_path / "main.py").write_text(
        examples.PROJECT_TEMPLATE.replace("#EXAMPLE#", "my_app") + """
import os
import threading
from pathlib import Path

upd.UPSTREAM = False
upd.API_KEYS.add("server-test")
upd.H2CORN_KWARGS["access_log"] = False
original_stop = upd.lifespan_stop


async def lifespan_start(app, tasks):
    app.state.start_thread = threading.get_ident()


async def lifespan_stop(app, tasks):
    await original_stop(app, tasks)
    Path("stopped").write_text(str(os.getpid()))


upd.lifespan_start = lifespan_start
upd.lifespan_stop = lifespan_stop


@uproot_server.get("/server-state/")
async def server_state():
    return {
        "pid": os.getpid(),
        "same_thread": threading.get_ident() == uproot_server.state.start_thread,
        "host": upd.HOST,
        "port": upd.PORT,
        "unsafe": upd.UNSAFE,
    }
""",
        encoding="utf-8",
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    command, shutdown_signal = request.param
    with (tmp_path / "server.log").open("w+") as log:
        started = False
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uproot.defaultcli",
                command,
                "--port",
                str(port),
                "--unsafe",
            ],
            cwd=tmp_path,
            env={
                **os.environ,
                "UPROOT_DATABASE": "sqlite3",
                "UPROOT_SQLITE3": str(tmp_path / "data.sqlite3"),
            },
            stdout=log,
            stderr=log,
        )
        try:
            with httpx2.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=1, trust_env=False
            ) as client:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        if client.get("/server-state/").status_code == 200:
                            started = True
                            yield client, process, command
                            return
                    except httpx2.TransportError:
                        pass
                    time.sleep(0.05)
                log.seek(0)
                pytest.fail(f"Server did not start:\n{log.read()}")
        finally:
            if process.poll() is None:
                process.send_signal(shutdown_signal)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                pytest.fail("Server did not shut down gracefully")
            if started:
                log.seek(0)
                assert process.returncode == 0, log.read()
                assert (tmp_path / "stopped").read_text() == str(process.pid)


def test_server_transports_and_single_process_lifecycle(running_server):
    client, process, command = running_server
    origin = str(client.base_url).rstrip("/")
    response = client.get("/server-state/")
    assert response.http_version == "HTTP/1.1"
    assert response.json() == {
        "pid": process.pid,
        "same_thread": True,
        "host": "127.0.0.1",
        "port": client.base_url.port,
        "unsafe": True,
    }
    assert client.get("/admin/dashboard/").status_code == 200
    assert client.get("/static/_uproot/favicon.ico").status_code == 200

    response = client.post(
        "/admin/api/v1/sessions/",
        headers={"Authorization": "Bearer server-test"},
        json={
            "config": "study01",
            "sname": "ws-test",
            "n_players": 1,
            "unames": ["alice"],
        },
    )
    assert response.status_code == 201
    response = client.get("/p/ws-test/alice/")
    assert response.status_code == 200
    page_vars = orjson.loads(re.search(r"uproot.vars = (.*?);", response.text)[1])[
        "_uproot_internal"
    ]
    response = client.post(
        "/p/ws-test/alice/",
        data={
            "_uproot_from": "-1",
            "_uproot_csrf": f"ws-test+alice+{page_vars['key']}",
        },
    )
    assert response.status_code == 200
    with client.websocket("/ws/ws-test/alice/", headers={"Origin": origin}) as ws:
        for future in range(1, 4):
            ws.send_json(
                {
                    "endpoint": "invoke",
                    "future": future,
                    "payload": {"mname": "increment", "args": [], "kwargs": {}},
                }
            )
            response_received = event_received = False
            while not (response_received and event_received):
                message = orjson.loads(ws.receive_bytes(timeout=3))
                if (
                    message["kind"] == "invoke"
                    and message["payload"]["future"] == future
                ):
                    assert message["payload"]["error"] is False
                    assert message["payload"]["data"] == future
                    response_received = True
                elif (
                    message["kind"] == "queue"
                    and message["payload"]["entry"]["event"] == "CounterUpdated"
                ):
                    assert message["payload"]["entry"]["data"] == {"counter": future}
                    event_received = True

    response = client.get(
        "/admin/api/v1/sessions/ws-test/players/alice/?fields=counter",
        headers={"Authorization": "Bearer server-test"},
    )
    assert response.json() == {"counter": 3}

    with client.websocket("/admin/ws/", headers={"Origin": origin}) as ws:
        ws.send_json({"endpoint": "hello", "future": 1})
        assert orjson.loads(ws.receive_bytes(timeout=3))["payload"]["future"] == 1

    with httpx2.Client(
        base_url=origin, http1=False, http2=True, timeout=3, trust_env=False
    ) as h2client:
        response = h2client.get("/server-state/")
        assert response.http_version == "HTTP/2"
        assert response.json()["pid"] == process.pid

    if command == "start":
        response = client.get(
            "/admin/api/v1/rooms/quick1/",
            headers={"Authorization": "Bearer server-test"},
        )
        assert response.status_code == 200
        assert response.json()["open"] is True
