#!/usr/bin/env python3
"""voiceover.py - make one narration MP3 with the ElevenLabs text-to-speech API. Standard library only.

One run sends the script text to ElevenLabs and spends the brand's ElevenLabs credits, so it is guarded:

  * The key comes from the environment variable ELEVENLABS_API_KEY, set for this one process, or from one
    line of standard input with --key-stdin. It is never a command line argument and never read from a file.
    It is never printed or written: every line this script prints is scrubbed of the key first.
  * The text comes from a file inside the work folder (the current folder). The voice id is an argument (this
    template ships none). The output is written inside the work folder.
  * The only host is api.elevenlabs.io over https. No redirect is ever followed (the key would follow it).
    The whole call has a deadline and a size cap. The reply is never trusted: an audio reply must really start
    like an MP3.
  * The call is made once and is never retried (a retry could be charged twice).
  * The last line on stdout is printed once, by one function: AUDIO_FILE: <relative path> or AUDIO_FAILED: <reason>.
    Server messages are stripped of control characters, scrubbed of the key and cut short before they are printed.
    No traceback is ever printed.

Request shape (ElevenLabs public docs, read 2026-11-22; not proven with a real account):
  POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128
  header xi-api-key, JSON body {"text", "model_id", optional "voice_settings"}; the success body is the audio.
  Errors are JSON {"detail": ...}: 401 bad key, 402 no credits, 429 rate limited, 404 voice not found, 422 invalid.
  https://elevenlabs.io/docs/api-reference/text-to-speech/convert

Usage
  voiceover.py --text-file work/vo-script.txt --voice-id VOICE_ID --out work/vo.mp3
               [--model-id eleven_multilingual_v2] [--output-format mp3_44100_128]
               [--stability 0.5] [--similarity-boost 0.75] [--style 0.0] [--speed 1.0] [--use-speaker-boost]
               [--timeout 120] [--max-bytes 41943040] [--key-stdin]

Exit codes: 0 saved | 1 provider or network failure, bad reply, deadline | 2 bad arguments or paths | 3 no key
(nothing was sent when the exit code is 2 or 3).
"""
import argparse
import http.client as _hc
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True

DEFAULT_BASE = "https://api.elevenlabs.io"
KEY_NAME = "ELEVENLABS_API_KEY"
DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_FORMAT = "mp3_44100_128"
MAX_TEXT_CHARS = 10000          # documented per-request limit of eleven_multilingual_v2; applied to every model
MAX_TEXT_FILE_BYTES = 80 * 1024
DEFAULT_MAX_BYTES = 40 * 1024 * 1024
LOOPBACK = ("127.0.0.1", "localhost")
UA = "r-reels-faceless-voiceover/1.0"
VOICE_RE = re.compile(r"[A-Za-z0-9_-]{8,64}")
MODEL_RE = re.compile(r"[a-z0-9_]{3,60}")
FORMAT_RE = re.compile(r"mp3_[0-9]{5}_[0-9]{2,3}")
KEY_RE = re.compile(r"[!-~]{8,200}")
TEXT_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f  ]+")
REASONS = {
    401: "the ElevenLabs key was refused",
    402: "not enough ElevenLabs credits for this request",
    429: "ElevenLabs is rate limiting this key; wait and try again",
    404: "ElevenLabs does not know that voice id",
    422: "ElevenLabs rejected the request",
}

_KEY = ""
_FINAL_DONE = False


class Usage(Exception):
    pass


class Failed(Exception):
    pass


class NoKey(Exception):
    pass


def clean(text, cap=200):
    """Server or user text made safe to print: control characters (newlines too) become spaces, length capped."""
    return _CONTROL.sub(" ", str(text))[:cap]


_ALNUM = re.compile(r"[^A-Za-z0-9]+")
WITHHELD = "<server message withheld: it held the key>"


def scrub(text, cap=200):
    """Print nothing that holds the key, however a server disguises it. Both the message and the key are reduced to
    ASCII letters and digits (so spaces, no-break or zero-width spaces, soft hyphens, byte-order marks and control
    characters between its characters do not hide it). A key whose reduced form has 8 or more characters that appears
    in the reduced message withholds the whole message. A shorter reduced key falls back to a plain replacement
    checked again with control characters deleted. Then the text is flattened to one line and cut."""
    text = str(text)
    if _KEY:
        reduced_key = _ALNUM.sub("", _KEY).lower()
        if len(reduced_key) >= 8 and reduced_key in _ALNUM.sub("", text).lower():
            return WITHHELD
        text = text.replace(_KEY, "<key>")
        if _KEY in _CONTROL.sub("", text):
            return WITHHELD
    return clean(text, cap)


def emit_final(ok, text):
    """The ONLY function that prints AUDIO_FILE or AUDIO_FAILED. It prints once."""
    global _FINAL_DONE
    if _FINAL_DONE:
        return
    _FINAL_DONE = True
    print("%s: %s" % ("AUDIO_FILE" if ok else "AUDIO_FAILED", scrub(text)), flush=True)


def check_base(url):
    """The real https host, or a loopback http address (tests only), parsed and compared exactly."""
    if url == DEFAULT_BASE:
        return url
    if not isinstance(url, str) or "@" in url or any(c in url for c in " \t\r\n\\"):
        raise Usage("--base-url is not allowed")
    u = urllib.parse.urlparse(url)
    try:
        port = u.port
    except ValueError:
        raise Usage("--base-url has an invalid port")
    if (u.scheme == "http" and u.hostname in LOOPBACK and port and "@" not in u.netloc
            and u.netloc == "%s:%d" % (u.hostname, port) and not u.path.strip("/")
            and not (u.params or u.query or u.fragment)):
        return "http://%s:%d" % (u.hostname, port)
    raise Usage("--base-url may only be %s (or http://127.0.0.1:PORT or http://localhost:PORT, for tests)" % DEFAULT_BASE)


def inside_work(path, what):
    work = os.path.realpath(os.getcwd())
    real = os.path.realpath(path)
    if real != work and not real.startswith(work + os.sep):
        raise Usage("%s must be inside the work folder (the current folder)" % what)
    return real


def read_key(use_stdin):
    raw = sys.stdin.readline().strip() if use_stdin else os.environ.get(KEY_NAME, "").strip()
    if not raw:
        raise NoKey("no ElevenLabs key: set %s for this command, or pass --key-stdin and send the key on standard input" % KEY_NAME)
    if not KEY_RE.fullmatch(raw):
        raise NoKey("the ElevenLabs key has an unusable shape (no spaces or control characters, 8 to 200 characters)")
    return raw


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_post(url, key, body, timeout, limit):
    """Return (status, bytes), reading at most limit+1 bytes. `timeout` is a deadline for the whole call.
    Raises Failed on a network problem, the deadline or a body over the cap."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg, application/json", "User-Agent": UA})
    handlers = [_NoRedirect()]
    if urllib.parse.urlparse(url).hostname in LOOPBACK:
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    end = time.monotonic() + timeout
    box = {}

    def work():
        try:
            try:
                with opener.open(req, timeout=min(timeout, 20)) as r:
                    chunks, got = [], 0
                    while got <= limit and time.monotonic() < end:
                        c = r.read(min(65536, limit + 1 - got))
                        if not c:
                            box["res"] = (r.status, b"".join(chunks))
                            return
                        chunks.append(c)
                        got += len(c)
                    box["res"] = "big" if got > limit else None
            except urllib.error.HTTPError as e:
                try:
                    box["res"] = (e.code, e.read(65536))
                except Exception:
                    box["res"] = (e.code, b"")
        except (urllib.error.URLError, OSError, ValueError, _hc.HTTPException) as e:
            box["err"] = type(getattr(e, "reason", e)).__name__
        except Exception as e:  # never let a worker error become a traceback
            box["err"] = type(e).__name__

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive() or ("res" not in box and "err" not in box):
        raise Failed("timed out after %ds waiting for ElevenLabs" % timeout)
    if box.get("err") in ("TimeoutError", "timeout"):
        raise Failed("timed out after %ds waiting for ElevenLabs" % timeout)
    if "err" in box:
        raise Failed("network error talking to ElevenLabs (%s)" % box["err"])
    if box.get("res") == "big":
        raise Failed("the reply is larger than the %d byte cap" % limit)
    if box.get("res") is None:
        raise Failed("timed out after %ds waiting for ElevenLabs" % timeout)
    return box["res"]


def error_text(status, raw):
    """A short reason for a non-200 reply. The server's own words are cleaned and capped by scrub() later."""
    base = REASONS.get(status)
    if status in (301, 302, 303, 307, 308):
        return "ElevenLabs answered with a redirect (HTTP %d); redirects are never followed" % status
    msg = ""
    try:
        detail = json.loads(raw.decode("utf-8", "replace")).get("detail")
        if isinstance(detail, dict):
            msg = str(detail.get("message") or detail.get("status") or "")
        elif isinstance(detail, list) and detail and isinstance(detail[0], dict):
            msg = str(detail[0].get("msg") or "")
        elif isinstance(detail, str):
            msg = detail
    except (ValueError, AttributeError):
        pass
    msg = scrub(msg) if msg else ""      # the provider's own words never print unless they are free of the key
    if base:
        return "%s (HTTP %d)%s" % (base, status, (": " + msg) if msg else "")
    return "ElevenLabs returned HTTP %d%s" % (status, (": " + msg) if msg else "")


def looks_like_mp3(raw):
    return len(raw) > 200 and (raw[:3] == b"ID3" or (raw[0] == 0xFF and raw[1] & 0xE0 == 0xE0))


def save_audio(raw, out):
    """Write the bytes through an exclusive temp file in the output folder, then os.replace. Refuses a symlink target."""
    if os.path.islink(out):
        raise Usage("the output path is a symbolic link")
    out_dir = os.path.dirname(os.path.abspath(out))
    inside_work(out_dir, "the output folder")
    os.makedirs(out_dir, exist_ok=True)
    inside_work(out_dir, "the output folder")
    fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".vo-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        if os.path.islink(out):
            raise Usage("the output path is a symbolic link")
        os.replace(tmp, out)
        inside_work(out, "the output file")
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def number(value, name, lo, hi):
    if value is None:
        return None
    if not lo <= value <= hi or value != value:
        raise Usage("%s must be between %g and %g" % (name, lo, hi))
    return float(value)


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Make one narration MP3 with ElevenLabs.",
                                 epilog="Key: environment variable %s, or --key-stdin." % KEY_NAME)
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--voice-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-id", default=DEFAULT_MODEL)
    ap.add_argument("--output-format", default=DEFAULT_FORMAT)
    ap.add_argument("--stability", type=float)
    ap.add_argument("--similarity-boost", type=float)
    ap.add_argument("--style", type=float)
    ap.add_argument("--speed", type=float)
    ap.add_argument("--use-speaker-boost", action="store_true")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    ap.add_argument("--key-stdin", action="store_true")
    ap.add_argument("--base-url", default=DEFAULT_BASE, help="tests only: http://127.0.0.1:PORT or http://localhost:PORT")
    return ap.parse_args(argv)


def run(argv):
    global _KEY
    try:
        a = parse_args(argv)
    except SystemExit as e:
        if e.code in (0, None):
            raise
        raise Usage("bad command line (run with --help)")
    base = check_base(a.base_url)
    if not VOICE_RE.fullmatch(a.voice_id):
        raise Usage("--voice-id may use letters, digits, - and _ only (8 to 64 characters)")
    if not MODEL_RE.fullmatch(a.model_id):
        raise Usage("--model-id may use lower-case letters, digits and _ only")
    if not FORMAT_RE.fullmatch(a.output_format):
        raise Usage("--output-format must be an mp3 format such as mp3_44100_128")
    if not 1 <= a.timeout <= 600 or not 1024 <= a.max_bytes <= 200 * 1024 * 1024:
        raise Usage("--timeout must be 1 to 600 seconds and --max-bytes 1 KiB to 200 MiB")
    if not a.out.lower().endswith(".mp3"):
        raise Usage("--out must end in .mp3")
    stab = number(a.stability, "--stability", 0, 1)
    sim = number(a.similarity_boost, "--similarity-boost", 0, 1)
    sty = number(a.style, "--style", 0, 1)
    spd = number(a.speed, "--speed", 0.7, 1.2)
    text_path = inside_work(a.text_file, "--text-file")
    out_real = inside_work(a.out, "--out")
    if os.path.islink(a.out):
        raise Usage("the output path is a symbolic link")
    if os.path.realpath(a.text_file) == out_real:
        raise Usage("--out must not be the text file")
    try:
        if not os.path.isfile(text_path) or os.path.getsize(text_path) > MAX_TEXT_FILE_BYTES:
            raise Usage("--text-file must be a text file of at most %d KB" % (MAX_TEXT_FILE_BYTES // 1024))
        with open(text_path, encoding="utf-8") as fh:
            text = fh.read().strip()
    except (OSError, UnicodeDecodeError):
        raise Usage("--text-file could not be read as UTF-8 text")
    if not text or TEXT_CONTROL.search(text):
        raise Usage("the text is empty or holds control characters")
    if len(text) > MAX_TEXT_CHARS:
        raise Usage("the text has %d characters; the limit for one request is %d" % (len(text), MAX_TEXT_CHARS))
    _KEY = read_key(a.key_stdin)
    body = {"text": text, "model_id": a.model_id}
    settings = {k: v for k, v in (("stability", stab), ("similarity_boost", sim), ("style", sty), ("speed", spd)) if v is not None}
    if a.use_speaker_boost:
        settings["use_speaker_boost"] = True
    if settings:
        body["voice_settings"] = settings
    url = "%s/v1/text-to-speech/%s?output_format=%s" % (base, urllib.parse.quote(a.voice_id, safe=""),
                                                       urllib.parse.quote(a.output_format, safe=""))
    status, raw = http_post(url, _KEY, body, a.timeout, a.max_bytes)
    if status != 200:
        raise Failed(error_text(status, raw))
    if not looks_like_mp3(raw):
        raise Failed("ElevenLabs answered 200 but the body is not an MP3 file")
    save_audio(raw, a.out)
    return os.path.relpath(out_real, os.path.realpath(os.getcwd())).replace(os.sep, "/")


def main(argv=None):
    try:
        rel = run(sys.argv[1:] if argv is None else argv)
    except Usage as e:
        emit_final(False, e)
        return 2
    except NoKey as e:
        emit_final(False, e)
        return 3
    except Failed as e:
        emit_final(False, e)
        return 1
    except SystemExit as e:
        return 0 if e.code in (0, None) else 2
    except BaseException:                    # no traceback, ever
        emit_final(False, "an unexpected error stopped the run")
        return 1
    emit_final(True, rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
