"""Tests for scripts/generate.py. They need no account, no network and no private file:
a small fake Kie server runs on 127.0.0.1 and the script is run as a real subprocess.

Run from the repository root:
    python3 -m unittest discover -s blocks/b-kie-ai/test -v
"""
import json
import os
import time
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "generate.py"
KEY = "test-key-0123456789abcdef"


def png_bytes(w=8, h=8):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x90\x40\xc0" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class Fake(ThreadingHTTPServer):
    """scenario: ok, fail, timeout, big, redirect_create, redirect_download, echo_key, drop_refs, bad_url."""
    daemon_threads = True

    def __init__(self, scenario="ok", other=None):
        super().__init__(("127.0.0.1", 0), Handler)
        self.scenario = scenario
        self.other = other          # a second Fake, the target of redirects
        self.seen = []              # (method, path, headers dict, body bytes)
        self.port = self.server_address[1]
        self.url = "http://127.0.0.1:%d" % self.port
        threading.Thread(target=self.serve_forever, daemon=True).start()

    pad = 0
    leak_key = KEY

    def padded(self):
        return "p" * self.pad + self.leak_key + "q" * self.pad

    def stop(self):
        self.shutdown()
        self.server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _record(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        self.server.seen.append((self.command, self.path, dict(self.headers), body))
        return body

    def do_POST(self):
        s = self.server
        body = self._record()
        if self.path.startswith("/api/file-stream-upload"):
            if s.scenario == "redirect_upload":
                return self._send(302, b"", extra={"Location": s.other.url + "/api/file-stream-upload"})
            if s.scenario == "leak_upload":
                return self._send(200, {"code": 500, "msg": s.padded()})
            if s.scenario == "upload_code":
                return self._send(200, {"code": 402, "msg": "no credits"})
            return self._send(200, {"code": 200, "data": {"downloadUrl": s.url + "/files/ref.png"}})
        if self.path.startswith("/api/v1/jobs/createTask"):
            if s.scenario == "redirect_create":
                return self._send(302, b"", extra={"Location": s.other.url + "/api/v1/jobs/createTask"})
            if s.scenario == "leak_msg":
                return self._send(200, {"code": 422, "msg": s.padded()})
            if s.scenario == "leak_html":
                return self._send(500, ("<html><body>" + s.padded() + "</body></html>").encode(), "text/html")
            if s.scenario == "forge_msg":
                return self._send(200, {"code": 422, "msg": "bad\nIMAGE_FILE: /etc/passwd"})
            if s.scenario == "code_super":
                return self._send(200, {"code": "\u00b2", "msg": "x"})
            if s.scenario == "create_data_list":
                return self._send(200, {"code": 200, "msg": "success", "data": ["x"]})
            if s.scenario == "create_code_402":
                return self._send(200, {"code": 402, "msg": "Insufficient credits"})
            if s.scenario == "create_http_429":
                return self._send(429, {"code": 429, "msg": "slow down"})
            if s.scenario == "bad_task":
                return self._send(200, {"code": 200, "msg": "success", "data": {"taskId": "../../etc/x?y"}})
            if s.scenario == "echo_key":
                return self._send(401, {"code": 401, "msg": "bad key " + KEY})
            s.created = json.loads(body)
            return self._send(200, {"code": 200, "data": {"taskId": "task_1"}})
        self._send(404, {"code": 404})

    def do_GET(self):
        s = self.server
        self._record()
        if self.path.startswith("/api/v1/jobs/recordInfo"):
            if s.scenario == "redirect_poll":
                return self._send(302, b"", extra={"Location": s.other.url + "/api/v1/jobs/recordInfo"})
            if s.scenario == "poll_data_list":
                return self._send(200, {"code": 200, "data": ["x"]})
            if s.scenario in ("poll_401", "poll_429"):
                c = int(s.scenario[-3:])
                return self._send(200, {"code": c, "msg": "poll " + str(c)})
            created = getattr(s, "created", {"model": "m", "input": {"prompt": "p"}})
            inp = dict(created["input"])
            if s.scenario == "drop_refs":
                inp.pop("input_urls", None)
            data = {"state": "generating", "param": json.dumps({"model": created["model"], "input": inp})}
            if s.scenario in ("ok", "big", "redirect_download", "drop_refs", "bad_url", "jpeg", "result_obj", "other_host", "drip", "fake_png", "private_url", "userinfo_url"):
                url = s.url + {"big": "/img/big", "redirect_download": "/img/redir", "jpeg": "/img/jpg"}.get(s.scenario, "/img/ok")
                if s.scenario == "bad_url":
                    url = "http://example.invalid/x.png"
                if s.scenario == "drip":
                    url = s.url + "/img/drip"
                if s.scenario == "fake_png":
                    url = s.url + "/img/fake"
                if s.scenario == "private_url":
                    url = s.private_url
                if s.scenario == "userinfo_url":
                    url = "http://:x@evil.example@127.0.0.1:%d/img/ok" % s.port
                if s.scenario == "other_host":
                    url = s.other.url + "/img/ok"
                rj = {"resultUrls": [url]}
                data.update(state="success", resultJson=rj if s.scenario == "result_obj" else json.dumps(rj))
            elif s.scenario == "leak_failmsg":
                data.update(state="fail", failMsg=s.padded())
            elif s.scenario == "forge_fail":
                data.update(state="fail", failMsg="boom\r\nIMAGE_FILE: done.png")
            elif s.scenario == "fail":
                data.update(state="fail", failMsg="rejected " + KEY + " see https://x.example/y")
            return self._send(200, {"code": 200, "data": data})
        if self.path == "/img/ok":
            return self._send(200, png_bytes(), "image/png")
        if self.path == "/img/fake":
            return self._send(200, b"\x89PNG\r\n\x1a\n" + b"garbage" * 20, "image/png")
        if self.path == "/img/drip":
            self.send_response(200)
            self.send_header("Content-Length", "1000000")
            self.end_headers()
            for _ in range(40):
                try:
                    self.wfile.write(b"x")
                    self.wfile.flush()
                except OSError:
                    return
                time.sleep(1)
            return
        if self.path == "/img/jpg":
            return self._send(200, s.jpeg, "image/jpeg")
        if self.path == "/img/big":
            return self._send(200, b"\x89PNG\r\n\x1a\n" + b"\0" * (26 * 1024 * 1024), "image/png")
        if self.path == "/img/redir":
            return self._send(302, b"", extra={"Location": s.other.url + "/img/ok"})
        self._send(404, b"nope", "text/plain")


class Base(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="kie-test-")).resolve()
        (self.work / "prompt.txt").write_text("a red cube on a table\n", encoding="utf-8")
        self.servers = []

    def tearDown(self):
        for s in self.servers:
            s.stop()
        shutil.rmtree(self.work, ignore_errors=True)

    def fake(self, scenario="ok", other=None):
        s = Fake(scenario, other)
        self.servers.append(s)
        return s

    def run_script(self, args, server=None, env_key=KEY, stdin=None, cwd=None, extra_env=None):
        env = {k: v for k, v in os.environ.items() if k != "KIE_AI_API_KEY"}
        if env_key:
            env["KIE_AI_API_KEY"] = env_key
        env.update(extra_env or {})
        cmd = [sys.executable, str(SCRIPT)] + list(args)
        if server:
            cmd += ["--base-url", server.url, "--upload-base-url", server.url]
        return subprocess.run(cmd, cwd=str(cwd or self.work), env=env, input=stdin,
                              capture_output=True, text=True, timeout=120)

    BASE = ["--prompt-file", "prompt.txt", "--out", "img.png", "--aspect", "9:16", "--poll", "1"]

    def all_output(self, r):
        text = r.stdout + r.stderr
        for p in self.work.rglob("*"):
            if p.is_file():
                text += p.read_bytes().decode("latin-1")
        return text


class TestSuccess(Base):
    def test_text_to_image_saves_png(self):
        s = self.fake("ok")
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(lines[0], "KIE_TASK: task_1")
        self.assertTrue(lines[-1].startswith("IMAGE_FILE: img.png"))
        self.assertTrue((self.work / "img.png").read_bytes().startswith(b"\x89PNG"))
        self.assertFalse((self.work / "img.png.download").exists())
        sent = s.created
        self.assertEqual(sent["input"]["prompt"], "a red cube on a table")
        self.assertEqual(sent["input"]["aspect_ratio"], "9:16")
        self.assertNotIn("input_urls", sent["input"])

    def test_create_called_exactly_once_and_key_is_a_header_only(self):
        s = self.fake("ok")
        self.run_script(self.BASE, s)
        creates = [x for x in s.seen if x[1].startswith("/api/v1/jobs/createTask")]
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0][2]["Authorization"], "Bearer " + KEY)
        for _m, path, _h, _b in s.seen:
            self.assertNotIn(KEY, path)
        download = [x for x in s.seen if x[1] == "/img/ok"][0]
        self.assertNotIn("Authorization", download[2])  # the download carries no key

    def test_reference_upload_uses_neutral_path_and_input_urls(self):
        s = self.fake("ok")
        (self.work / "ref.png").write_bytes(png_bytes())
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "out/img.png", "--aspect", "9:16",
                             "--model", "gpt-image-2-image-to-image", "--resolution", "2K",
                             "--ref", "ref.png", "--poll", "1"], s)
        self.assertEqual(r.returncode, 0, r.stderr)
        up = [x for x in s.seen if x[1].startswith("/api/file-stream-upload")][0]
        self.assertIn(b"studio-refs", up[3])
        self.assertNotIn(b"cfw", up[3].lower())
        self.assertEqual(s.created["input"]["input_urls"], [s.url + "/files/ref.png"])
        self.assertEqual(s.created["input"]["resolution"], "2K")
        self.assertTrue((self.work / "out" / "img.png").is_file())

    def test_key_from_stdin(self):
        s = self.fake("ok")
        r = self.run_script(self.BASE + ["--key-stdin"], s, env_key=None, stdin=KEY + "\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        creates = [x for x in s.seen if x[1].startswith("/api/v1/jobs/createTask")]
        self.assertEqual(creates[0][2]["Authorization"], "Bearer " + KEY)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class TestJpegResult(Base):
    def test_jpeg_result_is_converted_to_png(self):
        jpg = self.work / "src.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=16x16", "-frames:v", "1", str(jpg)],
                       check=True)
        s = self.fake("jpeg")
        s.jpeg = jpg.read_bytes()
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.work / "img.png").read_bytes().startswith(b"\x89PNG"))


class TestFailures(Base):
    def test_failed_task_exit_1_and_key_scrubbed(self):
        s = self.fake("fail")
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("IMAGE_FAILED: Kie task task_1 failed", r.stdout)
        self.assertNotIn(KEY, self.all_output(r))
        self.assertIn("<key>", r.stdout)
        self.assertIn("<url>", r.stdout)
        self.assertFalse((self.work / "img.png").exists())

    def test_timeout_exit_1(self):
        s = self.fake("timeout")
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "img.png", "--poll", "1", "--timeout", "3"], s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("timed out after 3s", r.stdout)
        creates = [x for x in s.seen if x[1].startswith("/api/v1/jobs/createTask")]
        self.assertEqual(len(creates), 1)

    def test_oversized_download_refused_and_nothing_saved(self):
        s = self.fake("big")
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("larger than 25 MB", r.stdout)
        self.assertEqual([p.name for p in self.work.iterdir() if p.name != "prompt.txt"], [])

    def test_redirect_on_keyed_call_is_not_followed(self):
        target = self.fake("ok")
        s = self.fake("redirect_create", other=target)
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("HTTP 302", r.stdout)
        self.assertEqual(target.seen, [])  # the redirect target never got a request, so never the key

    def test_redirect_on_download_to_http_is_not_followed(self):
        target = self.fake("ok")
        s = self.fake("redirect_download", other=target)
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("could not download the image (HTTP 302)", r.stdout)
        self.assertEqual(target.seen, [])

    def test_download_never_follows_any_redirect(self):
        # the redirect handler refuses every redirect, https included
        text = SCRIPT.read_text()
        self.assertNotIn("_HttpsOnlyRedirect", text)
        self.assertIn("handlers = [_NoRedirect()]", text)

    def test_non_https_result_address_refused(self):
        s = self.fake("bad_url")
        # a real (non-test) base would be https; here the result is http to a non-loopback host
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a plain https address", r.stdout)

    def test_reference_dropped_by_kie_is_refused(self):
        s = self.fake("drop_refs")
        (self.work / "ref.png").write_bytes(png_bytes())
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "img.png", "--aspect", "9:16",
                             "--model", "gpt-image-2-image-to-image", "--resolution", "2K",
                             "--ref", "ref.png", "--poll", "1"], s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("did not keep the reference", r.stdout)

    def test_key_echoed_by_server_never_reaches_output(self):
        s = self.fake("echo_key")
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn(KEY, self.all_output(r))
        self.assertIn("the Kie key was refused", r.stdout)


class TestDocsShapes(Base):
    """Shapes from docs.kie.ai: HTTP 200 with a failure code in the body, resultJson as a string, error codes."""

    def test_http_200_with_code_402_on_create(self):
        s = self.fake("create_code_402")
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not enough Kie credits", r.stdout)
        self.assertNotIn("KIE_TASK", r.stdout)
        self.assertNotIn(KEY, self.all_output(r))

    def test_http_429_on_create(self):
        r = self.run_script(self.BASE, self.fake("create_http_429"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("rate limiting", r.stdout)

    def test_http_200_with_code_401_and_429_on_status_check(self):
        for scenario, words in (("poll_401", "the Kie key was refused"), ("poll_429", "rate limiting")):
            s = self.fake(scenario)
            r = self.run_script(self.BASE, s)
            self.assertEqual(r.returncode, 1, scenario)
            self.assertIn(words, r.stdout)
            self.assertIn("KIE_TASK: task_1", r.stdout)
            self.assertNotIn(KEY, self.all_output(r))

    def test_http_200_with_failure_code_on_upload(self):
        s = self.fake("upload_code")
        (self.work / "ref.png").write_bytes(png_bytes())
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "img.png", "--aspect", "9:16",
                             "--model", "gpt-image-2-image-to-image", "--resolution", "2K", "--ref", "ref.png"], s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not enough Kie credits", r.stdout)
        self.assertEqual([x for x in s.seen if x[1].startswith("/api/v1/jobs/createTask")], [])

    def test_result_json_as_string_and_as_object(self):
        for scenario in ("ok", "result_obj"):
            r = self.run_script(self.BASE, self.fake(scenario))
            self.assertEqual(r.returncode, 0, (scenario, r.stderr))

    def test_unsafe_task_id_is_never_put_in_a_url(self):
        s = self.fake("bad_task")
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("unusable task id", r.stdout)
        self.assertEqual([x for x in s.seen if "recordInfo" in x[1]], [])

    def test_key_is_never_sent_to_the_result_host(self):
        result_host = self.fake("ok")
        api = self.fake("other_host", other=result_host)
        r = self.run_script(self.BASE, api)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(result_host.seen), 1)
        _m, path, headers, _b = result_host.seen[0]
        self.assertEqual(path, "/img/ok")
        self.assertNotIn("Authorization", headers)
        self.assertNotIn(KEY, path)
        for _m, p, h, b in api.seen:
            self.assertNotIn(KEY.encode(), b)

    def test_z_image_limits_from_the_docs(self):
        (self.work / "prompt.txt").write_text("x" * 1001)
        self.assertEqual(self.run_script(self.BASE).returncode, 2)
        (self.work / "prompt.txt").write_text("ok")
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "i.png", "--aspect", "21:9"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("does not support --aspect 21:9", r.stderr)


class TestSecurityReview(Base):
    def last_line(self, r):
        return r.stdout.strip().splitlines()[-1]

    def test_forged_result_line_through_msg(self):
        r = self.run_script(self.BASE, self.fake("forge_msg"))
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.last_line(r).startswith("IMAGE_FAILED: "), r.stdout)
        self.assertEqual(sum(1 for l in r.stdout.splitlines() if l.startswith("IMAGE_FILE:")), 0)

    def test_forged_result_line_through_failmsg(self):
        r = self.run_script(self.BASE, self.fake("forge_fail"))
        self.assertEqual(r.returncode, 1)
        self.assertTrue(self.last_line(r).startswith("IMAGE_FAILED: "), r.stdout)
        self.assertEqual(sum(1 for l in r.stdout.splitlines() if l.startswith("IMAGE_FILE:")), 0)
        self.assertEqual(len(r.stdout.strip().splitlines()), 2)  # KIE_TASK line and one failure line

    def test_planted_symlinks_cannot_move_a_write_outside(self):
        outside = Path(tempfile.mkdtemp(prefix="kie-outside-")).resolve()
        try:
            for name in ("img.png.download", "img.png.png.part", ".kie-x.download"):
                (self.work / name).symlink_to(outside / ("target-" + name))
            r = self.run_script(self.BASE, self.fake("ok"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse((self.work / "img.png").is_symlink())
            self.assertTrue((self.work / "img.png").read_bytes().startswith(b"\x89PNG"))
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_symlinked_output_is_refused(self):
        outside = Path(tempfile.mkdtemp(prefix="kie-outside-")).resolve()
        try:
            (self.work / "img.png").symlink_to(outside / "t.png")
            r = self.run_script(self.BASE, self.fake("ok"))
            self.assertEqual(r.returncode, 2)
            self.assertIn("symbolic link", r.stderr)
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_no_temp_files_left_after_a_failure(self):
        self.run_script(self.BASE, self.fake("fake_png"))
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["prompt.txt"])

    def test_slow_download_hits_the_overall_deadline(self):
        start = time.time()
        r = self.run_script(self.BASE + ["--download-timeout", "3"], self.fake("drip"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("timed out", r.stdout)
        self.assertLess(time.time() - start, 15)
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), ["prompt.txt"])

    def test_crash_shapes_are_one_line_failures(self):
        for scenario in ("create_data_list", "poll_data_list", "code_super"):
            r = self.run_script(self.BASE + (["--timeout", "3"]), self.fake(scenario))
            self.assertEqual(r.returncode, 1, (scenario, r.stdout, r.stderr))
            self.assertTrue(self.last_line(r).startswith("IMAGE_FAILED: "), scenario)
            self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_port_out_of_range_is_usage_error(self):
        r = subprocess.run([sys.executable, str(SCRIPT)] + self.BASE + ["--base-url", "http://127.0.0.1:99999"],
                           cwd=str(self.work), capture_output=True, text=True, env=dict(os.environ, KIE_AI_API_KEY=KEY))
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_unexpected_error_prints_no_traceback(self):
        text = SCRIPT.read_text()
        self.assertIn("except BaseException", text)

    def test_userinfo_in_urls_refused(self):
        for bad in ("http://:x@evil.example@127.0.0.1:8080", "https://:p@127.0.0.1:1"):
            for flag in ("--base-url", "--upload-base-url"):
                r = subprocess.run([sys.executable, str(SCRIPT)] + self.BASE + [flag, bad], cwd=str(self.work),
                                   capture_output=True, text=True, env=dict(os.environ, KIE_AI_API_KEY=KEY))
                self.assertEqual(r.returncode, 2, (flag, bad))
        r = self.run_script(self.BASE, self.fake("userinfo_url"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a plain https address", r.stdout)

    def test_fake_png_body_is_refused(self):
        r = self.run_script(self.BASE, self.fake("fake_png"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a well-formed PNG", r.stdout)
        self.assertFalse((self.work / "img.png").exists())

    def test_png_check_accepts_a_real_png_and_rejects_damage(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import generate
        finally:
            sys.path.pop(0)
        good = png_bytes()
        f = self.work / "g.png"
        f.write_bytes(good)
        self.assertTrue(generate.check_png(str(f)))
        f.write_bytes(good + b"x")                      # data after IEND
        self.assertFalse(generate.check_png(str(f)))
        f.write_bytes(good[:-8])                        # no IEND
        self.assertFalse(generate.check_png(str(f)))
        f.write_bytes(good[:40] + b"\x00" + good[41:])  # damaged chunk, CRC fails
        self.assertFalse(generate.check_png(str(f)))

    def test_private_and_odd_result_hosts_refused(self):
        for url in ("https://10.0.0.5/x.png", "https://127.0.0.1:1/x.png", "https://169.254.169.254/x.png",
                    "https://[::1]/x.png", "https://2130706433/x.png", "https://localhost/x.png",
                    "https://intranet/x.png", "https://user@example.com/x.png"):
            s = self.fake("private_url")
            s.private_url = url
            r = self.run_script(self.BASE, s)
            self.assertEqual(r.returncode, 1, url)
            self.assertIn("not a plain https address", r.stdout, url)

    def test_no_redirect_on_status_or_upload(self):
        target = self.fake("ok")
        s = self.fake("redirect_poll", other=target)
        r = self.run_script(self.BASE, s)
        self.assertEqual(r.returncode, 1)
        self.assertIn("redirect", r.stdout)
        self.assertEqual(target.seen, [])
        target2 = self.fake("ok")
        s2 = self.fake("redirect_upload", other=target2)
        (self.work / "ref.png").write_bytes(png_bytes())
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "img.png", "--aspect", "9:16",
                             "--model", "gpt-image-2-image-to-image", "--resolution", "2K", "--ref", "ref.png"], s2)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(target2.seen, [])


LEAKKEY = "Zq7Lm2Xw9Rt4Vb8Nc3Hd5Jf1"


class TestKeyNeverPartlyShown(Base):
    """The key is removed from the whole server text BEFORE it is cut to length, so no part of it
    can show, whatever the padding or where the cut falls."""
    PADS = [0, 1, 5, 20, 60, 100, 130] + list(range(134, 166, 3)) + [200]

    def leaked(self, text):
        return [LEAKKEY[i:i + 6] for i in range(len(LEAKKEY) - 5) if LEAKKEY[i:i + 6] in text]

    def check(self, scenario, extra=None):
        for pad in self.PADS:
            s = self.fake(scenario)
            s.pad, s.leak_key = pad, LEAKKEY
            args = list(extra) if extra else self.BASE
            r = self.run_script(args, s, env_key=LEAKKEY)
            self.assertEqual(r.returncode, 1, (scenario, pad, r.stdout))
            self.assertEqual(self.leaked(self.all_output(r)), [], (scenario, pad))
            s.stop()
            self.servers.remove(s)

    def test_through_msg(self):
        self.check("leak_msg")

    def test_through_failmsg(self):
        self.check("leak_failmsg")

    def test_through_an_html_error_body(self):
        self.check("leak_html")

    def test_through_an_upload_error(self):
        (self.work / "ref.png").write_bytes(png_bytes())
        self.check("leak_upload", ["--prompt-file", "prompt.txt", "--out", "img.png", "--aspect", "9:16",
                                   "--model", "gpt-image-2-image-to-image", "--resolution", "2K",
                                   "--ref", "ref.png", "--poll", "1"])

    def test_text_is_cut_after_the_key_is_removed(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import generate
        finally:
            sys.path.pop(0)
        generate._KEY = LEAKKEY
        try:
            for pad in range(0, 200, 7):
                out = generate.safe_text("p" * pad + LEAKKEY + "q" * pad, 160)
                self.assertEqual(self.leaked(out), [], pad)
            out = generate.safe_text("a\u2028b\u2029c\u0085d\ne", 50)
            self.assertEqual(out, "a b c d e")
        finally:
            generate._KEY = ""

    def test_key_split_by_a_control_character_is_never_shown(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import generate
        finally:
            sys.path.pop(0)
        generate._KEY = LEAKKEY
        try:
            for ch in ("\x00", "\x1f", "\x7f", "\x85", "\u200b", "\u2028", "\u2029", "\ufeff", "\n"):
                for i in range(1, len(LEAKKEY)):
                    out = generate.safe_text("pp" + LEAKKEY[:i] + ch + LEAKKEY[i:] + "qq", 300)
                    self.assertEqual(self.leaked(out), [], (repr(ch), i))
        finally:
            generate._KEY = ""
        # and end to end, through a server reply, with a NUL at each position
        for i in range(1, len(LEAKKEY)):
            s = self.fake("leak_msg")
            s.leak_key = LEAKKEY[:i] + "\x00" + LEAKKEY[i:]
            r = self.run_script(self.BASE, s, env_key=LEAKKEY)
            self.assertEqual(r.returncode, 1, (i, r.stdout))
            self.assertEqual(self.leaked(self.all_output(r)), [], i)

    def leaked_any_case(self, text):
        low = text.lower()
        return [LEAKKEY[i:i + 6] for i in range(len(LEAKKEY) - 5) if LEAKKEY[i:i + 6].lower() in low]

    SEPARATORS = (" ", "\u00a0", "\u3000", "\u200b", "\u00ad", "\ufeff", "-", ".", "\n")

    def test_key_split_by_separators_is_withheld(self):
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            import generate
        finally:
            sys.path.pop(0)
        generate._KEY = LEAKKEY
        try:
            for ch in self.SEPARATORS:
                for i in range(1, len(LEAKKEY)):
                    for case in (str, str.lower, str.upper, str.title):
                        echoed = case(LEAKKEY[:i] + ch + LEAKKEY[i:])
                        out = generate.safe_text("pp " + echoed + " qq", 300)
                        self.assertEqual(self.leaked_any_case(out), [], (repr(ch), i, case.__name__))
            # every separator between every pair of letters at once
            out = generate.safe_text("x " + " . ".join(LEAKKEY) + " y", 300)
            self.assertEqual(self.leaked(out), [])
            # a normal message still prints, and a plain echo still becomes <key>
            self.assertEqual(generate.safe_text("model busy, try again", 300), "model busy, try again")
            self.assertEqual(generate.safe_text("bad key " + LEAKKEY + " given", 300), "bad key <key> given")
        finally:
            generate._KEY = ""

    def test_key_split_by_separators_never_reaches_output_or_files(self):
        for ch in ("\u3000", "-", "\n", " "):
            for i in (1, 7, 13, len(LEAKKEY) - 1):
                for case in (str.lower, str.upper, str.title):
                    s = self.fake("leak_msg")
                    s.leak_key = case(LEAKKEY[:i] + ch + LEAKKEY[i:])
                    r = self.run_script(self.BASE, s, env_key=LEAKKEY)
                    self.assertEqual(r.returncode, 1, (repr(ch), i, r.stdout))
                    self.assertEqual(self.leaked_any_case(self.all_output(r)), [], (repr(ch), i, case.__name__))

    def test_all_server_text_goes_through_one_function(self):
        text = SCRIPT.read_text()
        self.assertNotIn("clean(", text)
        self.assertEqual(text.count("def safe_text"), 1)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class TestConvertNamesTheFormat(Base):
    def test_webp_and_jpeg_results_convert(self):
        for ext, extra in (("jpg", []), ("webp", ["-c:v", "libwebp"])):
            src = self.work / ("src." + ext)
            r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=16x16", "-frames:v", "1"]
                               + extra + [str(src)], capture_output=True)
            if r.returncode != 0:
                continue
            s = self.fake("jpeg")
            s.jpeg = src.read_bytes()
            out = self.run_script(self.BASE, s)
            self.assertEqual(out.returncode, 0, (ext, out.stderr, out.stdout))
            self.assertTrue((self.work / "img.png").read_bytes().startswith(b"\x89PNG"))
            (self.work / "img.png").unlink()

    def test_a_percent_sign_in_the_folder_name_is_not_a_file_pattern(self):
        folder = self.work / "w%03d"
        folder.mkdir()
        (folder / "prompt.txt").write_text("a red cube on a table\n", encoding="utf-8")
        src = self.work / "src.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=16x16", "-frames:v", "1", str(src)], check=True)
        s = self.fake("jpeg")
        s.jpeg = src.read_bytes()
        r = self.run_script(self.BASE, s, cwd=folder)
        self.assertEqual(r.returncode, 0, (r.stdout, r.stderr))
        data = (folder / "img.png").read_bytes()
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["img.png", "prompt.txt"], "no stray temp or numbered files")

    def test_ffmpeg_is_given_the_format_by_name(self):
        text = SCRIPT.read_text()
        self.assertIn('"-pattern_type", "none", "-f", "image2", "-c:v", codec, "-i", tmp', text)


class TestKeyHandling(Base):
    def test_no_key_exit_3_and_nothing_sent(self):
        s = self.fake("ok")
        r = self.run_script(self.BASE, s, env_key=None)
        self.assertEqual(r.returncode, 3)
        self.assertIn("IMAGE_FAILED: no Kie key", r.stdout)
        self.assertEqual(s.seen, [])

    def test_key_never_in_dry_run_output(self):
        r = self.run_script(self.BASE + ["--dry-run"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no request was sent", r.stdout)
        self.assertNotIn(KEY, self.all_output(r))

    def test_key_with_bad_characters_is_exit_2_and_not_echoed(self):
        r = self.run_script(self.BASE, env_key="bad key\twith space")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("bad key", r.stdout + r.stderr)

    def test_key_not_an_argument(self):
        r = self.run_script(self.BASE + ["--key", KEY])
        self.assertEqual(r.returncode, 2)

    def test_script_never_reads_a_key_file(self):
        text = SCRIPT.read_text()
        self.assertNotIn("expanduser", text)
        self.assertNotIn("dotenv", text)


class TestBadArguments(Base):
    def test_out_outside_work_folder(self):
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "../escape.png"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("inside the work folder", r.stderr)

    def test_out_through_symlink_outside(self):
        outside = Path(tempfile.mkdtemp(prefix="kie-outside-")).resolve()
        try:
            (self.work / "link").symlink_to(outside)
            r = self.run_script(["--prompt-file", "prompt.txt", "--out", "link/x.png"])
            self.assertEqual(r.returncode, 2)
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_prompt_file_outside_work_folder(self):
        r = self.run_script(["--prompt-file", "/etc/hosts", "--out", "img.png"])
        self.assertEqual(r.returncode, 2)

    def test_ref_outside_work_folder(self):
        outside = Path(tempfile.mkdtemp(prefix="kie-outside-")).resolve()
        try:
            (outside / "r.png").write_bytes(png_bytes())
            r = self.run_script(["--prompt-file", "prompt.txt", "--out", "img.png", "--aspect", "9:16",
                                 "--model", "gpt-image-2-image-to-image", "--resolution", "2K",
                                 "--ref", str(outside / "r.png")])
            self.assertEqual(r.returncode, 2)
            self.assertIn("inside the work folder", r.stderr)
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_base_url_must_be_loopback_http(self):
        for bad in ("https://evil.example", "http://evil.example:80", "http://127.0.0.1.evil.example:8080",
                    "http://user@127.0.0.1:80", "http://127.0.0.1"):
            r = subprocess.run([sys.executable, str(SCRIPT)] + self.BASE + ["--base-url", bad],
                               cwd=str(self.work), capture_output=True, text=True,
                               env=dict(os.environ, KIE_AI_API_KEY=KEY))
            self.assertEqual(r.returncode, 2, bad)
            self.assertNotIn(KEY, r.stdout + r.stderr)

    def test_prompt_on_command_line_not_accepted(self):
        r = self.run_script(["--prompt", "hello", "--out", "img.png"])
        self.assertEqual(r.returncode, 2)

    def test_ref_for_model_that_ignores_it(self):
        (self.work / "ref.png").write_bytes(png_bytes())
        r = self.run_script(self.BASE + ["--ref", "ref.png"])
        self.assertEqual(r.returncode, 2)
        self.assertIn("silently ignore", r.stderr)

    def test_ref_must_be_an_image(self):
        (self.work / "ref.png").write_text("not an image")
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "img.png", "--aspect", "9:16",
                             "--model", "gpt-image-2-image-to-image", "--resolution", "2K", "--ref", "ref.png"])
        self.assertEqual(r.returncode, 2)

    def test_i2i_needs_resolution(self):
        (self.work / "ref.png").write_bytes(png_bytes())
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "img.png", "--aspect", "9:16",
                             "--model", "gpt-image-2-image-to-image", "--ref", "ref.png"])
        self.assertEqual(r.returncode, 2)

    def test_empty_prompt_file(self):
        (self.work / "prompt.txt").write_text("  \n")
        r = self.run_script(self.BASE)
        self.assertEqual(r.returncode, 2)

    def test_out_must_be_png(self):
        r = self.run_script(["--prompt-file", "prompt.txt", "--out", "img.jpg"])
        self.assertEqual(r.returncode, 2)

    def test_bad_timeout_and_aspect(self):
        self.assertEqual(self.run_script(self.BASE + ["--timeout", "1"]).returncode, 2)
        self.assertEqual(self.run_script(["--prompt-file", "prompt.txt", "--out", "i.png", "--aspect", "wide"]).returncode, 2)


if __name__ == "__main__":
    unittest.main()
