#!/usr/bin/env python3
"""The CTA copy for the end card. Standard library only.

A typed `cta` input is staged as plain text at inputs/cta/cta.md. This reads, in order, and
never invents copy or a handle:

  1. inputs/cta/cta.json  {"text", "brandName", "handle"}       (any key may be absent)
  2. inputs/cta/cta.md, cta.txt, or any one .json/.md/.txt there: a JSON object as in 1, or plain
     text: the offer line(s); an @handle or a URL/domain in it is the handle
  3. brief.json brand.cta / brand.handle (when the order carries them)
  4. nothing: no CTA text and NO handle line

  resolve   [--inputs inputs/cta] [--brief brief.json] [--out work/cta.json]
            writes the result as JSON ({text, handle, brandName, source}); prints it when no --out
  has-text  FILE.json
            exit 0 when the resolved copy has a hero line, 3 when it has none
  check     --cta work/cta.json --html work/cta-card/index.html
            FAILS when the end-card composition does not show the CTA text and handle

The copy is data. It is never placed in a shell command or evaluated.
"""
import argparse
import glob
import html
import json
import os
import re
import sys

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


def resolve(inputs_dir, brief_path):
    if not brief_path or not os.path.isfile(brief_path):
        raise Bad("brief %s not found" % brief_path)
    try:
        b = json.load(open(brief_path, encoding="utf-8"))
    except ValueError as e:
        raise Bad("brief %s is not valid JSON: %s" % (brief_path, e))
    brand = b.get("brand") if isinstance(b, dict) and isinstance(b.get("brand"), dict) else {}
    got, src = read_cta_dir(inputs_dir)
    d = {"text": "", "handle": "", "brandName": text_of(brand.get("name")), "source": "none"}
    if got:
        d.update(text=got["text"], handle=got["handle"], source=src)
        if got.get("brandName"):
            d["brandName"] = got["brandName"]
    if not d["text"] and text_of(brand.get("cta")):
        d["text"], d["source"] = text_of(brand.get("cta")), "brief.json brand.cta"
    if not d["handle"] and text_of(brand.get("handle")):
        d["handle"] = text_of(brand.get("handle"))
    return d


def words(s):
    return re.findall(r"[a-z0-9]+", html.unescape(s).lower())


def contains(hay, needle):
    n = len(needle)
    return n == 0 or any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def check(cta_path, html_path):
    d = json.load(open(cta_path, encoding="utf-8"))
    src = open(html_path, encoding="utf-8").read()
    body = re.sub(r"<style[^>]*>.*?</style>", " ", src, flags=re.S | re.I)
    hay = words(re.sub(r"<[^>]+>", " ", body))
    missing = [k for k in ("text", "handle") if d.get(k) and not contains(hay, words(d[k]))]
    return missing


def main(argv=None):
    p = argparse.ArgumentParser(description="Resolve / check the end-card CTA copy.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("--inputs", default="inputs/cta")
    r.add_argument("--brief", default="brief.json")
    r.add_argument("--out", default="")
    h = sub.add_parser("has-text")
    h.add_argument("file")
    c = sub.add_parser("check")
    c.add_argument("--cta", required=True)
    c.add_argument("--html", required=True)
    a = p.parse_args(argv)
    try:
        if a.cmd == "resolve":
            d = resolve(a.inputs, a.brief)
            if a.out:
                os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
                json.dump(d, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            sys.stderr.write("[cta] source=%s text=%s handle=%s\n" % (d["source"], "yes" if d["text"] else "none",
                                                                      "yes" if d["handle"] else "none (no handle line)"))
            if not a.out:
                print(json.dumps(d, ensure_ascii=False))
            return 0
        if a.cmd == "has-text":
            return 0 if text_of(json.load(open(a.file, encoding="utf-8")).get("text")) else 3
        missing = check(a.cta, a.html)
        if missing:
            print("FAIL cta check: the end card %s does not show the CTA %s" % (a.html, " and ".join(missing)))
            return 1
        print("PASS cta check: the end card shows the CTA copy")
        return 0
    except (Bad, OSError, ValueError) as e:
        sys.stderr.write("cta_copy.py %s: FAILED - %s\n" % (a.cmd, e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
