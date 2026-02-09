# uproot

[![Examples](https://img.shields.io/badge/uproot--examples-blue)](https://github.com/mrpg/uproot-examples)
[![Website](https://img.shields.io/badge/Website-uproot.science-green)](https://uproot.science/)

*uproot* is a modern software framework for developing and conducting browser-based behavioral experiments. This includes studies with hundreds of participants such as large-scale surveys and experiments with real-time interaction between the participants.

> [!IMPORTANT]
> This repository contains a pre-alpha version. Breaking changes are made with reckless abandon. We are working towards the first release and invite you to join us.

*uproot* is 100% [Free/Libre Open Source Software](https://en.wikipedia.org/wiki/Free_and_open-source_software), and contains only unencumbered code. All libraries, styles and fonts are included and served locally (no CDNs). *uproot* believes in best practices.

## Getting started

*uproot* recommends the use of [uv](https://docs.astral.sh/uv/), a fast Python package manager that handles Python installation and the installation of dependencies automatically. See [alternative installation with pip](INSTALLATION-PIP.md) if you prefer traditional tools.

### 1. Install uv

**macOS/Linux:**
```console
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

See [uv installation docs](https://docs.astral.sh/uv/getting-started/installation/) for more options.

### 2. Create a project

```console
uv run --with 'uproot-science[dev] @ git+https://github.com/mrpg/uproot.git@main' uproot setup my_project
```

### 3. Run *uproot*

```console
cd my_project
uv run uproot run
```

You may then log in to the admin area, or [run an example experiment](http://127.0.0.1:8000/room/test/).
You can find other examples [here](https://github.com/mrpg/uproot-examples).
Needless to say, step (1) only needs to be done once, and step (2) only when creating a new project.

## License

*uproot* is licensed under the GNU LGPL version 3.0, or, at your option, any later version. Among other things, that means: (1) there is no warranty; (2) changes to uproot’s core are automatically licensed under the LGPL as well, (3) you are free to license your own experiments under whatever license you deem appropriate, or no license at all.

© [Max R. P. Grossmann](https://max.pm/), [Holger Gerhardt](https://www.econ.uni-bonn.de/iame/en/team/gerhardt), et al., 2026. A full alphabetical overview of contributors may be viewed [here](CONTRIBUTORS.md).

## Citation

[You are ethically obliged to cite specialist software used to create research outputs.](https://peerj.com/articles/cs-86/) Please cite the following paper:

```bibtex
 @unpublished{uproot,
  author = {Grossmann, Max~R.~P. and Gerhardt, Holger},
  title = {uproot: A Software Framework for Behavioral Experiments},
  year = {2026},
  note = {Unpublished manuscript}
}
```

## Contributing

Interested in contributing? See our [Contributing Guide](CONTRIBUTING.md) for development setup, coding standards, and workflow information.
