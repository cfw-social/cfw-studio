"""The shape of format.json: numbers and short labels only. Standard library only.

format.json is the only thing kept from the reference reel. This check is what keeps it free of
words: every key is on a fixed list, every label matches a fixed pattern in full, every number has
an exact type and is rounded to two decimals (cut times to one), and the cut times are few,
increasing and inside the clip. That removes most of the room to hide anything, not all of it: a
person who sets out to encode a short message in the gaps between numbers could still do so. This
check is not proof that nothing was taken.
"""
import math
import re

from rs_common import Stop

HOOK_TYPES = ("question", "claim", "stat", "story", "other")
INT_KEYS = ("width", "height", "word_count", "cut_count")
FLOAT_KEYS = ("duration_s", "fps", "speech_span_s", "first_word_at_s", "wpm", "speech_share",
              "cuts_per_10s", "mean_shot_s", "scene_threshold")
BEAT_FLOATS = ("start_s", "end_s", "share")
LABEL = re.compile(r"(hook|point_[1-9]|cta)")
STRUCTURE = re.compile(r"hook(, [1-9] points?)?(, cta)?")
MAX_CUTS_PER_SECOND = 10


def _int(v, name):
    if type(v) is not int or v < 0 or v > 100000:
        raise Stop("format.json: %s must be a whole number of 0 or more" % name, 1)


def _float(v, name, top=1_000_000):
    if type(v) not in (int, float) or not math.isfinite(v) or v < 0 or v > top or round(v, 2) != v:
        raise Stop("format.json: %s must be a number of 0 or more, rounded to two decimals" % name, 1)


def validate_format(obj):
    """Raise Stop unless obj is a clean format description. Returns obj."""
    if not isinstance(obj, dict):
        raise Stop("format.json: not an object", 1)
    allowed = {"format_version", "orientation", "cut_times_s", "hook", "beats", "structure"} | set(INT_KEYS) | set(FLOAT_KEYS)
    extra = set(obj) - allowed
    if extra:
        raise Stop("format.json: unexpected key (%s)" % sorted(extra)[0][:20], 1)
    if type(obj.get("format_version")) is not int or obj["format_version"] != 1:
        raise Stop("format.json: format_version must be the whole number 1", 1)
    for k in INT_KEYS:
        if k not in obj:
            raise Stop("format.json: missing %s" % k, 1)
        _int(obj[k], k)
    for k in FLOAT_KEYS:
        if k not in obj:
            raise Stop("format.json: missing %s" % k, 1)
        _float(obj[k], k)
    if obj.get("orientation") not in ("portrait", "landscape", "square"):
        raise Stop("format.json: bad orientation", 1)
    dur = obj["duration_s"]
    cuts = obj.get("cut_times_s")
    if not isinstance(cuts, list) or len(cuts) > math.ceil(MAX_CUTS_PER_SECOND * dur):
        raise Stop("format.json: cut_times_s must be a short list of numbers", 1)
    last = 0.0
    for c in cuts:
        _float(c, "cut_times_s")
        if round(c, 1) != c:
            raise Stop("format.json: cut_times_s must be rounded to one decimal", 1)
        if not last < c < dur:
            raise Stop("format.json: cut_times_s must increase and stay inside the clip", 1)
        last = c
    if obj["cut_count"] != len(cuts):
        raise Stop("format.json: cut_count does not match cut_times_s", 1)
    hook = obj.get("hook")
    if not isinstance(hook, dict) or set(hook) != {"type", "type_source", "seconds"}:
        raise Stop("format.json: bad hook", 1)
    if hook["type"] not in HOOK_TYPES or hook["type_source"] not in ("rules", "given"):
        raise Stop("format.json: bad hook label", 1)
    _float(hook["seconds"], "hook.seconds")
    beats = obj.get("beats")
    if not isinstance(beats, list) or not 1 <= len(beats) <= 8:
        raise Stop("format.json: beats must be a list of 1 to 8", 1)
    for b in beats:
        if not isinstance(b, dict) or set(b) != {"label", "words"} | set(BEAT_FLOATS) \
                or not isinstance(b["label"], str) or not LABEL.fullmatch(b["label"]):
            raise Stop("format.json: bad beat", 1)
        _int(b["words"], "beat.words")
        for k in BEAT_FLOATS:
            _float(b[k], "beat." + k)
    s = obj.get("structure")
    if not isinstance(s, str) or not STRUCTURE.fullmatch(s):
        raise Stop("format.json: bad structure", 1)
    return obj
