# Contributing to uproot

Thank you for contributing to uproot.

## Set up a development environment

uproot requires Python 3.12 or newer and uses [uv](https://docs.astral.sh/uv/) to manage its development environment.

```console
git clone https://github.com/mrpg/uproot.git
cd uproot
uv sync --extra dev
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

## Make and check changes

Please run `uv run pre-commit install`. We recommend running `uv run pytest -v` when making changes.
