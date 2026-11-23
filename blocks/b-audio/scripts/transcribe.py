#!/usr/bin/env python3
"""Speech to text with word timings, using one local tool named by the caller.

Writes <out> (a JSON array of {"text","start","end"}) and <out stem>.meta.json
(tool, version, model checksum). Exit codes: 0 ok, 1 failed, 2 bad usage or
bad input, 3 something required is missing. See ../README.md.
"""
import argparse
import array
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

TOOLS = {"whisper-cpp": "whisper-cli"}  # tool name -> executable name
MODEL_HOST = "huggingface.co"
MODEL_PATH = "/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin"
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")  # all patterns are used with fullmatch
LANG_RE = re.compile(r"[a-z]{2,3}(-[a-z]{2,4})?")
HINT_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # newline and tab are allowed
HINT_MAX_CHARS = 2000
SHA_RE = re.compile(r"[0-9a-fA-F]{64}")
CONTROL_RE = re.compile("[\x00-\x1f\x7f\x85\u2028\u2029]")
LOCAL_HOSTS = ("127.0.0.1", "localhost")


class Stop(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def inside(path, root):
    return path.resolve().is_relative_to(root)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def clean(value, limit=600):
    return CONTROL_RE.sub(" ", str(value))[:limit]


def local_origin(url):
    """Return (host, port) for http://127.0.0.1[:port] or http://localhost[:port], else None."""
    if CONTROL_RE.search(url) or " " in url:
        return None
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS and "@" not in parts.netloc
            and parts.path in ("", "/") and not parts.query and not parts.fragment):
        return (parts.hostname, port)
    return None


def place(tmp_path, target, work):
    """Move a finished temporary file onto target. Refuses a target that is a link."""
    if os.path.islink(target):
        raise Stop("%s is a symbolic link; refusing to write through it" % target.name, 2)
    os.replace(tmp_path, target)
    if not target.resolve().is_relative_to(work):
        raise Stop("the written file is not inside the work folder", 2)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def limit_read_time(resp, seconds):
    """Make the next read give up after `seconds` (never more than the time left)."""
    try:
        resp.fp.raw._sock.settimeout(max(0.1, seconds))
    except AttributeError:
        pass


def host_allowed(url, base_url):
    """Redirect targets: with a test base, exactly that origin; otherwise https on the model host."""
    if base_url:
        try:
            p = urllib.parse.urlsplit(url)
            p.port
        except ValueError:
            return False
        return local_origin("%s://%s" % (p.scheme, p.netloc)) == local_origin(base_url)
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    host = parts.hostname or ""
    return (parts.scheme == "https" and "@" not in parts.netloc and port in (None, 443)
            and (host == MODEL_HOST or host.endswith("." + MODEL_HOST) or host == "hf.co" or host.endswith(".hf.co")))


def download_model(name, target, base_url, max_bytes, deadline_s, expected_sha, work):
    """Download one model file into place. Only the documented host; redirects only to its own
    hosts. The temporary file is verified against the checksum BEFORE it is moved into place."""
    root = base_url.rstrip("/") if base_url else "https://" + MODEL_HOST
    url = root + MODEL_PATH.format(name=name)
    opener = urllib.request.build_opener(NoRedirect)
    for _ in range(4):
        try:
            resp = opener.open(urllib.request.Request(url), timeout=max(1, min(60, deadline_s)))
        except urllib.error.HTTPError as err:
            if err.code in (301, 302, 303, 307, 308) and err.headers.get("Location"):
                url = urllib.parse.urljoin(url, err.headers["Location"])
                if not host_allowed(url, base_url):
                    raise Stop("model download redirected to a host that is not allowed", 1)
                continue
            raise Stop("model download failed: HTTP %d" % err.code, 1)
        except (urllib.error.URLError, OSError) as err:
            raise Stop("model download failed: %s" % clean(err), 1)
        break
    else:
        raise Stop("model download redirected too many times", 1)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".b-audio-model-")
    started = time.monotonic()
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as out, resp:
            total = 0
            while True:
                left = deadline_s - (time.monotonic() - started)
                if left <= 0:
                    raise Stop("model download took longer than %d s" % deadline_s, 1)
                limit_read_time(resp, min(60, left))
                try:
                    chunk = resp.read1(65536)
                except OSError as err:
                    if time.monotonic() - started >= deadline_s - 0.5:
                        raise Stop("model download took longer than %d s" % deadline_s, 1)
                    raise Stop("model download failed: %s" % clean(err), 1)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise Stop("model download is larger than the %d byte cap" % max_bytes, 1)
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != expected_sha.lower():
            raise Stop("the downloaded model does not match --model-sha256; it was deleted", 1)
        place(tmp, target, work)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def ffmpeg_version(ffmpeg):
    try:
        proc = subprocess.run([ffmpeg, "-nostdin", "-version"], capture_output=True, text=True, shell=False, timeout=30)
        return clean(proc.stdout.splitlines()[0]) if proc.returncode == 0 and proc.stdout else "not reported"
    except (OSError, subprocess.TimeoutExpired):
        return "not reported"


def to_wav16k(src, work_tmp, info):
    """Return a path to a 16 kHz mono 16-bit PCM WAV of the input."""
    try:
        with wave.open(str(src), "rb") as w:
            if w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2:
                return src
    except (wave.Error, EOFError):
        pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise Stop("ffmpeg is not installed, and the input is not a 16 kHz mono 16-bit WAV. Install ffmpeg 6 or newer.", 3)
    info["ffmpeg_version"] = ffmpeg_version(ffmpeg)
    dest = work_tmp / "audio.wav"
    proc = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-y", "-protocol_whitelist", "file", "-i", str(src), "-vn", "-map", "0:a:0",
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(dest)],
        capture_output=True, text=True, shell=False)
    if proc.returncode != 0 or not dest.exists():
        tail = (proc.stderr.strip().splitlines() or ["no message"])[-1]
        raise Stop("ffmpeg could not read audio from the input: " + clean(tail), 1)
    return dest


def build_words(segments, duration, samples, rate):
    raw = []
    for seg in segments:
        for tok in seg.get("tokens") or []:
            text = tok.get("text") or ""
            if text.startswith("[_") or not text.strip():
                continue
            off = tok.get("offsets") or {}
            begin = max(0.0, off.get("from", 0) / 1000.0)
            finish = max(begin, off.get("to", 0) / 1000.0)
            if text[0].isspace() or not raw:
                raw.append({"w": text.strip(), "start": begin, "end": begin, "spoken": False})
            else:
                raw[-1]["w"] += text
            if re.search(r"\w", text):
                if not raw[-1]["spoken"]:
                    raw[-1]["start"] = begin
                raw[-1]["end"] = finish
                raw[-1]["spoken"] = True
    noise = re.compile(r"^(\[[^\]]*\]|\([^)]*\)|\*[^*]*\*)$")
    words = []
    for item in raw:
        text = item["w"]
        if noise.match(text) or "♪" in text:
            continue
        if not item["spoken"]:
            if words:
                words[-1]["text"] += text
            continue
        start = min(duration, item["start"])
        end = min(duration, max(start, item["end"]))
        if words:
            start = max(start, words[-1]["start"])
            end = max(end, start)
        words.append({"text": text, "start": start, "end": end})

    def silent(word):
        a = max(0, int((word["start"] - 0.3) * rate))
        window = samples[a:int((word["end"] + 0.3) * rate)]
        if not window:
            return True
        rms = math.sqrt(sum(v * v for v in window) / len(window))
        return rms < 32768 * 10 ** (-60 / 20)

    if samples is not None:
        words = [w for w in words if not silent(w)]
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        next_start = nxt["start"] if nxt else duration
        if w["end"] - w["start"] < 0.05 and next_start > w["start"]:
            w["end"] = min(next_start, w["start"] + 0.3)
        elif 0 < next_start - w["end"] < 0.12:
            w["end"] = next_start
        w["start"] = round(w["start"], 3)
        w["end"] = round(min(w["end"], duration), 3)
        if w["end"] < w["start"]:
            w["end"] = w["start"]
    for a, b in zip(words, words[1:]):
        if a["start"] > b["start"]:
            raise Stop("the tool returned word times that are out of order", 1)
    return words


def write_json(path, data, work):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".b-audio-out-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        place(tmp, path, work)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def run(args):
    work = Path.cwd().resolve()
    src = Path(args.input)
    out = Path(args.out)
    if not inside(src, work):
        raise Stop("input must be inside the work folder", 2)
    if not inside(out, work):
        raise Stop("--out must be inside the work folder", 2)
    if not src.is_file():
        raise Stop("input file not found: " + args.input, 2)
    for label, p in (("input", src), ("--out", out), ("--model", Path(args.model))):
        if CONTROL_RE.search(str(p)):
            raise Stop("%s has control characters in it" % label, 2)
    if LANG_RE.fullmatch(args.language) is None:
        raise Stop("--language must look like en or pt-br", 2)
    if args.max_model_bytes <= 0:
        raise Stop("--max-model-bytes must be positive", 2)
    if args.base_url and local_origin(args.base_url) is None:
        raise Stop("--base-url may only be http://127.0.0.1 or http://localhost (tests)", 2)
    if args.model_sha256 and SHA_RE.fullmatch(args.model_sha256) is None:
        raise Stop("--model-sha256 must be 64 hexadecimal characters", 2)
    if args.download_timeout <= 0 or args.timeout <= 0:
        raise Stop("--timeout and --download-timeout must be positive", 2)
    hint = None
    if args.hint_file:
        hp = Path(args.hint_file)
        if CONTROL_RE.search(str(hp)) or not inside(hp, work):
            raise Stop("--hint-file must be inside the work folder", 2)
        if not hp.is_file():
            raise Stop("hint file not found: " + clean(args.hint_file), 2)
        if hp.stat().st_size > HINT_MAX_CHARS * 4:
            raise Stop("hint file is longer than %d characters" % HINT_MAX_CHARS, 2)
        try:
            hint = hp.read_text(encoding="utf-8").strip()
        except (UnicodeDecodeError, OSError):
            raise Stop("hint file is not readable UTF-8 text", 2)
        if not hint:
            raise Stop("hint file is empty", 2)
        if len(hint) > HINT_MAX_CHARS:
            raise Stop("hint file is %d characters; the limit is %d" % (len(hint), HINT_MAX_CHARS), 2)
        if HINT_CONTROL_RE.search(hint):
            raise Stop("hint file has control characters in it", 2)
    meta_out = out.with_name(out.stem + ".meta.json")
    for target in (out, meta_out):
        if os.path.islink(target):
            raise Stop("%s is a symbolic link; refusing to write through it" % target.name, 2)

    allowed = [work]
    for d in args.allow_model_dir:
        dp = Path(d)
        if not dp.is_dir():
            raise Stop("--allow-model-dir is not a folder: " + d, 2)
        allowed.append(dp.resolve())
    model = Path(args.model).resolve()
    if not any(model.is_relative_to(a) for a in allowed):
        raise Stop("model path is outside the work folder and every --allow-model-dir folder; "
                   "this script never searches for a model", 2)
    if args.language != "en" and model.name.endswith(".en.bin"):
        raise Stop("the model %s is English only; pass a multilingual model" % model.name, 2)

    exe_name = TOOLS[args.tool]
    exe = args.tool_bin or shutil.which(exe_name)
    if not exe or not os.access(exe, os.X_OK):
        raise Stop("speech-to-text tool '%s' is not installed (it provides %s). Install whisper.cpp "
                   "%s or newer, for example 'brew install whisper-cpp'. Nothing else is tried."
                   % (args.tool, exe_name, args.tool_version), 3)

    downloaded = False
    if not model.is_file():
        if not args.allow_download:
            raise Stop("model file not found: %s. Pass its path, or pass --allow-download with "
                       "--model-name to fetch it from %s." % (model.name, MODEL_HOST), 3)
        if not args.model_name or NAME_RE.fullmatch(args.model_name) is None:
            raise Stop("--allow-download needs --model-name, for example base.en", 2)
        if not args.model_sha256:
            raise Stop("--allow-download needs --model-sha256: nothing is downloaded without a checksum to verify", 2)
        if not model.is_relative_to(work):
            raise Stop("a model is only downloaded into the work folder; this path is outside it", 2)
        model.parent.mkdir(parents=True, exist_ok=True)
        if not model.parent.resolve().is_relative_to(work):
            raise Stop("a model is only downloaded into the work folder; this path is outside it", 2)
        print("downloading model %s from %s" % (args.model_name, args.base_url or MODEL_HOST), file=sys.stderr)
        download_model(args.model_name, model, args.base_url, args.max_model_bytes,
                       args.download_timeout, args.model_sha256, work)
        downloaded = True
    model_sha = sha256_file(model)
    if args.model_sha256 and args.model_sha256.lower() != model_sha:
        raise Stop("model checksum does not match --model-sha256", 1)

    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.parent.resolve().is_relative_to(work):
        raise Stop("--out must be inside the work folder", 2)
    info = {"ffmpeg_version": None}
    tmp = Path(tempfile.mkdtemp(prefix=".b-audio-", dir=work))
    try:
        wav = to_wav16k(src.resolve(), tmp, info)
        with wave.open(str(wav), "rb") as w:
            rate = w.getframerate()
            duration = w.getnframes() / rate
            samples = array.array("h")
            samples.frombytes(w.readframes(w.getnframes()))
        if sys.byteorder == "big":
            samples.byteswap()
        cmd = [exe, "-m", str(model), "-f", str(wav), "-l", args.language, "-ojf", "-np", "-of", str(tmp / "asr")]
        if hint is not None:
            cmd += ["--prompt", hint]  # whisper.cpp's initial-prompt option; one argument, never a shell string
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=args.timeout, shell=False)
        asr = tmp / "asr.json"
        if proc.returncode != 0 or not asr.is_file():
            tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
            raise Stop("%s failed (exit %d)\n%s" % (exe_name, proc.returncode, clean(tail.replace("\n", " | "))), 1)
        try:
            segments = json.loads(asr.read_text(encoding="utf-8")).get("transcription") or []
        except (ValueError, AttributeError):
            raise Stop("the tool wrote output that is not the expected JSON", 1)
        words = build_words(segments, duration, samples, rate)
    except subprocess.TimeoutExpired:
        raise Stop("the speech-to-text tool timed out after %d s" % args.timeout, 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not words:
        print("warning: no speech recognised; wrote an empty list", file=sys.stderr)
    write_json(out, [{"text": w["text"], "start": w["start"], "end": w["end"]} for w in words], work)
    meta = {
        "tool": args.tool,
        "tool_version": args.tool_version,
        "tool_bin_as_given": args.tool_bin or ("%s (found on PATH)" % exe_name),
        "tool_sha256": sha256_file(exe),
        "ffmpeg_version": info["ffmpeg_version"],
        "hint_used": hint is not None,
        "hint_chars": len(hint) if hint is not None else 0,
        "hint_sha256": hashlib.sha256(hint.encode("utf-8")).hexdigest() if hint is not None else None,
        "model_file": model.name,
        "model_sha256": model_sha,
        "model_downloaded": downloaded,
        "language": args.language,
        "input": os.path.relpath(src.resolve(), work),
        "duration": round(duration, 3),
        "word_count": len(words),
        "text": " ".join(w["text"] for w in words),
        "wpm": round(len(words) / (duration / 60.0)) if duration > 0 else 0,
    }
    write_json(meta_out, meta, work)
    print("wrote %s (%d words)" % (os.path.relpath(out.resolve(), work), len(words)), file=sys.stderr)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print("error: " + clean(message), file=sys.stderr)
        sys.exit(2)


def main(argv=None):
    p = Parser(description="Speech to text with word timings (one local tool, named by the caller).")
    p.add_argument("input", help="audio or video file inside the work folder")
    p.add_argument("--out", required=True, help="words JSON to write, inside the work folder")
    p.add_argument("--tool", required=True, choices=sorted(TOOLS), help="the one tool to use")
    p.add_argument("--tool-version", required=True, help="installed version of the tool, recorded beside the output")
    p.add_argument("--tool-bin", help="explicit path to the tool's program (default: found on PATH)")
    p.add_argument("--model", required=True, help="model file (inside the work folder or an --allow-model-dir)")
    p.add_argument("--allow-model-dir", action="append", default=[], help="extra folder the model may live in (repeatable)")
    p.add_argument("--model-sha256", help="expected model checksum; a mismatch fails")
    p.add_argument("--language", default="en")
    p.add_argument("--hint-file", help="UTF-8 text file inside the work folder (up to 2000 characters) passed to the "
                                       "tool as its initial prompt, so names and product words are spelled right")
    p.add_argument("--allow-download", action="store_true", help="allow downloading the model from huggingface.co")
    p.add_argument("--model-name", help="model to download, for example base.en (with --allow-download)")
    p.add_argument("--max-model-bytes", type=int, default=4 * 1024 ** 3)
    p.add_argument("--timeout", type=int, default=1800, help="seconds before the tool is stopped")
    p.add_argument("--download-timeout", type=int, default=1800, help="overall seconds allowed for a model download")
    p.add_argument("--base-url", help=argparse.SUPPRESS)  # tests only: http://127.0.0.1 or http://localhost
    args = p.parse_args(argv)
    try:
        run(args)
    except Stop as stop:
        print("b-audio: %s" % clean(stop), file=sys.stderr)
        return stop.code
    except Exception as err:  # last resort: one fixed line, no traceback, no details
        print("b-audio: unexpected failure (%s)" % type(err).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
