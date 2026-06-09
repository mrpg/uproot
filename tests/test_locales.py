from pathlib import Path

import strictyaml


def test_default_locale_files_parse_as_string_mappings():
    schema = strictyaml.MapPattern(strictyaml.Str(), strictyaml.Str())
    locale_dir = Path("src/uproot/default/locales")
    locale_paths = sorted(locale_dir.glob("*.yml"))

    assert locale_paths

    entries_by_language = {}
    for path in locale_paths:
        data = strictyaml.load(path.read_text(encoding="utf-8"), schema).data

        assert data

        entries_by_language[path.stem] = data

    reference_language, reference_data = next(iter(entries_by_language.items()))
    reference_length = len(reference_data)
    reference_terms = set(reference_data)
    for language, data in entries_by_language.items():
        terms = set(data)

        assert len(data) == reference_length, (
            language,
            len(data),
            reference_language,
            reference_length,
        )
        assert terms == reference_terms, (
            language,
            "missing",
            sorted(reference_terms - terms),
            "extra",
            sorted(terms - reference_terms),
        )
