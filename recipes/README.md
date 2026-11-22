# Recipes

Recipe **templates**. Each recipe is a `p-*` folder. Recipes copied in today's format have a guiding document (`SKILL.md`), a `manifest.json` (inputs, steps, saves and checks) and a `steps/` folder. The later `recipe.yaml` format will list the blocks and effects a recipe uses, the union of their required inputs, and the final output.

A template teaches. A brand's bot reads it, builds its own recipe, tries it, and saves it in that brand's recipe library in CFW (planned). The saved recipe is what runs. The CFW tools for saving are planned, not built.

Recipes ship whole first, in today's file format. The `recipe.yaml` shown in the scaffold is the later format.

Start a new recipe from [`_template/`](_template/). If it needs a block or effect that does not exist yet, add it in the same pull request. See [../docs/DESIGN.md](../docs/DESIGN.md) and [../CONTRIBUTING.md](../CONTRIBUTING.md). The first recipe template here is [`p-carousel`](p-carousel/), with its source noted in [SOURCE.md](SOURCE.md).
