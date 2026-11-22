# Decisions

Dated from the CFW Studio design discussion on **19 November 2026** (America/Chicago). Nothing here is implemented yet.

**Read the last section first.** "2026-11-19 to 2026-11-22: owner decisions" changes the model. Where an earlier decision below says GitHub is the source of truth, or that a merge syncs into CFW, that part is replaced. The earlier text is kept as history.

## 2026-11-19 — Building blocks are `c-*` instructions plus scripts

**Decision.** A building block is a reusable piece of instructions plus supporting scripts, with declared inputs and outputs. The id is always `c-*`. Multiple variations of a block may coexist, each with its own fingerprint and a light variation id.

**Why.** This is the Lego piece the rest of the system is built from. Declared inputs and outputs are what let any agent, or any recipe, compose blocks without reading the scripts first. Variations can live side by side so a newer caption style does not silently break an older recipe.

## 2026-11-19 — Recipes are guiding documents composed of blocks

**Decision.** A recipe is a guiding document that lists the blocks it uses. Its inputs are the union of its blocks' required inputs, and it declares its final output. Any agent can read a recipe and run it as-is, or compose a new one.

**Why.** The Marketplace-facing unit should be one readable plan: what you have to supply, which blocks run, and what comes out. Agents should not have to reverse-engineer a recipe from scattered step files or a hidden packager.

## 2026-11-19 — GitHub is the source of truth; contributions are pull requests

**Decision.** The public repository `cfw-social/cfw-studio` is the source of truth. People and bots contribute through pull requests. A recipe submission automatically includes any new blocks it needs. An admin approves by reviewing sample outputs and merging. Bots that find reusable pieces, or invent new blocks (including from public ideas), should open PRs rather than writing into CFW directly.

**Why.** GitHub already provides review, history, forks, and credit for contributors, so we do not have to build that ourselves. Sample outputs are the quality bar. Letting bots upload snapshots straight into the database would bring back drift and make approval harder.

## 2026-11-19 — On merge, sync immutable fingerprinted snapshots into CFW

**Decision.** After a merge, a GitHub Action or webhook calls one CFW endpoint. That endpoint snapshots the changed blocks and recipes into Postgres as immutable, fingerprinted copies, with the commit SHA. The Marketplace reads those database rows. Bots run from the CFW snapshot, not from live GitHub, so every server renders the same files. A merge is live in the catalog with no application deploy.

**Why.** Consistency matters more than reading the latest GitHub tree at render time. A fingerprint plus commit SHA is enough to reproduce a render and to tag the posts it produced. Keeping GitHub as the authoring surface and Postgres as the run surface avoids two competing catalogs.

## 2026-11-19 — No heavy semver; light fingerprint and variation ids only

**Decision.** Do not require semantic versions on blocks or recipes. Each published snapshot has a content fingerprint and, for blocks, a light variation id. Retiring a snapshot sets a status; the bytes stay so older posts still resolve.

**Why.** Semver and the current immutable `(recipe, version)` publish path added ceremony without helping authors compose Lego pieces. A fingerprint is what Reviews tags and retirement need. A variation id is enough to tell two living flavors of the same block apart.

## 2026-11-19 — Reviews posts are auto-tagged with recipe and block fingerprints

**Decision.** Every post that reaches Reviews is tagged with the recipe fingerprint and the ordered block fingerprints (and the commit SHA). Those tags support usage analytics and later retirement of unused blocks or recipes.

**Why.** Without usage data, retiring a long-lived recipe or an old block variation is a guess. The tag also makes it possible to see which Lego pieces actually appear in published work.

## 2026-11-19 — Fold effects in as a block kind

**Decision.** Effects are not a separate public repository. They fold into `cfw-studio` as blocks with `kind: effect`.

**Why.** One library is easier to contribute to than a split between “recipes” and “effects.” Effects are reusable instructions plus scripts, which is already the block shape. Note: when this decision was recorded, no `cfw-effects` repository was present in the `cfw-social` org, and this repo's initial README contained only `# cfw-effects`. The source of today's effects still has to be located before they can be folded in.

## 2026-11-19 — Effects live in a top-level `effects/` folder

**Decision.** Effects still have `kind: effect` and are referenced from recipes like any other block, but they live in a top-level `effects/` folder (proposed id prefix `e-*`), not mixed into `blocks/`. Each effect includes a preview of the look or sound.

**Why.** A dedicated folder makes the library of transitions, confetti, fireworks, caption styles, overlays, sound effects, and music beds easy to browse and contribute to, without changing the runtime model. The earlier decision stands: there is not a separate effects repository, and an effect is still a block.

## 2026-11-19 — The repository is named `cfw-studio`

**Decision.** The public repo is `cfw-social/cfw-studio`, not `cfw-recipes`, `cfw-blocks`, `cfw-cookbook`, or `cfw-studio-kit`. Inside the repo and in the product, keep saying **blocks** and **recipes**, because that is the wording customers already see in the Marketplace.

**Why.** `cfw-studio` is short, reads as a public place to create, and leaves room for blocks, recipes, effects, and later templates. `cfw-recipes` was a close alternative because it matches the Marketplace word, but it underplays the reusable blocks. Dropping “kit” keeps the name smaller without losing meaning.

## 2026-11-19 to 2026-11-22: owner decisions

These replace parts of the earlier decisions. Source: the Studio design plan, revision 3, written 2026-11-19, and the owner's replies the same day.

**What changed**

| Earlier decision | Now |
| --- | --- |
| GitHub is the source of truth | GitHub holds **templates** that teach. It is not the source of truth for what runs. |
| Merge is approval and goes live in CFW | A merge only puts a template in this repo. It does not reach any brand. |
| One CFW sync endpoint snapshots merges into Postgres | Dropped. There is no sync endpoint, no sync log, and no approval queue for scripts. |
| Bots never write to Postgres | A brand's bot saves its own recipes through CFW tools, into its own brand recipe library. It never writes built-in rows. |
| The Marketplace reads snapshots from merges | Unchanged by this repo. Built-in recipes stay in CFW. |
| Reviews posts are tagged with recipe and block fingerprints | Posts are tagged with the brand recipe and the template it came from. |
| License: GPL-3.0 | MIT. |
| An admin merges | The owner vets each pull request and is the only one who merges. |

**The new model**

```text
 template here --bot reads--> brand's bot builds --saves--> brand recipe library
                                                             draft, try, edit
                                                             user likes it: lock in,
                                                             other drafts go
 post in Reviews --tag--> brand recipe + the template it came from
```

- A template teaches. The brand's saved recipe is what runs.
- The bot edits its own recipe alone. When the user likes a version, the bot locks it in and the other drafts go.
- The CFW tools for this are planned, not built.

**Why**

- The owner wants GitHub to be a place where an agent learns a recipe, not a second catalog that has to stay in step with CFW.
- A sync endpoint would make a public merge change what runs for paying brands. The owner chose to vet before merge instead, and to hold nothing after.
- Giving each bot full control of its own recipe means no approve tap for the brand. Safety rests on vetting at the template door, brand-only scope, server checks on every save, and the user locking in a version.
- MIT is simple for anyone to reuse, and the owner or his agents wrote the code in `effects/`.

**Also decided**

- Recipes ship whole first, in today's file format. The `block.yaml` and `recipe.yaml` format comes later. The existing templates stay as they are.
- Bots and agents open pull requests and issues only. A bot that finds a template problem files an issue. See [REPORTING.md](REPORTING.md).
- The names "templates", "recipe library" and "built-in recipes" are proposed and not yet confirmed by the owner.
