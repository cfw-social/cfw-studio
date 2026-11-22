"""Use fx from Python: per-frame API for custom pipelines."""
import numpy as np
import fx
from fx.compose import f32, u8
from fx.vio import read_frames, fit, Writer

pal = fx.load_palette("navy-amber")      # or a path / dict
seg = fx.Segmenter("ensemble")
frames = [fit(f, 1080, 1920) for f in read_frames("footage/clip.mp4", start=0, dur=3)]
masks = seg.sequence(frames)
w = Writer("out/api_demo.mp4", 1080, 1920, 30)
state = {}
for i, fr in enumerate(frames):
    F = f32(fr); M = seg.upscale(masks[i], fr)
    out = fx.apply_frame("scribble_outline", F, F, M, t=i / 30, dur=3.0, i=i, fps=30, palette=pal,
                         params={"color": "accent", "jitter": 6}, state=state)
    w.write(u8(out))
w.close()
