# b-audio

Use when a recipe needs the words of a recording with start and end times.

1. Put the audio or video inside the work folder. Run from that folder.
2. Pick the one installed tool (`whisper-cpp`) and read its version from your package manager.
3. Run `python3 <blocks>/b-audio/scripts/transcribe.py INPUT --out words.json --tool whisper-cpp --tool-version <v> --model <model file>`.
4. Read `words.json`: `[{"text","start","end"}]`, seconds. Read `words.meta.json` for the tool, version and model checksum.

Rules:
- Exit 3 means something is missing. Tell the person what to install. Do not try another tool.
- Do not download a model unless the person says yes. Then add `--allow-download --model-name <name> --model-sha256 <checksum>`, and the model path must be inside the work folder.
- Never point `--model` at a place the person did not name. Use `--allow-model-dir` for a model folder they named.
- To help spell names and product words, put them in a text file in the work folder and pass `--hint-file`. Keep the hint to a short list of names and unusual words, never the whole script. Reason: a hint holding a whole script (about 74 words of full sentences) made the transcriber stop after 4 words, while a short list of the script's names and unusual words gave all 74 words (seen once, with whisper.cpp 1.8.4 and the base English model).
- An empty list means no speech was found. Report it.

Full interface: README.md.
