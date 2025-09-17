# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from typing import Any, Optional

import wtforms
import wtforms.fields
import wtforms.validators


class BooleanField(wtforms.fields.BooleanField):
    def __init__(self, label: str = "", **kwargs: Any) -> None:
        super().__init__(
            label=label,
            **kwargs,
        )


class DateField(wtforms.fields.DateField):
    def __init__(self, label: str = "", optional: bool = False, **kwargs: Any) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class DecimalField(wtforms.fields.DecimalField):
    def __init__(
        self,
        label: str = "",
        min: Optional[float] = None,
        max: Optional[float] = None,
        optional: bool = False,
        **kwargs: Any,
    ) -> None:
        if not optional:
            v = [
                wtforms.validators.InputRequired(),
                wtforms.validators.NumberRange(min=min, max=max),
            ]
        else:
            v = [
                wtforms.validators.Optional(),
                wtforms.validators.NumberRange(min=min, max=max),
            ]

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class DecimalRangeField(wtforms.fields.DecimalRangeField):
    def __init__(
        self,
        label: str = "",
        min: Optional[float] = None,
        max: Optional[float] = None,
        step: float = 1.0,
        optional: bool = False,
        anchoring: bool = True,
        **kwargs: Any,
    ) -> None:
        if not optional:
            v = [
                wtforms.validators.InputRequired(),
                wtforms.validators.NumberRange(min=min, max=max),
            ]
        else:
            v = [
                wtforms.validators.Optional(),
                wtforms.validators.NumberRange(min=min, max=max),
            ]

        if step is not None:
            kwargs.setdefault("render_kw", {})["step"] = step

        self.anchoring = anchoring

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class EmailField(wtforms.fields.EmailField):
    def __init__(self, label: str = "", optional: bool = False, **kwargs: Any) -> None:
        if not optional:
            v = [
                wtforms.validators.InputRequired(),
                wtforms.validators.Email(),
            ]
        else:
            v = [
                wtforms.validators.Optional(),
                wtforms.validators.Email(),
            ]

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class FileField(wtforms.fields.FileField):
    def __init__(self, label: str = "", optional: bool = False, **kwargs: Any) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class IntegerField(wtforms.fields.IntegerField):
    def __init__(
        self,
        label: str = "",
        min: Optional[float] = None,
        max: Optional[float] = None,
        optional: bool = False,
        **kwargs: Any,
    ) -> None:
        if not optional:
            v = [
                wtforms.validators.InputRequired(),
                wtforms.validators.NumberRange(min=min, max=max),
            ]
        else:
            v = [
                wtforms.validators.Optional(),
                wtforms.validators.NumberRange(min=min, max=max),
            ]

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class LikertField(wtforms.fields.RadioField):
    def __init__(
        self,
        label: str = "",
        min: int = 1,
        max: int = 7,
        label_min: str = "",
        label_max: str = "",
        optional: bool = False,
        **kwargs: Any,
    ) -> None:
        choices = [(i, str(i)) for i in range(min, max + 1)]
        if not optional:
            v = [
                wtforms.validators.InputRequired(),
                wtforms.validators.NumberRange(min=min, max=max),
            ]
        else:
            v = [
                wtforms.validators.Optional(),
                wtforms.validators.NumberRange(min=min, max=max),
            ]

        self.min = min
        self.max = max
        self.label_min = label_min
        self.label_max = label_max

        super().__init__(
            label=label,
            choices=choices,
            validators=v,
            **kwargs,
        )


class RadioField(wtforms.fields.RadioField):
    def __init__(
        self,
        label: str = "",
        layout: str = "vertical",
        optional: bool = False,
        **kwargs: Any,
    ) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        if layout != "vertical":
            kwargs.setdefault("render_kw", {})
            if "class" in kwargs["render_kw"]:
                kwargs["render_kw"]["class"] += " form-check-inline"
            else:
                kwargs["render_kw"]["class"] = "form-check-inline"

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class SelectField(wtforms.fields.SelectField):
    def __init__(self, label: str = "", optional: bool = False, **kwargs: Any) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class StringField(wtforms.fields.StringField):
    def __init__(self, label: str = "", optional: bool = False, **kwargs: Any) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class TextAreaField(wtforms.fields.TextAreaField):
    def __init__(self, label: str = "", optional: bool = False, **kwargs: Any) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )


class IBANValidator:
    def __init__(self, message: Optional[str] = None) -> None:
        self.message = message or "Invalid IBAN format."

    def __call__(self, form: wtforms.Form, field: wtforms.Field) -> None:
        from schwifty import IBAN
        from schwifty.exceptions import SchwiftyException

        if field.data:
            try:
                IBAN(field.data)
            except SchwiftyException:
                raise wtforms.validators.ValidationError(self.message)


class IBANField(wtforms.fields.StringField):
    def __init__(self, label: str = "", optional: bool = False, **kwargs: Any) -> None:
        if not optional:
            v = [
                wtforms.validators.InputRequired(),
                IBANValidator(),
            ]
        else:
            v = [
                wtforms.validators.Optional(),
                IBANValidator(),
            ]

        super().__init__(
            label=label,
            validators=v,
            **kwargs,
        )
