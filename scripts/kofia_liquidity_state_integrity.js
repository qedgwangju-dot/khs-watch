'use strict';

const fs = require('fs');
const crypto = require('crypto');

const CORE = ['deposit', 'mmf', 'cma', 'credit'];

function loadStateStrict(filePath) {
  // Never interpret an unreadable/missing baseline as "no alert has ever been sent".
  if (!fs.existsSync(filePath)) {
    throw new Error('KOFIA persisted state missing: refuse duplicate-prone bootstrap');
  }
  let state;
  try {
    state = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    throw new Error('KOFIA persisted state unreadable: ' + error.message);
  }
  if (!state || typeof state !== 'object' || Array.isArray(state)) {
    throw new Error('KOFIA persisted state must be an object');
  }
  if (!/^[a-f0-9]{64}$/.test(String(state.fingerprint || ''))) {
    throw new Error('KOFIA persisted fingerprint missing or malformed');
  }
  const date = String(state.snapshot_date || '');
  if (!/^\d{8}$/.test(date)) {
    throw new Error('KOFIA persisted snapshot date missing or malformed');
  }
  if (state.alignment_ready !== true || !state.dates || !state.values) {
    throw new Error('KOFIA persisted state missing critical alignment and values');
  }
  for (const key of CORE) {
    if (String(state.dates[key]) !== date || state.values[key]?.date !== date) {
      throw new Error('KOFIA persisted state date inconsistent for ' + key);
    }
    for (const field of ['value', 'd1', 'd5']) {
      const number = state.values[key]?.[field];
      if (typeof number !== 'number' || !Number.isFinite(number)) {
        throw new Error('KOFIA persisted metric invalid: ' + key + '.' + field);
      }
    }
  }
  for (const key of ['receivable', 'forced']) {
    const extra = state.values[key];
    if (!extra || extra.date !== date || typeof extra.value !== 'number' ||
        !Number.isFinite(extra.value) || extra.value < 0) {
      throw new Error('KOFIA persisted optional-lane value malformed: ' + key);
    }
  }
  const payload = Object.fromEntries(
    ['deposit','mmf','cma','credit','receivable','forced'].map(k=>[k,state.values[k]])
  );
  const computedFingerprint = crypto.createHash('sha256')
    .update(JSON.stringify(payload)).digest('hex');
  if (computedFingerprint !== state.fingerprint) {
    throw new Error('KOFIA persisted values/fingerprint inconsistent: refuse replay');
  }

  const ref = state.reference_dates;
  if (ref !== undefined) {
    if (!Array.isArray(ref) || ref.length !== 6 ||
        ref[0] !== date || new Set(ref).size !== 6 ||
        ref.some((d, i) => i > 0 && d >= ref[i-1])) {
      throw new Error('KOFIA persisted 1D/5D reference dates inconsistent');
    }
  }
  return state;
}

module.exports = { loadStateStrict };
