# Installing uproot with pip

This guide uses Python's built-in tools. For a simpler setup, see the [main README](README.md) which uses uv.

## 1. Install Python 3.11+

<details open>
<summary><strong>Windows</strong></summary>

1. Download Python 3.11+ from [python.org](https://www.python.org/downloads/)
2. Run the installer as administrator
3. **Important**: Check "Add Python to PATH" during installation
4. Verify: `python --version`
</details>

<details>
<summary><strong>macOS</strong></summary>

Using Homebrew (recommended):
```bash
brew install python
```

Or download from [python.org](https://www.python.org/downloads/).

Verify: `python3 --version`
</details>

<details>
<summary><strong>Linux</strong></summary>

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-venv
```

Verify: `python3 --version`
</details>

## 2. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv env
.\env\Scripts\Activate.ps1
```

> If activation fails, run as administrator: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

**macOS/Linux:**
```bash
python3 -m venv env
source env/bin/activate
```

You'll see `(env)` in your prompt when active.

## 3. Install uproot

```console
pip install -U 'uproot-science[dev] @ git+https://github.com/mrpg/uproot.git@main'
```

<details>
<summary>Alternative if the above doesn't work</summary>

```console
pip install -U 'uproot-science[dev] @ https://github.com/mrpg/uproot/archive/main.zip'
```
</details>

## 4. Create and run a project

```console
uproot setup my_project
cd my_project
uproot run
```

Visit [the admin area](http://127.0.0.1:8000/admin/) with the provided credential.

**Note**: Always activate your virtual environment before running uproot commands.
