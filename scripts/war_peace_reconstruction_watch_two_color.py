"""Project verified event stages into the user's two directional alert colors.

The event-stage verifier runs before presentation. Its exact inputs remain as
sidecars so a repeated final check can verify both factual stages and the final
payload. This module does not collect, send, select articles, or modify state.
"""
from __future__ import annotations

import copy
import base64
import hashlib
import html
import json
from pathlib import Path
import re
import tempfile
from unittest.mock import patch

POLICY = 'war-direction-two-color-v1'
STAGE_ALERT = 'war_peace_reconstruction_stage_alert.txt'
STAGE_EVIDENCE = 'war_peace_reconstruction_stage_evidence.json'
MARKERS = {'red': '🔴', 'green': '🟢'}
REFERENCE_KINDS = frozenset(('commodity_market', 'market_effect', 'market_reaction',
                             'oil_market', 'corporate_spending'))
RISK_KINDS = frozenset(('sanctions', 'security_activity', 'military_discussion',
                        'military_analysis', 'military_report', 'reaction',
                        'operational_disruption', 'oil_pressure', 'fuel_shipping',
                        'mixed_restraint'))
CONSTRUCTIVE_KINDS = frozenset(('diplomatic_contact', 'diplomatic_plan',
                                'diplomatic_statement', 'diplomatic_analysis',
                                'diplomatic_appeal', 'trade_proposal',
                                'support_statement', 'attack_pause',
                                'ceasefire_position', 'diplomatic_position'))
DIPLOMATIC_TAGS = frozenset(('종전·협상', '휴전·평화'))
ITEM_START = re.compile(r'^[🔴🟢🟡]?\s*\[(?:신규|속보|후속)\]\s*<b>\d+\.')
ADVERSE = re.compile(
    r'압박|제재|결렬|교착|지연|미루|붕괴|무너|걷어찼|거부|배제|봉쇄|보복|'
    r'(?:협상|대화|회담|휴전|정전).{0,10}(?:파기|중단|종료|무산|불발|깨졌|거절)|'
    r'공격\s*(?:예고|경고|위협|계획)|공습\s*(?:예고|검토)|파괴공작|'
    r'\b(?:pressure|sanctions?|stalemate|deadlock|delay\w*|reject\w*|refus\w*|'
    r'exclud\w*|blockade|retaliat\w*|threaten\w*|collapse\w*)\b')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _fail(reason):
    raise RuntimeError('WAR_TWO_COLOR_GATE: ' + reason)


def _active_adverse(title):
    for match in ADVERSE.finditer(title):
        before = title[max(0, match.start() - 32):match.start()]
        after = title[match.end():match.end() + 24]
        if re.match(r'(?:을|를|는|은)?\s*(?:해제|완화|철회|중단)', after):
            continue
        if re.search(r'\b(?:lift\w*|ease\w*|end\w*|remove\w*)\s+(?:\w+\s+){0,2}$', before):
            continue
        if re.match(r'(?:설|할\s*의도)?(?:을|를|는|은|이|가)?\s*'
                    r'(?:하지\s*않|않겠|없|부인|아니)', after):
            continue
        if re.search(r'\b(?:not|no|never|denies?|denied)\s+(?:\w+\s+){0,2}$', before):
            continue
        return True
    return False


def _separate_attack_headline(title):
    """An explicit current attack in the headline wins over any easing clause."""
    return bool(re.search(
        r'\b(?:resum\w*|launch\w*|conduct\w*|start\w*|carry(?:ing)?\s+out)\b'
        r'.{0,35}\b(?:attacks?|airstrikes?|strikes?|bombardments?)\b|'
        r'\b(?:attacks?|airstrikes?|strikes?|bombardments?)\b.{0,20}'
        r'\b(?:resum\w*|launch\w*|continu\w*)\b|'
        r'(?:공습|공격|폭격|포격)(?:을|를|이|가)?\s*(?:재개|감행|실시|시작)|'
        r'(?:재개|감행|실시|시작).{0,12}(?:공습|공격|폭격|포격)', title))


def _explicit_easing_restoration(title):
    """Recognize a headline reporting that a restriction or service was restored."""
    if _active_adverse(title) or _separate_attack_headline(title):
        return False
    return bool(re.search(
        r'\b(?:speed|service|access|connectivity|network|operations?)\s+'
        r'(?:restrictions?|limitations?|limits?)\b.{0,45}'
        r'\b(?:lifted|removed|eased|relaxed|restored|reinstated)\b|'
        r'\b(?:restrictions?|limitations?|limits?)\b.{0,45}'
        r'\b(?:lifted|removed|eased|relaxed)\b|'
        r'\b(?:lifted|removed|eased|relaxed)\b.{0,45}'
        r'\b(?:restrictions?|limitations?|limits?)\b|'
        r'\b(?:service|speed|access|connectivity|network)\b.{0,40}'
        r'\b(?:restored|resumed|reinstated|reopened)\b|'
        r'(?:속도|서비스|접속|연결|네트워크).{0,20}'
        r'(?:제한|차단|중단).{0,18}(?:해제|완화|복구|재개)|'
        r'(?:제한|차단|중단).{0,20}(?:해제|완화|복구|재개).{0,20}'
        r'(?:속도|서비스|접속|연결|네트워크)|'
        r'(?:속도|서비스|접속|연결|네트워크).{0,20}(?:복구|정상화|재개|회복)', title))


def _explicit_ceasefire_progress(title):
    """Recognize a reported ceasefire confirmation or active date coordination."""
    negative = re.search(
        r'\b(?:no|not|never|den\w*|reject\w*|refus\w*)\b.{0,35}'
        r'\b(?:cease[- ]?fire|truce)\b|'
        r'\b(?:cease[- ]?fire|truce)\b.{0,35}'
        r'\b(?:not|never|den\w*|reject\w*|refus\w*|unconfirmed|unverified)\b|'
        r'(?:휴전|정전).{0,20}(?:아니|부인|거부|불발|미확인|확인되지 않)', title)
    if negative:
        return False
    if _separate_attack_headline(title):
        return False
    return bool(re.search(
        r'\b(?:confirm\w*|coordinat\w*|cooperat\w*|collaborat\w*|agree\w*|'
        r'implement\w*|extend\w*|resume\w*)\b.{0,80}'
        r'\b(?:cease[- ]?fire|truce)\b|'
        r'\b(?:cease[- ]?fire|truce)\b.{0,80}'
        r'\b(?:confirm\w*|coordinat\w*|cooperat\w*|collaborat\w*|agree\w*|'
        r'implement\w*|extend\w*|resume\w*)\b|'
        r'(?:휴전|정전).{0,40}(?:확인|조율|협의|협력|합의|발효|연장|재개)', title))


def direction(stage, row):
    """Return a display color, or None for a neutral market reference."""
    kind = stage.non_military_kind(row)
    color = stage.final_color(row)
    title = stage._headline(row)
    # A separate actual action wins over a diplomatic or financial background.
    if color == 'red':
        return 'red'
    if kind in REFERENCE_KINDS:
        return None
    adverse = _active_adverse(title)
    # A headline-confirmed easing/restoration is green even if inherited
    # background tags would otherwise fall through to the red default. A
    # separate current attack or adverse clause still keeps the item red.
    if _explicit_easing_restoration(title) and not adverse:
        return 'green'
    if stage._attack_plan_status(title) in ('held', 'denied') and not adverse:
        return 'green'
    if kind == 'sanctions' and not adverse and re.search(
            r'제재.{0,8}(?:해제|완화|철회)|\b(?:lift\w*|ease\w*|remove\w*)\b.{0,20}\bsanctions?\b', title):
        return 'green'
    if kind in RISK_KINDS or adverse or stage._settlement_pressure_headline(title):
        return 'red'
    if color == 'green':
        return 'green'
    if kind == 'military_statement':
        return 'red'
    if kind == 'military_position':
        withdrawal = re.search(r'철수|철군|\bwithdraw\w*\b', title)
        refusal = re.search(r'불가|않|거부|\b(?:not|cannot|refus\w*)\b', title)
        return 'green' if withdrawal and not refusal else 'red'
    if kind in CONSTRUCTIVE_KINDS:
        # A denied meeting/proposal is a constraint, not renewed dialogue.
        if (stage._meeting_plan_stage(title) == 'denied'
                or stage._ceasefire_proposal_stage(title) == 'denied'
                or stage._summit_openness_denied(title)):
            return 'red'
        return 'green'
    # The event classifier can leave a title-only ceasefire item untyped. When
    # the source carries the explicit diplomacy tag and the headline reports
    # confirmation/coordination, use the approved green direction. Keep the
    # body-verification status visible; this is a headline-stage classification.
    tags = {str(tag).strip() for tag in row.get('tags', [])}
    if (tags & DIPLOMATIC_TAGS and not adverse
            and _explicit_ceasefire_progress(title)):
        return 'green'
    if re.search(r'공격.{0,12}(?:않겠|안\s*할|중단)|긴장\s*완화|'
                 r'\b(?:will not attack|de.escalat\w*)\b', title):
        return 'green'
    # Retained military/operational risk reports have a risk marker; their exact
    # headline and stage label continue to say whether an action occurred.
    return 'red'


def _summary(colors):
    red, green = colors.count('red'), colors.count('green')
    lines = ['<b>투자 판정</b>']
    if red:
        lines.append(f'🔴 <b>공격·타격·확전·압박 관련:</b> {red}건')
    if green:
        lines.append(f'🟢 <b>대화·협상·완화 관련:</b> {green}건')
    if not colors:
        lines.append('방향성 기사 없음 · 시장 참고 기사만 확인')
    lines.extend(('- <b>표시 기준:</b> 초록은 대화·협상·완화, 빨강은 공격·타격·공격 예고·결렬·압박',
                  '- <b>현재 단계:</b> 제안·발언·예고와 실제 합의·이행·공격 발생은 기사 문구로 구분',
                  '- <b>다음:</b> 공식 행동·합의 이행·공격 발생 여부 재확인'))
    return '\n'.join(lines)


def project(stage, semantic_text, semantic_evidence, proof, snapshot):
    """Deterministic presentation of already selected and verified sources."""
    receipt = copy.deepcopy(semantic_evidence)
    lines = semantic_text.strip().splitlines()
    starts = [i for i, line in enumerate(lines) if ITEM_START.match(line)]
    rows = [row for row in receipt['articles'] if row.get('rendered')]
    if not starts or len(starts) != len(rows):
        _fail('source/block count mismatch')
    tail_at = next((i for i in range(starts[-1] + 1, len(lines))
                    if lines[i].startswith(('<b>시장 반응</b>', '<b>투자 판정</b>',
                                            '시장자료 확인 보류'))), len(lines))
    core, references, matched = [], [], []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else tail_at
        block = lines[start:end]
        urls = {html.unescape(url) for url in re.findall(r'<a href="([^"]+)"', '\n'.join(block))}
        candidates = [row for row in rows if {row.get('link'), row.get('resolved_url')} & urls]
        if len(candidates) != 1 or candidates[0]['id'] in matched:
            _fail('source not uniquely matched')
        row = candidates[0]
        matched.append(row['id'])
        color = direction(stage, row)
        row['semantic_classification_color'] = row.get('classification_color')
        row['classification_color'] = color
        row['display_section'] = 'core' if color else 'market_reference'
        if color:
            first = re.sub(r'^[🔴🟢🟡]?\s*', MARKERS[color] + ' ', block[0])
            first = re.sub(r'(<b>)\d+\.', lambda m: m[1] + str(len(core) + 1) + '.', first, count=1)
            core.append([first] + block[1:])
        else:
            first = re.sub(r'^[🔴🟢🟡]?\s*\[(?:신규|속보|후속)\]\s*<b>\d+\.',
                           f'<b>참고 {len(references) + 1}.', block[0], count=1)
            references.append([first] + block[1:])
    if set(matched) != {row['id'] for row in rows}:
        _fail('omitted selected source')
    preamble_end = next(i for i, line in enumerate(lines) if line == '<b>핵심 변화</b>')
    preamble = [line for line in lines[:preamble_end]
                if not re.match(r'^[🔴🟢🟡]\s*<b>', line)]
    colors = [row['classification_color'] for row in rows if row['classification_color']]
    badges = []
    if 'red' in colors:
        badges.append('🔴 <b>공격·타격·확전·압박</b>')
    if 'green' in colors:
        badges.append('🟢 <b>대화·협상·완화</b>')
    preamble[1:1] = badges
    output = preamble
    if core:
        output += ['<b>핵심 변화</b>']
        for block in core:
            output += block
    if references:
        output += ['<b>시장 참고</b>', '시장 기사는 전쟁·완화 방향 표시에서 제외', '']
        for block in references:
            output += block
    tail = '\n'.join(lines[tail_at:]).split('<b>투자 판정</b>', 1)[0].rstrip()
    if tail:
        output += [tail, '']
    output += [_summary(colors)]
    text = '\n'.join(output).strip() + '\n'
    visible = html.unescape(re.sub(r'<[^>]+>', '', text))
    if len(visible.encode('utf-16-le')) // 2 > 4000:
        _fail('final display exceeds existing message budget')
    receipt.update(presentation_policy=POLICY, semantic_proof=proof, semantic_snapshot=snapshot,
                   alert_sha256=digest(text.strip().encode('utf-8')))
    return text, receipt


class Presenter:
    def __init__(self, stage):
        self.stage = stage
        self.semantic_verify = stage.verify_alert

    def verify_alert(self, test_mode=False):
        stage, watch = self.stage, self.stage.watch
        if not watch.ALERT.exists() or not watch.AUDIT.exists():
            return self.semantic_verify(test_mode=test_mode)
        receipt = json.loads(watch.AUDIT.read_text(encoding='utf-8'))
        stage_alert, stage_evidence = watch.OUT / STAGE_ALERT, watch.OUT / STAGE_EVIDENCE
        if 'presentation_policy' not in receipt:
            self.semantic_verify(test_mode=test_mode)
            stage_alert.write_bytes(watch.ALERT.read_bytes())
            stage_evidence.write_bytes(watch.AUDIT.read_bytes())
            semantic_text = stage_alert.read_text(encoding='utf-8')
            proof = {'alert_sha256': digest(stage_alert.read_bytes()),
                     'evidence_sha256': digest(stage_evidence.read_bytes())}
            snapshot = {'alert_utf8_base64': base64.b64encode(stage_alert.read_bytes()).decode('ascii'),
                        'evidence_utf8_base64': base64.b64encode(stage_evidence.read_bytes()).decode('ascii')}
            text, presented = project(stage, semantic_text, receipt, proof, snapshot)
            watch.ALERT.write_bytes(text.encode('utf-8'))
            watch.AUDIT.write_bytes((json.dumps(presented, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
            receipt = presented
        if receipt.get('presentation_policy') != POLICY:
            _fail('unknown presentation policy')
        if not stage_alert.is_file() or not stage_evidence.is_file():
            _fail('missing verified event-stage proof')
        proof = {'alert_sha256': digest(stage_alert.read_bytes()),
                 'evidence_sha256': digest(stage_evidence.read_bytes())}
        if receipt.get('semantic_proof') != proof:
            _fail('event-stage proof hash mismatch')
        # Repeat the complete event-stage gate on isolated copies, including the
        # current pending list. Never temporarily replace the deliverable payload.
        with tempfile.TemporaryDirectory(prefix='war-event-stage-') as folder:
            folder = Path(folder)
            a, e, p = folder/'alert.txt', folder/'evidence.json', folder/'pending.json'
            a.write_bytes(stage_alert.read_bytes())
            e.write_bytes(stage_evidence.read_bytes())
            p.write_bytes(watch.PENDING.read_bytes())
            with patch.object(watch, 'ALERT', a), patch.object(watch, 'AUDIT', e), patch.object(watch, 'PENDING', p):
                self.semantic_verify(test_mode=test_mode)
        expected_text, expected_evidence = project(
            stage, stage_alert.read_text(encoding='utf-8'),
            json.loads(stage_evidence.read_text(encoding='utf-8')), proof,
            {'alert_utf8_base64': base64.b64encode(stage_alert.read_bytes()).decode('ascii'),
             'evidence_utf8_base64': base64.b64encode(stage_evidence.read_bytes()).decode('ascii')})
        if watch.ALERT.read_text(encoding='utf-8').strip() != expected_text.strip():
            _fail('final body differs from approved directional presentation')
        if receipt != expected_evidence:
            _fail('final evidence differs from verified sources or directional presentation')


def install(stage):
    presenter = getattr(stage, '_two_color_presenter', None)
    if presenter is None:
        presenter = stage._two_color_presenter = Presenter(stage)
    stage.runner.verify_alert = presenter.verify_alert
    return presenter
