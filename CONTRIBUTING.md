# Contributing to uproot

Thank you for contributing to uproot.

## Set up a development environment

uproot requires Python 3.11 or newer and uses [uv](https://docs.astral.sh/uv/) to manage its development environment.

```console
git clone https://github.com/mrpg/uproot.git
cd uproot
uv sync --extra dev
source .venv/bin/activate
pre-commit install
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

## Make and check changes

Add or update tests for behavioural changes. Before opening a pull request, run:

```console
ruff check --fix src/uproot
black src/uproot
isort src/uproot
mypy src/uproot
python check_translations.py
pytest
```

The formatters and Ruff may update files. Review those changes before committing. You can also run every configured hook with:

```console
pre-commit run --all-files
```

CI runs these checks across the supported Python versions and performs additional security and dependency checks.

For release steps and the versioning policy, see [RELEASE-WORKFLOW.md](RELEASE-WORKFLOW.md).
