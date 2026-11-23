# CFW Studio

The open library of **templates** (recipes, building blocks, and effects) that an AI agent can learn from to build its own recipes for a brand.

Think of it as a box of Lego. An **effect** is a brick with a look or a sound: a transition, confetti, fireworks, a caption style, an overlay, a sound effect, or a music bed. A **building block** is a reusable piece of work, such as transcribing a video or cutting on sentence boundaries. A **recipe** is the instruction sheet that snaps those pieces together and says what goes in and what comes out. A brand's bot reads these as templates and builds its own recipe from them.

## Names

```text
r-   a recipe template     recipes/r-<name>/
b-   a building block      blocks/b-<name>/
e-   an effect             effects/e-<name>/
```

A folder name starts with its letter, and the folder name is the template's id.

## Who it's for

- **Brand bots** that read a template, build their own recipe, and save it in the brand's recipe library in CFW Social.
- **Creators and brands** who want consistent short-form video, carousels, and other content their agents can run.
- **Contributors**, people and bots, who want to add a better template and see it vetted.

## How it works

This repo holds **templates**: recipes, blocks and effects. A template teaches. It never runs for a brand.

```text
 template here --bot reads--> brand's bot builds, tries --saves--> brand recipe library (in CFW)
                                                                    the saved recipe is what runs
```

**The save and lock-in tools are live in CFW Social. Post tags are planned.** Templates here only teach. The saved recipe is what runs.

- A brand's own bot reads a template, builds its own recipe, and tries it.
- The bot saves the recipe in that brand's recipe library inside [CFW Social](https://app.cfw.social). The recipe name starts with `my-`. The bot uses six tools on its render connection: `list_my_recipes`, `check_recipe_save`, `upload_recipe_files`, `save_recipe_draft`, `lock_in_recipe` and `remove_recipe`. They work only for a key made with the "Save its own recipes" permission. It is off unless the person ticks it. A brand can hold 20 recipes and 10 open drafts per recipe. A try needs a saved draft. When the user likes a version, the bot locks it in and the other versions go.
- Planned: posts are tagged with the brand recipe and the template it came from.
- Contributors open pull requests. The owner vets each one against an eight-point checklist (see [CONTRIBUTING.md](CONTRIBUTING.md)) and is the only one who merges. Bots and agents open pull requests and issues only.
- Merging here does not change what runs for any brand. There is no sync into CFW.

The names "templates", "recipe library" and "built-in recipes" are proposed and not yet confirmed by the owner.

## What's here today, and what isn't

**Now (this repository):** the design, contribution and reporting guides; eight building blocks under [`blocks/`](blocks/) (`b-audio`, `b-broll-sync`, `b-heygen`, `b-hyperframes`, `b-kie-ai`, `b-qa-gate`, `b-reel-premium`, `b-typing-ui`); a scaffold for `recipes/`; and a checked-in effects library under [`effects/`](effects/) with 29 `e-*` effect folders, including `e-camera-motion`. Most of the effects are the Python package `fx`. Each effect has `effect.yaml`, `SKILL.md` and a preview. Run and test them as described in [`effects/README.md`](effects/README.md). Recipe templates under `recipes/` are added separately. A recipe refers to a block by the relative path `../../blocks/b-<name>/`.

**Planned, not built:**

- Post tags for the brand recipe and its template
- A "Your recipes" page for the person in CFW Social
- The CFW Studio page of the CFW bot guide. It is being written. It will be linked from the bot guide at `https://app.cfw.social/assets/bot-setup.md`.
- The `block.yaml` and `recipe.yaml` format. Recipes ship whole first, in today's file format. The `_template` folders show the later format.
- Existing recipes moved in as templates

A folder in this repo is a template. It is not, by itself, something that runs in CFW.

## Roadmap

1. **Now:** safe repo, docs, effects library, eight building blocks.
2. **Next:** add the recipe templates under `recipes/`: move the recipes that run in CFW today into this repo as templates, one pull request each.
3. **Then:** the brand recipe library and the save tools are live in CFW Social. Still to come: post tags, a "Your recipes" page, and the CFW Studio page of the bot guide (being written).
4. **Later:** the block and recipe file format.

## Get started

- Setting up a machine? Start with [docs/SETUP.md](docs/SETUP.md): every tool the templates need, and three test pieces to make.
- Browse [`effects/`](effects/) for the checked-in looks (see the inventory in [`effects/README.md`](effects/README.md)), [`blocks/`](blocks/) for the building blocks, and [`recipes/`](recipes/) for the scaffold. Each area has a `_template/` to copy.
- To contribute, read [CONTRIBUTING.md](CONTRIBUTING.md) and open a pull request with your piece, any new blocks or effects it needs, and a sample run.
- If a template fails or is wrong, read [docs/REPORTING.md](docs/REPORTING.md) and file an issue.
- To understand the model, start with [docs/DESIGN.md](docs/DESIGN.md). Coding agents should read [AGENTS.md](AGENTS.md) first.

## Docs

- [docs/DESIGN.md](docs/DESIGN.md) — the model
- [docs/DECISIONS.md](docs/DECISIONS.md) — why this shape was chosen
- [docs/MIGRATION.md](docs/MIGRATION.md) — how to get here from today's publish path
- [docs/REPORTING.md](docs/REPORTING.md) — how a bot files an issue
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to add an effect, block, or recipe
- [AGENTS.md](AGENTS.md) — instructions for coding agents

## License

MIT. Copyright (c) 2026 CFW Social. See [LICENSE](LICENSE). The same terms cover the `effects/` library ([effects/LICENSE](effects/LICENSE)).
