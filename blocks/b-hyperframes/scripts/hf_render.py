#!/usr/bin/env python3
"""The one safe way to render a HyperFrames composition.

    python3 hf_render.py --comp work/comp --out work/visuals.mp4 [--fps 30] [--quality high] [--format mp4]

Order: local-only check (a failure stops here), lint, validate, render with one worker.
The renderer runs the pinned package from WORK/hyperframes-runtime (see hf_install.py)
with the pinned headless browser from WORK/.hf-cache, a short environment, no telemetry,
and caches under WORK/.hf-cache. The package's entry files and the browser are re-checked
against the checksums recorded at install. --use-system-browser PATH is an opt-in to an
installed Chrome, which makes its own background connections.

Exit codes: 0 rendered, 1 refused or failed, 2 bad usage, 3 renderer not installed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import shutil
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hfcommon import (FAIL, MISSING, OK, TRUST_FILE, USAGE, Stop, ensure_dir, entry_hashes, has_symlink_below,  # noqa: E402
                      inside_work, is_inside, load_pins, refuse_linked_children, run_main, safe_env, sha256_file,
                      work_folder)
from hf_install import NO_PHONE_HOME, run  # noqa: E402

EXT = {"mp4": ".mp4", "mov": ".mov"}
HERE = Path(__file__).resolve().parent
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
NOTABLE = re.compile(r"\[WARN\]|\[Browser:(?:WARN|ERROR|PAGEERROR)\]|\[non-blocking\]|\[ERROR\]|[\u26a0\u2716\u2717]"
                     r"|^\s*(?:error|warning)\b|(?<![\d.])[1-9]\d* (?:errors?|warnings?)\b", re.I)
MAX_SHOWN = 40


def open_log(path, work):
    """A fresh log file each run: any old one is unlinked (links are not followed), then exclusive create."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o644)
    except OSError as exc:
        raise Stop(USAGE, f"cannot create the log file {path}: {exc}")
    if not is_inside(path, work):
        os.close(fd)
        os.unlink(path)
        raise Stop(USAGE, "the log file's real path is outside the work folder; refused")
    return os.fdopen(fd, "wb")


def run_logged(cmd, cwd, env, timeout, log, log_path, label):
    """Run a stage with all its output in the run's log file. Returns (exit code, notable lines, last lines)."""
    start = log.tell()
    log.write(f"\n===== {label} =====\n".encode())
    log.flush()
    try:
        code = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, stdout=log, stderr=subprocess.STDOUT).returncode
    except subprocess.TimeoutExpired:
        raise Stop(FAIL, f"hyperframes {label} timed out after {timeout}s; see {log_path}")
    log.flush()
    with open(log_path, "rb") as fh:
        fh.seek(start)
        text = fh.read().decode("utf-8", errors="replace")
    lines = [ANSI.sub("", seg).strip() for seg in re.split(r"[\r\n]+", text)]
    lines = [l for l in lines if l and not l.startswith("=====")]
    notable = []
    for l in lines:
        if NOTABLE.search(l) and l not in notable:
            notable.append(l[:300])
    return code, notable[:MAX_SHOWN], [l[:300] for l in lines[-15:]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--comp", required=True, help="composition folder, inside the work folder")
    ap.add_argument("--out", required=True, help="output file, inside the work folder")
    ap.add_argument("--work", help="work folder (default: current folder)")
    ap.add_argument("--fps", type=int, default=30, choices=(24, 25, 30, 50, 60))
    ap.add_argument("--quality", default="high", choices=("draft", "standard", "high"))
    ap.add_argument("--format", default="mp4", choices=sorted(EXT), dest="fmt")
    ap.add_argument("--quiet", action="store_true", help="print only stages, warnings, errors and the final line; full output goes to a log file in WORK/.hf-cache/logs")
    ap.add_argument("--use-system-browser", metavar="PATH", help="use this installed Chrome instead of the pinned browser; it makes its own background connections")
    ap.add_argument("--cache", help="cache folder inside the work folder (default: WORK/.hf-cache)")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds allowed for the render step")
    args = ap.parse_args()

    work = work_folder(args.work)
    comp = inside_work(args.comp, work, "--comp")
    out = inside_work(args.out, work, "--out")
    cache = inside_work(args.cache or work / ".hf-cache", work, "--cache")
    runtime = inside_work(work / "hyperframes-runtime", work, "runtime folder")
    if not comp.is_dir():
        raise Stop(USAGE, f"composition folder not found: {args.comp}")
    if out.suffix.lower() != EXT[args.fmt]:
        raise Stop(USAGE, f"--out must end in {EXT[args.fmt]} for --format {args.fmt}")
    if is_inside(out, comp) or out == comp or is_inside(out, runtime) or is_inside(out, cache) or out.is_dir():
        raise Stop(USAGE, "--out must be a new file outside the composition, runtime and cache folders")

    cli = runtime / "node_modules" / "hyperframes" / "dist" / "cli.js"
    node = shutil.which("node")
    if not node or not cli.is_file() or not runtime.is_dir():
        raise Stop(MISSING, f"renderer not installed in {runtime}; run hf_install.py first")
    refuse_linked_children(runtime, work, "the runtime folder")
    if has_symlink_below(work, cli) or has_symlink_below(work, cli.parents[1] / "package.json"):
        raise Stop(MISSING, "the renderer path contains a symbolic link; refused")
    pins = load_pins()
    try:
        have = json.loads((cli.parents[1] / "package.json").read_text(encoding="utf-8")).get("version")
        trust = json.loads((runtime / TRUST_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Stop(MISSING, "renderer not installed or its trust record is missing; run hf_install.py")
    if have != pins["hyperframes"]["version"]:
        raise Stop(MISSING, f"installed hyperframes is {have}, not the pinned version; run hf_install.py")
    if entry_hashes(runtime) != trust.get("entry_files"):
        raise Stop(MISSING, "the renderer's files differ from what was installed; remove hyperframes-runtime and run hf_install.py")
    if args.use_system_browser:
        browser = Path(args.use_system_browser)
        if not browser.is_file():
            raise Stop(USAGE, f"--use-system-browser file not found: {browser}")
        print("note: using an installed browser; it makes its own background connections", file=sys.stderr)
    else:
        rec = trust.get("browser")
        if not rec:
            raise Stop(MISSING, "no pinned browser was installed; run hf_install.py without --skip-browser")
        browser = inside_work(work / rec["path"], work, "pinned browser")
        if not browser.is_file() or sha256_file(browser) != rec["sha256"]:
            raise Stop(MISSING, "the pinned browser is missing or changed; remove .hf-cache/.cache and run hf_install.py")

    # 1. The local-only check. Nothing below runs unless it passes.
    check = [sys.executable, str(HERE / "check_local.py"), "--comp", str(comp), "--work", str(work)]
    if subprocess.run(check, stdout=sys.stderr, stderr=sys.stderr).returncode != 0:
        raise Stop(FAIL, "local-only check failed; nothing was rendered")
    print("stage check: ok", file=sys.stderr)

    ensure_dir(cache, work, "--cache")
    refuse_linked_children(cache, work, "the cache folder")
    for sub in ("tmp", "fonts"):
        ensure_dir(cache / sub, work, f"cache/{sub}")
    ensure_dir(out.parent, work, "--out folder")
    env = safe_env(cache, {"HYPERFRAMES_FONT_CACHE_DIR": str(cache / "fonts"), "HYPERFRAMES_BROWSER_PATH": str(browser),
                           "PRODUCER_HEADLESS_SHELL_PATH": str(browser), **NO_PHONE_HOME})
    base = [node, str(cli)]
    steps = [
        ("lint", base + ["lint", str(comp)], 300),
        ("validate", base + ["validate", str(comp)], 300),
        ("render", base + ["render", str(comp), "--output", str(out), "--fps", str(args.fps),
                           "--quality", args.quality, "--format", args.fmt, "--workers", "1"], args.timeout),
    ]
    log_path = None
    if args.quiet:
        ensure_dir(cache / "logs", work, "cache/logs")
        log_path = cache / "logs" / (out.name + ".log")
        log = open_log(log_path, work)
    for name, cmd, limit in steps:
        began = time.monotonic()
        if log_path:
            code, notable, tail = run_logged(cmd, comp, env, limit, log, log_path, name)
            for line in notable:
                print(f"  [{name}] {line}", file=sys.stderr)
            if code != 0:
                for line in tail:
                    print(f"  [{name}] {line}", file=sys.stderr)
        else:
            code = run(cmd, comp, env, limit).returncode
        print(f"stage {name}: {'ok' if code == 0 else 'FAILED'} ({time.monotonic() - began:.1f}s)", file=sys.stderr)
        if code != 0:
            hint = f"; full log: {log_path}" if log_path else ""
            raise Stop(FAIL, f"hyperframes {name} failed{hint}")
    if not out.is_file() or out.stat().st_size == 0:
        raise Stop(FAIL, "render finished but produced no output file")
    print(out)
    return OK


if __name__ == "__main__":
    run_main(main)
