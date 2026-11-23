"""Pure faceless-recipe data checks. No process runner, network or installation.

`validate_beats` is run by check_beats.py. `private_brand` is only for CFW Social's order format:
outside CFW Social, write brief.json by hand. Failed checks return no replacement data.
"""
import json
import math
import re


def private_brand(claim, brief):
    """Validate the frozen winning claim; prepare only this order's private brief."""
    def check(condition):
        if not condition:
            raise ValueError("Invalid private claim")
    try:
        claim = json.loads(json.dumps(claim, allow_nan=False))
        result = json.loads(json.dumps(brief, allow_nan=False))
        oid, bid = claim["id"], claim["brandId"]
        check(isinstance(oid, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,120}", oid))
        check(isinstance(bid, str) and 1 <= len(bid) <= 120)
        task, snapshot = claim["taskOrder"], claim["brandDna"]
        brand = task["brand"]
        check(task["orderId"] == oid and brand["id"] == bid)
        check(type(snapshot["version"]) is int and snapshot["version"] == 1)
        check(set(snapshot) == {"version", "brandId", "renderProfile", "palette", "fonts"})
        check(snapshot["brandId"] == bid)
        check(all(brand.get(k) == snapshot[k] for k in ("palette", "fonts", "renderProfile")))
        check(isinstance(result, dict) and isinstance(result.get("brand", {}), dict))
        check(result.get("brand", {}).get("id", bid) == bid)
        for key in ("palette", "fonts"):
            check(isinstance(snapshot[key], dict))
            for name, value in snapshot[key].items():
                check(isinstance(name, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,39}", name))
                check(isinstance(value, str) and 1 <= len(value) <= 100)
                if key == "palette":
                    check(re.fullmatch(r"#[0-9a-fA-F]{6}", value))
        profile = snapshot["renderProfile"]
        check(profile is None or isinstance(profile, dict))
        profile = profile or {}
        allowed = {"version": None, "cta": {"line", "handle"},
                   "captions": {"font", "sizePx", "activeColor", "inactiveColor", "placement"},
                   "elevenlabs": {"voiceId", "modelId", "outputFormat", "stability", "similarityBoost", "style", "useSpeakerBoost"},
                   "heygen": {"voiceId", "avatarId"}}
        check(not set(profile) - set(allowed))
        for key, fields in allowed.items():
            if fields is not None and profile.get(key) is not None:
                check(isinstance(profile[key], dict) and not set(profile[key]) - fields)
        safe = {k: v for k, v in brand.items() if k in {
            "id", "slug", "name", "brief", "palette", "fonts", "typography", "logoUrl", "vizPrefs", "imageDirection", "renderProfile"}}
        name = safe.get("name") or claim.get("brandName")
        if name is not None:
            check(isinstance(name, str) and 0 < len(name) <= 200)
            safe["name"] = name
        for short, long in (("bg", "background"), ("fg", "text")):
            if short not in safe["palette"] and long in safe["palette"]:
                safe["palette"][short] = safe["palette"][long]
        for short, long in (("display", "headingFont"), ("body", "bodyFont")):
            if short not in safe["fonts"] and long in safe["fonts"]:
                safe["fonts"][short] = safe["fonts"][long]
        check(isinstance(safe.get("typography", {}), dict))
        safe["typography"] = {**safe["fonts"], **safe.get("typography", {})}
        cta = profile.get("cta") or {}
        check(all(isinstance(cta.get(k, ""), str) and len(cta.get(k, "")) <= 2000 for k in ("line", "handle")))
        safe["cta"], safe["handle"] = cta.get("line", ""), cta.get("handle", "")
        # Legacy local helpers read this alias; it comes only from the frozen profile.
        safe["elevenlabs"] = profile.get("elevenlabs") or {}
        result["brand"] = safe
        return result
    except (AttributeError, KeyError, TypeError, ValueError, RecursionError):
        raise ValueError("Invalid or mismatched private claim brand") from None


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Expected a finite timestamp")
    return float(value)


def validate_beats(plan, duration):
    """Reject unbounded filenames and gaps before any authoring or process call."""
    duration = number(duration)
    beats = plan.get("beats")
    if not isinstance(beats, list) or not beats or abs(number(plan["bed_duration"]) - duration) > 0.2:
        raise ValueError("Invalid beat list or bed duration")
    end, slugs = 0, set()
    for index, beat in enumerate(beats):
        start, stop = number(beat["start"]), number(beat["end"])
        if type(beat["index"]) is not int or beat["index"] != index or abs(start - end) >= 0.1 or stop <= start:
            raise ValueError("Beats must be ordered, contiguous and positive")
        end = stop
        if beat["kind"] == "graphics":
            slug = beat.get("slug")
            if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", slug) or slug in slugs:
                raise ValueError("Invalid or duplicate graphics slug")
            slugs.add(slug)
            scene = beat.get("scene") or {}
            if not isinstance(scene.get("title_html"), str) or not scene["title_html"].strip():
                raise ValueError("Graphics beat has no headline")
        elif beat["kind"] != "broll":
            raise ValueError("Unknown beat kind")
    if abs(end - duration) > 0.2:
        raise ValueError("Beats do not span voice bed")
    if beats[-1]["kind"] != "graphics" or beats[-1].get("scene", {}).get("type") != "cta":
        raise ValueError("Last beat must be a graphics CTA")
    return plan
