# Scripts

One file, `camera_motion.py`. It builds an ffmpeg filter and runs ffmpeg and ffprobe with argument lists. It has no other dependency and reads and writes only inside the work folder.

```bash
python3 camera_motion.py INPUT --motion NAME --out OUTPUT [options]
python3 camera_motion.py --list
```

`SKILL.md` has the motion table. `../README.md` has the full interface, limits and the test command. Keep credentials, private footage and downloaded model files out of this folder.
