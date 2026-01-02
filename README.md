# uproot

## About

*uproot* is a modern software framework for developing and conducting browser-based behavioral experiments. This includes studies with hundreds of participants such as large-scale surveys and experiments with real-time interaction between the participants.

*uproot* is 100% [Free/Libre Open Source Software](https://en.wikipedia.org/wiki/Free_and_open-source_software), and contains only unencumbered code. All libraries, styles and fonts are included and served locally (no CDNs).

We are working on producing the first alpha version (0.0.1), and invite you to join us. Example apps may be found [here](https://github.com/mrpg/uproot-examples).

> [!IMPORTANT]
> This repository contains a pre-alpha version. Breaking changes are made with reckless abandon.
>

## Getting started

### Installing *uproot* via the command line

**Prerequisites**: You need Python 3.11+ and be within an activated virtual environment. If you don't have Python installed yet, see the [detailed setup guide](#detailed-python-and-virtual-environment-setup) below.

1. Run this from within a Python venv:
    ```console
    pip install -U 'uproot-science[dev] @ git+https://github.com/mrpg/uproot.git@main'
    ```
    If this does not work, try
    ```console
    pip install -U 'uproot-science[dev] @ https://github.com/mrpg/uproot/archive/main.zip'
    ```
    or
    ```console
    pip install -U https://github.com/mrpg/uproot/archive/main.zip
    ```

2. Then, you may do:
    ```console
    uproot setup my_project
    ```

3. The resulting output shows you how to proceed. Have fun!

After running `uproot run`, we recommend you visit [the admin area](http://127.0.0.1:8000/admin/) with the provided credential.

### Detailed Python and virtual environment setup

If you're new to Python or don't have Python 3.11+ installed, follow these platform-specific guides:

- [**Using uv**](INSTALLATION-UV.md) (recommended) - A modern, fast package manager that handles Python installation automatically
- [Using pip](INSTALLATION-PIP.md) - Traditional setup with Python's built-in tools

## Development best practices

We follow these development practices to maintain code quality:

### Code Quality Tools
- **Code formatting**: [Black](https://black.readthedocs.io/) for consistent code formatting
- **Import sorting**: [isort](https://pycqa.github.io/isort/) with Black profile compatibility
- **Type checking**: [mypy](https://mypy.readthedocs.io/) with strict typing enabled
- **Linting**: [Ruff](https://docs.astral.sh/ruff/) for fast Python linting
- **Complexity analysis**: [Radon](https://radon.readthedocs.io/) for measuring code complexity and maintainability
- **Dependency management**: [pip-tools](https://pip-tools.readthedocs.io/) for reproducible dependency pinning

### Security Tools
- **Security scanning**: [Bandit](https://bandit.readthedocs.io/) for detecting security vulnerabilities
- **Dependency auditing**: [pip-audit](https://pypi.org/project/pip-audit/) for scanning dependencies for known CVEs
- **Dependency checking**: [Deptry](https://deptry.com/) for finding unused and missing dependencies

### Testing
- **Testing framework**: [pytest](https://pytest.org/) with coverage reporting via pytest-cov
- **Async testing**: pytest-asyncio for testing asynchronous code
- **Code coverage**: Coverage reports show missing lines for comprehensive testing

### Automation
- **Pre-commit hooks**: Automated checks before each commit
- **CI/CD**: GitHub Actions workflow running all checks on pull requests
- **Make commands**: Convenient `make` targets for common tasks

### Quick Start for Development

1. **Install development dependencies**:
   ```bash
   make install
   ```

2. **Run all checks**:
   ```bash
   make all
   ```

3. **Available commands**:
   ```bash
   make help              # Show all available commands
   make format            # Auto-format code
   make lint              # Run linting checks
   make type-check        # Run mypy
   make security          # Run security scans
   make quality           # Run code quality checks
   make test              # Run tests with coverage
   make requirements      # Compile requirements.txt
   ```

4. **Pre-commit hooks**: Automatically installed with `make install`. Manually run with:
   ```bash
   pre-commit run --all-files
   ```

### Standards
- **Python version**: Minimum Python 3.11 required
- **Database support**: Optional PostgreSQL support via psycopg
- **Versioning**: [Semantic versioning](https://semver.org/) (MAJOR.MINOR.PATCH)

All development dependencies are included in the `[dev]` optional dependency group.

## License

*uproot* is licensed under the GNU LGPL version 3.0, or, at your option, any later version. Among other things, that means: (1) there is no warranty; (2) changes to uproot’s core are automatically licensed under the LGPL as well, (3) you are free to license your own experiments under whatever license you deem appropriate, or no license at all. (By default, *uproot* puts new projects under the 0BSD license, but you are free to change this.)

© [Max R. P. Grossmann](https://max.pm/), [Holger Gerhardt](https://www.econ.uni-bonn.de/iame/en/team/gerhardt), et al., 2025. A full alphabetical overview of contributors may be viewed [here](CONTRIBUTORS.md).
