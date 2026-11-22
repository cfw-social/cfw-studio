# b-kie-ai

Makes one AI still image by calling the Kie API directly (`https://api.kie.ai`) and saves it as a PNG in the work folder. One run is one image and spends Kie credits.

This is a building block **template**. It teaches. A brand's bot reads it, adapts it, and runs it in its own recipe. It does not run for a brand from here. The CFW Social side that saves and locks in a brand's recipes is planned, not built.

## What you need

| Need | Version | Why |
|---|---|---|
| Python | 3.10 or newer; run with 3.15 only | the script uses the standard library only |
| ffmpeg | 6 or newer (run with 8.1) | only to turn a JPEG or WEBP result into PNG |
| A Kie account with credits | any | the brand's own key; there is no shared key |

The key is the brand's own Kie key. It comes from the order that started the run. It is never read from disk.

## Interface

One entry point, run from the work folder (the current folder is the work folder):

```text
python3 <blocks>/b-kie-ai/scripts/generate.py --prompt-file FILE --out FILE.png [options]
```

| Argument | Required | Meaning |
|---|---|---|
| `--prompt-file FILE` | yes | UTF-8 text file in the work folder, 1 to 1000 characters for `z-image`, 1 to 4000 for other models. The prompt is never a command-line string. |
| `--out FILE.png` | yes | PNG to write. Must end in `.png` and resolve inside the work folder. |
| `--aspect W:H` | no (default `16:9`) | Aspect ratio. `z-image` takes `1:1`, `4:3`, `3:4`, `16:9`, `9:16`. |
| `--model KEY` | no (default `z-image`) | Kie model key. Only `z-image` and `gpt-image-2-image-to-image` are confirmed (see Limits). |
| `--ref FILE` | for image-to-image | Reference image (PNG, JPEG or WEBP, 10 MB or less, inside the work folder). Repeatable up to 16. Only the model `gpt-image-2-image-to-image` accepts it. |
| `--resolution 1K\|2K\|4K` | for image-to-image | Output size sent to Kie. |
| `--timeout N` | no (default 150) | Seconds to wait, 3 to 1800. |
| `--poll N` | no (default 5) | Seconds between status checks, 1 to 60. |
| `--download-timeout N` | no (default 120) | Seconds allowed for the whole result download, 3 to 600. |
| `--key-stdin` | no | Read the key from one line of standard input instead of the environment. |
| `--dry-run` | no | Check everything, print the plan, send nothing. |
| `--base-url`, `--upload-base-url` | tests only | Only `http://127.0.0.1:PORT` or `http://localhost:PORT`. Any other value is refused. |

| Item | Value |
|---|---|
| Key | Environment variable `KIE_AI_API_KEY`, set for this one process, or one line on standard input with `--key-stdin`. Never an argument. Never read from a file. |
| Inputs | The prompt file, optional reference images. |
| Output files | The PNG at `--out`. Nothing else is left behind. |
| Output lines (stdout) | `KIE_TASK: <id>` once Kie accepts the task. Last line `IMAGE_FILE: <path> (...)` or `IMAGE_FAILED: <reason>`. |
| Exit 0 | Image saved. |
| Exit 1 | Kie or network failure (a body `code` other than 200 counts, even on HTTP 200), a rejected request, a failed task, a timeout, or a bad or oversized download. |
| Exit 2 | Bad arguments or a path outside the work folder. Nothing was sent. |
| Exit 3 | No key. Nothing was sent and nothing was spent. |

Example, from the work folder:

```bash
printf '%s' "$PROMPT_TEXT" > prompt.txt          # the bot writes the file, not a shell string
KIE_AI_API_KEY="$KEY" python3 ../../blocks/b-kie-ai/scripts/generate.py \
  --prompt-file prompt.txt --out image.png --aspect 9:16
```

## How it keeps the key and the money safe

```text
prompt file --> create task (once) --> poll status --> download (no key) --> PNG
   key only to api.kie.ai, and to the upload host when --ref is used
```

- The key is held in memory. Every line the script prints is scrubbed of it, even if a server echoes it. It is not passed to ffmpeg.
- No redirect is ever followed, on keyed calls or on the download.
- Kie can answer HTTP 200 with a failure `code` in the body, so the body `code` is checked. 401, 402, 429 and 455 get a plain one-line reason that never holds the key.
- Every piece of server text goes through one function before it is printed: the key is removed from the whole text first, then control characters (newlines, U+2028, U+2029, U+0085) become spaces, and only then is it cut to length. So no part of the key can show and a server cannot forge a result line. One function prints the `KIE_TASK`, `IMAGE_FILE` and `IMAGE_FAILED` lines; the result line is printed once, last.
- Each network call has a deadline for the whole transfer (download 120 s by default, status checks 20 s, upload 60 s), not only per read.
- A bad or odd reply is a one-line failure (exit 1). No traceback is ever printed.
- The task id is checked (letters, digits, `_`, `-`) before it goes into a URL.
- The create call is never retried, so you cannot be charged twice. Status checks are free and are retried a few times.
- The result must be an https address with no `@` in its host part and a public host: loopback, private, link-local and number-only addresses and single-word hosts are refused (loopback http is allowed only with a local test `--base-url`). The download carries no key, follows no redirect, and is capped at 25 MB.
- With `--ref`, the file is first sent (Kie's docs say uploaded files are deleted after 24 hours) to Kie's own upload call under the fixed path `studio-refs`, named by its content hash. Kie must keep the reference in the task, or the image is refused.
- The saved file is checked as a PNG: signature, `IHDR` first, every chunk length and CRC consistent, `IEND` last with nothing after it. A JPEG or WEBP result is converted by ffmpeg, which is told the input format by name from the file's own signature (it never guesses), and then checked the same way.
- Temporary files are created fresh (`mkstemp`) in the output folder, removed on every failure path, and the finished file is moved into place with `os.replace`. An output path that is a symbolic link is refused.
- Every path (prompt, reference, output) must resolve inside the current folder. The script writes nowhere else.

## Network use

| When | Host | What is sent |
|---|---|---|
| Setup | none | Nothing. There is nothing to install. |
| Run | `api.kie.ai` | The create call and the status checks, with the key. |
| Run, only when a reference image is used | `kieai.redpandaai.co` (Kie's documented upload host) | The reference image, with the key. Kie's docs say it is deleted after 24 hours. |
| Run | the https host Kie names in its reply for the result file | A plain download with no key header. The host is chosen by Kie, not fixed here. The key is never sent to it. |

Reference images are uploaded to Kie. Do not use `--ref` for a picture you may not send to Kie.

## Used by

`r-ai-image` and `r-ai-character` (recipe templates live under `recipes/` and are added separately).

## Proof

A short summary of the limits below. Where this README does not say, it reads "not recorded".

| What | Status | Detail |
|---|---|---|
| Automated tests | 65 tests, as of 2026-11-22 | `python3 -m unittest discover -s blocks/b-kie-ai/test`, from the repository root. A fake Kie server runs on `127.0.0.1`. |
| Run on which operating systems | macOS (Apple silicon) only; Linux and Windows not run | Python 3.15.2, Node 25.9.0, ffmpeg 8.1 on one Apple-silicon Mac. |
| Run with a real provider account | not run with a real account | Nothing here has run against the live provider. |
| Used in a real start-to-finish recipe run | only against a local fake server | Only the local fake server; no live Kie call has been made. |

## Tests

They need no paid account and no private file. A small fake Kie server runs on `127.0.0.1`. From the repository root:

```bash
python3 -m unittest discover -s blocks/b-kie-ai/test -v
```

The tests cover: success, a failed task, a timeout, an oversized download, a redirect on the keyed call and on the download, a key echoed by the server, key from standard input, no key, bad arguments, paths outside the work folder (including through a symlink), a reference that Kie drops, a JPEG result, HTTP 200 with a failure code in the body (create, status, upload), error codes 401, 402 and 429, `resultJson` as a string and as an object, an unsafe task id, the key never reaching the result host, a forged result line through `msg` and through `failMsg`, planted symlinks, a slow download hitting the overall deadline, crash-shaped replies, userinfo in URLs, a fake PNG body, private-address result hosts, and no redirect on create, status, upload or download.

## Limits and known gaps

- Image generation only. No video.
- The key is removed from server text. If a server echoes it with spaces, dots, hyphens or control characters put inside it, the whole message is withheld and a fixed line is printed instead. An encoded form of the key (for example base64) is not recognised and would be printed.
- **Not proven with a real account.** Nothing here has run against live Kie. The tests use a fake server.
- **Checked against Kie's public docs on 2026-11-22** (docs.kie.ai, read as reference data): create call and `model`/`input` body, `data.taskId`; the status call `recordInfo`, its states, `resultJson` as a JSON string, `failCode` and `failMsg`, and body codes (200, 401, 402, 422, 429, 455, 500, 501 and more; HTTP is 200 even on failure); the file stream upload call (`file`, `uploadPath`, `fileName`, `data.downloadUrl`). Pages: `market/google/nano-banana`, `market/common/get-task-detail`, `file-upload-api/upload-file-stream`, `file-upload-api/quickstart`.
- **Model shapes confirmed in the docs (2026-11-22):** `z-image` (`market/z-image/z-image`: `prompt` up to 1000 characters, `aspect_ratio` one of five, PNG output) and `gpt-image-2-image-to-image` (`market/gpt/gpt-image-2-image-to-image`: `prompt`, `input_urls` up to 16, `aspect_ratio`, `resolution` 1K/2K/4K with the stated exclusions). Any other `--model` is sent with the same fields and is **not confirmed in the docs**; check its page first.
- Host checks look at the written address only. A public name that resolves to a private address is not caught. This affects only the result download, which carries no key.
- Kie's upload page shows one host in its server block (`https://api.kie.ai`) and another in its curl example (`https://kieai.redpandaai.co`); its quickstart lists `https://kieai.redpandaai.co` only. This block uses `kieai.redpandaai.co`. Read on 2026-11-22; if Kie changes it, use `--upload-base-url` only for local tests and edit the script's constant after reading the docs.
- The docs list an `auto` aspect and a `background` field for `gpt-image-2-image-to-image`; this block does not send them. The docs give no size limit for reference images; the block caps them at 10 MB itself.
- Model names, credit costs and allowed values are Kie's and change. If Kie changes its API, the script fails with a plain message.
- Real hosts use the system proxy settings; loopback test addresses use none.
