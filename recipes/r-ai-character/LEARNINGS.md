# r-ai-character learnings

Lessons a new user can apply. Add a dated line when a run teaches something.

- Pass the reference image to every scene call. A scene made without it drifts.
- Reference images go to the provider as an uploaded file, never as base64 text. `b-kie-ai` does the upload; do not hand-write the call.
- Use the image-to-image model for scenes. A text-to-image model does not keep a character's identity from a picture.
- A scene that fails the drift check is regenerated on purpose. It is a new call, not a retry of a failed one.
- Answer the look questions by really looking at the scene next to the reference. Answer no when unsure.
