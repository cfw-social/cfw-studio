# Write the post captions

Read the shared rules, `prior/slide_copy.json`, `prior/slides.json`, the
optional `inputs/cta/cta.md` and `brief.json`. Use only claims and
numbers that appear in the checked slides. The typed CTA wins over `brand.cta`. Never invent a handle.

Write `saves/captions.json`: one object keyed by each lower-case target platform
plus `default`. Each value is a nonempty caption. With no targets, still write
default. The hook matches the cover, the body teases the useful points, and the
CTA follows the request. Use the brand voice and plain words.

Run `captions_per_target` with the bot's JSON tools. Parse the object,
check all required keys and nonblank values, and enforce limits: twitter 280,
threads 500, instagram 2200, linkedin/default/other 3000 characters. Twitter has
no hashtags; Threads has at most two. Store actual check evidence.

This step saves captions only. The final carousel media is the ordered real images
from render_slides, using `prior/slides.json.count`. Never use padded slots, the
cover or the contact sheet as the media. Hand the results over by following CFW
Social's bot guide. Do not approve, schedule or publish them.
This step has no input ask. Invalid earlier data or a failed check stops work.
