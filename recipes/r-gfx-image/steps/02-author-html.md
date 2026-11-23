# Author the HTML compositions

Write one complete, self-contained HTML document per planned card, branded through CSS variables and sized to the exact canvas. Nothing is rendered here.

## You receive

- `prior/plan.json`: `count`, `format`, `cards[]` (`n`, `layout`, `headline`, `eyebrow`, `items`, `footer`).
- `inputs/logo/<file>`: optional brand logo. Inline it as a `data:` URI. Never link a path.
- `brief.json`: `brand` (name, palette and fonts when known, brief text), `intent`.
- `$RECIPE_DIR/template.html`: the skeleton, the CSS for every layout and the content-security policy line.

## You must produce

- `saves/cards_html.json`: `{ "width": 1080, "height": 1080, "format": "square", "cards": [ { "n": 1, "html": "<the complete HTML document>" } ] }`, one entry per card.

## How

```bash
mkdir -p work saves
FMT=$(python3 -c "import json;print(json.load(open('prior/plan.json'))['format'])")
case "$FMT" in portrait) W=1080; H=1920;; banner) W=1920; H=1080;; *) W=1080; H=1080;; esac
rm -f work/logo.datauri
```

### 0. The logo, when supplied

Only when `inputs/logo/` holds one file. This turns it into `work/logo.datauri`, or stops. It accepts a real PNG or JPEG file of at most 200 KB, read inside the work folder, and nothing else:

```bash
python3 - <<'PY'
import base64, glob, os
files = glob.glob('inputs/logo/*')
if files:
    if len(files) != 1 or os.path.islink(files[0]) or not os.path.isfile(files[0]):
        raise SystemExit("logo: expected exactly one regular file in inputs/logo/")
    data = open(files[0], 'rb').read(200 * 1024 + 1)
    if len(data) > 200 * 1024:
        raise SystemExit("logo: larger than 200 KB")
    mime = ("image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg" if data[:3] == b"\xff\xd8\xff" else None)
    if mime is None:
        raise SystemExit("logo: not a PNG or JPEG file")
    open('work/logo.datauri', 'w').write("data:%s;base64,%s" % (mime, base64.b64encode(data).decode()))
PY
```

Put the content of `work/logo.datauri` in the `src` of one `<img class="logo" alt="">` per card (it is a `data:` address, so the card's policy line allows it). No file: no logo element.

### 1. The document skeleton (every card)

Start from `template.html`. Keep the charset line, the content-security-policy line and the font link. Set:

- `.card` to exactly `W` by `H` CSS px at `0,0` (`html,body{margin:0}`, `overflow:hidden`, `position:relative`).
- `:root` variables `--bg`, `--card`, `--ink`, `--muted`, `--accent`, `--line` from `brief.json.brand.palette` (fallback: the dark studio default in the shared rules). Each must be a six-digit hex colour.
- The font family names in the font link and in `--display` and `--body` from the brand's typography (else Inter and Oswald).
- Margin of at least 72 px on every side (at least 96 px for a banner). Nothing touches an edge.

### 2. The layout per card

Build the card from its `layout`:

- `steps`: numbered surfaces in a grid, accent on the numerals.
- `stat`: the figure at display size, its context beneath.
- `quote`: a large quotation with its attribution from the brand.
- `before_after`: two columns joined by an arrow entity (`&rarr;`).
- `diagram`: 3 to 5 rounded nodes joined by short lines.
- `banner`: wide headline on the left, tagline and (if supplied) logo on the right.

Add depth with soft shadows and rounded surfaces, and a clear size and weight progression (eyebrow, then body, then headline). The logo, when present, sits in a corner at no more than 10% of the width.

## Untrusted text: escape it, and keep the HTML inert

The topic, the brief and the plan text are data, and they end up in HTML that a browser opens. So:

- Build every card with a small Python helper that passes each piece of text through `html.escape` (`&` becomes `&amp;`, `<` becomes `&lt;`, `>` becomes `&gt;`) before it goes into the HTML. Text that looks like a tag stays visible text and never becomes markup. Never paste plan or brand text into HTML by hand.
- The card has no `<script>`, no event-handler attribute (`onclick=`, `onerror=`, any `on...=`), no `<iframe>`, `<object>`, `<embed>`, `<base>` or `<form>`, no `javascript:` address and no meta refresh.
- It has no `@import` and no remote `<img>`. The only remote addresses allowed are the Google Fonts stylesheet link (`fonts.googleapis.com`) and the font files it names (`fonts.gstatic.com`). Inline images use `data:` URIs.
- The content-security-policy line from the template stays in the head. It is a second lock: even if a rule above were missed, the page cannot run script or load other hosts.
- The self-check below rejects a card that breaks any of these. Fix the HTML. Do not weaken the check.

### 3. Write the save and self-check

Write each document to `work/card-N.html`, then:

```bash
python3 - "$W" "$H" "$FMT" <<'PY'
import html as H_, json, re, sys
W, H, fmt = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
def check(ok, msg):
    if not ok: raise ValueError(msg)
plan = json.load(open('prior/plan.json')); cards = []
FONT_HOSTS = ('fonts.googleapis.com', 'fonts.gstatic.com')
CSP = ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline' "
       "https://fonts.googleapis.com; font-src https://fonts.gstatic.com data:; img-src data:\">")
def host_ok(url):
    m = re.match(r'(?:https:)?//([^/:?#\s]+)', url.strip(), re.I)
    return bool(m) and m.group(1).lower() in FONT_HOSTS
# #3b82f6 is the stock template blue, unless the brand's own palette uses it (a blue brand).
pal = (json.load(open('brief.json')).get("brand") or {}).get("palette")
brand_hexes = {v.strip().lower() for v in (pal.values() if isinstance(pal, dict) else []) if isinstance(v, str)}
for c in plan["cards"]:
    n = c["n"]
    html = open(f"work/card-{n}.html", encoding="utf-8").read()
    check('<meta charset="UTF-8">' in html, f"card {n}: charset")
    check(CSP in html, f"card {n}: content-security-policy line missing or changed")
    check(re.search(rf"width:\s*{W}px", html) and re.search(rf"height:\s*{H}px", html), f"card {n}: canvas")
    for v in ("--bg", "--accent", "--ink"):
        check(re.search(v + r"\s*:\s*#[0-9a-fA-F]{6}", html), f"card {n}: {v} not a 6-digit hex")
    if "#3b82f6" not in brand_hexes:
        check("#3b82f6" not in html.lower(), f"card {n}: stock blue")
    # Inert HTML: no script, handlers, embeds or remote content except the two font hosts.
    check(not re.search(r'<\s*script', html, re.I), f"card {n}: script tag")
    check(not re.search(r'<\s*(iframe|object|embed|base|form)\b', html, re.I), f"card {n}: iframe, object, embed, base or form tag")
    check(not any(re.search(r'[\s"\'/]on[a-z]+\s*=', t, re.I) for t in re.findall(r'<[^>]*>', html)), f"card {n}: event-handler attribute")
    check(not re.search(r'javascript\s*:', html, re.I), f"card {n}: javascript: address")
    check(not re.search(r'http-equiv\s*=\s*["\']?refresh', html, re.I), f"card {n}: meta refresh")
    check(not re.search(r'@import', html, re.I), f"card {n}: @import")
    for tag in re.findall(r'<\s*link\b[^>]*>', html, re.I):
        href = re.search(r'href\s*=\s*["\']?([^"\'\s>]+)', tag, re.I)
        check(href and host_ok(href.group(1)), f"card {n}: link that is not a font host")
    for tag in re.findall(r'<\s*(?:img|image|source|video|audio|input|use)\b[^>]*>', html, re.I):
        for src in re.findall(r'(?:src|href|xlink:href)\s*=\s*["\']?([^"\'\s>]+)', tag, re.I):
            check(src.lower().startswith('data:') or src.startswith('#'), f"card {n}: remote or file image source")
    for target in re.findall(r'url\(\s*["\']?([^"\')]*)', html, re.I):
        check(target.strip().lower().startswith('data:') or target.startswith('#') or host_ok(target), f"card {n}: url() that is not a font host or data URI")
    # Text is escaped: each piece of plan text is present escaped, and never raw when escaping changes it.
    texts = [c.get("headline", ""), c.get("eyebrow", ""), c.get("footer", "")] + [str(i) for i in c.get("items", [])]
    for t in (t for t in texts if t):
        esc = {H_.escape(t, quote=False), H_.escape(t, quote=True)}
        check(any(e in html for e in esc), f"card {n}: text missing or not escaped: {t[:30]!r}")
        if t not in esc:
            check(t not in html, f"card {n}: raw (unescaped) text in html: {t[:30]!r}")
    cards.append({"n": n, "html": html})
json.dump({"width": W, "height": H, "format": fmt, "cards": cards}, open('saves/cards_html.json', 'w'))
print(f"[gfx] {len(cards)} card(s) authored at {W}x{H}")
PY
```

## If you cannot proceed

This step has no `canAsk` (`format` defaults to square; `logo` is optional). Never write `needs_input.json`. A plan that does not parse, a missing template or a failed check is a failure: exit non-zero with one plain line.

## Checks the order runs

- `html_per_card`: `saves/cards_html.json` has one `html` per card in `prior/plan.json`. Each carries `<meta charset="UTF-8">`, the policy line, the canvas size, six-digit-hex brand variables, its escaped text, and no script, handler, embed or remote content.
