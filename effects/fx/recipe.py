"""JSON recipe runner: cut segments from sources, frame them to the output size, chain effects per segment, add audio.

{
  "out": "reel.mp4", "size": [1080, 1920], "fps": 30,
  "palette": "palette.json" | {...},                    # optional; default navy-amber palette
  "seg": {"backend": "ensemble", "temporal_sigma": 1.2}, # optional
  "save_segments": "segments/",                       # optional: also write each segment (lets a later grid_collage reuse them)
  "segments": [
    {"src": "clip.mp4" | "frames_dir/", "src_fps": 30, "in": 2.0, "dur": 4.0, "speed": 1.0,
     "center": [0.5, 0.6], "zoom": 1.2 | [1.2, 1.35], "redact_src": [[x,y,w,h], ...],
     "mask_src": "clip_unredacted.mp4",               # optional: segment on this source (same timing) instead of src,
                                                      # e.g. when src is a privacy-blurred copy that confuses segmentation
     "flash_in": 0.1,
     "effects": [{"name": "spotlight", "start": 0.0, "end": null, "params": {...}}, ...]}
  ],
  "audio": {"music": "bed.mp3", "music_gain_db": -3, "voice": null,
            "sfx": [{"path": "hit.mp3", "at": 4.0, "gain_db": -10}],
            "sfx_each_segment": {"path": "whoosh.mp3", "offset": -0.08, "gain_db": -12}}
}
Effect times are relative to the segment start. Effects run in list order on each frame (later = on top).
"""
import json, os, time
import numpy as np
from .anim import Keyframes, lerp
from .compose import f32, u8
from .core import apply_frame
from .palette import load_palette
from .seg import Segmenter
from .vio import read_frames, fit, Writer, mux
from .audio import build_mix

def _load(r):
    if isinstance(r, str):
        base = os.path.dirname(os.path.abspath(r)); r = json.load(open(r)); r.setdefault("_base", base)
    return r

def _p(r, path):
    if path is None or os.path.isabs(path): return path
    return os.path.join(r.get("_base", os.getcwd()), path)

def run_recipe(recipe, out=None, only=None, stills=None, log=print):
    """only: list of segment indexes to render (for previews). stills: list of global times -> writes JPGs instead of video."""
    r = _load(recipe); out = out or _p(r, r["out"])
    W, H = r.get("size", [1080, 1920]); fps = r.get("fps", 30)
    pv = r.get("palette")
    if isinstance(pv, str) and os.path.exists(_p(r, pv)): pv = _p(r, pv)
    pal = load_palette(pv)
    seg = Segmenter(**r.get("seg", {}))
    t0 = time.time(); tmp = out + ".video.mp4"
    w = None if stills else Writer(tmp, W, H, fps)
    starts, T = [], 0.0
    for s in r["segments"]: starts.append(T); T += s["dur"]
    for si, s in enumerate(r["segments"]):
        if only is not None and si not in only: continue
        n = int(round(s["dur"] * fps))
        want = None
        if stills:
            want = {int(round((t - starts[si]) * fps)) for t in stills if starts[si] <= t < starts[si] + s["dur"]}
            if not want: continue
        z = s.get("zoom", 1.0); zk = Keyframes([(0, z[0]), (s["dur"], z[1])], "in_out_sine") if isinstance(z, list) else (lambda t, z=z: z)
        c = s.get("center", [0.5, 0.5]); ck = Keyframes([(0, tuple(c[0])), (s["dur"], tuple(c[1]))], "in_out_sine") if isinstance(c[0], list) else (lambda t, c=c: tuple(c))
        frames = []
        for i, f in enumerate(read_frames(_p(r, s["src"]), s.get("in", 0.0), s["dur"], fps, s.get("speed", 1.0), s.get("src_fps"))):
            if i >= n: break
            frames.append(fit(f, W, H, ck(i / fps), zk(i / fps), s.get("redact_src")))
        log(f"seg {si}: {len(frames)} frames; masks...")
        if s.get("mask_src"):
            mframes = []
            for i, f in enumerate(read_frames(_p(r, s["mask_src"]), s.get("in", 0.0), s["dur"], fps, s.get("speed", 1.0), s.get("src_fps"))):
                if i >= len(frames): break
                mframes.append(fit(f, W, H, ck(i / fps), zk(i / fps), s.get("redact_src")))
            while len(mframes) < len(frames): mframes.append(mframes[-1])
            masks = seg.sequence(mframes)
        else:
            masks = seg.sequence(frames)
        states = [dict() for _ in s.get("effects", [])]
        segw = None
        if r.get("save_segments") and not stills:
            sd = _p(r, r["save_segments"]); os.makedirs(sd, exist_ok=True); segw = Writer(os.path.join(sd, f"seg{si:02d}.mp4"), W, H, fps)
        for i, fr in enumerate(frames):
            if want is not None and i not in want: continue
            t = i / fps; F = f32(fr); out_f = F; M = None
            for e, stt in zip(s.get("effects", []), states):
                es, ee = e.get("start", 0.0), e.get("end") if e.get("end") is not None else s["dur"]
                if not (es <= t < ee): continue
                if M is None: M = seg.upscale(masks[i], fr)
                out_f = apply_frame(e["name"], out_f, F, M, t - es, ee - es, i - int(round(es * fps)), fps, pal, e.get("params"), stt)
            fl = s.get("flash_in", 0)
            if fl and t < fl: out_f = out_f + (1 - out_f) * (1 - t / fl) * 0.8
            if stills: 
                from PIL import Image
                p = f"{os.path.splitext(out)[0]}_still_{starts[si] + t:06.2f}.jpg"; Image.fromarray(u8(out_f)).save(p, quality=90); log("still", p)
            else:
                fu = u8(out_f); w.write(fu)
                if segw: segw.write(fu)
        if segw: segw.close()
        log(f"seg {si} done ({time.time()-t0:.0f}s)", flush=True) if log is print else log(f"seg {si} done")
    if stills: return None
    w.close()
    a = r.get("audio")
    if a and only is None:
        sfx = [dict(x, path=_p(r, x["path"])) for x in a.get("sfx", [])]
        if a.get("sfx_each_segment"):
            e = a["sfx_each_segment"]
            sfx += [dict(path=_p(r, e["path"]), at=max(0, st + e.get("offset", 0)), gain_db=e.get("gain_db", -12)) for st in starts[1:]]
        wav = build_mix(out + ".mix.wav", T, _p(r, a.get("music")), a.get("music_gain_db", -3), sfx=sfx, voice=_p(r, a.get("voice")))
        if wav: mux(tmp, wav, out); os.remove(tmp); os.remove(wav)
        else: os.replace(tmp, out)
    else: os.replace(tmp, out)
    log(f"wrote {out} ({T:.2f}s) in {time.time()-t0:.0f}s")
    return out
