# Migration from today's system

**Partly done.** Steps 3 and 4 below are live. The rest is planned. This is the path from today's CFW recipe library to the Studio model in [DESIGN.md](DESIGN.md). It does not authorize any production change by itself. Every CFW-side step below needs its own approved work in the Social app.

## What today looks like

Published recipes are stored in Postgres as immutable, content-hashed bundles (`recipe_library_*` tables). Getting a new recipe into the product takes an admin through several steps: author files in the harness source, package a bundle, publish it with `publish.mjs` and the account master key, add it to the vendored manifest in application code, and get it on the catalog and Marketplace lists.
## Where it is going

```text
 TODAY                                  TARGET
 admin publishes built-in recipes       built-in recipes stay (admin path)
 bots cannot make lasting recipes       each brand's bot saves its own recipes
                                        in the brand recipe library
 no public place to learn from          CFW Studio: templates that teach
```

- Built-in recipes stay as they are.
- Each brand gets its own recipe library. A recipe there is private to the brand.
- A brand's bot reads a template here, builds, tries, edits, and saves through CFW tools. The user says "I like it" and the bot locks the version in. The other drafts go.
- Posts are tagged with the brand recipe and the template it came from.
- No sync from this repo into CFW. No "merge goes live".

## Planned steps

Order matters. Each step is separate work with its own tests and the owner's approval.

1. **Make this repo safe to read.** MIT license, these docs, the vetting checklist, issue and pull request forms. Protect `main` so nothing merges without the owner. (This step is what this change set does, apart from the branch protection.)
2. **Move existing recipes in as templates.** Copy recipes and the blocks they use from the harness source, as they are, in today's file format. Recipes first, blocks later. Before any pull request: scan for keys, private paths and brand facts. One pull request per recipe, with a sample output. The owner vets each one.
3. **Add brand recipe libraries in CFW (done).** Add brand scope to the library tables and make every reader take the caller's brand. Test that one brand cannot list, fetch, pin or claim another brand's recipe.
4. **Give bots tools to save and lock in recipes (done).** A key scope for saves, a dry-run check, upload, lock-in, remove and list tools, with server checks on every save.
5. **Update the bot guide and the app (not done yet).** The guide teaches the loop: read a template at a named commit, build, try, lock in, reuse, report. A "Your recipes" page. Tags on posts.
6. **Retire what the library replaces.** The old skill tables and the register door, once nothing reads them. A table drop cannot be undone, so it needs a snapshot and the owner's approval.
7. **Later: the block and recipe file format.** Move templates to `block.yaml` and `recipe.yaml`.

The archived public `cfw-skills` repository can stay archived.
