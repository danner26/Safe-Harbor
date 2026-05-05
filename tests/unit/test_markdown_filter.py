"""Markdown rendering and sanitization tests."""

from __future__ import annotations

from markupsafe import Markup

from safeharbor import create_app
from safeharbor.utils.markdown import render_markdown


def test_render_markdown_returns_markup() -> None:
    rendered = render_markdown("Plain text")

    assert isinstance(rendered, Markup)


def test_script_tag_stripped() -> None:
    rendered = render_markdown("<script>alert('xss')</script>Safe")

    assert "<script" not in rendered
    assert "alert" not in rendered
    assert "Safe" in rendered


def test_onclick_attribute_stripped() -> None:
    rendered = render_markdown('<a href="https://example.test" onclick="evil()">link</a>')

    assert "onclick" not in rendered
    assert 'href="https://example.test"' in rendered


def test_img_denied() -> None:
    rendered = render_markdown("![alt](https://example.test/image.jpg)")

    assert "<img" not in rendered


def test_anchor_gets_rel_nofollow_noopener() -> None:
    rendered = render_markdown("[Safe Harbor](https://example.test)")

    assert 'href="https://example.test"' in rendered
    assert 'rel="nofollow noopener"' in rendered


def test_anchor_existing_rel_gets_noopener() -> None:
    rendered = render_markdown('<a href="https://example.test" rel="nofollow">link</a>')

    assert 'href="https://example.test"' in rendered
    assert 'rel="nofollow noopener"' in rendered


def test_javascript_protocol_stripped() -> None:
    rendered = render_markdown("[bad](javascript:alert('xss'))")

    assert "javascript:" not in rendered
    assert "href=" not in rendered


def test_mailto_protocol_allowed() -> None:
    rendered = render_markdown("[email](mailto:keeper@example.test)")

    assert 'href="mailto:keeper@example.test"' in rendered


def test_headings_render() -> None:
    rendered = render_markdown("# Heading")

    assert "<h1>Heading</h1>" in rendered


def test_lists_render() -> None:
    rendered = render_markdown("- Ammonia\n- Nitrite")

    assert "<ul>" in rendered
    assert "<li>Ammonia</li>" in rendered
    assert "<li>Nitrite</li>" in rendered


def test_markdown_filter_registered() -> None:
    app = create_app("testing")

    assert app.jinja_env.filters["markdown"] is render_markdown
