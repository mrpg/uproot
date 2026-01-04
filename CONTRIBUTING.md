# Contributing to uproot

Thank you for your interest in contributing to uproot! This guide will help you get started with development.

## Development Setup

1. **Clone the repository and set up your environment**:
   ```bash
   git clone https://github.com/mrpg/uproot.git
   cd uproot
   python -m venv env
   source env/bin/activate  # On Windows: env\Scripts\activate
   ```

2. **Install development dependencies**:
   ```bash
   make install
   ```

   This will:
   - Install the package in editable mode with all dev dependencies
   - Set up pre-commit hooks automatically

## Development Workflow

### Running Checks Locally

Before committing, ensure your code passes all checks:

```bash
# Run all checks at once
make all

# Or run individual checks:
make format          # Auto-format code (black, isort, ruff --fix)
make lint            # Check code style (ruff, black, isort)
make type-check      # Run mypy type checking
make security        # Run security scans (bandit, pip-audit, semgrep)
make quality         # Run code quality checks (radon, deptry)
make test            # Run tests with coverage
```

See all available commands with `make help`.

### Pre-commit Hooks

Pre-commit hooks are automatically installed with `make install`. To manually run them on all files:

```bash
pre-commit run --all-files
```

## Development Tools

We use the following tools to maintain code quality:

### Code Quality
- **[Black](https://black.readthedocs.io/)**: Code formatting
- **[isort](https://pycqa.github.io/isort/)**: Import sorting (Black profile)
- **[Ruff](https://docs.astral.sh/ruff/)**: Fast Python linting
- **[mypy](https://mypy.readthedocs.io/)**: Static type checking
- **[Radon](https://radon.readthedocs.io/)**: Code complexity analysis

### Security
- **[Bandit](https://bandit.readthedocs.io/)**: Security vulnerability detection
- **[pip-audit](https://pypi.org/project/pip-audit/)**: Dependency CVE scanning
- **[Deptry](https://deptry.com/)**: Unused/missing dependency detection

### Testing
- **[pytest](https://pytest.org/)**: Testing framework with coverage reporting
- **pytest-asyncio**: Async code testing
- **pytest-cov**: Coverage reports with missing line identification

### Automation
- **Pre-commit hooks**: Automated checks before each commit
- **GitHub Actions**: CI/CD workflow on pull requests
- **Make targets**: Convenient commands for common tasks

## Standards

- **Python version**: Minimum Python 3.11 required
- **Database support**: Optional PostgreSQL support via psycopg
- **Versioning**: [Semantic versioning](https://semver.org/) (MAJOR.MINOR.PATCH)

All development dependencies are included in the `[dev]` optional dependency group.
