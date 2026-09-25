import sys
from pathlib import Path

import pytest

from uproot import defaultcli, i18ncheck


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

    assert i18ncheck.find_python_translate_calls(str(source)) == [
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

    assert i18ncheck.find_python_translate_calls(str(source)) == [
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

    assert i18ncheck.find_underscore_calls(str(source)) == [
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

    assert i18ncheck.check_project(str(project)) == 0
    assert "fr: all 2 translation key uses found." in capsys.readouterr().out


def test_check_project_reports_near_misses(tmp_path: Path, capsys):
    project = write_project(tmp_path, '{% translate %}Click "Next".{% endtranslate %}')

    assert i18ncheck.check_project(str(project)) == 1

    out = capsys.readouterr().out
    assert "myapp/Page.html:1" in out
    assert "Differs only in quotes or spacing from: 'Click “Next”.'" in out


def test_check_project_rejects_invalid_locale(tmp_path: Path, capsys):
    project = write_project(tmp_path, "")
    (project / "myapp" / "fr.yml").write_text("[broken", encoding="utf-8")

    assert i18ncheck.check_project(str(project)) == 2
    assert "Could not read" in capsys.readouterr().out


def test_check_project_ignores_unrelated_yaml(tmp_path: Path):
    project = write_project(tmp_path, "")
    (project / "config.yml").write_text("[not-strictyaml", encoding="utf-8")

    assert i18ncheck.check_project(str(project)) == 0


def test_builtin_field_text_is_translated(tmp_path: Path, capsys):
    project = write_project(tmp_path, "")
    (project / "myapp" / "Page.py").write_text(
        'answer = StringField(label="Next")\n', encoding="utf-8"
    )

    assert i18ncheck.check_project(str(project)) == 0
    assert "no translation in any language" not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("page", "code"),
    [
        ("{% translate %}Click “Next”.{% endtranslate %}", 0),
        ('{% translate %}Click "Next".{% endtranslate %}', 1),
    ],
)
def test_check_translations_command(tmp_path: Path, monkeypatch, page, code):
    project = write_project(tmp_path, page)
    monkeypatch.setattr(sys, "argv", ["uproot", "check-translations", str(project)])

    with pytest.raises(SystemExit) as exit_info:
        defaultcli.main()

    assert exit_info.value.code == code


def test_check_translations_command_rejects_missing_directory(
    tmp_path: Path, monkeypatch, capsys
):
    missing = tmp_path / "missing"
    monkeypatch.setattr(sys, "argv", ["uproot", "check-translations", str(missing)])

    with pytest.raises(SystemExit) as exit_info:
        defaultcli.main()

    assert exit_info.value.code == 2
    assert "is not a directory" in capsys.readouterr().out


def test_find_field_texts(tmp_path: Path):
    source = tmp_path / "example.py"
    source.write_text(
        "\n".join(  # noqa: FLY002
            [
                "rain = RadioField(",
                '    label="Is it raining?",',
                '    choices=[(True, "Yes"), (False, "No")],',
                '    description="Look outside.",',
                ")",
                'team = wtforms.SelectField(choices=["Red", "Blue"], label=name)',
                'plain = StringField(render_kw={"placeholder": "Not translated"})',
                'grouped = wtforms.SelectField(choices={"Team": [("a", "Alpha")]})',
            ]
        ),
        encoding="utf-8",
    )

    assert sorted(i18ncheck.find_field_texts(str(source))) == [
        ("Alpha", 8),
        ("Blue", 6),
        ("Is it raining?", 2),
        ("Look outside.", 4),
        ("No", 3),
        ("Red", 6),
        ("Team", 8),
        ("Yes", 3),
    ]


def write_field_project(tmp_path: Path, german: str) -> Path:
    app = tmp_path / "myapp"
    app.mkdir()
    (app / "__init__.py").write_text(
        'rain = RadioField(label="Is it raining?", choices=["Deutsch"])\n'
        'sun = RadioField(label="Is it sunny?")\n',
        encoding="utf-8",
    )
    (app / "de.yml").write_text(german, encoding="utf-8")
    (app / "fr.yml").write_text(
        "? 'Is it raining?'\n: 'Pleut-il ?'\n", encoding="utf-8"
    )
    return tmp_path


def test_check_project_reports_partly_translated_field_texts(tmp_path: Path, capsys):
    project = write_field_project(tmp_path, "? 'Welcome'\n: 'Willkommen'\n")

    assert i18ncheck.check_project(str(project)) == 1

    out = capsys.readouterr().out
    assert "de: 1 translation key use(s) not found" in out
    assert "'Is it raining?'" in out


def test_check_project_lists_untranslated_field_texts_on_request(
    tmp_path: Path, capsys
):
    project = write_field_project(tmp_path, "? 'Is it raining?'\n: 'Regnet es?'\n")

    assert i18ncheck.check_project(str(project)) == 0
    out = capsys.readouterr().out
    assert "2 form field text(s) have no translation" in out
    assert "'Deutsch'" not in out

    assert i18ncheck.check_project(str(project), list_untranslated=True) == 0
    out = capsys.readouterr().out
    assert "  'Deutsch'" in out
    assert "  'Is it sunny?'" in out
