#!/usr/bin/env node
/**
 * b-broll-sync/scripts/validate-scene-plan.js
 *
 * Checks a scene plan (see SCENE-PLAN.md, version 1). Node only, no packages.
 *
 *   node validate-scene-plan.js PLAN.json [--bed-dur S] [--transcript WORDS.json]
 *
 * Exit 0: valid (warnings may be printed). 1: the plan is invalid.
 * 2: usage error or an unreadable or out-of-folder file. Reads only the files
 * named on the command line, and each must resolve inside the current folder.
 * No network. Starts no other program.
 *
 * Also usable as a module: { validateScenePlan, resolveAnchors, findPhrase }.
 */

'use strict';

const fs = require('fs');
const safe = require('./safe-path');
const inputs = require('./inputs');

const KINDS = new Set(['graphic', 'broll', 'avatar']);

// Tolerances, in seconds.
const OVERLAP_TOL = 0.05;
const GAP_TOL = 0.25;
const END_TOL = 0.25;

// Copy limits: a 1080x1920 card cannot hold more.
const MAX_HEADLINE_CHARS = 90;
const MAX_EYEBROW_CHARS = 40;
const MAX_GHOST_CHARS = 4;
const MIN_GRAPHIC_SECS = 1.0;
const WARN_GRAPHIC_SECS = 8.0;
const MAX_GRAPHIC_SECS = 12.0;

// A headline may hold only these tags. Anything else is refused, so a plan
// can never put markup into a rendered card.
const ALLOWED_TAG_RE = /<\/?span(\s+class="accent")?\s*>|<br\s*\/?>/gi;

function headlineText(h) {
  return String(h ?? '').replace(ALLOWED_TAG_RE, '').replace(/\s+/g, ' ').trim();
}

function hasDisallowedTag(h) {
  const stripped = String(h ?? '').replace(ALLOWED_TAG_RE, '');
  return /[<>]/.test(stripped);
}

// Text fields of a scene, with their length caps. When present they must be strings.
const TEXT_CAPS = { id: 60, type: 30, eyebrow: MAX_EYEBROW_CHARS, ghost: MAX_GHOST_CHARS, sub: 200, headline: 400,
  asset: 300, start_phrase: 200, end_phrase: 200 };
const KNOWN_SCENE_KEYS = new Set(['kind', 'start', 'end', 'in', 'cover', ...Object.keys(TEXT_CAPS)]);

/** Balanced span tags: every <span class="accent"> has its </span>. */
function spansBalanced(h) {
  const open = (String(h).match(/<span\b/gi) || []).length;
  const close = (String(h).match(/<\/span\s*>/gi) || []).length;
  return open === close;
}

function isNum(v) { return typeof v === 'number' && Number.isFinite(v); }
function fmt(n) { return isNum(n) ? n.toFixed(2) : String(n); }

const HYPHENS = /[-‐-―]+/;

/**
 * Find the first run of transcript words that matches `phrase` (ignoring case
 * and punctuation; each plan word may be a prefix of the spoken word).
 * Returns { start, end } or null. If nothing matches, both sides are split at
 * hyphens and tried again, because speech tools split "four-part" their own way.
 */
function findPhrase(words, phrase) {
  const norm = (s) => String(s).toLowerCase().replace(/[^a-z0-9']+/g, '');
  const wordText = (w) => w.text ?? w.word ?? '';
  const ph = String(phrase).trim().split(/\s+/).map(norm).filter(Boolean);
  if (ph.length === 0) return null;
  for (let i = 0; i + ph.length <= words.length; i++) {
    let ok = true;
    for (let j = 0; j < ph.length; j++) {
      if (!norm(wordText(words[i + j])).startsWith(ph[j])) { ok = false; break; }
    }
    if (ok) return { start: parseFloat(words[i].start), end: parseFloat(words[i + ph.length - 1].end) };
  }
  const sub = String(phrase).trim().split(/\s+/).flatMap((t) => t.split(HYPHENS)).map(norm).filter(Boolean);
  if (sub.length === 0) return null;
  const toks = [];
  words.forEach((w, k) => {
    String(wordText(w)).split(HYPHENS).map(norm).filter(Boolean).forEach((t) => toks.push({ t, k }));
  });
  for (let i = 0; i + sub.length <= toks.length; i++) {
    let ok = true;
    for (let j = 0; j < sub.length; j++) {
      if (!toks[i + j].t.startsWith(sub[j])) { ok = false; break; }
    }
    if (ok) return { start: parseFloat(words[toks[i].k].start), end: parseFloat(words[toks[i + sub.length - 1].k].end) };
  }
  return null;
}

/**
 * Turn start_phrase / end_phrase into numbers using the word transcript.
 * Numbers already present win. Returns { plan, errors }; the input is not changed.
 */
function resolveAnchors(plan, words) {
  const errors = [];
  const out = JSON.parse(JSON.stringify(plan));
  const scenes = Array.isArray(out.scenes) ? out.scenes : [];
  scenes.forEach((s, i) => {
    if (!s || typeof s !== 'object') return;
    const label = `scene ${i}${s.id ? ` (${s.id})` : ''}`;
    if (!isNum(s.start) && typeof s.start_phrase === 'string') {
      if (!Array.isArray(words)) { errors.push(`${label}: start_phrase needs a transcript to resolve`); return; }
      const m = findPhrase(words, s.start_phrase);
      if (!m) errors.push(`${label}: start_phrase "${s.start_phrase}" not found in transcript`);
      else s.start = m.start;
    }
    if (!isNum(s.end) && typeof s.end_phrase === 'string') {
      if (!Array.isArray(words)) { errors.push(`${label}: end_phrase needs a transcript to resolve`); return; }
      const m = findPhrase(words, s.end_phrase);
      if (!m) errors.push(`${label}: end_phrase "${s.end_phrase}" not found in transcript`);
      else s.end = m.start; // end_phrase is the first word of the NEXT scene
    }
  });
  // A scene with no end ends where the next one starts; the last ends at bed_duration.
  for (let i = 0; i < scenes.length; i++) {
    const s = scenes[i];
    if (!s || typeof s !== 'object') continue;
    if (!isNum(s.end)) {
      if (i + 1 < scenes.length && scenes[i + 1] && isNum(scenes[i + 1].start)) s.end = scenes[i + 1].start;
      else if (isNum(out.bed_duration)) s.end = out.bed_duration;
    }
    if (!isNum(s.start) && i > 0 && scenes[i - 1] && isNum(scenes[i - 1].end)) s.start = scenes[i - 1].end;
    if (!isNum(s.start) && i === 0) s.start = 0;
  }
  return { plan: out, errors };
}

/** Check a resolved plan. Returns { ok, errors[], warnings[] }. */
function validateScenePlan(plan, opts = {}) {
  const errors = [];
  const warnings = [];
  const bed = isNum(opts.bedDuration) ? opts.bedDuration
    : (plan && isNum(plan.bed_duration) ? plan.bed_duration : null);

  if (!plan || typeof plan !== 'object' || Array.isArray(plan)) {
    return { ok: false, errors: ['scene plan must be a JSON object { version: 1, scenes: [...] }'], warnings };
  }
  if (plan.version !== 1) errors.push(`version must be 1 (got ${JSON.stringify(plan.version)})`);
  if (!Array.isArray(plan.scenes) || plan.scenes.length === 0) {
    errors.push('scenes must be a non-empty array');
    return { ok: false, errors, warnings };
  }

  const scenes = plan.scenes;
  scenes.forEach((s, i) => {
    const label = `scene ${i}${s && s.id ? ` (${s.id})` : ''}`;
    if (!s || typeof s !== 'object') { errors.push(`${label}: not an object`); return; }
    for (const [key, cap] of Object.entries(TEXT_CAPS)) {
      if (s[key] === undefined) continue;
      if (typeof s[key] !== 'string') { errors.push(`${label}: ${key} must be text (got ${s[key] === null ? 'null' : Array.isArray(s[key]) ? 'a list' : typeof s[key]})`); continue; }
      if (s[key].length > cap) errors.push(`${label}: ${key} is ${s[key].length} characters (at most ${cap})`);
    }
    if (s.cover !== undefined && typeof s.cover !== 'boolean') errors.push(`${label}: cover must be true or false`);
    for (const [k, v] of Object.entries(s)) {
      if (KNOWN_SCENE_KEYS.has(k)) continue;
      try { inputs.checkPlain(v, `${label}: ${k}`); } catch (e) { errors.push(e.message); }
    }
    if (!KINDS.has(s.kind)) errors.push(`${label}: kind must be one of graphic|broll|avatar (got ${JSON.stringify(s.kind)})`);
    if (!isNum(s.start)) errors.push(`${label}: start must be a number (or a resolvable start_phrase)`);
    if (!isNum(s.end)) errors.push(`${label}: end must be a number (or a resolvable end_phrase)`);
    if (isNum(s.start) && isNum(s.end)) {
      if (s.start < 0) errors.push(`${label}: start < 0`);
      if (s.end <= s.start) errors.push(`${label}: end (${s.end}) must be > start (${s.start})`);
    }
    if (s.kind === 'graphic') {
      const hl = typeof s.headline === 'string' ? s.headline : '';
      const text = headlineText(hl);
      if (typeof s.headline !== 'string' && s.headline !== undefined) {
        /* type error already reported above */
      } else if (!text) {
        errors.push(`${label} [${fmt(s.start)}-${fmt(s.end)}]: graphic scene has EMPTY headline copy; every card needs copy`);
      } else {
        if (!spansBalanced(hl)) errors.push(`${label}: headline has a <span> that is not closed`);
        if (hasDisallowedTag(hl)) errors.push(`${label}: headline may only contain <span class="accent">...</span> and <br> tags`);
        if (text.length > MAX_HEADLINE_CHARS) errors.push(`${label}: headline is ${text.length} chars (max ${MAX_HEADLINE_CHARS}); split the beat or shorten`);
      }
      if (isNum(s.start) && isNum(s.end)) {
        const d = s.end - s.start;
        if (d < MIN_GRAPHIC_SECS) errors.push(`${label}: graphic scene is ${d.toFixed(2)} s (min ${MIN_GRAPHIC_SECS} s)`);
        else if (d > MAX_GRAPHIC_SECS) errors.push(`${label}: graphic scene is ${d.toFixed(1)} s (max ${MAX_GRAPHIC_SECS} s); split it`);
        else if (d > WARN_GRAPHIC_SECS) warnings.push(`${label}: graphic scene is ${d.toFixed(1)} s (over ${WARN_GRAPHIC_SECS} s reads long; consider splitting)`);
      }
    } else if (s.kind === 'broll') {
      if (typeof s.asset !== 'string' || !s.asset.trim()) errors.push(`${label}: broll scene needs a non-empty asset (a clip path, file name or label from the --broll cues file)`);
      if (s.in != null && (!isNum(s.in) || s.in < 0)) errors.push(`${label}: in must be a number >= 0`);
    }
  });

  // Order, overlap, gaps and coverage, for scenes with numeric times.
  const timed = scenes.filter((s) => s && isNum(s.start) && isNum(s.end));
  for (let i = 1; i < timed.length; i++) {
    const a = timed[i - 1], b = timed[i];
    const ia = scenes.indexOf(a), ib = scenes.indexOf(b);
    if (b.start < a.start) { errors.push(`scenes must be sorted by start (scene ${ib} starts before scene ${ia})`); continue; }
    if (b.start < a.end - OVERLAP_TOL) errors.push(`scene ${ia} and scene ${ib} overlap (${fmt(b.start)} < ${fmt(a.end)})`);
    else if (b.start > a.end + GAP_TOL) errors.push(`gap of ${(b.start - a.end).toFixed(2)} s between scene ${ia} (ends ${fmt(a.end)}) and scene ${ib} (starts ${fmt(b.start)}); coverage must be gapless`);
  }
  if (timed.length > 0) {
    if (timed[0].start > GAP_TOL) errors.push(`first scene starts at ${fmt(timed[0].start)}; the plan must start at 0`);
    if (bed != null) {
      const last = timed[timed.length - 1];
      if (last.end < bed - END_TOL) errors.push(`last scene ends at ${fmt(last.end)} but bed_duration is ${fmt(bed)}; the plan must cover the whole bed`);
      if (last.end > bed + END_TOL) errors.push(`last scene ends at ${fmt(last.end)}, past bed_duration ${fmt(bed)}`);
    }
  }
  if (bed == null) warnings.push('bed_duration unknown; coverage of the full bed not checked');

  return { ok: errors.length === 0, errors, warnings };
}

module.exports = {
  validateScenePlan, resolveAnchors, findPhrase, headlineText, hasDisallowedTag,
  LIMITS: { MAX_HEADLINE_CHARS, MAX_EYEBROW_CHARS, MAX_GHOST_CHARS, MIN_GRAPHIC_SECS, WARN_GRAPHIC_SECS, MAX_GRAPHIC_SECS, GAP_TOL, OVERLAP_TOL, END_TOL },
};

// ---- command line ----------------------------------------------------------

const USAGE = 'usage: validate-scene-plan.js PLAN.json [--bed-dur S] [--transcript WORDS.json]';

function main(argv) {
  let file = null, bedDur = null, transcriptPath = null;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') { console.log(USAGE); return 0; }
    if (a === '--bed-dur' || a === '--transcript') {
      if (i + 1 >= argv.length) { console.error(`[scene_plan] ${a} needs a value\n${USAGE}`); return 2; }
      const v = argv[++i];
      if (a === '--bed-dur') {
        bedDur = inputs.plainNumber(v);
        if (!Number.isFinite(bedDur) || bedDur <= 0) { console.error(`[scene_plan] --bed-dur must be a positive number (got "${v}")`); return 2; }
      } else transcriptPath = v;
    } else if (a.startsWith('-')) { console.error(`[scene_plan] unknown option ${a}\n${USAGE}`); return 2; }
    else if (file === null) file = a;
    else { console.error(`[scene_plan] only one plan file is allowed\n${USAGE}`); return 2; }
  }
  if (!file) { console.error(USAGE); return 2; }

  let plan, words = null;
  try {
    const root = safe.workRoot();
    plan = inputs.readJsonFile(root, file, 'plan').value;
    if (transcriptPath) words = inputs.readJsonFile(root, transcriptPath, 'transcript').value;
  } catch (e) { console.error(`[scene_plan] ${e.message}`); return 2; }
  if (words !== null) {
    try { words = inputs.checkWords(words); } catch (e) { console.error(`[scene_plan] ERROR: ${e.message}`); return 1; }
  }

  // --bed-dur also closes a last scene that has no `end`.
  if (plan && typeof plan === 'object' && !Array.isArray(plan) && !isNum(plan.bed_duration) && isNum(bedDur)) plan.bed_duration = bedDur;
  const r = resolveAnchors(plan && typeof plan === 'object' ? plan : {}, words);
  const v = validateScenePlan(plan && typeof plan === 'object' && !Array.isArray(plan) ? r.plan : plan, { bedDuration: bedDur });
  const errors = [...r.errors, ...v.errors];
  for (const w of v.warnings) console.warn(`[scene_plan] WARN: ${w}`);
  if (errors.length) {
    for (const e of errors) console.error(`[scene_plan] ERROR: ${e}`);
    console.error(`[scene_plan] INVALID: ${errors.length} error(s). Fix the plan; do not render blank cards.`);
    return 1;
  }
  console.log(`[scene_plan] OK: ${r.plan.scenes.length} scenes${bedDur ? ` covering ${bedDur}s` : ''}`);
  return 0;
}

if (require.main === module) {
  let code;
  try { code = main(process.argv.slice(2)); } catch (e) {
    console.error('[scene_plan] ERROR: unexpected failure. Check the arguments and files, then try again.');
    code = 1;
  }
  process.exit(code);
}
