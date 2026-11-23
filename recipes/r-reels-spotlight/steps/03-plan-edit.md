# Plan the edit

**You are the planner.** The engine running this step (Codex or Claude Code) reads the transcript
and the brand, thinks, and writes ONE curated `edit_plan.json` itself. There is no separate model
call, no API key and no fallback model. Every later step is a mechanical executor that fills
templates from this plan and never invents anything.

## You receive

- `prior/voice_track.mp4` — the sealed bed; probe it for `DUR`.
- `prior/transcripts.json` — use `.words` (`[{text,start,end}]`). Ignore `.broll_cues` here;
  b-roll placement is a later step.
- `brief.json` — brand (name, palette), intent, `options.grade` if set.

## You must produce

- `saves/edit_plan.json` — STRICT JSON, one object, no prose:

```json
{ "duration": DUR, "energy": "high|medium|low", "grade": "warm-amber|clean-bright",
  "cover_at": <float seconds — a content beat past the hook, NOT t=0, NOT in the hook scene>,
  "brand": {"bg":"#hex6","accent":"#hex6","fg":"#hex6"},
  "takeovers": [ {"start":s,"end":s,"template":"tk-stat|tk-keyword|tk-list|tk-quote|tk-typing-ui",
                  "fill":{...per-template keys...}} ],
  "caption_groups": [ {"start":s,"end":s,"style":0|1|2,
        "words":[{"w":"TEXT","s":start,"e":end,"em":false}] } ],
  "sfx": [ {"t":s,"name":"whoosh-deep|whoosh-air|impact-sub|impact-punch|riser|click|pop|swipe","gain":0.0-0.6} ] }
```

A **complete minimal** edit plan, for a 12-second bed (it passes both guards below; yours covers your whole
bed, so it has more caption groups, and 2–4 takeovers of 3–6 s each at least 4 s apart):

```json
{
  "duration": 12.0,
  "energy": "medium",
  "grade": "clean-bright",
  "cover_at": 9.0,
  "brand": { "bg": "#0F172A", "accent": "#F97316", "fg": "#F1F5F9" },
  "takeovers": [
    { "start": 3.0, "end": 6.5, "template": "tk-keyword",
      "fill": { "WORD": "ASKING", "SUPPORT": "beats waiting" } }
  ],
  "caption_groups": [
    { "start": 0.0, "end": 2.9, "style": 0,
      "words": [ { "w": "MOST", "s": 0.1, "e": 0.5, "em": false }, { "w": "SMALL", "s": 0.6, "e": 1.1, "em": false },
                 { "w": "BAKERIES", "s": 1.2, "e": 2.0, "em": true }, { "w": "WAIT", "s": 2.2, "e": 2.8, "em": false } ] },
    { "start": 3.0, "end": 6.4, "style": 1,
      "words": [ { "w": "FOR", "s": 3.1, "e": 3.4, "em": false }, { "w": "ORDERS", "s": 3.5, "e": 4.3, "em": true },
                 { "w": "INSTEAD", "s": 4.5, "e": 5.2, "em": false }, { "w": "OF", "s": 5.3, "e": 5.5, "em": false },
                 { "w": "ASKING", "s": 5.6, "e": 6.3, "em": false } ] },
    { "start": 6.6, "end": 11.6, "style": 2,
      "words": [ { "w": "WE", "s": 6.7, "e": 6.9, "em": false }, { "w": "ASKED", "s": 7.0, "e": 7.6, "em": true },
                 { "w": "AND", "s": 7.7, "e": 7.9, "em": false }, { "w": "ORDERS", "s": 8.0, "e": 8.8, "em": false },
                 { "w": "TRIPLED", "s": 9.0, "e": 11.5, "em": false } ] }
  ],
  "sfx": [
    { "t": 3.0, "name": "whoosh-deep", "gain": 0.5 },
    { "t": 3.4, "name": "impact-sub", "gain": 0.5 }
  ]
}
```

Template fill keys — `tk-stat`: EYEBROW, STAT (short, e.g. `3X` or `70%`), LABEL. `tk-keyword`:
WORD (one word), SUPPORT (short line). `tk-list`: TITLE, ITEM1, ITEM2, ITEM3. `tk-quote`: QUOTE,
ATTR. TITLE and QUOTE may wrap ONE key word in `<span class="accent">WORD</span>`. `tk-typing-ui`:
LABEL (a short card title such as `AI chat`), PROMPT (the typed text), TYPING_SPEED (0.5–1.5), BOTTOM_TAG, and
optionally CARD_LABEL (the line above the card; default `The prompt`).

## How

```bash
mkdir -p work saves || exit 1
DUR=$(ffprobe -v error -protocol_whitelist file -show_entries format=duration -of csv=p=0 prior/voice_track.mp4) || exit 1
python3 -c "import json; json.dump(json.load(open('prior/transcripts.json'))['words'], open('work/words.json','w'))" || exit 1
```

Read `work/words.json` and `brief.json`. Resolve the brand hexes (brand brief → palette in
`brief.json` → named style → default `#0F172A` / `#F97316` / `#F1F5F9`; 6-digit, single `#`).
The accent in `brief.json` is `brand.accent`, else `brand.palette.accent` (the order brief carries it
there); use the `#F97316` default only when neither is set, never because the first key is missing.
Then write `saves/edit_plan.json` with your file-writing tool, following these rules:

1. `caption_groups` cover the FULL duration, 2–4 words each (up to 6 to keep a phrase whole),
   non-overlapping, breaking at punctuation, clause starts or pauses ≥ 150 ms. Never break after a
   preposition, article, possessive, conjunction or auxiliary (`with`, `of`, `the`, `her`, `and`,
   `is`, …), and never
   leave a lone 1–2 word fragment from mid-clause (`She approved them` / `with flour still on her
   hands,` — not `She approved them with` / `FLOUR STILL` / `on her hands,`). Words VERBATIM from
   the transcript.
2. LATIN SCRIPT ONLY: transliterate any Devanagari (or other non-Latin) word phonetically. Never
   translate.
3. At most ONE word per group gets `"em": true`. Some groups have none.
4. `style` cycles 0/1/2 — never the same style on adjacent groups.
5. `takeovers`: 2–4 windows, 3–6 s each, first no earlier than t=2, none in the final 2 s (and
   none overlapping the final `cta_duration` seconds, default 3, where the end card sits), ≥ 4 s of
   speaker between windows, never the same template twice in a row. Content restates what is SAID
   in that window. Use `tk-typing-ui` only when the content involves AI / prompts / terminal work.
   Takeover text names only the order's brand: quote the speech word for word, or write the
   order's brand in place of any other brand or product the clip names; never invent a brand, and
   never write a competitor or comparison line that names another brand (`X vs Y`, `better than X`).
6. `sfx`: `whoosh-deep` at every takeover start, `impact-sub` 0.4 s later, optional `riser` 1.5 s
   before the biggest takeover, `click`/`pop` on at most 3 emphasis words. Max 12 cues, gain ≤ 0.6.
7. `cover_at`: a mid-content frame (ideally mid-sentence at peak energy) — NEVER t=0 or the first
   3 s. Typically 20–60 % of the duration, and not inside a takeover window (the cover must show
   the speaker).
8. A visible change (takeover, emphasis pop or caption style shift) every 2–4 seconds.
9. `grade`: honour `brief.json.options.grade` when set; otherwise pick `warm-amber` for warm /
   personal content and `clean-bright` for product / tech content.

Keep caption phrases whole. Run the helper on the plan: it moves a
group-ending preposition, article, conjunction or auxiliary into the next group, merges a
1–2 word mid-clause fragment into a neighbour (up to 6 words to keep a phrase whole), keeps
every word timing, and re-checks styles and emphasis. A plan that is already whole keeps its
groups; equal neighbouring styles, an overlap or a second emphasis word are still fixed.

```bash
python3 "$RECIPE_DIR/scripts/caption_phrases.py" saves/edit_plan.json || exit 1
```

Keep takeover text on the order's brand. A clip may name another brand or product (a promo cut
for `Test Brand` may say `XQZ already learned her voice`). A takeover line of 3+ words
that quotes the speech word for word keeps it. Any other line that carries a spoken acronym (also
spelled out, `X Q Z`) or CamelCase name (`XQZ`, `AcmeCloud`) the order does not own gets the order's
brand instead (`inputs/cta/cta.json` `brandName`, else `brief.json` `brand.name`, as on the end card),
or loses the name when the order has no brand. Generic acronyms (`CAC`, `MLS`, `HOA`, `NYC`, `PhD`),
`iPhone`-style words and names like `McKenzie` are never swapped. Run the helper on
the plan; it prints each line it changed.

```bash
python3 "$RECIPE_DIR/scripts/takeover_brand.py" saves/edit_plan.json work/words.json || exit 1
```

Then run the two mechanical guards and fix the plan until both pass. The first is this recipe's own
guard (`plan OK`); the second is the `b-reel-premium` block's plan check, the one that will later
read the caption groups, grade and sound effects (`--cover-tolerance 4.5` is the bed's silent
end-card tail):

```bash
python3 "$RECIPE_DIR/scripts/plan_guard.py" saves/edit_plan.json "$DUR" work/words.json || exit 1
python3 "$BLOCKS_DIR/b-reel-premium/scripts/check_plan.py" --plan saves/edit_plan.json --duration "$DUR" --cover-tolerance 4.5 || exit 1
```

## If you cannot proceed

This step has no `canAsk`. Never write `needs_input.json`. If `prior/transcripts.json` has too few
words to caption (fewer than ~10), exit non-zero with one plain line; the runner handles it.

## Checks

The two guards above are the checks. `plan_guard.py` parses the plan and checks that caption groups
cover the bed to within 4.5 s (its silent end-card tail) and keep phrases whole, Latin script only,
6-digit brand hexes, every takeover 2.5–7 s, `cover_at ≥ 2 s`. It also refuses angle brackets in
caption words and takeover text (only one `<span class="accent">` wrapper is allowed in `TITLE` and
`QUOTE`), unknown takeover templates, unknown sound-effect names and a sound-effect gain above 0.6.
These two guards are scripts you run, not `b-qa-gate` checks: the gate has no check for this plan.
