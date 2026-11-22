# b-heygen

Avatar narration through the HeyGen API. One Python script takes a narration text file, an avatar id and a voice id, creates the video, waits until it is done, and downloads the MP4 into the work folder.

**Not proven with a real account.** The tests run against a local fake server only. Nobody has run this script against HeyGen. See "What is not proven".

```text
narration.txt + avatar id + voice id
        |  POST /v3/videos   (key in header, no redirects)
        v
   video id --- poll GET /v3/videos/{video_id} every N s, up to a cap ---> completed | failed | timeout
        |
        v
   download video URL (no key sent, https only, size cap) --> avatar.mp4
```

## Interface

One entry point: `scripts/render.py` (Python 3.10 or newer, standard library only).

```text
HEYGEN_API_KEY=... python3 blocks/b-heygen/scripts/render.py \
  --script narration.txt --avatar-id <AVATAR_ID> --voice-id <VOICE_ID> --out avatar.mp4
```

| Argument | Required | Meaning |
|---|---|---|
| `--script FILE` | yes | Narration text (UTF-8), inside the work folder. Never a shell string. Up to `--max-chars` (default 5000). |
| `--avatar-id ID` | yes | HeyGen avatar id. Always an argument. This block ships none. |
| `--voice-id ID` | yes | HeyGen voice id. Always an argument. This block ships none. |
| `--out FILE.mp4` | yes | Where to write the video, inside the work folder. |
| `--background #RRGGBB` | no | Solid colour background. Default `#00FF00` (green, for keying out). |
| `--resolution R` | no | `4k`, `1080p` or `720p`. Default `720p`. Some resolutions are limited by plan or avatar type. |
| `--aspect-ratio A` | no | `16:9`, `9:16`, `4:5`, `5:4`, `1:1` or `auto`. Default `16:9`. |
| `--speed X` | no | Voice speed, 0.5 to 1.5. Sent as `voice_settings.speed`. Left out of the request when not given. |
| `--key-stdin` | no | Read the key from one line of standard input instead of the environment. |
| `--poll-seconds N` | no | Wait between status checks. Default 30. |
| `--max-wait N` | no | Seconds to wait for the render. Default 1800. |
| `--max-bytes N` | no | Download size cap. Default 500 MiB. |
| `--download-timeout N` | no | Overall seconds allowed for the download. Default 600. |

Ids are checked: 1 to 128 letters, digits, `-` or `_`.

**The key.** Environment variable `HEYGEN_API_KEY`, set for this one process only (not exported to a shell), or `--key-stdin`. There is no key option on the command line. The script reads no file for a key. The key is sent only in the `X-Api-Key` header to the HeyGen API host. It is never printed or written; it is also scrubbed from error text the server sends back.

**Never pay twice.** After submitting, the script writes `<out>.render.json` (`video_id`, `status`; no key). Run it again with the same `--out` and it resumes polling that render. Delete that file only if you want a new, separately charged render. A failed render is never resubmitted by the script. **If that file exists but is unreadable, malformed, a symbolic link, or holds an invalid id, the script stops with exit 2 and sends nothing**; you must delete the file yourself to start a new paid render.

**Output.** The MP4, and on stdout one line `VIDEO_FILE: <relative path>`. Logs go to stderr. The file is checked to start like an MP4.

Exit codes: `0` done | `1` failed (HeyGen error, failed render, timeout, redirect, download problem) | `2` bad usage or input (path outside the work folder, bad id, empty script) | `3` no key (nothing was sent).

## Safety

- https only to the API host. No redirect is followed on any request, and the keyed requests never get one.
- Download: the video URL comes from HeyGen's reply, must be https, carries **no key header**, follows **no redirect**, and is capped in size. If HeyGen's file host ever redirects, the download fails with a clear message instead of following it.
- Polling is capped by `--max-wait`. Three failed status checks in a row (network or server errors) stop it, and a rerun resumes.
- Writes only inside the work folder. Every file it writes (the MP4, a temporary file, the render record) is made with a random temporary name in the target folder, refused if the target is a symbolic link, moved into place, and checked to be inside the work folder. A planted link is never written through.
- Everything printed from the server is scrubbed of the key and stripped of control characters first, so a server message cannot forge the `VIDEO_FILE:` line. That line is printed once, last, by one function.
- The video URL must be https, must not carry a user name, and must not point at a loopback, private or link-local address. The download has an overall time limit (`--download-timeout`) as well as a size cap. Each read waits no longer than the time left, so the real bound is the limit plus a few seconds; connecting and reading the response headers wait up to the limit or 60 seconds, whichever is shorter, per step.
- An unexpected error prints one fixed line, never a traceback.
- A test-only option `--base-url` accepts `http://127.0.0.1` or `http://localhost` and nothing else.

## Network

| Host | When | What is sent |
|---|---|---|
| `api.heygen.com` | create and poll | The key, ids, and narration text. |
| The host in HeyGen's `video_url` reply (HeyGen's own file host; not named in this block, and https is required) | download | Nothing but the request. |

## Tools and versions

Python 3.10 or newer; run with 3.15 only. No other tool. A HeyGen account with API credits is needed for real use (the brand's own key). The recipe that uses the video decides what to do with a green background (for example, key it with ffmpeg).

## Used by

`r-inspired-reel` and the two HeyGen variants (`r-reels-pip-heygen`, `r-reels-spotlight-heygen`) call it (recipe templates live under `recipes/` and are added separately).

## Proof

A short summary of the limits below. Where this README does not say, it reads "not recorded".

| What | Status | Detail |
|---|---|---|
| Automated tests | 31 tests, as of 2026-11-22 | `python3 -m unittest discover -s blocks/b-heygen/test`, from the repository root. They run against a local fake server. |
| Run on which operating systems | macOS (Apple silicon) only; Linux and Windows not run | Python 3.15.2, Node 25.9.0, ffmpeg 8.1 on one Apple-silicon Mac. |
| Run with a real provider account | not run with a real account | Nothing here has run against the live provider. |
| Used in a real start-to-finish recipe run | only against a local fake server | Only the local fake server; no real HeyGen call has been made. |

## Tests

```text
cd blocks/b-heygen && python3 -m unittest discover -s test -v
```

They cover success, a failed render, a timeout, resume, an oversized download, a redirect, a non-MP4 download, bad paths and ids, and that the key appears in no output or file. No account or private file is needed.

## Sources

The request and response shapes follow HeyGen's public v3 pages, read on 2026-11-22:

- [Create video](https://developers.heygen.com/reference/create-video.md): `POST /v3/videos`, header `x-api-key`, body `type: "avatar"`, `avatar_id`, `script`, `voice_id`, `voice_settings.speed` (0.5 to 1.5), `background` (`type: "color"`, `value`), `resolution`, `aspect_ratio`; reply `data.video_id`.
- [Get video](https://developers.heygen.com/reference/get-video.md): `GET /v3/videos/{video_id}`; `data.status` is `pending`, `processing`, `completed` or `failed`; `data.video_url` is a presigned download URL; `data.failure_code` and `data.failure_message` on failure.
- [Endpoint version comparison](https://developers.heygen.com/endpoint-version-comparison.md): the v2 generate and v1 status calls are legacy, with a sunset of 31 October 2026. v3 is the supported API.

## What is not proven

- **Not run against a real HeyGen account.** The tests use a local fake server built from the shapes above.
- Not used, because not needed: `title`, `folder_id`, `fit`, `remove_background`, callbacks, `output_upload`, `watermark`, `caption`, `output_format`, `engine`, `motion_prompt`, audio inputs. The page's JSON field text was read through a summary, not copied word for word, so check `background` and `voice_settings` against the live page before the first paid run.
- The script length cap (`--max-chars`, default 5000) is this block's own limit. The page sets no maximum for avatar scripts.
- The `video_url` is presigned and short-lived. Download soon after completion.
- The block does not check that a resolution is allowed for an aspect ratio. A combination the provider refuses comes back as a provider error.
- Not tested on Windows.
- The key is removed from server text in its plain form only. If a server echoed the key in another encoding (for example base64), that form would not be recognised and would be printed.
- Host checks look at the written address only. Number forms, `localhost`, IPv6 literals and private ranges are refused, but a public name that resolves to a private address is not caught. This affects only the video download, which carries no key.
