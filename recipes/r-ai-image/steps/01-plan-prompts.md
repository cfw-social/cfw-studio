# Write the generation prompts

Turn the user's description into one concrete, brand-based generation prompt per requested
image, plus a negative list and the model choice. Nothing is generated here.

## You receive

- `inputs/prompt/prompt.md` — the user's image description.
- `inputs/count/count.md` — optional; one of `1`,`2`,`3`,`4`,`6`. Default `1`.
- `inputs/aspect_ratio/aspect_ratio.md` — optional; `1:1` (default), `9:16` or `16:9`.
- `inputs/reference_image/` — optional reference (note its presence: it sets `has_reference` and the
  model below; the next step sends the file to Kie as a hosted URL).
- `brief.json` — `intent`, `brand` (name, brief text, `imageStyle` when present), `targets`.

No prior saves: this is the first step.

## You must produce

- `saves/prompts.json`:

```json
{
  "count": 1,
  "aspect_ratio": "1:1",
  "model": "z-image",
  "has_reference": false,
  "negative": "watermark, text artifacts, extra limbs, blurry, low contrast",
  "images": [
    { "n": 1, "prompt": "<full prompt: brand style base + subject + setting + light + palette>", "variant": "<what makes this one different from the others>" }
  ]
}
```

Exactly `count` entries, `n` 1…count.

## How

`mkdir -p work saves`.

### 1. Read the inputs

```bash
DESC=$(cat inputs/prompt/prompt.md 2>/dev/null | tr -s '[:space:]' ' ')
N=$(cat inputs/count/count.md 2>/dev/null | tr -dc '0-9'); N=${N:-1}
AR=$(cat inputs/aspect_ratio/aspect_ratio.md 2>/dev/null | tr -d '[:space:]'); AR=${AR:-1:1}
ls inputs/reference_image/ 2>/dev/null
python3 -c "import json;b=json.load(open('brief.json'));br=b.get('brand') or {};print('intent:',b.get('intent'),'| brand name set:',bool(br.get('name')),'| imageStyle set:',bool(br.get('imageStyle')))"
```

The brand values are used, not echoed: take the name and `imageStyle` from `brief.json.brand` where
you write the prompts, and never print them (or any other `brief.json.brand` field) in the step
output. The command above prints only the intent and which brand fields are set.

If `DESC` is empty or does not name a subject (a single adjective, a URL, a question to you),
ask for it (below).

### 2. Write the prompts

For each of the `count` images: start from the brand's style base (`imageStyle` / brand brief),
then the user's subject, then setting, light, lens/medium and palette, in one paragraph of
plain descriptive sentences — no prompt-weight syntax. Batches vary ONE thing per image
(angle, time of day, composition) and keep the subject and style constant; say what varies in
`variant`. Text the user asked to appear is quoted verbatim and kept ≤ 4 words; otherwise add
"no text" to the prompt. The model is `z-image` without a reference image. Step 02 appends the negative list to every
prompt as "Avoid: ...", and `z-image` takes at most 1000 characters, so keep each prompt and the
negative list together under 1000 characters. (The only other model is the reference model below,
which takes up to 4000.) Do not pick another Kie model: `b-kie-ai` confirms only these two.

**With a reference image** (`inputs/reference_image/` holds a file) set `"has_reference": true` and
`"model": "gpt-image-2-image-to-image"`: `z-image` is text-to-image and would ignore the reference.
Each prompt then says in one plain sentence what to keep from the reference (its subject, face,
product or look) and what changes. Without a reference `has_reference` is `false` and the model is
`z-image`.

### 3. Write the save and self-check

```bash
python3 - <<'PY'
import glob, json, os
p = json.load(open('work/prompts.json'))
n = int(p["count"]); imgs = p["images"]
assert n in (1,2,3,4,6) and len(imgs) == n and [i["n"] for i in imgs] == list(range(1, n+1)), "count/numbering"
assert p["aspect_ratio"] in ("1:1","9:16","16:9"), "aspect"
ref = any(os.path.isfile(f) for f in glob.glob('inputs/reference_image/*'))
assert p.get("has_reference") is ref, "has_reference must be true exactly when inputs/reference_image holds a file"
if ref:  # a reference needs the image-to-image model; the text-to-image models would ignore it
    assert p["model"] == "gpt-image-2-image-to-image", "with a reference the model is gpt-image-2-image-to-image"
else:
    assert p["model"] == "z-image", "without a reference the model is z-image"
assert all(len(i["prompt"].split()) >= 12 for i in imgs), "prompt too thin"
limit = 1000 if p["model"] == "z-image" else 4000      # the block's own limits
for i in imgs:                                           # what step 02 will send: prompt + ". Avoid: " + negative
    sent = i["prompt"].strip().rstrip(". ") + ". Avoid: " + p["negative"]
    assert 1 <= len(sent) <= limit, "image %d: prompt plus negative list is %d characters; %s takes at most %d" % (i["n"], len(sent), p["model"], limit)
json.dump(p, open('saves/prompts.json', 'w'), indent=1)
print(f"[r-ai-image] {n} prompt(s), {p['aspect_ratio']}, model {p['model']}")
PY
```

## If you cannot proceed

This step may ask for **`prompt` only**. Write `needs_input.json` and stop (no save) when the
description is missing or too thin to picture, e.g.
`{"inputId":"prompt","reason":"Describe the image: what is in it, where, and the mood you want."}`.
Missing `count` / `aspect_ratio` are not asks — use the defaults.

## Checks for this step

- `prompts_shape` — `saves/prompts.json` parses; `images` has `count` entries numbered 1…N,
  each with a prompt of ≥ 12 words that fits the model's length limit once the negative list is added; `aspect_ratio` is `1:1`, `9:16` or `16:9`;
  `has_reference` is true exactly when a reference image was supplied, and then `model` is
  `gpt-image-2-image-to-image`.
