# b-typing-ui

Two vertical page templates, a chat-style typing card and a hook card (eyebrow, three big lines, subhead), with one safe filler script for each. Text comes from a JSON file and is escaped.

Use when a reel beat needs a typing card (a prompt typed into a chat card) or a hook card
(a big opening title). Never edit the template placeholders by hand: the fillers do the escaping.

## Steps

1. Write a JSON text file in the work folder.
   - Typing: `{"prompt": "...", "label": "AI chat", "card_label": "The prompt", "bottom_tag": ""}` (only `prompt` is required).
   - Hook: `{"eyebrow": "...", "line1": "...", "line2": "...", "line3": "...", "subhead": ""}` (only `line1` is required).
2. Fill it, from the work folder:
   - `python3 "$BLOCKS_DIR/b-typing-ui/scripts/typing_fill.py" --out work/typing.html --duration 9 --text-file work/typing.json --accent F97316 [--variant pip-safe] [--prompt-size 44] [--fg F8FAFC] [--bg 0F172A] [--speed 1.0]`
   - `python3 "$BLOCKS_DIR/b-typing-ui/scripts/hook_fill.py" --out work/hook.html --duration 3 --text-file work/hook.json --accent F97316`
   - Add `--wrap template` for a sub-composition, and `--slot tk1` to give a scene its own id when several share a page.
3. Fetch the library once: `python3 "$BLOCKS_DIR/b-hyperframes/scripts/fetch_gsap.py" --outdir vendor`. Copy `vendor/gsap.min.js` to `gsap.min.js` beside the filled page (for example `comp/gsap.min.js` next to `comp/index.html`).
4. Check and render: `python3 "$BLOCKS_DIR/b-hyperframes/scripts/hf_render.py" --comp comp --out out.mp4 --quiet` (it runs `check_local.py` first; run that alone to see `LOCAL_ONLY: PASS|FAIL`).

## Size and colours

Typing prompt size is 24 to 72 px (default 44, or 38 for `pip-safe`). Long prompts are cut off at the bottom of the card; a note says when. `--bg` and `--fg` set the background and text on both cards; contrast below 3.0 is refused (exit 2). With captions on, leave the hook `subhead` empty, and the `bottom_tag` empty for `pip-safe` (the caption band, 260 px tall, starts at the recipe's `--cap-top`).

## Text limits

The render check refuses any page with an address in it, even as plain text. So the fillers refuse (exit 2, naming the key) `http:`, `https:`, `ws:`, `wss:`, `ftp:`, any `name://`, `//host`, `javascript:`, `vbscript:`, `data:` types, `url(`, `@import` and `image-set(` in any text. Write `example.com`, not `https://example.com`.

## Rules

- Exit 2: fix the input (bad colour, over-long or empty text, a path outside the work folder). Exit 3: the block is damaged.
- Colours are six hex digits. Do not put another company's name or logo in `label` or `card_label`.
- Fonts Inter, JetBrains Mono and Oswald should be installed (each is declared with a local `@font-face`; if missing the generic family is used and the look differs). The library is not bundled and the page loads nothing from the network.
