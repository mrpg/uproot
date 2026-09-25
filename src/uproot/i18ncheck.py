# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Find translation keys in source files and check them against YAML files.

Used by `uproot check-translations` for projects and by check_translations.py
in the uproot repository.
"""

import ast
import os
import re

import strictyaml

from uproot.i18n import LOCALES_DIR

TRANSLATE_BLOCK = re.compile(
    r"{%\s*translate\s*%}(.*?){%\s*endtranslate\s*%}", re.DOTALL
)
# _('...'), _("..."), and JavaScript template literals without placeholders
UNDERSCORE_CALL = re.compile(r"""_\((?:'([^']*?)'|"([^"]*?)"|`([^`$]*?)`)\)""")

# translate("..."), lookup("...", language)
KEY_FUNCTIONS = {"translate", "lookup"}
# field.gettext("..."), i18n.lookup("...", language)
KEY_METHODS = {"gettext", "lookup"}

# Field attributes that uproot's form macros pass through translate()
FIELD_TEXTS = {"label", "description", "label_floating", "label_min", "label_max"}

SKIPPED_DIRS = {"__pycache__", "node_modules", "site-packages", "vendor"}
LANGUAGE_FILE = re.compile(r"^[a-z]{2,3}([_-][A-Za-z0-9]+)?$")
QUOTES = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'"})


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def loosely(key: str) -> str:
    """Normalize quotes and whitespace to find keys that almost match."""
    return normalize(key.translate(QUOTES))


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


def choice_labels(node: ast.expr) -> list[str]:
    """Return the literal labels of choices=[(value, "label"), "label", ...]
    or choices={value: "label"}."""
    labels: list[ast.expr] = []

    if isinstance(node, (ast.List, ast.Tuple)):
        for element in node.elts:
            if isinstance(element, ast.Tuple) and len(element.elts) == 2:
                labels.append(element.elts[1])
            else:
                labels.append(element)
    elif isinstance(node, ast.Dict):
        labels = list(node.values)

    return [
        label.value
        for label in labels
        if isinstance(label, ast.Constant) and isinstance(label.value, str)
    ]


def find_field_texts(filepath: str) -> list[tuple[str, int]]:
    """Return literal labels, descriptions, and choice labels of form fields,
    such as RadioField(label="...", choices=[...]). uproot translates these
    when rendering a form."""
    with open(filepath, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=filepath)

    results: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")

        if not name.endswith("Field"):
            continue

        for keyword in node.keywords:
            if (
                keyword.arg in FIELD_TEXTS
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
                and keyword.value.value
            ):
                results.append((keyword.value.value, keyword.value.lineno))
            elif keyword.arg == "choices":
                results += [
                    (label, keyword.value.lineno)
                    for label in choice_labels(keyword.value)
                ]

    return results


def find_used_keys(top: str) -> list[tuple[str, str, int]]:
    """Return (file, key, line) for all translation keys used below top."""
    used = []
    html_files = collect_files(top, (".html",))

    for filepath in html_files:
        used += [(filepath, k, line) for k, line in find_translate_blocks(filepath)]

    for filepath in html_files + collect_files(top, (".js",)):
        used += [(filepath, k, line) for k, line in find_underscore_calls(filepath)]

    for filepath in collect_files(top, (".py",)):
        used += [
            (filepath, k, line) for k, line in find_python_translate_calls(filepath)
        ]

    return used


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


def check_project(top: str, list_untranslated: bool = False) -> int:
    """Check that every key a project uses exists for each language that has a
    YAML file in the project, either there or among uproot's built-in
    translations. Print a report and return an exit code.

    Texts of form fields are translated automatically, whether or not they
    are meant to be. So they only count as missing if they are translated for
    some languages but not for others."""
    if not os.path.isdir(top):
        print(f"{top} is not a directory.")
        return 2

    project = load_locale_dir_terms(top)
    builtin = load_locale_dir_terms(LOCALES_DIR)
    used = find_used_keys(top)
    field_texts = [
        (filepath, key, line)
        for filepath in collect_files(top, (".py",))
        for key, line in find_field_texts(filepath)
    ]
    anywhere = set().union(*project.values()) if project else set()
    untranslated = sorted({k for _, k, _ in field_texts if k not in anywhere})
    rc = 0

    if not project:
        print(f"No translation files found in {top}.")
        return 0

    for language in sorted(project):
        known = project[language] | builtin.get(language, set())
        by_loose_key = {loosely(k): k for k in project[language]}
        checked = used + [(f, k, line) for f, k, line in field_texts if k in anywhere]
        missing = [(f, k, line) for f, k, line in checked if k not in known]

        if not missing:
            print(f"{language}: all {len(checked)} translation key uses found.")
            continue

        rc = 1
        print(f"{language}: {len(missing)} translation key use(s) not found:\n")

        for filepath, key, line in missing:
            print(f"  {os.path.relpath(filepath, top)}:{line}")
            print(f"    {key!r}")

            if (similar := by_loose_key.get(loosely(key))) is not None:
                print(f"    Differs only in quotes or spacing from: {similar!r}")

            print()

    if untranslated:
        print(
            f"\n{len(untranslated)} form field text(s) have no translation in "
            "any language and are shown as written."
        )

        if list_untranslated:
            for key in untranslated:
                print(f"  {key!r}")
        else:
            print("Use --untranslated to list them.")

    return rc
