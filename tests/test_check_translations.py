from pathlib import Path

import check_translations


def test_find_python_translate_calls_finds_literal_keys(tmp_path: Path):
    source = tmp_path / "example.py"
    source.write_text(
        "\n".join(  # noqa: FLY002
            [
                'first = translate("First key")',
                "second = translate(",
                '    "Second key"',
                ")",
                "dynamic = translate(key)",
            ]
        ),
        encoding="utf-8",
    )

    assert check_translations.find_python_translate_calls(str(source)) == [
        ("First key", 1),
        ("Second key", 2),
    ]


def test_find_python_translate_calls_finds_gettext_keys(tmp_path: Path):
    source = tmp_path / "example.py"
    source.write_text(
        "\n".join(  # noqa: FLY002
            [
                'one = field.gettext("Singular key")',
                'two = field.ngettext("One thing", "#n# things", n)',
                "three = field.gettext(message)",
            ]
        ),
        encoding="utf-8",
    )

    assert check_translations.find_python_translate_calls(str(source)) == [
        ("Singular key", 1),
        ("One thing", 2),
        ("#n# things", 2),
    ]


def test_find_underscore_calls_normalizes_template_literals(tmp_path: Path):
    source = tmp_path / "example.js"
    source.write_text(
        'a = _("Plain key");\nb = _(`Multi\n    line key`);\nc = _(`Hi ${name}`);\n',
        encoding="utf-8",
    )

    assert check_translations.find_underscore_calls(str(source)) == [
        ("Plain key", 1),
        ("Multi line key", 2),
    ]


def write_project(tmp_path: Path, page: str) -> Path:
    app = tmp_path / "myapp"
    app.mkdir()
    (app / "Page.html").write_text(page, encoding="utf-8")
    (app / "fr.yml").write_text(
        "? 'Click “Next”.'\n: 'Cliquez sur « Suivant ».'\n", encoding="utf-8"
    )
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "Ignored.html").write_text(
        "{% translate %}Not checked{% endtranslate %}", encoding="utf-8"
    )
    return tmp_path


def test_check_project_accepts_project_and_builtin_keys(tmp_path: Path, capsys):
    project = write_project(
        tmp_path,
        "{% translate %}Click “Next”.{% endtranslate %}"
        "{% translate %}Please wait{% endtranslate %}",
    )

    assert check_translations.check_project(str(project)) == 0
    assert "fr: all 2 translation key uses found." in capsys.readouterr().out


def test_check_project_reports_near_misses(tmp_path: Path, capsys):
    project = write_project(tmp_path, '{% translate %}Click "Next".{% endtranslate %}')

    assert check_translations.check_project(str(project)) == 1

    out = capsys.readouterr().out
    assert "myapp/Page.html:1" in out
    assert "Differs only in quotes or spacing from: 'Click “Next”.'" in out
