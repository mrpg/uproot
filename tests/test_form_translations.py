from types import SimpleNamespace

import wtforms

import uproot as u
from uproot.fields import BoundedChoiceField, EmailField, IntegerField
from uproot.pages import FormTranslations, form_factory
from uproot.types import Page


class FormData(dict):
    def getlist(self, key):
        if key not in self:
            return []
        value = self[key]
        return value if isinstance(value, list) else [value]


def form_in(language, **fields):
    translations = FormTranslations(language)

    class Meta:
        def get_translations(self, form):
            return translations

    return type("TranslatedForm", (wtforms.Form,), fields | {"Meta": Meta})


def test_wtforms_messages_are_translated():
    Form = form_in("fr", age=IntegerField(min=10, max=120))
    form = Form(formdata=FormData({"age": ""}))

    assert form.validate() is False
    assert form.age.errors == ["Ce champ est requis."]


def test_uproot_messages_are_translated():
    Form = form_in("de", email=EmailField())
    form = Form(formdata=FormData({"email": "not-an-email"}))

    assert form.validate() is False
    assert form.email.errors == ["Ungültige E-Mail-Adresse."]


def test_uproot_plural_messages_are_translated():
    Form = form_in(
        "fr",
        teams=BoundedChoiceField(choices=["a", "b", "c"], min=2),
    )
    form = Form(formdata=FormData({"teams": ["a"]}))

    assert form.validate() is False
    assert form.teams.errors == ["Veuillez sélectionner au moins 2 options."]


def test_unknown_language_falls_back_to_english():
    Form = form_in("cmn", email=EmailField())
    form = Form(formdata=FormData({"email": ""}))

    assert form.validate() is False
    assert form.email.errors == ["This field is required."]


async def test_form_factory_uses_app_language(monkeypatch):
    class Survey(Page):
        @classmethod
        def fields(page, player):
            return {"age": IntegerField(min=10, max=120)}

    app = SimpleNamespace(language=lambda player: "ja")
    monkeypatch.setattr(u, "APPS", {Survey.__module__: app}, raising=False)

    Form = await form_factory(Survey, None)
    form = Form(formdata=FormData({"age": "5"}))

    assert form.validate() is False
    assert form.age.errors == ["数値は 10 以上, 120 以下でなければいけません。"]
