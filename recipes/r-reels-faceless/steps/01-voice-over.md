# Generate the voice-over

Read `_shared.md` first (it also covers the setup). This step makes one continuous narration bed: no picture
and no captions. Before spending anything, check every requested option, the
required tools, that a local speech-to-text tool exists (step 2 needs it), the
brand data in `brief.json` and that the person has allowed a paid voice call.

Receive `inputs/script/` (`script.json` with `text`, or one `.md`/`.txt`) or the
explicit research path's `prior/approved_script.md`, optional `inputs/voice_id/`,
and `brief.json`. Read each with native UTF-8/JSON tools. Use the approved
script verbatim for meaning. For TTS-clean `work/vo-script.txt`, remove headings,
markup and stage directions and spell tricky tokens for speech without adding
claims; keep hook first and CTA last. Word count is a guide, about 80 to 230 words; the real limit is the
measured bed length below (30 seconds or more, up to 87.1 seconds), and a script that gives a shorter or longer
bed is revised, not delivered. Never fewer than 60 words. A missing/unsuitable script asks only for `script`; a missing or malformed
voice asks only for `voice_id`. Write `needs_input.json` and stop, without saves.

A typed voice wins; otherwise use `brand.elevenlabs.voiceId` from the brief. The template ships no voice
id. Accept only `[A-Za-z0-9_-]{8,64}`. The brief's ElevenLabs model and settings win when supplied;
otherwise the script's defaults apply (model `eleven_multilingual_v2`, format `mp3_44100_128`, the
provider's own voice settings). Use MP3 output for this version; another format is a named blocker. The
script text must be at most 10,000 characters (the script refuses more). A missing provider key is a
failure, never a question about the voice.

## Make the voice with voiceover.py

This step contacts one host, `api.elevenlabs.io`, and only to make the voice. Write the TTS-clean text to
`work/vo-script.txt`, then run the recipe's script. The brand's own key goes in only as the environment
variable `ELEVENLABS_API_KEY` of this one command, or as one line on standard input with `--key-stdin`.
Never an argument, never read from a file, never printed.

```text
python3 "$RECIPE_DIR/scripts/voiceover.py" --text-file work/vo-script.txt --voice-id <voice id> --out work/vo.mp3 [--model-id <id>] [--stability <0-1>] [--similarity-boost <0-1>] [--style <0-1>] [--speed <0.7-1.2>] [--use-speaker-boost]
```

The exact form. The key comes from the order's private input into one variable in your own process, never
echoed, never typed into command text, never written to a file, and it reaches only this one child process:

```python
import os, subprocess
args = ['python3', recipe_dir + '/scripts/voiceover.py', '--text-file', 'work/vo-script.txt',
        '--voice-id', voice_id, '--out', 'work/vo.mp3']
env = dict(os.environ, ELEVENLABS_API_KEY=brand_key)          # this one command only; not exported anywhere else
result = subprocess.run(args, env=env, capture_output=True, text=True, shell=False, timeout=700)
# or, with no environment variable at all: add '--key-stdin' to args and pass input=brand_key + '\n'
last_line = result.stdout.strip().splitlines()[-1]            # AUDIO_FILE: ... or AUDIO_FAILED: ...
```

In a shell the same rule reads `ELEVENLABS_API_KEY="$KEY" python3 ...` with `KEY` an unexported variable that was
set without echoing; prefer the argument-list form above.

The last line it prints is `AUDIO_FILE: work/vo.mp3` (exit 0) or `AUDIO_FAILED: <reason>` (exit 1, 2 or 3),
printed once. Exit 3 means no key was given and nothing was sent. The call is made once and never retried,
because a retry could be charged twice. Do not print the request, the key, the settings or raw provider
responses beyond that line. An existing `work/vo.mp3` may be reused only if your own note shows it was made
from this exact script, model and settings, and ffprobe confirms it decodes. Otherwise stop and ask the
person before paying for a second take; never synthesise twice silently. A successful reply is not proof of
good audio: the script checks the MP3 header, and you require ffprobe codec `mp3` and a clean decode.

## Trim, normalise once and wrap

Run these argument lists with the FFmpeg and ffprobe the bot resolved.
The relative paths are fixed names inside the run folder.
Create `work` and `saves` with native file operations. `bg` is the validated palette
`BG` and `bed_duration` is the finite ffprobe duration of `work/vo-normed.wav`.

```python
trim = ('silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.3,'
        'areverse,silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.3,'
        'areverse,loudnorm=I=-14:TP=-1.5:LRA=11')
args = ['-y', '-protocol_whitelist', 'file', '-i', 'work/vo.mp3', '-af', trim, '-ar', '48000', '-ac', '2', 'work/vo-normed.wav']
# Run ffmpeg(args), check success, then probe the WAV with JSON output.
args = ['-y', '-f', 'lavfi', '-protocol_whitelist', 'file', '-i', 'color=c=' + bg + ':s=1080x1920:r=30',
        '-protocol_whitelist', 'file', '-i', 'work/vo-normed.wav', '-t', str(bed_duration), '-map', '0:v', '-map', '1:a',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'fast', '-crf', '20',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-shortest',
        '-movflags', '+faststart', 'saves/voice_bed.mp4']
```

Save `saves/voice_bed.mp4`: 1080×1920/30fps H.264 yuv420p, AAC 48kHz stereo,
leading/trailing silence <=0.3s, integrated -14 LUFS ±1.5. Keep room inside the
30–90s final budget for a 0.4s cover and supplied outro duration or 2.5s generated
outro; a bed outside 30s through `90 - 0.4 - outro_seconds` asks for a revised script
and is not delivered (the spec's `vo_duration_window` enforces 30 to 87.1 s for the 2.5 s card; tighten the
maximum if a supplied outro is longer). Do not stretch speech or cut the voice to fit.

Record actual `bed_has_audio` and `bed_duration_window` checks. Probe dimensions, frame rate,
codecs/channels and loudness too. For the voice itself, run the mechanical checks the spec lists
under `steps.voicebed`, with `b-qa-gate`:

```text
python3 "$BLOCKS_DIR/b-qa-gate/check.py" --kind reel --spec "$RECIPE_DIR/acceptance.json" --step voicebed --input work/vo-normed.wav --out work/voicebed-scorecard.json
```

Exit 0 means the length (30 to 87.1 s), the loudness (-14 LUFS, 1.5 tolerance) and the speech level passed. Exit 1 means the
voice failed: report which row, and do not proceed.
