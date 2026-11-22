# Blocks

Building block **templates**. Each block is a `c-*` folder of instructions (`SKILL.md`) plus supporting scripts, with declared inputs and outputs in `block.yaml`. A template teaches. A brand's bot reads it and builds its own recipe in CFW. It does not run for a brand from here.

Visual and audio treatments (transitions, caption styles, overlays, and the like) do **not** belong here; they live in [`../effects/`](../effects/).

Recipes ship whole first, in today's file format. The `block.yaml` format is the later format, so blocks are added after recipes.

Start a new block from [`_template/`](_template/). See [../docs/DESIGN.md](../docs/DESIGN.md) for the model and [../CONTRIBUTING.md](../CONTRIBUTING.md) for the vetting checklist. This folder is a scaffold; there are no blocks in this repository yet.
