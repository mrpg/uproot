# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
Basic usage:
    import uproot.i18n as i18n

    # Load your project's translations
    i18n.load("/path/to/your/locales/")

    # Use in templates: {% translate %}Welcome{% endtranslate %}
    # Use in code: i18n.lookup("Welcome", "de") -> "Willkommen"
"""

import os
import re
from typing import Annotated, Callable

import orjson
import strictyaml
from jinja2 import BaseLoader, Environment

ISO639 = Annotated[
    str,
    "ISO 639 language code (ISO 639-1 codes preferred, e.g., en, de, it, pt)",
]

LANGUAGES: set[ISO639] = set()
LOCALES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "default", "locales"
)

MISSING: set[tuple[str, ISO639]] = set()
TERMS: dict[str, dict[ISO639, str]] = dict()
JSON: dict[ISO639, str] = dict()


class TranslateLoader(BaseLoader):
    def __init__(self, base_loader: BaseLoader) -> None:
        self.base_loader = base_loader
        self.pattern = r"{%\s*translate\s*%}(.*?){%\s*endtranslate\s*%}"

    def get_source(
        self, environment: Environment, template: str
    ) -> tuple[str, str | None, Callable[[], bool] | None]:
        source, filename, uptodate = self.base_loader.get_source(environment, template)

        def replace_translate_block(mtch: re.Match[str]) -> str:
            # Extract and strip the content from the match
            content = mtch.group(1).strip()

            return compile_translate_block(content)

        processed_source = re.sub(
            self.pattern, replace_translate_block, source, flags=re.DOTALL
        )
        return processed_source, filename, uptodate


def missing(s: str, target: ISO639) -> str:
    from uproot.deployment import LOGGER

    LOGGER.debug(f"Missing translation into {target} of: '{s}'")

    MISSING.add((s, target))

    return s


def lookup(s: str, target: ISO639) -> str:
    try:
        return TERMS[s][target]
    except KeyError:
        # Try fallback with line endings normalized
        normalized = s.replace("\r", "").replace("\n", " ")
        try:
            return TERMS[normalized][target]
        except KeyError:
            return missing(s, target)


def compile_translate_block(s: str) -> str:
    out = ""

    for i, lang in enumerate(LANGUAGES):
        translated = lookup(s, lang)
        el_ = "el" if i > 0 else ""

        out += (
            "{% "
            + el_
            + "if _uproot_internal.language == '"
            + lang
            + "' %}"
            + translated
        )

    return (
        out
        + "{% else %}Missing translation into {{ _uproot_internal.language }} of '"
        + s
        + "'{% endif %}"
    )


def json(target: ISO639) -> str:
    if target not in JSON:
        translations = {
            src: translations[target]
            for src, translations in TERMS.items()
            if target in translations
        }

        JSON[target] = orjson.dumps(translations).decode()

    return JSON[target]


def load(yaml_path: str, default_language: ISO639 = "en") -> None:
    """
    Load translation terms from YAML files or directory.

    Args:
        yaml_path: Path to directory containing YAML files, or path to a single YAML file
        default_language: The language to use as the key (uproot default is English)
    """
    global TERMS, LANGUAGES

    all_translations = {}

    if os.path.isfile(yaml_path):
        # Single YAML file - assume it contains all languages
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = strictyaml.load(f.read()).data
                if isinstance(data, dict):
                    all_translations = data
        except Exception:
            return
    else:
        # Directory containing separate YAML files
        if not os.path.isdir(yaml_path):
            return

        # Load all YAML files in the directory
        for filename in os.listdir(yaml_path):
            if filename.endswith(".yml") or filename.endswith(".yaml"):
                lang = filename.split(".")[0]
                file_path = os.path.join(yaml_path, filename)

                with open(file_path, "r", encoding="utf-8") as f:
                    lang_data = strictyaml.load(f.read()).data

                    if isinstance(lang_data, dict):
                        all_translations[lang] = lang_data

    # Add translations to TERMS cache
    if all_translations:
        all_keys: set[str] = set()

        for lang_data in all_translations.values():
            if isinstance(lang_data, dict):
                all_keys.update(lang_data.keys())

        for key in all_keys:
            if key not in TERMS:
                TERMS[key] = {}

            for lang, lang_data in all_translations.items():
                if isinstance(lang_data, dict) and key in lang_data:
                    TERMS[key][lang] = lang_data[key]

        LANGUAGES.update(all_translations.keys())


def load_defaults() -> None:
    if os.path.exists(LOCALES_DIR):
        load(LOCALES_DIR)


load_defaults()
