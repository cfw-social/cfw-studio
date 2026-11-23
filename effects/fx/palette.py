"""Palette loading. A palette is a JSON object of named colours plus optional role aliases.

Accepted shapes (all merged on top of DEFAULT_PALETTE):
  {"navy": "#0C1842", "amber": "#FDA107", ...}                 # named swatches
  {"roles": {"text": "offwhite", "accent": "amber"}}           # role -> swatch name or hex
  captions_v2 style: {"primary": "#FDFDFC", "punch": "#FDA107", "outline": "#0C1842", ...}
Effects ask for colours by role ("accent", "text", "outline", "bg", "glow", "secondary", "hot")
or by swatch name or by literal hex.
"""
import json, os

PRESETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets")
DEFAULT_PRESET = os.environ.get("FX_PALETTE", "navy-amber")

def list_presets():
    return sorted(f[:-5] for f in os.listdir(PRESETS) if f.endswith(".json")) if os.path.isdir(PRESETS) else []

# Built-in fallback (identical to presets/navy-amber.json) so the package works without the presets folder.
DEFAULT_PALETTE = {
    "name": "navy-amber",
    "swatches": {"navy": "#0C1842", "periwinkle": "#6962EE", "offwhite": "#FDFDFC",
                 "amber": "#FDA107", "redorange": "#F44C2D"},
    "roles": {"bg": "navy", "outline": "navy", "text": "offwhite", "paper": "offwhite",
              "accent": "amber", "punch": "amber", "glow": "amber",
              "secondary": "periwinkle", "note": "periwinkle", "hot": "redorange", "split": "redorange"},
}

def _hex(h):
    h = h.strip().lstrip("#")
    if len(h) == 3: h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def load_palette(src=None):
    """src: None (default preset) | preset name (presets/<name>.json) | path to JSON | dict | JSON string.
    Returns normalised dict {name, swatches, roles}."""
    pal = {"name": DEFAULT_PALETTE["name"], "swatches": dict(DEFAULT_PALETTE["swatches"]), "roles": dict(DEFAULT_PALETTE["roles"])}
    if src is None:
        src = DEFAULT_PRESET
        if not os.path.exists(os.path.join(PRESETS, src + ".json")): return pal
    if isinstance(src, str):
        preset = os.path.join(PRESETS, src + ".json")
        if os.path.exists(preset): src = json.load(open(preset))
        elif os.path.exists(src): src = json.load(open(src))
        else: src = json.loads(src)
    if "name" in src: pal["name"] = src["name"]
    for k, v in (src.get("swatches") or {}).items(): pal["swatches"][k] = v
    for k, v in (src.get("roles") or {}).items(): pal["roles"][k] = v
    for k, v in src.items():                      # flat keys: hex -> swatch/role
        if k in ("name", "swatches", "roles") or not isinstance(v, str) or not v.startswith("#"): continue
        if k in pal["roles"] or k in ("primary",):
            pal["roles"]["text" if k == "primary" else k] = v
        else:
            pal["swatches"][k] = v
    return pal

def color(pal, key, alpha=None):
    """Resolve role / swatch / '#hex' / (r,g,b) to an RGB (or RGBA) tuple of ints."""
    if isinstance(key, (tuple, list)): rgb = tuple(int(x) for x in key[:3])
    else:
        k = key
        for _ in range(4):
            if isinstance(k, str) and k.startswith("#"): break
            k = pal["roles"].get(k, pal["swatches"].get(k, k))
        if not (isinstance(k, str) and k.startswith("#")): raise KeyError(f"unknown colour {key!r}")
        rgb = _hex(k)
    return rgb + (int(alpha),) if alpha is not None else rgb

def colorf(pal, key):
    import numpy as np
    return np.array(color(pal, key), np.float32) / 255.0
