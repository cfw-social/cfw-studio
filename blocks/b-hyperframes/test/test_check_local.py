"""Tests for scripts/check_local.py. No network, no renderer, no private files."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_local.py"
FAKE_GSAP = b"/* stand-in for the pinned library, not GSAP */\nwindow.gsap = {};\n"

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
@font-face { font-family: "Oswald"; src: local("Oswald"); }
body { font-family: "Oswald", sans-serif; background: url(bg.png); }
.x { fill: url(#grad); }
</style></head><body>
<div id="root" data-composition-id="t" data-start="0" data-duration="1" data-width="360" data-height="640">
<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>
<img src="bg.png" alt=""><img src="data:image/png;base64,AAAA" alt="">
<script src="gsap.min.js"></script>
<script>window.__timelines = {}; var tl = gsap.timeline({paused:true}); window.__timelines["t"] = tl;</script>
</div></body></html>
"""


class CheckLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(os.path.realpath(self.tmp.name))
        self.comp = self.work / "comp"
        self.comp.mkdir()
        (self.comp / "bg.png").write_bytes(b"\x89PNG")
        (self.comp / "gsap.min.js").write_bytes(FAKE_GSAP)
        self.pins = self.work / "pins.json"
        self.pins.write_text(json.dumps({"gsap": {"file_sha256": hashlib.sha256(FAKE_GSAP).hexdigest()}}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, page=None, comp="comp"):
        if page is not None:
            (self.comp / "index.html").write_text(page, encoding="utf-8")
        done = subprocess.run([sys.executable, str(SCRIPT), "--comp", comp, "--work", str(self.work),
                               "--pins", str(self.pins)], capture_output=True, text=True, cwd=self.work)
        return done.returncode, done.stdout + done.stderr

    def refused(self, page, needle):
        code, text = self.run_check(page)
        self.assertEqual(code, 1, text)
        self.assertIn(needle, text)

    def test_good_page_passes(self):
        code, text = self.run_check(PAGE)
        self.assertEqual(code, 0, text)
        self.assertIn("LOCAL_ONLY: PASS", text)

    def test_remote_and_script_patterns_are_refused(self):
        cases = {
            "http image": ('<img src="http://example.com/a.png">', "address"),
            "https link": ('<link rel="stylesheet" href="https://example.com/a.css">', "address"),
            "protocol relative": ('<img src="//example.com/a.png">', "address"),
            "css url": ("<style>.a{background:url(https://example.com/a.png)}</style>", "address"),
            "css import": ('<style>@import url("//example.com/a.css");</style>', "address"),
            "css import local missing": ('<style>@import "nope.css";</style>', "does not exist"),
            "font via url": ("<style>@font-face{font-family:F;src:url(https://e.com/f.woff2);}</style>", "address"),
            "svg data uri": ('<img src="data:image/svg+xml;utf8,<svg/>">', "data:"),
            "html data uri": ('<iframe src="data:text/html,hi"></iframe>', "data:"),
            "javascript url": ('<a href="javascript:alert(1)">x</a>', "script address"),
            "iframe": ('<iframe src="a.html"></iframe>', "embedding"),
            "object": ('<object data="a.swf"></object>', "embedding"),
            "base": ('<base href="a/">', "embedding"),
            "meta refresh": ('<meta http-equiv="refresh" content="0">', "meta"),
            "preconnect": ('<link rel="preconnect" href="x.html">', "connection hint"),
            "fetch": ("<script>fetch('a.json')</script>", "fetch("),
            "xhr": ("<script>new XMLHttpRequest()</script>", "XMLHttpRequest"),
            "websocket": ("<script>new WebSocket('x')</script>", "WebSocket"),
            "event source": ("<script>new EventSource('x')</script>", "EventSource"),
            "beacon": ("<script>navigator.sendBeacon('x')</script>", "sendBeacon"),
            "dynamic import": ("<script>import('./a.js')</script>", "import("),
            "module import": ("<script type=module>\nimport x from './a.js'\n</script>", "module import"),
            "eval": ("<script>eval('1')</script>", "eval("),
            "function ctor": ("<script>new Function('1')()</script>", "Function"),
            "computed global": ("<script>window['fe'+'tch']('x')</script>", "computed access"),
            "innerHTML": ("<script>d.innerHTML = '<b>' + t</script>", "markup built"),
            "set src": ("<script>img.setAttribute('src', a)</script>", "link attribute"),
            "assign src": ("<script>img.src = a;</script>", "link property"),
            "new Image": ("<script>new Image()</script>", "Image"),
            "create script": ("<script>document.createElement('script')</script>", "loadable element"),
            "location": ("<script>location.href = 'a.html'</script>", "navigation"),
            "window.open": ("<script>window.open('a.html')</script>", "navigation"),
            "string address": ("<script>var a = '//host/x';</script>", "protocol-relative"),
        }
        for name, (snippet, needle) in cases.items():
            with self.subTest(name):
                self.refused(PAGE.replace("</body>", snippet + "</body>"), needle)

    def test_innerhtml_empty_string_is_allowed(self):
        code, text = self.run_check(PAGE.replace("</body>", "<script>el.innerHTML = '';</script></body>"))
        self.assertEqual(code, 0, text)

    def test_undeclared_font_is_refused(self):
        page = PAGE.replace('@font-face { font-family: "Oswald"; src: local("Oswald"); }', "")
        self.refused(page, "no @font-face")

    def test_font_through_a_variable_is_followed(self):
        page = PAGE.replace("<style>", "<style>:root{--f:'Inter',sans-serif} .y{font-family:var(--f)}")
        self.refused(page, "'inter'")
        declared = page.replace("<style>", '<style>@font-face{font-family:"Inter";src:local("Inter");}')
        code, text = self.run_check(declared)
        self.assertEqual(code, 0, text)

    def test_shorthand_font_is_checked(self):
        self.refused(PAGE.replace("<style>", "<style>.z{font: 700 40px/1.1 Anton, sans-serif}"), "'anton'")

    def test_unresolvable_variable_font_is_refused(self):
        self.refused(PAGE.replace("<style>", "<style>.y{font-family:var(--missing)}"), "cannot be resolved")

    def test_paths_must_stay_inside_the_work_folder(self):
        outside = self.work.parent / "outside-file.png"
        outside.write_bytes(b"x")
        try:
            self.refused(PAGE.replace('src="bg.png"', 'src="../../outside-file.png"'), "leaves the work folder")
        finally:
            outside.unlink()
        self.refused(PAGE.replace('src="bg.png"', 'src="/etc/hosts"'), "relative local path")
        self.refused(PAGE.replace('src="bg.png"', 'src="file:///etc/hosts"'), "outside the work folder")
        self.refused(PAGE.replace('src="bg.png"', 'src="a\\\\b.png"'), "backslash")
        self.refused(PAGE.replace('src="bg.png"', 'src="missing.png"'), "does not exist")
        self.refused(PAGE.replace('src="bg.png"', 'src="{{VIDEO}}"'), "cannot be checked")

    def test_file_in_work_folder_outside_comp_is_allowed_and_scanned(self):
        (self.work / "shared.css").write_text("body{margin:0}")
        code, text = self.run_check(PAGE.replace("<style>", '<link rel="stylesheet" href="../shared.css"><style>'))
        self.assertEqual(code, 0, text)
        (self.work / "shared.css").write_text("body{background:url(http://example.com/x.png)}")
        code, text = self.run_check()
        self.assertEqual(code, 1, text)
        self.assertIn("shared.css", text)

    def test_symlinks_are_refused(self):
        (self.work / "real.png").write_bytes(b"x")
        os.symlink(self.work / "real.png", self.comp / "link.png")
        self.refused(PAGE.replace('src="bg.png"', 'src="link.png"'), "symbolic link")

    def test_pinned_library_is_trusted_only_by_checksum(self):
        code, text = self.run_check(PAGE)
        self.assertEqual(code, 0, text)
        (self.comp / "gsap.min.js").write_bytes(FAKE_GSAP + b"fetch('x');\n")
        code, text = self.run_check()
        self.assertEqual(code, 1, text)
        self.assertIn("fetch(", text)

    def test_other_local_script_files_are_scanned(self):
        (self.comp / "extra.js").write_text("var u = 'https://example.com';")
        code, text = self.run_check(PAGE.replace("<script src=\"gsap.min.js\">", '<script src="extra.js"></script><script src="gsap.min.js">'))
        self.assertEqual(code, 1, text)
        self.assertIn("extra.js", text)

    def test_sub_composition_files_are_scanned(self):
        (self.comp / "compositions").mkdir()
        (self.comp / "compositions" / "a.html").write_text("<template><img src='https://example.com/a.png'></template>")
        code, text = self.run_check(PAGE)
        self.assertEqual(code, 1, text)
        self.assertIn("compositions/a.html", text)

    def test_usage_errors(self):
        code, _ = self.run_check(PAGE, comp="../elsewhere")
        self.assertEqual(code, 2)
        code, _ = self.run_check(comp="does-not-exist")
        self.assertEqual(code, 2)
        done = subprocess.run([sys.executable, str(SCRIPT), "--bogus"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)

    def test_script_free_disguised_addresses_are_refused(self):
        cases = {
            "css escapes in url": "<style>.a{background:\\75rl(ht\\74p://127.0.0.1:1/x)}</style>",
            "image-set": '<style>.a{background-image:image-set("ht\\74p://127.0.0.1:1/x" 1x)}</style>',
            "entity in imagesrcset": '<link rel=preload as=image imagesrcset="&#104;ttp://127.0.0.1:1/x">',
            "entity in src": '<img src="&#104;ttp://127.0.0.1:1/x">',
            "named entity colon": '<img src="http&colon;//127.0.0.1:1/x">',
            "escaped import": '<style>@import "ht\\74p://127.0.0.1:1/x.css";</style>',
            "escape in src descriptor": '<style>@font-face{font-family:Q;src:url(\\68 ttp://127.0.0.1:1/f.woff2);}</style>',
            "srcdoc": '<div srcdoc="<b>x</b>"></div>',
            "plain srcset": '<img srcset="http://127.0.0.1:1/a.png 1x">',
        }
        for name, snippet in cases.items():
            with self.subTest(name):
                code, text = self.run_check(PAGE.replace("</body>", snippet + "</body>"))
                self.assertEqual(code, 1, text)

    def test_known_limits_hand_written_scripts_pass(self):
        """KNOWN LIMITS. These three pages with script still pass the check. They are recorded
        here so nobody believes the check stops a hostile page. If one starts failing, update the README."""
        cases = {
            "aliased fetch": "<script>var f=self.fetch; f('ht'+'tp://127.0.0.1:1/x');</script>",
            "computed property": "<script>var im=document.getElementsByTagName('img')[0]; im['sr'+'c']='ht'+'tp://127.0.0.1:1/x';</script>",
            "attribute name in a variable": "<script>var a='sr'+'c'; document.getElementsByTagName('img')[0].setAttribute(a,'ht'+'tp://127.0.0.1:1/x');</script>",
        }
        for name, snippet in cases.items():
            with self.subTest(name):
                code, text = self.run_check(PAGE.replace("</body>", snippet + "</body>"))
                self.assertEqual(code, 0, text)

    def test_shipped_example_passes(self):
        example = Path(__file__).resolve().parent.parent / "examples" / "minimal" / "index.html"
        code, text = self.run_check(example.read_text(encoding="utf-8"))
        self.assertEqual(code, 0, text)

    def test_missing_index_is_a_problem(self):
        (self.comp / "index.html").unlink() if (self.comp / "index.html").exists() else None
        code, text = self.run_check()
        self.assertEqual(code, 1, text)
        self.assertIn("no index.html", text)


if __name__ == "__main__":
    unittest.main()
