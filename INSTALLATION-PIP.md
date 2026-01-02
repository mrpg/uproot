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
   ```powershell
   .\env\Scripts\Activate.ps1
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
