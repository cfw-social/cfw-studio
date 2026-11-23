# r-inspired-reel

Make an original reel inspired by the **format** of a reference reel.

## 1. What it makes

One 9:16 reel, 1080x1920 at 30 fps, 15 to 90 seconds long, about as long as the reference (within 15 percent). A narrated avatar speaks a brand-new script, with word-timed captions, a light colour grade and sound effects. The script, topic, voice and face are the brand's own. Only the reference's **shape** is taken: its length, words per minute, cut rate, how it opens, and the order and share of its beats (for example "hook, 3 points, call to action"). The reel uses none of the reference's footage and none of its audio, and no run of six or more words in a row comes from the reference (see "What the overlap check catches").

This is a template to learn from and adapt. The plan is that a brand's bot reads it, builds its own recipe, and saves that recipe in the brand's recipe library in CFW Social. Those CFW tools are planned, not built (see [../../docs/DESIGN.md](../../docs/DESIGN.md)). Today you can read the steps and follow them by hand or with your own agent.

## 2. What you need

| Tool | Version |
| --- | --- |
| Python 3 | 3.10 or newer; run with 3.15 only |
| ffmpeg and ffprobe | 6 or newer (tests ran on 8.1) |
| whisper.cpp (`whisper-cli`) and a model file | You name the version and the model; `b-audio` records both. Not run for real by this recipe (see section 10) |
| Node.js and npm | Node 22 or newer, only for the caption render (`b-hyperframes`, which also downloads a pinned headless browser). Observed: 25.9.0 |
| bash | the steps use bash; zsh also works |

Provider account: **HeyGen**, with API credits. The bot uses the brand's own HeyGen key, taken from the order. The key is set in the environment of the one narration command (`HEYGEN_API_KEY="${ORDER_KEY:-}" python3 ...`) or piped on standard input with `--key-stdin`. It is never typed into a command line, never written to a file and never printed. The template ships no key, no avatar id, no voice id, no person's name and no reference media. The avatar id and voice id come from the order.

**Not proven with a real account.** Nothing here has run against live HeyGen. The tests use a small local fake server.

**Using a reference.** Use a reference you have the right to study. The recipe takes its shape, not its content: it keeps only numbers and labels, writes every word fresh, and refuses a script that shares six or more words in a row with the reference's transcript. The avatar and voice must be the brand's own, of a person who agreed to be shown and heard. The person supplies the reference as a file; the template has no downloader. This is a plain safety note, not legal advice.

The script text is uploaded to HeyGen to be spoken; its retention policy was not checked. The reference file and its transcript are never uploaded anywhere. Speech to text runs on your own machine.

## 3. Blocks it uses

| Block | Why | Path |
| --- | --- | --- |
| `b-audio` | Speech to text with word timings: the reference's words (for the format and the overlap check; no hint) and the new narration's words (for captions; with a short word-list hint from the script) | `../../blocks/b-audio/` |
| `b-heygen` | Avatar narration of the new script through the HeyGen API | `../../blocks/b-heygen/` |
| `b-reel-premium` | Checks the caption plan, builds the caption page, then grades the footage, lays the captions over it and mixes sound effects (`check_plan.py`, `build_comp.py`, `mux.py --captions-mov`, `qa.py`) | `../../blocks/b-reel-premium/` |
| `b-hyperframes` | The one safe way to render the caption page, as a transparent `.mov` (`hf_render.py --format mov --quiet`): pinned install, local-only check, render. The footage never goes through it | `../../blocks/b-hyperframes/` |
| `b-qa-gate` | `check.py --kind reel` runs the measured checks in `acceptance.json` and lists the look questions; `--finalize` records the answers | `../../blocks/b-qa-gate/` |

`b-typing-ui` (hook and typing cards) is not used in this edition. The bot sets two environment variables before a step: `RECIPE_DIR` (this folder) and `BLOCKS_DIR` (`../../blocks` from here). Steps stop with one plain line if either is missing.

The recipe's own small scripts, in `scripts/`, do the work no block owns. Each does one job, writes only inside the work folder (a path outside it or a link on the way is refused; every file is written to an exclusive temporary file and renamed), checks numbers before they reach ffmpeg, opens media with `-protocol_whitelist file`, and prints one plain line on failure, never a traceback:

| Script | Job |
| --- | --- |
| `prepare_reference.py` | Check the supplied reference file and extract its audio to `ref/audio.wav` |
| `measure_format.py` | Measure length, cuts, pace and beats; write `format.json` |
| `check_script_shape.py` | Check the new script has the reference's beats and word count; write the narration text and a short word-list hint for `b-audio` |
| `check_overlap.py` | Refuse a script that shares six or more words in a row with the reference |
| `cleanup_reference.py` | Scan for reference words, delete the reference transcript and audio (only the folder named `ref`), then check they are gone |
| `verify_final.py` | The last gate: save the final reel and report only for a finalized PASS scorecard that matches the file |
| `make_base_reel.py` | Fit the avatar video to 1080x1920, 30 fps, -14 LUFS |
| `make_spec.py` | Write a version of `acceptance.json` for this order, with the duration window set from `format.json` |
| `format_schema.py`, `rs_common.py` | The fixed-keys check for `format.json`, and shared path, write and word helpers |

## 4. The steps

```text
reference file (supplied by the person)
   |
 1 prepare_reference --> ref/audio.wav --> b-audio --> ref/words.json          (these stay in ref/)
   |
 2 measure_format ------> format.json   (numbers and labels only)
   |
 3 bot writes script.txt from format.json + brand topic + brand voice
   |   check_script_shape  (beats, word count)      check_overlap  (no run of 6 words)
   |
 4 cleanup_reference: delete ref/, check it is gone     <- the reference transcript ends here
   |
 5 narration text --> b-heygen --> avatar.mp4 --> make_base_reel --> base_reel.mp4
   |
 6 b-audio (new words) --> caption plan --> check_plan --> build_comp --> b-hyperframes render (captions.mov)
   |                                                                              |
   |        mux: grade the footage, lay the captions over it, add sound effects <-+
   |
 7 b-qa-gate (--kind reel) --> answer the looks --> --finalize --> cleanup check again --> final.mp4
```

The seven logical steps live in three step files, because each CFW order step gets its own work folder holding only declared saves, and the reference transcript must not be a save. Everything that touches the transcript therefore runs in one step file and ends with its deletion:

1. `steps/01-reference-to-script.md`: logical steps 1 to 4. Ends with `format.json`, `script.md`, `overlap.json`, `cleanup.json`.
2. `steps/02-narration.md`: logical step 5. Ends with `base_reel.mp4`.
3. `steps/03-captions-and-checks.md`: logical steps 6 and 7. Ends with `final.mp4` and `qa_report.json`.

The deletion happens as early as it can (step 4, once the script has passed both checks) and is checked again at the end (step 7). The final overlap check against the spoken words is not needed: HeyGen speaks the script text, and the script already passed.

`steps/_shared.md` holds the rules every step shares: the work folder layout, the key rule, and the rules that make this a format-only recipe.

### How the overlap check works

`check_overlap.py` normalises both texts (NFKD, accents and combining marks dropped, every Unicode format character such as zero-width spaces, joiners and soft hyphens dropped, lower case, punctuation and apostrophes ignored), then looks for any run of six or more consecutive words that appears in both. A hyphen inside a word is tried both as a split and as a join, so it cannot hide a run. Punctuation between letters (`peo.ple`) is tried as a split and as a join too. A script is refused, with the character named, if it holds any letter that is not plain a to z once accents are removed (Cyrillic or Greek look-alikes, small capitals, dotless i, and the like) or odd control characters, because such letters would slip past a word comparison. Five shared words pass; six fail. It prints where the run starts in the new script and how long it is, never the words. Its optional `--out` file holds numbers only. Both sides may be plain text or a words list. An empty script, or an empty reference transcript, is refused (exit 2) so a failed transcription is not taken for a pass. The bot is told not to open the reference transcript at all, so it writes from the format alone.

**What it catches:** a run of six or more words in a row, in any case, with any punctuation, accents, invisible characters or hyphenation.
**What it cannot do:** judge likeness or meaning. It compares words. It does not catch a number written as digits where the reference wrote it in words (or the reverse). A reworded copy of the reference's ideas, a translation, or a script that keeps the reference's jokes and order in new words passes it. A person should read the script, and the `nothing_of_the_reference` look is the second line.

### How the clean-up works

`cleanup_reference.py` runs in step 4 of the first step file. It accepts only the folder named `ref`, directly inside the work folder (`.`, the work folder itself and any other name are refused). Before deleting, it remembers every six-word run in the reference transcript and meta file (in memory only), and looks for them in every file that decodes as text, whatever its extension, in every folder outside `inputs/` and `ref/` (a file over 2 MB is not skipped quietly: see below). That scan runs in step 1, before the transcript is deleted; later steps can only check that the reference folder is gone, not that no reference words got into a file. The scan reads UTF-8 text. It cannot read UTF-16 or compressed files, so any file outside `inputs/` that it could not read as text (UTF-16, compressed, binary, over 2 MB, or a link) and that is not a wav, mp4, mov, png or jpg file with the right header makes the scan FAIL with that file named. The one exception is a file with a valid media header (see the limits). Keep the speech model outside the work folder for the same reason. Then it deletes the whole `ref/` folder (a link inside it is removed, never followed; a `ref/` that is itself a link is refused). Then it checks that `ref/` is gone or empty, and that `format.json` still passes its fixed-keys check. It exits 1 if a run of reference words turned up in a file (it names the file, not the words), if anything was left behind, or if `format.json` holds anything other than numbers and labels. `--check-only` repeats the checks without deleting; step 7 runs it again at the end. The reference video the person supplied stays in `inputs/`: it is theirs, and this recipe never changes it, moves it, or uses it after step 2.

## 5. Inputs and outputs

Inputs (see `manifest.json`):

| Input | Required | Meaning |
| --- | --- | --- |
| `reference_reel` | yes | One video file, 15 to 90 s, with sound, that the person has the right to study |
| `topic` | yes | What the new reel is about, in the brand's own subject |
| `avatar_id`, `voice_id` | yes | The brand's own HeyGen avatar and voice ids. The template ships none |
| `cta` | no | The closing line |

The brief supplies the brand's voice and palette. The bot sets `WHISPER_VERSION`, `WHISPER_MODEL` (and optionally `WHISPER_BIN`, `WHISPER_MODEL_DIR`) for `b-audio`, and may set `BG` (a six-digit hex colour, default `#14181F`) for the avatar's solid background. There is no green screen and no keying.

Outputs (saves): `format`, `script`, `overlap`, `cleanup`, `base_reel`, `final`, `qa_report`. The reference transcript and audio are not saves and do not survive step 1.

### What `format.json` holds

Numbers and labels only: `duration_s`, `width`, `height`, `orientation`, `fps`, `speech_span_s`, `first_word_at_s`, `word_count`, `wpm`, `speech_share`, `cut_count`, `cuts_per_10s`, `mean_shot_s`, `scene_threshold`, `cut_times_s`, `hook` (`type` of `question`, `claim`, `stat` or `story`; `type_source`; `seconds`), `beats` (a `label` of `hook`, `point_N` or `cta`, with `start_s`, `end_s`, `share` of the speaking time, `words`) and `structure` such as `hook, 3 points, cta`. Every key and label is on a fixed list and matched in full; every number has an exact type (whole numbers are not booleans) and is rounded to two decimals; the cut times are rounded to one decimal, must be increasing, inside the clip, and at most 10 per second of length. That leaves less room, not none (see the limits). Anything else is refused when it is written, read, and cleaned up.

## 6. Network use

At setup, only what the blocks contact. This table is taken from the block READMEs; check them for the current detail.

| When | Host | What is sent |
| --- | --- | --- |
| Setup, caption render only (`b-hyperframes` `hf_install.py`) | `registry.npmjs.org` | Package downloads for the pinned HyperFrames and its dependencies. No install script runs |
| Setup, by default (`hf_install.py`, skipped with `--skip-browser`) | `storage.googleapis.com` | Download of the pinned headless Chrome shell, about 88 MB, into the work folder's cache |
| Setup (`b-hyperframes` `fetch_gsap.py`) | `registry.npmjs.org` | Download of the pinned animation library; no redirect followed |
| Setup, only if the person says yes (`b-audio --allow-download`) | `huggingface.co` (and `hf.co` redirects) | A download of the speech model file; nothing sent |
| Run | `api.heygen.com` | The create and status calls, with the key, the avatar id, the voice id and the narration text |
| Run | the https host HeyGen names in its reply (`video_url`) | A plain download of the narration video, with no key header. The host is chosen by HeyGen, not fixed here |

The recipe's own scripts, `b-reel-premium`, `b-qa-gate`, `b-audio` (by default) and the caption render (pinned browser, local-only page) make no network call that `b-hyperframes` observed. The reference file and its transcript are never sent anywhere. The tests make no call outside `127.0.0.1`.

## 7. Run the tests

From the repository root. They need no real key and no paid call. A small fake HeyGen server runs on `127.0.0.1`, and a fake speech tool stands in for whisper.cpp.

```sh
python3 -I -m unittest discover -s recipes/r-inspired-reel/test -v
```

`test_scripts.py` covers the overlap check (six words refused, five accepted, case and punctuation ignored, empty input refused), that `format.json` holds no sentence from a known transcript, the format measurement on small ffmpeg-made clips with known cuts, the clean-up (removal, a file left behind, a leaked run, links), and path safety for every script (a path outside the work folder, a planted link). `test_end_to_end.py` runs the steps' own bash blocks with the real `b-audio` (fake speech tool), the real `b-heygen` against the fake server, the real `b-reel-premium` (`check_plan.py`, `mux.py` laying a transparent stand-in caption video, `qa.py`) and the real `b-qa-gate` on a small stand-in reel with this recipe's `acceptance.json`, and checks that the key reaches no output file and no output stream. Tests that need ffmpeg are skipped, by name, when it is missing. The blocks' own tests are in the blocks.

## 8. Sample

There is none. A sample needs a HeyGen account with credits, a reference file the brand has the right to use, and an avatar and voice of a person who agreed. The template ships none of these. Add a sample to `examples/` after a run you are allowed to publish.

## 9. Terms used by CFW Social

These belong to CFW Social's order format. Outside CFW Social you can ignore them.

- **`manifest.json`**: the order format listing inputs, steps, saves and checks.
- **Save**: a file a step writes to `saves/` under an id (`format`, `final`).
- **Check ids** such as `words_found`, `script_shape`, `no_shared_run`, `reference_deleted`, `plan_valid`, `looks_answered`: labels under which the order records a result. Each step file says what to check.
- **`canAsk` and `needs_input.json`**: how a step asks for a missing input.
- **`heygen`** in `providers`: the HeyGen account the brand supplies.

## 10. Limits and known gaps

- **Not proven with a real HeyGen account.** The narration step ran only against a local fake server. HeyGen's resolution and aspect-ratio options are as `b-heygen` documents them; whether `1080p` at `9:16` gives exactly 1080x1920 is not confirmed, and `make_base_reel.py` scales and pads to fit.
- **What was run end to end, once.** On macOS, in a scratch folder, following the step files in order, with stand-ins: a generated reference clip with hard cuts and macOS `say` speech; the real `b-audio` with whisper.cpp 1.8.4 and `ggml-base.en.bin` on the reference and on the new narration; the paid HeyGen call replaced by a generated test-pattern clip with `say` speech (so the avatar look could not be answered yes); then the real `hf_install.py` (with its browser download), `fetch_gsap.py`, `build_comp.py`, `hf_render.py --format mov --quiet`, `mux.py --captions-mov`, `qa.py`, `b-qa-gate` and `--finalize`, and the clean-up checks. The recorded files are not in this repository. Not run: a real HeyGen account, a real reference reel, a real avatar, Windows, Linux.
- **A hint must be a word list.** Tried on the real model, a `--hint-file` made of the whole script stopped whisper.cpp after four words. A short list of the script's longer words worked, and `check_script_shape.py --hint-out` writes that. The hint biases the tool and does not guarantee spelling: "ripe" was still heard as "right".
- **The format read is a first guess.** Beats come from sentence ends and pauses of 0.8 s or more; the first sentence is the hook, the last is the call to action, and the sentences between are grouped into points. The hook type comes from simple rules (a question mark, a number, an opening "I" or "my"). These were tried on made-up transcripts only. A reference that does not follow a hook, points and close structure gets a rough read. `--hook-type` lets the person say what the hook is.
- **Cuts do not carry over.** The measured cut rate only paces captions and sounds; the narration is one continuous avatar shot. This edition does not cut between visuals. A hook card from `b-typing-ui` or cutaways from `b-broll-sync` could be added and would need their own steps and tests.
- **The reference file stays.** The person's file remains in `inputs/`. Delete it yourself if you do not want it kept.
- **The six-word check can be beaten by typing tricks.** It still passes a space typed inside a word (`peo ple`) and digits typed in place of letters (`m0st pe0ple`).
- **The step-1 scan does not read inside a file with a valid media header.** A wav, mp4, mov, png or jpg is accepted by its header, so text hidden after such a header is not seen.
- **A check cannot judge likeness or meaning.** The overlap check compares words only. It finds shared words, not shared ideas, and it does not catch a number written as digits instead of words. Whether the new reel is original in substance is a look question (`nothing_of_the_reference`) that the bot must answer by looking, and a person should still read the script.
- **A scorecard is a record, not proof.** `b-qa-gate` writes down what the bot says it checked and looked at. Someone who edits a scorecard by hand can make it pass. `verify_final.py` re-hashes the final file and rejects a changed file or a missing row, but it cannot tell an honest scorecard from a forged one.
- **`format.json` is numbers and labels, not proof.** It holds only numbers and labels, with exact types, short rounded values and a cut-time list limited to ten a second. Even so, numbers can still carry a short hidden message if someone sets out to do that. The file is not proof that nothing was taken from the reference.
- **The clean-up scan sees UTF-8 text only.** See "How the clean-up works": an unreadable file outside `inputs/` fails the scan instead of passing, but the scan compares words, so a reference sentence turned into pictures or audio would not be found.
- **Narration length can miss.** A voice slower or faster than the reference makes a reel longer or shorter. The gate fails outside plus or minus 15 percent. The fix is a new narration at a different `--speed`, which is a new paid render.
- **macOS only; the steps are bash.** The steps are written as bash commands and were run on macOS only; Windows is not covered by these steps. The commands of step 3 were also pasted into zsh 5.9 and ran as written. The recipe scripts use no shell and no OS-specific call, but no run on Windows or Linux is recorded. Not recorded as run on any bot app either. `manifest.json` names `macos` under `needs.os`, the order setting carried over. Nothing here was run on Windows or Linux.
- **Captions** use the generic sans-serif font unless the brand supplies a font file; a supplied font is third-party and its licence must be named. Latin script only.
- **One speaker, one language.** The word reader and the caption block are built for one speaker in English or another Latin-script language.
