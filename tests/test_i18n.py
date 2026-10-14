import pytest
from jinja2 import DictLoader, Environment

from uproot import i18n


@pytest.mark.parametrize(
    "space",
    [" ", "\t", "\r", "\n", "\r\n", "\v", "\f", "\u00a0", "\u202f", "\u3000", "\ufeff"],
)
def test_lookup_normalizes_whitespace_without_changing_values(monkeypatch, space):
    value = " \tHallo\u00a0Welt\n "
    monkeypatch.setattr(i18n, "TERMS", {"Hello world": {"de": value}})

    assert i18n.lookup(f"{space}Hello{space}{space}world{space}", "de") == value


@pytest.mark.parametrize("key", [" and ", "Many\n  spaces", "#x#\u00a0day", ""])
def test_lookup_prefers_exact_key(monkeypatch, key):
    terms = {i18n.normalize(key): {"de": "normalized"}, key: {"de": "exact"}}
    monkeypatch.setattr(i18n, "TERMS", terms)

    assert i18n.lookup(key, "de") == "exact"


def test_lookup_falls_back_for_the_requested_language(monkeypatch):
    monkeypatch.setattr(
        i18n,
        "TERMS",
        {" and ": {"de": " und "}, "and": {"fr": "et"}},
    )

    assert i18n.lookup(" and ", "fr") == "et"


def test_lookup_preserves_missing_source_and_records_original(monkeypatch):
    key = " \tMissing\u00a0translation\n "
    monkeypatch.setattr(i18n, "TERMS", {"Missing translation": {"de": "fehlt"}})
    monkeypatch.setattr(i18n, "MISSING", set())

    assert i18n.lookup(key, "fr") == key
    assert i18n.MISSING == {(key, "fr")}


@pytest.mark.parametrize(
    "character", ["\x1c", "\x1d", "\x1e", "\x1f", "\x85", "\u200b"]
)
def test_normalize_preserves_characters_that_are_not_javascript_whitespace(character):
    text = f"{character}Hello{character}world{character}"

    assert i18n.normalize(text) == text


def test_translate_block_normalizes_source_but_preserves_translation(monkeypatch):
    monkeypatch.setattr(i18n, "LANGUAGES", {"de"})
    monkeypatch.setattr(i18n, "TERMS", {"Hello world": {"de": " Hallo\u00a0Welt "}})
    environment = Environment(
        loader=i18n.TranslateLoader(
            DictLoader(
                {"page": "{% translate %}\n  Hello\u00a0\tworld\n{% endtranslate %}"}
            )
        )
    )

    rendered = environment.get_template("page").render(
        {"_uproot_internal": {"language": "de"}}
    )

    assert rendered == " Hallo\u00a0Welt "
