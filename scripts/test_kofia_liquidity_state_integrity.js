'use strict';
const assert = require('assert');
const fs = require('fs');
const crypto = require('crypto');
const os = require('os');
const path = require('path');
const {loadStateStrict} = require('./kofia_liquidity_state_integrity');

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'kofia_state_guard_'));
const file = path.join(root, 'state.json');
const date = '20261007';
const values = Object.fromEntries(['deposit','mmf','cma','credit'].map(k=>[
  k, {date, value: k === 'mmf' ? 262894698 : 100379607, d1: k === 'mmf' ? 4928506 : -669020, d5: k === 'mmf' ? 24445118 : -7346063}
]));
values.receivable = {date, value: 931602};
values.forced = {date, value: 19220, ratio: 2};
const base={
  fingerprint: 'a'.repeat(64),
  snapshot_date: date,
  alignment_ready: true,
  dates: Object.fromEntries(Object.keys(values).map(k=>[k,date])),
  reference_dates: ['20261007','20261006','20261002','20261001','20260930','20260929'],
  values,
};
base.fingerprint=crypto.createHash('sha256')
  .update(JSON.stringify(values)).digest('hex');

const check = (name, state, fails) => {
  if (state !== null) fs.writeFileSync(file,typeof state==='string' ? state : JSON.stringify(state));
  else if (fs.existsSync(file)) fs.unlinkSync(file);
  if (fails) assert.throws(()=>loadStateStrict(file), Error, name);
  else assert.deepStrictEqual(loadStateStrict(file), state, name);
  console.log('PASS '+name);
};

try {
  check('valid baseline', base, false);
  check('missing state must block', null, true);
  check('corrupt JSON must block', '{bad-json', true);
  check('missing fingerprint must block', {...base,fingerprint:''}, true);
  check('wrong snapshot date must block', {...base,snapshot_date:'20261006'}, true);
  check('misaligned dates must block', {...base,dates:{...base.dates,mmf:'20261006'}}, true);
  check('missing numeric value must block', {...base,values:{...base.values,mmf:{...base.values.mmf,d1:null}}}, true);
  check('tampered but valid-looking metric must block', {...base,values:{...base.values,mmf:{...base.values.mmf,d1:4928507}}}, true);
  check('duplicate 5D reference date must block', {...base,reference_dates:['20261007','20261006','20261002','20261001','20260930','20260930']}, true);
  console.log('PASS all KOFIA persisted-state failure-mode tests');
} finally {
  fs.rmSync(root,{recursive:true,force:true});
}
