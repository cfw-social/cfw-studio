# CFW Studio

The open, community-built library of **effects**, **building blocks**, and **recipes** that any AI agent can learn from and run to produce content.

Think of it as a box of Lego. An **effect** is a brick with a look or a sound: a transition, confetti, fireworks, a caption style, an overlay, a sound effect, or a music bed. A **building block** is a reusable piece of work, such as transcribing a video or cutting on sentence boundaries. A **recipe** is the instruction sheet that snaps those pieces together and says what goes in and what comes out. Agents can follow a recipe as written, or snap existing pieces into a new one.

## Who it's for

- **Creators and brands** who want consistent short-form video, carousels, and other content their agents can actually run.
- **Agent builders** who need a public library an agent can read, with declared inputs and outputs, instead of a hidden pile of scripts.
- **Contributors** — people and bots — who want to add a better caption style, a new effect, or a whole recipe, and see it used.

## How it works

Contributors open a pull request. An admin reviews the **sample outputs** and merges. Once the sync is in place, merged content is snapshotted into [CFW Social](https://app.cfw.social)'s Marketplace as immutable, fingerprinted copies, so any bot, on any server, renders the same files. Every post that reaches Reviews is tagged with the recipe, blocks, and effects that made it. Usage then drives what stays in the library and what gets retired.

People and bots are both welcome. A bot that finds a reusable piece, or composes a new recipe, should open a pull request like anyone else — and include sample output so an admin can judge the result.

## What's here today, and what isn't

**Now (this repository):** the design, contribution guides, scaffolds for `blocks/` and `recipes/`, and a checked-in effects library under [`effects/`](effects/). That library is the Python package `fx`: 24 subject-aware vertical effects, plus `grid_collage` and the utilities `label`, `redact`, and `grade`. Each one is also an `e-*` effect block with `effect.yaml`, `SKILL.md`, and a synthetic preview. Run and test them as described in [`effects/README.md`](effects/README.md).

**Proposed, not built yet:**

- A settled, validated format and CI for blocks, effects, and recipes
- The merge-to-snapshot sync into CFW Social
- Marketplace listing from those snapshots, with no app deploy
- Automatic Reviews tagging and usage-based retirement

A folder in this repo is not, by itself, something already runnable in CFW. Do not assume otherwise.

## Roadmap

1. **Now** — design, guides, scaffolds, and the checked-in `effects/` library (package `fx`, with one `e-*` entry per effect).
2. **Next** — settle the block, effect, and recipe file format, and add CI that checks declarations and a sample.
3. **Then** — the sync endpoint and Marketplace listing from snapshots.
4. **Then** — post tagging in Reviews, plus usage analytics that inform what to keep or retire.

## Get started

- Browse [`effects/`](effects/) for the checked-in looks (see the inventory in [`effects/README.md`](effects/README.md)), and [`blocks/`](blocks/) and [`recipes/`](recipes/) for scaffolds. Each area has a `_template/` to copy.
- To contribute, read [CONTRIBUTING.md](CONTRIBUTING.md) and open a pull request with your piece, any new blocks or effects it needs, and sample outputs.
- To understand the model, start with [docs/DESIGN.md](docs/DESIGN.md). Coding agents should read [AGENTS.md](AGENTS.md) first.

## Docs

- [docs/DESIGN.md](docs/DESIGN.md) — full target design
- [docs/DECISIONS.md](docs/DECISIONS.md) — why this shape was chosen
- [docs/MIGRATION.md](docs/MIGRATION.md) — how to get here from today's publish path
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to add an effect, block, or recipe
- [AGENTS.md](AGENTS.md) — instructions for coding agents

## License

MIT. Copyright (c) 2026 CFW Social. See [LICENSE](LICENSE). The same terms cover the `effects/` library ([effects/LICENSE](effects/LICENSE)).
