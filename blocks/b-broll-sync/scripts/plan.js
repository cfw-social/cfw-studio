#!/usr/bin/env node
/**
 * b-broll-sync/scripts/plan.js
 *
 * Turns a checked scene plan into a gapless beat list. It decides nothing
 * about which clip goes with which words: the bot does that by writing `broll`
 * scenes in the scene plan. This script only checks, places and tiles.
 *
 *   node plan.js --transcript WORDS.json --bed-dur S --scene-plan PLAN.json --out BEATS.json
 *        [--broll CUES.json] [--inputs-dir inputs] [--brand BRAND.json]
 *        [--coverage 30] [--clip-secs 5] [--min-secs 4] [--max-secs 6]
 *        [--order as-given|even] [--reuse true|false]
 *        [--min-card-secs 1.0] [--allow-empty-copy]
 *
 * Exit 0 written. 1 the plan or the data is invalid (blank card, unknown clip,
 * bad plan). 2 usage error, unknown option, unknown ordering, or a path that
 * is unreadable or outside the allowed folder. Nothing is written on 1 or 2.
 *
 * No network. Starts no other program. Reads only the files named on the command
 * line. Every input must resolve inside the current folder (the work folder),
 * and every clip must resolve inside --inputs-dir (default `inputs`).
 */

'use strict';

const path = require('path');
const safe = require('./safe-path');
const inputs = require('./inputs');
const { validateScenePlan, resolveAnchors } = require('./validate-scene-plan');

const VALUE_OPTIONS = new Set([
  'transcript', 'broll', 'inputs-dir', 'coverage', 'clip-secs', 'min-secs', 'max-secs',
  'order', 'reuse', 'bed-dur', 'brand', 'out', 'scene-plan', 'min-card-secs',
]);
const FLAG_OPTIONS = new Set(['allow-empty-copy']);
const readInputs = new Set();   // real paths of every file read, so the output can never be one of them
const ORDERS = new Set(['as-given', 'even']);

class UsageError extends inputs.InputError {}
class DataError extends inputs.DataError {}

// ---- arguments --------------------------------------------------------------

function parseArgs(argv) {
  const raw = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) throw new UsageError(`unexpected argument "${a}"`);
    const key = a.slice(2);
    if (FLAG_OPTIONS.has(key)) { raw[key] = true; continue; }
    if (!VALUE_OPTIONS.has(key)) throw new UsageError(`unknown option ${a}`);
    if (i + 1 >= argv.length) throw new UsageError(`${a} needs a value`);
    raw[key] = argv[++i];
  }
  return raw;
}

function num(raw, key, def, { min, max, exclusiveMin = false } = {}) {
  if (raw[key] === undefined) return def;
  const v = inputs.plainNumber(raw[key]);
  if (!Number.isFinite(v) || (min !== undefined && (exclusiveMin ? v <= min : v < min)) || (max !== undefined && v > max)) {
    throw new UsageError(`--${key} must be a plain decimal number${min !== undefined ? ` ${exclusiveMin ? '>' : '>='} ${min}` : ''}${max !== undefined ? ` and <= ${max}` : ''} (got "${raw[key]}")`);
  }
  return v;
}

function options(raw) {
  const order = raw.order ?? 'as-given';
  if (!ORDERS.has(order)) {
    throw new UsageError(`--order must be as-given or even (got "${order}")`);
  }
  if (raw.reuse !== undefined && raw.reuse !== 'true' && raw.reuse !== 'false') throw new UsageError(`--reuse must be true or false (got "${raw.reuse}")`);
  if (!raw.transcript) throw new UsageError('--transcript is required');
  const o = {
    transcript: raw.transcript,
    broll: raw.broll || null,
    inputsDir: raw['inputs-dir'] || 'inputs',
    brand: raw.brand || null,
    scenePlan: raw['scene-plan'] || null,
    out: raw.out || 'beat_list.json',
    coverage: num(raw, 'coverage', 30, { min: 0, max: 100 }),
    clipSecs: num(raw, 'clip-secs', 5, { min: 0, exclusiveMin: true }),
    minSecs: num(raw, 'min-secs', 4, { min: 0, exclusiveMin: true }),
    maxSecs: num(raw, 'max-secs', 6, { min: 0, exclusiveMin: true }),
    bedDur: num(raw, 'bed-dur', null, { min: 0, exclusiveMin: true }),
    minCardSecs: num(raw, 'min-card-secs', 1.0, { min: 0 }),
    order,
    reuse: raw.reuse === 'true',
    allowEmptyCopy: raw['allow-empty-copy'] === true,
  };
  if (o.minSecs > o.maxSecs) throw new UsageError('--min-secs must not be larger than --max-secs');
  return o;
}

// ---- inputs -----------------------------------------------------------------

function readJson(root, p, what) {
  const { value, real } = inputs.readJsonFile(root, p, what);   // regular file, size cap, unsafe keys dropped
  readInputs.add(real);
  return value;
}

function loadWords(raw) { return inputs.checkWords(raw); }

/**
 * Load the b-roll cue list. Every clip path must be a real file inside the
 * inputs folder, which itself must be inside the work folder. Anything else
 * (absolute path elsewhere, `..`, a symbolic link pointing outside) is refused.
 * Clip paths in the output are relative to the work folder.
 */
function loadClips(root, raw, inputsDir) {
  if (!Array.isArray(raw)) throw new DataError('--broll must be a JSON array of {clip,duration,cues}');
  if (raw.length > 500) throw new DataError('--broll lists more than 500 clips');
  if (raw.length === 0) return [];
  let inputsReal;
  try { inputsReal = safe.resolveExisting(root, inputsDir, '--inputs-dir'); } catch (e) { throw new UsageError(e.message); }
  return raw.map((c, i) => {
    if (!inputs.isObj(c) || typeof c.clip !== 'string' || !c.clip.trim() || c.clip.length > 300) throw new DataError(`broll entry ${i} needs a clip path (text, at most 300 characters)`);
    if (c.duration !== undefined && !(typeof c.duration === 'number' && Number.isFinite(c.duration) && c.duration > 0)) throw new DataError(`broll entry ${i}: duration must be a positive number`);
    if (c.label !== undefined && (typeof c.label !== 'string' || c.label.length > 100)) throw new DataError(`broll entry ${i}: label must be text of at most 100 characters`);
    if (c.cues !== undefined) {
      if (!Array.isArray(c.cues)) throw new DataError(`broll entry ${i}: cues must be a list`);
      c.cues.forEach((cue, j) => {
        if (!inputs.isObj(cue) || typeof cue.text !== 'string' || cue.text.length > inputs.MAX_STRING
          || typeof cue.start !== 'number' || typeof cue.end !== 'number' || !Number.isFinite(cue.start) || !Number.isFinite(cue.end)) {
          throw new DataError(`broll entry ${i}: cue ${j} needs text (at most ${inputs.MAX_STRING} characters), start and end numbers`);
        }
      });
    }
    let real;
    try { real = safe.resolveExisting(inputsReal, c.clip, `clip ${i}`); } catch (e) {
      throw new UsageError(`${e.message} (clips must be files inside ${path.relative(root, inputsReal) || '.'}/)`);
    }
    inputs.regularFile(inputsReal, c.clip, `clip ${i}`);
    readInputs.add(real);
    const rel = path.relative(root, real).split(path.sep).join('/');
    return { ...c, clip: rel };
  });
}

// ---- placement --------------------------------------------------------------

/**
 * Windows of b-roll spaced evenly over the bed. Which clips fill them depends on the order:
 *   as-given  the first clips in the listed order (the listed order is kept)
 *   even      clips picked evenly across the whole list, so a long list is represented end to end
 * When there are at least as many slots as clips (or reuse is on) both cycle through the list.
 * Returns [{clipIndex, beatStart, beatEnd, in, out}].
 */
function pickClip(order, i, slots, n) {
  if (order === 'even' && slots < n) return Math.floor(((i + 0.5) * n) / slots);
  return i % n;
}

function placeSpread(clips, slots, windowSecs, o, bed, warn) {
  const placements = [];
  if (clips.length === 0 || slots === 0) return placements;
  const spacing = bed / (slots + 1);
  for (let i = 0; i < slots; i++) {
    const idx = pickClip(o.order, i, slots, clips.length);
    const clip = clips[idx];
    const clipDur = clip.duration || (windowSecs + 1);
    const len = Math.min(Math.max(windowSecs, o.minSecs), Math.min(o.maxSecs, clipDur));
    if (len < o.minSecs - 1e-9) warn(`clip "${clip.clip}" is ${clipDur} s long, shorter than --min-secs ${o.minSecs}; its window is only ${len.toFixed(2)} s`);
    const start = Math.max(0, spacing * (i + 1) - len / 2);
    const end = Math.min(bed, start + len);
    placements.push({ clipIndex: idx, beatStart: start, beatEnd: end, in: 0, out: end - start });
  }
  return placements;
}

/** The plan's `asset` must name a clip from --broll: exact path, base name or label. */
function resolveClipIndex(clips, asset) {
  const a = String(asset).trim();
  let i = clips.findIndex((c) => c.clip === a || c.label === a);
  if (i >= 0) return i;
  i = clips.findIndex((c) => path.basename(c.clip) === path.basename(a));
  return i;
}

function placeFromPlan(clips, planBroll, warn) {
  return planBroll.map((sc) => {
    const idx = resolveClipIndex(clips, sc.asset);
    if (idx < 0) {
      throw new DataError(`broll scene "${sc.id || sc.asset}": asset "${sc.asset}" matches no clip in --broll (by path, base name or label)`);
    }
    const clipDur = clips[idx].duration || Infinity;
    const inPt = Math.max(0, Number(sc.in ?? 0));
    const outPt = Math.min(inPt + (sc.end - sc.start), clipDur);
    if (outPt <= inPt) throw new DataError(`broll scene "${sc.id || sc.asset}": "in" ${inPt} is past the end of the clip (${clipDur} s)`);
    const want = sc.end - sc.start;
    if (outPt - inPt < want - 0.01) {
      warn(`broll scene "${sc.id || sc.asset}": the clip has ${(outPt - inPt).toFixed(2)} s after "in" ${inPt} but the scene is ${want.toFixed(2)} s; the beat was shortened to ${sc.start}-${r3(sc.start + outPt - inPt)} s. The next card is stretched back to cover the rest. Use a longer clip or shorten the scene if that is not wanted`);
    }
    return { clipIndex: idx, beatStart: sc.start, beatEnd: sc.start + (outPt - inPt), in: inPt, out: outPt, matchReason: 'placed by scene_plan' };
  });
}

// ---- beat list --------------------------------------------------------------

const r3 = (n) => parseFloat(n.toFixed(3));

function blankGraphics(index, start, end, brand) {
  return { index, start: r3(start), end: r3(end), kind: 'graphics', scene: { eyebrow: '', ghost: '', title_html: '', brand } };
}

/** Fill the time around b-roll windows with graphics beats. Gapless, sorted. */
function buildBeatList(placements, clips, bed, brand) {
  const sorted = [...placements].sort((a, b) => a.beatStart - b.beatStart);
  const kept = [];
  let cursor = 0;
  for (const p of sorted) {
    if (p.beatStart >= cursor - 0.01) { kept.push(p); cursor = p.beatEnd; }
  }
  const beats = [];
  let t = 0;
  for (const p of kept) {
    if (p.beatStart > t + 0.05) beats.push(blankGraphics(beats.length, t, p.beatStart, brand));
    beats.push({
      index: beats.length, start: r3(p.beatStart), end: r3(p.beatEnd), kind: 'broll',
      broll: { clip: clips[p.clipIndex].clip, in: r3(p.in), out: r3(p.out), match_score: 1.0, match_reason: p.matchReason ?? '' },
    });
    t = p.beatEnd;
  }
  if (t < bed - 0.05) beats.push(blankGraphics(beats.length, t, bed, brand));
  return beats;
}

const PLAN_ONLY_KEYS = new Set(['start', 'end', 'start_phrase', 'end_phrase', 'kind', 'headline', 'asset', 'in', 'cover']);

function sceneToGraphics(sc, start, end, brand) {
  const extra = {};
  for (const [k, v] of Object.entries(sc)) if (!PLAN_ONLY_KEYS.has(k)) extra[k] = v;
  return {
    start: r3(start), end: r3(end), kind: 'graphics',
    scene: { ...extra, eyebrow: sc.eyebrow ?? '', ghost: sc.ghost ?? '', title_html: sc.headline, sub: sc.sub ?? '', type: sc.type ?? 'standard', scene_id: sc.id ?? null, source: 'scene_plan', brand },
  };
}

/** Split each graphics window by the plan's graphic and avatar scenes and attach their copy. */
function applyScenePlan(beats, plan, minCardSecs, brand) {
  const cards = plan.scenes.filter((sc) => sc.kind === 'graphic' || sc.kind === 'avatar').sort((x, y) => x.start - y.start);
  const out = [];
  for (const b of beats) {
    if (b.kind !== 'graphics') { out.push(b); continue; }
    const frags = [];
    for (const sc of cards) {
      const s = Math.max(sc.start, b.start), e = Math.min(sc.end, b.end);
      if (e - s > 0.01) frags.push({ sc, s, e });
    }
    if (frags.length === 0) throw new DataError(`no graphic scene in the plan covers the window ${b.start.toFixed(2)}-${b.end.toFixed(2)} s; add a card for it`);
    // A fragment shorter than the minimum joins a neighbour (the previous one first).
    for (let i = 0; i < frags.length; i++) {
      if (frags[i].e - frags[i].s >= minCardSecs || frags.length === 1) continue;
      if (i > 0) { frags[i - 1].e = frags[i].e; frags.splice(i, 1); i--; }
      else { frags[i + 1].s = frags[i].s; frags.splice(i, 1); i--; }
    }
    frags[0].s = b.start;
    frags[frags.length - 1].e = b.end;
    for (const f of frags) {
      if (f.sc.kind === 'avatar') {
        out.push({ start: r3(f.s), end: r3(f.e), kind: 'avatar', avatar: { asset: f.sc.asset ?? null, scene_id: f.sc.id ?? null, source: 'scene_plan' } });
      } else out.push(sceneToGraphics(f.sc, f.s, f.e, brand));
    }
  }
  return out;
}

/** A moment past the opening, away from b-roll, for the cover frame. */
function pickCoverAt(beats, dur) {
  const firstGfx = beats.find((b, i) => b.kind === 'graphics' && i > 0 && b.start >= 1.5);
  let t;
  if (firstGfx) t = firstGfx.start + (firstGfx.end - firstGfx.start) / 2;
  else if (beats.length > 1) t = beats[1].start + (beats[1].end - beats[1].start) / 2;
  else t = dur * 0.35;
  const inBroll = beats.find((b) => b.kind === 'broll' && t >= b.start && t < b.end);
  if (inBroll) {
    const after = beats.find((b) => b.kind === 'graphics' && b.start >= inBroll.end);
    if (after) t = after.start + Math.min(1.0, (after.end - after.start) / 2);
  }
  return r3(Math.min(Math.max(t, 2.0), Math.max(0, dur - 0.1)));
}

// ---- main -------------------------------------------------------------------

function run(argv) {
  const o = options(parseArgs(argv));
  const root = safe.workRoot();
  let outPath;
  try { outPath = safe.resolveForWrite(root, o.out, '--out'); } catch (e) { throw new UsageError(e.message); }

  const words = loadWords(readJson(root, o.transcript, 'transcript'));
  const clips = o.broll ? loadClips(root, readJson(root, o.broll, '--broll'), o.inputsDir) : [];
  let brand = {};
  if (o.brand) {
    brand = readJson(root, o.brand, '--brand');
    if (!inputs.isObj(brand)) throw new DataError('--brand must be a JSON object');
    inputs.checkPlain(brand, '--brand');
  }
  const bed = o.bedDur || words[words.length - 1].end;

  let plan = null;
  const planWarnings = [];
  if (o.scenePlan) {
    const rawPlan = readJson(root, o.scenePlan, '--scene-plan');
    if (rawPlan && typeof rawPlan === 'object' && !Array.isArray(rawPlan) && !Number.isFinite(rawPlan.bed_duration)) rawPlan.bed_duration = bed;
    const resolved = resolveAnchors(rawPlan && typeof rawPlan === 'object' ? rawPlan : {}, words);
    const verdict = validateScenePlan(Array.isArray(rawPlan) ? rawPlan : resolved.plan, { bedDuration: bed });
    for (const w of verdict.warnings) console.warn(`[b-broll-sync] scene plan WARN: ${w}`);
    planWarnings.push(...verdict.warnings);
    const errs = [...resolved.errors, ...verdict.errors];
    if (errs.length) throw new DataError(`scene plan invalid (${errs.length} error(s)):\n  ${errs.join('\n  ')}\nFix ${o.scenePlan}; blank cards are never written.`);
    plan = resolved.plan;
    console.log(`[b-broll-sync] scene plan: ${plan.scenes.length} scenes loaded`);
  }

  const warnings = [];
  const warn = (m) => { warnings.push(m); console.warn(`[b-broll-sync] WARN: ${m}`); };

  // Budget, worked out here and nowhere else.
  const budget = (o.coverage / 100) * bed;
  const windowSecs = Math.min(Math.max(o.clipSecs, o.minSecs), o.maxSecs);
  const maxWindows = Math.floor(budget / windowSecs);
  const slots = o.reuse ? maxWindows : Math.min(maxWindows, clips.length);
  let shortfallNote = null;
  if (!o.reuse && clips.length > 0 && clips.length < maxWindows) {
    const pct = ((clips.length * windowSecs) / bed * 100).toFixed(1);
    shortfallNote = `requested ${o.coverage}%, achieved ${pct}%: only ${clips.length} clip${clips.length !== 1 ? 's' : ''}, no reuse`;
    console.warn(`[b-broll-sync] shortfall: ${shortfallNote}`);
  }
  if (clips.length > 0 && maxWindows === 0 && !(plan && plan.scenes.some((sc) => sc.kind === 'broll'))) {
    shortfallNote = `the bed (${bed} s) at ${o.coverage}% leaves ${budget.toFixed(2)} s, less than one ${windowSecs} s window; no b-roll was placed`;
    console.warn(`[b-broll-sync] shortfall: ${shortfallNote}`);
  }
  if (clips.length === 0) console.log('[b-broll-sync] no b-roll supplied: 100% graphics (valid)');

  const planBroll = plan ? plan.scenes.filter((sc) => sc.kind === 'broll') : [];
  let placements;
  if (planBroll.length > 0) {
    console.log(`[b-broll-sync] plan carries ${planBroll.length} broll scene(s): using them as the placements (--order ignored)`);
    placements = placeFromPlan(clips, planBroll, warn);
  } else {
    placements = placeSpread(clips, slots, windowSecs, o, bed, warn);
  }

  let beats = buildBeatList(placements, clips, bed, brand);
  if (plan) beats = applyScenePlan(beats, plan, o.minCardSecs, brand);
  beats.forEach((b, i) => {
    b.index = i;
    if (b.kind === 'graphics' && !b.slug) {
      const id = b.scene && b.scene.scene_id ? String(b.scene.scene_id) : '';
      const safeId = id.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
      b.slug = safeId ? `beat${i}-${safeId}` : `beat${i}`;
    }
  });

  const blank = beats.filter((b) => b.kind === 'graphics' && !String((b.scene || {}).title_html || '').replace(/<[^>]*>/g, '').trim());
  if (blank.length > 0 && !o.allowEmptyCopy) {
    const where = blank.map((b) => `beat ${b.index} (${b.start.toFixed(2)}-${b.end.toFixed(2)} s)`).join(', ');
    throw new DataError(`${blank.length} graphics beat(s) have no copy: ${where}. Supply --scene-plan so every card has copy. (--allow-empty-copy writes them blank; the bot must then author the copy before any render.)`);
  }
  if (blank.length > 0) console.warn(`[b-broll-sync] WARN: ${blank.length} graphics beat(s) written with EMPTY copy (--allow-empty-copy)`);

  // The list must be gapless and cover the bed.
  let prevEnd = 0;
  for (const b of beats) {
    if (Math.abs(b.start - prevEnd) > 0.11) throw new DataError(`beat ${b.index} starts at ${b.start} but the previous beat ended at ${prevEnd.toFixed(3)}`);
    prevEnd = b.end;
  }
  if (Math.abs(prevEnd - bed) > 0.2) throw new DataError(`beats end at ${prevEnd.toFixed(3)} but bed_duration is ${bed}`);

  const brollSecs = beats.filter((b) => b.kind === 'broll').reduce((s, b) => s + (b.end - b.start), 0);
  const achieved = parseFloat(((brollSecs / bed) * 100).toFixed(1));
  let coverAt = pickCoverAt(beats, bed);
  if (plan) {
    const flagged = plan.scenes.find((sc) => sc.cover === true);
    if (flagged) coverAt = r3(flagged.start + Math.min((flagged.end - flagged.start) / 2, 2.0));
  }

  const output = {
    bed_duration: r3(bed),
    achieved_broll_pct: achieved,
    cover_at: coverAt,
    shortfall_note: shortfallNote,
    warnings: [...planWarnings, ...warnings],
    params: {
      broll_coverage_pct: o.coverage, broll_clip_seconds: o.clipSecs, broll_min_seconds: o.minSecs,
      broll_max_seconds: o.maxSecs, broll_order: o.order, broll_reuse: o.reuse,
      scene_plan: o.scenePlan ? path.basename(o.scenePlan) : null,
    },
    beats,
  };
  try { safe.writeSafely(root, outPath, JSON.stringify(output, null, 2), [...readInputs]); } catch (e) { throw new UsageError(e.message); }
  console.log(`[b-broll-sync] done: ${beats.length} beats, ${achieved}% b-roll (${brollSecs.toFixed(1)}s / ${bed}s), wrote ${o.out}`);
  return 0;
}

if (require.main === module) {
  try {
    process.exit(run(process.argv.slice(2)));
  } catch (e) {
    if (e instanceof inputs.InputError) { console.error(`[b-broll-sync] ERROR: ${e.message}`); process.exit(2); }
    if (e instanceof inputs.DataError) { console.error(`[b-broll-sync] ERROR: ${e.message}`); process.exit(1); }
    console.error('[b-broll-sync] ERROR: unexpected failure; nothing was written. Check the arguments and files, then try again.');
    process.exit(1);
  }
}

module.exports = { run, parseArgs, options, placeSpread, buildBeatList, applyScenePlan };
