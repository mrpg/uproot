#!/usr/bin/env python3
# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Check that all translation keys used in HTML/JS/Python files exist in en.yml.

With --project, check an uproot project instead: every translation key used in
the project must exist for each language that has a YAML file in the project,
either there or among uproot's built-in translations.

Usage:
    python check_translations.py                     # report only
    python check_translations.py --fix               # remove superfluous keys, add missing ones
    python check_translations.py --project PATH      # check an uproot project
"""

import ast
import os
import re
import sys

import strictyaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(SCRIPT_DIR, "src", "uproot")
LOCALES_DIR = os.path.join(SRC_DIR, "default", "locales")
EN_YML = os.path.join(LOCALES_DIR, "en.yml")

TRANSLATE_BLOCK = re.compile(
    r"{%\s*translate\s*%}(.*?){%\s*endtranslate\s*%}", re.DOTALL
)
# _('...'), _("..."), and JavaScript template literals without placeholders
UNDERSCORE_CALL = re.compile(r"""_\((?:'([^']*?)'|"([^"]*?)"|`([^`$]*?)`)\)""")

# Keys that are intentionally in en.yml without appearing in source files
EXEMPT_KEYS = {"The Use of Knowledge in Society"}


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def load_en_keys() -> set[str]:
    with open(EN_YML, "r", encoding="utf-8") as f:
        data = strictyaml.load(f.read()).data

    return set(data.keys())


def yaml_quote(s: str) -> str:
    """Quote a string for use in YAML, matching the existing file style."""
    if "'" in s:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return "'" + s + "'"


def format_entry(key: str, value: str) -> str:
    """Format a single YAML entry in the ? key / : value style."""
    return f"? {yaml_quote(key)}\n: {yaml_quote(value)}"


def collect_yml_files() -> list[str]:
    result = []
    for f in sorted(os.listdir(LOCALES_DIR)):
        if f.endswith((".yml", ".yaml")):
            result.append(os.path.join(LOCALES_DIR, f))
    return result


def read_yml_entries(filepath: str) -> list[tuple[str, str]]:
    """Read a YAML file and return ordered (key, value) pairs."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    data = strictyaml.load(content).data
    return [(key, value) for key, value in data.items()]


def write_yml(filepath: str, entries: list[tuple[str, str]]) -> None:
    """Write ordered (key, value) pairs to a YAML file."""
    blocks = [format_entry(k, v) for k, v in entries]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks) + "\n")


SKIPPED_DIRS = {"__pycache__", "node_modules", "site-packages", "vendor"}


def collect_files(top: str, suffixes: tuple[str, ...]) -> list[str]:
    """Return files below top with the given suffixes, skipping hidden files,
    hidden directories (such as .venv), and third-party code."""
    result = []
    for root, directories, files in os.walk(top):
        directories[:] = [
            d for d in directories if not d.startswith(".") and d not in SKIPPED_DIRS
        ]
        for f in files:
            if f.endswith(suffixes) and not f.startswith("."):
                result.append(os.path.join(root, f))
    return sorted(result)


def collect_html_files(top: str = SRC_DIR) -> list[str]:
    return collect_files(top, (".html",))


def collect_js_files(top: str = SRC_DIR) -> list[str]:
    return collect_files(top, (".js",))


def collect_python_files(top: str = SRC_DIR) -> list[str]:
    return collect_files(top, (".py",))


def find_translate_blocks(filepath: str) -> list[tuple[str, int]]:
    """Return list of (normalized_key, line_number) from {% translate %} blocks."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    results = []
    for m in TRANSLATE_BLOCK.finditer(content):
        key = normalize(m.group(1))
        line = content[: m.start()].count("\n") + 1
        results.append((key, line))
    return results


def find_underscore_calls(filepath: str) -> list[tuple[str, int]]:
    """Return list of (key, line_number) from _('...'), _("..."), and _(`...`)
    calls. Keys in template literals are whitespace-normalized, like uproot.js
    does when looking them up."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    results = []
    for m in UNDERSCORE_CALL.finditer(content):
        single, double, template = m.groups()
        key = normalize(template) if template is not None else single or double or ""
        line = content[: m.start()].count("\n") + 1
        results.append((key, line))
    return results


def literal_args(node: ast.Call, count: int) -> list[str]:
    """Return the first count arguments if all are string literals."""
    keys = [
        arg.value
        for arg in node.args[:count]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    ]
    return keys if len(keys) == count else []


# translate("..."), lookup("...", language)
KEY_FUNCTIONS = {"translate", "lookup"}
# field.gettext("..."), i18n.lookup("...", language)
KEY_METHODS = {"gettext", "lookup"}


def find_python_translate_calls(filepath: str) -> list[tuple[str, int]]:
    """Return literal keys from translate("...") and lookup("...", language)
    calls, and from gettext("...") and ngettext("...", "...", n) method calls
    (form validation messages), in Python files."""
    with open(filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=filepath)

    results: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        is_function = isinstance(func, ast.Name) and func.id in KEY_FUNCTIONS
        is_method = isinstance(func, ast.Attribute) and func.attr in KEY_METHODS

        if is_function or is_method:
            keys = literal_args(node, 1)
        elif isinstance(func, ast.Attribute) and func.attr == "ngettext":
            keys = literal_args(node, 2)
        else:
            keys = []

        results.extend((key, node.lineno) for key in keys)
    return results


def fix_yml_files(missing_keys: set[str], superfluous_keys: set[str]) -> None:
    """Remove superfluous keys and add missing keys to all YAML files."""
    for filepath in collect_yml_files():
        entries = read_yml_entries(filepath)

        # Remove superfluous keys
        entries = [(k, v) for k, v in entries if k not in superfluous_keys]

        # Add missing keys
        existing = {k for k, _ in entries}
        for key in sorted(missing_keys - existing):
            value = key
            entries.append((key, value))

        write_yml(filepath, entries)

    print("Fixed all YAML files.")


LANGUAGE_FILE = re.compile(r"^[a-z]{2,3}([_-][A-Za-z0-9]+)?$")
QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'"})


def loosely(key: str) -> str:
    """Normalize quotes and whitespace to find keys that almost match."""
    return normalize(key.translate(QUOTES))


def load_locale_dir_terms(top: str) -> dict[str, set[str]]:
    """Return the translated keys per language from YAML files below top.
    Supports one file per language (such as fr.yml) and single files that map
    languages to translations, as uproot.i18n.load() does."""
    terms: dict[str, set[str]] = {}

    for filepath in collect_files(top, (".yml", ".yaml")):
        stem = os.path.splitext(os.path.basename(filepath))[0]

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = strictyaml.load(f.read()).data
        except (OSError, UnicodeError, strictyaml.YAMLError):
            continue

        if not isinstance(data, dict):
            continue

        if LANGUAGE_FILE.match(stem) and all(isinstance(v, str) for v in data.values()):
            terms.setdefault(stem, set()).update(data)
        elif data and all(
            LANGUAGE_FILE.match(str(k)) and isinstance(v, dict) for k, v in data.items()
        ):
            for language, translations in data.items():
                terms.setdefault(language, set()).update(translations)

    return terms


def find_used_keys(top: str) -> list[tuple[str, str, int]]:
    """Return (file, key, line) for all translation keys used below top."""
    used = []
    html_files = collect_html_files(top)

    for filepath in html_files:
        used += [(filepath, k, line) for k, line in find_translate_blocks(filepath)]

    for filepath in html_files + collect_js_files(top):
        used += [(filepath, k, line) for k, line in find_underscore_calls(filepath)]

    for filepath in collect_python_files(top):
        used += [
            (filepath, k, line) for k, line in find_python_translate_calls(filepath)
        ]

    return used


def builtin_locales_dir() -> str:
    """Use the repository's locales, or those of the installed uproot package
    when this script was downloaded on its own."""
    if os.path.isdir(LOCALES_DIR):
        return LOCALES_DIR

    import uproot

    return os.path.join(os.path.dirname(uproot.__file__), "default", "locales")


def check_project(top: str) -> int:
    project = load_locale_dir_terms(top)
    builtin = load_locale_dir_terms(builtin_locales_dir())
    used = find_used_keys(top)
    rc = 0

    if not project:
        print(f"No translation files found in {top}.")
        return 0

    for language in sorted(project):
        known = project[language] | builtin.get(language, set())
        by_loose_key = {loosely(k): k for k in project[language]}
        missing = [(f, k, line) for f, k, line in used if k not in known]

        if not missing:
            print(f"{language}: all {len(used)} translation key uses found.")
            continue

        rc = 1
        print(f"{language}: {len(missing)} translation key use(s) not found:\n")

        for filepath, key, line in missing:
            print(f"  {os.path.relpath(filepath, top)}:{line}")
            print(f"    {key!r}")

            if (similar := by_loose_key.get(loosely(key))) is not None:
                print(f"    Differs only in quotes or spacing from: {similar!r}")

            print()

    return rc


def main() -> int:
    if "--project" in sys.argv:
        index = sys.argv.index("--project") + 1

        if index >= len(sys.argv):
            print("Usage: python check_translations.py --project PATH")
            return 2

        return check_project(sys.argv[index])

    fix = "--fix" in sys.argv

    en_keys = load_en_keys()
    used_keys: set[str] = set()
    missing: list[tuple[str, str, int]] = []  # (file, key, line)

    html_files = collect_html_files()
    js_files = collect_js_files()
    python_files = collect_python_files()

    # Check {% translate %} blocks in HTML files
    for filepath in html_files:
        for key, line in find_translate_blocks(filepath):
            used_keys.add(key)
            if key not in en_keys:
                missing.append((filepath, key, line))

    # Check _('...') / _("...") calls in HTML and JS files
    for filepath in html_files + js_files:
        for key, line in find_underscore_calls(filepath):
            used_keys.add(key)
            if key not in en_keys:
                missing.append((filepath, key, line))

    # Check translate("...") calls in Python files
    for filepath in python_files:
        for key, line in find_python_translate_calls(filepath):
            used_keys.add(key)
            if key not in en_keys:
                missing.append((filepath, key, line))

    rc = 0

    missing_keys = {key for _, key, _ in missing}

    if missing:
        print(
            f"Found {len(missing_keys)} unique translation key(s) missing from en.yml:\n"
        )
        for filepath, key, line in missing:
            rel = os.path.relpath(filepath, SCRIPT_DIR)
            print(f"  {rel}:{line}")
            print(f"    {key!r}\n")
        rc = 1
    else:
        print("All translation keys found in en.yml.")

    superfluous_keys = en_keys - used_keys - EXEMPT_KEYS
    superfluous = sorted(superfluous_keys)
    if superfluous:
        print(f"\nFound {len(superfluous)} superfluous key(s) in en.yml:\n")
        for key in superfluous:
            print(f"  {key!r}")
        rc = 1
    else:
        print("\nNo superfluous keys in en.yml.")

    if fix and (missing_keys or superfluous_keys):
        print()
        fix_yml_files(missing_keys, superfluous_keys)

    return rc


if __name__ == "__main__":
    sys.exit(main())
