# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from typing import Any, Callable, Optional

import wtforms
import wtforms.fields
import wtforms.validators


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
        class_wrapper: Optional[str] = None,
        label: str = "",
        validators: Optional[list[Any]] = None,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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
        class_wrapper: Optional[str] = None,
        label: str = "",
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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
        class_wrapper: Optional[str] = None,
        label: str = "",
        min: Optional[float] = None,
        max: Optional[float] = None,
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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


class DecimalRangeField(wtforms.fields.DecimalRangeField):
    def __init__(
        self,
        *,
        class_wrapper: Optional[str] = None,
        label: str = "",
        min: Optional[float] = None,
        max: Optional[float] = None,
        step: float = 1.0,
        optional: bool = False,
        anchoring: bool = True,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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

        if render_kw is None:
            render_kw = {}
        if step is not None:
            render_kw["step"] = step
        render_kw["autocomplete"] = "off"

        self.anchoring = anchoring
        self.class_wrapper = class_wrapper

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
        class_wrapper: Optional[str] = None,
        label: str = "",
        label_floating: Optional[str] = None,
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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
        class_wrapper: Optional[str] = None,
        label: str = "",
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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
        class_wrapper: Optional[str] = None,
        label: str = "",
        min: Optional[float] = None,
        max: Optional[float] = None,
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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
        class_wrapper: Optional[str] = None,
        label: str = "",
        label_max: str = "",
        label_min: str = "",
        max: int = 7,
        min: int = 1,
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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
        choices: Optional[list[tuple[Any, str] | Any] | dict[Any, str]] = None,
        class_wrapper: Optional[str] = None,
        label: str = "",
        layout: str = "vertical",
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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
        class_wrapper: Optional[str] = None,
        label: str = "",
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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
        class_wrapper: Optional[str] = None,
        label: str = "",
        label_floating: Optional[str] = None,
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

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
        class_wrapper: Optional[str] = None,
        label: str = "",
        label_floating: Optional[str] = None,
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
        **kwargs: Any,  # WTForms-internal use only
    ) -> None:
        if not optional:
            v = [wtforms.validators.InputRequired()]
        else:
            v = [wtforms.validators.Optional()]

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
    def __init__(
        self,
        *,
        class_wrapper: Optional[str] = None,
        label: str = "",
        label_floating: Optional[str] = None,
        optional: bool = False,
        render_kw: Optional[dict[str, Any]] = None,
        description: str = "",
        widget: Optional[Any] = None,
        default: Optional[Any] = None,
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
