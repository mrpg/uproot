import wtforms

from uproot.fields import EmailField, FloatField, FloatRangeField, SelectField
from uproot.pages import ENV


class FormData(dict):
    def getlist(self, key):
        if key not in self:
            return []
        return [self[key]]


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


async def render_select_options(form):
    template = ENV.from_string(
        '{% from "Macros.html" import field with context %}'
        "{{ field(form.study) }}{{ field(form.color) }}"
    )
    html = await template.render_async(form=form, _=lambda text: text)

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
