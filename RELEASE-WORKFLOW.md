# Release workflow

1. Choose version `X.Y.Z` according to the versioning policy below.
1. Update `__version_info__` in `src/uproot/__init__.py`.
1. Update `version` in `pyproject.toml`.
1. Update `recommendedVersion` in `announcements.json`, and add or update the matching version-specific announcement if needed.
1. Copy or move (after 2027-01-01) `announcements.json` to [uproot-docs](https://github.com/mrpg/uproot-docs). Deploy docs.
1. For `1.0.0` or the first PyPI release, update install and status text in `README.md` and `INSTALLATION-PIP.md`.
1. Rerun `uv sync --extra dev --upgrade`.
1. Run formatters and autofixes: `uv run ruff check --fix src/uproot/ && uv run black src/uproot/ && uv run isort src/uproot/`.
1. Run release checks: `uv run pytest && uv run mypy src/uproot/ && uv run bandit -r src/uproot/ -c pyproject.toml && uvx pip-audit && uv run deptry src/uproot/ && uv run radon cc src/uproot/ -a -nb && uv run radon mi src/uproot/ -nb`.
1. Commit changes with commit message `Release vX.Y.Z`.
1. Push with `git push`. Ensure that CI passes.
1. Tag with `git tag vX.Y.Z`.
1. Push with `git push --tags`.
1. Create [GitHub release](https://github.com/mrpg/uproot/releases/new).
1. Clean and build release artifacts: `rm -rf dist/ && uv run pip wheel . -w dist/`.
1. Verify release artifacts: `uv run twine check dist/*`.
1. Upload to PyPI: `uv run twine upload dist/uproot*.whl`.

# Versioning policy

1. uproot follows [Semantic Versioning](https://semver.org/). Versions are represented by Git tags with the `v` prefix, for example `v1.0.0`.
1. uproot avoids SemVer pre-release identifiers.
1. Versions `0.x.y` are development versions.
1. Version `1.0.0` is the first release recommended for public use.
1. Version `1.0.0` may only be released after *(i)* a public review and *(ii)* four days of inactivity on this repository.

# Versions

- `0.3.1` (2026-08-05)
- `0.3.0` (2026-07-26)
- `0.2.0` (2026-07-16)
- `0.1.0` (2026-07-11)
- `0.0.1` (not formally assigned; denotes all initial-development versions before `0.1.0`)
