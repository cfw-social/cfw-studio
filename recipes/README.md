# Recipes

Recipe **templates**. Each recipe is an `r-*` folder: a guiding document (`SKILL.md`) plus `recipe.yaml`, which lists the blocks and effects it uses, the union of their required inputs, and the final output.

A template teaches. A brand's bot reads it, builds its own recipe, tries it, and saves it in that brand's recipe library in CFW. The saved recipe is what runs. The CFW tools for saving are planned, not built.

Recipes ship whole first, in today's file format. The `recipe.yaml` shown in the scaffold is the later format.

Start a new recipe from [`_template/`](_template/). If it needs a block or effect that does not exist yet, add it in the same pull request. See [../docs/DESIGN.md](../docs/DESIGN.md) and [../CONTRIBUTING.md](../CONTRIBUTING.md). This folder holds the scaffold now. The recipe templates are added separately.

A recipe refers to a block by the relative path `../../blocks/b-<name>/`, for example `../../blocks/b-qa-gate/check.py`.
