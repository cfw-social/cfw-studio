// Recipe-only HTML-to-PNG tool. The customer bot owns preparation and reporting.
// Native Windows/macOS/Linux: argument arrays, path.resolve and pathToFileURL.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { lstatSync, mkdirSync, realpathSync, renameSync, rmSync, statSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { parseArgs } from 'node:util';

const { values, positionals } = parseArgs({ allowPositionals: true, options: {
  width: { type: 'string', default: '1080' }, height: { type: 'string', default: '1350' },
  scale: { type: 'string', default: '2' }, 'playwright-version': { type: 'string' },
} });
if (positionals.length > 1 || values.width !== '1080' ||
    !['1080', '1350'].includes(values.height) || !['1', '2'].includes(values.scale)) {
  throw new Error('render.mjs: use one HTML file, width 1080, height 1080/1350 and scale 1/2');
}
const expectedVersion = values['playwright-version'] ?? process.env.CFW_PLAYWRIGHT_PIN;
if (!expectedVersion || !/^\d+\.\d+\.\d+$/.test(expectedVersion) ||
    (process.env.CFW_PLAYWRIGHT_PIN && process.env.CFW_PLAYWRIGHT_PIN !== expectedVersion)) {
  throw new Error('render.mjs: exact Playwright pin is missing or conflicting');
}
const WIDTH = Number(values.width), HEIGHT = Number(values.height), SCALE = Number(values.scale);
const ROOT = realpathSync(process.cwd());
const within = (p) => p === ROOT || p.startsWith(ROOT + path.sep);
// The HTML must be a regular file inside the work folder (after links are resolved).
let htmlPath;
try { htmlPath = realpathSync(path.resolve(positionals[0] ?? 'carousel.html')); }
catch { throw new Error('render.mjs: the HTML file does not exist'); }
if (!within(htmlPath) || !statSync(htmlPath).isFile()) {
  throw new Error('render.mjs: the HTML file must be a regular file inside the work folder');
}
// An output folder is made one level at a time and may not be, or sit under, a link.
function safeDir(rel) {
  let cur = ROOT;
  for (const part of rel.split('/')) {
    cur = path.join(cur, part);
    let st = null;
    try { st = lstatSync(cur); } catch { /* missing: made below */ }
    if (st && st.isSymbolicLink()) throw new Error(`render.mjs: ${path.relative(ROOT, cur)} is a symbolic link`);
    if (st && !st.isDirectory()) throw new Error(`render.mjs: ${path.relative(ROOT, cur)} is not a folder`);
    if (!st) mkdirSync(cur);
  }
  if (!within(realpathSync(cur))) throw new Error('render.mjs: output folder resolves outside the work folder');
  return cur;
}
const tmpName = (name) => `.tmp-${randomBytes(6).toString('hex')}-${name}`;
// Put a finished file at dir/name by renaming a temporary file. Refuse a link at the target.
function place(tmp, dir, name) {
  const dest = path.join(dir, name);
  let st = null;
  try { st = lstatSync(dest); } catch { /* new file */ }
  if (st && (st.isSymbolicLink() || st.isDirectory())) throw new Error(`render.mjs: ${name} is a link or a folder`);
  renameSync(tmp, dest);
  if (!within(realpathSync(dest))) throw new Error('render.mjs: output file resolves outside the work folder');
  return dest;
}
const captureDir = SCALE > 1 ? 'slides-2x' : 'slides';
const slidesDir = safeDir('slides');
const capDir = safeDir(captureDir);
// ffprobe validates dimensions even at scale 1. Never mask a missing executable.
for (const bin of ['ffmpeg', 'ffprobe']) execFileSync(bin, ['-version'], { stdio: 'ignore' });
// Select one package from this private working directory. No package/browser
// install or alternate package fallback is performed by this recipe tool.
const require = createRequire(path.join(process.cwd(), 'package.json'));
const actualVersion = require('playwright/package.json').version;
if (actualVersion !== expectedVersion) throw new Error('render.mjs: Playwright differs from exact runtime pin');
const module = await import(pathToFileURL(require.resolve('playwright')).href);
const { chromium } = module.default ?? module;
const browser = await chromium.launch();
try {
  // The page holds order text, so treat it as untrusted: no script runs (the template has
  // none) and only local files, inline data and the two declared font hosts may load.
  const context = await browser.newContext({
    viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: SCALE, javaScriptEnabled: false,
  });
  const FONT_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url());
    const ok = url.protocol === 'file:' || url.protocol === 'data:' ||
      (url.protocol === 'https:' && FONT_HOSTS.has(url.hostname));
    if (!ok) console.error(`blocked request: ${url.protocol}//${url.hostname}`);
    return ok ? route.continue() : route.abort();
  });
  const page = await context.newPage();
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  const ids = await page.$$eval('section.slide[id]', els => els.map(e => e.id));
  if (![3, 5, 7, 10].includes(ids.length) || ids.some((id, i) => id !== `s${i + 1}`)) {
    throw new Error('render.mjs: slides must be consecutive s1..sN for N=3,5,7,10');
  }
  for (const id of ids) {
    const el = await page.$('#' + id);
    const name = `slide-${id.slice(1)}.png`;
    const tmpShot = path.join(capDir, tmpName(name));
    let final;
    try {
      await el.screenshot({ path: tmpShot });
      const captured = place(tmpShot, capDir, name);
      final = captured;
      if (SCALE > 1) {
        const tmpFinal = path.join(slidesDir, tmpName(name));
        try {
          execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', captured,
            '-vf', `scale=${WIDTH}:${HEIGHT}:flags=lanczos`, tmpFinal], { stdio: 'pipe' });
          final = place(tmpFinal, slidesDir, name);
        } finally { rmSync(tmpFinal, { force: true }); }
      }
    } finally { rmSync(tmpShot, { force: true }); }
    const dims = execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0',
      '-show_entries', 'stream=width,height', '-of', 'csv=p=0', final], { encoding: 'utf8' }).trim();
    if (dims !== `${WIDTH},${HEIGHT}`) throw new Error(`render.mjs: ${id} has wrong dimensions`);
    console.log(`rendered ${id} ${WIDTH}x${HEIGHT}`);
  }
  console.log(`done: ${ids.length} slides at ${WIDTH}x${HEIGHT}`);
} finally { await browser.close(); }
