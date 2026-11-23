# Outline the slides

Read the shared rules. Read `inputs/topic/topic.md`, `brief.json` and the
optional slide-count input with the bot's file tools. Use 5 slides when
the count is absent. Only 3, 5, 7 and 10 are supported. Do not use shell expansion.

Write `saves/outline.json`:
```json
{"topic":"request topic","num_slides":5,"slides":[{"n":1,"role":"cover","headline":"Short hook","angle":"Promise"},{"n":2,"role":"content","headline":"One point","angle":"Useful detail"}]}
```
The example is abbreviated; write exactly N entries numbered 1 through N.
The first role is cover, last closing, and all middle roles content. Each
headline has one to eight words. Each angle says what that card adds. Keep the
claim and audience faithful to the request; do not invent facts or statistics.
Use `brand.cta` for the closing card unless a typed order CTA wins.

Run `outline_shape` with the bot's JSON tools: parse the file, compare
the chosen count, consecutive numbers, roles and nonempty headlines. Save the
actual result as evidence. A parse/count/role failure blocks completion.

If the topic is missing or unusable, ask for the `topic` input only (see
"Claiming and reporting" in the shared rules) and stop. A missing optional slide
count is not a question. If the order asks for an outline review, report the
checked outline and wait for a person to approve it. Never approve it yourself.
