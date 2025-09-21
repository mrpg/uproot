# uproot

## About

*uproot* is a modern software framework for developing and conducting browser-based behavioral experiments. This includes studies with hundreds of participants such as large-scale surveys and experiments with real-time interaction between the participants.

*uproot* is 100% [Free/Libre Open Source Software](https://en.wikipedia.org/wiki/Free_and_open-source_software), and contains only unencumbered code. All libraries, styles and fonts are included and served locally (no CDNs).

We are working on producing the first alpha version (0.0.1), and invite you to join us.

> [!IMPORTANT]
> This repository contains a pre-alpha version. Breaking changes are made with reckless abandon. **Do not use in production.**
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

### Example apps

Example apps may be found [here](https://github.com/mrpg/uproot-examples).

### Detailed Python and virtual environment setup

If you're new to Python or don't have Python 3.11+ installed, follow these platform-specific guides:

#### Windows

1. **Install Python** (requires administrator privileges):
   - Download Python 3.11+ from [python.org](https://www.python.org/downloads/)
   - Run the installer as administrator
   - Select the following advanced options:
       - **Important**: During installation, check "Add Python to PATH" - this is crucial
       - Choose "Install for all users"
   - Verify installation by opening Command Prompt and running:
     ```cmd
     python --version
     ```

2. **Create and activate virtual environment**: Start PowerShell and run:
   ```cmd
   python -m venv env
   ```
   
   **Before activating**: You may need to allow script execution by running PowerShell as administrator and executing:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
   
   Then activate the environment:
   ```cmd
   env\Scripts\activate
   ```

3. **Continue with the main installation guide above**

#### macOS

1. **Install Python**:
   - **Option 1** - Using Homebrew (recommended):
     ```bash
     brew install python
     ```
   - **Option 2** - Download Python 3.11+ from [python.org](https://www.python.org/downloads/)
   
   - Verify installation:
     ```bash
     python3 --version
     ```

2. **Create and activate virtual environment**:
   ```bash
   python3 -m venv env
   source env/bin/activate
   ```

3. **Continue with the main installation guide above**

#### Linux

Most Linux distributions include Python, but you may need to install the virtual environment module:

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-venv

# Create and activate virtual environment
python3 -m venv env
source env/bin/activate
```

**Note**: Always activate your virtual environment (`env`) before installing or running *uproot*. You'll know it's active when you see `(env)` at the beginning of your command prompt.

## Development best practices

We follow these development practices to maintain code quality:

- **Code formatting**: [Black](https://black.readthedocs.io/) for consistent code formatting
- **Import sorting**: [isort](https://pycqa.github.io/isort/) with Black profile compatibility
- **Type checking**: [mypy](https://mypy.readthedocs.io/) with strict typing enabled
- **Linting**: [Ruff](https://docs.astral.sh/ruff/) for fast Python linting
- **Testing**: [pytest](https://pytest.org/) with coverage reporting via pytest-cov
- **Async testing**: pytest-asyncio for testing asynchronous code
- **Code coverage**: Coverage reports show missing lines for comprehensive testing
- **Python version**: Minimum Python 3.11 required
- **Database support**: Optional PostgreSQL support via psycopg
- **Versioning**: [Semantic versioning](https://semver.org/) (MAJOR.MINOR.PATCH)
- **Development workflow**: Install with `[dev]` extras for all development tools

All development dependencies are included in the `[dev]` optional dependency group.

## License

*uproot* is licensed under the GNU LGPL version 3.0, or, at your option, any later version. Among other things, that means: (1) there is no warranty; (2) changes to uproot’s core are automatically licensed under the LGPL as well, (3) you are free to license your own experiments under whatever license you deem appropriate, or no license at all.

© [Max R. P. Grossmann](https://max.pm/), [Holger Gerhardt](https://www.econ.uni-bonn.de/iame/en/team/gerhardt), et al., 2025. A full alphabetical overview of contributors may be viewed [here](CONTRIBUTORS.md).
