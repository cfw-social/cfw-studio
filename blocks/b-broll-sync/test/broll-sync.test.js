#!/usr/bin/env node
// b-broll-sync tests. node:test and node:assert only. No account, no private file, no network.
//   node --test blocks/b-broll-sync/test/broll-sync.test.js
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const BLOCK = path.resolve(__dirname, '..');
const SCRIPTS = path.join(BLOCK, 'scripts');
const { validateScenePlan, resolveAnchors, findPhrase, headlineText, hasDisallowedTag } = require(path.join(SCRIPTS, 'validate-scene-plan.js'));

const TEXT = 'nobody talks about this feature it is called zorp it connects gizmo to real tools your files your calendar the setup takes fifteen minutes comment zorp and i will mail you the notes plus three tools that matter most today'.split(' ');
const WORDS = TEXT.map((w, i) => ({ text: w, start: i * 0.5, end: i * 0.5 + 0.45 }));
const BED = TEXT.length * 0.5; // 20

function goodPlan() {
  return { version: 1, scenes: [
    { id: 'hook', kind: 'graphic', start: 0, end: 4, type: 'hook', eyebrow: 'NOBODY TALKS ABOUT THIS', ghost: '?', headline: 'THE FEATURE THAT <span class="accent">CHANGED</span> HOW I WORK' },
    { id: 'zorp', kind: 'graphic', start: 4, end: 9, type: 'terminal', ghost: 'ZORP', headline: 'IT IS CALLED <span class="accent">ZORP</span>' },
    { id: 'tools', kind: 'graphic', start: 9, end: 14, ghost: '04', headline: 'GIZMO + YOUR <span class="accent">REAL</span> TOOLS' },
    { id: 'cta', kind: 'graphic', start: 14, end: 20, type: 'cta', ghost: 'MAIL', headline: 'COMMENT <span class="accent">ZORP</span>', sub: 'I will mail you the notes' },
  ] };
}

// A work folder with inputs/broll/clip-a.mp4 (a stand-in file; the planner never decodes it).
function workFolder() {
  const tmp = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'broll-sync-')));
  fs.mkdirSync(path.join(tmp, 'inputs', 'broll'), { recursive: true });
  fs.writeFileSync(path.join(tmp, 'inputs', 'broll', 'clip-a.mp4'), 'not a real video');
  fs.writeFileSync(path.join(tmp, 'words.json'), JSON.stringify(WORDS));
  fs.writeFileSync(path.join(tmp, 'broll.json'), JSON.stringify([{ clip: 'inputs/broll/clip-a.mp4', duration: 8, label: 'a', cues: [] }]));
  fs.writeFileSync(path.join(tmp, 'brand.json'), JSON.stringify({ bg: '#0F172A', accent: '#F97316' }));
  return tmp;
}
const run = (script, args, cwd) => spawnSync('node', [path.join(SCRIPTS, script), ...args], { encoding: 'utf8', cwd });
const plan = (args, cwd) => run('plan.js', args, cwd);
const read = (tmp, f) => JSON.parse(fs.readFileSync(path.join(tmp, f), 'utf8'));
const write = (tmp, f, o) => fs.writeFileSync(path.join(tmp, f), JSON.stringify(o));
const BASE = ['--transcript', 'words.json', '--bed-dur', String(BED), '--out', 'beats.json'];

// ---- validator --------------------------------------------------------------

test('valid plan passes', () => {
  const v = validateScenePlan(goodPlan(), { bedDuration: BED });
  assert.equal(v.ok, true, v.errors.join('; '));
});

test('empty or missing headline is an error', () => {
  const p = goodPlan(); p.scenes[1].headline = '  <span class="accent"></span> ';
  assert.match(validateScenePlan(p, { bedDuration: BED }).errors.join('\n'), /EMPTY headline/);
  const q = goodPlan(); delete q.scenes[2].headline;
  assert.equal(validateScenePlan(q, { bedDuration: BED }).ok, false);
});

test('overlap is refused', () => {
  const p = goodPlan(); p.scenes[1].start = 3.0;
  const v = validateScenePlan(p, { bedDuration: BED });
  assert.equal(v.ok, false); assert.match(v.errors.join('\n'), /overlap/);
});

test('a gap is refused', () => {
  const p = goodPlan(); p.scenes[2].start = 10.0;
  const v = validateScenePlan(p, { bedDuration: BED });
  assert.equal(v.ok, false); assert.match(v.errors.join('\n'), /gap of/);
});

test('plan must start at 0 and cover the whole bed', () => {
  const p = goodPlan(); p.scenes[3].end = 17;
  assert.match(validateScenePlan(p, { bedDuration: BED }).errors.join('\n'), /cover the whole bed/);
  const q = goodPlan(); q.scenes[0].start = 1;
  assert.match(validateScenePlan(q, { bedDuration: BED }).errors.join('\n'), /must start at 0/);
});

test('markup in a headline other than the accent span and br is refused', () => {
  const p = goodPlan(); p.scenes[0].headline = 'HELLO <script>x</script>';
  assert.match(validateScenePlan(p, { bedDuration: BED }).errors.join('\n'), /may only contain/);
  const q = goodPlan(); q.scenes[0].headline = '<img src=x onerror=alert(1)>';
  assert.equal(validateScenePlan(q, { bedDuration: BED }).ok, false);
  assert.equal(hasDisallowedTag('A <span class="accent">B</span><br>C'), false);
  assert.equal(headlineText('A <span class="accent">B</span><br>C'), 'A BC');
});

test('graphic scenes longer than 12 s fail; 8 to 12 s warn', () => {
  const p = goodPlan();
  p.scenes = [{ id: 'x', kind: 'graphic', start: 0, end: 13, headline: 'LONG' }, { id: 'y', kind: 'graphic', start: 13, end: 20, headline: 'OK' }];
  assert.match(validateScenePlan(p, { bedDuration: BED }).errors.join('\n'), /max 12 s/);
  p.scenes = [{ id: 'x', kind: 'graphic', start: 0, end: 10, headline: 'LONG' }, { id: 'y', kind: 'graphic', start: 10, end: 20, headline: 'OK' }];
  const w = validateScenePlan(p, { bedDuration: BED });
  assert.equal(w.ok, true); assert.equal(w.warnings.length, 2);
});

test('broll scene needs an asset; avatar scene needs no copy', () => {
  const p = goodPlan();
  p.scenes[1] = { id: 'b', kind: 'broll', start: 4, end: 9 };
  assert.equal(validateScenePlan(p, { bedDuration: BED }).ok, false);
  p.scenes[1] = { id: 'b', kind: 'broll', start: 4, end: 9, asset: 'clip-a.mp4' };
  p.scenes[2] = { id: 'a', kind: 'avatar', start: 9, end: 14 };
  assert.equal(validateScenePlan(p, { bedDuration: BED }).ok, true);
});

test('bad kind, version and shape fail', () => {
  const p = goodPlan(); p.scenes[0].kind = 'graphics';
  assert.equal(validateScenePlan(p, { bedDuration: BED }).ok, false);
  assert.equal(validateScenePlan({ version: 2, scenes: goodPlan().scenes }).ok, false);
  assert.equal(validateScenePlan([]).ok, false);
  assert.equal(validateScenePlan({ version: 1, scenes: [] }).ok, false);
});

test('phrase anchors resolve and chain', () => {
  const p = { version: 1, bed_duration: BED, scenes: [
    { id: 'hook', kind: 'graphic', start: 0, end_phrase: 'it is called', headline: 'HOOK' },
    { id: 'zorp', kind: 'graphic', start_phrase: 'it is called', end_phrase: 'the setup', headline: 'ZORP' },
    { id: 'rest', kind: 'graphic', start_phrase: 'the setup', headline: 'REST' },
  ] };
  const r = resolveAnchors(p, WORDS);
  assert.deepEqual(r.errors, []);
  assert.equal(r.plan.scenes[0].end, 2.5);
  assert.equal(r.plan.scenes[2].end, BED);
  assert.match(resolveAnchors({ version: 1, scenes: [{ kind: 'graphic', start: 0, end_phrase: 'not in script', headline: 'X' }] }, WORDS).errors.join('\n'), /not found in transcript/);
});

test('hyphenated phrases match split or joined speech-tool words', () => {
  const W = (a) => a.map((t, i) => ({ text: t, start: i * 0.5, end: i * 0.5 + 0.45 }));
  assert.deepEqual(findPhrase(W(['my', ' four', '-part', 'plan']), 'four-part'), { start: 0.5, end: 1.45 });
  assert.deepEqual(findPhrase(W(['my', 'four', 'part', 'plan']), 'four-part plan'), { start: 0.5, end: 1.95 });
  assert.deepEqual(findPhrase(W(['the', 'settings']), 'the set'), { start: 0, end: 0.95 });
  assert.equal(findPhrase(W(['these', 'tools']), 'the set'), null);
});

test('validator CLI: 0 valid, 1 invalid, 2 usage and bad paths', () => {
  const tmp = workFolder();
  write(tmp, 'ok.json', goodPlan());
  const bad = goodPlan(); bad.scenes[3].headline = '';
  write(tmp, 'bad.json', bad);
  assert.equal(run('validate-scene-plan.js', ['ok.json', '--bed-dur', String(BED)], tmp).status, 0);
  const r = run('validate-scene-plan.js', ['bad.json', '--bed-dur', String(BED)], tmp);
  assert.equal(r.status, 1); assert.match(r.stderr, /INVALID/);
  assert.equal(run('validate-scene-plan.js', ['ok.json', '--bogus', '1'], tmp).status, 2);
  assert.equal(run('validate-scene-plan.js', [], tmp).status, 2);
  assert.equal(run('validate-scene-plan.js', ['missing.json'], tmp).status, 2);
  write(tmp, 'anch.json', { version: 1, scenes: [
    { id: 'a', kind: 'graphic', start: 0, end_phrase: 'the setup', headline: 'A' },
    { id: 'b', kind: 'graphic', start_phrase: 'the setup', headline: 'B' }] });
  assert.equal(run('validate-scene-plan.js', ['anch.json', '--bed-dur', String(BED), '--transcript', 'words.json'], tmp).status, 0);
});

test('validator refuses a plan file outside the work folder, and one reached through a link', () => {
  const tmp = workFolder();
  const other = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'broll-other-')));
  fs.writeFileSync(path.join(other, 'plan.json'), JSON.stringify(goodPlan()));
  const abs = run('validate-scene-plan.js', [path.join(other, 'plan.json')], tmp);
  assert.equal(abs.status, 2); assert.match(abs.stderr, /outside/);
  fs.symlinkSync(path.join(other, 'plan.json'), path.join(tmp, 'link.json'));
  const viaLink = run('validate-scene-plan.js', ['link.json'], tmp);
  assert.equal(viaLink.status, 2); assert.match(viaLink.stderr, /outside/);
});

// ---- plan.js: beat lists -----------------------------------------------------

test('graphics-only plan gives a gapless list with copy on every beat', () => {
  const tmp = workFolder();
  write(tmp, 'scene_plan.json', goodPlan());
  const r = plan([...BASE, '--brand', 'brand.json', '--scene-plan', 'scene_plan.json'], tmp);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const bl = read(tmp, 'beats.json');
  assert.equal(bl.beats.length, 4);
  assert.ok(bl.beats.every((b) => b.kind === 'graphics' && b.scene.title_html.length > 0 && b.scene.source === 'scene_plan'));
  assert.equal(bl.beats[1].slug, 'beat1-zorp');
  assert.equal(bl.beats[1].scene.type, 'terminal');
  assert.equal(bl.beats[1].scene.brand.accent, '#F97316');
  assert.equal(bl.params.broll_order, 'as-given');
  let t = 0; for (const b of bl.beats) { assert.ok(Math.abs(b.start - t) < 0.02); t = b.end; }
  assert.ok(Math.abs(t - BED) < 0.02);
});

test('without a scene plan blank cards are an error; --allow-empty-copy writes them', () => {
  const tmp = workFolder();
  const r = plan(BASE, tmp);
  assert.equal(r.status, 1); assert.match(r.stderr, /have no copy/);
  assert.equal(fs.existsSync(path.join(tmp, 'beats.json')), false);
  const ok = plan([...BASE, '--allow-empty-copy'], tmp);
  assert.equal(ok.status, 0, ok.stderr);
  assert.ok(read(tmp, 'beats.json').beats.every((b) => b.scene.title_html === ''));
});

for (const order of ['as-given', 'even']) {
  test(`--order ${order}: one clip placed by coverage, graphics split around it`, () => {
    const tmp = workFolder();
    write(tmp, 'scene_plan.json', goodPlan());
    const r = plan([...BASE, '--broll', 'broll.json', '--coverage', '25', '--order', order, '--scene-plan', 'scene_plan.json'], tmp);
    assert.equal(r.status, 0, r.stdout + r.stderr);
    const bl = read(tmp, 'beats.json');
    const broll = bl.beats.filter((b) => b.kind === 'broll');
    assert.equal(broll.length, 1);
    assert.equal(broll[0].broll.clip, 'inputs/broll/clip-a.mp4');
    assert.ok(Math.abs(broll[0].start - 7.5) < 0.01 && Math.abs(broll[0].end - 12.5) < 0.01);
    for (const b of bl.beats.filter((x) => x.kind === 'graphics')) assert.ok(b.scene.title_html.length > 0);
    let t = 0; for (const b of bl.beats) { assert.ok(Math.abs(b.start - t) < 0.02, `gap at ${b.start}`); t = b.end; }
    assert.ok(Math.abs(t - BED) < 0.02);
  });
}

test('as-given and even differ when there are more clips than windows', () => {
  const tmp = workFolder();
  const names = ['c0', 'c1', 'c2', 'c3', 'c4'];
  names.forEach((n) => fs.writeFileSync(path.join(tmp, 'inputs', 'broll', n + '.mp4'), 'x'));
  write(tmp, 'five.json', names.map((n) => ({ clip: `inputs/broll/${n}.mp4`, duration: 8 })));
  write(tmp, 'scene_plan.json', goodPlan());
  const used = {};
  for (const order of ['as-given', 'even']) {
    const r = plan([...BASE, '--broll', 'five.json', '--coverage', '50', '--order', order, '--scene-plan', 'scene_plan.json'], tmp);
    assert.equal(r.status, 0, r.stderr);
    used[order] = read(tmp, 'beats.json').beats.filter((b) => b.kind === 'broll').map((b) => path.basename(b.broll.clip, '.mp4'));
  }
  assert.deepEqual(used['as-given'], ['c0', 'c1']);   // the first clips, in the listed order
  assert.deepEqual(used.even, ['c1', 'c3']);          // spread across the whole list
  assert.notDeepEqual(used['as-given'], used.even);
});

test('as-given and even agree when every clip gets a window', () => {
  const tmp = workFolder();
  write(tmp, 'scene_plan.json', goodPlan());
  const out = [];
  for (const order of ['as-given', 'even']) {
    assert.equal(plan([...BASE, '--broll', 'broll.json', '--coverage', '25', '--order', order, '--scene-plan', 'scene_plan.json'], tmp).status, 0);
    out.push(read(tmp, 'beats.json').beats);
  }
  assert.deepEqual(out[0], out[1]);
});

test('broll scenes in the plan are the placements; cover flag sets cover_at', () => {
  const tmp = workFolder();
  const p = goodPlan();
  p.scenes[1] = { id: 'b1', kind: 'broll', start: 4, end: 9, asset: 'clip-a.mp4', cover: true };
  write(tmp, 'scene_plan.json', p);
  const r = plan([...BASE, '--broll', 'broll.json', '--scene-plan', 'scene_plan.json'], tmp);
  assert.equal(r.status, 0, r.stdout + r.stderr);
  const bl = read(tmp, 'beats.json');
  const broll = bl.beats.filter((b) => b.kind === 'broll');
  assert.equal(broll.length, 1);
  assert.equal(broll[0].start, 4); assert.equal(broll[0].end, 9);
  assert.equal(bl.cover_at, 6);
  assert.match(r.stdout, /using them as the placements/);
});

test('asset matches by path, base name or label', () => {
  for (const asset of ['inputs/broll/clip-a.mp4', 'clip-a.mp4', 'a']) {
    const tmp = workFolder();
    const p = goodPlan(); p.scenes[1] = { id: 'b1', kind: 'broll', start: 4, end: 9, asset };
    write(tmp, 'scene_plan.json', p);
    const r = plan([...BASE, '--broll', 'broll.json', '--scene-plan', 'scene_plan.json'], tmp);
    assert.equal(r.status, 0, `${asset}: ${r.stderr}`);
  }
});

test('asset not listed in --broll is an error, even if it is a real file', () => {
  const tmp = workFolder();
  fs.writeFileSync(path.join(tmp, 'inputs', 'broll', 'other.mp4'), 'x');
  for (const asset of ['missing.mp4', 'inputs/broll/other.mp4', '/etc/hosts', '../secret.mp4']) {
    const p = goodPlan(); p.scenes[1] = { id: 'b1', kind: 'broll', start: 4, end: 9, asset };
    write(tmp, 'scene_plan.json', p);
    const r = plan([...BASE, '--broll', 'broll.json', '--scene-plan', 'scene_plan.json'], tmp);
    assert.equal(r.status, 1, asset); assert.match(r.stderr, /matches no clip/);
  }
  assert.equal(fs.existsSync(path.join(tmp, 'beats.json')), false);
});

test('an invalid plan stops with the validator message', () => {
  const tmp = workFolder();
  const p = goodPlan(); p.scenes[0].headline = '';
  write(tmp, 'scene_plan.json', p);
  const r = plan([...BASE, '--scene-plan', 'scene_plan.json'], tmp);
  assert.equal(r.status, 1); assert.match(r.stderr, /EMPTY headline/);
});

test('gaps and overlaps in the plan stop plan.js', () => {
  const tmp = workFolder();
  const gap = goodPlan(); gap.scenes[2].start = 10;
  write(tmp, 'scene_plan.json', gap);
  assert.match(plan([...BASE, '--scene-plan', 'scene_plan.json'], tmp).stderr, /gap of/);
  const ov = goodPlan(); ov.scenes[1].start = 3;
  write(tmp, 'scene_plan.json', ov);
  assert.match(plan([...BASE, '--scene-plan', 'scene_plan.json'], tmp).stderr, /overlap/);
});

test('reuse true repeats clips to meet coverage; reuse false reports a shortfall', () => {
  const tmp = workFolder();
  write(tmp, 'scene_plan.json', goodPlan());
  const a = plan([...BASE, '--broll', 'broll.json', '--coverage', '50', '--reuse', 'true', '--scene-plan', 'scene_plan.json'], tmp);
  assert.equal(a.status, 0, a.stderr);
  assert.equal(read(tmp, 'beats.json').beats.filter((b) => b.kind === 'broll').length, 2);
  const b = plan([...BASE, '--broll', 'broll.json', '--coverage', '50', '--scene-plan', 'scene_plan.json'], tmp);
  assert.equal(b.status, 0, b.stderr);
  assert.match(read(tmp, 'beats.json').shortfall_note, /only 1 clip/);
});

// ---- plan.js: refusals ------------------------------------------------------

test('an unknown ordering is an error naming the two valid values, and nothing is written', () => {
  const tmp = workFolder();
  write(tmp, 'scene_plan.json', goodPlan());
  for (const bad of ['transcript-match', 'smart']) {
    const r = plan([...BASE, '--order', bad, '--scene-plan', 'scene_plan.json'], tmp);
    assert.equal(r.status, 2);
    assert.match(r.stderr, /--order must be as-given or even/);
    assert.match(r.stderr, new RegExp(`got "${bad}"`));
  }
  assert.equal(fs.existsSync(path.join(tmp, 'beats.json')), false);
});

test('unknown options, stray arguments and bad numbers are usage errors', () => {
  const tmp = workFolder();
  assert.equal(plan([...BASE, '--bogus', '1'], tmp).status, 2);
  assert.equal(plan([...BASE, 'extra'], tmp).status, 2);
  assert.equal(plan([...BASE, '--coverage', 'lots'], tmp).status, 2);
  assert.equal(plan([...BASE, '--coverage', '120'], tmp).status, 2);
  assert.equal(plan([...BASE, '--reuse', 'maybe'], tmp).status, 2);
  assert.equal(plan([...BASE, '--min-secs', '7', '--max-secs', '3'], tmp).status, 2);
  assert.equal(plan(['--bed-dur', '10'], tmp).status, 2);
});

test('a clip outside the inputs folder is refused', () => {
  const tmp = workFolder();
  fs.writeFileSync(path.join(tmp, 'stray.mp4'), 'x');                       // in the work folder, not in inputs
  const other = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'broll-other-')));
  fs.writeFileSync(path.join(other, 'away.mp4'), 'x');                      // in another folder
  for (const clip of ['stray.mp4', path.join(other, 'away.mp4'), '/etc/hosts']) {
    write(tmp, 'b.json', [{ clip, duration: 8 }]);
    const r = plan([...BASE, '--broll', 'b.json', '--allow-empty-copy'], tmp);
    assert.equal(r.status, 2, clip); assert.match(r.stderr, /outside/);
  }
  assert.equal(fs.existsSync(path.join(tmp, 'beats.json')), false);
});

test('a path that climbs out with .. is refused', () => {
  const tmp = workFolder();
  const other = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'broll-other-')));
  fs.writeFileSync(path.join(other, 'away.mp4'), 'x');
  const up = path.relative(tmp, path.join(other, 'away.mp4'));             // ../broll-other-xxx/away.mp4
  assert.ok(up.startsWith('..'));
  for (const clip of [up, 'inputs/../../' + path.basename(other) + '/away.mp4', 'inputs/broll/../../../etc/hosts']) {
    write(tmp, 'b.json', [{ clip, duration: 8 }]);
    const r = plan([...BASE, '--broll', 'b.json', '--allow-empty-copy'], tmp);
    assert.equal(r.status, 2, clip); assert.match(r.stderr, /outside|cannot be read/);
  }
});

test('a symbolic link inside inputs that points outside is refused', () => {
  const tmp = workFolder();
  const other = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'broll-other-')));
  fs.writeFileSync(path.join(other, 'away.mp4'), 'x');
  fs.symlinkSync(path.join(other, 'away.mp4'), path.join(tmp, 'inputs', 'broll', 'link.mp4'));
  fs.symlinkSync(other, path.join(tmp, 'inputs', 'dirlink'));
  for (const clip of ['inputs/broll/link.mp4', 'inputs/dirlink/away.mp4']) {
    write(tmp, 'b.json', [{ clip, duration: 8 }]);
    const r = plan([...BASE, '--broll', 'b.json', '--allow-empty-copy'], tmp);
    assert.equal(r.status, 2, clip); assert.match(r.stderr, /outside/);
  }
});

test('an inputs folder that is itself a link out of the work folder is refused', () => {
  const tmp = workFolder();
  const other = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'broll-other-')));
  fs.writeFileSync(path.join(other, 'away.mp4'), 'x');
  fs.symlinkSync(other, path.join(tmp, 'ext'));
  write(tmp, 'b.json', [{ clip: 'ext/away.mp4', duration: 8 }]);
  const r = plan([...BASE, '--broll', 'b.json', '--inputs-dir', 'ext', '--allow-empty-copy'], tmp);
  assert.equal(r.status, 2); assert.match(r.stderr, /outside/);
});

test('a missing clip file is an error', () => {
  const tmp = workFolder();
  write(tmp, 'b.json', [{ clip: 'inputs/broll/nope.mp4', duration: 8 }]);
  assert.equal(plan([...BASE, '--broll', 'b.json', '--allow-empty-copy'], tmp).status, 2);
});

test('--out outside the work folder, or through a link, is refused', () => {
  const tmp = workFolder();
  const other = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'broll-other-')));
  write(tmp, 'scene_plan.json', goodPlan());
  const args = ['--transcript', 'words.json', '--bed-dur', String(BED), '--scene-plan', 'scene_plan.json'];
  const abs = plan([...args, '--out', path.join(other, 'beats.json')], tmp);
  assert.equal(abs.status, 2); assert.match(abs.stderr, /outside/);
  fs.symlinkSync(other, path.join(tmp, 'outlink'));
  assert.equal(plan([...args, '--out', 'outlink/beats.json'], tmp).status, 2);
  fs.symlinkSync(path.join(other, 'target.json'), path.join(tmp, 'dangling.json'));
  assert.equal(plan([...args, '--out', 'dangling.json'], tmp).status, 2);
  assert.deepEqual(fs.readdirSync(other), []);
  assert.equal(plan([...args, '--out', 'beats.json'], tmp).status, 0);
});

test('planted links and same-file outputs are refused; nothing outside changes; no temp file is left', () => {
  const tmp = workFolder();
  const other = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'broll-other-')));
  const victim = path.join(other, 'victim.json');
  fs.writeFileSync(victim, 'keep me');
  write(tmp, 'scene_plan.json', goodPlan());
  fs.symlinkSync(victim, path.join(tmp, 'planted.json'));                 // link to a file outside
  fs.symlinkSync(path.join(tmp, 'words.json'), path.join(tmp, 'inside.json')); // link that stays inside
  fs.symlinkSync(other, path.join(tmp, 'dirlink'));                       // parent folder pointing outside
  const args = ['--transcript', 'words.json', '--bed-dur', String(BED), '--scene-plan', 'scene_plan.json'];
  for (const out of ['planted.json', 'inside.json', 'dirlink/victim.json', 'words.json', './scene_plan.json', 'broll.json']) {
    const r = plan([...args, '--broll', 'broll.json', '--out', out], tmp);
    assert.equal(r.status, 2, `${out}: ${r.stderr}`);
    assert.doesNotMatch(r.stderr, /at .*\.js:\d+/);
  }
  assert.equal(fs.readFileSync(victim, 'utf8'), 'keep me');
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(tmp, 'words.json'), 'utf8')), WORDS);
  assert.deepEqual(fs.readdirSync(other), ['victim.json']);
  assert.deepEqual(fs.readdirSync(tmp).filter((n) => n.endsWith('.tmp')), []);
  // a normal write replaces the file whole and leaves no temporary file
  assert.equal(plan([...args, '--out', 'beats.json'], tmp).status, 0);
  assert.equal(plan([...args, '--out', 'beats.json'], tmp).status, 0);
  assert.deepEqual(fs.readdirSync(tmp).filter((n) => n.endsWith('.tmp')), []);
});

test('an unexpected error prints one fixed line and no stack trace', () => {
  const tmp = workFolder();
  const r = plan([...BASE, '--scene-plan', 'scene_plan.json'], tmp);   // scene_plan.json does not exist: a normal usage error
  assert.equal(r.status, 2);
  assert.equal(r.stderr.trim().split('\n').length, 1);
  assert.doesNotMatch(r.stderr, /at .*\.js:\d+/);
});

test('--transcript outside the work folder is refused', () => {
  const tmp = workFolder();
  const other = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'broll-other-')));
  fs.writeFileSync(path.join(other, 'w.json'), JSON.stringify(WORDS));
  const r = plan(['--transcript', path.join(other, 'w.json'), '--bed-dur', String(BED), '--out', 'beats.json', '--allow-empty-copy'], tmp);
  assert.equal(r.status, 2); assert.match(r.stderr, /outside/);
});

// ---- the agent path is gone and nothing else is reached -------------------------

test('no agent command line, child process, network call or key variable remains in the block', () => {
  const needles = [
    ['child', '_process'], ['spawn'], ['exec', 'Sync'], ['exec', 'File'], ['fork', '('],
    ['--', 'print'], ['dangerously'], ['skip', '-permissions'], ['clau', 'de'], ['kimi'], ['opus'],
    ['ANTHROPIC'], ['API', '_KEY'], ['process.', 'env'], ['require(', "'http"], ['require(', "'https"], ['require(', "'net'"],
    ['fetch', '('], ['XMLHttp'], ['WebSocket'], ['http', '://'], ['https', '://'],
  ].map((p) => p.join(''));
  const files = [];
  (function walk(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const f = path.join(d, e.name);
      if (e.isDirectory()) { if (e.name !== 'test') walk(f); } else files.push(f);
    }
  })(BLOCK);
  assert.ok(files.length >= 6);
  for (const f of files) {
    const text = fs.readFileSync(f, 'utf8').toLowerCase();
    for (const n of needles) assert.ok(!text.includes(n.toLowerCase()), `${path.relative(BLOCK, f)} contains "${n}"`);
  }
});

// ---- review fixes -------------------------------------------------------------

test('1. text fields must be strings, in both scripts', () => {
  const tmp = workFolder();
  const cases = [
    ['headline', { a: 1 }], ['headline', 5], ['headline', { toString: 1 }], ['headline', ['x']], ['headline', null],
    ['eyebrow', 7], ['ghost', {}], ['sub', [1]], ['type', 3], ['id', { x: 1 }],
  ];
  for (const [key, bad] of cases) {
    const p = goodPlan(); p.scenes[1][key] = bad;
    assert.equal(validateScenePlan(p, { bedDuration: BED }).ok, false, `${key}=${JSON.stringify(bad)}`);
    write(tmp, 'bad.json', p);
    const v = run('validate-scene-plan.js', ['bad.json', '--bed-dur', String(BED)], tmp);
    assert.equal(v.status, 1, `${key}: ${v.stderr}`); assert.match(v.stderr, /must be text/);
    assert.doesNotMatch(v.stderr, /unexpected failure/);
    const r = plan([...BASE, '--scene-plan', 'bad.json'], tmp);
    assert.equal(r.status, 1, `${key}: ${r.stderr}`);
    assert.equal(fs.existsSync(path.join(tmp, 'beats.json')), false);
  }
  const long = goodPlan(); long.scenes[1].sub = 'x'.repeat(201); long.scenes[1].id = 'y'.repeat(61);
  const errs = validateScenePlan(long, { bedDuration: BED }).errors.join('\n');
  assert.match(errs, /sub is 201 characters/); assert.match(errs, /id is 61 characters/);
  const extra = goodPlan(); extra.scenes[1].lines = ['z'.repeat(501)];
  assert.match(validateScenePlan(extra, { bedDuration: BED }).errors.join('\n'), /longer than 500/);
  const fn = goodPlan(); fn.scenes[1].cover = 'yes';
  assert.match(validateScenePlan(fn, { bedDuration: BED }).errors.join('\n'), /cover must be/);
  // cue and brand files too
  write(tmp, 'scene_plan.json', goodPlan());
  write(tmp, 'b1.json', [{ clip: 'inputs/broll/clip-a.mp4', label: { x: 1 } }]);
  assert.equal(plan([...BASE, '--scene-plan', 'scene_plan.json', '--broll', 'b1.json'], tmp).status, 1);
  write(tmp, 'b2.json', [{ clip: 'inputs/broll/clip-a.mp4', cues: [{ start: 0, end: 1, text: { a: 1 } }] }]);
  assert.equal(plan([...BASE, '--scene-plan', 'scene_plan.json', '--broll', 'b2.json'], tmp).status, 1);
  write(tmp, 'brand2.json', { accent: { deep: { deeper: { a: { b: { c: { d: 1 } } } } } } });
  assert.equal(plan([...BASE, '--scene-plan', 'scene_plan.json', '--brand', 'brand2.json'], tmp).status, 1);
  write(tmp, 'brand3.json', { name: 'n'.repeat(501) });
  assert.equal(plan([...BASE, '--scene-plan', 'scene_plan.json', '--brand', 'brand3.json'], tmp).status, 1);
});

test('2. a named pipe is never opened: usage error, no hang', { timeout: 20000 }, (t) => {
  const tmp = workFolder();
  const fifo = (name) => spawnSync('mkfifo', [path.join(tmp, name)]).status === 0;
  if (!fifo('pipe.json')) { t.skip('mkfifo is not available here'); return; }
  const v = spawnSync('node', [path.join(SCRIPTS, 'validate-scene-plan.js'), 'pipe.json'], { cwd: tmp, encoding: 'utf8', timeout: 8000 });
  assert.equal(v.status, 2, v.stderr); assert.match(v.stderr, /not a regular file/);
  for (const flag of ['--transcript', '--scene-plan', '--brand', '--broll']) {
    const args = ['--transcript', 'words.json', '--bed-dur', String(BED), '--out', 'beats.json', '--allow-empty-copy'];
    const i = args.indexOf(flag);
    if (i >= 0) args[i + 1] = 'pipe.json'; else args.push(flag, 'pipe.json');
    const r = spawnSync('node', [path.join(SCRIPTS, 'plan.js'), ...args], { cwd: tmp, encoding: 'utf8', timeout: 8000 });
    assert.equal(r.status, 2, `${flag}: ${r.stderr}`); assert.match(r.stderr, /not a regular file/);
  }
  assert.ok(fifo('clip.mp4'));
  fs.renameSync(path.join(tmp, 'clip.mp4'), path.join(tmp, 'inputs', 'broll', 'pipe.mp4'));
  write(tmp, 'bp.json', [{ clip: 'inputs/broll/pipe.mp4', duration: 8 }]);
  const c = spawnSync('node', [path.join(SCRIPTS, 'plan.js'), ...BASE, '--broll', 'bp.json', '--allow-empty-copy'], { cwd: tmp, encoding: 'utf8', timeout: 8000 });
  assert.equal(c.status, 2, c.stderr); assert.match(c.stderr, /not a regular file/);
});

test('2b. a JSON file over the size cap is refused', () => {
  const tmp = workFolder();
  fs.writeFileSync(path.join(tmp, 'huge.json'), '[' + ' '.repeat(8 * 1024 * 1024 + 10) + ']');
  const r = plan(['--transcript', 'huge.json', '--out', 'beats.json'], tmp);
  assert.equal(r.status, 2); assert.match(r.stderr, /larger than/);
});

test('3. non-object transcript words are a clear error, in both scripts', () => {
  const tmp = workFolder();
  write(tmp, 'ok.json', goodPlan());
  for (const bad of [[null], [1], ['x'], [[1, 2]], [{ text: 'a', start: 0, end: 1 }, null]]) {
    write(tmp, 'w.json', bad);
    const v = run('validate-scene-plan.js', ['ok.json', '--transcript', 'w.json'], tmp);
    assert.equal(v.status, 1, JSON.stringify(bad) + v.stderr); assert.match(v.stderr, /transcript word \d+ must be an object/);
    const r = plan(['--transcript', 'w.json', '--out', 'beats.json', '--allow-empty-copy'], tmp);
    assert.equal(r.status, 1, r.stderr); assert.match(r.stderr, /transcript word \d+ must be an object/);
    assert.doesNotMatch(v.stderr + r.stderr, /unexpected failure|at .*\.js:\d+/);
  }
});

test('4. transcript numbers must be real, end not before start, starts not going back', () => {
  const tmp = workFolder();
  const w = (o) => ({ text: 'a', start: 0, end: 1, ...o });
  const bads = [w({ start: '1' }), w({ start: null }), w({ end: true }), w({ start: [1] }), w({ end: NaN === 1 ? 0 : 'x' }),
    w({ start: 2, end: 1 }), w({ start: -1 }), w({ text: 5 })];
  for (const bad of bads) {
    write(tmp, 'w.json', [bad]);
    const r = plan(['--transcript', 'w.json', '--out', 'beats.json', '--allow-empty-copy'], tmp);
    assert.equal(r.status, 1, JSON.stringify(bad) + r.stderr);
  }
  write(tmp, 'w.json', [w({ start: 1, end: 2 }), w({ start: 0.5, end: 1 })]);
  const back = plan(['--transcript', 'w.json', '--out', 'beats.json', '--allow-empty-copy'], tmp);
  assert.equal(back.status, 1); assert.match(back.stderr, /goes back in time/);
  write(tmp, 'w.json', [w({ start: 0, end: 1 }), w({ start: 1, end: 1 })]);
  assert.equal(plan(['--transcript', 'w.json', '--out', 'beats.json', '--allow-empty-copy'], tmp).status, 0);
});

test('5. title_html is a restricted HTML fragment: hostile markup never reaches it', () => {
  const tmp = workFolder();
  for (const headline of ['<img src=x onerror=alert(1)>', 'A <span class="accent" onclick="x()">B</span>', '<script>x</script>', 'A <span class="accent">B']) {
    const p = goodPlan(); p.scenes[1].headline = headline;
    write(tmp, 'scene_plan.json', p);
    const r = plan([...BASE, '--scene-plan', 'scene_plan.json'], tmp);
    assert.equal(r.status, 1, headline); assert.equal(fs.existsSync(path.join(tmp, 'beats.json')), false);
  }
  // Escaped text is kept as written, so it is shown as text and is never markup.
  const p = goodPlan(); p.scenes[1].headline = '&lt;img src=x onerror=alert(1)&gt; <span class="accent">OK</span><br>NEXT';
  write(tmp, 'scene_plan.json', p);
  assert.equal(plan([...BASE, '--scene-plan', 'scene_plan.json'], tmp).status, 0);
  const html = read(tmp, 'beats.json').beats[1].scene.title_html;
  assert.equal(html, '&lt;img src=x onerror=alert(1)&gt; <span class="accent">OK</span><br>NEXT');
  assert.ok(!/<(?!\/?span( class="accent")?>|br>)/i.test(html), 'only span and br tags may appear');
});

test('6. a short clip or a short bed is reported in warnings and on stderr', () => {
  const tmp = workFolder();
  // clip 6 s, in 4, scene 8 to 13: the beat shrinks to 8-10 and the next card is stretched back; both are reported
  write(tmp, 'b.json', [{ clip: 'inputs/broll/clip-a.mp4', duration: 6, label: 'a' }]);
  const p = goodPlan();
  p.scenes = [
    { id: 'a', kind: 'graphic', start: 0, end: 8, headline: 'ONE' },
    { id: 'b', kind: 'broll', start: 8, end: 13, asset: 'a', in: 4 },
    { id: 'c', kind: 'graphic', start: 13, end: 20, headline: 'TWO' },
  ];
  write(tmp, 'scene_plan.json', p);
  const r = plan([...BASE, '--broll', 'b.json', '--scene-plan', 'scene_plan.json'], tmp);
  assert.match(r.stderr, /WARN: broll scene "b": the clip has 2.00 s after "in" 4 but the scene is 5.00 s; the beat was shortened to 8-10 s/);
  assert.equal(r.status, 0, r.stderr);
  const out = read(tmp, 'beats.json');
  assert.ok(out.warnings.some((w) => /shortened to 8-10 s/.test(w)));
  const br = out.beats.find((b) => b.kind === 'broll');
  assert.equal(br.start, 8); assert.equal(br.end, 10);
  assert.equal(out.beats[out.beats.indexOf(br) + 1].start, 10);   // the next card is stretched back
  // a clip shorter than --min-secs
  write(tmp, 'b.json', [{ clip: 'inputs/broll/clip-a.mp4', duration: 2 }]);
  write(tmp, 'scene_plan.json', goodPlan());
  const s = plan([...BASE, '--broll', 'b.json', '--coverage', '25', '--scene-plan', 'scene_plan.json'], tmp);
  assert.equal(s.status, 0, s.stderr);
  assert.match(s.stderr, /shorter than --min-secs 4/);
  assert.ok(read(tmp, 'beats.json').warnings.some((w) => /shorter than --min-secs/.test(w)));
  // a bed too short for any window
  const short = goodPlan();
  short.scenes = [{ id: 'x', kind: 'graphic', start: 0, end: 3, headline: 'SHORT' }];
  write(tmp, 'scene_plan.json', short);
  write(tmp, 'w.json', [{ text: 'hi', start: 0, end: 3 }]);
  const t = plan(['--transcript', 'w.json', '--bed-dur', '3', '--broll', 'broll.json', '--scene-plan', 'scene_plan.json', '--out', 'beats.json'], tmp);
  assert.equal(t.status, 0, t.stderr);
  assert.match(read(tmp, 'beats.json').shortfall_note, /less than one .* s window; no b-roll was placed/);
  // no warnings key content on a clean run
  write(tmp, 'scene_plan.json', goodPlan());
  assert.equal(plan([...BASE, '--scene-plan', 'scene_plan.json'], tmp).status, 0);
  assert.deepEqual(read(tmp, 'beats.json').warnings, []);
});

test('7. unsafe keys are dropped at every depth; only plain decimals are numbers', () => {
  const tmp = workFolder();
  fs.writeFileSync(path.join(tmp, 'brand.json'), '{"accent":"#F00","__proto__":{"polluted":1},"deep":{"constructor":{"x":1},"prototype":2,"ok":[{"__proto__":3,"keep":1}]}}');
  fs.writeFileSync(path.join(tmp, 'scene_plan.json'), JSON.stringify(goodPlan()).replace('"id":"zorp"', '"id":"zorp","__proto__":{"y":1},"extra":{"constructor":1,"keep":2}'));
  const r = plan([...BASE, '--brand', 'brand.json', '--scene-plan', 'scene_plan.json'], tmp);
  assert.equal(r.status, 0, r.stderr);
  const text = fs.readFileSync(path.join(tmp, 'beats.json'), 'utf8');
  assert.doesNotMatch(text, /__proto__|constructor|prototype|polluted/);
  const b = JSON.parse(text).beats[1].scene;
  assert.equal(b.brand.accent, '#F00'); assert.deepEqual(b.brand.deep.ok, [{ keep: 1 }]);
  assert.deepEqual(b.extra, { keep: 2 });
  assert.equal({}.polluted, undefined);
  for (const bad of ['0x10', '1e2', ' 5', '5 ', '', 'NaN', 'Infinity', '1_0', '--5', '5.5.5']) {
    assert.equal(plan([...BASE, '--coverage', bad, '--allow-empty-copy'], tmp).status, 2, `--coverage ${JSON.stringify(bad)}`);
  }
  assert.equal(plan([...BASE, '--coverage', '12.5', '--allow-empty-copy'], tmp).status, 0);
  assert.equal(plan([...BASE, '--coverage', '.5', '--allow-empty-copy'], tmp).status, 0);
  assert.equal(run('validate-scene-plan.js', ['scene_plan.json', '--bed-dur', '0x14'], tmp).status, 2);
});
