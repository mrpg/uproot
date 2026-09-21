#!/usr/bin/env bash

set -euxo pipefail

# Sync dependencies
uv sync --extra dev --upgrade

# Run formatters and autofixes
uv run ruff check --fix src/uproot/
uv run black src/uproot/
uv run isort src/uproot/


# Run release checks
uv run pytest
uv run mypy
uv run bandit -r src/uproot/ -c pyproject.toml
uvx pip-audit
uv run deptry src/uproot/
uv run radon cc src/uproot/ -a -nb
uv run radon mi src/uproot/ -nb

# Commit and push changes
git add .
git commit -m "Release $1"
git push

# Add tag
git tag -a "$1" -m "Release $1"
git push --tags

# Clean and build release artifacts

SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"

rm -rf ./dist/
export SOURCE_DATE_EPOCH
umask 022
uv run pip wheel . -w dist/

# Verify release artifacts
uv run twine check dist/uproot*.whl

# Finish
echo
echo OK
