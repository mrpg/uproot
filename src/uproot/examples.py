# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later OR 0BSD OR MIT
# You may use this file (and ONLY this file) under any of the above licenses.
# The intention here is to liberate the example project and the example app.

import os
import shutil
import stat
import subprocess  # nosec B404  # git init command is safe
from datetime import date
from pathlib import Path

import uproot as u
from uproot.constraints import ensure

LICENSE_PATH = Path(__file__).parent / "_static" / "uproot_license.txt"

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
from uproot.rooms import room
from uproot.server import load_config, uproot_server

upd.project_metadata(created="#TODAY#", uproot="#VERSION#")

# Load your app configs here
# Examples are available at https://github.com/mrpg/uproot-examples

load_config(uproot_server, config="study01", apps=["#EXAMPLE#"])

# Create admin

upd.ADMINS["admin"] = ...  # Leave as-is to enable auto login

# Create room if it does not exist

upd.DEFAULT_ROOMS.append(
    room(
        "test",
        config="study01",
        open=True,
    )
)

# Other settings

upd.LANGUAGE = "en"

# Run uproot (leave this as-is)

if __name__ == "__main__":
    cli()
""".lstrip()

MINIMAL_INIT_PY = """
# Copyright (c) 2025 [Insert Your Name Here] - MIT License
#
# Third-party dependencies:
# - uproot: LGPL v3+, see ../uproot_license.txt
#
# Docs are available at https://uproot.science/
# Examples are available at https://github.com/mrpg/uproot-examples

from uproot.fields import *
from uproot.smithereens import *

DESCRIPTION = ""
LANDING_PAGE = False


class C:
    pass


class FirstPage(Page):
    pass


page_order = [
    FirstPage,
]
""".lstrip()

FIRSTPAGE_HTML = """
{% extends "Base.html" %}

{% block title %}
First page
{% endblock title %}


{% block main %}

<p>… or isn’t <i>more</i> more?</p>

{% endblock main %}
""".lstrip()

PD_INIT_PY = """
# Copyright (c) 2025 [Insert Your Name Here] - MIT License
#
# Third-party dependencies:
# - uproot: LGPL v3+, see ../uproot_license.txt
#
# Docs are available at https://uproot.science/
# Examples are available at https://github.com/mrpg/uproot-examples

from uproot.fields import *
from uproot.smithereens import *


DESCRIPTION = "Prisoner’s dilemma"
LANDING_PAGE = True


class C:
    pass


class GroupPlease(GroupCreatingWait):
    group_size = 2


class Dilemma(Page):
    fields = dict(
        cooperate=RadioField(
            label="Do you wish to cooperate?",
            choices=[(True, "Yes"), (False, "No")],
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
""".lstrip()

DILEMMA_HTML = """
{% extends "Base.html" %}

{% block title %}
Dilemma
{% endblock title %}


{% block main %}

{{ fields() }}

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

PROCFILE = "web: uproot run -h 0.0.0.0 -p $PORT\n"

PYTHON_VERSION = "3.13\n"

APP_JSON = """{
  "name": "Uproot Project",
  "description": "An uproot-based web application for behavioral science experiments",
  "keywords": ["python", "uproot", "experimental-economics", "behavioral-science"],
  "buildpacks": [
    {
      "url": "heroku/python"
    }
  ],
  "formation": {
    "web": {
      "quantity": 1,
      "size": "basic"
    }
  },
  "addons": [
    {
      "plan": "heroku-postgresql:essential-0"
    }
  ],
  "env": {
    "UPROOT_ORIGIN": {
      "description": "The public URL of your app (e.g., https://your-app-name.herokuapp.com). Auto-detected if you enable 'heroku labs:enable runtime-dyno-metadata'. Override for custom domains.",
      "required": false
    }
  }
}
""".lstrip()


def setup_empty_project(path: Path, minimal: bool) -> None:
    mainpath = path / "main.py"
    staticdir = path / "_static"

    with open(mainpath, "w", encoding="utf-8") as mf:
        template = (
            PROJECT_TEMPLATE.replace("#VERSION#", u.__version__)
            .replace("#TODAY#", date.today().strftime("%Y-%m-%d"))
            .replace("#EXAMPLE#", "my_app" if minimal else "prisoners_dilemma")
        )
        mf.write(template)

    try:
        os.chmod(mainpath, os.stat(mainpath).st_mode | stat.S_IEXEC)
    except Exception:  # nosec B110 - Best effort chmod, not critical if it fails
        pass

    staticdir.mkdir(exist_ok=False)

    with open(path / ".gitignore", "w", encoding="utf-8") as rf:
        rf.write(GITIGNORE)

    with open(path / "requirements.txt", "w", encoding="utf-8") as rf:
        rf.write(
            f"# For PostgreSQL support, instead use: uproot-science[pg]>={u.__version__}\n"
            f"uproot-science>={u.__version__}, <{u.__version_info__[0] + 1}.0.0\n"
        )

    shutil.copy(LICENSE_PATH, path / "uproot_license.txt")

    # Heroku deployment files
    with open(path / "Procfile", "w", encoding="utf-8") as pf:
        pf.write(PROCFILE)

    with open(path / ".python-version", "w", encoding="utf-8") as pv:
        pv.write(PYTHON_VERSION)

    with open(path / "app.json", "w", encoding="utf-8") as aj:
        aj.write(APP_JSON)

    # Initialize git repository if git is available
    if shutil.which("git") is not None:
        git_dir = path / ".git"
        if not git_dir.exists():
            try:
                subprocess.run(  # nosec B603 B607  # Hardcoded git command, no user input
                    ["git", "init"],
                    cwd=path,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError:
                pass  # Silently ignore if git init fails


def new_prisoners_dilemma(path: Path, app: str = "prisoners_dilemma") -> None:
    ensure(
        app.isidentifier(),  # KEEP AS IS
        ValueError,
        "Apps must have valid Python identifiers as names.",
    )
    appdir = path / app

    appdir.mkdir(exist_ok=False)
    (appdir / "_static").mkdir(exist_ok=False)

    with open(appdir / "__init__.py", "w", encoding="utf-8") as f1:
        f1.write(PD_INIT_PY)

    with open(appdir / "Dilemma.html", "w", encoding="utf-8") as f2:
        f2.write(DILEMMA_HTML)

    with open(appdir / "Results.html", "w", encoding="utf-8") as f3:
        f3.write(RESULTS_HTML)


def new_minimal_app(path: Path, app: str = "my_app") -> None:
    ensure(
        app.isidentifier(),  # KEEP AS IS
        ValueError,
        "Apps must have valid Python identifiers as names.",
    )
    appdir = path / app

    appdir.mkdir(exist_ok=False)
    (appdir / "_static").mkdir(exist_ok=False)

    with open(appdir / "__init__.py", "w", encoding="utf-8") as f1:
        f1.write(MINIMAL_INIT_PY)

    with open(appdir / "FirstPage.html", "w", encoding="utf-8") as f2:
        f2.write(FIRSTPAGE_HTML)
