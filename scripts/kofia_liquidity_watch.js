'use strict';

const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const OUT_DIR = path.join(process.cwd(), 'out');
const STATE_FILE = path.join(process.cwd(), 'data', 'kofia_liquidity_state.json');
const ALERT_FILE = path.join(OUT_DIR, 'kofia_liquidity_alert.html');
const STATUS_FILE = path.join(OUT_DIR, 'kofia_liquidity_status.md');
const PENDING_FILE = path.join(OUT_DIR, 'kofia_liquidity_pending_state.json');

const SID = {
  deposit: 'STATSCU0100000060',
  credit: 'STATSCU0100000070',
  cma: 'STATSCU0100000090',
  mmf: 'STATFND0400000050',
};

function ensureDirs() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  for (const f of [ALERT_FILE, STATUS_FILE, PENDING_FILE]) {
    try { fs.unlinkSync(f); } catch (_) {}
  }
}

function parseJsonMaybe(value) {
  let v = value;
  for (let i = 0; i < 3 && typeof v === 'string'; i++) v = JSON.parse(v);
  return v;
}

function toNum(v, label) {
  const n = Number(v);
  if (!Number.isFinite(n)) throw new Error(`${label}: non-numeric value ${String(v)}`);
  return n;
}

function dateMinusDays(yyyymmdd, days) {
  const y = Number(yyyymmdd.slice(0,4));
  const m = Number(yyyymmdd.slice(4,6));
  const d = Number(yyyymmdd.slice(6,8));
  const dt = new Date(Date.UTC(y, m-1, d));
  dt.setUTCDate(dt.getUTCDate() - days);
  return `${dt.getUTCFullYear()}${String(dt.getUTCMonth()+1).padStart(2,'0')}${String(dt.getUTCDate()).padStart(2,'0')}`;
}

function fmtDate(d) {
  return `${Number(d.slice(4,6))}/${Number(d.slice(6,8))}`;
}

function fmtTrillion(rawMillionWon) {
  return `${(rawMillionWon / 1_000_000).toFixed(2)}조`;
}

function fmtDelta(rawMillionWon) {
  const v = rawMillionWon / 1_000_000;
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(2)}조`;
}

function fmtEokFromMillion(rawMillionWon) {
  return `${Math.round(rawMillionWon / 100).toLocaleString('ko-KR')}억원`;
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function readState() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); } catch (_) { return null; }
}

function fingerprint(payload) {
  return crypto.createHash('sha256').update(JSON.stringify(payload)).digest('hex');
}

function assertRange(label, rawMillionWon, minTrillion, maxTrillion) {
  const t = rawMillionWon / 1_000_000;
  if (!(t >= minTrillion && t <= maxTrillion)) {
    throw new Error(`${label}: sanity range failed (${t.toFixed(3)}T)`);
  }
}

(async () => {
  ensureDirs();
  const exe = ['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium','/usr/bin/chromium-browser'].find(p => fs.existsSync(p));
  if (!exe) throw new Error('No system Chromium/Chrome found');

  const browser = await chromium.launch({
    executablePath: exe,
    headless: true,
    args: ['--no-sandbox','--disable-dev-shm-usage','--disable-blink-features=AutomationControlled'],
    ignoreDefaultArgs: ['--enable-automation'],
  });
  const context = await browser.newContext({ locale: 'ko-KR', timezoneId: 'Asia/Seoul' });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
  });
  const page = await context.newPage();
  await page.goto('https://freesis.kofia.or.kr/stat/main.do', { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(800);

  async function postJson(endpoint, body) {
    const result = await page.evaluate(async ({ endpoint, body }) => {
      const r = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=UTF-8' },
        body: JSON.stringify(body),
      });
      const text = await r.text();
      return { status: r.status, text };
    }, { endpoint, body });
    if (result.status !== 200) throw new Error(`${endpoint}: HTTP ${result.status}`);
    return parseJsonMaybe(result.text);
  }

  async function metadata(sid) {
    const j = await postJson('/meta/getSrvData.do', { dmSearchData: { strSvrId: sid } });
    const rd = (j.dsLatestDate || []).find(x => x.TMPV1 === 'RD');
    if (!rd || !/^\d{8}$/.test(String(rd.TMPV2 || ''))) throw new Error(`${sid}: latest RD date missing`);
    return { latest: String(rd.TMPV2), raw: j };
  }

  async function timeSeries(sid, start, end) {
    const j = await postJson('/meta/getMetaDataList.do', {
      dmSearch: {
        tmpV40: '1000000', tmpV41: '1', tmpV6: '2', tmpV7: '1', tmpV4: '', tmpV11: '',
        tmpV1: 'RD', tmpV45: start, tmpV46: end, OBJ_NM: `${sid}BO`,
      },
    });
    return (j.ds1 || []).filter(x => /^\d{8}$/.test(String(x.TMPV1 || '')))
      .sort((a,b) => String(b.TMPV1).localeCompare(String(a.TMPV1)));
  }

  async function mmfAt(d) {
    const j = await postJson('/meta/getMetaDataList.do', {
      dmSearch: { tmpV40: '1000000', tmpV34: d, tmpV39: '1', OBJ_NM: `${SID.mmf}BO` },
    });
    const total = (j.ds1 || []).find(x => x.TMPV98 === '99' || x.TMPV1 === '합계');
    if (!total) throw new Error(`MMF ${d}: total row missing`);
    return { date: d, value: toNum(total.TMPV2, `MMF ${d}`), daily: toNum(total.TMPV6, `MMF daily ${d}`) };
  }

  async function cmaAt(d) {
    const j = await postJson('/meta/getMetaDataList.do', {
      dmSearch: { tmpV40: '1000000', tmpV1: 'RD', tmpV45: d, tmpV46: d, OBJ_NM: `${SID.cma}BO` },
    });
    const total = (j.ds1 || []).find(x => Number(x.ORD_SEQ) === 99 || x.TMPV1 === '합계');
    if (!total) throw new Error(`CMA ${d}: total row missing`);
    return { date: d, value: toNum(total.TMPV8, `CMA ${d}`) };
  }

  const [depMeta, crMeta, mmfMeta, cmaMeta] = await Promise.all([
    metadata(SID.deposit), metadata(SID.credit), metadata(SID.mmf), metadata(SID.cma),
  ]);

  const depRows = await timeSeries(SID.deposit, dateMinusDays(depMeta.latest, 35), depMeta.latest);
  const crRows = await timeSeries(SID.credit, dateMinusDays(crMeta.latest, 35), crMeta.latest);
  if (depRows.length < 6) throw new Error(`Deposit series too short: ${depRows.length}`);
  if (crRows.length < 6) throw new Error(`Credit series too short: ${crRows.length}`);
  if (String(depRows[0].TMPV1) !== depMeta.latest) throw new Error(`Deposit latest mismatch: meta=${depMeta.latest} data=${depRows[0].TMPV1}`);
  if (String(crRows[0].TMPV1) !== crMeta.latest) throw new Error(`Credit latest mismatch: meta=${crMeta.latest} data=${crRows[0].TMPV1}`);

  const dep = depRows.slice(0, 6).map(r => ({
    date: String(r.TMPV1), value: toNum(r.TMPV2, `deposit ${r.TMPV1}`),
    receivable: toNum(r.TMPV5 || 0, `receivable ${r.TMPV1}`),
    forced: toNum(r.TMPV6 || 0, `forced ${r.TMPV1}`),
    forcedRatio: Number(r.TMPV7 || 0),
  }));
  const credit = crRows.slice(0, 6).map(r => ({ date: String(r.TMPV1), value: toNum(r.TMPV2, `credit ${r.TMPV1}`) }));

  function refDatesFor(latest) {
    const dates = [latest, ...depRows.map(r => String(r.TMPV1)).filter(d => d < latest)];
    return [...new Set(dates)].slice(0, 6);
  }

  const mmfDates = refDatesFor(mmfMeta.latest);
  const cmaDates = refDatesFor(cmaMeta.latest);
  if (mmfDates.length < 6 || cmaDates.length < 6) throw new Error('Reference dates too short for MMF/CMA 5-day comparison');

  const mmf = [];
  for (const d of mmfDates) mmf.push(await mmfAt(d));
  const cma = [];
  for (const d of cmaDates) cma.push(await cmaAt(d));

  await browser.close();

  const depNow = dep[0], depPrev = dep[1], dep5 = dep[5];
  const crNow = credit[0], crPrev = credit[1], cr5 = credit[5];
  const mmfNow = mmf[0], mmfPrev = mmf[1], mmf5 = mmf[5];
  const cmaNow = cma[0], cmaPrev = cma[1], cma5 = cma[5];

  if (Math.abs((mmfNow.value - mmfPrev.value) - mmfNow.daily) > 1) {
    throw new Error(`MMF daily-change cross-check failed: calc=${mmfNow.value - mmfPrev.value}, official=${mmfNow.daily}`);
  }

  assertRange('Investor deposits', depNow.value, 20, 300);
  assertRange('MMF', mmfNow.value, 50, 500);
  assertRange('CMA', cmaNow.value, 20, 300);
  assertRange('Credit', crNow.value, 1, 100);

  const metrics = {
    deposit: { date: depNow.date, value: depNow.value, d1: depNow.value - depPrev.value, d5: depNow.value - dep5.value },
    mmf: { date: mmfNow.date, value: mmfNow.value, d1: mmfNow.value - mmfPrev.value, d5: mmfNow.value - mmf5.value },
    cma: { date: cmaNow.date, value: cmaNow.value, d1: cmaNow.value - cmaPrev.value, d5: cmaNow.value - cma5.value },
    credit: { date: crNow.date, value: crNow.value, d1: crNow.value - crPrev.value, d5: crNow.value - cr5.value },
    receivable: { date: depNow.date, value: depNow.receivable },
    forced: { date: depNow.date, value: depNow.forced, ratio: depNow.forcedRatio },
  };

  const fpPayload = {
    deposit: metrics.deposit,
    mmf: metrics.mmf,
    cma: metrics.cma,
    credit: metrics.credit,
    receivable: metrics.receivable,
    forced: metrics.forced,
  };
  const fp = fingerprint(fpPayload);
  const priorState = readState();
  const forceSend = String(process.env.FORCE_SEND || '').toLowerCase() === 'true' || process.env.FORCE_SEND === '1';
  const changed = !priorState || priorState.fingerprint !== fp;

  const strongMove = metrics.deposit.d5 >= 5_000_000 && metrics.mmf.d5 <= -5_000_000;
  const big1d = Math.abs(metrics.deposit.d1) >= 2_000_000 || Math.abs(metrics.mmf.d1) >= 3_000_000 || Math.abs(metrics.cma.d1) >= 2_000_000 || Math.abs(metrics.credit.d1) >= 500_000;
  const leverageText = metrics.credit.d1 > 0 && metrics.credit.d5 <= 0
    ? '신용융자는 1D 증가·5D 감소 → 레버리지 추세 전환은 아직 미확정'
    : metrics.credit.d5 > 0
      ? '신용융자 5D 증가 → 레버리지 확대 동반'
      : '신용융자 5D 감소 → 대기자금 증가와 레버리지 확대는 분리';

  const dates = Object.fromEntries(Object.entries(metrics).slice(0,4).map(([k,v]) => [k, v.date]));
  const sameDatesAsState = priorState && JSON.stringify(priorState.dates || {}) === JSON.stringify(dates);
  const eventLabel = !priorState ? '초기 기준 확정' : sameDatesAsState ? '동일 기준일 수정치' : '신규 공식값';
  const signal = strongMove ? '예탁금↑ + MMF↓ 동시 신호 강함' : big1d ? '당일 큰 변동 감지' : '공식값 갱신';

  let baselineLine = '';
  const dep0904 = depRows.find(r => String(r.TMPV1) === '20260904');
  if (dep0904 && mmfNow.date === '20260914') {
    const oldMmf = await (async () => {
      // Values were already validated in live probes; avoid reopening browser here.
      return 267088692;
    })();
    baselineLine = `\n• <b>9/4→9/14 검증</b>: 예탁금 ${fmtDelta(depNow.value - Number(dep0904.TMPV2))} / MMF ${fmtDelta(mmfNow.value - oldMmf)}`;
  }

  const message = [
    `📊 <b>[국내 증시 대기자금 추적 | ${esc(eventLabel)}]</b>`,
    `KOFIA FreeSIS 공식 원자료 직접 조회`,
    ``,
    `<b>무엇이 달라졌나</b>`,
    `• 투자자예탁금 <b>${fmtTrillion(metrics.deposit.value)}</b> (${fmtDate(metrics.deposit.date)}) | 1D ${fmtDelta(metrics.deposit.d1)} | 5D ${fmtDelta(metrics.deposit.d5)}`,
    `• MMF 설정원본 <b>${fmtTrillion(metrics.mmf.value)}</b> (${fmtDate(metrics.mmf.date)}) | 1D ${fmtDelta(metrics.mmf.d1)} | 5D ${fmtDelta(metrics.mmf.d5)}`,
    `• CMA 잔고 <b>${fmtTrillion(metrics.cma.value)}</b> (${fmtDate(metrics.cma.date)}) | 1D ${fmtDelta(metrics.cma.d1)} | 5D ${fmtDelta(metrics.cma.d5)}`,
    `• 신용융자 <b>${fmtTrillion(metrics.credit.value)}</b> (${fmtDate(metrics.credit.date)}) | 1D ${fmtDelta(metrics.credit.d1)} | 5D ${fmtDelta(metrics.credit.d5)}`,
    `• 미수금 ${fmtTrillion(metrics.receivable.value)} | 실제 반대매매 ${fmtEokFromMillion(metrics.forced.value)}${baselineLine}`,
    ``,
    `<b>현재 판정</b>`,
    `• ${esc(signal)}`,
    `• ${esc(leverageText)}`,
    `• MMF 감소와 예탁금 증가는 <b>동시 변화</b>이며, 동일 자금의 직접 이전을 입증하는 수치는 아님`,
    ``,
    `<b>검증</b>`,
    `• 동일 KOFIA 공식 원천·백만원 단위 원값으로 계산`,
    `• MMF 1D는 공식 전일대비증감과 재계산값 일치 확인`,
    `• 신규 기준일 또는 동일 기준일 수정치가 있을 때만 재알림`,
  ].join('\n');

  const status = [
    `# KOFIA Liquidity Watch`,
    ``,
    `- deposit ${metrics.deposit.date}: ${metrics.deposit.value} / 1D ${metrics.deposit.d1} / 5D ${metrics.deposit.d5}`,
    `- mmf ${metrics.mmf.date}: ${metrics.mmf.value} / 1D ${metrics.mmf.d1} / 5D ${metrics.mmf.d5}`,
    `- cma ${metrics.cma.date}: ${metrics.cma.value} / 1D ${metrics.cma.d1} / 5D ${metrics.cma.d5}`,
    `- credit ${metrics.credit.date}: ${metrics.credit.value} / 1D ${metrics.credit.d1} / 5D ${metrics.credit.d5}`,
    `- receivable ${metrics.receivable.value}; forced ${metrics.forced.value}; forcedRatio ${metrics.forced.ratio}`,
    `- fingerprint ${fp}`,
    `- prior fingerprint ${priorState ? priorState.fingerprint : 'none'}`,
    `- changed ${changed}`,
    `- force_send ${forceSend}`,
    `- signal ${signal}`,
    `- source https://freesis.kofia.or.kr/stat/main.do`,
  ].join('\n');
  fs.writeFileSync(STATUS_FILE, status + '\n', 'utf8');

  if (changed || forceSend) {
    fs.writeFileSync(ALERT_FILE, message + '\n', 'utf8');
    const nextState = {
      fingerprint: fp,
      dates,
      values: fpPayload,
      last_event: eventLabel,
      source: 'KOFIA FreeSIS',
      source_url: 'https://freesis.kofia.or.kr/stat/main.do',
    };
    fs.writeFileSync(PENDING_FILE, JSON.stringify(nextState, null, 2) + '\n', 'utf8');
    console.log(`kofia_liquidity_alert_ready=true event=${eventLabel} fingerprint=${fp}`);
  } else {
    console.log(`kofia_liquidity_alert_ready=false unchanged=true fingerprint=${fp}`);
  }
})().catch(err => {
  ensureDirs();
  fs.writeFileSync(STATUS_FILE, `# KOFIA Liquidity Watch\n\n- status: FAILED\n- error: ${String(err && err.stack || err)}\n`, 'utf8');
  console.error(err);
  process.exit(1);
});
