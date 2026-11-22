# Contributing to CFW Studio

Thank you for improving the templates. This repo holds **templates**: recipes, blocks and effects. A template teaches. A brand's own bot reads it, builds its own recipe, and saves that recipe in the brand's recipe library in CFW. A merge here does not publish anything into CFW and changes nothing for any brand.

**Only the owner merges.** People, bots and agents open pull requests and issues only.

## What to contribute

- An **effect** under `effects/e-<name>/` — a visual or audio treatment (transition, confetti, fireworks, caption style, overlay, sound effect, or music bed). An effect is a block of `kind: effect` that recipes reference by id. Include a preview of the look or sound.
- A **block** under `blocks/c-<name>/` — reusable instructions plus supporting scripts, with declared inputs and outputs.
- A **recipe** under `recipes/p-<name>/` — a guiding document that lists the blocks and effects it uses. If the recipe needs a block or effect that does not exist yet, include it in the same pull request.

A new variation of an existing block or effect is a sibling (a new `variation` id), not a silent rewrite of the old files if others still depend on them.

Start from `effects/_template/`, `blocks/_template/`, or `recipes/_template/`.

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

- The folder name matches the id (`e-*`, `c-*`, or `p-*`).
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
