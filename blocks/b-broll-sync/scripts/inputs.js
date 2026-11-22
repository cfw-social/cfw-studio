'use strict';
// Reading and checking input data for b-broll-sync. Shared by plan.js and validate-scene-plan.js.

const fs = require('fs');
const safe = require('./safe-path');

const MAX_JSON_BYTES = 8 * 1024 * 1024;
const MAX_STRING = 500;       // longest text allowed in a pass-through value
const MAX_DEPTH = 6;
const BAD_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

class InputError extends Error {}   // a file cannot be used at all (exit 2)
class DataError extends Error {}    // the data is wrong (exit 1)

/** A plain decimal only: 12, 12.5, .5, -3. No hex, no exponent, no spaces. */
function plainNumber(text) {
  return typeof text === 'string' && /^[+-]?(\d+(\.\d*)?|\.\d+)$/.test(text) ? Number(text) : NaN;
}

/** Resolve inside root and require a regular file, so a named pipe or device is never opened. */
function regularFile(root, p, what) {
  let real;
  try { real = safe.resolveExisting(root, p, what); } catch (e) { throw new InputError(e.message); }
  let st;
  try { st = fs.statSync(real); } catch (e) { throw new InputError(`${what} "${p}" cannot be read`); }
  if (!st.isFile()) throw new InputError(`${what} "${p}" is not a regular file`);
  return { real, size: st.size };
}

/**
 * Read a JSON file inside root. Must be a regular file of at most 8 MB. The keys __proto__,
 * constructor and prototype are dropped at every depth. Returns { value, real }.
 */
function readJsonFile(root, p, what) {
  const { real, size } = regularFile(root, p, what);
  if (size > MAX_JSON_BYTES) throw new InputError(`${what} "${p}" is larger than ${MAX_JSON_BYTES / (1024 * 1024)} MB`);
  let text;
  try { text = fs.readFileSync(real, 'utf8'); } catch (e) { throw new InputError(`${what} "${p}" cannot be read`); }
  try { return { value: JSON.parse(text, (k, v) => (BAD_KEYS.has(k) ? undefined : v)), real }; }
  catch (e) { throw new InputError(`${what} "${p}" is not valid JSON`); }
}

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

/** Transcript words: [{text|word, start, end}] with real numbers, end >= start, starts not going back. */
function checkWords(raw) {
  if (!Array.isArray(raw) || raw.length === 0) throw new DataError('transcript must be a non-empty JSON array of {text,start,end}');
  let prev = -Infinity;
  return raw.map((w, i) => {
    if (!isObj(w)) throw new DataError(`transcript word ${i} must be an object with text, start and end`);
    const text = w.text !== undefined ? w.text : w.word;
    if (typeof text !== 'string' || text.length > 100) throw new DataError(`transcript word ${i}: text must be a string of at most 100 characters`);
    if (typeof w.start !== 'number' || !Number.isFinite(w.start) || typeof w.end !== 'number' || !Number.isFinite(w.end)) {
      throw new DataError(`transcript word ${i}: start and end must be numbers`);
    }
    if (w.start < 0 || w.end < w.start) throw new DataError(`transcript word ${i}: end must not be before start, and start must not be negative`);
    if (w.start < prev) throw new DataError(`transcript word ${i}: start goes back in time`);
    prev = w.start;
    return { text, start: w.start, end: w.end };
  });
}

/** Pass-through data: JSON values, strings at most 500 characters, depth at most 6. Throws DataError. */
function checkPlain(value, label, depth = 0) {
  if (depth > MAX_DEPTH) throw new DataError(`${label} is nested too deeply`);
  if (typeof value === 'string') {
    if (value.length > MAX_STRING) throw new DataError(`${label} has text longer than ${MAX_STRING} characters`);
  } else if (Array.isArray(value)) {
    value.forEach((v, i) => checkPlain(v, `${label}[${i}]`, depth + 1));
  } else if (isObj(value)) {
    for (const [k, v] of Object.entries(value)) checkPlain(v, `${label}.${k}`, depth + 1);
  } else if (value !== null && typeof value !== 'boolean' && !(typeof value === 'number' && Number.isFinite(value))) {
    throw new DataError(`${label} must be text, a number, true or false, a list or an object`);
  }
}

module.exports = { InputError, DataError, plainNumber, regularFile, readJsonFile, checkWords, checkPlain, isObj, MAX_STRING };
