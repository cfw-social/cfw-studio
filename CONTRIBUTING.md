# Contributing to CFW Studio

Thank you for improving the templates. This repo holds **templates**: recipes, blocks and effects. A template teaches. A brand's own bot reads it, builds its own recipe, and saves that recipe in the brand's recipe library in CFW. A merge here does not publish anything into CFW and changes nothing for any brand.

**Only the owner merges.** People, bots and agents open pull requests and issues only.

## What to contribute

The repo holds eight building blocks under `blocks/` and the effects under `effects/`. Recipe templates under `recipes/` are added separately. A recipe refers to a block by the relative path `../../blocks/b-<name>/`.

- An **effect** under `effects/e-<name>/` — a visual or audio treatment (transition, confetti, fireworks, caption style, overlay, sound effect, or music bed). An effect is a block of `kind: effect` that recipes reference by id. Include a preview of the look or sound.
- A **block** under `blocks/b-<name>/` — reusable instructions plus supporting scripts, with declared inputs and outputs.
- A **recipe** under `recipes/r-<name>/` — a guiding document that lists the blocks and effects it uses. If the recipe needs a block or effect that does not exist yet, include it in the same pull request.

**Names**

```text
r-   a recipe template     recipes/r-<name>/
b-   a building block      blocks/b-<name>/
e-   an effect             effects/e-<name>/
```

A folder name starts with its letter, and the folder name is the template's id.

A new variation of an existing block or effect is a sibling (a new `variation` id), not a silent rewrite of the old files if others still depend on them.

Start from `effects/_template/`, `blocks/_template/`, or `recipes/_template/`.

## Improve first

Make what is here better before you add something new.

- Before you add a new folder, try to make an existing block, recipe or effect do the job. A pull request that adds a new folder must say which existing one you tried, and why it could not be extended.
- A new block is accepted only when at least two recipes call its code. Code that only one recipe needs stays as a script inside that recipe.
- A new recipe is built from the existing blocks. If it needs new shared code, that goes in first, as a block change in its own pull request.
- A new effect must say why it is not an option or a preset of an existing effect.
- Every fix adds a test that would have caught the problem.
- Problems come first. If a `template-problem` issue is open against a block, recipe or effect, fix it before you add something new in the same area.

```text
 Things get better                           Something new is asked for
 ----------------                            --------------------------
 a bot uses a template                       someone asks for a new folder
        |                                             |
        v                                             v
 it hits a problem, or has to                the "improve first" questions:
 change something                            what existing one was tried?
        |                                    why can it not be extended?
        v                                             |
 an issue names the folder                            v
        |                                    accepted only if they are
        v                                    answered
 the fix lands with a test
        |
        v
 the folder's "Proof" table grows
```

Each block README has a "Proof" table. It says how far the block has been tested and run. Keep it true when you change the block. The check `tests/test_repo_rules.py` (below) looks for the table.

Run the check from the repository root:

```text
python3 tests/test_repo_rules.py
```

## Vetting checklist

Whatever is merged here can end up running on a buyer's computer. The owner checks every pull request against these eight points before merging. A pull request that fails any point is not merged.

1. Every script file is read in full.
2. No network call that the template does not declare.
3. Nothing reads keys, env files or another brand's folders.
4. Nothing writes outside the order's work folder.
5. Order text and brand text are never placed into a shell command.
6. Tool and package versions are pinned.
7. A sample run is attached.
8. No secrets, no private paths, no brand facts.

The pull request template lists the same eight points as tick boxes. Tick only what is true. Ticking a box does not replace the owner's read.

## Also check before you open a pull request

- The folder name matches the id (`r-*`, `b-*`, or `e-*`).
- `SKILL.md` is enough for an agent to follow without private local paths or credentials.
- Supporting scripts live in `scripts/` and are self-contained.
- Effect pull requests include a preview (see `effects/_template/PREVIEW.md`).
- Recipes ship whole first, in today's file format. Do not convert a recipe to `recipe.yaml` or `block.yaml` yet.

## Review and merge

The owner reads the scripts and the sample run, not only the file list. Merging puts the template in this repo. It does not sync into CFW.

## Bots

Bots may open pull requests when they find a reusable piece or build a better template. Follow the same checklist, attach a sample run, and never put brand facts, order text or keys in a pull request. A bot never merges.

If a template fails or is wrong, file an issue. Read [docs/REPORTING.md](docs/REPORTING.md) first.

## License

By opening a pull request you agree that your contribution is under the MIT License in [LICENSE](LICENSE). This applies to everything in the repository, including `effects/`.
