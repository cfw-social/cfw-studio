#!/usr/bin/env python3
"""Read the CTA copy typed or supplied for the end card. Standard library only.

A CTA input may arrive as inputs/cta/cta.json or as plain text in inputs/cta/cta.md. This module
(used by cta_takeover.py) reads, in order, and never invents copy or a handle:

  1. inputs/cta/cta.json  {"text", "brandName", "handle"}       (any key may be absent)
  2. inputs/cta/cta.md, cta.txt, or any one .json/.md/.txt there: a JSON object as in 1, or plain
     text: the offer line(s); an @handle or a URL/domain in it is the handle
  3. nothing: no CTA text and NO handle line (the caller then falls back to the brand's own copy)
"""
import glob
import json
import os
import re

# What counts as a handle ("Node.js" or an email's domain must not become the handle line).
#   a line that is ONLY a handle or URL:  @name | scheme/www URL | a bare domain (e.g. brand.com/book)
#   inside offer prose:                   @name | scheme/www URL | a domain WITH a path; never a bare
#                                         "word.tld" (Node.js, Next.js, an email's domain)
_HANDLE = r"@[A-Za-z0-9_.]{2,30}[A-Za-z0-9_]"
_URL = r"(?:https?://|www\.)[^\s]+"
_DOMAIN = r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}"
LINE_RE = re.compile(r"(%s)|(%s)|(%s(?:/[^\s]*)?)" % (_HANDLE, _URL, _DOMAIN))
INLINE_RE = re.compile(r"(?<![\w@])(?:(%s)|(%s)|((?<![\w@.-])%s/[^\s]*))" % (_HANDLE, _URL, _DOMAIN))
CODE_SUFFIXES = {"js", "ts", "jsx", "tsx", "py", "rb", "rs", "go", "md", "sh", "json", "html", "css", "php", "java", "cs", "txt"}


class Bad(Exception):
    pass


def text_of(v):
    return v.strip() if isinstance(v, str) else ""


def bare_code_name(s):
    """True for a bare `name.js` / `file.py` style word that is not a web address."""
    return "/" not in s and "@" not in s and s.rsplit(".", 1)[-1].lower() in CODE_SUFFIXES


def from_plain(raw):
    """Plain typed text: a line that is only a handle/URL is the handle; the rest is the offer."""
    lines = [ln.strip() for ln in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()]
    handle, offer = "", []
    for ln in lines:
        if not handle and LINE_RE.fullmatch(ln) and not bare_code_name(ln):
            handle = ln
        else:
            offer.append(ln)
    text = " ".join(offer)
    if not handle:
        m = INLINE_RE.search(text)
        if m:
            handle = (m.group(1) or m.group(2) or m.group(3)).rstrip(".,!?;:")
    return {"text": text, "handle": handle, "brandName": ""}


def read_cta_dir(d):
    if not d or not os.path.isdir(d):
        return None, ""
    order = [os.path.join(d, n) for n in ("cta.json", "cta.md", "cta.txt")]
    order += sorted(p for p in glob.glob(os.path.join(d, "*"))
                    if p.lower().endswith((".json", ".md", ".txt")) and p not in order)
    for p in order:
        if not os.path.isfile(p):
            continue
        try:
            raw = open(p, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError) as e:
            raise Bad("CTA input %s could not be read: %s" % (p, e))
        if not raw.strip():
            continue
        src = "inputs/cta/" + os.path.basename(p)
        stripped = raw.strip()
        if p.endswith(".json") or stripped.startswith("{"):
            try:
                obj = json.loads(stripped)
            except ValueError:
                if p.endswith(".json"):
                    raise Bad("CTA input %s is not valid JSON" % src)
                return from_plain(raw), src
            if not isinstance(obj, dict):
                raise Bad("CTA input %s is not a JSON object" % src)
            return {"text": text_of(obj.get("text")), "handle": text_of(obj.get("handle")),
                    "brandName": text_of(obj.get("brandName"))}, src
        return from_plain(raw), src
    return None, ""
