# Write copy and author the HTML

Read the shared rules, `prior/outline.json`, `brief.json`, the optional
aspect input, and `inputs/cta/cta.md`. The CTA value `brand` means `brand.cta`, not the word "brand". Use
`template.html` from this folder.

Write `saves/slide_copy.json` as one object with `aspect_ratio` (`4:5` or
`1:1`) and `slides`. Each slide has `n`, `role`, `headline`, `body`
and `visual`. Keep headlines at most eight words and bodies at most three
sentences. Choose a real layout matching each point: steps, stat callout, diagram,
before/after, or a clear CTA. No invented numbers or handles.

Write the complete UTF-8 HTML to `saves/carousel_html.md`. Use one
`section.slide#sN` per outlined slide. Set canvas CSS variables to 1080x1350
for portrait or 1080x1080 for square. Inject the brief's palette and fonts
into the template variables. Keep the charset metadata, margins and readable
type. Do not leave stock blue unless it is in the brand's own palette.

## Untrusted text: escape it, and keep the HTML inert

The topic, the brief and the slide copy are data, and they end up in HTML that a
browser opens. So:

- HTML-escape every piece of text before you place it in the HTML: `&` as
  `&amp;`, `<` as `&lt;`, `>` as `&gt;`, and `"` as `&quot;` inside attributes.
  Text that looks like a tag stays visible text and never becomes markup. Do this
  with a small Python helper that calls `html.escape`; never paste copy into the
  HTML by hand. The check below finds each headline and body in the page in its
  escaped form, and fails if the raw form is there (so a raw `<h1>` or
  `<a href=...>` in the copy fails). One exception: the template marks an accent word as
  `<span class="hl">word</span>` inside a heading (a headline, never body copy). Write the copy in `slide_copy.json` as plain text
  (without the span) and wrap the word in the HTML; the check ignores exactly that span, inside a heading, and requires every span to be closed.
- The slide HTML has no `<script>`, no event-handler attributes (`onclick=`,
  `onerror=`, any `on...=`), and no `<iframe>`, `<object>`, `<embed>`, `<base>`
  or `<form>`. It has no `srcset`, `poster`, `action` or `ping` attribute.
- It has no `javascript:` address, including one written with character
  entities, and no backslash escapes inside CSS (they can hide `url(`).
- It has no remote `<link>`, `<img>`, `@import`, `image-set(` or `url(...)`. The only remote
  addresses allowed are the two font hosts, `fonts.googleapis.com` and
  `fonts.gstatic.com`. Inline images may use `data:` URIs.
- The authoring check below rejects a slide file that breaks any of these. Fix
  the HTML. Do not weaken the check.

Run both declared checks using the bot's file and HTML tools:
- `html_has_slides`: exactly N sections, unique consecutive s1 through sN,
  with the same count as the outline and slide-copy JSON.
- `brand_vars_set`: required accent, ink, background and card CSS values are
  valid six-digit colors and agree with the brief's palette.

Store actual check evidence. Never claim a check ran from file presence alone.
This step cannot ask for an input. A broken earlier save, a missing template,
an unsupported style or a failed check is a named failure.

## Native authoring check

Run this check with Python 3. It needs no shell. The files stay in the work folder. Stock blue is valid
only when it appears in `brief.json.brand.palette`.
Stage HTML at `work/carousel.html` and copy at `work/slide_copy.json` first.
The check writes their saves only after validation passes.

```python
import html as H_, json, re
from pathlib import Path
def check(condition, message):
    if not condition: raise ValueError(message)
outline = json.loads(Path('prior/outline.json').read_text(encoding='utf-8'))
copy = json.loads(Path('work/slide_copy.json').read_text(encoding='utf-8'))
html = Path('work/carousel.html').read_text(encoding='utf-8')
n = int(outline['num_slides'])
# Inert-HTML rules: no script, no handlers, no embeds, no remote content except the two font hosts.
FONT_HOSTS = ('fonts.googleapis.com', 'fonts.gstatic.com')
def host_ok(url):
    m = re.match(r'(?:https:)?//([^/:?#\s]+)', url.strip(), re.I)
    return bool(m) and m.group(1).lower() in FONT_HOSTS
check(not re.search(r'<\s*script', html, re.I), 'slide HTML contains a script tag')
check(not re.search(r'<\s*(iframe|object|embed|base|form)\b', html, re.I), 'slide HTML contains an iframe, object, embed, base or form tag')
tags = re.findall(r'<[^>]*>', html)
check(not any(re.search(r'[\s"\'/](srcset|poster|action|formaction|ping)\s*=', tag, re.I) for tag in tags), 'slide HTML contains a srcset, poster, action or ping attribute')
# Character entities are decoded by the browser, so look at the decoded form too.
decoded = H_.unescape(html)
check(not re.search(r'(?:java|vb)script\s*:', re.sub(r'[\x00-\x20]+', '', H_.unescape(' '.join(tags))), re.I), 'slide HTML contains a javascript: address (maybe entity-encoded)')
styles = re.findall(r'<style[^>]*>(.*?)</style>', decoded, re.I | re.S)
styles += [a or b for a, b in re.findall(r'style\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', decoded, re.I)]
check(not any('\\' in s for s in styles), 'slide HTML has a backslash escape inside CSS')
check(not re.search(r'image-set\s*\(|\bsrc\s*\(', ' '.join(styles), re.I), 'slide HTML has image-set( or src( in CSS')
check(not any(re.search(r'[\s"\'/]on[a-z]+\s*=', tag, re.I) for tag in re.findall(r'<[^>]*>', html)), 'slide HTML contains an event-handler attribute')
check(not re.search(r'javascript\s*:', html, re.I), 'slide HTML contains a javascript: address')
check(not re.search(r'http-equiv\s*=\s*["\']?refresh', html, re.I), 'slide HTML contains a meta refresh')
check(not re.search(r'@import', html, re.I), 'slide HTML contains @import')
for tag in re.findall(r'<\s*link\b[^>]*>', html, re.I):
    href = re.search(r'href\s*=\s*["\']?([^"\'\s>]+)', tag, re.I)
    check(href and host_ok(href.group(1)), 'slide HTML has a link that is not a font host')
for tag in re.findall(r'<\s*(?:img|image|source|video|audio|input|use)\b[^>]*>', html, re.I):
    for src in re.findall(r'(?:src|href|xlink:href)\s*=\s*["\']?([^"\'\s>]+)', tag, re.I):
        check(src.lower().startswith('data:') or src.startswith('#'), 'slide HTML has a remote or file image source')
for target in re.findall(r'url\(\s*["\']?([^"\')]*)', html + ' ' + decoded, re.I):
    check(target.strip().lower().startswith('data:') or target.startswith('#') or host_ok(target), 'slide HTML has a url() that is not a font host or data URI')
ids = re.findall(r'<section[^>]*class="[^"]*\bslide\b[^"]*"[^>]*id="s(\d+)"', html) or re.findall(r'<section[^>]*id="s(\d+)"[^>]*class="[^"]*\bslide\b', html)
check(sorted(map(int, ids)) == list(range(1, n + 1)), 'slide sections differ from outline')
check(len(copy['slides']) == n, 'copy count differs from outline')
# Text is escaped: each headline and body is in the page escaped, and never raw when escaping changes it.
# One accent span is allowed, only inside a heading (h1 to h6), exactly as template.html shows it:
# <span class="hl">word</span>. Spans must be balanced, a heading may hold no other span, and a span anywhere else
# (a body paragraph, a card) is refused. Only that exact span, inside a heading, is ignored when looking for the
# escaped copy; any other tag still splits the text and fails.
HEAD = r'<h([1-6])\b[^>]*>(.*?)</h\1>'
check(len(re.findall(r'<span\b', html, re.I)) == len(re.findall(r'</span\s*>', html, re.I)), 'slide HTML has an unclosed or stray span')
check('<span class="hl">' not in re.sub(HEAD, '', html, flags=re.S), 'an accent span is outside a headline')
for _, inner in re.findall(HEAD, html, flags=re.S):
    check(len(re.findall(r'<span\b', inner, re.I)) == inner.count('<span class="hl">'), 'a heading holds a span that is not the accent span')
    check(inner.count('<span class="hl">') == inner.count('</span>'), 'a heading has an unclosed or stray span')
plain_html = re.sub(HEAD, lambda m: re.sub(r'<span class="hl">|</span>', '', m.group(0)), html, flags=re.S)
for slide in copy['slides']:
    for field in ('headline', 'body'):
        text = slide.get(field) or ''
        if not text:
            continue
        esc = {H_.escape(text, quote=False), H_.escape(text, quote=True)}
        check(any(e in plain_html for e in esc), 'slide %s: %s text missing or not escaped: %r' % (slide.get('n'), field, text[:30]))
        if text not in esc:
            check(text not in html, 'slide %s: raw (unescaped) %s text in the HTML: %r' % (slide.get('n'), field, text[:30]))
check('<meta charset="UTF-8">' in html, 'missing UTF-8 charset')
for key in ('--accent', '--ink', '--bg', '--card'):
    check(re.search(re.escape(key) + r'\s*:\s*#[0-9a-fA-F]{6}', html), 'missing brand color')
palette = (json.loads(Path('brief.json').read_text(encoding='utf-8')).get('brand') or {}).get('palette')
colors = {v.strip().lower() for v in (palette.values() if isinstance(palette, dict) else []) if isinstance(v, str)}
if '#3b82f6' not in colors:
    check('#3b82f6' not in html.lower(), 'stock blue left in template')
Path('saves').mkdir(exist_ok=True)
Path('saves/carousel_html.md').write_text(html, encoding='utf-8')
Path('saves/slide_copy.json').write_text(json.dumps(copy, ensure_ascii=False), encoding='utf-8')
print('authoring checks passed')
```
