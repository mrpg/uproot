# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from decimal import Decimal
from typing import Any, Callable

import wtforms
import wtforms.fields
import wtforms.validators

Number = int | float | Decimal


def type_coercer(choices: list[tuple[Any, str] | Any]) -> Callable[[str], Any]:
    def local_coerce(chosen: str) -> Any:
        for choice in choices:
            if isinstance(choice, tuple) and len(choice) == 2:
                coded_as, _ = choice
            else:
                coded_as = choice

            submission = str(coded_as)

            if chosen == submission or chosen == coded_as:
                return coded_as

        raise ValueError("Invalid choice")

    return local_coerce


class BooleanField(wtforms.fields.BooleanField):
    def __init__(
        self,
        *,
        class_wrapper: str | None = None,
        label: str = "",
        validators: list[Any] | None = None,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        self.class_wrapper = class_wrapper

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            validators=validators,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class DateField(wtforms.fields.DateField):
    def __init__(
        self,
        *,
        class_wrapper: str | None = None,
        label: str = "",
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        self.class_wrapper = class_wrapper

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            validators=v,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class DecimalField(wtforms.fields.DecimalField):
    def __init__(
        self,
        *,
        addon_start: str | None = None,
        addon_end: str | None = None,
        class_addon_start: str = "",
        class_addon_end: str = "",
        class_wrapper: str | None = None,
        label: str = "",
        min: Number | None = None,
        max: Number | None = None,
        step: Number | None = None,
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
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

        self.addon_start = addon_start
        self.addon_end = addon_end
        self.class_addon_start = class_addon_start
        self.class_addon_end = class_addon_end
        self.class_wrapper = class_wrapper

        if render_kw is None:
            render_kw = {}
        if step is not None:
            render_kw["step"] = step
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            validators=v,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class DecimalRangeField(wtforms.fields.DecimalRangeField):
    def __init__(
        self,
        *,
        class_wrapper: str | None = None,
        hide_popover: bool = False,
        label: str = "",
        label_min: str | None = None,
        label_max: str | None = None,
        min: Number | None = None,
        max: Number | None = None,
        step: Number = 1.0,
        optional: bool = False,
        anchoring: bool = True,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
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

        if label_min is None:
            label_min = str(min)
        if label_max is None:
            label_max = str(max)
        if render_kw is None:
            render_kw = {}
        if step is not None:
            render_kw["step"] = step
        render_kw["autocomplete"] = "off"

        self.anchoring = anchoring
        self.class_wrapper = class_wrapper
        self.hide_popover = hide_popover
        self.label_min = label_min
        self.label_max = label_max

        super().__init__(
            label=label,
            validators=v,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class EmailField(wtforms.fields.EmailField):
    def __init__(
        self,
        *,
        class_wrapper: str | None = None,
        label: str = "",
        label_floating: str | None = None,
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if not optional:
            v = [
                wtforms.validators.InputRequired(),
                # This requires email_validator to be installed:
                # wtforms.validators.Email(),
            ]
        else:
            v = [
                wtforms.validators.Optional(),
                # This requires email_validator to be installed:
                # wtforms.validators.Email(),
            ]

        self.class_wrapper = class_wrapper
        self.label_floating = label_floating

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            validators=v,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class FileField(wtforms.fields.FileField):
    def __init__(
        self,
        *,
        class_wrapper: str | None = None,
        label: str = "",
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        self.class_wrapper = class_wrapper

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            validators=v,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class IntegerField(wtforms.fields.IntegerField):
    def __init__(
        self,
        *,
        addon_start: str | None = None,
        addon_end: str | None = None,
        class_addon_start: str = "",
        class_addon_end: str = "",
        class_wrapper: str | None = None,
        label: str = "",
        min: Number | None = None,
        max: Number | None = None,
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
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

        self.addon_start = addon_start
        self.addon_end = addon_end
        self.class_addon_start = class_addon_start
        self.class_addon_end = class_addon_end
        self.class_wrapper = class_wrapper

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            validators=v,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class LikertField(wtforms.fields.RadioField):
    def __init__(
        self,
        *,
        class_wrapper: str | None = None,
        label: str = "",
        label_max: str = "",
        label_min: str = "",
        max: int = 7,
        min: int = 1,
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
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

        self.class_wrapper = class_wrapper
        self.label_max = label_max
        self.label_min = label_min
        self.max = max
        self.min = min

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            choices=choices,
            validators=v,
            coerce=type_coercer(choices),
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class RadioField(wtforms.fields.RadioField):
    def __init__(
        self,
        *,
        choices: list[tuple[Any, str] | Any] | dict[Any, str] | None = None,
        class_wrapper: str | None = None,
        label: str = "",
        layout: str = "vertical",
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if choices is None:
            choices = [True, False]
        elif isinstance(choices, dict):
            choices = [*choices.items()]

        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        if render_kw is None:
            render_kw = {}
        if layout != "vertical":
            if "class" in render_kw:
                render_kw["class"] += " form-check-inline"
            else:
                render_kw["class"] = "form-check-inline"
        render_kw["autocomplete"] = "off"

        self.class_wrapper = class_wrapper

        super().__init__(
            choices=choices,
            label=label,
            validators=v,
            coerce=type_coercer(choices),
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class SelectField(wtforms.fields.SelectField):
    def __init__(
        self,
        *,
        choices: list[tuple[Any, str] | Any] | dict[Any, str],
        class_wrapper: str | None = None,
        label: str = "",
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if isinstance(choices, dict):
            choices = [*choices.items()]

        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        self.class_wrapper = class_wrapper

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            choices=choices,
            label=label,
            validators=v,
            coerce=type_coercer(choices),
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class StringField(wtforms.fields.StringField):
    def __init__(
        self,
        *,
        addon_start: str | None = None,
        addon_end: str | None = None,
        class_addon_start: str = "",
        class_addon_end: str = "",
        class_wrapper: str | None = None,
        label: str = "",
        label_floating: str | None = None,
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        self.addon_start = addon_start
        self.addon_end = addon_end
        self.class_addon_start = class_addon_start
        self.class_addon_end = class_addon_end
        self.class_wrapper = class_wrapper
        self.label_floating = label_floating

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            validators=v,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class TextAreaField(wtforms.fields.TextAreaField):
    def __init__(
        self,
        *,
        addon_start: str | None = None,
        addon_end: str | None = None,
        class_addon_start: str = "",
        class_addon_end: str = "",
        class_wrapper: str | None = None,
        label: str = "",
        label_floating: str | None = None,
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

        self.addon_start = addon_start
        self.addon_end = addon_end
        self.class_addon_start = class_addon_start
        self.class_addon_end = class_addon_end
        self.class_wrapper = class_wrapper
        self.label_floating = label_floating

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            validators=v,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )


class BoundedChoiceValidator:
    def __init__(self, min: int, max: int | None) -> None:
        self.min = min
        self.max = max

    def __call__(self, form: wtforms.Form, field: wtforms.Field) -> None:
        count = len(field.data) if field.data else 0

        if count < self.min:
            if self.min == 1:
                raise wtforms.validators.ValidationError(
                    "Please select at least one option."
                )
            else:
                raise wtforms.validators.ValidationError(
                    f"Please select at least {self.min} options."
                )

        if self.max is not None and count > self.max:
            if self.max == 1:
                raise wtforms.validators.ValidationError(
                    "Please select at most one option."
                )
            else:
                raise wtforms.validators.ValidationError(
                    f"Please select at most {self.max} options."
                )


class BoundedChoiceField(wtforms.fields.SelectMultipleField):
    def __init__(
        self,
        *,
        choices: list[tuple[Any, str] | Any] | dict[Any, str],
        class_wrapper: str | None = None,
        label: str = "",
        layout: str = "vertical",
        min: int = 0,
        max: int | None = None,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if isinstance(choices, dict):
            choices = [*choices.items()]

        v = [BoundedChoiceValidator(min=min, max=max)]

        if render_kw is None:
            render_kw = {}
        if layout != "vertical":
            if "class" in render_kw:
                render_kw["class"] += " form-check-inline"
            else:
                render_kw["class"] = "form-check-inline"
        render_kw["autocomplete"] = "off"

        self.class_wrapper = class_wrapper
        self.bounded_min = min
        self.bounded_max = max

        super().__init__(
            choices=choices,
            label=label,
            validators=v,
            coerce=type_coercer(choices),
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default if default is not None else [],
            **kwargs,  # Unpacks WTForms-internal kwargs
        )

    def process_formdata(self, valuelist: list[Any]) -> None:
        # Filter out empty strings from hidden input placeholder
        valuelist = [v for v in valuelist if v != ""]
        super().process_formdata(valuelist)

        # Ensure data is always a list
        if self.data is None:  # type: ignore[has-type]
            self.data = []  # type: ignore[var-annotated]


class IBANValidator:
    def __init__(self, message: str | None = None) -> None:
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
    def __init__(
        self,
        *,
        addon_start: str | None = None,
        addon_end: str | None = None,
        class_addon_start: str = "",
        class_addon_end: str = "",
        class_wrapper: str | None = None,
        label: str = "",
        label_floating: str | None = None,
        optional: bool = False,
        render_kw: dict[str, Any] | None = None,
        description: str = "",
        widget: Any | None = None,
        default: Any | None = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
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

        self.addon_start = addon_start
        self.addon_end = addon_end
        self.class_addon_start = class_addon_start
        self.class_addon_end = class_addon_end
        self.class_wrapper = class_wrapper
        self.label_floating = label_floating

        if render_kw is None:
            render_kw = {}
        render_kw["autocomplete"] = "off"

        super().__init__(
            label=label,
            validators=v,
            render_kw=render_kw,
            description=description,
            widget=widget,
            default=default,
            **kwargs,  # Unpacks WTForms-internal kwargs
        )
