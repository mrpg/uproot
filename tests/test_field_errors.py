import pytest
from jinja2 import ChoiceLoader, DictLoader
from starlette.datastructures import FormData
from starlette.requests import Request

import uproot as u
from uproot import pages
from uproot.fields import RadioField
from uproot.types import Page


class Question(Page):
    @classmethod
    def fields(page, player):
        return {"answer": RadioField(choices=[("a", "A"), ("b", "B")])}

    @classmethod
    def validate(page, player, data):
        return {"answer": "Not quite."}


class Typo(Question):
    @classmethod
    def validate(page, player, data):
        return {"answsr": "Not quite."}


@pytest.fixture(autouse=True)
def no_apps(monkeypatch):
    monkeypatch.setattr(u, "APPS", {}, raising=False)


@pytest.fixture
def question_template(monkeypatch):
    monkeypatch.setattr(
        pages.ENV,
        "loader",
        ChoiceLoader(
            [
                DictLoader(
                    {
                        f"{__name__}/Question.html": (
                            '{% extends "Base.html" %}'
                            "{% block main %}{{ fields() }}{% endblock main %}"
                        ),
                    }
                ),
                pages.ENV.loader,
            ]
        ),
    )


async def test_errors_from_validate_are_shown_with_their_field(question_template):
    formdata = FormData({"answer": "a"})
    valid, errors, field_errors = (await pages.validate(Question, None, formdata))[1:]

    assert not valid
    assert field_errors == {"answer": ["Not quite."]}

    request = Request({"type": "http", "path": "/", "headers": []})
    html = await pages.render(
        None, request, None, Question, formdata, errors, None, None, field_errors
    )

    assert "Not quite." in html
    assert "uproot-error" in html


async def test_errors_for_unknown_fields_are_rejected():
    with pytest.raises(KeyError, match="answsr"):
        await pages.validate(Typo, None, FormData({"answer": "a"}))
