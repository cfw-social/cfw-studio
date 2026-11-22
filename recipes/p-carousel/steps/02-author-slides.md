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
import json, re
from pathlib import Path
def check(condition, message):
    if not condition: raise ValueError(message)
outline = json.loads(Path('prior/outline.json').read_text(encoding='utf-8'))
copy = json.loads(Path('work/slide_copy.json').read_text(encoding='utf-8'))
html = Path('work/carousel.html').read_text(encoding='utf-8')
n = int(outline['num_slides'])
ids = re.findall(r'<section[^>]*class="[^"]*\bslide\b[^"]*"[^>]*id="s(\d+)"', html) or re.findall(r'<section[^>]*id="s(\d+)"[^>]*class="[^"]*\bslide\b', html)
check(sorted(map(int, ids)) == list(range(1, n + 1)), 'slide sections differ from outline')
check(len(copy['slides']) == n, 'copy count differs from outline')
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
