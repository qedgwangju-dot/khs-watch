'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const {loadStateStrict} = require('./kofia_liquidity_state_integrity');

const OUT_DIR = path.join(process.cwd(), 'out');
const STATE_FILE = path.join(process.cwd(), 'data', 'kofia_liquidity_state.json');
const ALERT_FILE = path.join(OUT_DIR, 'kofia_liquidity_alert.html');
const STATUS_FILE = path.join(OUT_DIR, 'kofia_liquidity_status.md');
const PENDING_FILE = path.join(OUT_DIR, 'kofia_liquidity_pending_state.json');
const EVIDENCE_FILE = path.join(OUT_DIR, 'kofia_liquidity_source_evidence.json');
const DELIVERY_FILE = path.join(OUT_DIR, 'kofia_liquidity_delivery.json');
const MESSAGE_VERSION = 'kofia-balances-20261013-v2';
const ORIGIN = 'https://freesis.kofia.or.kr';
let sourceEvidence;

function kstNow() {
  return new Date().toLocaleString('sv-SE', { timeZone: 'Asia/Seoul' }).replace(' ', 'T') + '+09:00';
}

function saveEvidence() {
  if (sourceEvidence) fs.writeFileSync(EVIDENCE_FILE, JSON.stringify(sourceEvidence, null, 2) + '\n', 'utf8');
}

const SID = {
  deposit: 'STATSCU0100000060',
  credit: 'STATSCU0100000070',
  cma: 'STATSCU0100000090',
  mmf: 'STATFND0400000050',
};

function ensureDirs(preserveEvidence = false) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  for (const f of [ALERT_FILE, STATUS_FILE, PENDING_FILE, DELIVERY_FILE]) {
    try { fs.unlinkSync(f); } catch (_) {}
  }
  if (!preserveEvidence) {
    try { fs.unlinkSync(EVIDENCE_FILE); } catch (_) {}
  }
}

function parseJsonMaybe(value) {
  let v = value;
  for (let i = 0; i < 3 && typeof v === 'string'; i++) v = JSON.parse(v);
  return v;
}

function toNum(v, label) {
  // Number(null), Number('') and Number('   ') are 0 in JavaScript.
  // Missing official KOFIA values must never silently turn into zero balances.
  if (v === null || v === undefined || (typeof v === 'string' && !v.trim())) {
    throw new Error(`${label}: missing official numeric value`);
  }
  if (!['number', 'string'].includes(typeof v)) throw new Error(`${label}: invalid numeric type`);
  const n = Number(typeof v === 'string' ? v.replace(/,/g, '').trim() : v);
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
  return loadStateStrict(STATE_FILE);
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

function criticalDatesAligned(dates) {
  const required = ['deposit', 'mmf', 'cma', 'credit'];
  const vals = required.map(k => String((dates || {})[k] || ''));
  return vals.every(validDate) && new Set(vals).size === 1;
}

function validDate(value) {
  if (!/^\d{8}$/.test(value)) return false;
  const day = new Date(`${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)}T00:00:00Z`);
  return Number.isFinite(day.getTime()) && day.toISOString().slice(0,10).replaceAll('-', '') === value;
}

// Production guard self-test: a mixed-date snapshot must never be considered aligned.
if (
  !criticalDatesAligned({ deposit: '20260929', mmf: '20260929', cma: '20260929', credit: '20260929' }) ||
  criticalDatesAligned({ deposit: '20260929', mmf: '20260928', cma: '20260929', credit: '20260929' })
) {
  throw new Error('critical date-alignment guard self-test failed');
}

async function main() {
  ensureDirs();
  const priorState = readState();
  sourceEvidence = {
    schema_version: 1, source: 'KOFIA FreeSIS', source_origin: ORIGIN,
    unit: '백만원', unit_won: 1000000, started_at_kst: kstNow(), phase: 'collecting',
    run_id: process.env.GITHUB_RUN_ID || null,
    code_sha: process.env.KOFIA_CODE_SHA || process.env.GITHUB_SHA || null, requests: [],
  };
  saveEvidence();
  const deadline = Date.now() + 240000;

  async function postJson(endpoint, body) {
    if (!['/meta/getSrvData.do', '/meta/getMetaDataList.do'].includes(endpoint)) throw new Error('Unknown source endpoint');
    for (let attempt = 1; attempt <= 2; attempt++) {
      const record = { endpoint, payload: body, attempt, requested_at_kst: kstNow() };
      sourceEvidence.requests.push(record);
      try {
        const remaining = deadline - Date.now();
        if (remaining <= 0) throw new Error('KOFIA collection deadline exceeded');
        const response = await fetch(ORIGIN + endpoint, {
          method: 'POST', redirect: 'error',
          headers: { 'Content-Type': 'application/json; charset=UTF-8', 'User-Agent': 'khs-watch/3.0' },
          body: JSON.stringify(body), signal: AbortSignal.timeout(Math.min(20000, remaining)),
        });
        const bytes = Buffer.from(await response.arrayBuffer());
        Object.assign(record, { status: response.status, response_url: response.url,
          content_type: response.headers.get('content-type'), response_text: bytes.toString('utf8'),
          response_body_base64: bytes.toString('base64'), response_bytes: bytes.length });
        record.response_sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
        saveEvidence();
        if (response.status !== 200) {
          const error = new Error(`${endpoint}: HTTP ${response.status}`);
          error.retryable = response.status >= 500 || response.status === 408;
          throw error;
        }
        return parseJsonMaybe(record.response_text);
      } catch (error) {
        record.error = String(error.message || error);
        saveEvidence();
        // Same URL and identity only. Denials, redirects and bad JSON are not retried.
        const transient = error.retryable || ['TimeoutError', 'AbortError'].includes(error.name)
          || (error instanceof TypeError && error.message === 'fetch failed'
              && !String(error.cause?.message || '').toLowerCase().includes('redirect'));
        if (attempt === 2 || !transient || Date.now() >= deadline) throw error;
        await new Promise(resolve => setTimeout(resolve, 300));
      }
    }
  }

  async function metadata(sid) {
    const j = await postJson('/meta/getSrvData.do', { dmSearchData: { strSvrId: sid } });
    const rd = (j.dsLatestDate || []).find(x => x.TMPV1 === 'RD');
    if (!rd || !validDate(String(rd.TMPV2 || ''))) throw new Error(`${sid}: latest RD date missing/invalid`);
    if (rd.TMPV2 > kstNow().slice(0,10).replaceAll('-', '')) throw new Error(`${sid}: future reference date`);
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
  const latestDates = { deposit: depMeta.latest, credit: crMeta.latest, mmf: mmfMeta.latest, cma: cmaMeta.latest };
  if (!criticalDatesAligned(latestDates)) {
    Object.assign(sourceEvidence, { phase: 'alignment_pending', latest_dates: latestDates, finished_at_kst: kstNow() });
    saveEvidence();
    fs.writeFileSync(STATUS_FILE, '# KOFIA Liquidity Watch\n\n- alignment_pending true\n- latest_dates '
      + JSON.stringify(latestDates) + '\n- alert_ready false\n', 'utf8');
    console.log('kofia_liquidity_alert_ready=false alignment_pending=true');
    return;
  }

  const depRows = await timeSeries(SID.deposit, dateMinusDays(depMeta.latest, 35), depMeta.latest);
  const crRows = await timeSeries(SID.credit, dateMinusDays(crMeta.latest, 35), crMeta.latest);
  if (depRows.length < 6) throw new Error(`Deposit series too short: ${depRows.length}`);
  if (crRows.length < 6) throw new Error(`Credit series too short: ${crRows.length}`);
  if (String(depRows[0].TMPV1) !== depMeta.latest) throw new Error(`Deposit latest mismatch: meta=${depMeta.latest} data=${depRows[0].TMPV1}`);
  if (String(crRows[0].TMPV1) !== crMeta.latest) throw new Error(`Credit latest mismatch: meta=${crMeta.latest} data=${crRows[0].TMPV1}`);

  const dep = depRows.slice(0, 6).map(r => ({
    date: String(r.TMPV1), value: toNum(r.TMPV2, `deposit ${r.TMPV1}`),
    receivable: toNum(r.TMPV5, `receivable ${r.TMPV1}`),
    forced: toNum(r.TMPV6, `forced ${r.TMPV1}`),
    forcedRatio: toNum(r.TMPV7, `forced ratio ${r.TMPV1}`),
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

  // The start and end of every 1D/5D calculation must also be the SAME
  // trading dates across all four official series. Checking latest dates
  // alone is not sufficient when one lane skips a reporting day.
  const referenceDates = dep.map(r => r.date);
  if (referenceDates.length !== 6 ||
      new Set(referenceDates).size !== 6 ||
      referenceDates.some((d, i) => i > 0 && d >= referenceDates[i-1])) {
    throw new Error('KOFIA deposit 1D/5D dates are not six distinct descending trading dates: ' + referenceDates.join(','));
  }
  for (const [name, values] of Object.entries({ credit, mmf, cma })) {
    const actualDates = values.map(r => r.date);
    if (actualDates.length !== referenceDates.length ||
        actualDates.some((date, i) => date !== referenceDates[i])) {
      throw new Error(`KOFIA 1D/5D reference-date mismatch ${name}: deposit=${referenceDates.join(',')} vs ${name}=${actualDates.join(',')}`);
    }
  }

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
  // A delayed API cache cannot roll back a previously delivered date.
  if (priorState && priorState.snapshot_date && depNow.date < priorState.snapshot_date) {
    throw new Error(`KOFIA date rolled back: stored=${priorState.snapshot_date} fetched=${depNow.date}`);
  }
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
  const alignmentReady = criticalDatesAligned(dates);
  const snapshotDate = alignmentReady ? dates.deposit : null;
  const sameDatesAsState = priorState && JSON.stringify(priorState.dates || {}) === JSON.stringify(dates);
  // A real interpretation correction keeps the unchanged official values and
  // is sent once per message version, after confirmed delivery only.
  const narrativeCorrection = Boolean(priorState && !changed &&
    priorState.snapshot_date === snapshotDate &&
    priorState.message_version !== MESSAGE_VERSION);
  const eventLabel = narrativeCorrection
    ? '해석 정정'
    : (!priorState ? '초기 기준 확정' : sameDatesAsState ? '동일 기준일 수정치' : '신규 공식값');
  const signal = strongMove ? '예탁금↑ + MMF↓ 동시 신호 강함' : big1d ? '당일 큰 변동 감지' : '공식값 갱신';

  const baselineLine = ''; // No hardcoded historical MMF baselines.
  const queriedAt = kstNow();
  const message = [
    `📊 <b>[국내 증시 대기자금 추적 | ${esc(eventLabel)}]</b>`,
    `KOFIA FreeSIS 공식 원자료 직접 조회`,
    `• 핵심 4개 지표 기준일 동기화: <b>${snapshotDate ? fmtDate(snapshotDate) : '미완료'}</b>`,
    `• 원자료 조회: ${queriedAt.replace('T',' ').replace('+09:00',' KST')}`,
    `• 비교 기준: 1D ${fmtDate(referenceDates[1])} → ${fmtDate(referenceDates[0])} / 5D ${fmtDate(referenceDates[5])} → ${fmtDate(referenceDates[0])}`,
    `• 1D는 직전 공표일, 5D는 최근 5개 공표구간의 잔액 차이`,
    ...(narrativeCorrection ? [
      `• <b>정정 사유</b>: 잔액만으로 위험자산 이동 가능성·수급의 질을 평가하던 문구와 비교 기준 설명을 수정. 공식 원값은 바뀌지 않았습니다.`
    ] : []),
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
    `• 투자자예탁금·MMF·CMA·신용융자 기준일이 모두 같은 날일 때만 종합 알림 전송`,
    `• MMF 1D는 공식 전일대비증감과 재계산값 일치 확인${mmfNow.daily !== metrics.mmf.d1 ? ' (백만원 표시 반올림 차이 1 이내)' : ''}`,
    `• 잔액 변화로 실제 주식 순매수·신규 자금·상품 간 이동 경로를 확인할 수 없음`,
    `• MMF형 CMA 등 상품 간 포함 관계가 있어 네 잔액을 합산하지 않음`,
    `• 신규 동기화 기준일·원값 수정 또는 확인된 해석 정정에만 재알림`,
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
    `- narrative_correction ${narrativeCorrection}`,
    `- message_version ${MESSAGE_VERSION}`,
    `- alignment_selftest true`,
    `- alignment_ready ${alignmentReady}`,
    `- snapshot_date ${snapshotDate || 'none'}`,
    `- critical_dates deposit=${dates.deposit} mmf=${dates.mmf} cma=${dates.cma} credit=${dates.credit}`,
    `- reference_date_alignment true`,
    `- common_reference_dates ${referenceDates.join(',')}`,
    `- 1d_reference_date ${referenceDates[1]} / 5d_reference_date ${referenceDates[5]}`,
    `- mmf_published_daily_delta ${mmfNow.daily} / recomputed ${mmfNow.value - mmfPrev.value}`,
    `- force_send ${forceSend}`,
    `- signal ${signal}`,
    `- source https://freesis.kofia.or.kr/stat/main.do`,
  ].join('\n');
  fs.writeFileSync(STATUS_FILE, status + '\n', 'utf8');
  Object.assign(sourceEvidence, { phase: 'validated', finished_at_kst: queriedAt, latest_dates: latestDates,
    reference_dates: referenceDates, values: fpPayload, fingerprint: fp,
    mmf_published_daily_delta: mmfNow.daily, prior_fingerprint: priorState.fingerprint,
    changed, narrative_correction: narrativeCorrection });
  saveEvidence();

  // Fail closed on mixed reference dates. FORCE_SEND can bypass duplicate suppression,
  // but never this data-quality gate.
  if (!alignmentReady) {
    console.log(
      `kofia_liquidity_alert_ready=false alignment_pending=true ` +
      `deposit=${dates.deposit} mmf=${dates.mmf} cma=${dates.cma} credit=${dates.credit}`
    );
    return;
  }

  if (changed || forceSend || narrativeCorrection) {
    fs.writeFileSync(ALERT_FILE, message + '\n', 'utf8');
    const nextState = {
      fingerprint: fp,
      snapshot_date: snapshotDate,
      alignment_ready: true,
      dates,
      reference_dates: referenceDates,
      values: fpPayload,
      message_version: MESSAGE_VERSION,
      last_event: eventLabel,
      source: 'KOFIA FreeSIS',
      source_url: 'https://freesis.kofia.or.kr/stat/main.do',
      queried_at_kst: sourceEvidence.finished_at_kst,
      code_sha: sourceEvidence.code_sha,
      period_basis: 'five_published_intervals',
      mmf_reported_daily_delta: mmfNow.daily,
      mmf_daily_rounding_difference: metrics.mmf.d1 - mmfNow.daily,
      prior_fingerprint: priorState.fingerprint,
    };
    fs.writeFileSync(PENDING_FILE, JSON.stringify(nextState, null, 2) + '\n', 'utf8');
    console.log(`kofia_liquidity_alert_ready=true event=${eventLabel} snapshot_date=${snapshotDate} fingerprint=${fp}`);
  } else {
    console.log(`kofia_liquidity_alert_ready=false unchanged=true snapshot_date=${snapshotDate} fingerprint=${fp}`);
  }
}

if (require.main === module) main().catch(err => {
  ensureDirs(true);
  if (sourceEvidence) { sourceEvidence.phase = 'failed'; sourceEvidence.error = String(err.message || err); saveEvidence(); }
  fs.writeFileSync(STATUS_FILE, `# KOFIA Liquidity Watch\n\n- status: FAILED\n- error: ${String(err && err.stack || err)}\n`, 'utf8');
  console.error(err);
  process.exit(1);
});

module.exports = { toNum, validDate, criticalDatesAligned, main };
