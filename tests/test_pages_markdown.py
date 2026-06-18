from importlib.resources import files

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

from uproot import i18n, pages
from uproot.pages import IncludeMarkdownExtension, MarkdownLoader


def make_environment(templates: dict[str, str]) -> Environment:
    default_templates = files("uproot").joinpath("default")
    return Environment(
        loader=MarkdownLoader(
            i18n.TranslateLoader(
                ChoiceLoader(
                    [
                        DictLoader(templates),
                        FileSystemLoader(str(default_templates)),
                    ]
                )
            )
        ),
        autoescape=True,
        enable_async=True,
        extensions=[IncludeMarkdownExtension],
    )


def markdown_path(page: type) -> str:
    return f"{page.__module__}/{page.__name__}.md"


async def test_markdown_page_uses_h1_as_rendered_title():
    class ExamplePage:
        pass

    environment = make_environment(
        {
            markdown_path(ExamplePage): (
                "# Hello *{{ name }}*\n\n" "Value: **{{ value }}**\n"
            ),
            "Base.html": (
                "{% set page_title %}{% block title %}{% endblock title %}"
                "{% endset %}"
                '{% if page_title %}<h1 id="uproot-title">'
                "{{ page_title }}</h1>{% endif %}"
                "<main>{% block main %}{% endblock main %}</main>"
            ),
        }
    )

    rendered = await environment.get_template("BaseMarkdown.html").render_async(
        page=ExamplePage,
        name="<Alice>",
        value="<strong>",
    )

    assert '<h1 id="uproot-title">Hello <em>&lt;Alice&gt;</em></h1>' in rendered
    assert "<h1>Hello" not in rendered
    assert "<p>Value: <strong>&lt;strong&gt;</strong></p>" in rendered


async def test_multiple_markdown_h1s_do_not_create_uproot_title():
    class ExamplePage:
        pass

    environment = make_environment(
        {
            markdown_path(ExamplePage): "# First\n\n# Second\n",
            "Base.html": (
                "{% set page_title %}{% block title %}{% endblock title %}"
                "{% endset %}"
                '{% if page_title %}<h1 id="uproot-title">'
                "{{ page_title }}</h1>{% endif %}"
                "<main>{% block main %}{% endblock main %}</main>"
            ),
        }
    )

    rendered = await environment.get_template("BaseMarkdown.html").render_async(
        page=ExamplePage
    )

    assert 'id="uproot-title"' not in rendered
    assert "<h1>First</h1>" in rendered
    assert "<h1>Second</h1>" in rendered


def test_truepath_falls_back_to_markdown_but_prefers_html(monkeypatch):
    class MarkdownPage:
        pass

    class HtmlPage:
        pass

    environment = make_environment(
        {
            markdown_path(MarkdownPage): "# Markdown\n",
            markdown_path(HtmlPage): "# Markdown\n",
            f"{HtmlPage.__module__}/{HtmlPage.__name__}.html": "HTML",
        }
    )
    monkeypatch.setattr(pages, "ENV", environment)

    assert pages.truepath(MarkdownPage) == "BaseMarkdown.html"
    assert pages.truepath(HtmlPage) == f"{HtmlPage.__module__}/{HtmlPage.__name__}.html"


def test_truepath_populates_template_cache(monkeypatch):
    class HtmlPage:
        pass

    html_path = f"{HtmlPage.__module__}/{HtmlPage.__name__}.html"
    environment = make_environment({html_path: "HTML"})
    monkeypatch.setattr(pages, "ENV", environment)

    assert pages.truepath(HtmlPage) == html_path
    assert len(environment.cache) == 1
    cached_template = environment.get_template(html_path)

    assert cached_template is environment.get_template(html_path)


async def test_markdown_translation_preserves_markdown(monkeypatch):
    class ExamplePage:
        pass

    source_title = "Hello **world**"
    source_body = "This is **important**"
    environment = make_environment(
        {
            markdown_path(ExamplePage): (
                f"# {{% translate %}}{source_title}{{% endtranslate %}}\n\n"
                f"{{% translate %}}{source_body}{{% endtranslate %}}\n"
            ),
            "Base.html": (
                "{% set page_title %}{% block title %}{% endblock title %}"
                "{% endset %}"
                "<h1>{{ page_title }}</h1>"
                "<main>{% block main %}{% endblock main %}</main>"
            ),
        }
    )
    monkeypatch.setattr(i18n, "LANGUAGES", {"de"})
    monkeypatch.setattr(
        i18n,
        "TERMS",
        {
            source_title: {"de": "Hallo **Welt**"},
            source_body: {"de": "Dies ist **wichtig**"},
        },
    )

    rendered = await environment.get_template("BaseMarkdown.html").render_async(
        page=ExamplePage,
        _uproot_internal={"language": "de"},
    )

    assert "<h1>Hallo <strong>Welt</strong></h1>" in rendered
    assert "<p>Dies ist <strong>wichtig</strong></p>" in rendered
