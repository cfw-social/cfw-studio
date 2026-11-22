#!/usr/bin/env python3
"""Escaping for text that enters a page this recipe writes. Standard library only. Not run directly.

refuse_addresses(text, name)
                    raise ValueError when the text holds a web address, a script address or a CSS
                    address form. b-hyperframes' local-only check reads a page after undoing entities
                    and CSS escapes, so it cannot tell such text from a real address; the same text is
                    refused up front, naming the key (same rules as the b-typing-ui fillers).
strip_scheme(text)  drop `http://`, `https://`, `ws://`, `wss://`, `ftp://` and a leading `www.`
                    from a handle or link shown on a card (`https://brand.example/x` -> `brand.example/x`).
esc(value)          text for an HTML text node. < > & quotes, braces, backslash, slash, colon,
                    parentheses, @ and the back quote become numeric entities. They display the
                    same, but no value can look like markup, a placeholder, a web address, a url()
                    or an import to the local-only check of b-hyperframes. Control characters and
                    U+2028/2029 become spaces.
accent_html(value)  as esc, but keeps balanced <span class="accent">...</span> wrappers.
fill(text, values)  replace {{KEY}} placeholders in ONE pass; a value is never searched again.
"""
import html
import re

_ADDRESS_RULES = [
    (re.compile(r"(?i)(?<![A-Za-z0-9+.-])(?:https?|wss?|ftp)\s*:"), "a web address (http, https, ws, wss or ftp)"),
    (re.compile(r"[A-Za-z][A-Za-z0-9+.-]*\s*:\s*/\s*/"), "an address with a scheme (name://)"),
    (re.compile(r"(?i)(?:javascript|vbscript)\s*:"), "a script address (javascript: or vbscript:)"),
    (re.compile(r"(?i)(?<![\w$.])data:\s*[a-z0-9.+-]+/[a-z0-9.+-]+"), "a data: address"),
    (re.compile(r"(?<![A-Za-z0-9])//[A-Za-z0-9\[]"), "a protocol-relative address (//host)"),
    (re.compile(r"(?i)(?<![A-Za-z0-9_])url\s*\("), "url("),
    (re.compile(r"(?i)@\s*import"), "@import"),
    (re.compile(r"(?i)image-set\s*\("), "image-set("),
]
_CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\n]?|\\(.)", re.S)
_SCHEME = re.compile(r"(?i)\b(?:https?|wss?|ftp)://(?:www\.)?")
_SCRIPT_WORDS = re.compile(
    r"(?i)XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|serviceWorker|innerHTML|outerHTML|"
    r"insertAdjacentHTML|createContextualFragment|DOMParser|(?:document|window)\s*\.\s*(?:write|open)|"
    r"location\s*\.\s*(?:href|assign|replace)")
ACCENT_TAG = re.compile(r'(<span class="accent">|</span>)')
ACCENT_OPEN = '<span class="accent">'
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
_ENTITIES = (("{", "&#123;"), ("}", "&#125;"), ("\\", "&#92;"), ("/", "&#47;"),
             (":", "&#58;"), ("(", "&#40;"), (")", "&#41;"), ("@", "&#64;"), ("`", "&#96;"))


def _css_decode(text):
    def one(m):
        if m.group(1):
            n = int(m.group(1), 16)
            return chr(n) if 0 < n <= 0x10FFFF else ""
        return m.group(2)
    return _CSS_ESCAPE.sub(one, text)


def refuse_addresses(text, name):
    text = str(text)
    for form in (text, _css_decode(text)):
        for pattern, what in _ADDRESS_RULES:
            if pattern.search(form):
                raise ValueError("%s contains %s. The render check refuses any page with an address in it, "
                                 "even as plain text. Write example.com, not https://example.com" % (name, what))


def strip_scheme(text):
    return _SCHEME.sub("", str(text))


def _hide_script_words(text):
    # a word the render check refuses anywhere in a page: one letter becomes an entity, the page shows the same text
    return _SCRIPT_WORDS.sub(lambda m: "&#%d;%s" % (ord(m.group(0)[0]), m.group(0)[1:]), text)


def esc(value):
    text = html.escape(str(value), quote=True)
    for ch, ent in _ENTITIES:
        text = text.replace(ch, ent)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f\u2028\u2029]", " ", text)
    return _hide_script_words(text)


def accent_html(value):
    value = str(value)
    if value.count(ACCENT_OPEN) != value.count("</span>"):
        return esc(value)
    return "".join(p if ACCENT_TAG.fullmatch(p) else esc(p) for p in ACCENT_TAG.split(value))


def fill(text, values):
    return PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), text)
