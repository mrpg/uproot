from datetime import date
from decimal import Decimal

import pytest
import wtforms
from starlette.datastructures import FormData

from uproot import fields
from uproot.fields import EmailField, FloatField, FloatRangeField, SelectField
from uproot.pages import ENV


@pytest.mark.parametrize(
    "field_type, submitted, expected, widget",
    [
        (fields.DateField, "2026-10-17", date(2026, 10, 17), 'type="date"'),
        (fields.FileField, "upload.csv", "upload.csv", 'type="file"'),
        (fields.DecimalField, "3.14", Decimal("3.14"), 'type="number"'),
        (fields.FloatField, "3.14", 3.14, 'type="number"'),
        (fields.DecimalRangeField, "3.14", Decimal("3.14"), 'type="range"'),
        (fields.FloatRangeField, "3.14", 3.14, 'type="range"'),
        (fields.StringField, "hello", "hello", 'type="text"'),
        (fields.TextAreaField, "hello\nworld", "hello\nworld", "<textarea"),
    ],
)
def test_shared_field_initializers_preserve_behavior(
    field_type, submitted, expected, widget
):
    class Form(wtforms.Form):
        value = field_type(
            label="Value",
            description="Description",
            class_wrapper="wrapper",
            render_kw={"title": "hint"},
        )

    form = Form(formdata=FormData({"value": submitted}))

    assert form.validate()
    assert type(form.value.data) is type(expected)
    assert form.value.data == expected
    assert form.value.label.text == "Value"
    assert form.value.description == "Description"
    assert form.value.class_wrapper == "wrapper"
    html = form.value()
    assert widget in html
    assert 'autocomplete="off"' in html
    assert 'title="hint"' in html

    assert not Form(formdata=FormData({"value": ""})).validate()

    class OptionalForm(wtforms.Form):
        value = field_type(optional=True)

    assert OptionalForm(formdata=FormData({"value": ""})).validate()


def test_email_field_rejects_invalid_email():
    class EmailForm(wtforms.Form):
        email = EmailField()

    form = EmailForm(formdata=FormData({"email": "not-an-email"}))

    assert form.validate() is False
    assert form.email.errors == ["Invalid email address."]


def test_email_field_accepts_valid_email():
    class EmailForm(wtforms.Form):
        email = EmailField()

    form = EmailForm(formdata=FormData({"email": "user@example.com"}))

    assert form.validate() is True


def test_optional_email_field_allows_empty_value():
    class EmailForm(wtforms.Form):
        email = EmailField(optional=True)

    form = EmailForm(formdata=FormData({"email": ""}))

    assert form.validate() is True


def test_float_field_stores_float():
    class FloatForm(wtforms.Form):
        value = FloatField()

    form = FloatForm(formdata=FormData({"value": "3.14"}))

    assert form.validate() is True
    assert type(form.value.data) is float
    assert form.value.data == 3.14


def test_float_field_renders_as_number_input():
    class FloatForm(wtforms.Form):
        value = FloatField(min=0.0, max=10.0, step=0.5)

    form = FloatForm()
    html = form.value()

    assert 'type="number"' in html
    assert 'min="0.0"' in html
    assert 'max="10.0"' in html
    assert 'step="0.5"' in html


def test_float_field_enforces_range():
    class FloatForm(wtforms.Form):
        value = FloatField(min=0.0, max=1.0)

    form = FloatForm(formdata=FormData({"value": "1.5"}))

    assert form.validate() is False


def test_float_field_rejects_non_numeric_input():
    class FloatForm(wtforms.Form):
        value = FloatField()

    form = FloatForm(formdata=FormData({"value": "abc"}))

    assert form.validate() is False


def test_optional_float_field_allows_empty_value():
    class FloatForm(wtforms.Form):
        value = FloatField(optional=True)

    form = FloatForm(formdata=FormData({"value": ""}))

    assert form.validate() is True
    assert form.value.data is None


def test_float_range_field_stores_float():
    class FloatForm(wtforms.Form):
        value = FloatRangeField(min=0.0, max=10.0, step=0.5)

    form = FloatForm(formdata=FormData({"value": "7.5"}))

    assert form.validate() is True
    assert type(form.value.data) is float
    assert form.value.data == 7.5


def test_float_range_field_renders_as_range_input():
    class FloatForm(wtforms.Form):
        value = FloatRangeField(min=0.0, max=10.0, step=0.5)

    form = FloatForm()
    html = form.value()

    assert 'type="range"' in html
    assert 'step="0.5"' in html


def test_float_range_field_enforces_range():
    class FloatForm(wtforms.Form):
        value = FloatRangeField(min=0.0, max=10.0)

    form = FloatForm(formdata=FormData({"value": "10.5"}))

    assert form.validate() is False


class SelectForm(wtforms.Form):
    study = SelectField(choices=[("eng", "Engineering"), ("law", "Law")])
    color = SelectField(choices=[("", "Pick one"), ("red", "Red")], optional=True)


async def render_fields(form, translate=str):
    template = ENV.from_string(
        '{% from "Macros.html" import field with context %}'
        "{% for form_field in form %}{{ field(form_field) }}{% endfor %}"
    )
    return await template.render_async({"form": form, "_": translate})


async def render_select_options(form):
    html = await render_fields(form)

    return [line.strip() for line in html.splitlines() if "<option" in line]


async def test_select_field_renders_selected_placeholder_first():
    options = await render_select_options(SelectForm())

    assert options[:3] == [
        '<option value="" selected>—</option>',
        '<option value="eng">Engineering</option>',
        '<option value="law">Law</option>',
    ]


async def test_select_field_keeps_submitted_choice_selected():
    form = SelectForm(formdata=FormData({"study": "law", "color": "red"}))
    options = await render_select_options(form)

    assert options[0] == '<option value="">—</option>'
    assert '<option selected value="law">Law</option>' in options


async def test_select_field_without_placeholder_if_choices_have_empty_value():
    options = await render_select_options(SelectForm())

    assert options[3:] == [
        '<option value="">Pick one</option>',
        '<option value="red">Red</option>',
    ]


def test_select_field_placeholder_is_not_a_valid_answer():
    form = SelectForm(formdata=FormData({"study": ""}))

    assert form.validate() is False
    assert form.study.errors == ["This field is required."]


async def test_plain_wtforms_select_field_renders_without_placeholder():
    class PlainForm(wtforms.Form):
        team = wtforms.SelectField(
            choices=[wtforms.SelectChoice("a", "A"), wtforms.SelectChoice("b", "B")]
        )

    options = await render_select_options(PlainForm())

    assert options == ['<option value="a">A</option>', '<option value="b">B</option>']


@pytest.mark.parametrize(
    "field_type",
    [
        fields.RadioField,
        fields.SelectField,
        fields.BoundedChoiceField,
        fields.LikertField,
        fields.LikertFieldClassic,
    ],
)
@pytest.mark.parametrize(
    "choices, submitted, expected",
    [
        ([True, False], "False", False),
        ([-1, 0, 1], "0", 0),
        ([1.5, 2.5], "2.5", 2.5),
        ([Decimal("0.50"), Decimal("1.00")], "0.50", Decimal("0.50")),
        (["red", "blue"], "blue", "blue"),
        ([(1, "One"), (2, "Two")], "2", 2),
        ({1: "One", 2: "Two"}, "2", 2),
        ([wtforms.SelectChoice(1, "One"), wtforms.SelectChoice(2, "Two")], "2", 2),
    ],
)
async def test_choice_fields_render_and_preserve_value_types(
    field_type, choices, submitted, expected
):
    class Form(wtforms.Form):
        value = field_type(choices=choices)

    assert f'value="{submitted}"' in await render_fields(Form())

    form = Form(formdata=FormData({"value": submitted}))
    assert form.validate()
    data = form.value.data
    if field_type is fields.BoundedChoiceField:
        assert len(data) == 1
        data = data[0]
    assert type(data) is type(expected)
    assert data == expected
    html = await render_fields(form)
    if field_type is fields.SelectField:
        assert f'selected value="{submitted}"' in html
    else:
        assert "checked" in html

    assert not Form(formdata=FormData({"value": "invalid"})).validate()


@pytest.mark.parametrize(
    "field_type, submitted, expected",
    [
        (fields.RadioField, "True", True),
        (fields.RadioField, "False", False),
        (fields.LikertField, "4", 4),
        (fields.LikertFieldClassic, "4", 4),
    ],
)
async def test_choice_fields_default_options(field_type, submitted, expected):
    class Form(wtforms.Form):
        value = field_type()

    form = Form(formdata=FormData({"value": submitted}))

    assert form.validate()
    assert type(form.value.data) is type(expected)
    assert form.value.data == expected
    assert "checked" in await render_fields(form)


def test_bounded_choice_field_validates_multiple_numeric_choices():
    class Form(wtforms.Form):
        value = fields.BoundedChoiceField(choices=[0, 1, 2], min=2, max=2)

    form = Form(formdata=FormData([("value", ""), ("value", "0"), ("value", "2")]))

    assert form.validate()
    assert form.value.data == [0, 2]
    assert not Form(formdata=FormData({"value": "1"})).validate()
    assert not Form(
        formdata=FormData([("value", "0"), ("value", "1"), ("value", "2")])
    ).validate()


@pytest.mark.parametrize("field_type", [fields.SelectField, wtforms.SelectField])
@pytest.mark.parametrize("grouped", [False, True])
async def test_select_field_translates_choices_and_groups(field_type, grouped):
    choices = [
        wtforms.SelectChoice("", "Pick one"),
        wtforms.SelectChoice(
            "a&b",
            "Alpha",
            {"data_hint": '"hint"'},
            optgroup="Group" if grouped else None,
        ),
        wtforms.SelectChoice("c", "Gamma", {"disabled": True}),
    ]

    class Form(wtforms.Form):
        value = field_type(choices=choices)

    translations = {
        "Pick one": "Choose",
        "Alpha": "Alpha <translated>",
        "Gamma": "Gamma & translated",
        "Group": "Group <translated>",
    }
    form = Form(formdata=FormData({"value": "a&b"}))
    html = await render_fields(form, lambda text: translations.get(text, text))
    options = [line.strip() for line in html.splitlines() if "<option" in line]

    assert form.validate()
    assert options == [
        '<option value="">Choose</option>',
        '<option data-hint="&#34;hint&#34;" selected value="a&amp;b">Alpha &lt;translated&gt;</option>',
        '<option disabled value="c">Gamma &amp; translated</option>',
    ]
    if grouped:
        assert html.count("<optgroup") == html.count("</optgroup>") == 1
        assert '<optgroup label="Group &lt;translated&gt;">' in html
        assert html.index("Choose</option>") < html.index("<optgroup")
        assert html.index("Alpha &lt;translated&gt;</option>") < html.index(
            "</optgroup>"
        )
        assert html.index("</optgroup>") < html.index("Gamma &amp; translated</option>")
    else:
        assert "<optgroup" not in html

    assert ">Alpha</option>" in await render_fields(form)
    assert choices[1].label == "Alpha"
