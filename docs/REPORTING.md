# Reporting a template problem

This page is for a bot. It says when to file an issue in this repo, how, and what must never go in one.

**Issues here are public.** Anyone on the internet can read them.

## When to file an issue

File an issue when a template in this repo:

- fails when you follow it, and you think the template is the cause
- gives a wrong result with the right inputs
- needs a tool, package or setting it does not say
- has a step that is unclear or missing
- looks unsafe (for example it reads a key or writes outside its work folder)

Do not file an issue for a problem in your own recipe or your own brand's data. Do not file one for a CFW Social app problem. Tell the brand's owner instead.

## How to file

```text
 template failed --> check for an open issue --> open one with the form
                       (same template + step)     "Template problem"
```

1. Search open issues for the same template and step. If one exists, add a comment only if you have new facts.
2. Open a new issue with the **Template problem** form. Fill every field:
   - template name
   - the commit of this repo that you read
   - the step that failed
   - the error text, cleaned (see below)
   - operating system
   - tool versions
   - what you expected
3. Do not open a pull request to fix a template unless the brand's owner asked for it. If you do, follow [CONTRIBUTING.md](../CONTRIBUTING.md). Only the owner merges.

## What must NEVER go in an issue

Clean the error text before you paste it. Replace each of these with a placeholder such as `[removed]`.

- keys, tokens, passwords, or env file contents
- brand facts: brand names, voice, colors, products, prices, plans
- order text, captions, prompts, or any text a customer wrote
- file paths (they show user names and brand folders)
- customer names, emails, or handles
- links to private media

If you cannot clean the error and keep it useful, say what kind of error it is in plain words and leave the text out.

## If you have no GitHub access

Do not look for a workaround. Tell the brand's owner what failed, with the template name, the commit, the step and the cleaned error. Point them to **support@cfw.social**.

## Labels

The owner reads the issues and sorts them. The form adds `template-problem`. These labels are documented here. They are not created by this repo.

| Label | Use it for |
| --- | --- |
| `template-problem` | Any template failed or is wrong (added by the form) |
| `recipe` | The template is under `recipes/` |
| `block` | The template is under `blocks/` |
| `effect` | The template is under `effects/` |
| `needs-info` | The owner needs more facts from the reporter |
| `unsafe` | The template may read keys, make undeclared network calls, or write outside its work folder |
| `docs` | A guide in this repo is wrong or unclear |
