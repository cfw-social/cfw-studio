// Recipe-only HTML-to-PNG tool. The customer bot owns preparation and reporting.
// Native Windows/macOS/Linux: argument arrays, path.resolve and pathToFileURL.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { mkdir } from 'node:fs/promises';
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
// Select one package from this private working directory. No package/browser
// install or alternate package fallback is performed by this recipe tool.
const require = createRequire(path.join(process.cwd(), 'package.json'));
const actualVersion = require('playwright/package.json').version;
if (actualVersion !== expectedVersion) throw new Error('render.mjs: Playwright differs from exact runtime pin');
const module = await import(pathToFileURL(require.resolve('playwright')).href);
const { chromium } = module.default ?? module;
const WIDTH = Number(values.width), HEIGHT = Number(values.height), SCALE = Number(values.scale);
const htmlPath = path.resolve(positionals[0] ?? 'carousel.html');
const captureDir = SCALE > 1 ? 'slides-2x' : 'slides';
// ffprobe validates dimensions even at scale 1. Never mask a missing executable.
for (const bin of ['ffmpeg', 'ffprobe']) execFileSync(bin, ['-version'], { stdio: 'ignore' });
await mkdir('slides', { recursive: true });
await mkdir(captureDir, { recursive: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: WIDTH, height: HEIGHT }, deviceScaleFactor: SCALE });
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  const ids = await page.$$eval('section.slide[id]', els => els.map(e => e.id));
  if (![3, 5, 7, 10].includes(ids.length) || ids.some((id, i) => id !== `s${i + 1}`)) {
    throw new Error('render.mjs: slides must be consecutive s1..sN for N=3,5,7,10');
  }
  for (const id of ids) {
    const el = await page.$('#' + id);
    const name = `slide-${id.slice(1)}.png`;
    const captured = path.join(captureDir, name), final = path.join('slides', name);
    await el.screenshot({ path: captured });
    if (SCALE > 1) execFileSync('ffmpeg', ['-v', 'error', '-y', '-i', captured,
      '-vf', `scale=${WIDTH}:${HEIGHT}:flags=lanczos`, final], { stdio: 'pipe' });
    const dims = execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0',
      '-show_entries', 'stream=width,height', '-of', 'csv=p=0', final], { encoding: 'utf8' }).trim();
    if (dims !== `${WIDTH},${HEIGHT}`) throw new Error(`render.mjs: ${id} has wrong dimensions`);
    console.log(`rendered ${id} ${WIDTH}x${HEIGHT}`);
  }
  console.log(`done: ${ids.length} slides at ${WIDTH}x${HEIGHT}`);
} finally { await browser.close(); }
