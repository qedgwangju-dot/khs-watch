"""Keep sanctions and diplomatic reactions separate from reported attacks."""
from __future__ import annotations

import html
import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
import datetime as dt

import war_peace_reconstruction_watch_oct04_guard as previous
import war_peace_reconstruction_watch_bodycolor_parallel as body_parallel

watch, runner = previous.watch, previous.runner
_score, _color = watch.score_item, previous.final_color
_topic, _build = watch.topic_label, watch.build_alert
_verdict = previous.guard._verdict
_future_refinery = previous._future_refinery_policy
_verify = runner.verify_alert
KIND_LABELS = {'sanctions': '제재·압박', 'reaction': '외교반응·개입검토',
               'attack_pause': '공격 중단·부인 발언'}


def refinery_attack_denial(row):
    title = html.unescape(str(row.get('title_original') or row.get('title') or '')).lower()
    # Keep the denial in the same headline clause as the Ukrainian actor and
    # refinery target. The opponent's "continues attacks" clause is separate.
    first = re.split(r'…|\.{3}|[;；]', title)[0]
    actor = re.search(r'젤렌스키|우크라이나|\b(?:ukraine|zelenskyy?|zelenskiy)\b', first)
    target = re.search(r'정유시설|정유소|정유 공장|\brefiner(?:y|ies)\b', first)
    denial = re.search(r'(?:공격|타격|공습)(?:을|하지)?\s*(?:안\s*(?:했|한|해)|하지\s*않|않았|중단|멈)|'
                       r'\b(?:did not|has not|have not)\s+(?:attack|strike|hit|bomb)', first)
    return bool(actor and target and denial and actor.start() < denial.start())


def future_refinery_policy(row):
    return not refinery_attack_denial(row) and _future_refinery(row)


def non_military_kind(row):
    title = html.unescape(str(row.get('title_original') or row.get('title') or row.get('title_ko') or '')).lower()
    # Require an explicit new-action predicate before background weapon nouns
    # can turn a sanctions listing or a condemnation into a military event.
    actual = bool(re.search(
        r'공습\s*(?:개시|재개|감행)|공격\s*(?:개시|재개|감행)|미사일\s*발사|'
        r'보복\s*(?:공습|공격)\s*(?:개시|실시)|'
        r'\band\s+(?:attacks?|strikes?|bombs?)\b|'
        r'\b(?:launches?|launched|conducts?|conducted|resumes?|resumed)\s+(?:new\s+)?(?:attacks?|strikes?|airstrikes?)',
        title))
    if actual:
        return None
    if refinery_attack_denial(row):
        return 'attack_pause'
    if re.search(r'제재|\bsanctions?\b|restrictive measures', title):
        if not re.search(r'공항.*피격|드론.*공격|\b(?:attacked|struck|bombed)\b', title):
            return 'sanctions'
    if re.search(r'규탄|비난|\bcondemns?\b|\bdenounces?\b', title):
        return 'reaction'
    return None


def score_item(row, now):
    score, tags = _score(row, now)
    kind = non_military_kind(row)
    if kind and score > 0:
        row['non_military_kind'] = kind
        row['signals_ko'] = []
        tags = [tag for tag in tags if tag not in ('확전', '확전위험', '재확전위험', '휴전·평화')]
        tags = [tag for tag in tags if tag != '공격확대예고']
        tags.append(KIND_LABELS[kind])
    return score, tags


def final_color(row):
    return 'yellow' if non_military_kind(row) else _color(row)


def topic_label(row):
    topic = _topic(row)
    kind = non_military_kind(row)
    if kind:
        topic = topic.split(' · ')[0]
        topic += ' · ' + KIND_LABELS[kind]
    return topic


def verdict(items):
    kinds = [non_military_kind(row) for row in items]
    if kinds and all(kinds):
        core = ('공격 중단·부인 발언과 제재·외교반응 관련 보도' if 'attack_pause' in kinds else
                '제재·외교적 규탄·군사개입 검토 관련 보도')
        return (
            '<b>투자 판정</b>\n'
            f'- <b>핵심:</b> {core}\n'
            '- <b>현재 단계:</b> 발언·경제·외교 조치와 검토 단계 — 새로운 군사작전 개시는 확인되지 않음\n'
            + ('- <b>확인:</b> 공격 중단 발언만으로 양측 휴전 합의·실제 이행이 확인되지는 않음\n' if 'attack_pause' in kinds else '')
            +
            '- <b>시장:</b> 거래 제한·협상 제약의 영향은 가능하나 유가·해운·보험료 방향은 별도 관측 필요\n'
            '- <b>다음:</b> 제재 발효·대상 확인 → 공식 군사 명령 여부 → 실제 작전·운영 영향'
        )
    # Weapon/attack words cited as the reason for sanctions or condemnation
    # must not decide the military stage of another negotiation item.
    other_items = [row for row, kind in zip(items, kinds) if not kind]
    text = _verdict(other_items)
    return text.replace(
        '- <b>시장:</b> 유가·해운·보험 위험프리미엄 상승 압력',
        '- <b>조건부 영향:</b> 추가 공격·운영 차질이 확대되면 유가·해운·보험 위험프리미엄 상승 가능')


def _publication_label(row, now):
    metadata = row.get('source_metadata') or {}
    if metadata.get('publication_status') == 'conflict':
        candidates = metadata.get('publication_candidates') or []
        visible = next((x['at_kst'] for x in candidates if x['field'].startswith('visible:')), None)
        machine = next((x['at_kst'] for x in candidates if not x['field'].startswith('visible:')), None)
        if visible and machine:
            return f"보도시각 불일치 · 원문 표기 {visible[5:16].replace('T', ' ')} / 메타 {machine[5:16].replace('T', ' ')} KST"
        return '보도시각 불일치 · 원문 내 공표시각이 서로 다름'
    stamp = watch.parse_pub(row.get('published'))
    if stamp is None:
        return '보도시각 확인 불가'
    prefix = '보도' if metadata.get('publication_status') == 'verified' else 'RSS 보도'
    age = watch.age_minutes(row, now)
    return f'{prefix} {stamp:%m-%d %H:%M} KST · <b>{age}분 경과</b>'


def build_alert(items, markets, now):
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(items)))) as executor:
        list(executor.map(body_parallel._safe_enrich, items[:8]))
    visible = []
    for row in items:
        metadata = row.get('source_metadata') or {}
        dates = [dt.datetime.fromisoformat(value['at_kst']) for value in metadata.get('publication_candidates', [])]
        if dates and (min(dates) < now - dt.timedelta(hours=3) or max(dates) > now + dt.timedelta(minutes=5)):
            row['render_withheld'] = 'origin_publication_stale_or_future'
            continue
        visible.append(row)
    if not visible:
        return ''
    for row in items:
        kind = non_military_kind(row)
        if kind:
            row['non_military_kind'] = kind
            row['tags'] = [tag for tag in row.get('tags', []) if tag not in ('확전', '확전위험', '공격확대예고')]
            row['tags'].append(KIND_LABELS[kind])
            row['signals_ko'] = []
    text = _build(visible, markets, now)
    lines = text.splitlines()
    positions = [i for i, line in enumerate(lines) if re.match(r'^[🔴🟢🟡]?\s*\[(?:신규|속보|후속)\]\s*<b>\d+\.', line)]
    for n, start in enumerate(positions):
        end = positions[n + 1] if n + 1 < len(positions) else len(lines)
        block = '\n'.join(lines[start:end])
        urls = {html.unescape(value) for value in re.findall(r'<a href="([^"]+)"', block)}
        row = next((row for row in items if {row.get('link'), row.get('resolved_url')} & urls), None)
        if row is None:
            continue
        kind = non_military_kind(row)
        color = final_color(row)
        row['classification_color'] = color
        marker = {'red': '🔴 ', 'yellow': '🟡 ', 'green': '🟢 '}.get(color, '')
        lines[start] = re.sub(r'^[🔴🟢🟡]?\s*', marker, lines[start])
        if kind == 'attack_pause':
            # Preserve the original speaker and both clauses instead of the
            # older template's invented promise to increase Ukrainian strikes.
            lines[start + 1] = html.escape(str(row.get('title_ko') or row.get('title_original') or ''))
        for i in range(start + 1, end):
            line_urls = {html.unescape(value) for value in re.findall(r'<a href="([^"]+)"', lines[i])}
            if not line_urls & {row.get('link'), row.get('resolved_url')}:
                continue
            if ' KST · ' in lines[i] and '<b>' in lines[i]:
                tail = re.split(r'</b>\s*·\s*', lines[i], maxsplit=1)
                if len(tail) == 2:
                    lines[i] = _publication_label(row, now) + ' · ' + tail[1]
            if kind:
                lines[i] = lines[i].replace(' · 확전 · ', ' · ' + KIND_LABELS[kind] + ' · ')
            if not row.get('body_verified') and 'news.google.com/' in str(row.get('link')):
                lines[i] = lines[i].replace(' 원문</a>', ' 검색 링크</a>')
                lines[i] += ' · 제목 기준·본문 미확인'
    # The final header must describe the rendered event kinds, including after
    # the older text-level color guard has scanned background attack words.
    before_items = positions[0] if positions else len(lines)
    lines = [line for i, line in enumerate(lines) if not (i < before_items and any(
        badge in line for badge in ('<b>공격·확전</b>', '<b>재건·휴전</b>', '<b>군사위협·협상 제약</b>', '<b>협상 제약·불확실성</b>')))]
    rendered = '\n'.join(lines)
    badges = []
    rendered_urls = {html.unescape(value) for value in re.findall(r'<a href="([^"]+)"', rendered)}
    rendered_rows = [row for row in visible if {row.get('link'), row.get('resolved_url')} & rendered_urls]
    yellow_others = any(not non_military_kind(row) and final_color(row) == 'yellow' for row in rendered_rows)
    yellow_label = '군사위협·협상 제약' if yellow_others else '발언·제재·외교반응·협상 제약'
    for marker, label in [('🔴', '공격·확전'), ('🟢', '재건·휴전'), ('🟡', yellow_label)]:
        if re.search(r'(?m)^' + marker + r'\s*\[(?:신규|속보|후속)\]', rendered):
            badges.append(f'{marker} <b>{label}</b>')
    if yellow_others and any(non_military_kind(row) for row in rendered_rows):
        badges.append('🟡 <b>제재·외교반응</b>')
    if badges:
        lines.insert(1, '  |  '.join(badges))
    if any(' KST' in line and '조회' in line for line in lines):
        at = next(i for i, line in enumerate(lines) if '조회' in line and ' KST' in line)
        lines.insert(at + 1, '기사 시각 기준 · 실제 사건 발생시각과 구분')
    for market in markets:
        needle = f"{market['name']}  <b>{market['price']:,.2f}</b>  {market['pct']:+.2f}%"
        for i, line in enumerate(lines):
            if needle in line:
                lines[i] += f" · {html.escape(market.get('source', '출처 확인 대기'))} {html.escape(market.get('symbol', ''))}"
    missing = [row for row in getattr(watch, 'market_source_status', {}).values() if row.get('status') != 'available']
    if missing:
        at = next((i for i, line in enumerate(lines) if line == '<b>투자 판정</b>'), len(lines))
        note = '시장자료 확인 보류 · ' + ' / '.join(f"{row['name']} ({row['reason']})" for row in missing)
        lines.insert(at, html.escape(note))
        lines.insert(at + 1, '')
    return '\n'.join(lines).strip() + '\n'


def verify_alert(test_mode=False):
    _verify(test_mode=test_mode)
    if not watch.ALERT.exists() or not watch.AUDIT.exists():
        return
    text = watch.ALERT.read_text(encoding='utf-8').strip()
    receipt = json.loads(watch.AUDIT.read_text(encoding='utf-8'))
    if receipt['alert_sha256'] != hashlib.sha256(text.encode()).hexdigest():
        raise RuntimeError('WAR_INTEGRITY_GATE: alert/evidence hash mismatch')
    rows = [row for row in receipt['articles'] if row.get('rendered')]
    pending = json.loads(watch.PENDING.read_text(encoding='utf-8'))['ids']
    ids = [row['id'] for row in rows]
    if set(ids) != set(pending) or len(ids) != len(pending) or len(ids) != len(set(ids)):
        raise RuntimeError('WAR_INTEGRITY_GATE: pending differs from rendered source IDs')
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if re.match(r'^[🔴🟢🟡]?\s*\[(?:신규|속보|후속)\]\s*<b>\d+\.', line)]
    if len(starts) != len(rows):
        raise RuntimeError('WAR_INTEGRITY_GATE: item/source evidence count mismatch')
    matched = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        block = '\n'.join(lines[start:end])
        urls = {html.unescape(url) for url in re.findall(r'<a href="([^"]+)"', block)}
        candidates = [row for row in rows if {row.get('link'), row.get('resolved_url')} & urls]
        if len(candidates) != 1:
            raise RuntimeError('WAR_INTEGRITY_GATE: item lacks unique source evidence')
        row = candidates[0]
        matched.append(row['id'])
        marker = {'red': '🔴', 'green': '🟢', 'yellow': '🟡'}.get(row.get('classification_color'), '')
        if marker and not lines[start].startswith(marker):
            raise RuntimeError('WAR_INTEGRITY_GATE: final marker differs from event stage')
        if row.get('non_military_kind') == 'attack_pause' and any(
                phrase in block for phrase in ('공격 확대 방침', '공격확대예고')):
            raise RuntimeError('WAR_INTEGRITY_GATE: attack denial rewritten as escalation')
    if set(matched) != set(ids):
        raise RuntimeError('WAR_INTEGRITY_GATE: duplicated or omitted rendered source')
    for row in receipt['markets']:
        price, close, pct = row['price'], row['previous_close'], row['pct']
        if not all(math.isfinite(value) for value in (price, close, pct)) or price <= 0 or close <= 0:
            raise RuntimeError('WAR_INTEGRITY_GATE: invalid market operands')
        if not math.isclose(pct, (price / close - 1) * 100, rel_tol=1e-12, abs_tol=1e-9):
            raise RuntimeError('WAR_INTEGRITY_GATE: market change differs from saved operands')
        if row.get('previous_close_date_verified') is False and '전일' in row.get('basis', ''):
            raise RuntimeError('WAR_INTEGRITY_GATE: undated comparison close labelled as previous day')


watch.score_item, watch.topic_label, watch.build_alert = score_item, topic_label, build_alert
previous.final_color = final_color
previous.prev._final_item_color = final_color
previous.prev._emergency_color = final_color
previous.guard._enhanced_body_color = final_color
previous.guard.prev._strict_body_color = final_color
previous.guard.prev.core._body_color = final_color
previous.guard._verdict = verdict
previous._future_refinery_policy = future_refinery_policy
runner.verify_alert = verify_alert


if __name__ == '__main__':
    raise SystemExit(previous.main())
