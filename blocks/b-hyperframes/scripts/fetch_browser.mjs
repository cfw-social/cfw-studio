// Fetch the pinned Chrome headless shell into a cache folder, using the same library
// call HyperFrames 0.7.5 uses. Called by hf_install.py with checked folders.
//   node fetch_browser.mjs --runtime DIR --cache DIR --version 131.0.6778.85
// Prints "BROWSER_EXE: <path>". Downloads from storage.googleapis.com only when the
// browser is not already in the cache folder.
import { createRequire } from 'node:module';
import path from 'node:path';

const args = process.argv.slice(2);
const opt = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const runtime = opt('--runtime');
const cache = opt('--cache');
const version = opt('--version');
if (!runtime || !cache || !/^\d+\.\d+\.\d+\.\d+$/.test(version || '')) {
  console.error('usage: fetch_browser.mjs --runtime DIR --cache DIR --version A.B.C.D');
  process.exit(2);
}
const require = createRequire(path.join(path.resolve(runtime), 'package.json'));
const pb = require('@puppeteer/browsers');
const platform = pb.detectBrowserPlatform();
if (!platform) {
  console.error('unsupported platform');
  process.exit(1);
}
const installed = await pb.install({
  cacheDir: path.resolve(cache),
  browser: pb.Browser.CHROMEHEADLESSSHELL,
  buildId: version,
  platform,
});
console.log('BROWSER_EXE: ' + installed.executablePath);
