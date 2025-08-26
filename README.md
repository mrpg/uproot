# uproot

## About

*uproot* is a modern software framework for developing and conducting browser-based behavioral experiments. This includes studies with hundreds of participants such as large-scale surveys and experiments with real-time interaction between the participants.

*uproot* is 100% [Free/Libre Open Source Software](https://en.wikipedia.org/wiki/Free_and_open-source_software), and contains only unencumbered code.

We are working on producing the first alpha version (0.0.1), and invite you to join us.

**Note: This repository contains a pre-alpha version. Breaking changes are made with reckless abandon. DO NOT USE IN PRODUCTION.**


## Getting started

### Installing *uproot* via the command line

1. Run this from within a Python venv:
    ```console
    pip install -U 'uproot-science[dev] @ https://github.com/mrpg/uproot/archive/main.zip'
    ```
    If this does not work, try
    ```console
    pip install -U 'uproot-science[dev] @ git+https://github.com/mrpg/uproot.git@main'
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

### Example apps

Example apps may be found [here](https://github.com/mrpg/uproot-examples).

## License

*uproot* is licensed under the GNU LGPL version 3.0, or, at your option, any later version. Among other things, that means: (1) there is no warranty; (2) changes to uproot’s core are automatically licensed under the LGPL as well, (3) you are free to license your own experiments under whatever license you deem appropriate, or no license at all.

© [Max R. P. Grossmann](https://max.pm/), [Holger Gerhardt](https://www.econ.uni-bonn.de/iame/en/team/gerhardt), et al., 2025. A full alphabetical overview of contributors may be viewed [here](CONTRIBUTORS.md).
