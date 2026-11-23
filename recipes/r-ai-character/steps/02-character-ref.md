# Generate the character reference

Produce the single reference image every scene call will be anchored to: full body, clean
studio background, all six attributes visible. Audit it against the lock before saving.

## You receive

- `prior/character_lock.json`: `type`, `attributes`, `lock_prompt`.
- `inputs/reference_image/<file>`: optional; an existing character image the brand wants
  kept. When present, the reference is an image-to-image pass that keeps that character and
  places it in the studio setup; the audit still applies. **That file is uploaded to the
  provider.** See "People and likeness" below before you use it.
- `brief.json`: `brand` (`imageStyle` when present), `intent`.
- The brand's Kie key, supplied with the order (see "The key" below).

## You must produce

- `saves/char_ref.png`: the reference at exactly `1080x1920`.
- `saves/ref_audit.json`: `{ "task_id": "...", "model": "...", "attempts": 1, "audit": {
  "1": "PASS", "2": "PASS", "3": "PASS", "4": "PASS", "5": "PASS", "6": "PASS" }, "notes": [] }`.

## People and likeness

The optional `reference_image` is sent to Kie (host `kieai.redpandaai.co`). Kie's docs say
uploaded files are deleted after 24 hours; Kie's own terms apply. Use only a reference image
the brand has the right to use, of a person who agreed to it. If the picture shows a real
person and you are not sure they agreed, do not use it: describe the character in words
instead. This template ships no reference image, no person's name and no id. This is a
plain safety note, not legal advice.

## The key

The key is the brand's own Kie key, taken from the order. The generation script reads it
from the environment variable `KIE_AI_API_KEY` of that one process, or from one line on
standard input with `--key-stdin`.

- Put it in the environment of the one command only, as in the block below (`ORDER_KEY` is a
  shell variable your tool fills from the order).
- Never type the key into a command line as an argument, never write it to a file, never
  print it. Do not turn on shell tracing (`set -x`).
- If the script exits 3 there is no key: stop and report it. Nothing was sent or spent.

## How

```bash
mkdir -p work saves
[ -n "${RECIPE_DIR:-}" ] || { echo "RECIPE_DIR is not set; point it at this recipe folder"; exit 1; }
BLOCKS_DIR="$RECIPE_DIR/../../blocks"
GEN="$BLOCKS_DIR/b-kie-ai/scripts/generate.py"
[ -f "$GEN" ] || { echo "the b-kie-ai generate.py is missing under the blocks folder"; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || { echo "ffmpeg is not installed"; exit 1; }
TYPE=$(python3 -c "import json;print(json.load(open('prior/character_lock.json'))['type'])")
REF=$(ls inputs/reference_image/* 2>/dev/null | head -1)
```

### 1. The prompt

Write the prompt to `work/prompt.txt` with your file-writing tool, never as a shell string.
The generation script reads the file. See the order-text rule in `_shared.md`.

`"<brand imageStyle base, if any>. <LOCK>. Full body, standing, facing camera, product
photography, plain white studio background, clean soft studio lighting, no text."` For
`plush` append `", plush toy, soft fabric texture, photorealistic toy photography"`. The lock
sentence (`lock_prompt` from `prior/character_lock.json`) is included verbatim, never
paraphrased.

Length: the text-to-image model `z-image` takes 1 to 1000 characters; the image-to-image model
takes 1 to 4000. If the script exits 2 for length, shorten the brand style text, never the
lock sentence.

### 2. Create, poll, download

One call is one paid image. The script creates the task once, never retries the create call,
polls every 5 s up to `--timeout`, and stops with a plain reason on a Kie error. Use only the
two models the block lists as confirmed:

- no `$REF`: text-to-image, `--model z-image`, `--aspect 9:16`;
- with `$REF`: image-to-image, `--model gpt-image-2-image-to-image --resolution 2K --aspect 9:16`
  with the picture passed by `--ref`. The script uploads it and refuses the image if Kie
  does not keep the reference in the task. First copy the brand's file to a JPEG of at most
  2048 px a side, which is well under the 10 MB limit, whatever the input format.

```bash
RC=0
if [ -n "$REF" ]; then
  ffmpeg -y -v error -protocol_whitelist file -i "$REF" -vf "scale='min(2048,iw)':'min(2048,ih)':force_original_aspect_ratio=decrease" -frames:v 1 -q:v 2 work/ref-in.jpg \
    || { echo "the reference image could not be read; send a PNG, JPEG or WEBP picture"; exit 1; }
  KIE_AI_API_KEY="${ORDER_KEY:-}" python3 "$GEN" --prompt-file work/prompt.txt --out work/raw-ref.png \
    --aspect 9:16 --model gpt-image-2-image-to-image --resolution 2K --ref work/ref-in.jpg \
    --timeout 240 --poll 5 > work/gen.log 2>&1 || RC=$?
else
  KIE_AI_API_KEY="${ORDER_KEY:-}" python3 "$GEN" --prompt-file work/prompt.txt --out work/raw-ref.png \
    --aspect 9:16 --model z-image --timeout 150 --poll 5 > work/gen.log 2>&1 || RC=$?
fi
tail -1 work/gen.log
[ "$RC" -eq 0 ] || exit 1      # IMAGE_FAILED: the reason is on the last line; never repeat the call
TASK=$(sed -n 's/^KIE_TASK: //p' work/gen.log | tail -1)   # the task_id for ref_audit.json
ffmpeg -y -v error -i work/raw-ref.png -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" -frames:v 1 work/char-ref.png
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 work/char-ref.png
```

Exit codes of the script: 0 saved; 1 Kie or network failure; 2 bad arguments or a path outside
the work folder (nothing sent); 3 no key (nothing sent). After exit 1, do not call again
without a person's say-so: the task may still have been charged.

### 3. Audit against the lock

READ `work/char-ref.png` and check each of the six attributes from `prior/character_lock.json`
is visibly present and correct; also: full body in frame, plain background, no text, no
distorted anatomy. Any attribute that fails: regenerate on purpose (tighten the wording of the
failing attribute in the prompt; up to 3 attempts total, each a new paid call). Record the
verdicts with the recipe script, which writes `work/ref_audit.json`. `$TASK` is the task id
from the generation block, `$MODEL` the model it used, `ATTEMPTS` how many images you made:

```bash
python3 "$RECIPE_DIR/scripts/record.py" ref-audit --task-id "$TASK" --model "$MODEL" --attempts 1 \
  --audit 1=PASS 2=PASS 3=PASS 4=PASS 5=PASS 6=PASS
```

The file has the shape `{ "task_id", "model", "attempts", "audit": {"1": "PASS", ... "6": "PASS"},
"notes": [] }`. Add `--note "short text"` (repeatable) for a note. Use `FAIL` for an attribute
that failed; step 4 refuses a reference with any `FAIL`.

### 4. Write the saves

```bash
python3 - <<'PY'
import json, shutil
a = json.load(open('work/ref_audit.json'))
assert set(a["audit"]) == {"1","2","3","4","5","6"} and all(v == "PASS" for v in a["audit"].values()), "reference failed the six-attribute audit"
shutil.copy('work/char-ref.png', 'saves/char_ref.png')
json.dump(a, open('saves/ref_audit.json','w'), indent=1)
print(f"[character] reference locked after {a.get('attempts',1)} attempt(s), model {a['model']}")
PY
```

## If you cannot proceed

This step has no `canAsk` (`reference_image` is optional). Never write `needs_input.json`. A
missing key (exit 3), exhausted credits, a refused upload or generation (`IMAGE_FAILED`), or a
reference that fails the audit three times is a failure: exit non-zero with one plain line
naming the failing attribute or the Kie reason.

## Checks declared in the manifest

- `ref_dims`: `saves/char_ref.png` is exactly 1080x1920.
- `not_black`: centre luma of `saves/char_ref.png` is 16 or more.
- `ref_matches_lock`: `saves/ref_audit.json` has six `PASS` verdicts.
