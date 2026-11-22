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
    const pkg = path.join(cwd, 'node_modules', 'playwright');
    mkdirSync(pkg, { recursive: true });
    writeFileSync(path.join(pkg, 'package.json'), JSON.stringify({ name: 'playwright', version: '1.59.0' }));
  });
});
