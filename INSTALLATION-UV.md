We recommend using [uv](https://docs.astral.sh/uv/), a modern Python package manager written in Rust. It's 10-100x faster than pip, automatically manages Python versions, and replaces multiple tools (pip, virtualenv, pyenv) with a single command.

#### Windows

1. **Install uv** (PowerShell):
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Alternatively, use winget:
   ```powershell
   winget install --id=astral-sh.uv -e
   ```

2. **Install Python and create virtual environment**:
   ```powershell
   uv python install 3.12
   uv venv
   ```

3. **Activate the environment**:
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

4. **Continue with the main installation guide**

#### macOS

1. **Install uv**:
   - **Option 1** - Using the installer (recommended):
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
   - **Option 2** - Using Homebrew:
     ```bash
     brew install uv
     ```

2. **Install Python and create virtual environment**:
   ```bash
   uv python install 3.12
   uv venv
   ```

3. **Activate the environment**:
   ```bash
   source .venv/bin/activate
   ```

4. **Continue with the main installation guide**

#### Linux

1. **Install uv**:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install Python and create virtual environment**:
   ```bash
   uv python install 3.12
   uv venv
   ```

3. **Activate the environment**:
   ```bash
   source .venv/bin/activate
   ```

4. **Continue with the main installation guide**

**Note**: uv automatically downloads and manages Python versions, so you don't need Python pre-installed. The virtual environment is created in `.venv` by default.
