# CFW Studio: design

**Part of this is built and part is planned.** This repo and its templates exist. The CFW-side tools that let a brand's bot save and lock in its own recipes are **planned, not built**. See [DECISIONS.md](DECISIONS.md) for why, and the last section there for what changed on 2026-11-22. See [MIGRATION.md](MIGRATION.md) for the path from today's system.

The names "templates", "recipe library" and "built-in recipes" are proposed and not yet confirmed by the owner.

## The idea

CFW Studio is a public place to learn from. What is in it are **templates**: recipes, blocks and effects. A template teaches. It never runs for a brand.

Each brand's own bot reads a template here, builds its own recipe, tries it, and saves it in that brand's **recipe library** inside CFW Social. That saved recipe is what runs. The bot edits it alone. When the user likes a version, the bot locks it in and the other drafts go. Each post is tagged with the brand recipe and the template it came from.

```text
   CFW STUDIO (GitHub, public)                CFW (one per brand)
 +------------------------------+       +---------------------------------+
 | TEMPLATES                    |       | RECIPE LIBRARY ('Your recipes') |
 | recipes, blocks, effects     |       | recipes this brand's bot made   |
 | vetted before merge          |       | versioned, private to the brand |
 | teach only, never run        |       | these are what run              |
 +---------------+--------------+       +----------------+----------------+
        ^        | bot reads                             ^
 issue  |        v                                       | bot saves, edits,
 report |  +------------------------------+              | locks in, removes
        +--| THE BRAND'S BOT              |--------------+
           | follows CFW's bot guide      |
           +------------------------------+
```

The bot follows CFW Social's bot guide. The Studio section of that guide is planned, not written yet.

CFW also keeps **built-in recipes**: the ones CFW makes. A bot may start from one, too.

## What is built and what is not

| Piece | State |
| --- | --- |
| This repo, the `effects/` library, scaffolds | Exists |
| Issue form and pull request template | Exists (see `.github/`) |
| Brand recipe library in CFW | Planned, not built |
| Tools to check, save, lock in and remove a recipe | Planned, not built |
| Tags on posts: brand recipe and template | Planned, not built |
| `block.yaml` and `recipe.yaml` format | Later. The `_template` folders show it. Real recipes are copied in whole, in today's file format, first. |

There is **no sync** from this repo into CFW. Merging here does not make anything live for any brand.

## The life of one brand recipe

```text
 1 BUILD        2 TRY            3 EDIT          4 LOCK IN        5 REUSE
 bot reads a    one-off run      bot changes     user says        automation
 template,      with the draft,  the recipe,     'I like it':     pins the
 saves draft    post goes to     saves drafts    v3 is locked,    locked
 v1             Reviews          v2, v3          v1 and v2 go     version

   v1 ---------> v1 run -------> v2, v3 -------> [v3 LOCKED] ---> v3, v3, v3
```

- A change never edits a saved version. It makes a new one.
- A draft and a locked version can both run. Automations use the locked one.
- A draft that made no post is deleted. A draft that made a post leaves the list but keeps a small record.

## Tagging

```text
 post in Reviews --> its order --> brand recipe name, version
                                        |
                                        +--> came from: template name and commit
                                        +--> uses: blocks and effects
```

CFW stores the "came from" and "uses" lines as the bot reports them. It does not check them against GitHub.

## Safety

With no approve tap, safety rests on four things.

1. **Vetting at the template door.** Whatever is merged here can end up running on a buyer's computer. The owner reads the scripts before merge, using the eight-point checklist in [CONTRIBUTING.md](../CONTRIBUTING.md). Only the owner merges.
2. **Brand-only scope.** No other brand can list, read, pin or claim a brand's recipe.
3. **Server checks on every save** (planned): the brand key, fingerprints computed by the server, size limits, and a refusal of anything that looks like a key.
4. **The user stays in the loop.** A recipe is locked only when the user says they like it.

Brand facts stay out of templates. Voice, colors and names live in Brand DNA and in the order inputs. A recipe holds the method, not the brand's data.

## File format

Recipes ship **whole first, in today's file format**. The `block.yaml` and `recipe.yaml` format below comes later. The `_template` folders show the later format as a preview. Real recipes are copied in whole, in today's file format, first.

## Building blocks (later format)

A block lives in `blocks/c-<name>/` and contains:

- `block.yaml` — identity, kind, variation, and declared inputs and outputs
- `SKILL.md` — the instructions an agent follows
- `scripts/` — supporting scripts the instructions call

### Proposed `block.yaml` fields

| Field | Role |
| --- | --- |
| `id` | Stable slug, for example `c-transcribe`. Blocks in `blocks/` use `c-*`. |
| `kind` | `component` or `step` for folders in `blocks/`. Effects use `kind: effect` and live under `effects/`. |
| `variation` | Light variation id (for example `default` or `karaoke-glow`). Not semver. A new variation is a sibling, not a replacement, until the old one is retired. |
| `label`, `summary` | Human-readable name and one-line description. |
| `inputs[]` | `id`, `type` (`text`, `json`, `image`, `video`, `audio`), `required`, `cardinality` (`one` or `many`), and a short description. |
| `outputs[]` | Same shape as inputs: what this block produces. |
| `needs` | Optional tools, OS, or providers the block requires. |

A **fingerprint** is a hash of the contract plus the instruction and script files. CFW computes it when a recipe is saved. It is not authored by hand.

## Effects (later format)

An effect lives in `effects/e-<name>/` and contains:

- `effect.yaml` — the manifest (same field shape as `block.yaml`, with `kind: effect`)
- `SKILL.md` — the instructions an agent follows to apply the effect
- `scripts/` — supporting scripts the instructions call
- a preview file (gif, video, still, or audio) so reviewers can judge the look or sound

Effects are blocks that recipes reference. They get their own folder so the library of looks and sounds is easy to browse and contribute to. Start from `effects/_template/`.

## Recipes (later format)

A recipe lives in `recipes/p-<name>/` and contains:

- `recipe.yaml` — identity, the ordered list of blocks, the input union, and the final output
- `SKILL.md` — the guiding document: when to use it, how the blocks fit, and any coordination the agent needs

### Proposed `recipe.yaml` fields

| Field | Role |
| --- | --- |
| `id` / `label` | Stable slug such as `p-reels-clipper`, plus a display name. |
| `blocks[]` | Ordered list of block or effect ids and variation ids. This is the Lego list. Effects are included here; there is no separate effects array. |
| `inputs` | Union of the required inputs of those blocks, plus any recipe-level optional settings. An agent can read this and know what to ask for. |
| `output` | The final deliverable: kind, aspect, cardinality (`one` or `many`), and a short description. |

## Example idea: p-reels-clipper

A clipper template could take one long source video and produce a variable number of 15–60 second vertical shorts. That output shape is not expressible in today's fixed `finalOutputs` list, so the new contract needs a `many` cardinality. Do not copy AGPL third-party clipper code; write CFW blocks from the ideas.

| Block | Role | Status |
| --- | --- | --- |
| `c-ingest-video` | Accept a long source video | Partial — today's reel inputs assume a short talking-head bed |
| `c-transcribe` | Words and timestamps | Reusable from today's transcribe pattern |
| `c-score-moments` | Score hook, engagement, value, and shareability; 3–9 word hook titles | **New block needed** |
| `c-cut-on-sentences` | Cut 15–60 second clips on sentence boundaries | **New block needed** |
| `c-reframe-9x16` | Vertical around faces, or full frame on a blurred bed when a tight crop would clip slides or people | **New block needed** |
| `c-captions` | Karaoke-style captions | Partial — today's captions are not yet a reusable style-pack block |
| `c-shorts-qa` | Duration, canvas, cover, captions QA | Reusable pattern for one reel, not yet for N clips |
| Variable output | A list of shorts, not one deliverable | **New contract needed** |

Proposed recipe inputs, as the union of those blocks: required `source_video`; optional `max_clips`, `mode` (`highlights`, `recap`, or `trailer`), and `caption_style`. Proposed output: many vertical videos, 1080×1920, 15–60 seconds each.

## Repo layout

```text
cfw-studio/
  README.md
  CONTRIBUTING.md
  AGENTS.md
  LICENSE
  docs/
    DESIGN.md
    DECISIONS.md
    MIGRATION.md
    REPORTING.md
  effects/
    README.md
    _template/
      effect.yaml
      SKILL.md
      scripts/
      PREVIEW.md
    e-*/                 # one folder per effect (kind: effect)
  blocks/
    README.md
    _template/
      block.yaml
      SKILL.md
      scripts/
    c-*/                 # one folder per building block
  recipes/
    README.md
    _template/
      recipe.yaml
      SKILL.md
    p-*/                 # one folder per recipe
  .github/               # issue form and pull request template
  docs/REPORTING.md      # how a bot files an issue
```

Proposed CI, once added, should validate input and output declarations and run or attach a sample (and, for effects, a preview). This repository does not yet include that workflow (no application code is being added with this design).

## Contribute

```text
 person or bot --> pull request --> owner vets (8 points) --> owner merges
                                                                  |
                                              brand bots read the template here
```

Merging puts a template in this repo and nothing more. Bots and agents open pull requests and issues only. See [CONTRIBUTING.md](../CONTRIBUTING.md) and [REPORTING.md](REPORTING.md).

## Open questions

- How should a variable list of outputs (N shorts) be declared in the recipe contract?
- What does each effect need on Windows, macOS and Linux? Not checked yet.
- Later format: a block fingerprint must cover the shared `effects/fx` package, and each `effect.yaml` should declare what the effect needs (numpy, pillow, OpenCV, mediapipe, onnxruntime today).
- Where do sample outputs live for review (PR attachments or a `samples/` folder)?
- Final names for "templates", "recipe library" and "built-in recipes".
