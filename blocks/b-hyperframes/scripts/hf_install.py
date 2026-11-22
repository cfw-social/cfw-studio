#!/usr/bin/env python3
"""Install the pinned HyperFrames renderer and its pinned browser inside the work folder.

    python3 hf_install.py [--work work] [--skip-browser]

Copies this block's package.json and package-lock.json into WORK/hyperframes-runtime/
and runs `npm ci --ignore-scripts` there, with npm's config files pointed at an empty
file. Then downloads the pinned Chrome headless shell into WORK/.hf-cache and records
the SHA-256 of the package's entry files and of the browser in
WORK/hyperframes-runtime/.hf-trust.json, which hf_render.py re-checks.
Nothing is installed globally. Every folder written, deleted or run from is checked
to be inside the work folder with no symbolic link on the way.

Exit codes: 0 done, 1 install or check failed, 2 bad usage, 3 node, npm, ffmpeg or ffprobe missing.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hfcommon import (BLOCK_DIR, FAIL, MISSING, OK, TRUST_FILE, USAGE, Stop, atomic_write, ensure_dir,  # noqa: E402
                      entry_hashes, inside_work, is_inside, load_pins, refuse_linked_children, run_main,
                      safe_env, sha256_file, work_folder)

NO_PHONE_HOME = {
    "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1",
    "HYPERFRAMES_NO_UPDATE_CHECK": "1", "HYPERFRAMES_NO_AUTO_INSTALL": "1",
}


def run(cmd, cwd, env, timeout, capture=False):
    """Run an argument list. Output goes to stderr so stdout stays clean, unless captured."""
    try:
        if capture:
            done = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, stdout=subprocess.PIPE, stderr=sys.stderr, text=True)
        else:
            done = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, stdout=sys.stderr, stderr=sys.stderr)
    except subprocess.TimeoutExpired:
        raise Stop(FAIL, f"timed out after {timeout}s: {Path(cmd[0]).name}")
    return done


def node_ok(node):
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        return int(out.lstrip("v").split(".")[0]) >= 22
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", help="work folder (default: current folder)")
    ap.add_argument("--cache", help="cache folder inside the work folder (default: WORK/.hf-cache)")
    ap.add_argument("--skip-browser", action="store_true", help="do not download the pinned browser")
    args = ap.parse_args()

    work = work_folder(args.work)
    cache = ensure_dir(args.cache or work / ".hf-cache", work, "--cache")
    runtime = ensure_dir(work / "hyperframes-runtime", work, "runtime folder")
    refuse_linked_children(cache, work, "the cache folder")
    refuse_linked_children(runtime, work, "the runtime folder")
    if (runtime / ".npmrc").exists():
        raise Stop(FAIL, f"{runtime / '.npmrc'} exists; a project npm config could redirect the install. Remove it and run again")
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm or not node_ok(node):
        raise Stop(MISSING, "Node.js 22 or newer and npm are required and were not found")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise Stop(MISSING, "ffmpeg and ffprobe (version 6 or newer) are required for rendering and were not found")

    pins = load_pins()
    lock = json.loads((BLOCK_DIR / "runtime" / "package-lock.json").read_text(encoding="utf-8"))
    if lock["packages"]["node_modules/hyperframes"]["integrity"] != pins["hyperframes"]["tarball_integrity"]:
        raise Stop(FAIL, "the shipped lockfile does not match pins.json; refusing to install")

    for name in ("package.json", "package-lock.json"):
        src, dst = BLOCK_DIR / "runtime" / name, runtime / name
        data = src.read_bytes()
        if dst.exists() and dst.read_bytes() != data:
            raise Stop(FAIL, f"{dst} differs from the block's {name}; remove {runtime} and run again")
        atomic_write(dst, data)
    for sub in ("tmp", "npm"):
        ensure_dir(cache / sub, work, f"cache/{sub}")
    user_rc, global_rc = cache / "empty-user.npmrc", cache / "empty-global.npmrc"
    atomic_write(user_rc, b"")
    atomic_write(global_rc, b"")

    env = safe_env(cache, {"npm_config_cache": str(cache / "npm"), "npm_config_registry": "https://registry.npmjs.org/",
                           "npm_config_userconfig": str(user_rc), "npm_config_globalconfig": str(global_rc),
                           "npm_config_update_notifier": "false", **NO_PHONE_HOME})
    cmd = [npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--registry", "https://registry.npmjs.org/",
           "--userconfig", str(user_rc), "--globalconfig", str(global_rc)]
    if run(cmd, runtime, env, 900).returncode != 0:
        raise Stop(FAIL, "npm ci failed")

    pkg_json = runtime / "node_modules" / "hyperframes" / "package.json"
    pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
    if pkg.get("version") != pins["hyperframes"]["version"]:
        raise Stop(FAIL, f"installed hyperframes {pkg.get('version')}, expected {pins['hyperframes']['version']}")
    trust = {"entry_files": entry_hashes(runtime)}

    if not args.skip_browser:
        fetch = [node, str(BLOCK_DIR / "scripts" / "fetch_browser.mjs"), "--runtime", str(runtime),
                 "--cache", str(cache / ".cache" / "hyperframes" / "chrome"), "--version", pins["chrome"]["version"]]
        ensure_dir(cache / ".cache" / "hyperframes" / "chrome", work, "browser cache")
        done = run(fetch, runtime, env, 1800, capture=True)
        exe = next((l.split(": ", 1)[1].strip() for l in done.stdout.splitlines() if l.startswith("BROWSER_EXE: ")), None)
        if done.returncode != 0 or not exe:
            raise Stop(FAIL, "the pinned browser could not be downloaded")
        exe = inside_work(exe, work, "the downloaded browser")
        if not exe.is_file():
            raise Stop(FAIL, "the downloaded browser file is missing")
        trust["browser"] = {"path": str(exe.relative_to(work)).replace("\\", "/"), "sha256": sha256_file(exe),
                            "version": pins["chrome"]["version"]}
    atomic_write(runtime / TRUST_FILE, (json.dumps(trust, indent=2) + "\n").encode())
    print(f"HYPERFRAMES {pkg['version']} installed in {runtime}", file=sys.stderr)
    print(runtime)
    return OK


if __name__ == "__main__":
    run_main(main)
