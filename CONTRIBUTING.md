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
