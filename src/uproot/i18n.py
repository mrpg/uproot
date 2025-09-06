# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import csv
import io
import os
import re
from textwrap import dedent
from typing import Annotated, Callable, Optional

import orjson
from jinja2 import BaseLoader, Environment

ISO639 = Annotated[
    str,
    "ISO 639 language code (ISO 639-1 codes preferred, e.g., en, de, it, pt)",
]
LANGUAGES: set[ISO639] = set(["en"])
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
            content = dedent(mtch.group(1))
            content = mtch.group(1).strip()

            return compile_translate_block(content)

        processed_source = re.sub(
            self.pattern, replace_translate_block, source, flags=re.DOTALL
        )
        return processed_source, filename, uptodate


def missing(s: str, target: ISO639) -> str:
    from uproot.deployment import HIDE_MISSING_I18N, LOGGER

    if not HIDE_MISSING_I18N:
        LOGGER.warning(f"Missing translation into {target} of: '{s}'")

    MISSING.add((s, target))

    return s


def lookup(s: str, target: ISO639) -> str:
    try:
        return TERMS[s][target]
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


def add_terms(terms_list: list[dict[ISO639, str]], default: ISO639 = "en") -> None:
    global TERMS, LANGUAGES

    for t in terms_list:
        TERMS[t[default]] = {k: v for k, v in t.items() if isinstance(v, str)}
        LANGUAGES |= t.keys()


def terms_from_csv(
    filename: str, delimiter: Optional[str] = None
) -> list[dict[ISO639, str]]:
    if delimiter is None:
        with io.open(filename, encoding="utf-8-sig", newline="") as f:
            sample = f.read(1024)

        dialect = csv.Sniffer().sniff(sample, delimiters=",;|")
        delimiter = dialect.delimiter

    with io.open(filename, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)

        return [{k: v for k, v in row.items()} for row in reader]


def json(target: ISO639) -> str:
    if target not in JSON:
        JSON[target] = orjson.dumps(
            {
                src: translations[target]
                for src, translations in TERMS.items()
                if target in translations
            }
        ).decode()

    return JSON[target]


add_terms(
    terms_from_csv(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "default", "terms.csv")
    )
)
