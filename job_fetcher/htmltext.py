from __future__ import annotations

from html.parser import HTMLParser

MAX_DESCRIPTION_LENGTH = 6000

_BLOCK_TAGS = {
    "p", "li", "ul", "ol", "div", "br", "tr", "td",
    "h1", "h2", "h3", "h4", "h5", "h6",
}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data):
        self._chunks.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self._chunks.append(" ")

    def text(self) -> str:
        return " ".join("".join(self._chunks).split())


def strip_html(html_text: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html_text)
    return parser.text()


def description_from_html(html_text: str | None) -> str | None:
    if not html_text:
        return None
    stripped = strip_html(html_text)
    if not stripped:
        return None
    return stripped[:MAX_DESCRIPTION_LENGTH]


def description_from_plain(plain_text: str | None) -> str | None:
    if not plain_text:
        return None
    collapsed = " ".join(plain_text.split())
    if not collapsed:
        return None
    return collapsed[:MAX_DESCRIPTION_LENGTH]
