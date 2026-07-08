import wtforms

from uproot.fields import EmailField


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
