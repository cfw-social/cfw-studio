"""Catalog checks for the checked-in effects.

Every registered fx effect has one e-* folder (a standalone effect, with
`engine: standalone`, has its own script and sample instead of an fx name), the README lists it, and the
tree contains no private brand media links.
"""
import os
import re
from pathlib import Path

import fx

EFFECTS = Path(__file__).resolve().parents[1]
REPO = EFFECTS.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "cache"}


def _needle(*parts: str) -> bytes:
    return "".join(parts).encode()


# Split so this file does not itself contain the private host or brand id.
NEEDLES = (
    _needle("cmpda", "8nmp"),
    _needle("media.", "cfw.social"),
)


def _top_level(text: str) -> dict:
    data = {}
    for line in text.splitlines():
        if not line or line[0] in " \t-#":
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data


def _entries():
    return sorted(p for p in EFFECTS.iterdir() if p.is_dir() and p.name.startswith("e-"))


def test_every_effect_has_a_catalog_entry():
    registered = fx.list_effects()
    by_fx = {}
    for folder in _entries():
        manifest = _top_level((folder / "effect.yaml").read_text())
        assert manifest["id"] == folder.name
        assert manifest["kind"] == "effect"
        assert manifest["variation"] == "default"
        if manifest.get("engine") == "standalone":
            # A standalone effect has its own script and sample and is not in the fx registry.
            assert "fx_name" not in manifest, folder.name
            for rel in ("SKILL.md", "PREVIEW.md", "scripts/README.md"):
                assert (folder / rel).is_file(), (folder.name, rel)
            scripts = [p for p in (folder / "scripts").glob("*.py")]
            assert scripts, folder.name
            sample = re.search(r"\]\((\.\./examples/samples/[^)]+\.mp4)\)", (folder / "PREVIEW.md").read_text())
            assert sample, folder.name
            assert (folder / sample.group(1)).is_file(), (folder.name, sample.group(1))
            continue
        fx_name = manifest["fx_name"]
        assert fx_name in registered, fx_name
        assert fx_name not in by_fx
        by_fx[fx_name] = folder
        for rel in ("SKILL.md", "PREVIEW.md", "scripts/README.md"):
            assert (folder / rel).is_file(), (folder.name, rel)
        sample = "_grid.mp4" if fx_name == "grid_collage" else f"{fx_name}.mp4"
        preview = (folder / "PREVIEW.md").read_text()
        assert f"../examples/samples/{sample}" in preview
        assert (EFFECTS / "examples" / "samples" / sample).is_file()
        skill = (folder / "SKILL.md").read_text()
        assert f"--effect {fx_name}" in skill
        assert "python -m fx apply" in skill
    assert set(by_fx) == set(registered)


def test_readme_lists_every_entry():
    readme = (EFFECTS / "README.md").read_text()
    for folder in _entries():
        assert f"]({folder.name}/)" in readme


def test_fx_package_lives_under_effects():
    assert Path(fx.__file__).resolve().parent == (EFFECTS / "fx").resolve()


def test_effects_library_license_marker():
    pyproject = (EFFECTS / "pyproject.toml").read_text()
    assert 'license = "MIT"' in pyproject
    assert (EFFECTS / "LICENSE").is_file()
    readme = (EFFECTS / "README.md").read_text()
    assert "MIT License" in readme


def test_no_private_brand_media_links():
    hits = []
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                data = path.read_bytes()
            except OSError:
                continue
            for needle in NEEDLES:
                if needle in data:
                    hits.append(f"{path}: {needle.decode()}")
    assert hits == []
