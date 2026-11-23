"""Tests for e-camera-motion. They make a tiny clip with ffmpeg and need no account and no model.

    cd effects && pytest tests/test_camera_motion.py -q
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "e-camera-motion" / "scripts" / "camera_motion.py"
ZOOM = ["push-in", "focus", "pull-out", "ken-burns", "drift", "pan-left", "pan-right", "pan-up", "pan-down"]
WARP = ["tilt-back", "tilt-forward", "orbit", "sway"]
CARD = ["card-orbit", "card-swoop", "card-focus", "card-glide"]

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                reason="ffmpeg and ffprobe are not installed")


def run(work, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=str(work),
                          capture_output=True, text=True, timeout=120)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)["streams"]


@pytest.fixture(scope="module")
def work(tmp_path_factory):
    w = tmp_path_factory.mktemp("work")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x120:r=10:d=1.2",
                    "-f", "lavfi", "-i", "sine=d=1.2", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", str(w / "in.mp4")], check=True)
    return w


def test_list_names_every_motion(work):
    r = run(work, "--list")
    assert r.returncode == 0
    for name in ZOOM + WARP + CARD:
        if name != "focus":
            assert name in r.stdout


@pytest.mark.parametrize("motion", ZOOM + WARP)
def test_in_frame_motion_renders_same_size_with_audio(work, motion):
    r = run(work, "in.mp4", "--motion", motion, "--out", "out/%s.mp4" % motion)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().splitlines()[-1] == "OUTPUT_FILE: out/%s.mp4" % motion
    streams = probe(work / "out" / ("%s.mp4" % motion))
    video = [s for s in streams if s["codec_type"] == "video"][0]
    assert (video["codec_name"], video["width"], video["height"]) == ("h264", 160, 120)
    assert any(s["codec_type"] == "audio" and s["codec_name"] == "aac" for s in streams)


@pytest.mark.parametrize("motion", CARD)
def test_card_motion_renders_on_canvas(work, motion):
    r = run(work, "in.mp4", "--motion", motion, "--canvas", "320x240", "--background", "#102030",
            "--out", "out/%s.mp4" % motion)
    assert r.returncode == 0, r.stderr
    video = [s for s in probe(work / "out" / ("%s.mp4" % motion)) if s["codec_type"] == "video"][0]
    assert (video["width"], video["height"]) == (320, 240)


def test_transparent_card_to_mov(work):
    r = run(work, "in.mp4", "-m", "card-focus", "--canvas", "320x240", "--background", "transparent",
            "--out", "out/alpha.mov")
    assert r.returncode == 0, r.stderr
    assert probe(work / "out" / "alpha.mov")[0]["codec_name"] == "prores"


def test_transparent_card_needs_alpha_container(work):
    r = run(work, "in.mp4", "-m", "card-focus", "--background", "transparent", "--out", "out/x.mp4")
    assert r.returncode == 2
    assert not (work / "out" / "x.mp4").exists()


def test_print_filter_is_deterministic_and_renders_nothing(work):
    a = run(work, "in.mp4", "-m", "push-in", "--print-filter")
    b = run(work, "in.mp4", "-m", "push-in", "--print-filter")
    assert a.returncode == 0 and a.stdout == b.stdout
    assert a.stdout.startswith("scale=w='2*round(iw*(1+0.180000*")
    assert "crop=w=160:h=120:" in a.stdout
    assert run(work, "in.mp4", "-m", "pan-left", "--print-filter").stdout.count("(1-") >= 1
    w = run(work, "in.mp4", "-m", "tilt-back", "--print-filter").stdout
    assert w.startswith("perspective=x0='11.200000+") and w.rstrip().endswith("scale=160:120,setsar=1")
    c = run(work, "in.mp4", "-m", "card-swoop", "--canvas", "320x240", "--background", "0xAABBCC", "--print-filter").stdout
    assert "color=c=0xAABBCC:s=320x240:" in c and c.rstrip().endswith("[out]")


def test_amount_changes_the_filter(work):
    a = run(work, "in.mp4", "-m", "push-in", "--amount", "0.3", "--print-filter").stdout
    assert "(1+0.300000*" in a


@pytest.mark.parametrize("bad", [
    ["--motion", "spin"],
    ["--motion", "push-in;rm"],
    ["--amount", "0.9"],
    ["--amount", "-0.1"],
    ["--amount", "nan"],
    ["--amount", "inf"],
    ["--drift-x", "2"],
    ["--intensity", "2", "--motion", "orbit"],
    ["--crf", "52"],
    ["--crf", "-1"],
    ["--preset", "medium,drawtext=text=x"],
    ["--motion", "card-orbit", "--background", "red"],
    ["--motion", "card-orbit", "--background", "0x00FF00,drawtext=text=x"],
    ["--motion", "card-orbit", "--background", "#12345"],
    ["--motion", "card-orbit", "--background", "0x00FF00:s=1x1"],
    ["--motion", "card-orbit", "--background", "movie=/etc/hosts"],
    ["--motion", "card-orbit", "--canvas", "1920"],
    ["--motion", "card-orbit", "--canvas", "99999x100"],
    ["--motion", "card-orbit", "--canvas", "10x10"],
    ["--motion", "card-orbit", "--canvas", "320x240,x"],
    ["--motion", "card-orbit", "--card-scale", "2"],
    ["--motion", "card-orbit", "--card-scale", "0"],
    ["--motion", "card-orbit", "--corner-radius", "0.9"],
    ["--motion", "card-orbit", "--intensity", "9"],
    ["--motion", "push-in", "--canvas", "320x240"],
    ["--motion", "orbit", "--amount", "0.2"],
    ["--motion", "push-in", "--intensity", "1"],
])
def test_bad_option_exits_2_and_writes_nothing(work, bad):
    r = run(work, "in.mp4", *bad, "--out", "bad/out.mp4")
    assert r.returncode == 2, (bad, r.stdout, r.stderr)
    assert not (work / "bad").exists()


def test_out_is_required(work):
    assert run(work, "in.mp4", "-m", "push-in").returncode == 2


def test_out_outside_work_folder_refused(work, tmp_path):
    r = run(work, "in.mp4", "--out", "../escape.mp4")
    assert r.returncode == 2 and "inside the work folder" in r.stderr
    assert not (work.parent / "escape.mp4").exists()
    r = run(work, "in.mp4", "--out", str(tmp_path / "abs.mp4"))
    assert r.returncode == 2
    assert not (tmp_path / "abs.mp4").exists()


def test_out_through_symlink_refused(work, tmp_path):
    link = work / "linkdir"
    if not link.exists():
        link.symlink_to(tmp_path)
    r = run(work, "in.mp4", "--out", "linkdir/x.mp4")
    assert r.returncode == 2
    assert list(tmp_path.iterdir()) == []


def test_input_outside_work_folder_refused(work, tmp_path):
    shutil.copy(work / "in.mp4", tmp_path / "other.mp4")
    r = run(work, str(tmp_path / "other.mp4"), "--out", "x.mp4")
    assert r.returncode == 2 and "inside the work folder" in r.stderr


def test_out_may_not_be_the_input_or_a_wrong_extension(work):
    assert run(work, "in.mp4", "--out", "in.mp4").returncode == 2
    assert run(work, "in.mp4", "--out", "x.gif").returncode == 2
    assert run(work, "in.mp4", "--out", "out").returncode == 2


def test_missing_and_non_video_input(work):
    assert run(work, "nope.mp4", "--out", "x.mp4").returncode == 2
    (work / "text.mp4").write_text("not a video")
    r = run(work, "text.mp4", "--out", "x.mp4")
    assert r.returncode == 1
    assert not (work / "x.mp4").exists()


def test_filter_text_in_input_name_is_inert(work):
    name = "a,drawtext=text=x;b.mp4"
    shutil.copy(work / "in.mp4", work / name)
    r = run(work, name, "-m", "sway", "--out", "q.mp4")
    assert r.returncode == 0, r.stderr
    assert name not in run(work, name, "-m", "sway", "--print-filter").stdout


def test_script_has_no_shell_string_calls():
    text = SCRIPT.read_text()
    assert "shell=True" not in text
    assert "os.system" not in text


def test_exit_3_when_ffmpeg_is_missing(work, tmp_path):
    r = subprocess.run([sys.executable, str(SCRIPT), "in.mp4", "--motion", "push-in", "--out", "x.mp4"],
                       cwd=str(work), capture_output=True, text=True, env={"PATH": str(tmp_path)})
    assert r.returncode == 3, r.stderr
    assert "not installed" in r.stderr
    assert not (work / "x.mp4").exists()


def test_failed_render_leaves_no_partial_output(work):
    fake = work.parent / "fakebin"
    fake.mkdir(exist_ok=True)
    ff = fake / "ffmpeg"
    ff.write_text("#!/bin/sh\nfor last; do :; done\nprintf partial > \"$last\"\necho boom >&2\nexit 1\n")
    ff.chmod(0o755)
    real_probe = shutil.which("ffprobe")
    (fake / "ffprobe").symlink_to(real_probe) if not (fake / "ffprobe").exists() else None
    r = subprocess.run([sys.executable, str(SCRIPT), "in.mp4", "--motion", "sway", "--out", "partial.mp4"],
                       cwd=str(work), capture_output=True, text=True, env={"PATH": str(fake)})
    assert r.returncode == 1, r.stderr
    assert "boom" in r.stderr
    assert not (work / "partial.mp4").exists()


def test_existing_output_file_is_replaced(work):
    (work / "precious.mp4").write_text("old")
    r = run(work, "in.mp4", "--motion", "sway", "--out", "precious.mp4")
    assert r.returncode == 0, r.stderr
    assert (work / "precious.mp4").read_bytes()[:4] != b"old\n"[:4]
    assert [s for s in probe(work / "precious.mp4") if s["codec_type"] == "video"]
