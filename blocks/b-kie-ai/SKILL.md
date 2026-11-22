# b-kie-ai

Make one AI still image with the Kie API. Use it when a recipe needs a generated image. It spends the brand's Kie credits, so call it once per image you need.

## Steps

1. Write the prompt to a text file in the work folder (for example `prompt.txt`). Never put it in a shell string.
2. Run from the work folder, with the brand's Kie key in `KIE_AI_API_KEY` for that one command only (or pipe it in with `--key-stdin`):
   `python3 ../../blocks/b-kie-ai/scripts/generate.py --prompt-file prompt.txt --out image.png --aspect 9:16`
3. To anchor on a reference picture, add `--model gpt-image-2-image-to-image --resolution 2K --ref ref.png`. The reference must be inside the work folder.
4. Read the last stdout line. `IMAGE_FILE:` means the PNG is saved. `IMAGE_FAILED:` means it is not.

## Exit codes

0 saved. 1 Kie or network failure. 2 bad arguments, nothing sent. 3 no key, nothing sent.

## Rules

- Never print, log or save the key. Never pass it as an argument.
- `z-image` prompts are at most 1000 characters.
- Do not retry after exit 1 without a person's say-so; the task may still have been charged.
- Write only inside the work folder. Do not copy the image elsewhere from here.
- Check the PNG by looking at it before you use it.

Details, limits and the network hosts are in [README.md](README.md).
