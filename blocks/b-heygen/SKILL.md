# b-heygen

Use when a recipe needs a narrated avatar video from HeyGen. Needs the brand's own HeyGen key, an avatar id and a voice id, all supplied by the order or the person. Uses HeyGen v3. Not proven with a real account.

1. Write the narration to a text file inside the work folder.
2. Run, with the key set for this one process only:
   `HEYGEN_API_KEY=<key> python3 <blocks>/b-heygen/scripts/render.py --script narration.txt --avatar-id <id> --voice-id <id> --out avatar.mp4`
   Or pass the key on standard input with `--key-stdin`.
3. Read the `VIDEO_FILE:` line. The default background is green `#00FF00` for keying.

Rules:
- Never put the key on the command line, in a file, in a log or in your reply.
- Never invent or reuse an avatar or voice id. Ask the person.
- Exit 3 means no key: tell the person HeyGen is not connected. Exit 1 on a failed render or timeout: report it and stop.
- Do not submit the same render again. A rerun with the same `--out` resumes the first one. A second submit is charged.
- Check the video is the right length and has audio before using it.

Full interface and limits: README.md.
