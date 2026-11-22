#!/usr/bin/env python3
"""generate.py - make one AI still with the Kie API and save it as a PNG in the work folder.

Python standard library only (plus the ffmpeg program, only to convert a JPEG or WEBP
result to PNG). One run makes one image and spends Kie credits, so it is guarded:

  * The key comes from the environment variable KIE_AI_API_KEY, set for this one
    process, or from one line of standard input with --key-stdin. It is never a command
    line argument and is never read from a file. It is never printed, logged or written
    to a file: every line this script prints is scrubbed of the key first.
  * The key goes only to api.kie.ai and, with --ref, to Kie's file upload host
    kieai.redpandaai.co. The result download carries no key. No redirect is ever followed.
  * Kie can answer HTTP 200 with a failure `code` in the body, so the body code is checked.
  * The create call is never retried (a retry could be charged twice). Status checks
    are free and are retried a few times.
  * Everything is read from and written to the work folder, which is the current folder:
    the prompt file, the reference images and the output PNG must all resolve inside it.
  * The prompt comes from a file (--prompt-file), never from a shell string.

Usage
  generate.py --prompt-file work/prompt.txt --out work/image.png --aspect 9:16
              [--model z-image] [--timeout 150] [--poll 5] [--key-stdin] [--dry-run]
  generate.py --prompt-file work/prompt.txt --out work/image.png --aspect 9:16
              --model gpt-image-2-image-to-image --resolution 2K --ref work/ref.png

Output (stdout)
  KIE_TASK: <task id>       printed once Kie accepts the create call
  IMAGE_FILE: <path>        last line on success
  IMAGE_FAILED: <reason>    last line on failure (exit 1 or 3)
A bad command line prints the problem on stderr and exits 2.

Exit codes
  0 image saved       1 Kie or network failure, rejected request, timeout, bad download
  2 bad arguments     3 no key (nothing was sent, nothing was spent)
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import zlib
import ipaddress
import http.client as _hc
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://api.kie.ai"
DEFAULT_UPLOAD_BASE = "https://kieai.redpandaai.co"
UPLOAD_PATH = "studio-refs"
DEFAULT_MODEL = "z-image"
UA = "studio-generate/1.0"
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_API_BYTES = 1024 * 1024
MAX_REF_BYTES = 10 * 1024 * 1024
MAX_PROMPT_FILE_BYTES = 64 * 1024
KEY_NAME = "KIE_AI_API_KEY"
LOOPBACK = ("127.0.0.1", "localhost")
# Models that read reference images from input.input_urls, with the aspect ratios and
# resolutions allowed for them.
REF_MODELS = {
    "gpt-image-2-image-to-image": {
        "aspects": ("1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16",
                    "2:1", "1:2", "3:1", "1:3", "21:9", "9:21"),
        "resolutions": {"1K": (), "2K": ("5:4", "4:5", "3:1", "1:3", "9:21"), "4K": ("3:1", "1:3", "9:21")},
        "max_refs": 16,
    },
}
# Text-to-image models with a documented shape (docs.kie.ai/market/z-image/z-image).
TEXT_MODELS = {
    "z-image": {"aspects": ("1:1", "4:3", "3:4", "16:9", "9:16"), "max_prompt": 1000},
}
RUNNING = ("waiting", "queuing", "queued", "generating", "running", "processing", "pending")
DONE = ("success", "completed", "done")
FAILED = ("fail", "failed", "error")

_KEY = ""  # set once in main(); used only to scrub output


class Usage(Exception):
    pass


class Failed(Exception):
    pass


_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]+")
_FINAL_DONE = False


MAX_RAW_TEXT = 64 * 1024


def safe_text(value, cap=300):
    """THE one function every piece of server or user text passes through before it is printed.
    Order matters: (1) cap the raw text at a sane size and remove the key from ALL of it,
    (2) replace control characters (newlines, U+2028, U+2029, U+0085 ...) with spaces,
    (3) only then cut to `cap` characters. Cutting first could leave part of the key in view."""
    text = str(value)[:MAX_RAW_TEXT]
    if _KEY:
        text = text.replace(_KEY, "<key>")
        # a key with control or format characters inserted in it: look for it in a copy with those deleted
        squeezed = "".join(c for c in text if unicodedata.category(c) not in ("Cc", "Cf", "Zl", "Zp"))
        if _KEY in squeezed:
            text = squeezed.replace(_KEY, "<key>")
    text = re.sub(r"https?://\S+", "<url>", text)
    text = _CONTROL.sub(" ", text)
    if _KEY:
        text = text.replace(_KEY, "<key>")
    return text[:cap]


def scrub(text, cap=300):
    return safe_text(text, cap)


def emit_line(label, text, final=False):
    """The ONLY place that prints KIE_TASK, IMAGE_FILE and IMAGE_FAILED lines. A final line is printed once."""
    global _FINAL_DONE
    if _FINAL_DONE:
        return
    if final:
        _FINAL_DONE = True
    print("%s: %s" % (label, scrub(text)), flush=True)


def finish(ok, text, code):
    emit_line("IMAGE_FILE" if ok else "IMAGE_FAILED", text, final=True)
    sys.exit(code)


def as_dict(x):
    return x if isinstance(x, dict) else {}


def _blocked_host(host, local_ok):
    """True for a host the key-less download must not fetch: loopback, private, link-local, numeric tricks."""
    h = (host or "").lower().strip(".")
    if not h:
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        ip = None
    if ip is not None:
        bad = (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
               or ip.is_unspecified)
        return bad and not (local_ok and ip.is_loopback)
    if re.fullmatch(r"(0x[0-9a-f]+|[0-9]+)(\.(0x[0-9a-f]+|[0-9]+))*", h):
        return True  # numeric forms such as 2130706433 or 0x7f.1
    if h == "localhost" or h.endswith(".localhost"):
        return not local_ok
    return "." not in h and not (local_ok and h in LOOPBACK)


def check_result_url(url, local_ok):
    """The result file address: plain https with a public host and no login. Loopback http only for tests."""
    u = urllib.parse.urlparse(url)
    try:
        host, _port = u.hostname, u.port
    except ValueError:
        raise Failed("Kie returned a result address that is not a plain https address")
    local = local_ok and u.scheme == "http" and host in LOOPBACK
    if (u.scheme != "https" and not local) or not host or "@" in u.netloc or _blocked_host(host, local):
        raise Failed("Kie returned a result address that is not a plain https address with a public host")


def check_base(url, default, flag):
    """The real https host, or a loopback http address (tests only). Nothing else."""
    if url == default:
        return url
    u = urllib.parse.urlparse(url)
    try:
        port = u.port
    except ValueError:
        raise Usage("%s has an invalid port" % flag)
    if u.scheme == "http" and u.hostname in LOOPBACK and port and "@" not in u.netloc and not u.path.strip("/"):
        return url.rstrip("/")
    raise Usage("%s may only be %s (or an http://127.0.0.1 or http://localhost address, for tests)" % (flag, default))


def inside_work(path, what):
    """The real path of `path`, which must be inside the current folder (the work folder)."""
    work = os.path.realpath(os.getcwd())
    real = os.path.realpath(path)
    if real != work and not real.startswith(work + os.sep):
        raise Usage("%s %r must be inside the work folder (the current folder)" % (what, path))
    return real


def read_key(use_stdin):
    if use_stdin:
        return sys.stdin.readline().strip()
    return os.environ.get(KEY_NAME, "").strip()


def ref_kind(path):
    """(mime, extension) of a PNG, JPEG or WEBP reference file, or a Usage error."""
    real = inside_work(path, "--ref")
    if not os.path.isfile(real):
        raise Usage("--ref %r is not a file" % path)
    size = os.path.getsize(real)
    if not 0 < size <= MAX_REF_BYTES:
        raise Usage("--ref %r must be 1 byte to %d MB" % (path, MAX_REF_BYTES // (1024 * 1024)))
    with open(real, "rb") as fh:
        head = fh.read(16)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise Usage("--ref %r must be a PNG, JPEG or WEBP image" % path)


def multipart(fields, file_name, content, mime):
    boundary = "studio-" + os.urandom(16).hex()
    out = []
    for k, v in fields:
        out.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode())
    out.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                % (boundary, file_name, mime)).encode())
    out.append(content)
    out.append(("\r\n--%s--\r\n" % boundary).encode())
    return b"".join(out), "multipart/form-data; boundary=" + boundary


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """No redirect is ever followed: not on a keyed call (the key would follow it), not on the download."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http(method, url, key=None, body=None, timeout=30, form=None, limit=MAX_API_BYTES):
    """Return (status, bytes), reading at most limit+1 bytes. `timeout` is a deadline for the WHOLE call
    (connect, headers and body), not for one read. Raises Failed on a network problem or the deadline."""
    headers = {"User-Agent": UA, "Accept": "application/json, image/*"}
    data = None
    if key:
        headers["Authorization"] = "Bearer " + key
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data, headers["Content-Type"] = form
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
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
                    box["res"] = (r.status, b"".join(chunks)) if got > limit else None
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
    if t.is_alive() or ("res" not in box and "err" not in box) or box.get("res") is None and "err" not in box:
        raise Failed("timed out after %ds on a network call to Kie or its file host" % timeout)
    if "err" in box:
        raise Failed("network error talking to Kie (%s)" % box["err"])
    return box["res"]


REASONS = {
    401: "the Kie key was refused",
    402: "not enough Kie credits",
    429: "Kie is rate limiting this key; wait and try again",
    455: "Kie is down for maintenance",
}


def reply_code(raw):
    """(code as int or None, parsed reply or None). Kie can send HTTP 200 with a failure `code` in the body."""
    try:
        j = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return None, None
    if not isinstance(j, dict):
        return None, None
    c = j.get("code")
    return (int(c) if re.fullmatch(r"-?[0-9]{1,6}", str(c), re.ASCII) else None), j


def api_error(status, raw):
    """A short, safe one-line reason: HTTP status, Kie code, a known reason and the message."""
    code, j = reply_code(raw)
    msg = ""
    if j:
        msg = safe_text(j.get("msg") or j.get("message") or "", 160)
    hint = REASONS.get(status if status in REASONS else code)
    return "HTTP %s, Kie code %s%s: %s" % (status, code if code is not None else "-",
                                           " (%s)" % hint if hint else "", msg or "no message")


def upload_ref(upload_base, key, path, local_ok):
    """Send one local reference image to Kie's file upload; return its hosted URL.
    The upload path is a fixed neutral name and the file name is the content hash."""
    mime, ext = ref_kind(path)
    with open(inside_work(path, "--ref"), "rb") as fh:
        content = fh.read()
    name = hashlib.sha256(content).hexdigest()[:32] + ext
    form = multipart((("uploadPath", UPLOAD_PATH), ("fileName", name)), name, content, mime)
    status, raw = http("POST", upload_base + "/api/file-stream-upload", key, form=form, timeout=60)
    try:
        reply = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        reply = None
    url = as_dict(as_dict(reply).get("data")).get("downloadUrl")
    if status != 200 or not isinstance(reply, dict) or str(reply.get("code")) != "200" or not url:
        raise Failed("Kie did not accept the reference upload of %s: %s; no image was requested"
                     % (os.path.basename(path), api_error(status, raw)))
    try:
        check_result_url(str(url), local_ok)
    except Failed:
        raise Failed("Kie's reference upload returned an address that is not a plain https address; no image was requested")
    return str(url)


def echoed_refs(param):
    """The input_urls Kie recorded for a task, [] if it recorded none, None if the shape is unknown."""
    try:
        p = json.loads(param) if isinstance(param, str) else param
    except ValueError:
        return None
    if not isinstance(p, dict):
        return None
    inp = p.get("input", p)
    if isinstance(inp, str):
        try:
            inp = json.loads(inp)
        except ValueError:
            return None
    if not isinstance(inp, dict):
        return None
    if "input_urls" in inp:
        refs = inp["input_urls"]
        return [str(r) for r in refs] if isinstance(refs, list) else []
    return [] if "prompt" in inp else None


PNG_SIG = b"\x89PNG\r\n\x1a\n"


def check_png(path):
    """True when the file is a well-formed PNG: signature, IHDR first, every chunk length and CRC
    consistent, IEND last, nothing after it."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if fh.read(8) != PNG_SIG:
                return False
            pos, first, seen_idat = 8, True, False
            while True:
                head = fh.read(8)
                if len(head) < 8:
                    return False
                n, kind = int.from_bytes(head[:4], "big"), head[4:]
                if n > size or pos + 12 + n > size:
                    return False
                body = fh.read(n)
                crc = fh.read(4)
                if len(body) != n or len(crc) != 4 or zlib.crc32(kind + body) & 0xFFFFFFFF != int.from_bytes(crc, "big"):
                    return False
                pos += 12 + n
                if first:
                    if kind != b"IHDR" or n != 13 or int.from_bytes(body[:4], "big") < 1 \
                            or int.from_bytes(body[4:8], "big") < 1:
                        return False
                    first = False
                seen_idat = seen_idat or kind == b"IDAT"
                if kind == b"IEND":
                    return n == 0 and seen_idat and pos == size
    except OSError:
        return False


def new_temp(out_dir, suffix):
    """A new private temp file inside the output folder (O_EXCL, never follows a planted name)."""
    fd, path = tempfile.mkstemp(dir=out_dir, prefix=".kie-", suffix=suffix)
    return fd, path


def save_png(raw, out):
    """Write the downloaded bytes to `out` as a checked PNG. Every temp file is created fresh in the output
    folder with mkstemp, the finished file is moved into place with os.replace, and temps are removed on
    every path. A JPEG or WEBP is converted with ffmpeg."""
    out_dir = os.path.dirname(out)
    temps = []
    try:
        fd, tmp = new_temp(out_dir, ".download")
        temps.append(tmp)
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        head = raw[:16]
        final = tmp
        if head.startswith(PNG_SIG):
            pass
        elif head.startswith(b"\xff\xd8\xff") or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"):
            codec = "mjpeg" if head.startswith(b"\xff\xd8\xff") else "webp"  # named from the file's own signature
            ff = shutil.which("ffmpeg")
            if not ff:
                raise Failed("Kie returned a JPEG/WEBP image and ffmpeg is not available to convert it")
            fd2, final = new_temp(out_dir, ".png")
            os.close(fd2)
            temps.append(final)
            env = {k: v for k, v in os.environ.items() if k != KEY_NAME}  # the key never reaches ffmpeg
            r = subprocess.run([ff, "-v", "error", "-y", "-pattern_type", "none", "-f", "image2", "-c:v", codec, "-i", tmp, "-frames:v", "1",
                                "-update", "1", "-f", "image2", "-c:v", "png", final], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=120)
            if r.returncode != 0:
                raise Failed("could not convert the downloaded image to PNG")
        else:
            raise Failed("the download was not a PNG, JPEG or WEBP image")
        if not check_png(final):
            raise Failed("the downloaded file is not a well-formed PNG")
        os.replace(final, out)
        temps.remove(final)
    finally:
        for t in temps:
            try:
                os.remove(t)
            except OSError:
                pass


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Generate one AI still with the Kie API and save it as a PNG.",
                                 epilog="Key: environment variable %s, or --key-stdin." % KEY_NAME)
    ap.add_argument("--prompt-file", required=True, help="text file in the work folder holding the prompt")
    ap.add_argument("--out", required=True, help="PNG file to write, inside the work folder")
    ap.add_argument("--aspect", default="16:9", help="aspect ratio such as 16:9, 1:1, 9:16")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="Kie model key (default z-image)")
    ap.add_argument("--ref", action="append", default=[], metavar="FILE",
                    help="reference image (PNG/JPEG/WEBP, max 10 MB, inside the work folder); repeatable; "
                         "only for: " + ", ".join(sorted(REF_MODELS)))
    ap.add_argument("--resolution", help="output resolution sent as input.resolution (1K, 2K or 4K)")
    ap.add_argument("--timeout", type=int, default=150, help="seconds to wait for the image, 3..1800 (default 150)")
    ap.add_argument("--poll", type=int, default=5, help="seconds between status checks, 1..60 (default 5)")
    ap.add_argument("--download-timeout", type=int, default=120,
                    help="seconds allowed for the whole result download, 3..600 (default 120)")
    ap.add_argument("--key-stdin", action="store_true", help="read the key from one line of standard input")
    ap.add_argument("--base-url", default=DEFAULT_BASE, help="tests only: http://127.0.0.1:PORT or http://localhost:PORT")
    ap.add_argument("--upload-base-url", default=DEFAULT_UPLOAD_BASE,
                    help="tests only: http://127.0.0.1:PORT or http://localhost:PORT")
    ap.add_argument("--dry-run", action="store_true", help="check everything, print the plan, send nothing")
    return ap.parse_args(argv)


def main(argv):
    global _KEY
    args = parse_args(argv)
    if not re.match(r"^\d{1,2}:\d{1,2}$", args.aspect):
        raise Usage("--aspect must look like 16:9, got %r" % args.aspect)
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_./-]{0,63}$", args.model):
        raise Usage("--model %r is not a valid model key" % args.model)
    if not 3 <= args.download_timeout <= 600:
        raise Usage("--download-timeout must be 3..600 seconds")
    if not (3 <= args.timeout <= 1800 and 1 <= args.poll <= 60):
        raise Usage("--timeout must be 3..1800 and --poll 1..60 seconds")
    if args.resolution is not None and args.resolution not in ("1K", "2K", "4K"):
        raise Usage("--resolution must be 1K, 2K or 4K, got %r" % args.resolution)
    if not args.out.lower().endswith(".png"):
        raise Usage("--out must end in .png")
    if os.path.islink(os.path.abspath(args.out)):
        raise Usage("--out %r is a symbolic link; give a plain file name" % args.out)
    out = inside_work(args.out, "--out")
    if os.path.isdir(out):
        raise Usage("--out %r is a folder" % args.out)

    pf = inside_work(args.prompt_file, "--prompt-file")
    if not os.path.isfile(pf) or os.path.getsize(pf) > MAX_PROMPT_FILE_BYTES:
        raise Usage("--prompt-file %r must be a text file of at most %d KB" % (args.prompt_file, MAX_PROMPT_FILE_BYTES // 1024))
    try:
        with open(pf, "r", encoding="utf-8") as fh:
            prompt = fh.read().strip()
    except (OSError, UnicodeDecodeError):
        raise Usage("--prompt-file %r is not readable UTF-8 text" % args.prompt_file)
    tspec = TEXT_MODELS.get(args.model)
    limit = tspec["max_prompt"] if tspec else 4000
    if not prompt or len(prompt) > limit:
        raise Usage("the prompt for model %s must be 1 to %d characters" % (args.model, limit))
    if tspec and args.aspect not in tspec["aspects"]:
        raise Usage("model %s does not support --aspect %s (use one of %s)" % (args.model, args.aspect, ", ".join(tspec["aspects"])))

    spec = REF_MODELS.get(args.model)
    if args.ref and not spec:
        raise Usage("--ref is only supported for %s; model %s would silently ignore the reference"
                    % (", ".join(sorted(REF_MODELS)), args.model))
    if spec:
        if not args.ref:
            raise Usage("model %s is image-to-image: give at least one --ref" % args.model)
        if len(args.ref) > spec["max_refs"]:
            raise Usage("model %s takes at most %d --ref images" % (args.model, spec["max_refs"]))
        if args.aspect not in spec["aspects"]:
            raise Usage("model %s does not support --aspect %s" % (args.model, args.aspect))
        if args.resolution is None:
            raise Usage("model %s needs --resolution (1K, 2K or 4K)" % args.model)
        if args.aspect in spec["resolutions"][args.resolution]:
            raise Usage("model %s does not support --aspect %s at %s" % (args.model, args.aspect, args.resolution))
    for r in args.ref:
        ref_kind(r)
    base = check_base(args.base_url, DEFAULT_BASE, "--base-url")
    upload_base = check_base(args.upload_base_url, DEFAULT_UPLOAD_BASE, "--upload-base-url")

    key = read_key(args.key_stdin)
    if key and not re.match(r"^[\x21-\x7e]{1,512}$", key):
        raise Usage("the key has characters that are not allowed in a header (value not shown)")
    _KEY = key

    if args.dry_run:
        print(scrub("DRY RUN: would %screate one %s%s image (%s) with model %s -> %s" % (
            "upload %d reference image(s), send them in input_urls, then " % len(args.ref) if args.ref else "",
            args.aspect, " " + args.resolution if args.resolution else "",
            "a key is present" if key else "NO KEY, it would stop with exit 3", args.model, args.out)))
        print("no request was sent")
        return 0
    if not key:
        finish(False, "no Kie key (set %s for this process or use --key-stdin); nothing was sent and nothing was spent"
               % KEY_NAME, 3)

    os.makedirs(os.path.dirname(out), exist_ok=True)

    # 0. Upload the reference images (free). Kie reads input_urls as hosted URLs.
    test_hosts = upload_base != DEFAULT_UPLOAD_BASE
    ref_urls = [upload_ref(upload_base, key, r, test_hosts) for r in args.ref]

    # 1. Create the task. Exactly once.
    task_input = {"prompt": prompt, "aspect_ratio": args.aspect}
    if args.resolution:
        task_input["resolution"] = args.resolution
    if ref_urls:
        task_input["input_urls"] = ref_urls
    try:
        status, raw = http("POST", base + "/api/v1/jobs/createTask", key, {"model": args.model, "input": task_input})
    except Failed as e:
        raise Failed("%s; the request was not repeated, so you cannot be charged twice" % e)
    try:
        reply = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        reply = None
    task = as_dict(as_dict(reply).get("data")).get("taskId")
    if status != 200 or not isinstance(reply, dict) or str(reply.get("code")) != "200" or not task:
        raise Failed("Kie did not accept the request: " + api_error(status, raw))
    task = str(task)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task):
        raise Failed("Kie returned an unusable task id")
    emit_line("KIE_TASK", task)

    # 2. Poll. Status checks are free, so a short network blip is retried.
    deadline = time.time() + args.timeout
    blips = 0
    refs_checked = not ref_urls
    while True:
        time.sleep(args.poll)
        try:
            status, raw = http("GET", base + "/api/v1/jobs/recordInfo?taskId=" + urllib.parse.quote(task), key, timeout=20)
        except Failed:
            blips += 1
            if blips > 3:
                raise
            status, raw = 0, b""
        code, body = reply_code(raw) if status == 200 else (None, None)
        if status == 200 and code is not None and code != 200:
            raise Failed("Kie refused the status check: " + api_error(status, raw))
        if status == 200:
            data = as_dict(as_dict(body).get("data"))
            state = str(data.get("state", "")).lower()
            if not refs_checked and data.get("param") is not None:
                # Kie drops an input key it does not read; a task that lost its references
                # would come back as a plain text-to-image.
                echoed = echoed_refs(data.get("param"))
                if echoed is not None and len(echoed) != len(ref_urls):
                    raise Failed("Kie task %s did not keep the reference image(s) in input_urls (recorded %d of %d); "
                                 "the image would not match the reference" % (task, len(echoed), len(ref_urls)))
                if echoed is None:
                    sys.stderr.write("generate.py: recordInfo.param has an unknown shape; reference echo not checked\n")
                refs_checked = True
            if state in DONE:
                rj = data.get("resultJson")
                try:
                    rj = json.loads(rj or "{}") if isinstance(rj, str) else rj
                    urls = (rj or {}).get("resultUrls") or []
                except (ValueError, AttributeError):
                    urls = []
                if not isinstance(urls, list):
                    urls = []
                if not urls:
                    raise Failed("Kie finished task %s but returned no image" % task)
                url = str(urls[0])
                break
            if state in FAILED:
                why = safe_text(data.get("failMsg") or data.get("error") or "", 160)
                fc = safe_text(data.get("failCode") or "", 8)
                raise Failed("Kie task %s failed%s: %s" % (task, " (code %s)" % fc if fc.isdigit() else "", why or "no reason given"))
        elif 300 <= status < 400:
            raise Failed("Kie answered the status check with a redirect, which is never followed")
        elif status in (401, 402, 403, 404, 429):
            raise Failed("Kie refused the status check: " + api_error(status, raw))
        if time.time() >= deadline:
            raise Failed("timed out after %ds waiting for Kie task %s (it may still finish on Kie; it was not "
                         "retried so you are not charged twice)" % (args.timeout, task))

    # 3. Download. No key is sent. The result address is never printed.
    check_result_url(url, base != DEFAULT_BASE)
    status, raw = http("GET", url, None, timeout=args.download_timeout, limit=MAX_IMAGE_BYTES)
    if status != 200 or not raw:
        raise Failed("could not download the image (HTTP %s)" % status)
    if len(raw) > MAX_IMAGE_BYTES:
        raise Failed("the image is larger than %d MB; it was not saved" % (MAX_IMAGE_BYTES // (1024 * 1024)))
    save_png(raw, out)
    finish(True, "%s (%d bytes, model %s)" % (args.out, os.path.getsize(out), args.model), 0)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]) or 0)
    except SystemExit:
        raise
    except Usage as e:
        sys.stderr.write("generate.py: %s\n" % scrub(e))
        sys.exit(2)
    except Failed as e:
        finish(False, str(e), 1)
    except KeyboardInterrupt:
        sys.exit(130)
    except BaseException:
        # last resort: never a traceback, never any server text
        finish(False, "unexpected error; nothing more was done", 1)
