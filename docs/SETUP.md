# Set up a machine for CFW Studio

This page is for a bot that has been told to get ready. It lists every tool the templates in this repo need, then three test pieces that prove the machine works. Everything here was run on macOS only. Windows and Linux were not run. Nothing in this repo installs a tool for you.

```text
install tools --> read the templates --> make 3 test pieces --> say "ready" (or say what failed)
```

## Tools

Run each check from the repository root unless it says "in the work folder". "Run with" means the version that was actually run. Other versions are untested unless the cell says "or newer".

**Needed by almost everything**

| Tool | What needs it | Check it is there | Version stated |
|---|---|---|---|
| Python 3 | the Python scripts of the blocks, recipes and effects | `python3 --version` | 3.10 or newer; run with 3.15 (but see the effects packages below: they need 3.10 to 3.14 today) |
| FFmpeg with ffprobe | `b-audio`, `b-hyperframes`, `b-kie-ai`, `b-qa-gate`, `b-reel-premium`, every recipe, every effect | `ffmpeg -version` and `ffprobe -version` | 6 or newer; run with 8.1 (`b-qa-gate` states 8.1 only) |

**Needed to turn pages into pictures or video**

| Tool | What needs it | Check it is there | Version stated |
|---|---|---|---|
| Node.js and npm | `b-hyperframes`, `b-broll-sync`, tests of `b-reel-premium` and `b-typing-ui`, `r-carousel`, `r-gfx-image`, every `r-reels-*` and `r-inspired-reel` | `node --version` and `npm --version` | Node 22 or newer; run with 25.9.0 |
| HyperFrames (npm `hyperframes`), GSAP (npm `gsap`) and a pinned headless Chrome | `b-hyperframes`, and through it every reel recipe and `b-reel-premium` | in the work folder: `ls hyperframes-runtime/.hf-trust.json` | `hyperframes` 0.7.5, `gsap` 3.14.2, Chrome headless shell 131.0.6778.85 |
| Playwright (npm) and its Chromium headless shell | `r-carousel`, `r-gfx-image` | in the work folder: `npm ls playwright` | exactly 1.64.1; Chromium revision 1248 |
| Fonts Oswald, Inter, JetBrains Mono | the card and caption pages of the reel recipes and `b-typing-ui` | `fc-list : family` and look for the three names (macOS: Font Book) | none stated |

`b-hyperframes` is the only place that installs the pinned renderer. It installs HyperFrames, fetches GSAP and downloads the headless Chrome (about 88 MB) into the work folder. Its install command, from its README, is `python3 blocks/b-hyperframes/scripts/hf_install.py` (once per work folder). It needs Node, npm and FFmpeg first. `r-carousel` installs the Playwright package into the work folder with `npm install --save-exact playwright@1.64.1`. Its browser, from `npx playwright install chromium-headless-shell`, goes into Playwright's own cache folder in the user's home, not the work folder.

If the fonts are missing, the templates fall back to a generic family and the letter shapes change; the reel recipes still render, and `r-carousel` fetches its fonts from the two Google font hosts. Installing a font is a change to the system, so ask the person first.

**Needed for speech to text**

| Tool | What needs it | Check it is there | Version stated |
|---|---|---|---|
| whisper.cpp (`whisper-cli`) and one ggml model file | `b-audio`, and through it `r-reels-faceless`, `r-reels-pip`, `r-reels-pip-heygen`, `r-reels-spotlight`, `r-reels-spotlight-heygen`, `r-inspired-reel` | `whisper-cli --help` and `test -f <model file>` | you name the version; run with 1.8.4 and `ggml-base.en.bin` |

`b-audio` supports only whisper.cpp. Its `--model` file must be in the work folder or in a folder you name with `--allow-model-dir DIR`, so a model already on the machine can be read where it is. A model download needs the person's yes (`--allow-download`, with `--model-sha256`).

**Packages a script imports that are not in the standard library**

| Package | What needs it | Check it is there | Version stated |
|---|---|---|---|
| `numpy`, `pillow`, `opencv-contrib-python-headless`, `mediapipe`, `onnxruntime` (Python) | the `fx` package in `effects/` (all `e-*` effects except `e-camera-motion`) | `python3 -c "import numpy, PIL, cv2, mediapipe, onnxruntime"`, run inside the virtual environment below | numpy 1.26+, pillow 10+, opencv 4.9+, mediapipe 0.10+, onnxruntime 1.17+ |
| ImageMagick (`convert`) and bash | `r-ai-character`, `r-ai-image`, `r-gfx-image` (shell steps) | `convert -version` and `bash --version` | ImageMagick 7.1.2; bash 5.3.12 (r-gfx-image: 3.2.57) |

The effects packages need Python 3.10 to 3.14 today. On Python 3.15, `pip install -r effects/requirements.txt` failed in a real run: no `onnxruntime` build exists for it yet. Make the effects virtual environment with a 3.10 to 3.14 Python, switch it on, then install: `python3.14 -m venv effects/.venv`, `. effects/.venv/bin/activate`, `pip install -r effects/requirements.txt`. Run the import check and every `python -m fx` command in that switched-on environment, not in a fresh shell. The other scripts ran with 3.15. Every other script in `blocks/` and `recipes/` uses the standard library only.

**Provider accounts (optional and paid)**

| Account | What needs it | Check it is there | Version stated |
|---|---|---|---|
| Kie | `b-kie-ai`, `r-ai-image`, `r-ai-character` | none: the brand's key comes with the order | |
| HeyGen | `b-heygen`, `r-inspired-reel`, `r-reels-pip-heygen`, `r-reels-spotlight-heygen` | none: same | HeyGen API v3 |
| ElevenLabs | `r-reels-faceless` (the voice step) | none: same | |

Use a provider only with the person's yes. The key is given per order. Never read a key from disk. None is needed for the first run below.

Install what is missing with your system's package manager. Ask the person only when an install needs an admin password. Do not install anything this page does not list without asking.

## First run: three test pieces

Make these with no paid provider call. Read each template's `SKILL.md` and `steps/` first. How long it takes: one real run on one Mac took about 70 minutes (carousel about 15, reel about 45, effects reel about 10) and about 1 GB of disk. It is one run, on macOS.

1. **A carousel**, from `recipes/r-carousel`. Follow its steps with a made-up topic and the sample brand in its `steps/_shared.md`. Passed means every slide has a final `b-qa-gate` scorecard with verdict PASS and the recipe's report is written. The render reaches only the two Google font hosts; offline it falls back to system fonts.
2. **A reel**, from `recipes/r-reels-faceless`. Passed means `b-qa-gate` gives a final verdict of PASS on `saves/final_video.mp4`, and the voice bed passes its `voicebed` check first (30 to 87.1 seconds, loudness -14 LUFS within 1.5, speech level).
   - `r-reels-faceless` and `r-reels-spotlight` list `research` and `script` steps that run on CFW Social's server. For a first run, write the script yourself.
   - Step 1 makes the voice with ElevenLabs, which is paid. Do not make that call. The template has no free voice path, and it does not describe a stand-in. What the later steps need is a file saved as `work/vo.mp3` that ffprobe reads as MP3 and that passes the `voicebed` check. Step 2 also needs real speech: at least 20 timed words from whisper.cpp, and the script should be 60 words or more.
   - So a bot may make that file with a local text-to-speech tool, or record one. A tone is not enough, because speech to text finds no words in it. Say in your report that the voice is a stand-in.
3. **A short reel of 10 to 15 seconds with several effects**, from `effects/`. Chain three or four segments in one `python -m fx recipe` file (format and example: `effects/README.md` and `effects/examples/recipe_example.json`). Use several of: `e-backdrop-words`, `e-spotlight`, `e-glass-card`, `e-digital-zoom`, `e-moody-grade`, `e-label`, `e-stamp`, `e-vertigo`. Add `e-camera-motion` if you want a move that needs only FFmpeg. The committed clip `effects/examples/assets/synthetic_mannequin.mp4` is 4 seconds, so use segments of 4 seconds or less. The segmentation model files are not in the repo (`scripts/download_models.sh` fetches them), so use the chroma backend, as `effects/README.md` shows for this clip. Passed means `python -m fx` exits 0, the file is 10 to 15 seconds long, and `pytest` in `effects/` passes. Then write a small spec of `dims`, `fps` and `duration_window` rows (see `blocks/b-qa-gate/README.md`) and run `b-qa-gate` on the result.

When the three are done, tell the person what you made, what passed and what failed.

## If a template is wrong

Follow [REPORTING.md](REPORTING.md) and open an issue with the "Template problem" form.
