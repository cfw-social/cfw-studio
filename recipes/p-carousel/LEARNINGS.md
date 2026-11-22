# Lessons

- Render at 2x, then downscale to the exact canvas (1080x1350). Rendering directly at 1x gives soft text. The exact-size check fails on a raw 2x image, so keep the 2x copies in a separate folder.
- Pin the Playwright package version. A newer package asks for a different Chromium revision, and the launch fails with "Executable doesn't exist".
- `template.html` fetches web fonts over the network. With the font hosts blocked, the render still finishes and the text uses system fonts (checked on 2026-11-22 with Playwright 1.64.1: sans-serif text, monospace labels). Bundle `@font-face` files with the order if the exact brand fonts matter.
- The outline and the caption steps can wait for a person. If nobody can answer, put the full outline and the caption choice into the order up front.
