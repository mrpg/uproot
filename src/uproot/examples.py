# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later OR 0BSD OR MIT
# You may use this file (and ONLY this file) under any of the above licenses.
# The intention here is to liberate the example project and the example app.

import os
import shutil
import stat
from datetime import date
from pathlib import Path

import uproot as u
import uproot.types as t
from uproot.constraints import ensure

LICENSE_PATH = Path(__file__).parent / "static" / "uproot_license.txt"

GITIGNORE = """
build/
.coverage
.coverage.*
dist/
**/.DS_Store
dump.rdb
*.egg-info/
.env
env/
.env.local
htmlcov/
.hypothesis/
.idea/
.ipynb_checkpoints/
*.log
.mypy_cache
.mypy_cache/
*.mdb
*.orig
*.pyc
__pycache__
__pycache__/
*.pyo
.pytest_cache/
.python-version
.ropeproject/
*.sqlite3*
*.swo
*.swp
Thumbs.db
.tox/
.venv/
venv/
.vscode
.vscode/
*.whl
""".lstrip()

PROJECT_TEMPLATE = """
#!/usr/bin/env python
# Third-party dependencies:
# - uproot: LGPL v3+, see ./uproot_license.txt
import uproot.deployment as upd
from uproot.cli import cli
from uproot.server import load_config, uproot_server
from uproot.rooms import room

upd.project_metadata(created="#TODAY#", uproot="#VERSION#")

# Load your app configs here
# Examples are available at https://github.com/mrpg/uproot-examples

load_config(uproot_server, config="my_config", apps=["prisoners_dilemma"])

# Create admin

upd.ADMINS["admin"] = "#PASSWORD#"  # Example password

# Create room if it does not exist

upd.DEFAULT_ROOMS.append(
    room(
        "test",
        config="my_config",
        start=True,
    )
)

# Set default language

upd.LANGUAGE = "en"  # Available languages: "de", "en", "es"

# Run uproot (leave this as-is)

if __name__ == "__main__":
    upd.SALT = "#SALT#"
    cli()
""".lstrip()

APP_TEMPLATE = '''
"""
Copyright (c) 2025 [Insert Your Name Here] - MIT License

Third-party dependencies:
- uproot: LGPL v3+, see ../uproot_license.txt

Docs are available at https://uproot.science/
Examples are available at https://github.com/mrpg/uproot-examples
"""

from uproot.fields import *
from uproot.smithereens import *


DESCRIPTION = "Prisoner’s dilemma"


class Constants:
    pass


class GroupPlease(GroupCreatingWait):
    group_size = 2


class Dilemma(Page):
    fields = dict(
        cooperate=BooleanField(
            label="Do you wish to cooperate?",
        ),
    )


def set_payoff(player):
    other = other_in_group(player)

    match player.cooperate, other.cooperate:
        case True, True:
            player.payoff = 10
        case True, False:
            player.payoff = 0
        case False, True:
            player.payoff = 15
        case False, False:
            player.payoff = 3


class Sync(SynchronizingWait):
    @classmethod
    def all_here(page, group):
        for player in players(group):
            set_payoff(player)


class Results(Page):
    @classmethod
    def context(page, player):
        return dict(
            other=other_in_group(player),
        )


page_order = [
    GroupPlease,
    Dilemma,
    Sync,
    Results,
]
'''.lstrip()

DILEMMA_HTML = """
{% extends "Base.html" %}

{% block title %}
Dilemma
{% endblock title %}


{% block main %}

{{ uproot.field(form.cooperate) }}

{% endblock main %}
""".lstrip()

RESULTS_HTML = """
{% extends "Base.html" %}

{% block title %}
Results
{% endblock title %}


{% block main %}

{% if player.cooperate %}
<p>You cooperated.</p>
{% else %}
<p>You did not cooperate.</p>
{% endif %}

{% if other.cooperate %}
<p>Your partner cooperated.</p>
{% else %}
<p>Your partner did not cooperate.</p>
{% endif %}

<p>Your payoff is <b>{{ player.payoff }}</b>.</p>

{% endblock main %}
""".lstrip()


def setup_mere_project(path: Path) -> None:
    mainpath = path / "main.py"

    with open(mainpath, "w", encoding="utf-8") as mf:
        template = (
            PROJECT_TEMPLATE.replace("#PASSWORD#", t.token_unchecked(18))
            .replace("#SALT#", t.token_unchecked(18))
            .replace("#VERSION#", u.__version__)
            .replace("#TODAY#", date.today().strftime("%Y-%m-%d"))
        )
        mf.write(template)

    try:
        os.chmod(mainpath, os.stat(mainpath).st_mode | stat.S_IEXEC)
    except Exception:
        pass

    with open(path / ".gitignore", "w", encoding="utf-8") as rf:
        rf.write(GITIGNORE)

    with open(path / "requirements.txt", "w", encoding="utf-8") as rf:
        rf.write(f"uproot-science=={u.__version__}\n")

    shutil.copy(LICENSE_PATH, path / "uproot_license.txt")


def setup_mere_app(path: Path, app: str = "prisoners_dilemma") -> None:
    ensure(
        app.isidentifier(),
        ValueError,
        "Apps must have valid Python identifiers as names.",
    )
    appdir = path / app

    appdir.mkdir(exist_ok=False)
    (appdir / "static").mkdir(exist_ok=False)

    with open(appdir / "__init__.py", "w", encoding="utf-8") as f1:
        f1.write(APP_TEMPLATE)

    with open(appdir / "Dilemma.html", "w", encoding="utf-8") as f2:
        f2.write(DILEMMA_HTML)

    with open(appdir / "Results.html", "w", encoding="utf-8") as f3:
        f3.write(RESULTS_HTML)
