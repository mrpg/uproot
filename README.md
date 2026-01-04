# uproot

*uproot* is a modern software framework for developing and conducting browser-based behavioral experiments. This includes studies with hundreds of participants such as large-scale surveys and experiments with real-time interaction between the participants.

**[See example apps.](https://github.com/mrpg/uproot-examples)**

> [!IMPORTANT]
> This repository contains a pre-alpha version. Breaking changes are made with reckless abandon. We are working towards the first alpha (0.0.1) and invite you to join us.

*uproot* is 100% [Free/Libre Open Source Software](https://en.wikipedia.org/wiki/Free_and_open-source_software), and contains only unencumbered code. All libraries, styles and fonts are included and served locally (no CDNs).

## Getting started

These instructions use [uv](https://docs.astral.sh/uv/), a fast Python package manager that handles Python installation automatically. See [alternative installation with pip](INSTALLATION-PIP.md) if you prefer traditional tools.

### 1. Install uv

**macOS/Linux:**
```console
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

<details>
<summary>Other installation methods</summary>

- **macOS with Homebrew**: `brew install uv`
- **Windows with winget**: `winget install --id=astral-sh.uv -e`

See [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for more options.
</details>

### 2. Create a project

```console
uv run --with 'uproot-science[dev] @ git+https://github.com/mrpg/uproot.git@main' uproot setup my_project
```

### 3. Run *uproot*

```console
cd my_project
uv run uproot run
```

Visit [the admin area](http://127.0.0.1:8000/admin/) with the provided credential.

## License

*uproot* is licensed under the GNU LGPL version 3.0, or, at your option, any later version. Among other things, that means: (1) there is no warranty; (2) changes to uproot’s core are automatically licensed under the LGPL as well, (3) you are free to license your own experiments under whatever license you deem appropriate, or no license at all. (By default, *uproot* puts new projects under the 0BSD license, but you are free to change this.)

© [Max R. P. Grossmann](https://max.pm/), [Holger Gerhardt](https://www.econ.uni-bonn.de/iame/en/team/gerhardt), et al., 2026. A full alphabetical overview of contributors may be viewed [here](CONTRIBUTORS.md).

## Contributing

Interested in contributing? See our [Contributing Guide](CONTRIBUTING.md) for development setup, coding standards, and workflow information.
