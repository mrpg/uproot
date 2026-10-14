import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def repository_checker(tmp_path: Path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "check_translations.py"
    spec = importlib.util.spec_from_file_location("repository_translations", path)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    locales = tmp_path / "locales"
    locales.mkdir()
    monkeypatch.setattr(checker, "SRC_DIR", str(tmp_path))
    monkeypatch.setattr(checker, "LOCALES_DIR", str(locales))
    monkeypatch.setattr(checker, "EN_YML", str(locales / "en.yml"))
    monkeypatch.setattr(sys, "argv", ["check_translations.py"])
    return checker


def test_repository_checker_counts_normalized_catalog_keys(
    repository_checker, tmp_path: Path, capsys
):
    Path(repository_checker.EN_YML).write_text(
        "? 'Hello world'\n: 'Hello\u00a0world'\n" "? 'Block text'\n: 'Block text'\n",
        encoding="utf-8",
    )
    (tmp_path / "page.js").write_text(
        '_(" Hello\u00a0world "); _(`Hello\n  world`);', encoding="utf-8"
    )
    (tmp_path / "page.py").write_text('translate("Hello\\tworld")', encoding="utf-8")
    (tmp_path / "page.html").write_text(
        "{% translate %}\n  Block\ttext\n{% endtranslate %}", encoding="utf-8"
    )

    assert repository_checker.main() == 0
    out = capsys.readouterr().out
    assert "All translation keys found in en.yml." in out
    assert "No superfluous keys in en.yml." in out


def test_repository_fix_preserves_exact_keys_and_values(
    repository_checker, tmp_path: Path, monkeypatch
):
    Path(repository_checker.EN_YML).write_text(
        "? ' and '\n: ' & '\n"
        "? 'and'\n: 'unused'\n"
        "? 'white space'\n: 'unused'\n"
        "? 'white  space'\n: ' nonbreaking\u00a0value '\n",
        encoding="utf-8",
    )
    (tmp_path / "page.js").write_text(
        '_(" and "); _(`white  space`);', encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["check_translations.py", "--fix"])

    assert repository_checker.main() == 1
    assert repository_checker.read_yml_entries(repository_checker.EN_YML) == [
        (" and ", " & "),
        ("white  space", " nonbreaking\u00a0value "),
    ]
    assert repository_checker.main() == 0


def test_repository_fix_writes_keys_that_read_back_exactly(
    repository_checker, tmp_path: Path, monkeypatch
):
    Path(repository_checker.EN_YML).write_text("? 'x'\n: 'x'\n", encoding="utf-8")
    (tmp_path / "page.js").write_text(
        '_(`a\n  b`); _("a b"); _(`It\'s\n "here" \\\\`);', encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["check_translations.py", "--fix"])

    assert repository_checker.main() == 1
    assert repository_checker.read_yml_entries(repository_checker.EN_YML) == [
        ('It\'s\n "here" \\\\', 'It\'s\n "here" \\\\'),
        ("a\n  b", "a\n  b"),
        ("a b", "a b"),
    ]
    assert repository_checker.main() == 0


def test_repository_yaml_quote_escapes_characters_yaml_would_change(
    repository_checker,
):
    characters = [chr(c) for c in [*range(0x20), *range(0x7F, 0xA0), 0xFFFE, 0xFFFF]]
    entries = [(f"{c}a {c} b{c}", "value") for c in characters]
    repository_checker.write_yml(repository_checker.EN_YML, entries)

    assert repository_checker.read_yml_entries(repository_checker.EN_YML) == entries
