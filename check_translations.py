#!/usr/bin/env python3
# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Check that all translation keys used in HTML/JS/Python files exist in en.yml.

To check an uproot project instead, run `uproot check-translations PATH`.

Usage:
    python check_translations.py          # report only
    python check_translations.py --fix    # remove superfluous keys, add missing ones
"""

import os
import sys

import strictyaml

from uproot.i18ncheck import (
    collect_files,
    find_python_translate_calls,
    find_translate_blocks,
    find_underscore_calls,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(SCRIPT_DIR, "src", "uproot")
LOCALES_DIR = os.path.join(SRC_DIR, "default", "locales")
EN_YML = os.path.join(LOCALES_DIR, "en.yml")

# Keys that are intentionally in en.yml without appearing in source files
EXEMPT_KEYS = {"The Use of Knowledge in Society"}


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


def main() -> int:
    fix = "--fix" in sys.argv

    en_keys = load_en_keys()
    used_keys: set[str] = set()
    missing: list[tuple[str, str, int]] = []  # (file, key, line)

    html_files = collect_files(SRC_DIR, (".html",))
    js_files = collect_files(SRC_DIR, (".js",))
    python_files = collect_files(SRC_DIR, (".py",))

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
