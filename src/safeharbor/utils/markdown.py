"""Markdown rendering helpers."""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from typing import Final

import bleach  # type: ignore[import-untyped]
from markdown_it import MarkdownIt
from markupsafe import Markup

_ALLOWED_TAGS: Final[frozenset[str]] = frozenset(
    {
        "p",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "a",
        "ul",
        "ol",
        "li",
        "strong",
        "em",
        "code",
        "pre",
        "blockquote",
        "hr",
        "br",
    }
)
_ALLOWED_ATTRIBUTES: Final[dict[str, tuple[str, ...]]] = {"a": ("href", "title", "rel")}
_ALLOWED_PROTOCOLS: Final[frozenset[str]] = frozenset({"http", "https", "mailto"})
_REQUIRED_ANCHOR_REL: Final[tuple[str, ...]] = ("nofollow", "noopener")
_DANGEROUS_RAW_HTML_RE: Final[re.Pattern[str]] = re.compile(
    r"<(script|style|iframe)\b[^>]*>.*?</\1\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)


class _BleachSanitizedMarkdownIt(MarkdownIt):  # type: ignore[misc, unused-ignore]
    def validateLink(self, url: str) -> bool:  # noqa: N802
        """Allow bleach to enforce link protocols during sanitization."""
        return True


_MARKDOWN = _BleachSanitizedMarkdownIt("commonmark", {"html": True})


class _AnchorRelInjector(HTMLParser):
    """Serialize sanitized HTML while ensuring anchors carry the required rel."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._chunks: list[str] = []

    def html(self) -> str:
        return "".join(self._chunks)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._append_starttag(tag, attrs, closed=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._append_starttag(tag, attrs, closed=True)

    def handle_endtag(self, tag: str) -> None:
        self._chunks.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self._chunks.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        self._chunks.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._chunks.append(f"&#{name};")

    def _append_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]], *, closed: bool
    ) -> None:
        normalized_attrs = list(attrs)
        if tag == "a":
            normalized_attrs = self._normalize_anchor_rel(normalized_attrs)

        rendered_attrs = "".join(
            f' {name}="{escape(value or "", quote=True)}"' for name, value in normalized_attrs
        )
        suffix = " />" if closed else ">"
        self._chunks.append(f"<{tag}{rendered_attrs}{suffix}")

    def _normalize_anchor_rel(
        self, attrs: list[tuple[str, str | None]]
    ) -> list[tuple[str, str | None]]:
        rel_tokens: list[str] = []
        attrs_without_rel: list[tuple[str, str | None]] = []
        for name, value in attrs:
            if name == "rel":
                rel_tokens.extend((value or "").split())
            else:
                attrs_without_rel.append((name, value))

        merged_tokens = list(dict.fromkeys([*rel_tokens, *_REQUIRED_ANCHOR_REL]))
        attrs_without_rel.append(("rel", " ".join(merged_tokens)))
        return attrs_without_rel


def render_markdown(text: str) -> Markup:
    """Render CommonMark text to sanitized HTML safe for Jinja templates."""
    raw_html = _MARKDOWN.render(_DANGEROUS_RAW_HTML_RE.sub("", text))
    clean_html = bleach.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )

    rel_injector = _AnchorRelInjector()
    rel_injector.feed(clean_html)
    rel_injector.close()
    return Markup(rel_injector.html())
