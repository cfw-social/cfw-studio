# Recipes

Recipe **templates**. Each recipe is an `r-*` folder. Recipes copied in today's format have a guiding document (`SKILL.md`), a `manifest.json` (inputs, steps, saves and checks) and a `steps/` folder. The later `recipe.yaml` format will list the blocks and effects a recipe uses, the union of their required inputs, and the final output.

A template teaches. A brand's bot reads it, builds its own recipe, tries it, and saves it in that brand's recipe library in CFW. The saved recipe is what runs. The CFW tools for saving are live. They work only for a key made with the "Save its own recipes" permission. Tags on posts and a "Your recipes" page are planned.

Recipes ship whole first, in today's file format. The `recipe.yaml` shown in the scaffold is the later format.

Start a new recipe from [`_template/`](_template/). Read the "Improve first" rules in [../CONTRIBUTING.md](../CONTRIBUTING.md) before you add one: a recipe is built from the existing blocks. See also [../docs/DESIGN.md](../docs/DESIGN.md).

A recipe refers to a block by the relative path `../../blocks/b-<name>/`, for example `../../blocks/b-qa-gate/check.py`.

## The recipe templates

Each folder has its own README with what it makes, what it needs, its steps, its network use and its limits.

| Recipe | In one line | Blocks it uses |
|---|---|---|
| [`r-carousel`](r-carousel/) | Carousel slides from an outline | `b-qa-gate` |
| [`r-gfx-image`](r-gfx-image/) | A designed graphic image | `b-qa-gate` |
| [`r-ai-image`](r-ai-image/) | Generated images through the Kie API | `b-kie-ai`, `b-qa-gate` |
| [`r-ai-character`](r-ai-character/) | Scenes of one character from a reference image | `b-kie-ai`, `b-qa-gate` |
| [`r-reels-faceless`](r-reels-faceless/) | A vertical reel from a voice-over, clips and cards | `b-audio`, `b-broll-sync`, `b-typing-ui`, `b-reel-premium`, `b-hyperframes`, `b-qa-gate` |
| [`r-reels-pip`](r-reels-pip/) | A vertical reel with the speaker in a small card over clips | `b-audio`, `b-broll-sync`, `b-typing-ui`, `b-reel-premium`, `b-hyperframes`, `b-qa-gate` |
| [`r-reels-pip-heygen`](r-reels-pip-heygen/) | The same, with the speaker video made by HeyGen | the six above and `b-heygen` |
| [`r-reels-spotlight`](r-reels-spotlight/) | A vertical reel that keeps the speaker on screen, with takeovers and clips | `b-audio`, `b-broll-sync`, `b-typing-ui`, `b-reel-premium`, `b-hyperframes`, `b-qa-gate` |
| [`r-reels-spotlight-heygen`](r-reels-spotlight-heygen/) | The same, with the speaker video made by HeyGen | the six above and `b-heygen` |
| [`r-inspired-reel`](r-inspired-reel/) | An original reel shaped by the format of a reference reel | `b-audio`, `b-heygen`, `b-reel-premium`, `b-hyperframes`, `b-qa-gate` |

None of these has been run with a real paid provider account. Each README says what was run and what was not.
