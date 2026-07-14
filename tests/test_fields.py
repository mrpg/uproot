import wtforms

from uproot.fields import EmailField, FloatField, FloatRangeField


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
