# b-qa-gate

Use this at the end of a recipe, on the finished reel or image, to run the mechanical
checks in the recipe's `acceptance.json` and get a scorecard.

## Run it

From the order's work folder:

```sh
python3 ../../blocks/b-qa-gate/check.py --kind reel  --spec <recipe>/acceptance.json --input saves/final.mp4 --out work/scorecard.json
python3 ../../blocks/b-qa-gate/check.py --kind image --spec <recipe>/acceptance.json --input saves/card.png   --out work/scorecard.json
```

- `--kind reel` for a video, `--kind image` for a still. Run it once per file.
- `--input` and `--out` must be inside the current folder.
- A step that wrote its own spec copy (for another canvas size) passes that copy as `--spec`.
- `--step NAME` runs one interim step's checks.
- Pass paths as separate arguments. Never build the command from order or brand text.

## Read the result

| Exit | What to do |
|---|---|
| 0 | Everything passed. Continue. |
| 4 | Mechanical checks passed. Answer every `LOOK` row (see below), then continue. |
| 1 | Something failed. Read `FAIL` lines in the output or `checks` in the scorecard. Fix the file or the recipe step, run again. Do not deliver. |
| 2 | Your command was wrong. Nothing was checked. Fix the arguments. |

A check kind this block does not know is a FAIL, not a skip. Do not edit the spec to make
it go away. A recipe-specific guard belongs in the recipe, run as its own step.

## Answer the looks

For each row with `status` `LOOK`, open the file (for a reel, the PNGs listed in
`frames`) and answer the row's `question` with your own vision tool. Write
`work/answers.json`, one entry per LOOK row id, then finalize:

```json
{ "<check id>": { "answer": "yes", "note": "short reason" } }
```

```sh
python3 ../../blocks/b-qa-gate/check.py --finalize work/scorecard.json --answers work/answers.json --out work/final-scorecard.json
```

| Exit | Meaning |
|---|---|
| 0 | Final PASS. Every look is "yes" and every mechanical row passed. |
| 1 | Final FAIL: a "no", a missing answer, an answer for an id that is not a look, or a mechanical FAIL. Fix the file and run the check again. |
| 2 | Bad command or paths. Nothing was written. |

Every LOOK row needs an answer. Answer "no" if you did not really look or are unsure.
A scorecard with a mechanical FAIL can never become PASS. Deliver only on the final scorecard's PASS.

## Rules

- A scorecard is a record, not proof. Never edit a scorecard by hand: it defeats the gate. If the checked file changes, run the check again; `--finalize` fails on a changed or missing input.
- Keep `--out` different from the input, the spec and the answers file. Never plant links where the scorecard or its frames folder go.
- Never lower a threshold in the spec to pass.
- Never skip a row, and never answer "yes" for a row you did not look at.
- This block makes no network call and reads no key.
