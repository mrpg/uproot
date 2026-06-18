# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import builtins
import os
import re
import time
import traceback
import urllib.parse
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

import mistune
import orjson
from jinja2 import (
    BaseLoader,
    ChoiceLoader,
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    nodes,
)
from jinja2.ext import Extension
from jinja2.parser import Parser
from markupsafe import Markup
from pydantic import validate_call
from wtforms import Form as BaseForm
from wtforms.widgets.core import clean_key, html_params

import uproot as u
import uproot.admin as a
import uproot.deployment as d
import uproot.i18n as i18n
from uproot.constraints import ensure
from uproot.storage import Storage
from uproot.types import (
    InternalPage,
    Page,
    ensure_awaitable,
    materialize,
    optional_call,
)

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from starlette.datastructures import FormData

BUILTINS = {
    fname: getattr(builtins, fname)
    for fname in dir(builtins)
    if callable(getattr(builtins, fname))
}

H1_PATTERN = re.compile(r"<h1>(.*?)</h1>\s*", re.DOTALL)


class MarkdownLoader(BaseLoader):
    def __init__(self, base_loader: BaseLoader) -> None:
        self.base_loader = base_loader

    def get_source(
        self, environment: Environment, template: str
    ) -> tuple[str, str | None, Callable[[], bool] | None]:
        title_template = template.endswith(".md:title")
        source_template = (
            template.removesuffix(":title") if title_template else template
        )
        source, filename, uptodate = self.base_loader.get_source(
            environment, source_template
        )

        if source_template.endswith(".md"):
            html = cast(str, mistune.html(source))

            h1s = H1_PATTERN.findall(html)
            if title_template:
                return (
                    h1s[0].strip() if len(h1s) == 1 else "",
                    filename,
                    uptodate,
                )

            return (
                H1_PATTERN.sub("", html, count=1) if len(h1s) == 1 else html,
                filename,
                uptodate,
            )

        return source, filename, uptodate


class IncludeMarkdownExtension(Extension):
    tags = {"include_markdown"}

    def parse(self, parser: Parser) -> nodes.Node:
        lineno = next(parser.stream).lineno
        filename_node = parser.parse_expression()

        if isinstance(filename_node, nodes.Const) and "$Page" in filename_node.value:
            parts = filename_node.value.split("$Page")
            concat_parts: list[nodes.Expr] = []
            for i, part in enumerate(parts):
                if i > 0:
                    concat_parts.append(
                        nodes.Getattr(nodes.Name("page", "load"), "__module__", "load")
                    )
                    concat_parts.append(nodes.Const("/"))
                    concat_parts.append(
                        nodes.Getattr(nodes.Name("page", "load"), "__name__", "load")
                    )
                if part:
                    concat_parts.append(nodes.Const(part))

            template_expr: nodes.Expr = nodes.Concat(concat_parts)
        else:
            template_expr = filename_node

        return nodes.Include(template_expr, True, False).set_lineno(lineno)


ENV = Environment(
    loader=MarkdownLoader(
        i18n.TranslateLoader(
            ChoiceLoader(
                [
                    FileSystemLoader(d.PATH),
                    FileSystemLoader(
                        os.path.join(
                            os.path.dirname(os.path.abspath(__file__)), "default"
                        )
                    ),
                ]
            )
        )
    ),
    autoescape=True,
    undefined=StrictUndefined,
    cache_size=250,
    auto_reload=True,
    enable_async=True,
    lstrip_blocks=True,
    extensions=[IncludeMarkdownExtension],
)


def app_or_default(app: Any, filename: str) -> str:
    if hasattr(app, "__name__"):
        in_app = Path(app.__name__) / filename

        if in_app.exists():
            return str(in_app)

    # uproot default or project default
    return filename


def static_factory(realm: str = "_uproot") -> Callable[[str], str]:
    def localstatic(fname: str) -> str:
        last_mile = "/".join(urllib.parse.quote_plus(part) for part in fname.split("/"))
        return f"{d.ROOT}/static/{realm}/{last_mile}"

    return localstatic


def terms_url(language: i18n.ISO639) -> str:
    language_path = urllib.parse.quote(str(language), safe="")
    return f"{d.ROOT}/terms/{language_path}.js?v={i18n.VERSION}"


def function_context(page: Optional[type[Page]]) -> dict[str, Any]:
    if page is not None:
        return {
            "internalstatic": static_factory(),
            "projectstatic": static_factory("_project"),
            "appstatic": static_factory(page.__module__),
        }

    return {
        "internalstatic": static_factory(),
        "projectstatic": static_factory("_project"),
    }


def make_buttons(
    translate: Callable[[str], str], allow_back: bool
) -> tuple[Callable[..., Markup], Callable[..., Markup], dict[str, bool]]:
    state: dict[str, bool] = {"placed": False}

    def button_next(**kwargs: Any) -> Markup:
        state["placed"] = True
        label = kwargs.pop("label", None) or translate("Next")
        kwargs.setdefault("class_", "btn btn-primary")
        kwargs.setdefault("type", "submit")
        kwargs.setdefault("id", "uproot-button-next")
        return Markup(  # nosec B704
            f"<button {html_params(**kwargs)}>{Markup.escape(label)}</button>"
        )

    def button_back(**kwargs: Any) -> Markup:
        state["placed"] = True
        if not allow_back:
            return Markup("")
        label = kwargs.pop("label", None) or translate("Back")
        kwargs.setdefault("class_", "btn btn-outline-secondary")
        kwargs.setdefault("type", "button")
        kwargs.setdefault("id", "uproot-button-back")
        kwargs.setdefault("onclick", "uproot.goBack()")
        return Markup(  # nosec B704
            f"<button {html_params(**kwargs)}>{Markup.escape(label)}</button>"
        )

    return button_next, button_back, state


def make_timeout(
    translate: Callable[[str], str],
) -> tuple[Callable[..., Markup], Callable[..., Markup]]:
    def timeout(**kwargs: Any) -> Markup:
        extra = html_params(**kwargs) if kwargs else ""
        space = " " if extra else ""
        return Markup(  # nosec B704
            f'<span x-text="$store.uproot.timeout.compact"{space}{extra}>__:__</span>'
        )

    def timeout_box(**kwargs: Any) -> Markup:
        preamble = kwargs.pop("preamble", None) or translate(
            "Remaining time on this page:"
        )
        aria_label = translate("Remaining time on this page")
        class_ = kwargs.pop("class_", "alert callout mb-4-5 mt-4 pe-4")
        kwargs.setdefault("id", "uproot-timeout")
        time_id = kwargs.pop("time_id", "uproot-time-remaining")
        preamble_id = kwargs.pop("preamble_id", "uproot-time-remaining-preamble")
        extra = html_params(**kwargs) if kwargs else ""
        space = " " if extra else ""
        time_span = timeout(id=time_id)
        return Markup(  # nosec B704
            f"<div x-cloak"
            f' x-show="$store.uproot.timeout.active"'
            f" x-bind:class=\"'uproot-timeout-' + $store.uproot.timeout.level\""
            f' class="{Markup.escape(class_)}"'
            f' role="timer"'
            f' aria-label="{Markup.escape(aria_label)}"'
            f' aria-atomic="true"'
            f"{space}{extra}>"
            f'<span id="{Markup.escape(preamble_id)}">{Markup.escape(preamble)}</span> '
            f"{time_span}"
            f"</div>"
        )

    return timeout, timeout_box


def select_html_params(field: Any, class_: str) -> Any:
    attrs = {}

    if field.render_kw is not None:
        attrs = {clean_key(k): v for k, v in field.render_kw.items()}

    attrs["class"] = class_
    attrs.setdefault("id", field.id)

    validation_attrs = getattr(field.widget, "validation_attrs", ())

    for attr in dir(field.flags):
        if attr in validation_attrs and attr not in attrs:
            attrs[attr] = getattr(field.flags, attr)

    return html_params(name=field.name, **attrs)


async def form_factory(page: type[Page], player: object) -> type[BaseForm]:
    fields = await ensure_awaitable(
        optional_call, page, "fields", default_return=None, player=player
    )

    if fields is not None:
        return type("FormOnPage", (BaseForm,), fields)

    raise ValueError


def timeout_reached(page: type[Page], player: Storage, tol: float) -> bool:
    try:
        return cast(
            bool,
            time.time() + tol >= player._uproot_timeouts_until[str(player.show_page)],
        )
    except (AttributeError, KeyError):
        pass

    return False


def is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def exported_constants(app: Any) -> dict[str, Any]:
    if not (hasattr(app, "C") and hasattr(app.C, "__export__")):
        return {}

    C = app.C
    if isinstance(C, type):
        export = getattr(C, "__export__")

        if export is Ellipsis:
            return {k: v for k, v in vars(C).items() if not is_dunder(k)}

        return {k: getattr(C, k) for k in export}
    elif isinstance(C, dict):
        if C["__export__"] is Ellipsis:
            return C

        return {k: C[k] for k in C["__export__"]}
    else:
        raise TypeError(f"'C' must be class or dict (app: {app.__name__})")


async def render(
    server: "FastAPI",
    request: "Request",
    player: Optional[Storage],
    page: type[Page],
    formdata: Optional[Any] = None,
    custom_errors: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    uauth: Optional[str] = None,
    field_errors: Optional[dict[str, list[str]]] = None,
) -> str:
    ppath = truepath(page)
    group = nullcontext()

    if player is None:
        sname, uname, thisis, key = [None] * 4
        part = 0
        session = nullcontext()
    else:
        sname, uname, thisis, key = (
            player._uproot_session,
            player.name,
            player.show_page,
            player._uproot_key,
        )
        part = player._uproot_part
        session = player.session

        if player._uproot_group is not None:
            group = player.group

    data = a.from_cookie(uauth)
    is_admin = (
        d.UNSAFE
        or a.verify_auth_token(data.get("user", ""), data.get("token", "")) is not None
    )

    try:
        form = await form_factory(page, player)

        if formdata is None:
            if hasattr(page, "keep_values") and page.keep_values:
                form = form(obj=player)
            else:
                form = form()
        else:
            form = form(formdata)
            form.validate()
    except ValueError:
        form = None

    app = u.APPS[page.__module__] if page.__module__ in u.APPS else None

    if app is None and player is not None:
        for page_path in reversed(player.page_order):
            app_name = page_path.split("/", 1)[0]

            if app_name in u.APPS:
                app = u.APPS[app_name]
                break

    language = await ensure_awaitable(
        optional_call,
        app,
        "language",
        default_return=d.LANGUAGE,
        player=player,
    )

    internal = {
        "_uproot_internal": {
            "C": exported_constants(app),
            "is_admin": is_admin,
            "key": key,
            "language": language,
            "root": d.ROOT,
            "sname": sname,
            "thisis": thisis,
            "uname": uname,
            "allow_enter": d.ALLOW_ENTER,
        }
        | (metadata if metadata is not None else {})
    }
    jsvars = (
        cast(
            dict[str, Any],
            await ensure_awaitable(
                optional_call, page, "jsvars", default_return={}, player=player
            ),
        )
        | internal
    )

    def translate(s: str) -> str:
        return i18n.lookup(s, language)

    button_next, button_back, buttons_placed = make_buttons(
        translate, getattr(page, "allow_back", False)
    )
    timeout, timeout_box = make_timeout(translate)

    with session, group:
        context = (
            cast(
                dict[str, Any],
                await ensure_awaitable(
                    optional_call,
                    page,
                    "templatevars",
                    default_return={},
                    player=player,
                )
                or {},
            )
            | BUILTINS
            | {
                "app": app,
                "app_or_default": app_or_default,
                "button_back": button_back,
                "button_next": button_next,
                "buttons_placed": buttons_placed,
                "timeout": timeout,
                "timeout_box": timeout_box,
                "C": getattr(app, "C", {}),
                "form": form,
                "_": translate,
                "page": page,
                "part": part,
                "player": player,
                "safe": Markup,
                "session": session,
                "show2path": show2path,
                "uproot_terms_url": terms_url(cast(i18n.ISO639, language)),
                "_uproot_errors": custom_errors,
                "_uproot_field_errors": (
                    field_errors if field_errors is not None else {}
                ),
                "_uproot_js": jsvars,
                "_uproot_simulate": bool(
                    player is not None and session.get("_uproot_simulate", False)  # type: ignore[attr-defined]
                ),
                "show_testing": sname is not None
                and (is_admin or getattr(session, "_uproot_testing", False)),
            }
            | function_context(page)
            | internal
        )

        if player is not None:
            player.flush()

        return await ENV.get_template(ppath).render_async(**context)


async def render_error(
    request: "Request",
    player: Storage,
    uauth: Optional[str],
    exc: Exception,
) -> str:
    sname, uname, session = (
        player._uproot_session,
        player.name,
        materialize(player._uproot_session),
    )

    data = a.from_cookie(uauth)
    is_admin = (
        d.UNSAFE
        or a.verify_auth_token(data.get("user", ""), data.get("token", "")) is not None
    )

    internal = {
        "_uproot_internal": {
            "sname": sname,
            "uname": uname,
            "root": d.ROOT,
            "language": d.LANGUAGE,
            "is_admin": is_admin,
        },
    }

    context = (
        BUILTINS
        | {
            "_uproot_errors": None,
            "_uproot_js": internal,  # not a huge fan of this construction
            "uproot_terms_url": terms_url(d.LANGUAGE),
        }
        | function_context(None)
        | internal
        | {
            "player": player,
            "session": session,
            "show2path": show2path,
            "_uproot_simulate": False,
            "show_testing": session is not None
            and (is_admin or session._uproot_testing),
        }
    )

    # the following builds some info about the exception for admins

    if is_admin or (session is not None and session._uproot_testing):
        tb_list = traceback.extract_tb(exc.__traceback__)

        stack_frames = []

        for frame in tb_list:
            stack_frames.append(
                {
                    "filename": frame.filename,
                    "function": frame.name,
                    "lineno": frame.lineno,
                    "code": frame.line,
                }
            )

        # Get local variables from the last frame (where error occurred)
        if exc.__traceback__ is not None:
            last_frame = exc.__traceback__.tb_frame
            local_vars = {k: repr(v) for k, v in last_frame.f_locals.items()}
        else:
            local_vars = {}

        context |= {
            "error_message": str(exc),
            "exception_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
            "stack_frames": stack_frames,
            "local_vars": local_vars,
        }

    d.LOGGER.error(traceback.format_exc())

    return await ENV.get_template("InternalError.html").render_async(**context)


def truepath(page: type[Page]) -> str:
    if InternalPage in page.__mro__ and hasattr(page, "show") and not page.show:
        return f"#{page.__name__}"

    if not hasattr(page, "template"):
        html_path = f"{page.__module__}/{page.__name__}.html"

        try:
            ENV.get_template(html_path)
        except TemplateNotFound:
            md_path = f"{page.__module__}/{page.__name__}.md"
            try:
                ENV.get_template(md_path)
                return "BaseMarkdown.html"
            except TemplateNotFound:
                pass

        return html_path

    return page.template


def page2path(page: type[Page]) -> str:
    if InternalPage in page.__mro__:
        if page.__module__ == "uproot.types":
            # This is a true uproot-core-defined InternalPage
            return f"#{page.__name__}"
        # E.g., landing pages and StartApp
        return f"{page.__module__}/#{page.__name__}"

    return f"{page.__module__}/{page.__name__}"


def path2page(path: str) -> type[Page]:
    # System pages (Initialize.html, End.html, etc.)
    if path in u.PAGES:
        return u.PAGES[path]

    # Smithereens internal pages (#RandomStart, #{, etc.)
    if path.startswith("#"):
        from uproot.smithereens import INTERNAL_PAGES

        return INTERNAL_PAGES[path[1:]]

    # App pages (appname/PageName or appname/#InternalName)
    appname, pagename = path.split("/", 1)

    if pagename == "#StartApp":
        from uproot.core import make_start_app

        return cast(type[Page], make_start_app(appname))

    if pagename == "#LandingPage":
        from uproot.core import make_landing_page

        return make_landing_page(u.APPS[appname], appname)

    if pagename.startswith("#"):
        return cast(type[Page], getattr(u.APPS[appname], pagename[1:]))

    return cast(type[Page], getattr(u.APPS[appname], pagename))


@validate_call
def show2path(page_order: list[str], show_page: int) -> str:
    if show_page == -1:
        return "Initialize.html"

    if 0 <= show_page < len(page_order):
        return page_order[show_page]

    if len(page_order) == show_page:
        return "End.html"

    raise ValueError(show_page)


async def validate(
    page: type[Page], player: Storage, formdata: "FormData"
) -> tuple[Any, bool, list[str], dict[str, list[str]]]:
    form = None
    errors = []

    if hasattr(page, "fields"):
        form = (await form_factory(page, player))(formdata)

        if not form.validate():
            return form, False, [], {k: list(v) for k, v in form.errors.items()}

        errors_from_page = cast(
            str | list[str] | dict[str, str | list[str]],
            await ensure_awaitable(
                optional_call,
                page,
                "validate",
                default_return=[],
                player=player,
                data=form.data,
            ),
        )

        if isinstance(errors_from_page, str):
            errors = [errors_from_page]
        elif isinstance(errors_from_page, dict):
            field_errors: dict[str, list[str]] = {}
            for fname, ferrors in errors_from_page.items():
                if isinstance(ferrors, str):
                    ferrors = [ferrors]
                field_errors[fname] = list(ferrors)
            return form, not field_errors, [], field_errors
        else:
            errors = errors_from_page or []
            ensure(isinstance(errors, list), TypeError, "Errors must be a list")

    return form, not errors, errors, {}


def verify_csrf(page: type[Page], player: Storage, formdata: "FormData") -> bool:
    return (
        "_uproot_csrf" in formdata
        and formdata["_uproot_csrf"]
        == f"{player._uproot_session}+{player.name}+{player._uproot_key}"
    )


def to_filter(value: float, places: int) -> str:
    return f"{value:.{places}f}"


def unixtime2datetime_filter(epoch: float, precise: bool = False) -> str:
    dt = datetime.fromtimestamp(epoch)

    if precise:
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")

    return dt.strftime("%H:%M:%S.%f")[:-3]


def type_filter(x: Any) -> str:
    return str(type(x))


def tojson_filter(x: Any, indent: Optional[int] = None) -> str:
    option = orjson.OPT_INDENT_2 if indent else 0
    json_str = orjson.dumps(x, option=option).decode("utf-8")
    # Escape </ to prevent breaking out of <script> tags when used with |safe.
    # The \/ is valid JSON (RFC 8259) and decodes correctly.
    json_str = json_str.replace("</", r"<\/")
    # Return a plain string (not Markup) so Jinja2's autoescaping makes it safe
    # in HTML attribute and element contexts.  In <script> blocks, add |safe.
    return json_str


def fmtnum_filter(
    value: float,
    pre: str = "",
    post: str = "",
    places: int = 2,
    use_nbsp: bool = True,
    sep: str = ",",
    decsep: str = ".",
) -> str:
    formatted = f"{value:,.{places}f}" if sep else f"{value:.{places}f}"

    if sep:
        if decsep != ".":
            formatted = (
                formatted.replace(",", "\x00").replace(".", decsep).replace("\x00", sep)
            )
        else:
            formatted = formatted.replace(",", sep)

    if decsep != "." and not sep:
        formatted = formatted.replace(".", decsep)

    formatted = f"{pre}{formatted}{post}"

    if value < 0:
        formatted = "\u2212" + formatted.replace("-", "")

    if use_nbsp:
        formatted = formatted.replace(" ", "\xa0")

    return formatted


ENV.filters["fmtnum"] = fmtnum_filter
ENV.filters["repr"] = repr
ENV.filters["tojson"] = tojson_filter
ENV.filters["to"] = to_filter
ENV.filters["type"] = type_filter
ENV.filters["unixtime2datetime"] = unixtime2datetime_filter
ENV.globals["select_html_params"] = select_html_params
