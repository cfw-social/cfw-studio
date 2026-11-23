#!/usr/bin/env python3
"""Build the end-card spec (cta-card.json) from the brand palette in plan.json and the
resolved CTA copy (cta.json, written by scripts/cta_copy.py).

Usage:
  python3 cta-card.py PLAN.json CTA.json OUT-SPEC.json [--project DIR --gsap FILE] [--duration S]
  With --project, also writes DIR/index.html + gsap.min.js: an animated HyperFrames
  composition of the card that b-hyperframes' hf_render.py renders.

CTA.json keys: text (hero line, REQUIRED: empty stops the script, generic copy such as
"FOLLOW FOR MORE" is never invented; the caller skips the card instead), handle (EMPTY: the
handle layer is omitted, never a placeholder), brandName (EMPTY: the kicker is omitted).

Every text goes into the page HTML-escaped. Colours must be 6-digit hex.
Prints the layer types it emitted, one per line, so the caller's log shows whether a handle line shipped.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import page_text  # noqa: E402


# The renderer takes a project DIRECTORY holding index.html, not the .json spec. So the
# spec is also written out as a HyperFrames project: one full-frame composition whose GSAP
# timeline plays the scale-pop entry, staggers the kicker, hero words and handle in, draws the
# arrow at appearAt and keeps the glow and arrow moving to the last frame.
def write_project(card: dict, project_dir: str, gsap_src: str) -> None:
    import shutil
    if not os.path.isfile(gsap_src):
        raise SystemExit(f"cta-card.py: gsap.min.js not found at {gsap_src}; never load a CDN copy")
    os.makedirs(project_dir, exist_ok=True)
    shutil.copy(gsap_src, os.path.join(project_dir, "gsap.min.js"))
    dur = round(float(card["duration"]), 3)
    w, h = card["size"]
    entry = card.get("entry") or {}
    pop_from, pop_dur = float(entry.get("from", 0.92)), float(entry.get("duration", 0.35))
    parts, css = [], []
    for n, layer in enumerate(card["layers"]):
        kind, cls = layer["type"], f"l{n}"
        if kind == "arrow":
            (x0, y0), (x1, y1) = layer["from"], layer["to"]
            css.append(f"#cta-card .{cls}{{left:{x0 - 40}px;top:{y0}px;width:80px;height:{y1 - y0 + 40}px;}}"
                       f"#cta-card .{cls} .shaft{{left:36px;top:0;width:8px;height:{y1 - y0}px;background:{layer['color']};"
                       f"border-radius:4px;transform-origin:50% 0;}}"
                       f"#cta-card .{cls} .head{{left:12px;top:{y1 - y0 - 24}px;width:56px;height:56px;"
                       f"border-right:8px solid {layer['color']};border-bottom:8px solid {layer['color']};"
                       f"border-radius:4px;transform:rotate(45deg);}}")
            parts.append(f'<div class="layer arrow {cls}"><div class="shaft"></div><div class="head"></div></div>')
            continue
        size = int(layer.get("fontSize", 52 if kind == "kicker" else 80))
        font = "'Oswald', sans-serif" if kind in ("hero", "kicker") else "'Inter', sans-serif"
        weight = int(layer.get("weight", 700))
        css.append(f"#cta-card .{cls}{{top:{int(layer['y'])}px;color:{layer['color']};font-family:{font};font-size:{size}px;"
                   f"font-weight:{weight};opacity:{float(layer.get('opacity', 1.0))};"
                   + ("letter-spacing:0.18em;" if kind == "kicker" else "")
                   + ("text-transform:uppercase;line-height:1.0;" if kind == "hero" else "") + "}")
        if kind == "hero":
            # the brand name (the kicker text) is ONE unit: a nowrap span whose words are joined by
            # non-breaking spaces, so the headline never splits it ("FOLLOW TEST / BRAND FOR / MORE").
            norm = lambda t: t.strip(".,!?:;'\"()").upper()
            keep = [norm(t) for t in next((l["text"] for l in card["layers"] if l["type"] == "kicker"), "").split()]
            toks, units, i = layer["text"].split(), [], 0
            while i < len(toks):
                if keep and [norm(t) for t in toks[i:i + len(keep)]] == keep:
                    units.append('<span class="word brand">'
                                 + "&#160;".join(page_text.esc(t) for t in toks[i:i + len(keep)]) + "</span>")
                    i += len(keep)
                else:
                    units.append(f'<span class="word">{page_text.esc(toks[i])}</span>')
                    i += 1
            words = " ".join(units)
            parts.append(f'<div class="layer hero {cls}" data-size="{size}">{words}</div>')
        else:
            parts.append(f'<div class="layer {kind} {cls}" data-size="{size}">{page_text.esc(layer["text"])}</div>')
    accent = next((l["color"] for l in card["layers"] if l["type"] == "arrow"), "#ffffff")
    arrow_at = next((float(l.get("appearAt", 0.5)) for l in card["layers"] if l["type"] == "arrow"), 0.5)
    bobs = max(0, int((dur - arrow_at - 0.6) / 0.5) * 2 - 1)
    css_text, body_text = "".join(css), "\n        ".join(parts)
    # fit the headline and the kicker before the timeline is built, and again once fonts load.
    fit_js = r'''        // the brand name is one hero unit (.word.brand, nowrap) and never breaks. The units go on
        // the fewest lines (max 3) whose most balanced split fits HERO_MAX_W ((1080 - 2 x 60) / 1.04 breathe),
        // at the design size when possible, else the font shrinks; at HERO_MIN a unit still wider than the
        // safe width (a very long brand name) shrinks on its own. The kicker stays on one line inside
        // KICKER_MAX_W. Refit once fonts load. The text is never cut.
        var HERO_MAX_W = 920, HERO_MAX_LINES = 3, HERO_MIN = 60, KICKER_MAX_W = 960;
        function fitOne(el, base, maxW) {
          el.style.fontSize = base + "px";
          var w = el.scrollWidth;
          if (w <= maxW) return;
          var size = Math.floor(base * maxW / w);
          el.style.fontSize = size + "px";
          while (size > 8 && el.scrollWidth > maxW) { size -= 1; el.style.fontSize = size + "px"; }
        }
        function splitLines(ws, gap) {
          var n = ws.length;
          function span(a, b) { var s = gap * (b - a - 1); for (var i = a; i < b; i++) s += ws[i]; return s; }
          for (var k = 1; k <= Math.min(HERO_MAX_LINES, n); k++) {
            var cuts = [], best = null, bestW = Infinity;
            if (k === 1) cuts.push([]);
            if (k === 2) for (var a = 1; a < n; a++) cuts.push([a]);
            if (k === 3) for (var b = 1; b < n - 1; b++) for (var c = b + 1; c < n; c++) cuts.push([b, c]);
            cuts.forEach(function (cut) {
              var edges = [0].concat(cut, [n]), widest = 0;
              for (var j = 0; j < k; j++) widest = Math.max(widest, span(edges[j], edges[j + 1]));
              if (widest < bestW) { bestW = widest; best = edges; }
            });
            if (bestW <= HERO_MAX_W) return best;
          }
          return null;
        }
        function fitHero() {
          var hero = document.querySelector("#cta-card .hero");
          if (!hero) return;
          var units = Array.prototype.slice.call(hero.querySelectorAll(".word"));
          if (!units.length) return;
          var size = parseFloat(hero.getAttribute("data-size")) || 110, edges = null;
          for (;;) {
            hero.style.fontSize = size + "px";
            units.forEach(function (u) {
              u.style.fontSize = "";
              if (size <= HERO_MIN && u.scrollWidth > HERO_MAX_W) fitOne(u, size, HERO_MAX_W);
            });
            edges = splitLines(units.map(function (u) { return u.scrollWidth; }), size * 0.28);
            if (edges || size <= 8) break;
            size = size > HERO_MIN ? Math.max(HERO_MIN, Math.floor(size * 0.94)) : size - 2;
          }
          if (!edges) edges = [0, units.length];
          var old = Array.prototype.slice.call(hero.querySelectorAll(".line"));
          for (var j = 0; j + 1 < edges.length; j++) {
            var row = document.createElement("div");
            row.className = "line";
            for (var i = edges[j]; i < edges[j + 1]; i++) row.appendChild(units[i]);
            hero.appendChild(row);
          }
          old.forEach(function (r) { hero.removeChild(r); });
        }
        function fitCard() {
          var kicker = document.querySelector("#cta-card .kicker");
          if (kicker) fitOne(kicker, parseFloat(kicker.getAttribute("data-size")) || 52, KICKER_MAX_W);
          fitHero();
        }
        fitCard();
        if (document.fonts && document.fonts.ready) { document.fonts.ready.then(fitCard); }
'''
    doc = f'''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={w}, height={h}" />
    <script src="gsap.min.js"></script>
    <style>
      @font-face {{ font-family: "Oswald"; src: local("Oswald"); }}
      @font-face {{ font-family: "Inter"; src: local("Inter"); }}
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {w}px; height: {h}px; overflow: hidden; background: {card['background']}; }}
      #cta-card {{ position: relative; width: {w}px; height: {h}px; overflow: hidden; background: {card['background']}; }}
      #cta-card .glow {{ position: absolute; left: -260px; top: 260px; width: 1100px; height: 1100px;
        background: radial-gradient(circle, {accent}33 0%, transparent 62%); }}
      #cta-card .card {{ position: absolute; inset: 0; transform-origin: 50% 45%; }}
      #cta-card .layer {{ position: absolute; left: 60px; right: 60px; text-align: center; }}
      #cta-card .hero {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 0 0.28em; }}
      #cta-card .word {{ display: inline-block; }}
      #cta-card .hero .line {{ flex: 0 0 100%; display: flex; justify-content: center; gap: 0 0.28em; }}
      #cta-card .hero .word {{ flex: none; }}
      #cta-card .word.brand, #cta-card .kicker {{ white-space: nowrap; }}
      #cta-card .arrow, #cta-card .arrow div {{ position: absolute; right: auto; }}
      {css_text}
    </style>
  </head>
  <body>
    <div id="cta-card" data-composition-id="cta-card" data-start="0" data-duration="{dur}"
         data-width="{w}" data-height="{h}">
      <div class="glow"></div>
      <div class="card">
        {body_text}
      </div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      (function () {{
        var DUR = {dur};
{fit_js}        var tl = gsap.timeline({{ paused: true }});
        tl.fromTo("#cta-card .glow", {{ x: -120, y: 80, opacity: 0.4 }},
          {{ x: 360, y: -140, opacity: 1, duration: DUR, ease: "sine.inOut" }}, 0);
        tl.fromTo("#cta-card .card", {{ scale: {pop_from}, opacity: 0 }},
          {{ scale: 1, opacity: 1, duration: {pop_dur}, ease: "back.out(2)" }}, 0);
        tl.from("#cta-card .kicker", {{ y: -40, opacity: 0, duration: 0.4, ease: "power3.out" }}, 0.08);
        tl.from("#cta-card .word", {{ y: 90, opacity: 0, duration: 0.45, ease: "power4.out", stagger: 0.07 }}, 0.14);
        tl.to("#cta-card .hero", {{ scale: 1.04, duration: Math.max(0.5, DUR - 0.9), ease: "sine.inOut" }}, 0.8);
        tl.from("#cta-card .handle", {{ y: 40, opacity: 0, duration: 0.4, ease: "power3.out" }}, 0.42);
        tl.from("#cta-card .arrow .shaft", {{ scaleY: 0, duration: 0.3, ease: "power2.out" }}, {arrow_at});
        tl.from("#cta-card .arrow .head", {{ opacity: 0, y: -30, duration: 0.25, ease: "back.out(3)" }}, {arrow_at + 0.2});
        tl.to("#cta-card .arrow", {{ y: 24, duration: 0.25, ease: "sine.inOut", yoyo: true, repeat: {bobs} }}, {arrow_at + 0.5});
        window.__timelines["cta-card"] = tl;
      }})();
    </script>
  </body>
</html>
'''
    with open(os.path.join(project_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(doc)


HEX6 = re.compile(r"#?[0-9A-Fa-f]{6}")


def hex6(v, what):
    if not isinstance(v, str) or not HEX6.fullmatch(v.strip()):
        raise SystemExit(f"cta-card.py: {what} must be a 6-digit hex colour")
    return v.strip().lstrip("#")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("cta")
    ap.add_argument("out")
    ap.add_argument("--project", default="")
    ap.add_argument("--gsap", default="")
    ap.add_argument("--duration", type=float, default=3.0)
    a = ap.parse_args(argv[1:])
    with open(a.plan, encoding="utf-8") as fh:
        brand = json.load(fh)["brand"]
    bg, accent, fg = (hex6(brand[k], "brand." + k) for k in ("bg", "accent", "fg"))
    with open(a.cta, encoding="utf-8") as fh:
        copy = json.load(fh)
    cta_text = str(copy.get("text") or "").strip()
    if not cta_text:
        print("cta-card.py: the CTA text is empty; the end card never invents copy. "
              "Skip the card when the order has no CTA text.", file=sys.stderr)
        return 2
    cta_handle = page_text.strip_scheme(str(copy.get("handle") or "").strip())   # a card shows brand.example/x, not https://
    brand_name = str(copy.get("brandName") or "").strip()
    for what, value in (("text", cta_text), ("handle", cta_handle), ("brandName", brand_name)):
        try:
            page_text.refuse_addresses(value, "the CTA " + what)
        except ValueError as exc:
            print("cta-card.py: %s" % exc, file=sys.stderr)
            return 2
    duration = a.duration

    layers: list[dict] = []
    if brand_name:
        layers.append({"type": "kicker", "text": brand_name.upper(), "color": f"#{accent}", "y": 540})
    layers.append(
        {"type": "hero", "text": cta_text, "color": f"#{fg}", "y": 760, "fontSize": 110, "weight": 800, "wrap": True}
    )
    if cta_handle:
        layers.append(
            {"type": "handle", "text": cta_handle, "color": f"#{fg}", "y": 1180, "fontSize": 56, "opacity": 0.72}
        )
    layers.append({"type": "arrow", "from": [540, 1320], "to": [540, 1420], "color": f"#{accent}", "appearAt": 0.5})

    card = {
        "duration": duration,
        "fps": 30,
        "size": [1080, 1920],
        "background": f"#{bg}",
        "layers": layers,
        "entry": {"type": "scale-pop", "from": 0.92, "to": 1.0, "duration": 0.35, "sfx": "impact-sub"},
        "exit": {"type": "none"},
    }
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(card, fh, indent=2)
        fh.write("\n")
    if a.project:
        if not a.gsap:
            raise SystemExit("cta-card.py: --project needs --gsap FILE (a local GSAP build)")
        write_project(card, a.project, a.gsap)
        print(f"[spotlight] cta-card project: {a.project}/index.html ({card['duration']:.3f}s)")
    for layer in layers:
        print(f"[spotlight] cta-card layer: {layer['type']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
