from pathlib import Path

import check_translations


def test_find_python_translate_calls_finds_literal_keys(tmp_path: Path):
    source = tmp_path / "example.py"
    source.write_text(
        "\n".join(
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
