# r-reels-spotlight-heygen

A template that teaches. Your bot reads it, understands the method, and builds its own version
for your brand. Nothing here runs for a brand by itself. Based on CFW Social's built-in script-driven spotlight reel recipe.

**It is [`r-reels-spotlight`](../r-reels-spotlight/) with one difference:** the talking-head video is not
supplied by the person. It is generated first, with [`b-heygen`](../../blocks/b-heygen/), from a script
text, an avatar id and a voice id (step 00). Then steps 01 to 07 follow, unchanged. Read that recipe's
README for everything else; this one says what is new.

## 1. What it makes

One full-frame vertical reel (1080×1920, 30 fps, H.264 + AAC, 20 to 65 seconds) in which the brand's
HeyGen avatar reads your script. The avatar's voice is a single unbroken audio bed. Word-synced kinetic
captions, sound effects and a colour grade ride over the whole reel. Motion-graphics takeovers (and
optional b-roll cutaways you place) cover the picture at planned beats. A money-shot cover frame sits at
frame 0, and a branded end card closes the reel. It also writes the cover image and post text per platform.

```text
audio:    ████████████████████████████████████████████  the avatar's voice, never cut
video:    [avatar][== GRAPHICS / B-ROLL ==][avatar][== GRAPHICS ==][avatar + END CARD]
captions: ▁▂▃ word-synced captions over everything ▃▂▁
frame 0:  money-shot cover (0.4 s freeze), then the full reel
```

**What leaves your machine.** Step 00 uploads the script text, the avatar id and the voice id to HeyGen
and downloads the finished video. Nothing else is sent: steps 01 to 07 run locally, as in the base recipe.
**One paid render per run.** A rerun resumes the render from its record instead of paying twice (section 5).
**Not proven with a real account:** `b-heygen` was only run against a local fake server (section 10).

## 2. What you need

Everything in the base recipe's table, plus:

| Need | Version | Used for |
|---|---|---|
| Python | 3.10 or newer; standard library only | `b-heygen` and the recipe's scripts |
| Everything in [`r-reels-spotlight`'s section 2](../r-reels-spotlight/README.md) | as listed there: `ffmpeg` 6+, Node.js 22+, `hyperframes` 0.7.5, `gsap` 3.14.2, Chrome headless shell 131.0.6778.85 (pinned and fetched by `b-hyperframes`), whisper.cpp with a ggml model file, fonts Oswald, Inter and JetBrains Mono | steps 01 to 07 |
| A HeyGen account with API access | HeyGen API v3 (what `b-heygen` calls) | step 00. **The brand's own key**, a private input of the order, used for that one command |
| A HeyGen avatar id and voice id | none shipped | step 00. **The brand's own, of a person who agreed** to be used this way |

This template ships no avatar id, no voice id, no key and no person's name.

## 3. Blocks it uses

Blocks live in `../../blocks/`. This recipe reaches them only by that relative path.

| Block | Why | Path |
|---|---|---|
| `b-heygen` | Step 00: makes the avatar video from the script, avatar id and voice id | `../../blocks/b-heygen/` |
| `b-audio` | Speech to text with word timings (step 02); HeyGen does not give word times | `../../blocks/b-audio/` |
| `b-hyperframes` | The one place that installs, checks and renders (pinned renderer, pinned GSAP, local-only check) | `../../blocks/b-hyperframes/` |
| `b-reel-premium` | Plan check, transparent caption render, grade and sound effects under the voice; holds the eight sound effects | `../../blocks/b-reel-premium/` |
| `b-qa-gate` | The mechanical checks and the looks the bot answers, run over `acceptance.json` | `../../blocks/b-qa-gate/` |
| `b-broll-sync` | Checks the bot's scene plan and lays out the beat list (only when b-roll is supplied) | `../../blocks/b-broll-sync/` |
| `b-typing-ui` | The typed-prompt takeover scene (only for a `tk-typing-ui` takeover) | `../../blocks/b-typing-ui/` |

## 4. The steps

```text
 script + avatar id + voice id ─> 00 generate ─> 01 prepare ─> 02 transcribe ─> 03 plan edit ──┬─> 05 render ─> 06 assemble ─> 07 final
   (HeyGen key, one command)       b-heygen      voice_track     b-audio         edit_plan     │    ... as in r-reels-spotlight ...
                                   (paid, once)                                                │
   broll (0..n) ───────────────────────────────────────────────────────────────> 04 plan b-roll ┘
```

Step 00 is new. Step 01 reads `prior/talking_head.mp4` instead of an input video. Steps 02 to 07 are the
same files as in `r-reels-spotlight`, and the scripts and templates are the same files byte for byte (a
test fails if they drift). In step 02 the script is known, so `b-audio` gets a short hint (the brand name
and the names and unusual words in the script) and the recognised words are checked against the script.

Step 00 in detail:

- It checks the inputs before anything is sent or paid (`scripts/heygen_inputs.py`). A missing or invalid
  script, avatar id or voice id is a question for the person: `needs_input.json` is written and the step stops.
- It calls `b-heygen/scripts/render.py` with `--aspect-ratio 9:16`, `--resolution 1080p` and
  `--background "#0F172A"`. The aspect ratio and the resolution come from the block's fixed lists. The
  background is a plain dark navy, not keyed out: step 01 scales the picture to fill the frame, so the
  avatar plays full-frame on that colour. If HeyGen refuses 1080p for the plan or avatar type, the step
  stops and says so; it does not pick another size.
- It takes the key from a private input into an unexported shell variable without echoing it, and passes it
  only as a per-command prefix on the render command (or on standard input). It is never typed into command
  text, never written to a file.
- It copies the render record to `saves/avatar_render.json` as soon as the render command returns, whether
  it worked or not, and restores it before a rerun, so a runner that discards `work/` cannot cause a second
  paid render.
- After the render, it checks the download (`scripts/check_avatar.py`: decodable, has audio, portrait,
  20 to 60 s) and saves it as `talking_head`. A wrong-length video at this point is a failure with the
  record saved, not a question.

## 5. Inputs and outputs

| Input | Required | Notes |
|---|---|---|
| `script` | yes | the narration, one `inputs/script/script.txt` or `script.md`, plain prose, 50 to 150 words (150 words a minute is 20 to 60 s, the window the video is checked against), at most 5000 characters. **It is uploaded to HeyGen.** |
| `avatar_id` | yes | the brand's HeyGen avatar id, `inputs/avatar_id/avatar_id.txt` (or `brief.json` `brand.heygen.avatarId`). Supplied by the person; never invented |
| `voice_id` | yes | the brand's HeyGen voice id, `inputs/voice_id/voice_id.txt` (or `brand.heygen.voiceId`). Supplied by the person |
| HeyGen key | yes | the brand's own key, a private input of the order: taken into an unexported shell variable without echo, then passed only as a per-command prefix on the one `render.py` command (or on standard input with `--key-stdin`). Never typed into command text, never in a file, a log or a reply |
| `broll` | no | any number of clips; when none, step 04 is skipped |
| `cta` | no | end-card copy as `{"text","brandName","handle"}` or typed text |
| `brief.json` | yes | intent, target platforms, brand (name, palette, optional `cta` and `handle`) and `options` |
| a whisper.cpp model file | yes | part of the bot's own setup (`STT_MODEL`, with `STT_VERSION`), not of the order; a download only if the person says yes |

Outputs: `final_video.mp4`, `cover.png`, `captions.json`. There is also `work/avatar.mp4` and its record
`work/avatar.mp4.render.json` (`video_id` and `status`, no key), copied to `saves/avatar_render.json`. **A rerun of step 00 with the same `--out`
resumes that render instead of submitting a new one.** Delete the record only if you want a new, separately
paid render. If the record exists but cannot be read, the script stops and sends nothing.

**Use only an avatar and a voice that are the brand's own, of a person who agreed to be used this way.**

## 6. Network use

Everything in the base recipe's section 6 (setup downloads by `b-hyperframes` and, if you say yes, `b-audio`;
run time none), plus step 00:

| When | Host | What |
|---|---|---|
| Step 00, create and poll | `api.heygen.com` | the key (in the `X-Api-Key` header only), the avatar id, the voice id and **the script text** |
| Step 00, download | the host in HeyGen's `video_url` reply: HeyGen's own file host, not named by the block; https is required, no redirect is followed, the size is capped | nothing but the request. The key is not sent |

`b-heygen` follows no redirect on any request, sends the key only to the API host, and scrubs the key from
any text the server sends back. The finished video is then processed locally. At run time no other script
opens a connection. No script reads a key from a file or writes outside the work folder.

## 7. How to run the tests

```bash
cd recipes/r-reels-spotlight-heygen
for t in test/test_*.py; do python3 -I "$t" || break; done
```

They need `ffmpeg` and `ffprobe` and the blocks beside the recipe (the repository layout). No network, no
HeyGen account, no real key, no private file. `test_heygen.py` runs step 00's own command line (read from
the step file) against a local fake server on 127.0.0.1, and checks the request, the resume without a second
submit, the failed render, the missing key (exit 3, nothing sent), the key on standard input, and that the key
is in no output and no file. `test_variant.py` fails if a shared script, template or step differs from
`../r-reels-spotlight/`, and runs the real `b-qa-gate` on the spec. The rest are the base recipe's tests. They
do not render a reel and do not call HeyGen.

## 8. Sample

None. A sample needs a paid HeyGen render with the brand's own avatar and voice, which this repository does
not do. The base recipe was run end to end once on stand-in media (see its README). This recipe was not run
end to end, and step 00 has never been run against HeyGen.

## 9. Terms used by CFW Social

You can ignore these outside CFW Social.

- **Order**: one request to make something, with its inputs and a brief.
- **Step work folder**: the folder one step runs in (`inputs/`, `prior/`, `saves/`, `work/`, `brief.json`).
- **Saves / prior**: what a step writes (`saves/`) and what the next step reads (`prior/`).
- **Runner**: whatever runs the steps and their checks.
- **`canAsk`**: an input a step may ask the owner for by writing `needs_input.json`.
- **`manifest.json`, `acceptance.json`**: CFW Social's order format: the inputs, steps and checks. Kept as it is.
- **`order-brand-v2`** (a manifest feature name): a flag in CFW Social's order format for how the brand reaches the recipe.
- **Reviews**: where a finished reel lands for the owner to look at.

## 10. Limits and known gaps

- **A scorecard is a record, not proof;** someone who edits it by hand can make it pass. The delivery check
  refuses a card whose verdict alone was changed, and the video reaches `saves/` only after that check passes.
- **Not proven with a real account.** `b-heygen` and step 00 were only run against a local fake server built
  from HeyGen's public v3 pages as the block read them. Nobody has run this recipe against HeyGen. The
  first paid render needs a person to look at it. Check `background` and `voice_settings` against the live
  page first, as the block's README says.
- **Paid and uploaded.** One paid render per run, and the script text is sent to HeyGen. A new script means
  a new paid render. A length problem found after the download (outside 20 to 60 s) is a failure, and a different script is a new paid render that only the person decides.
- **Resolution.** Higher resolutions may depend on the provider plan. If HeyGen refuses `1080p`, the recipe
  does not fall back to another size.
- **Background.** A plain navy background is asked for, not keyed out. How cleanly the avatar sits on it
  depends on the avatar. Nothing here removes or replaces it.
- **Hint file.** The hint for `b-audio` is short (brand name, names and unusual words). A hint holding the whole
  script made whisper.cpp repeat its last sentence in a test of the base recipe, so it is never sent. That
  test used a synthetic voice, not a HeyGen avatar.
- **Operating system and what was run.** The manifest value says where the steps are expected to work; it is
  not a record of testing. The shared steps were run on macOS in the base recipe; this variant has not been
  run start to finish, and its first step has run only against a local fake server.
- **Everything else** is the base recipe's: stand-in media in its run, no Windows or Linux run, Latin script
  only, the transparent caption render about 160 MB while it exists.
- **Planned, not built:** the CFW Social tools that let a brand's bot save, try and lock in its own version
  of this recipe. Until then this template only teaches.
