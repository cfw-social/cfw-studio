/** Native process/pin refusals. No network, browser or paid call.
 * Run: node --test test/test_render.mjs  (from this recipe's folder)
 */
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';

const tool = fileURLToPath(new URL('../render.mjs', import.meta.url));
function refused(args, pattern, setup = () => {}, pin) {
  const cwd = mkdtempSync(path.join(os.tmpdir(), 'carousel native # '));
  try {
    setup(cwd);
    const env = { ...process.env }; delete env.CFW_PLAYWRIGHT_PIN;
    if (pin) env.CFW_PLAYWRIGHT_PIN = pin;
    const result = spawnSync(process.execPath, [tool, ...args], { cwd, env, encoding: 'utf8' });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, pattern);
  } finally { rmSync(cwd, { recursive: true }); }
}
test('rejects unsupported sizes, scale and extra HTML arguments before package lookup', () => {
  for (const args of [['--width', '720'], ['--height', '1920'], ['--scale', '3'], ['--width', '1080x'], ['a.html', 'b.html']]) {
    refused(args, /width 1080, height 1080\/1350 and scale 1\/2/);
  }
});
test('rejects absent, malformed and conflicting exact pins before package lookup', () => {
  refused([], /exact Playwright pin is missing or conflicting/);
  refused(['--playwright-version', 'latest'], /exact Playwright pin is missing or conflicting/);
  refused(['--playwright-version', '1.60.0'], /exact Playwright pin is missing or conflicting/, undefined, '1.59.0');
});
test('never substitutes a different installed Playwright version', () => {
  refused(['--playwright-version', '1.60.0'], /Playwright differs from exact runtime pin/, (cwd) => {
    writeFileSync(path.join(cwd, 'carousel.html'), '<html></html>');
    const pkg = path.join(cwd, 'node_modules', 'playwright');
    mkdirSync(pkg, { recursive: true });
    writeFileSync(path.join(pkg, 'package.json'), JSON.stringify({ name: 'playwright', version: '1.59.0' }));
  });
});

// ---- Path safety. These stop before any browser starts, so they need no Playwright.
import { symlinkSync as symlink, readdirSync, existsSync } from 'node:fs';
const PIN = ['--playwright-version', '1.64.1'];
function inWorkFolder(setup, args, pattern) {
  const cwd = mkdtempSync(path.join(os.tmpdir(), 'carousel-paths-'));
  const outside = mkdtempSync(path.join(os.tmpdir(), 'carousel-outside-'));
  try {
    writeFileSync(path.join(cwd, 'carousel.html'), '<html></html>');
    setup(cwd, outside);
    const env = { ...process.env }; delete env.CFW_PLAYWRIGHT_PIN;
    const r = spawnSync(process.execPath, [tool, ...args, ...PIN], { cwd, env, encoding: 'utf8' });
    assert.notEqual(r.status, 0);
    assert.match(r.stderr, pattern);
    assert.deepEqual(readdirSync(outside), [], 'something was written outside the work folder');
  } finally { rmSync(cwd, { recursive: true, force: true }); rmSync(outside, { recursive: true, force: true }); }
}
test('refuses an HTML file outside the work folder', () => {
  const cwd = mkdtempSync(path.join(os.tmpdir(), 'carousel-paths-'));
  const other = mkdtempSync(path.join(os.tmpdir(), 'carousel-outside-'));
  try {
    writeFileSync(path.join(other, 'x.html'), '<html></html>');
    const r = spawnSync(process.execPath, [tool, path.join(other, 'x.html'), ...PIN], { cwd, encoding: 'utf8' });
    assert.notEqual(r.status, 0);
    assert.match(r.stderr, /regular file inside the work folder/);
  } finally { rmSync(cwd, { recursive: true, force: true }); rmSync(other, { recursive: true, force: true }); }
});
test('refuses an HTML path that is a link to a file outside the work folder', () => {
  inWorkFolder((cwd, outside) => {
    const elsewhere = mkdtempSync(path.join(os.tmpdir(), 'carousel-elsewhere-'));
    writeFileSync(path.join(elsewhere, 'x.html'), '<html></html>');
    rmSync(path.join(cwd, 'carousel.html'));
    symlink(path.join(elsewhere, 'x.html'), path.join(cwd, 'carousel.html'));
  }, [], /regular file inside the work folder/);
});
test('refuses an HTML path that is a folder or missing', () => {
  inWorkFolder((cwd) => { rmSync(path.join(cwd, 'carousel.html')); mkdirSync(path.join(cwd, 'carousel.html')); },
    [], /regular file inside the work folder/);
  inWorkFolder((cwd) => rmSync(path.join(cwd, 'carousel.html')), [], /does not exist/);
});
test('refuses a slides folder that is a link, and writes nothing outside', () => {
  inWorkFolder((cwd, outside) => symlink(outside, path.join(cwd, 'slides')), [], /slides is a symbolic link/);
});
test('refuses a slides-2x folder that is a link, and writes nothing outside', () => {
  inWorkFolder((cwd, outside) => symlink(outside, path.join(cwd, 'slides-2x')), [], /slides-2x is a symbolic link/);
});
test('refuses an output folder that is a file', () => {
  inWorkFolder((cwd) => writeFileSync(path.join(cwd, 'slides'), 'x'), [], /slides is not a folder/);
});

// ---- Browser tests: script must not run, and non-font remote content must not load.
// They need the pinned Playwright, its browser and ffmpeg. Set CAROUSEL_TEST_PLAYWRIGHT_DIR
// to a folder that has node_modules/playwright at 1.64.1; otherwise these tests are skipped.
import http from 'node:http';
import { symlinkSync, readFileSync } from 'node:fs';
import { spawn, execFileSync } from 'node:child_process';

const PW_DIR = process.env.CAROUSEL_TEST_PLAYWRIGHT_DIR;
const PW_PIN = '1.64.1';
const skipBrowser = !PW_DIR ? 'set CAROUSEL_TEST_PLAYWRIGHT_DIR to run browser tests' : false;

function pageWith(extraBody) {
  const sections = [1, 2, 3].map((n) =>
    `<section class="slide" id="s${n}" style="width:1080px;height:1350px;background:#ffffff">${n === 1 ? extraBody : ''}</section>`).join('');
  return `<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="margin:0">${sections}</body></html>`;
}

async function renderPage(html) {
  const cwd = mkdtempSync(path.join(os.tmpdir(), 'carousel-browser-'));
  symlinkSync(path.join(PW_DIR, 'node_modules'), path.join(cwd, 'node_modules'), 'dir');
  writeFileSync(path.join(cwd, 'carousel.html'), html);
  const env = { ...process.env }; delete env.CFW_PLAYWRIGHT_PIN;
  const child = spawn(process.execPath, [tool, 'carousel.html', '--scale', '1', '--playwright-version', PW_PIN], { cwd, env });
  let err = '';
  child.stderr.on('data', (d) => { err += d; });
  const code = await new Promise((resolve) => child.on('close', resolve));
  return { cwd, code, err };
}

function pixel(file, x, y) {
  const out = execFileSync('ffmpeg', ['-v', 'error', '-i', file, '-vf', `crop=1:1:${x}:${y}`,
    '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { encoding: 'buffer' });
  return [...out];
}

test('renderer runs no script and fetches no non-font remote resource', { skip: skipBrowser }, async () => {
  const hits = [];
  const server = http.createServer((req, res) => { hits.push(req.url); res.end('x'); });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${server.address().port}`;
  const evil = `
    <script>document.getElementById('s1').style.background='#ff0000'; fetch('${base}/script-fetch')</script>
    <img src="${base}/img.png" onerror="document.getElementById('s1').style.background='#ff0000'">
    <div onclick="1" style="width:10px;height:10px;background:url(${base}/bg.png)"></div>
    <link rel="stylesheet" href="${base}/a.css">
    <iframe src="${base}/frame.html"></iframe>
    <p>&lt;script&gt;alert(1)&lt;/script&gt;</p>`;
  const r = await renderPage(pageWith(evil));
  try {
    assert.equal(r.code, 0, r.err);
    assert.deepEqual(hits, [], 'the page reached a non-font remote host');
    assert.match(r.err, /blocked request: http:\/\/127\.0\.0\.1/);
    const px = pixel(path.join(r.cwd, 'slides', 'slide-1.png'), 1070, 1340);
    assert.deepEqual(px, [255, 255, 255], 'script ran: the slide background changed');
  } finally {
    server.close();
    rmSync(r.cwd, { recursive: true, force: true });
  }
});

test('renderer still renders a clean page', { skip: skipBrowser }, async () => {
  const r = await renderPage(pageWith('<p>Plain text</p>'));
  try {
    assert.equal(r.code, 0, r.err);
    assert.match(readFileSync(path.join(r.cwd, 'slides', 'slide-1.png')).subarray(1, 4).toString(), /PNG/);
  } finally { rmSync(r.cwd, { recursive: true, force: true }); }
});

test('refuses an output file that is a link and writes nothing outside', { skip: skipBrowser }, async () => {
  const cwd = mkdtempSync(path.join(os.tmpdir(), 'carousel-browser-'));
  const outside = mkdtempSync(path.join(os.tmpdir(), 'carousel-outside-'));
  try {
    symlinkSync(path.join(PW_DIR, 'node_modules'), path.join(cwd, 'node_modules'), 'dir');
    writeFileSync(path.join(cwd, 'carousel.html'), pageWith(''));
    mkdirSync(path.join(cwd, 'slides'));
    symlink(path.join(outside, 'stolen.png'), path.join(cwd, 'slides', 'slide-1.png'));
    const env = { ...process.env }; delete env.CFW_PLAYWRIGHT_PIN;
    const r = spawnSync(process.execPath, [tool, 'carousel.html', '--scale', '1', '--playwright-version', PW_PIN],
      { cwd, env, encoding: 'utf8' });
    assert.notEqual(r.status, 0);
    assert.match(r.stderr, /slide-1\.png is a link or a folder/);
    assert.deepEqual(readdirSync(outside), [], 'a file was written through the link');
    assert.deepEqual(readdirSync(path.join(cwd, 'slides')).filter((f) => f.startsWith('.tmp-')), [], 'temporary file left behind');
  } finally { rmSync(cwd, { recursive: true, force: true }); rmSync(outside, { recursive: true, force: true }); }
});

test('a normal render leaves no temporary files and keeps both folders inside the work folder', { skip: skipBrowser }, async () => {
  const r = await renderPage(pageWith('<p>Plain text</p>'));
  try {
    assert.equal(r.code, 0, r.err);
    for (const d of ['slides', 'slides-2x']) if (existsSync(path.join(r.cwd, d))) {
      assert.deepEqual(readdirSync(path.join(r.cwd, d)).filter((f) => f.startsWith('.tmp-')), []);
    }
    assert.deepEqual(readdirSync(path.join(r.cwd, 'slides')).sort(), ['slide-1.png', 'slide-2.png', 'slide-3.png']);
  } finally { rmSync(r.cwd, { recursive: true, force: true }); }
});
