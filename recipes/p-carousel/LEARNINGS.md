# Lessons

- Render at 2x, then downscale to the exact canvas (1080x1350). Rendering directly at 1x gives soft text. The exact-size check fails on a raw 2x image, so keep the 2x copies in a separate folder.
- Pin the Playwright package version. A newer package asks for a different Chromium revision, and the launch fails with "Executable doesn't exist".
- `template.html` fetches web fonts over the network. On a machine with no outbound access the render falls back to system fonts. Bundle `@font-face` files with the order if that matters.
- The outline and the caption steps can wait for a person. If nobody can answer, put the full outline and the caption choice into the order up front.
