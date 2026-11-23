#!/usr/bin/env bash
# Static checks on this recipe's own files and on the block files it calls. No render, no network.
# Usage: bash scripts/verify-skill.sh
# The blocks are found at ../../blocks/ relative to this recipe (the layout of this repository).
set -uo pipefail

RECIPE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BLOCKS="$RECIPE_DIR/../../blocks"
PASS=0; FAIL=0

pass() { echo "  PASS  $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }
check() { local label="$1"; shift; if "$@" >/dev/null 2>&1; then pass "$label"; else fail "$label"; fi; }

echo "=== r-reels-pip-heygen static checks ==="

check "SKILL.md has the recipe name"     grep -q "^name: r-reels-pip-heygen" "$RECIPE_DIR/SKILL.md"
check "manifest.json parses"             python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$RECIPE_DIR/manifest.json"
check "acceptance.json parses"           python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$RECIPE_DIR/acceptance.json"
for f in _shared 00-generate-avatar 01-prepare-footage 02-transcribe 03-plan-beats 04-build-background 05-composite 06-final-checks; do
  check "steps/$f.md exists"             test -f "$RECIPE_DIR/steps/$f.md"
done

# The two page templates reserve the card's band and keep order text out of the page.
T="$RECIPE_DIR/templates/motion-card.html"
check "motion card reserves the band"      grep -q "bottom: var(--pip-band)" "$T"
check "motion card declares its fonts"     grep -q '@font-face { font-family: "Oswald"' "$T"
check "motion card has no remote address"  bash -c "! grep -qiE 'https?://|//cdn|url\\(' '$T'"
check "motion card has no random or clock" bash -c "! grep -qE 'Math.random|Date.now|requestAnimationFrame' '$T'"
check "end card declares its fonts"        grep -q '@font-face { font-family: "Oswald"' "$RECIPE_DIR/templates/cta-card.html"

# Guard rails the steps must keep.
S="$RECIPE_DIR/steps"
check "bed loudness once (step 1)"         grep -q "loudnorm=I=-14" "$S/01-prepare-footage.md"
check "no later step normalises loudness"  bash -c "! grep -l 'loudnorm' '$S'/0[2-6]*.md"
check "SFX are mixed under the voice"      grep -q "normalize=0" "$S/05-composite.md"
check "cover freeze (step 6)"              grep -q "cover-freeze" "$S/06-final-checks.md"
check "captions stay above the card"       grep -q "CAP_TOP=980" "$S/05-composite.md"
check "renders go through b-hyperframes"   bash -c "! grep -rqE 'npx +hyperframes' '$S'"
check "no step starts an agent"            bash -c "! grep -rqE 'dangerously|claude --print|codex exec' '$S'"
check "no eval in a step"                  bash -c "! grep -rqE '^eval |bash -c' '$S'"
check "step 6 delivers only after the delivery check" grep -q "check_delivery.py" "$S/06-final-checks.md"
check "no option list is an unquoted text string" bash -c "! grep -rhE '\\\$\\{?[A-Za-z_]*(ARGS|OPTS|FLAGS)' '$S' | grep -vE '\"\\\$\\{[A-Za-z_]+\\[@\\]\\}\"' | grep -vE '^\`|are arrays'"
check "RECIPE_DIR is checked to be absolute" bash -c "grep -q 'must be an absolute path' '$S/05-composite.md'"
check "the end card window is kept plain" grep -q "check_scene_plan.py" "$S/03-plan-beats.md"
check "the key is never on a command line" bash -c "! grep -rqE '(-key|--api-key)[ =]' '$S'"
check "the avatar render record is saved" grep -q "avatar_render.json" "$S/00-generate-avatar.md"
check "the end card is a .mov with alpha"  grep -q -- "--format mov" "$S/05-composite.md"

# The block files the steps call.
for p in b-heygen/scripts/render.py b-audio/scripts/transcribe.py b-broll-sync/scripts/plan.js b-broll-sync/scripts/validate-scene-plan.js \
         b-typing-ui/scripts/typing_fill.py b-typing-ui/scripts/hook_fill.py \
         b-hyperframes/scripts/hf_install.py b-hyperframes/scripts/fetch_gsap.py b-hyperframes/scripts/hf_render.py \
         b-hyperframes/scripts/check_local.py \
         b-reel-premium/scripts/check_plan.py b-reel-premium/scripts/build_comp.py b-reel-premium/scripts/mux.py \
         b-reel-premium/scripts/qa.py b-qa-gate/check.py; do
  check "block file $p"                    test -f "$BLOCKS/$p"
done

echo ""
echo "Results: ${PASS} pass, ${FAIL} fail"
[ "$FAIL" -eq 0 ] && echo "All checks passed." || { echo "Some checks failed."; exit 1; }
