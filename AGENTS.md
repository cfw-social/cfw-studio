# Agent instructions

CFW Studio holds **templates**: recipes, blocks and effects. A template teaches. It never runs for a brand.

Your brand's bot reads a template here, builds its own recipe, tries it, and saves it in that brand's recipe library inside CFW Social. The saved recipe is what runs.

```text
 CFW Studio (this repo)            CFW Social, one per brand
 templates: teach only    read     recipe library: what runs
 vetted, then merged  ------->  bot builds, tries, saves, locks in
```

The names "templates", "recipe library" and "built-in recipes" are proposed. The owner has not confirmed them.

## What exists and what does not

- Exists: this repo, with eight building blocks under `blocks/`, the `effects/` library (29 `e-*` folders, mostly the Python package `fx`) and a scaffold for `recipes/`. Recipe templates under `recipes/` are added separately. A recipe refers to a block by the relative path `../../blocks/b-<name>/`.
- Built: a brand recipe library in CFW Social. A brand's own recipe name starts with `my-`. Six tools on the bot's render connection (`list_my_recipes`, `check_recipe_save`, `upload_recipe_files`, `save_recipe_draft`, `lock_in_recipe`, `remove_recipe`) let a bot list, check, upload, save, lock in and remove them. They work only for a key made with the "Save its own recipes" permission, which is off unless the person ticks it. Limits: 20 recipes per brand and 10 open drafts per recipe.
- Planned, not built: tags on posts that show the brand recipe and the template it came from, a "Your recipes" page in CFW Social, and the CFW Studio page of the bot guide (being written).
- There is no sync from this repo into CFW. Merging here does not change what runs for any brand.

## Start here

1. Read [docs/DESIGN.md](docs/DESIGN.md) for the model.
2. Read [docs/DECISIONS.md](docs/DECISIONS.md) for why. The latest section overrides the earlier ones.
3. Read [docs/MIGRATION.md](docs/MIGRATION.md) before touching today's Social publish path.
4. Follow [CONTRIBUTING.md](CONTRIBUTING.md) to open a pull request.
5. If a template fails or is wrong, read [docs/REPORTING.md](docs/REPORTING.md) and file an issue.

## Hard rules

- Open pull requests and issues only. The owner vets every pull request against the eight-point checklist in CONTRIBUTING.md and is the only one who merges. Never push to `main`.
- A brand's bot saves its own recipes through CFW tools. It never edits built-in recipes and never writes rows by hand.
- Do not commit secrets, keys, private local paths, brand facts, customer names, or order text.
- Do not put order text or brand text into a shell command.
- Do not copy AGPL third-party application code into this repo. Rebuild ideas as CFW effects, blocks and recipes.
- Recipes ship whole first, in today's file format. `block.yaml` and `recipe.yaml` come later. Do not convert existing templates yet.
- Do not implement CFW-side tools in this repo. They belong in the Social app.
