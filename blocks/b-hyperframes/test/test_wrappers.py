"""Tests for hf_render.py and hf_install.py using stand-in `node` programs. No real renderer, no network."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from hfcommon import TRUST_FILE, entry_hashes, sha256_file  # noqa: E402

BLOCK = Path(__file__).resolve().parent.parent
RENDER = BLOCK / "scripts" / "hf_render.py"
INSTALL = BLOCK / "scripts" / "hf_install.py"
PINNED = json.loads((BLOCK / "pins.json").read_text())["hyperframes"]["version"]

FAKE_CLI = r"""
const fs = require('fs'), path = require('path');
const argv = process.argv.slice(2);
const keep = ['HOME', 'TMPDIR', 'HYPERFRAMES_NO_TELEMETRY', 'DO_NOT_TRACK', 'HYPERFRAMES_NO_UPDATE_CHECK',
  'HYPERFRAMES_NO_AUTO_INSTALL', 'HYPERFRAMES_FONT_CACHE_DIR', 'HYPERFRAMES_BROWSER_PATH', 'PRODUCER_HEADLESS_SHELL_PATH', 'SECRET_TEST_KEY', 'HTTPS_PROXY'];
const env = {}; for (const k of keep) env[k] = process.env[k] === undefined ? null : process.env[k];
fs.appendFileSync(path.join(process.env.CALL_LOG_DIR || process.cwd(), 'calls.jsonl'),
  JSON.stringify({ argv, cwd: process.cwd(), env }) + '\n');
if (argv[0] === 'render') { for (let n = 1; n <= 30; n++) console.log('\x1b[2K  Streaming frame ' + n + '/30'); console.log('[WARN] sample warning'); console.error('[non-blocking] Failed to load resource: 404'); }
const i = argv.indexOf('--output');
if (argv[0] === 'render' && i >= 0 && !fs.existsSync('no-output.flag')) fs.writeFileSync(argv[i + 1], 'fake video');
if (argv[0] === 'lint' && fs.existsSync('lint-fails.flag')) process.exit(1);
"""

FAKE_NPM = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
Path("npm-call.json").write_text(json.dumps({"argv": sys.argv[1:], "cache": os.environ.get("npm_config_cache"),
    "home": os.environ.get("HOME"), "secret": os.environ.get("SECRET_TEST_KEY")}))
pkg = Path("node_modules/hyperframes"); (pkg / "dist").mkdir(parents=True, exist_ok=True)
(pkg / "package.json").write_text(json.dumps({"name": "hyperframes", "version": "%s"}))
(pkg / "dist" / "cli.js").write_text(Path(%r).read_text())
pb = Path("node_modules/@puppeteer/browsers"); pb.mkdir(parents=True, exist_ok=True)
(pb / "package.json").write_text('{"name":"@puppeteer/browsers","version":"0.0.0","main":"index.js"}')
(pb / "index.js").write_text('''const fs=require('fs'),path=require('path');
exports.Browser={CHROMEHEADLESSSHELL:'chrome-headless-shell'};
exports.detectBrowserPlatform=()=> 'test';
exports.install=async(o)=>{const d=path.join(o.cacheDir,o.buildId);fs.mkdirSync(d,{recursive:true});
const e=path.join(d,'chrome-headless-shell');fs.writeFileSync(e,'fake browser '+o.buildId);return {executablePath:e};};''')
"""

PAGE = """<!DOCTYPE html><html><body>
<div id="root" data-composition-id="t" data-start="0" data-duration="1" data-width="360" data-height="640">
<script>window.__timelines = {};</script></div></body></html>"""

NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node is not installed")
class Wrappers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(os.path.realpath(self.tmp.name)) / "work"
        self.work.mkdir()
        self.comp = self.work / "comp"
        self.comp.mkdir()
        (self.comp / "index.html").write_text(PAGE)
        self.cli_src = self.work.parent / "fake_cli.js"
        self.cli_src.write_text(FAKE_CLI)

    def tearDown(self):
        self.tmp.cleanup()

    def fake_tools(self):
        bindir = self.work.parent / "bin"
        bindir.mkdir(exist_ok=True)
        npm = bindir / "npm"
        npm.write_text(FAKE_NPM % (PINNED, str(self.cli_src)))
        npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
        for tool in ("ffmpeg", "ffprobe"):
            (bindir / tool).write_text("#!/bin/sh\n")
            (bindir / tool).chmod(0o755)
        return bindir

    def install_fake_runtime(self, version=PINNED, trust=True):
        runtime = self.work / "hyperframes-runtime"
        pkg = runtime / "node_modules" / "hyperframes"
        (pkg / "dist").mkdir(parents=True)
        (pkg / "package.json").write_text(json.dumps({"name": "hyperframes", "version": version}))
        (pkg / "dist" / "cli.js").write_text(FAKE_CLI)
        exe = self.work / ".hf-cache" / ".cache" / "hyperframes" / "chrome" / "fake-shell"
        exe.parent.mkdir(parents=True)
        exe.write_text("pinned fake browser")
        if trust:
            rec = {"entry_files": entry_hashes(runtime),
                   "browser": {"path": str(exe.relative_to(self.work)), "sha256": sha256_file(exe), "version": "0"}}
            (runtime / TRUST_FILE).write_text(json.dumps(rec))
        self.exe = exe

    def render(self, *extra, env=None, comp="comp", out="out/v.mp4"):
        full = {**os.environ, "SECRET_TEST_KEY": "must-not-reach-the-child", "HTTPS_PROXY": "http://x:1"}
        full.update(env or {})
        cmd = [sys.executable, str(RENDER), "--comp", comp, "--out", out, "--work", str(self.work), *extra]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=self.work, env=full)

    def calls(self):
        log = self.comp / "calls.jsonl"
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    def test_render_runs_lint_validate_render_with_one_worker(self):
        self.install_fake_runtime()
        done = self.render("--fps", "60", "--quality", "draft", "--format", "mov", out="out/v.mov")
        self.assertEqual(done.returncode, 0, done.stderr)
        steps = self.calls()
        self.assertEqual([c["argv"][0] for c in steps], ["lint", "validate", "render"])
        render = steps[2]["argv"]
        self.assertEqual(render[render.index("--workers") + 1], "1")
        self.assertEqual(render[render.index("--fps") + 1], "60")
        self.assertEqual(render[render.index("--quality") + 1], "draft")
        self.assertEqual(render[render.index("--format") + 1], "mov")
        self.assertEqual(Path(render[render.index("--output") + 1]), self.work / "out" / "v.mov")
        self.assertEqual(Path(done.stdout.strip()), self.work / "out" / "v.mov")
        self.assertTrue((self.work / "out" / "v.mov").is_file())

    def test_environment_is_short_and_inside_the_work_folder(self):
        self.install_fake_runtime()
        self.assertEqual(self.render().returncode, 0)
        env = self.calls()[2]["env"]
        cache = self.work / ".hf-cache"
        self.assertEqual(env["HYPERFRAMES_NO_TELEMETRY"], "1")
        self.assertEqual(env["DO_NOT_TRACK"], "1")
        self.assertEqual(env["HYPERFRAMES_NO_UPDATE_CHECK"], "1")
        self.assertEqual(env["HYPERFRAMES_NO_AUTO_INSTALL"], "1")
        self.assertEqual(Path(env["HOME"]), cache)
        self.assertEqual(Path(env["TMPDIR"]), cache / "tmp")
        self.assertEqual(Path(env["HYPERFRAMES_FONT_CACHE_DIR"]), cache / "fonts")
        self.assertIsNone(env["SECRET_TEST_KEY"])
        self.assertIsNone(env["HTTPS_PROXY"])

    def test_failed_check_means_no_renderer_is_started(self):
        self.install_fake_runtime()
        (self.comp / "index.html").write_text(PAGE.replace("</div>", '<img src="https://example.com/a.png"></div>'))
        done = self.render()
        self.assertEqual(done.returncode, 1)
        self.assertIn("nothing was rendered", done.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.work / "out").exists())

    def test_lint_failure_stops_before_render(self):
        self.install_fake_runtime()
        (self.comp / "lint-fails.flag").write_text("x")
        done = self.render()
        self.assertEqual(done.returncode, 1)
        self.assertEqual([c["argv"][0] for c in self.calls()], ["lint"])

    def test_no_output_file_is_a_failure(self):
        self.install_fake_runtime()
        (self.comp / "no-output.flag").write_text("x")
        done = self.render()
        self.assertEqual(done.returncode, 1)
        self.assertIn("no output file", done.stderr)

    def test_quiet_prints_stages_and_warnings_and_logs_the_rest(self):
        self.install_fake_runtime()
        loud = self.render(out="out/loud.mp4")
        self.assertEqual(loud.returncode, 0, loud.stderr)
        self.assertIn("Streaming frame 30/30", loud.stderr + loud.stdout)
        done = self.render("--quiet")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("Streaming frame", done.stderr + done.stdout)
        for stage in ("stage check: ok", "stage lint: ok", "stage validate: ok", "stage render: ok"):
            self.assertIn(stage, done.stderr)
        self.assertIn("[WARN] sample warning", done.stderr)
        self.assertIn("[non-blocking]", done.stderr)
        self.assertEqual(Path(done.stdout.strip()), self.work / "out" / "v.mp4")
        log = self.work / ".hf-cache" / "logs" / "v.mp4.log"
        self.assertIn("Streaming frame 30/30", log.read_text())
        self.assertLess(len(done.stderr.splitlines()), 12)

    def test_quiet_failure_shows_the_tail_and_names_the_log(self):
        self.install_fake_runtime()
        (self.comp / "lint-fails.flag").write_text("x")
        done = self.render("--quiet")
        self.assertEqual(done.returncode, 1)
        self.assertIn("stage lint: FAILED", done.stderr)
        self.assertIn("full log:", done.stderr)

    def test_quiet_refuses_a_symlinked_log_folder(self):
        self.install_fake_runtime()
        outside = self.work.parent / "outside-logs"
        outside.mkdir()
        os.symlink(outside, self.work / ".hf-cache" / "logs")
        self.assertEqual(self.render("--quiet").returncode, 2)
        self.assertEqual(list(outside.iterdir()), [])

    def test_quiet_log_is_a_fresh_file_and_never_follows_planted_links(self):
        self.install_fake_runtime()
        outside = self.work.parent / "victim.txt"
        outside.write_text("precious")
        logs = self.work / ".hf-cache" / "logs"
        logs.mkdir()
        log = logs / "v.mp4.log"
        for plant in (os.symlink, os.link):
            with self.subTest(plant.__name__):
                if log.is_symlink() or log.exists():
                    log.unlink()
                plant(outside, log)
                done = self.render("--quiet")
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(outside.read_text(), "precious")
                self.assertFalse(log.is_symlink())
                self.assertEqual(log.stat().st_nlink, 1)
                self.assertIn("Streaming frame 30/30", log.read_text())
        # a second run replaces the log instead of appending to it
        first = log.read_text()
        self.assertEqual(self.render("--quiet").returncode, 0)
        self.assertEqual(log.read_text().count("===== lint ====="), first.count("===== lint ====="))

    def test_pinned_browser_is_passed_and_system_browser_is_opt_in(self):
        self.install_fake_runtime()
        self.assertEqual(self.render().returncode, 0)
        env = self.calls()[2]["env"]
        self.assertEqual(Path(env["HYPERFRAMES_BROWSER_PATH"]), self.exe)
        self.assertEqual(Path(env["PRODUCER_HEADLESS_SHELL_PATH"]), self.exe)
        # a browser path in the caller's environment does not redirect the renderer
        self.assertEqual(self.render(env={"HYPERFRAMES_BROWSER_PATH": "/bin/sh"}, out="out/b.mp4").returncode, 0)
        self.assertEqual(Path(self.calls()[5]["env"]["HYPERFRAMES_BROWSER_PATH"]), self.exe)
        other = self.work.parent / "system-chrome"
        other.write_text("x")
        done = self.render("--use-system-browser", str(other), out="out/c.mp4")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("background connections", done.stderr)
        self.assertEqual(Path(self.calls()[8]["env"]["HYPERFRAMES_BROWSER_PATH"]), other)

    def test_changed_entry_file_or_browser_is_refused(self):
        self.install_fake_runtime()
        cli = self.work / "hyperframes-runtime" / "node_modules" / "hyperframes" / "dist" / "cli.js"
        cli.write_text(FAKE_CLI + "\n// changed\n")
        done = self.render()
        self.assertEqual(done.returncode, 3)
        self.assertIn("differ", done.stderr)
        self.assertEqual(self.calls(), [])
        cli.write_text(FAKE_CLI)
        self.assertEqual(self.render().returncode, 0)
        self.exe.write_text("swapped browser")
        done = self.render(out="out/x.mp4")
        self.assertEqual(done.returncode, 3)
        self.assertIn("browser", done.stderr)

    def test_missing_trust_record_or_browser_record_is_refused(self):
        self.install_fake_runtime(trust=False)
        self.assertEqual(self.render().returncode, 3)
        trust = {"entry_files": entry_hashes(self.work / "hyperframes-runtime")}
        (self.work / "hyperframes-runtime" / TRUST_FILE).write_text(json.dumps(trust))
        done = self.render()
        self.assertEqual(done.returncode, 3)
        self.assertIn("no pinned browser", done.stderr)

    def test_symlinked_runtime_cache_or_output_folders_are_refused(self):
        outside = self.work.parent / "outside"
        outside.mkdir()
        self.install_fake_runtime()
        runtime = self.work / "hyperframes-runtime"
        moved = self.work.parent / "moved-runtime"
        runtime.rename(moved)
        os.symlink(moved, runtime)
        self.assertEqual(self.render().returncode, 2)
        self.assertEqual(self.calls(), [])
        os.unlink(runtime)
        moved.rename(runtime)
        cache = self.work / ".hf-cache"
        moved_cache = self.work.parent / "moved-cache"
        cache.rename(moved_cache)
        os.symlink(moved_cache, cache)
        self.assertEqual(self.render().returncode, 2)
        os.unlink(cache)
        moved_cache.rename(cache)
        os.symlink(outside, cache / "tmp")
        self.assertEqual(self.render().returncode, 2)
        os.unlink(cache / "tmp")
        self.assertEqual(list(outside.iterdir()), [])

    def test_output_may_not_be_an_input_or_inside_one(self):
        self.install_fake_runtime()
        for out in ("comp/index.html", "comp/out.mp4", "hyperframes-runtime/v.mp4", ".hf-cache/v.mp4"):
            with self.subTest(out):
                self.assertEqual(self.render(out=out).returncode, 2)
        (self.work / "out").mkdir()
        self.assertEqual(self.render(out="out").returncode, 2)
        self.assertEqual((self.comp / "index.html").read_text(), PAGE)

    def test_install_refuses_symlinked_folders_and_writes_nothing_outside(self):
        outside = self.work.parent / "outside"
        outside.mkdir()
        (outside / "node_modules").mkdir()
        (outside / "node_modules" / "keep.txt").write_text("keep")
        bindir = self.fake_tools()
        env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
        cmd = [sys.executable, str(INSTALL), "--work", str(self.work), "--skip-browser"]
        os.symlink(outside, self.work / "hyperframes-runtime")
        done = subprocess.run(cmd, capture_output=True, text=True, cwd=self.work, env=env)
        self.assertEqual(done.returncode, 2, done.stderr)
        os.unlink(self.work / "hyperframes-runtime")
        shutil.rmtree(self.work / ".hf-cache", ignore_errors=True)
        os.symlink(outside, self.work / ".hf-cache")
        self.assertEqual(subprocess.run(cmd, capture_output=True, text=True, cwd=self.work, env=env).returncode, 2)
        os.unlink(self.work / ".hf-cache")
        (self.work / "hyperframes-runtime").mkdir()
        os.symlink(outside, self.work / "hyperframes-runtime" / "node_modules")
        self.assertEqual(subprocess.run(cmd, capture_output=True, text=True, cwd=self.work, env=env).returncode, 2)
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ["node_modules"])
        self.assertEqual((outside / "node_modules" / "keep.txt").read_text(), "keep")

    def test_install_refuses_a_planted_npmrc(self):
        bindir = self.fake_tools()
        env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
        (self.work / "hyperframes-runtime").mkdir()
        (self.work / "hyperframes-runtime" / ".npmrc").write_text("registry=http://127.0.0.1:1/\n")
        done = subprocess.run([sys.executable, str(INSTALL), "--work", str(self.work), "--skip-browser"],
                              capture_output=True, text=True, cwd=self.work, env=env)
        self.assertEqual(done.returncode, 1)
        self.assertIn(".npmrc", done.stderr)
        self.assertFalse((self.work / "hyperframes-runtime" / "npm-call.json").exists())

    def test_renderer_not_installed_or_wrong_version(self):
        self.assertEqual(self.render().returncode, 3)
        self.install_fake_runtime(version="0.0.1")
        self.assertEqual(self.render().returncode, 3)

    def test_usage_errors(self):
        self.install_fake_runtime()
        self.assertEqual(self.render(out="../outside.mp4").returncode, 2)
        self.assertEqual(self.render(out="out/v.mov").returncode, 2)  # extension must match the format
        self.assertEqual(self.render("--fps", "7").returncode, 2)
        self.assertEqual(self.render("--quality", "ultra").returncode, 2)
        self.assertEqual(self.render(comp="../comp").returncode, 2)
        self.assertEqual(self.render(comp="nope").returncode, 2)
        self.assertEqual(self.calls(), [])

    def test_symlinked_output_folder_is_refused(self):
        self.install_fake_runtime()
        other = self.work.parent / "elsewhere"
        other.mkdir()
        os.symlink(other, self.work / "out")
        self.assertEqual(self.render().returncode, 2)
        self.assertEqual(list(other.iterdir()), [])

    def test_install_uses_lockfile_and_blocks_install_scripts(self):
        bindir = self.work.parent / "bin"
        bindir.mkdir()
        npm = bindir / "npm"
        npm.write_text(FAKE_NPM % (PINNED, str(self.cli_src)))
        npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
        for tool in ("ffmpeg", "ffprobe"):
            (bindir / tool).write_text("#!/bin/sh\n")
            (bindir / tool).chmod(0o755)
        env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "SECRET_TEST_KEY": "nope"}
        cmd = [sys.executable, str(INSTALL), "--work", str(self.work), "--skip-browser"]
        done = subprocess.run(cmd, capture_output=True, text=True, cwd=self.work, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        runtime = self.work / "hyperframes-runtime"
        call = json.loads((runtime / "npm-call.json").read_text())
        user_rc = str(self.work / ".hf-cache" / "empty-user.npmrc")
        global_rc = str(self.work / ".hf-cache" / "empty-global.npmrc")
        self.assertEqual(call["argv"], ["ci", "--ignore-scripts", "--no-audit", "--no-fund", "--registry",
                                         "https://registry.npmjs.org/", "--userconfig", user_rc, "--globalconfig", global_rc])
        self.assertEqual((self.work / ".hf-cache" / "empty-user.npmrc").read_bytes(), b"")
        self.assertEqual(Path(call["cache"]), self.work / ".hf-cache" / "npm")
        self.assertEqual(Path(call["home"]), self.work / ".hf-cache")
        self.assertIsNone(call["secret"])
        for name in ("package.json", "package-lock.json"):
            self.assertEqual((runtime / name).read_bytes(), (BLOCK / "runtime" / name).read_bytes())
        # a second run with the same files is fine; a changed lockfile is refused, not overwritten
        self.assertEqual(subprocess.run(cmd, capture_output=True, text=True, cwd=self.work, env=env).returncode, 0)
        (runtime / "package-lock.json").write_text("{}")
        again = subprocess.run(cmd, capture_output=True, text=True, cwd=self.work, env=env)
        self.assertEqual(again.returncode, 1)
        self.assertEqual((runtime / "package-lock.json").read_text(), "{}")

    def test_install_checks_the_browser_step(self):
        bindir = self.work.parent / "bin"
        bindir.mkdir()
        npm = bindir / "npm"
        npm.write_text(FAKE_NPM % (PINNED, str(self.cli_src)))
        npm.chmod(npm.stat().st_mode | stat.S_IEXEC)
        for tool in ("ffmpeg", "ffprobe"):
            (bindir / tool).write_text("#!/bin/sh\n")
            (bindir / tool).chmod(0o755)
        env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}"}
        done = subprocess.run([sys.executable, str(INSTALL), "--work", str(self.work)],
                              capture_output=True, text=True, cwd=self.work, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        trust = json.loads((self.work / "hyperframes-runtime" / TRUST_FILE).read_text())
        exe = self.work / trust["browser"]["path"]
        self.assertTrue(exe.is_file())
        self.assertIn(".hf-cache", str(exe))
        self.assertEqual(trust["browser"]["sha256"], sha256_file(exe))
        self.assertIn("dist/cli.js", " ".join(trust["entry_files"]))

    def test_install_needs_ffmpeg(self):
        bindir = self.work.parent / "bin-no-ffmpeg"
        bindir.mkdir()
        os.symlink(NODE, bindir / "node")
        (bindir / "npm").write_text("#!/bin/sh\n")
        (bindir / "npm").chmod(0o755)
        env = {**os.environ, "PATH": str(bindir)}
        done = subprocess.run([sys.executable, str(INSTALL), "--work", str(self.work)],
                              capture_output=True, text=True, cwd=self.work, env=env)
        self.assertEqual(done.returncode, 3)
        self.assertIn("ffmpeg", done.stderr)

    def test_install_refuses_cache_outside_work(self):
        done = subprocess.run([sys.executable, str(INSTALL), "--work", str(self.work), "--cache", str(self.work.parent / "c")],
                              capture_output=True, text=True, cwd=self.work)
        self.assertEqual(done.returncode, 2)


class ShippedFiles(unittest.TestCase):
    def test_package_json_pins_an_exact_version(self):
        pkg = json.loads((BLOCK / "runtime" / "package.json").read_text())
        self.assertEqual(pkg["dependencies"], {"hyperframes": PINNED})

    def test_lockfile_matches_pins_and_uses_only_the_public_registry(self):
        lock = json.loads((BLOCK / "runtime" / "package-lock.json").read_text())
        pins = json.loads((BLOCK / "pins.json").read_text())["hyperframes"]
        self.assertEqual(lock["packages"]["node_modules/hyperframes"]["version"], PINNED)
        self.assertEqual(lock["packages"]["node_modules/hyperframes"]["integrity"], pins["tarball_integrity"])
        for name, meta in lock["packages"].items():
            if not name:
                continue
            self.assertTrue(meta.get("integrity", "").startswith("sha512-"), name)
            self.assertTrue(meta.get("resolved", "").startswith("https://registry.npmjs.org/"), name)


if __name__ == "__main__":
    unittest.main()
