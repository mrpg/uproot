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

LICENSE_0BSD = """\
Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
"""

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

README = """\
# uproot project

This directory contains an [uproot](https://uproot.science/) project for browser-based behavioral experiments.

## Run locally

```bash
uv run uproot run  # or just "uproot run"
```

Then follow the instructions from the console.

## Documentation

See [https://uproot.science/](https://uproot.science/) to peruse the *uproot* documentation.
""".lstrip()

PROJECT_TEMPLATE = """
#!/usr/bin/env python
# SPDX-License-Identifier: 0BSD
#
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
# SPDX-License-Identifier: 0BSD
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
# SPDX-License-Identifier: 0BSD
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

PAGE_TEMPLATE_HTML = """
{% extends "Base.html" %}

{% block title %}
#PAGENAME#
{% endblock title %}


{% block main %}

{{ fields() }}

{% endblock main %}
""".lstrip()

PAGE_TEMPLATE_PY = """

class #PAGENAME#(Page):
    fields = dict(
        # Add your fields here
    )
"""

PROCFILE = "web: uproot run -h 0.0.0.0 -p $PORT\n"

PYTHON_VERSION = "3.13\n"

PYPROJECT_TOML = """\
[project]
name = "uproot-project"
version = "0.1.0"
description = "An uproot-based web application for behavioral science experiments"
readme = "README.md"
license = "0BSD"
requires-python = ">=3.13"
dependencies = [
    "uproot-science @ git+https://github.com/mrpg/uproot.git@main",
]

[project.optional-dependencies]
pg = [
    "uproot-science[pg] @ git+https://github.com/mrpg/uproot.git@main",
]
"""


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

    with open(path / "README.md", "w", encoding="utf-8") as rf:
        rf.write(README)

    with open(path / "pyproject.toml", "w", encoding="utf-8") as pf:
        pf.write(PYPROJECT_TOML)

    shutil.copy(LICENSE_PATH, path / "uproot_license.txt")

    with open(path / "LICENSE", "w", encoding="utf-8") as lf:
        lf.write(LICENSE_0BSD)

    # Deployment files
    with open(path / "Procfile", "w", encoding="utf-8") as pf:
        pf.write(PROCFILE)

    with open(path / ".python-version", "w", encoding="utf-8") as pv:
        pv.write(PYTHON_VERSION)

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


def new_page(path: Path, app: str, page: str) -> None:
    ensure(
        page.isidentifier(),  # KEEP AS IS
        ValueError,
        "Pages must have valid Python identifiers as names.",
    )
    appdir = path / app

    ensure(
        appdir.exists() and appdir.is_dir(),
        ValueError,
        f"App directory '{app}' does not exist.",
    )

    # Create the HTML file
    html_path = appdir / f"{page}.html"
    ensure(
        not html_path.exists(),
        ValueError,
        f"Page '{page}.html' already exists.",
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(PAGE_TEMPLATE_HTML.replace("#PAGENAME#", page))

    # Try to modify __init__.py if safe
    init_path = appdir / "__init__.py"
    if init_path.exists():
        try:
            content = init_path.read_text(encoding="utf-8")
            marker = "\n\npage_order = ["
            if marker in content:
                page_class = PAGE_TEMPLATE_PY.replace("#PAGENAME#", page)
                new_content = content.replace(marker, page_class + "\n\npage_order = [")
                init_path.write_text(new_content, encoding="utf-8")
        except Exception:
            pass  # Fail silently if __init__.py cannot be safely modified
