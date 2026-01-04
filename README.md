# uproot

*uproot* is a modern software framework for developing and conducting browser-based behavioral experiments. This includes studies with hundreds of participants such as large-scale surveys and experiments with real-time interaction between the participants.

**[See example apps.](https://github.com/mrpg/uproot-examples)**

> [!IMPORTANT]
> This repository contains a pre-alpha version. Breaking changes are made with reckless abandon. We are working towards the first alpha (0.0.1) and invite you to join us.

*uproot* is 100% [Free/Libre Open Source Software](https://en.wikipedia.org/wiki/Free_and_open-source_software), and contains only unencumbered code. All libraries, styles and fonts are included and served locally (no CDNs).

## Getting started

### 1. Set up Python

You need Python 3.11+ within an activated virtual environment.

**New to Python?** Follow one of these guides first:
- [**Using uv**](INSTALLATION-UV.md) (recommended) - A modern, fast package manager that handles Python installation automatically
- [Using pip](INSTALLATION-PIP.md) - Traditional setup with Python's built-in tools

**Already have Python 3.11+ in a venv?** Continue below.

### 2. Install *uproot*

From within your activated virtual environment:

```console
pip install -U 'uproot-science[dev] @ git+https://github.com/mrpg/uproot.git@main'
```

<details>
<summary>Alternative installation methods</summary>

If the above doesn't work, try:
```console
pip install -U 'uproot-science[dev] @ https://github.com/mrpg/uproot/archive/main.zip'
```

Or without dev dependencies:
```console
pip install -U https://github.com/mrpg/uproot/archive/main.zip
```
</details>

### 3. Create a project

```console
uproot setup my_project
```

The output shows you how to proceed. After running `uproot run`, visit [the admin area](http://127.0.0.1:8000/admin/) with the provided credential.

## License

*uproot* is licensed under the GNU LGPL version 3.0, or, at your option, any later version. Among other things, that means: (1) there is no warranty; (2) changes to uproot’s core are automatically licensed under the LGPL as well, (3) you are free to license your own experiments under whatever license you deem appropriate, or no license at all. (By default, *uproot* puts new projects under the 0BSD license, but you are free to change this.)

© [Max R. P. Grossmann](https://max.pm/), [Holger Gerhardt](https://www.econ.uni-bonn.de/iame/en/team/gerhardt), et al., 2026. A full alphabetical overview of contributors may be viewed [here](CONTRIBUTORS.md).

## Contributing

Interested in contributing? See our [Contributing Guide](CONTRIBUTING.md) for development setup, coding standards, and workflow information.
