# Upgrading from v0.0.1

To upgrade, search your *uproot* project’s `pyproject.toml` for this section:

```toml
dependencies = [
    "uproot-science @ git+https://github.com/mrpg/uproot.git@main",
    ...
]
```

Replace the `uproot-science` entry with

```toml
dependencies = [
    "uproot-science<1",
    ...
]
```

If your `pyproject.toml` also contains this section (projects created by `uproot setup` do):

```toml
[project.optional-dependencies]
pg = [
    "uproot-science[pg] @ git+https://github.com/mrpg/uproot.git@main",
]
```

replace that entry as well:

```toml
[project.optional-dependencies]
pg = [
    "uproot-science[pg]<1",
]
```

**Do not skip this step.** If a `git+` entry relating to `uproot-science` remains anywhere in your `pyproject.toml`, it silently takes precedence, and your project will keep tracking uproot’s current development version.

> [!IMPORTANT]
> Then run `uv sync --upgrade`.

If your project contains a `requirements.txt` (some legacy deployments may use it), replace the `uproot-science` line there in the same way:

```
uproot-science<1
```

If you manage your virtual environment manually, you should then run `pip install -Ur requirements.txt` or similar.

Thank you for being an early adopter!

## Pinning versions exactly (not recommended)

*Note*: You can also pin versions exactly as follows:

```toml
dependencies = [
    "uproot-science==x.y.z",  # Set x, y, z as desired
    ...
]
```

(And similar in the other places.)

However, **this is usually unnecessary**. Your project folder contains a file called `uv.lock`, which records the exact version of *uproot* (and of every other package) that your project uses. As long as that file is in place, `uv` will keep installing exactly those versions — your setup stays reproducible without you having to pin anything yourself.

Reproducibility matters in experimental research, so treat `uv.lock` as part of your experiment: keep it under version control (`uproot setup` initializes a Git repository for you, and `uv.lock` belongs in it), and share it alongside your code. Anyone with your project folder — including your future self — can then recreate the exact same environment with a plain `uv sync`.

In other words:

- Nothing about your installed packages changes behind your back. `uv sync` reinstalls exactly what is recorded in `uv.lock`.
- Upgrades happen only when you explicitly run `uv sync --upgrade`. Do this deliberately — for example, between sessions of an experiment, not in the middle of one.
- If a new version requires your attention, *uproot*’s admin interface will show you an announcement.

Pinning particular versions in `pyproject.toml` therefore adds nothing for reproducibility — the lockfile already guarantees it — but it does block future upgrades until you edit `pyproject.toml` again by hand. **Use it only if you have a specific reason to forbid upgrades entirely.**
