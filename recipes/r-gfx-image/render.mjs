// Recipe-only HTML-to-PNG tool: one PNG per card file, at the exact canvas.
// The cards hold order text, so they are treated as untrusted: JavaScript is off, and only
// local files, inline data and the two declared font hosts may load.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { mkdir, lstat, realpath, rename, rm } from 'node:fs/promises';
import { randomBytes } from 'node:crypto';
import { parseArgs } from 'node:util';

const CANVASES = new Set(['1080x1080', '1080x1920', '1920x1080']);
const FONT_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com']);
const { values, positionals } = parseArgs({ allowPositionals: true, options: {
  width: { type: 'string' }, height: { type: 'string' },
  'out-dir': { type: 'string', default: 'work' }, 'playwright-version': { type: 'string' },
} });

const cwd = process.cwd();
const inside = (p) => { const r = path.relative(cwd, p); return r !== '' && !r.startsWith('..') && !path.isAbsolute(r); };
if (!CANVASES.has(`${values.width}x${values.height}`) || positionals.length < 1 || positionals.length > 4) {
  throw new Error('render.mjs: use --width/--height 1080x1080, 1080x1920 or 1920x1080 and one to four card-N.html files');
}
if (!/^\d+\.\d+\.\d+$/.test(values['playwright-version'] ?? '')) {
  throw new Error('render.mjs: pass the exact Playwright version with --playwright-version');
}
const outDir = path.resolve(values['out-dir']);
if (!inside(outDir) && outDir !== cwd) throw new Error('render.mjs: --out-dir must be inside the work folder');
const cards = positionals.map((f) => {
  const abs = path.resolve(f);
  const m = /^card-(\d+)\.html$/.exec(path.basename(abs));
  if (!inside(abs) || !m) throw new Error('render.mjs: cards must be card-N.html files inside the work folder');
  return { abs, n: m[1] };
});

// Use the one Playwright package installed in this work folder. Nothing is installed here.
const require = createRequire(path.join(cwd, 'package.json'));
if (require('playwright/package.json').version !== values['playwright-version']) {
  throw new Error('render.mjs: installed Playwright differs from the pinned version');
}
const mod = await import(pathToFileURL(require.resolve('playwright')).href);
const { chromium } = mod.default ?? mod;
const WIDTH = Number(values.width), HEIGHT = Number(values.height);

// The output folder, and every folder on the way to it below the work folder, must be a real
// folder, not a link. Files are written under a fresh temporary name and renamed into place.
const realCwd = await realpath(cwd);
const lst = async (p) => lstat(p).catch((e) => { if (e.code === 'ENOENT') return null; throw e; });
let walk = cwd;
for (const part of path.relative(cwd, outDir).split(path.sep).filter(Boolean)) {
  walk = path.join(walk, part);
  let st = await lst(walk);
  if (!st) { await mkdir(walk); st = await lst(walk); }
  if (st.isSymbolicLink() || !st.isDirectory()) throw new Error('render.mjs: the output folder (or a parent of it) is a link or not a folder');
}
const insideReal = async (p) => { const r = path.relative(realCwd, await realpath(p)); return r !== '' && !r.startsWith('..') && !path.isAbsolute(r); };
if (!(await insideReal(outDir)) && (await realpath(outDir)) !== realCwd) throw new Error('render.mjs: the output folder resolves outside the work folder');
const browser = await chromium.launch(); // the browser sandbox stays on
try {
  const context = await browser.newContext({
    viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: 1, javaScriptEnabled: false,
  });
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url());
    const ok = url.protocol === 'file:' || url.protocol === 'data:' ||
      (url.protocol === 'https:' && FONT_HOSTS.has(url.hostname));
    if (!ok) console.error(`blocked request: ${url.protocol}//${url.hostname}`);
    return ok ? route.continue() : route.abort();
  });
  for (const { abs, n } of cards) {
    const page = await context.newPage();
    await page.goto(pathToFileURL(abs).href, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    const final = path.join(outDir, `img-${n}.png`);
    const tmp = path.join(outDir, `.img-${n}.${randomBytes(8).toString('hex')}.tmp.png`);
    const old = await lst(final);
    if (old && (old.isSymbolicLink() || !old.isFile())) throw new Error('render.mjs: the output file is a link or not a file');
    try {
      await page.screenshot({ path: tmp, clip: { x: 0, y: 0, width: WIDTH, height: HEIGHT } });
      await rename(tmp, final);
    } catch (e) { await rm(tmp, { force: true }); throw e; }
    if (!(await insideReal(final))) throw new Error('render.mjs: the output file resolves outside the work folder');
    await page.close();
    console.log(`rendered card ${n} ${WIDTH}x${HEIGHT}`);
  }
} finally { await browser.close(); }
