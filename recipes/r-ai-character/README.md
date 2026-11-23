# r-ai-character

Based on CFW Social's built-in AI character recipe.

## 1. What it makes

A character-consistent set of 3 to 6 still images, each exactly 1080x1920 (9:16 portrait), that tell a short visual story in story order. Scene 1 is the cover. It also saves a one-row contact sheet of all scenes. It does not make a video.

This is a template to learn from and adapt. The plan is that a brand's bot reads it, builds its own recipe, and saves that recipe in the brand's recipe library in CFW Social. Those CFW tools are planned, not built (see [../../docs/DESIGN.md](../../docs/DESIGN.md)). Today you can read the steps and follow them by hand or with your own agent.

## 2. What you need

| Tool | Version |
| --- | --- |
| Python 3 | 3.15.2 (the version the tests ran on; others untested) |
| ffmpeg and ffprobe | 8.1 (the version the tests ran on; others untested) |
| ImageMagick | 7.1.2-17, with the `convert` command (the version the tests ran on; others untested) |
| bash | 5.3.12 (the version the tests ran on; the contact-sheet test also runs `/bin/bash` and zsh when present) |

Provider account: **Kie** (kie.ai), with credits. The bot uses the brand's own Kie account and key, taken from the order. The key is put in the environment of the one generation command (or piped on standard input with `--key-stdin`). It is never typed into a command line, never written to a file and never printed. A vision-capable model must look at every image; there is no mechanical-only pass.

**Not proven with a real account.** Nothing here has run against live Kie. The tests use small local fake servers.

**People and likeness.** The optional `reference_image` is uploaded to Kie, and so is the generated character reference with every scene call. Kie's docs say uploaded files are deleted after 24 hours; Kie's own terms apply. Use only reference images the brand has the right to use, of a person who agreed. This template ships no reference image, no person's name and no id. This is a plain safety note, not legal advice.

## 3. Blocks it uses

| Block | Why | Path |
| --- | --- | --- |
| `b-kie-ai` | `scripts/generate.py` makes each image: uploads the reference, creates the task once, polls, downloads | `../../blocks/b-kie-ai/` |
| `b-qa-gate` | `check.py --kind image` runs the size, brightness and not-flat checks in `acceptance.json` and lists the look questions; `check.py --finalize` records the answers | `../../blocks/b-qa-gate/` |

The bot sets one environment variable before a step: `RECIPE_DIR` (this folder). Every step then sets `BLOCKS_DIR="$RECIPE_DIR/../../blocks"` once at its top. A step stops with one plain line if `RECIPE_DIR` is unset or a block is missing.

The generation command, run from the work folder (the prompt is a file the step wrote first):

```bash
KIE_AI_API_KEY="${ORDER_KEY:-}" python3 "$BLOCKS_DIR/b-kie-ai/scripts/generate.py" \
  --prompt-file work/prompt-1.txt --out work/raw-1.png --aspect 9:16 \
  --model gpt-image-2-image-to-image --resolution 2K --ref work/char-ref.jpg --timeout 240 --poll 5
```

`ORDER_KEY` is a shell variable your tool fills from the order. Do not echo it and do not turn on shell tracing.

## 4. The steps

```text
story + character text
        |
 01 lock + arc --> 02 reference --> 03 scenes, one at a time --> 04 quality gate
 (2 json files)    (char_ref.png)   (scene_1..N, scene_sheet)     (final.png, qa_report.json)
                                      each checked for drift       b-qa-gate, then looks
```

1. `steps/01-character-lock.md`: six-attribute audit (hard gate) and a story arc. Nothing is generated.
2. `steps/02-character-ref.md`: one full-body reference, audited against the lock.
3. `steps/03-scene-images.md`: one image-to-image call per scene, each anchored on the reference, with a drift check before the next scene.
4. `steps/04-qa-gate.md`: `b-qa-gate` on each scene, then the bot looks at each scene next to the reference, answers each look question, and records the answers with `--finalize`.

`steps/_shared.md` holds the rules every step shares.

## 5. Inputs and outputs

Inputs: `story_concept` and `character_description` (required); `character_type` (`human` or `plush`, default `human`), `num_scenes` (3 to 6, default 5) and `reference_image` (an existing picture of the character, uploaded to Kie) are optional.

Outputs (saves): `character_lock`, `story_arc`, `char_ref`, `ref_audit`, `scene_1`, `scene_sheet`, `scenes`, `final` (the cover), `qa_report`. `manifest.json` lists each save and its checks. `scripts/record.py` writes the two small work-folder records (`work/tasks.json`, `work/ref_audit.json`) from an argument list. `acceptance.json` holds the `b-qa-gate` checks (kinds `dims`, `luma_floor`, `not_flat` and `perceptual`).

## 6. Network use

At setup: none. At run time, only what `b-kie-ai` contacts, and the block's README is the source for this table. `b-qa-gate` makes no network call. The steps make none. The tests make none outside `127.0.0.1`.

| When | Host | What is sent |
| --- | --- | --- |
| Run | `api.kie.ai` | The create call and the status checks, with the key. |
| Run, only when a reference image is used (every scene, and step 2 when the brand supplies a picture) | `kieai.redpandaai.co` (Kie's documented upload host) | The reference image, with the key. Kie's docs say it is deleted after 24 hours. |
| Run | the https host Kie names in its reply for the result file | A plain download with no key header. The host is chosen by Kie, not fixed here. The key is never sent to it. |

## 7. Run the tests

From this folder. They need no real key and no paid call. A small fake Kie server runs on `127.0.0.1`.

```sh
python3 -I test/test_scene_sheet.py -v
python3 -I test/test_step_guards.py -v
python3 -I test/test_end_to_end.py -v
python3 -I test/test_record.py -v
```

`test_scene_sheet.py` runs the step 3 block that builds the contact sheet, for 3 to 6 scenes, and needs ImageMagick. `test_step_guards.py` checks that the steps stop with a plain line, before any paid call, when the reference, `generate.py` or ffmpeg is missing. `test_end_to_end.py` runs the real `b-kie-ai` generation script and the real `b-qa-gate` through the steps' own command lines, against local fake Kie servers, with a reference image drawn in the test (a plain shape, not a person). It checks that the key reaches no output file and no output stream. `test_record.py` tests `scripts/record.py`. They use only files in this repository. The blocks' own tests are in the blocks.

## 8. Sample

There is none. A sample needs a Kie account with credits: one reference image plus one image per scene, check the provider's current prices, and a reference picture the brand has the right to use. The template does not make paid calls for you, and it ships no picture of a person. Add a sample to `examples/` after a run you are allowed to publish.

## 9. Terms used by CFW Social

These belong to CFW Social's order format. Outside CFW Social you can ignore them.

- **`manifest.json`**: the order format listing inputs, steps, saves and checks.
- **Save**: a file a step writes to `saves/` under an id (`char_ref`, `scenes`).
- **Check ids** such as `six_attributes`, `arc_shape`, `ref_dims`, `not_black`, `ref_matches_lock`, `scene_dims`, `scenes_not_dark`, `no_diverged_scenes`, `vision_qa_pass`, `final_dims`: labels under which the order records a result. Each step file says what to check.
- **`canAsk` and `needs_input.json`**: how step 1 asks the brand for a missing input.
- **`kie`** in `providers`: the Kie account the brand supplies.

## 10. Limits and known gaps

- **Stills only.** An earlier method also animated each scene with an image-to-video model, joined clips with crossfades and added music. None of that is here. No animation, assembly or music step exists in this folder, none is tested, and the manifest does not list it. A video version would have to be written and tested.
- **Where it was run.** The tests ran on macOS (arm64) only, with the tool versions in section 2. No run on Windows or Linux, none on a bot app and none against a live Kie account is recorded. `manifest.json` names `macos` under `needs.os`; that is the original order setting, not a verified limit.
- **Two models only.** `z-image` (text to image, prompt of 1000 characters or fewer) and `gpt-image-2-image-to-image` are the models `b-kie-ai` lists as confirmed. Model names and prices are Kie's and change, so check the provider's current prices; if Kie changes its API the script fails with a plain message.
- **Cover only in `final`.** The manifest saves the cover and a contact sheet, not one output per scene in order. A bot that needs every scene as its own file must keep them itself from `work/`.
- **Drift check is by eye.** Whether a scene is the same character is a look question answered by a vision-capable model. `b-qa-gate` only measures size, brightness and flatness, and records the answers. A scorecard is a record, not proof that the bot looked.
- **Paid provider.** Every image is a paid call; a failed or drifted scene costs again when regenerated on purpose. The generation script never retries a create call by itself.
