#!/usr/bin/env python3
# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Check that all translation keys used in HTML/JS files exist in en.yml.

Usage:
    python check_translations.py          # report only
    python check_translations.py --fix    # remove superfluous keys, add missing ones
"""

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
UNDERSCORE_CALL = re.compile(r"""_\((?:'([^']*?)'|"([^"]*?)")\)""")

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
        if f.endswith(".yml") or f.endswith(".yaml"):
            result.append(os.path.join(LOCALES_DIR, f))
    return result


def read_yml_entries(filepath: str) -> list[tuple[str, str]]:
    """Read a YAML file and return ordered (key, value) pairs."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    entries = []
    for m in re.finditer(
        r"^\?\s*(?:'((?:[^']*)*)'|\"((?:[^\"\\]|\\.)*)\")\n"
        r":\s*(?:'((?:[^']*)*)'|\"((?:[^\"\\]|\\.)*)\")",
        content,
        re.MULTILINE,
    ):
        key = m.group(1) if m.group(1) is not None else m.group(2)
        value = m.group(3) if m.group(3) is not None else m.group(4)
        entries.append((key, value))
    return entries


def write_yml(filepath: str, entries: list[tuple[str, str]]) -> None:
    """Write ordered (key, value) pairs to a YAML file."""
    blocks = [format_entry(k, v) for k, v in entries]
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n\n".join(blocks) + "\n")


def collect_html_files() -> list[str]:
    result = []
    for root, _, files in os.walk(SRC_DIR):
        for f in files:
            if f.endswith(".html"):
                result.append(os.path.join(root, f))
    return sorted(result)


def collect_js_files() -> list[str]:
    result = []
    for root, _, files in os.walk(SRC_DIR):
        for f in files:
            if f.endswith(".js") and "vendor" not in root:
                result.append(os.path.join(root, f))
    return sorted(result)


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
    """Return list of (key, line_number) from _('...') and _("...") calls."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    results = []
    for m in UNDERSCORE_CALL.finditer(content):
        key = m.group(1) if m.group(1) is not None else m.group(2)
        line = content[: m.start()].count("\n") + 1
        results.append((key, line))
    return results


def fix_yml_files(missing_keys: set[str], superfluous_keys: set[str]) -> None:
    """Remove superfluous keys and add missing keys to all YAML files."""
    for filepath in collect_yml_files():
        is_en = os.path.basename(filepath).startswith("en")
        entries = read_yml_entries(filepath)

        # Remove superfluous keys
        entries = [(k, v) for k, v in entries if k not in superfluous_keys]

        # Add missing keys
        existing = {k for k, _ in entries}
        for key in sorted(missing_keys - existing):
            value = key if is_en else "TODO"
            entries.append((key, value))

        write_yml(filepath, entries)

    print("Fixed all YAML files.")


def main() -> int:
    fix = "--fix" in sys.argv

    en_keys = load_en_keys()
    used_keys: set[str] = set()
    missing: list[tuple[str, str, int]] = []  # (file, key, line)

    html_files = collect_html_files()
    js_files = collect_js_files()

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
