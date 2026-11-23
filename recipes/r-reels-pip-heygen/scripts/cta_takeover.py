#!/usr/bin/env python3
"""Decide whether step 05 draws the CTA end-card takeover (the picture-in-picture reel recipes).

The reel ends on ONE call to action, and step 05 never invents its copy.

  1. options.cta_card is not "on"                          -> no takeover.
  2. The planned background already contains a CTA beat:
     any beat of the beat list has
     kind "graphics" and scene.type "cta"                   -> no takeover, no scrim.
  3. CTA copy: --text, else inputs/cta/cta.json `text`, else the typed answer the bot writes
     as inputs/cta/cta.md (or cta.txt; plain text, an @handle or URL in it is the handle),
     else brand.cta. No copy at all                         -> no takeover (said so).
  4. Otherwise                                              -> takeover with that copy.

The handle comes from --handle, else the cta input's handle, else brand.handle, else none.
The brand is brief.json `brand`, or the --brand FILE when given (work/brand.json).

Writes the decision to --decision as JSON and prints nothing on stdout. The JSON holds
`takeover` (true/false), `text`, `handle`, `source`, `reason`. When a takeover is drawn and
--card-text is given, it also writes {"text", "handle"} there, the text file that
fill_page.py --card cta reads: the copy is escaped by that filler, never put into a shell command
and never passed to `eval`. The reason line also goes to stderr. Bad input (missing or malformed
beat list, unreadable JSON) exits 2.

  python3 "$RECIPE_DIR/scripts/cta_takeover.py" --brief brief.json \
         --beats prior/beat_list.json --cta inputs/cta/cta.json --cta-card on \
         --decision work/cta-decision.json --card-text work/cta/text.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cta_copy  # the shared rule for reading inputs/cta/ (cta.json, then cta.md / cta.txt)


class InputError(Exception):
    pass


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        raise InputError("%s %s could not be read: %s" % (what, path, e))


def text_field(obj, key, where):
    v = obj.get(key) if isinstance(obj, dict) else None
    if v is None:
        return ""
    if not isinstance(v, str):
        raise InputError("%s `%s` is not text" % (where, key))
    return v.strip()


def planned_cta_beat(beats_path):
    """The latest planned CTA beat anywhere in the timeline, else None."""
    if not os.path.isfile(beats_path):
        raise InputError("beat list %s is missing" % beats_path)
    bl = load_json(beats_path, "beat list")
    beats = bl.get("beats") if isinstance(bl, dict) else None
    if not isinstance(beats, list) or not beats or not all(isinstance(b, dict) for b in beats):
        raise InputError("beat list %s has no beats" % beats_path)
    try:
        ordered = sorted(beats, key=lambda b: float(b["end"]), reverse=True)
    except (KeyError, TypeError, ValueError):
        raise InputError("beat list %s has a beat without a numeric `end`" % beats_path)
    for beat in ordered:
        scene = beat.get("scene") if isinstance(beat.get("scene"), dict) else {}
        if beat.get("kind") == "graphics" and str(scene.get("type") or "").strip().lower() == "cta":
            return beat
    return None


def decide(brief_path, beats_path, cta_path, cta_card, text_arg="", handle_arg="", brand_path=""):
    if brand_path:
        brand = load_json(brand_path, "brand")
    else:
        brief = load_json(brief_path, "brief") if brief_path and os.path.isfile(brief_path) else {}
        brand = brief.get("brand") if isinstance(brief, dict) else {}
    if not isinstance(brand, dict):
        brand = {}
    cta, cta_src = {}, "inputs/cta/cta.json"
    if cta_path and os.path.isfile(cta_path):
        cta = load_json(cta_path, "CTA input")
        if not isinstance(cta, dict):
            raise InputError("CTA input %s is not a JSON object" % cta_path)
    elif cta_path:
        # No cta.json: the bot writes a typed answer as inputs/cta/<id>.md, so read cta.md / cta.txt beside it.
        try:
            got, cta_src = cta_copy.read_cta_dir(os.path.dirname(cta_path) or ".")
        except cta_copy.Bad as e:
            raise InputError(str(e))
        cta = got or {}

    cta_text = text_field(cta, "text", cta_src)
    brand_cta = text_field(brand, "cta", "brand")
    text, source = "", ""
    for value, name in ((text_arg.strip(), "CTA_TEXT"), (cta_text, cta_src),
                        (brand_cta, "brand.cta")):
        if value:
            text, source = value, name
            break
    handle = (handle_arg.strip() or text_field(cta, "handle", cta_src)
              or text_field(brand, "handle", "brand"))

    beat = planned_cta_beat(beats_path)
    d = {"takeover": False, "text": "", "handle": "", "source": None, "cta_beat": None}
    if (cta_card or "").strip().lower() != "on":
        d["reason"] = "end card off (options.cta_card=%s); no takeover drawn" % (cta_card or "off")
    elif beat is not None:
        d["cta_beat"] = {k: beat.get(k) for k in ("index", "slug", "start", "end")}
        d["reason"] = ("end card skipped: the planned background already contains a CTA beat "
                       "(beat %s %s, %s-%s s, scene.type=cta); no second CTA and no scrim drawn"
                       % (beat.get("index"), beat.get("slug") or "", beat.get("start"), beat.get("end")))
        if source:
            d["reason"] += "; the %s copy was not drawn" % source
    elif not text:
        d["reason"] = ("end card skipped: no CTA copy (no inputs/cta/ text, no brand.cta); "
                       "step 05 never invents copy")
    else:
        d.update(takeover=True, text=text, handle=handle, source=source,
                 reason="end card drawn from %s%s" % (source, " with handle" if handle else ", no handle line"))
    return d


def main(argv=None):
    p = argparse.ArgumentParser(description="Decide the picture-in-picture reel CTA end-card takeover.")
    p.add_argument("--brief", default="brief.json", help="order brief; its `brand` gives cta/handle")
    p.add_argument("--brand", default="", help="a brand JSON file to use instead of the brief's `brand`")
    p.add_argument("--beats", default="prior/beat_list.json")
    p.add_argument("--cta", default="inputs/cta/cta.json")
    p.add_argument("--cta-card", default="on")
    p.add_argument("--text", default="", help="explicit CTA copy (wins over inputs/cta/ and brand.cta)")
    p.add_argument("--handle", default="", help="explicit handle (wins over inputs/cta/ and brand.handle)")
    p.add_argument("--decision", default="", help="write the decision JSON here")
    p.add_argument("--card-text", default="", help="when a takeover is drawn, write its text file for fill_page.py here")
    a = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        d = decide(a.brief, a.beats, a.cta, a.cta_card, a.text, a.handle, a.brand)
    except InputError as e:
        sys.stderr.write("cta_takeover.py: FAILED - %s\n" % e)
        return 2
    if a.decision:
        with open(a.decision, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
    if a.card_text and d["takeover"]:
        os.makedirs(os.path.dirname(a.card_text) or ".", exist_ok=True)
        with open(a.card_text, "w", encoding="utf-8") as fh:
            json.dump({"text": d["text"], "handle": d["handle"]}, fh)
    sys.stderr.write("[pip] %s\n" % d["reason"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
