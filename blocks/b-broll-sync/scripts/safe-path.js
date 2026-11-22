'use strict';
// Path containment for b-broll-sync. A path is accepted only when its real
// location (symbolic links followed) is inside the given folder.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function isInside(root, target) {
  const rel = path.relative(root, target);
  return rel === '' || (!rel.startsWith('..' + path.sep) && rel !== '..' && !path.isAbsolute(rel));
}

/** Real path of the work folder (the current folder). */
function workRoot() {
  return fs.realpathSync(process.cwd());
}

/**
 * Resolve an existing file or folder. Returns its real path, or throws an
 * Error whose message says why it was refused.
 */
function resolveExisting(root, p, what) {
  let real;
  try {
    real = fs.realpathSync(path.resolve(process.cwd(), String(p)));
  } catch (e) {
    throw new Error(`${what} "${p}" cannot be read (${e.code || e.message})`);
  }
  if (!isInside(root, real)) throw new Error(`${what} "${p}" is outside ${path.basename(root) || 'the allowed folder'}; refused`);
  return real;
}

/**
 * Resolve a path that may not exist yet (an output file). The nearest existing
 * parent, and the file itself if it exists, must resolve inside root.
 */
function resolveForWrite(root, p, what) {
  const abs = path.resolve(process.cwd(), String(p));
  if (isLink(abs)) throw new Error(`${what} "${p}" is a link; refused`);
  let probe = abs;
  const tail = [];
  while (!fs.existsSync(probe) && !isLink(probe)) {
    const up = path.dirname(probe);
    if (up === probe) break;
    tail.unshift(path.basename(probe));
    probe = up;
  }
  let real;
  try { real = fs.realpathSync(probe); } catch (e) { throw new Error(`${what} "${p}" cannot be resolved (${e.code || e.message})`); }
  const full = path.join(real, ...tail);
  if (!isInside(root, full)) throw new Error(`${what} "${p}" is outside the work folder; refused`);
  return full;
}

function isLink(p) { try { return fs.lstatSync(p).isSymbolicLink(); } catch (e) { return false; } }

/**
 * Write a file inside root, safely. Refuses a target that is a link, a parent folder whose real
 * path is outside root, a folder as target, and a target that is the same file as any of `inputs`
 * (real paths). The text goes to a new file created exclusively (flag 'wx', random name) in the
 * target folder, then is renamed into place. The final real path is checked, and the temporary
 * file is removed on every failure path.
 */
function writeSafely(root, p, text, inputs) {
  const abs = path.resolve(process.cwd(), String(p));
  if (isLink(abs)) throw new Error(`--out "${p}" is a link; refused`);
  let parentReal;
  try { parentReal = fs.realpathSync(path.dirname(abs)); } catch (e) { throw new Error(`--out folder for "${p}" does not exist`); }
  if (!isInside(root, parentReal)) throw new Error(`--out "${p}" is outside the work folder; refused`);
  const full = path.join(parentReal, path.basename(abs));
  try { if (fs.statSync(full).isDirectory()) throw new Error(`--out "${p}" is a folder`); } catch (e) { if (e.code !== 'ENOENT') throw e; }
  for (const other of inputs || []) {
    if (other === full) throw new Error(`--out "${p}" is the same file as an input; refused`);
    try { if (fs.existsSync(full) && fs.realpathSync(full) === other) throw new Error(`--out "${p}" is the same file as an input; refused`); } catch (e) { if (e.code !== 'ENOENT') throw e; }
  }
  const tmp = path.join(parentReal, `.plan-${crypto.randomBytes(8).toString('hex')}.tmp`);
  let fd;
  try {
    fd = fs.openSync(tmp, 'wx', 0o644);
    fs.writeSync(fd, text);
    fs.closeSync(fd);
    fd = undefined;
    fs.renameSync(tmp, full);
  } catch (e) {
    if (fd !== undefined) { try { fs.closeSync(fd); } catch (x) { /* already closed */ } }
    try { fs.unlinkSync(tmp); } catch (x) { /* nothing to remove */ }
    throw e;
  }
  if (!isInside(root, fs.realpathSync(full))) {
    try { fs.unlinkSync(full); } catch (x) { /* best effort */ }
    throw new Error(`--out "${p}" ended up outside the work folder; removed`);
  }
}

module.exports = { isInside, workRoot, resolveExisting, resolveForWrite, writeSafely };
