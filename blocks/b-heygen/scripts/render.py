#!/usr/bin/env python3
"""Render an avatar narration video through the HeyGen API and download it.

Reads the narration text from a file, creates the video, polls until it is done,
downloads the MP4 into the work folder. The API key arrives privately (the
HEYGEN_API_KEY environment variable of this process, or one line on standard
input with --key-stdin). It is never printed, logged or written.
Exit codes: 0 done, 1 failed, 2 bad usage or input, 3 key missing.
See ../README.md. Shapes follow HeyGen's public v3 docs (read 2026-11-22).
"""
import argparse
import ipaddress
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_HOST = "https://api.heygen.com"
CREATE_PATH = "/v3/videos"
STATUS_PATH = "/v3/videos/"  # + video id
RESOLUTIONS = ("4k", "1080p", "720p")
ASPECT_RATIOS = ("16:9", "9:16", "4:5", "5:4", "1:1", "auto")
ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")  # always used with fullmatch
COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")
KEY_RE = re.compile(r"[\x21-\x7e]{8,512}")
CONTROL_RE = re.compile("[\x00-\x1f\x7f\x85\u2028\u2029]")
LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
LOCAL_HOSTS = ("127.0.0.1", "localhost")
SECRET = [""]  # the key, so that every printed line can be scrubbed


def safe_text(value, limit=300):
    """Scrub the key, strip control characters, then cut. Used on everything printed."""
    text = str(value)
    if SECRET[0]:
        text = text.replace(SECRET[0], "[redacted]")
        # a key with control or format characters inserted in it: look for it in a copy with those deleted
        squeezed = "".join(c for c in text if unicodedata.category(c) not in ("Cc", "Cf", "Zl", "Zp"))
        if SECRET[0] in squeezed:
            text = squeezed.replace(SECRET[0], "[redacted]")
    return CONTROL_RE.sub(" ", text)[:limit]


def is_local_base(url):
    """True only for http://127.0.0.1[:port] or http://localhost[:port], nothing else."""
    if CONTROL_RE.search(url) or " " in url:
        return False
    try:
        parts = urllib.parse.urlsplit(url)
        parts.port
    except ValueError:
        return False
    return (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS and "@" not in parts.netloc
            and parts.path in ("", "/") and not parts.query and not parts.fragment)


def private_host(host):
    """True when a download host must be refused. Judges the written address only.

    Accepted: a DNS name with a dot (ASCII letters, digits, hyphens; the last label has a letter),
    or an IPv4 address in plain dotted-quad form that is publicly routable. Refused: IPv6 literals,
    single-label names, localhost in any form, number forms (decimal, hex, octal, short), and every
    loopback, private, link-local, carrier-grade NAT, multicast and reserved address."""
    if not host:
        return True
    host = host.lower()
    if host.endswith("."):
        host = host[:-1]
    if not host or ":" in host or len(host) > 253:
        return True  # empty, or an IPv6 literal
    labels = host.split(".")
    if len(labels) < 2 or not all(LABEL_RE.fullmatch(label) for label in labels):
        return True  # single label, or characters a public name never has
    if labels[-1] == "localhost" or host == "localhost":
        return True
    last = labels[-1]
    if last.isdigit() or last.startswith("0x"):
        # numeric form: only a plain dotted quad is understood, and it must be a public address
        if len(labels) != 4 or not all(l.isdigit() and (l == "0" or not l.startswith("0")) for l in labels):
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return True
        return (not ip.is_global) or ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_private
    return False


def limit_read_time(resp, seconds):
    """Make the next read give up after `seconds` (never more than the time left)."""
    try:
        resp.fp.raw._sock.settimeout(max(0.1, seconds))
    except AttributeError:
        pass


def place(tmp_path, target, work):
    """Move a finished temporary file onto target. Refuses a target that is a link."""
    if os.path.islink(target):
        raise Stop("%s is a symbolic link; refusing to write through it" % target.name, 2)
    os.replace(tmp_path, target)
    if not target.resolve().is_relative_to(work):
        raise Stop("the written file is not inside the work folder", 2)


def write_text_atomic(target, text, work):
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".b-heygen-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        place(tmp, target, work)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Stop(Exception):
    def __init__(self, message, code, transient=False):
        super().__init__(message)
        self.code = code
        self.transient = transient


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


class Client:
    def __init__(self, base, key):
        self.base = base
        self.key = key

    def scrub(self, text):
        return safe_text(text)

    def call(self, method, path, body=None, query=None):
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"x-api-key": self.key, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with OPENER.open(req, timeout=60) as resp:
                raw = resp.read(1 << 20)
        except urllib.error.HTTPError as err:
            if 300 <= err.code < 400:
                raise Stop("HeyGen answered with a redirect (HTTP %d); redirects are not followed "
                           "on a request that carries the key" % err.code, 1)
            detail = safe_text(err.read(65536).decode("utf-8", "replace").strip())
            raise Stop("HeyGen returned HTTP %d: %s" % (err.code, detail), 1, transient=err.code >= 500 or err.code == 429)
        except (urllib.error.URLError, OSError) as err:
            raise Stop("could not reach HeyGen: %s" % self.scrub(err), 1, transient=True)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise Stop("HeyGen returned something that is not JSON", 1)
        if not isinstance(parsed, dict):
            raise Stop("HeyGen returned an unexpected JSON shape", 1)
        return parsed


def download(url, dest, max_bytes, deadline_s, work, test_mode):
    """Download the finished video. The key is NOT sent. No redirects."""
    try:
        parts = urllib.parse.urlsplit(url)
        parts.port
    except ValueError:
        raise Stop("the video URL is not valid", 1)
    if CONTROL_RE.search(url) or " " in url or "@" in parts.netloc or not parts.hostname:
        raise Stop("the video URL is not valid", 1)
    if test_mode:
        if not (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS):
            raise Stop("test mode: the video URL must be on 127.0.0.1 or localhost", 1)
    else:
        if parts.scheme != "https":
            raise Stop("the video URL is not https; refusing to download", 1)
        if private_host(parts.hostname):
            raise Stop("the video URL points at a local or private address; refusing to download", 1)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".b-heygen-")
    started = time.monotonic()
    try:
        with os.fdopen(fd, "wb") as out:
            try:
                resp = OPENER.open(urllib.request.Request(url), timeout=max(1, min(60, deadline_s)))
            except urllib.error.HTTPError as err:
                raise Stop("video download failed: HTTP %d (redirects are not followed)" % err.code, 1)
            except (urllib.error.URLError, OSError) as err:
                raise Stop("video download failed: %s" % safe_text(err), 1)
            with resp:
                length = resp.headers.get("Content-Length")
                if length and length.isdigit() and int(length) > max_bytes:
                    raise Stop("the video is larger than the %d byte cap" % max_bytes, 1)
                total = 0
                while True:
                    left = deadline_s - (time.monotonic() - started)
                    if left <= 0:
                        raise Stop("the video download took longer than %d s" % deadline_s, 1)
                    limit_read_time(resp, min(60, left))
                    try:
                        chunk = resp.read1(65536)
                    except OSError as err:
                        if time.monotonic() - started >= deadline_s - 0.5:
                            raise Stop("the video download took longer than %d s" % deadline_s, 1)
                        raise Stop("video download failed: %s" % safe_text(err), 1)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise Stop("the video is larger than the %d byte cap" % max_bytes, 1)
                    out.write(chunk)
        with open(tmp, "rb") as fh:
            head = fh.read(12)
        if len(head) < 12 or head[4:8] != b"ftyp":
            raise Stop("the downloaded file is not an MP4", 1)
        place(tmp, dest, work)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def valid_id(value):
    return isinstance(value, str) and ID_RE.fullmatch(value) is not None


def run(args):
    work = Path.cwd().resolve()
    script = Path(args.script)
    out = Path(args.out)
    for label, p in (("--script", script), ("--out", out)):
        if CONTROL_RE.search(str(p)):
            raise Stop("%s has control characters in it" % label, 2)
        if not p.resolve().is_relative_to(work):
            raise Stop("%s must be inside the work folder" % label, 2)
    if not script.is_file():
        raise Stop("script file not found: " + safe_text(args.script), 2)
    if out.suffix.lower() != ".mp4":
        raise Stop("--out must end in .mp4", 2)
    for label, value in (("--avatar-id", args.avatar_id), ("--voice-id", args.voice_id)):
        if not valid_id(value):
            raise Stop("%s must be 1 to 128 letters, digits, - or _" % label, 2)
    if COLOR_RE.fullmatch(args.background) is None:
        raise Stop("--background must look like #00FF00", 2)
    if args.speed is not None and not (0.5 <= args.speed <= 1.5):
        raise Stop("--speed must be between 0.5 and 1.5", 2)
    if (not (0.01 <= args.poll_seconds <= 300) or args.max_wait <= 0 or args.max_bytes <= 0
            or args.download_timeout <= 0):
        raise Stop("--poll-seconds, --max-wait, --max-bytes and --download-timeout are out of range", 2)
    if args.base_url:
        if not is_local_base(args.base_url):
            raise Stop("--base-url may only be http://127.0.0.1 or http://localhost (tests)", 2)
        base = args.base_url.rstrip("/")
    else:
        base = API_HOST
    test_mode = bool(args.base_url)

    try:
        text = script.read_text(encoding="utf-8").strip()
    except (UnicodeDecodeError, OSError):
        raise Stop("script file is not readable UTF-8 text", 2)
    if not text:
        raise Stop("script file is empty", 2)
    if len(text) > args.max_chars:
        raise Stop("script is %d characters; the limit here is %d" % (len(text), args.max_chars), 2)

    if args.key_stdin:
        key = sys.stdin.readline().strip()
    else:
        key = os.environ.get("HEYGEN_API_KEY", "").strip()
    if not key:
        raise Stop("no HeyGen key. Set HEYGEN_API_KEY for this one process, or use --key-stdin. "
                   "Nothing was sent.", 3)
    if KEY_RE.fullmatch(key) is None:
        raise Stop("the key has characters or a length a key never has. Nothing was sent.", 2)
    SECRET[0] = key
    client = Client(base, key)

    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.parent.resolve().is_relative_to(work):
        raise Stop("--out must be inside the work folder", 2)
    if os.path.islink(out):
        raise Stop("%s is a symbolic link; refusing to write through it" % out.name, 2)
    state = out.with_name(out.name + ".render.json")
    video_id = None
    if os.path.lexists(state):
        problem = "%s exists but cannot be used (%%s). Nothing was sent. Delete that file only if you " \
                  "want to start a new, separately charged render." % state.name
        if os.path.islink(state):
            raise Stop(problem % "it is a symbolic link", 2)
        try:
            video_id = json.loads(state.read_text(encoding="utf-8"))["video_id"]
        except (ValueError, KeyError, TypeError, OSError):
            raise Stop(problem % "unreadable or malformed", 2)
        if not valid_id(video_id):
            raise Stop(problem % "it holds an invalid video id", 2)
        print("resuming render %s (delete %s to submit a new, separately charged render)"
              % (video_id, state.name), file=sys.stderr)
    else:
        body = {"type": "avatar", "avatar_id": args.avatar_id, "script": text, "voice_id": args.voice_id,
                "background": {"type": "color", "value": args.background},
                "resolution": args.resolution, "aspect_ratio": args.aspect_ratio}
        if args.speed is not None:
            body["voice_settings"] = {"speed": args.speed}
        reply = client.call("POST", CREATE_PATH, body)
        data = reply.get("data") if isinstance(reply.get("data"), dict) else {}
        video_id = data.get("video_id")
        if not valid_id(video_id):
            raise Stop("HeyGen did not return a usable video id: " + safe_text(reply.get("error") or "no detail"), 1)
        write_text_atomic(state, json.dumps({"video_id": video_id, "status": "submitted"}) + "\n", work)
        print("submitted render %s" % video_id, file=sys.stderr)

    deadline = time.monotonic() + args.max_wait
    url = None
    bad_polls = 0
    while True:
        try:
            reply = client.call("GET", STATUS_PATH + video_id)
            bad_polls = 0
        except Stop as stop:
            bad_polls += 1
            if not stop.transient or bad_polls >= 3:
                raise Stop("%s (render %s may still be running; run again to resume)" % (stop, video_id), 1)
            reply = {}
        data = reply.get("data") if isinstance(reply.get("data"), dict) else {}
        status = data.get("status")
        if status == "completed":
            url = data.get("video_url")
            if not isinstance(url, str) or not url:
                raise Stop("render completed but no video URL was returned", 1)
            break
        if status == "failed":
            code = safe_text(data.get("failure_code") or "unknown", 80)
            message = safe_text(data.get("failure_message") or "no message")
            raise Stop("HeyGen render failed (%s): %s. Not retried: a second submit is charged again."
                       % (code, message), 1)
        if time.monotonic() >= deadline:
            raise Stop("render %s did not finish within %d s; run again to resume" % (video_id, args.max_wait), 1)
        time.sleep(args.poll_seconds)

    download(url, out, args.max_bytes, args.download_timeout, work, test_mode)
    write_text_atomic(state, json.dumps({"video_id": video_id, "status": "completed"}) + "\n", work)
    return os.path.relpath(out.resolve(), work)


def emit_result(relpath):
    """The only place the VIDEO_FILE line is printed. Called last, once."""
    print("VIDEO_FILE: " + CONTROL_RE.sub("", relpath))


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print("error: " + safe_text(message, 500), file=sys.stderr)
        sys.exit(2)


def main(argv=None):
    p = Parser(description="Render an avatar narration video through HeyGen.")
    p.add_argument("--script", required=True, help="narration text file inside the work folder")
    p.add_argument("--avatar-id", required=True)
    p.add_argument("--voice-id", required=True)
    p.add_argument("--out", required=True, help="MP4 to write, inside the work folder")
    p.add_argument("--background", default="#00FF00")
    p.add_argument("--resolution", default="720p", choices=RESOLUTIONS)
    p.add_argument("--aspect-ratio", default="16:9", choices=ASPECT_RATIOS)
    p.add_argument("--speed", type=float)
    p.add_argument("--key-stdin", action="store_true", help="read the key from one line of standard input")
    p.add_argument("--poll-seconds", type=float, default=30.0)
    p.add_argument("--max-wait", type=int, default=1800, help="seconds to wait for the render")
    p.add_argument("--max-bytes", type=int, default=500 * 1024 * 1024, help="download size cap")
    p.add_argument("--download-timeout", type=int, default=600, help="overall seconds allowed for the download")
    p.add_argument("--max-chars", type=int, default=5000, help="script length cap")
    p.add_argument("--base-url", help=argparse.SUPPRESS)  # tests only: http://127.0.0.1 or http://localhost
    args = p.parse_args(argv)
    try:
        relpath = run(args)
    except Stop as stop:
        print("b-heygen: %s" % safe_text(stop, 600), file=sys.stderr)
        return stop.code
    except Exception as err:  # last resort: one fixed line, no traceback, no details
        print("b-heygen: unexpected failure (%s)" % type(err).__name__, file=sys.stderr)
        return 1
    emit_result(relpath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
