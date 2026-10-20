"""Keep sanctions and diplomatic reactions separate from reported attacks."""
from __future__ import annotations

import html
import hashlib
import json
import math
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt

import war_peace_reconstruction_watch_oct04_guard as previous
import war_peace_reconstruction_watch_bodycolor_parallel as body_parallel
import war_peace_reconstruction_watch_clean as source_score

watch, runner = previous.watch, previous.runner
_score, _color = watch.score_item, previous.final_color
_topic, _build = watch.topic_label, watch.build_alert
_verdict = previous.guard._verdict
_future_refinery = previous._future_refinery_policy
_verify = runner.verify_alert
_parse_pub = watch.parse_pub
KIND_LABELS = {'sanctions': '제재·압박', 'reaction': '외교반응·개입검토',
               'attack_pause': '공격 중단·부인 발언', 'mixed_restraint': '자제 발언·상대 공격 주장',
               'military_statement': '군사 대응·보복 발언', 'support_statement': '지원 정책 발언',
               'military_position': '군사 개입·철수 입장',
               'corporate_spending': '기업 투자·자본배분 보도',
               'market_reaction': '증시 반응 보도',
               'maritime_routing': '선박 항로·운송 보도',
               'military_discussion': '공습 재개 논의·이견', 'military_analysis': '군사·안보 해설',
               'market_effect': '전쟁의 물가 파급 보도', 'ceasefire_position': '휴전·공격 중단 입장',
               'military_report': '공격 조사·보고서 공표', 'fuel_shipping': '봉쇄·연료 선적 보도',
               'trade_proposal': '에너지 거래 재개 제안',
               'diplomatic_contact': '외교 접촉 보도',
               'diplomatic_plan': '협상 추진·논의',
               'diplomatic_statement': '거래·정책 평가 발언',
               'diplomatic_analysis': '외교·안보 해설',
               'diplomatic_position': '외교 갈등·압박 보도',
               'diplomatic_appeal': '항행·협상 재개 요구',
               'operational_disruption': '행사·운영 일정 변경 보도',
               'maritime_shipping': '원유·연료 운송 보도',
               'oil_market': '원유 공급·가격 보도',
               'oil_pressure': '유가 압박·정치일정 보도'}


def _headline(row):
    return html.unescape(str(row.get('title_original') or row.get('title') or row.get('title_ko') or '')).lower()


def parse_pub(value):
    """Retain RSS dates and accept fully dated ISO timestamps with an explicit zone."""
    parsed = _parse_pub(value)
    if parsed is not None:
        return parsed
    text = str(value or '').strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', text):
        return None
    try:
        return dt.datetime.fromisoformat(text.replace('Z', '+00:00')).astimezone(watch.KST)
    except ValueError:
        return None


def maritime_attack_tally(row):
    """A period's ship-attack count does not identify a new projectile incident."""
    title = _headline(row)
    ships = re.search(r'선박|상선|유조선|\b(?:ships?|vessels?|tankers?)\b', title)
    attacks = re.search(r'피격|공격(?:당|받)|\b(?:was|were|been)\s+(?:attacked|struck|hit)\b|'
                        r'\b(?:ships?|vessels?|tankers?)\s+attacked\b', title)
    count = re.search(r'\d[\d,]*\s*척|\b\d[\d,]*\s+(?:ships?|vessels?|tankers?)\b', title)
    period = re.search(r'\d+\s*(?:주|개월)|\d+\s*일\s*(?:간|동안|사이)|'
                       r'\b(?:\d+|one|two|three)\s+(?:days?|weeks?|months?)\b', title)
    uncertain = re.search(r'부인|미확인|가능성|우려|예고|\?|\b(?:denies?|denied|not|never|may|might|could)\b', title)
    return bool(ships and attacks and count and period and not uncertain)


def _maritime_attack_headline(row):
    """A ship-attack headline does not establish an older template's details."""
    title = _headline(row)
    uncertain = re.search(r'부인|미확인|가능성|우려|예고|\?|\b(?:denies?|denied|not|never|may|might|could)\b', title)
    hit = re.search(r'피격|\b(?:ships?|vessels?|tankers?)\b.{0,18}\b(?:attacked|struck|hit)\b(?!\s+(?:record|a deal))', title)
    return bool(re.search(r'선박|상선|유조선|\b(?:ships?|vessels?|tankers?)\b', title)
                and hit and not uncertain)


def _energy_trade_proposal_headline(title):
    energy = re.search(r'천연가스|가스관|가스|원유|석유|\b(?:natural gas|gas|oil|pipeline)\b', title)
    trade = re.search(r'수입|수출|운송|재가동|\b(?:imports?|exports?|pipeline)\b', title)
    proposal = re.search(r'제안|추진|검토|\b(?:propos\w*|consider\w*|discuss\w*)\b', title)
    implemented = re.search(r'양측.{0,15}(?:휴전|공격\s*중단).{0,12}(?:발효됐|이행했|이행\s*중|시행됐)', title)
    return bool(energy and trade and proposal and not implemented)


def _riyadh_missile_headline(row):
    """The headline identifies this report; body background is a separate event."""
    title = _headline(row)
    return bool(re.search(r'리야드|\briyadh\b', title)
                and re.search(r'미사일|\bmissiles?\b', title)
                and re.search(r'후티|\bhouthi', title))


def _display_headline(row):
    original = str(row.get('title_original') or row.get('title') or '')
    if (non_military_kind(row) in ('diplomatic_appeal', 'operational_disruption', 'maritime_shipping', 'maritime_routing', 'oil_market', 'oil_pressure', 'corporate_spending', 'market_reaction')
            or _summit_openness_headline(_headline(row))
            or _summit_openness_denied(_headline(row))
            or _harm_intent_denial_headline(_headline(row))
            or _near_military_authorization(_headline(row))
            or _negotiation_stalemate_headline(_headline(row))
            or _ceasefire_proposal_stage(_headline(row))
            or _headline_attack_casualties(row) or _headline_energy_operation(row)):
        # RSS bullet lines remain one ordered headline in the rendered block.
        return ' '.join(original.split())
    return original if (_riyadh_missile_headline(row) or re.search(r'[가-힣]', original)
                        or _diplomatic_deal_statement(original.lower())) else str(row.get('title_ko') or original)


def _energy_facility_headline(row):
    title = _headline(row)
    return _headline_energy_operation(row) or bool(re.search(r'(?:에너지|핵(?:\s*및\s*에너지)?)\s*시설', title)
                and re.search(r'공격|공습|폭격|타격', title))


def _energy_facility_statement_spans(title):
    """A nominal restart announcement or attack plan does not prove execution."""
    spans = re.finditer(
        r'(?:공격|공습|폭격|타격)(?:을|를)?\s*'
        r'(?:(?:재개|개시)(?:를|을)?\s*(?:발표|선언|방침|계획|하겠다|할\s*(?:것|계획)|하지\s*않|부인)|'
        r'계획|검토|추진|하겠다|할\s*(?:것|계획)|하지\s*않)', title)
    return [span for span in spans if re.search(
        r'(?:에너지|핵(?:\s*및\s*에너지)?)\s*시설',
        re.split(r'…|\.{3}|[;；]', title[max(0, span.start()-80):span.start()])[-1])]


def _headline_action_label(row):
    if _headline_energy_operation(row) and re.search(r'\b(?:expands?|expanded)\b', _headline(row)):
        return '에너지 시설 공격 확대 보도'
    if _maritime_attack_expansion(row):
        if re.search(r'공격\s*강화', _headline(row)):
            return '선박 공격 강화 보도'
        return '선박 공격 확대 보도' if re.search(r'선박|상선|유조선|\b(?:ships?|vessels?|tankers?)\b', _headline(row)) else '공격 확대 보도'
    if _headline_attack_casualties(row):
        return '공습·공격 피해 보도'
    if _headline_drone_action(row):
        return '드론 공습 보도'
    if _maritime_attack_headline(row):
        return '선박 피격 보도'
    return '에너지 시설 공격 보도' if _energy_facility_headline(row) else '정유시설 공격 보도'


def _headline_group(title):
    """Use actors in the current headline, before background actors or caches."""
    us = bool(re.search(r'미국|트럼프|(?:^|\s)美(?:\s|,)|\b(?:trump|united states)\b|'
                        r'(?:^|\s)미\s+(?:국방부|국방장관|정부|행정부|군)|'
                        r'\bu\.s\.(?=\s|$)|^us(?=\s|:|,)', title))
    if re.search(r'후티|\bhouthi', title):
        if us:
            return '미국·후티'
        return '사우디·후티' if re.search(r'사우디|\bsaudi\b', title) else '후티'
    if re.search(r'우크라|러시아|젤렌스키|\b(?:ukrain|russia|zelenskyy?|zelenskiy)', title):
        return '우크라이나·러시아'
    if re.search(r'이란|\biran\b', title):
        if re.search(r'이스라엘|네타냐후|\b(?:israel|netanyahu)\b', title):
            return '미국·이스라엘·이란' if us else '이스라엘·이란'
        return '미국·이란' if us else '이란'
    if re.search(r'이스라엘|네타냐후|\b(?:israel|netanyahu)\b', title):
        return '미국·이스라엘' if us else '이스라엘'
    if re.search(r'사우디|\bsaudi\b', title):
        return '사우디'
    return '전쟁·외교'


def _summit_openness_denied(title):
    return bool(re.search(r"\b(?:not|never|isn['’]t|wasn['’]t)\s+(?:yet\s+)?open\s+to\b.{0,25}\bsummit\b", title))


def _summit_openness_headline(title):
    return bool(re.search(r'\bopen\s+to\b.{0,25}\b(?:a\s+)?summit\b', title)
                and not _summit_openness_denied(title))


def _bargain_proposal_headline(title):
    return bool(re.search(r'담판(?:을|를)?\s*(?:제안|추진|논의|검토)', title))


def _bargain_question_headline(title):
    return bool(re.search(r'담판(?:을|를)?\s*(?:짓나|성사될까|가능할까)', title))


def _meeting_uncertainty_headline(title):
    return bool(re.search(r'회담.{0,18}여부.{0,18}(?:모르겠|미정|확답.{0,5}않)|'
                          r'회담.{0,18}(?:정해지지\s*않|아직\s*미정)', title))


def _meeting_intent_stage(title):
    if re.search(r'회담\s*용의.{0,8}(?:없|부인)|회담.{0,25}원하면.{0,12}하지\s*않', title):
        return 'denied'
    if re.search(r'회담.{0,25}(?:원하면|동의하면).{0,12}(?:할\s*것|하겠다|가능)', title):
        return 'conditional'
    return 'willing' if re.search(r'회담\s*용의', title) else None


def _participation_exclusion_headline(title):
    return bool(re.search(r'협상(?:에서|서|에)?\s*배제|젤렌스키(?:\s*대통령)?\s*배제', title))


def _summit_proposal_headline(title):
    summit = r'(?:정상\s*회담|\d+\s*자\s*(?:정상\s*)?회담)'
    return bool(_summit_openness_headline(title) or _meeting_intent_stage(title) in ('conditional', 'willing')
                or re.search(summit + r'.{0,18}(?:제안|추진|논의|검토|계획)', title)
                or re.search(r'\b(?:propos\w*|discuss\w*|plans?)\b.{0,60}\bsummit\b|'
                             r'\bsummit\b.{0,25}\b(?:proposal|under discussion|planned)\b', title))


def _summit_possibility_reaction(title):
    return bool(re.search(r'(?:\d+\s*자\s*)?(?:정상\s*)?회담.{0,35}가능성.{0,20}반응', title))


def _diplomatic_group(title):
    # A three-party summit can discuss Ukraine without inviting Ukraine.
    # Keep the named participants distinct from that discussion's object.
    if _meeting_uncertainty_headline(title):
        # A possible venue is not an additional meeting participant.
        title = re.sub(r'(?:중국|中)(?:에)?서', '', title)
    if (_summit_proposal_headline(title) or _bargain_question_headline(title)) and not re.search(r'젤렌스키.{0,12}배제하지\s*않', title):
        title = re.sub(r'젤렌스키(?:\s*대통령)?(?:를|는|가)?\s*(?:배제|제외|아닌|빠져라)', '', title)
    trilateral = bool(re.search(r'미\s*[·ㆍ/]?\s*중\s*[·ㆍ/]?\s*러', title))
    north_russia = bool(re.search(r'(?<![가-힣])북\s*[·ㆍ/]?\s*러(?=\s|$)', title))
    actors = []
    for label, pattern in (
            ('미국', r'미국|트럼프|백악관|美|\bwhite\s+house\b|\bu\.s\.|\bunited\s+states\b|'
                     r'\bus(?=\s+(?:midterms?|elections?|officials?|government|military)\b)|'
                     r'\b(?:trump|witkoff|kushner)\b|위트코프|쿠슈너'),
            ('우크라이나', r'우크라|젤렌스키|\b(?:ukrain\w*|zelenskyy?|zelenskiy)\b'),
            ('중국', r'중국|시진핑|\b(?:china|chinese|xi(?:\s+jinping)?)\b'),
            ('러시아', r'러시아|푸틴|크렘린|라브로프|(?:^|[\s·ㆍ/])러(?=\s|[·ㆍ/]|$)|\b(?:russia\w*|putin|kremlin|lavrov)\b'),
            ('이란', r'이란|\biran(?:ian)?\b'),
            ('파키스탄', r'파키스탄|\bpakistan(?:i)?\b'),
            ('북한', r'북한|김정은|\bnorth\s+korea\b|\bkim\s+jong[ -]?un\b')):
        if (re.search(pattern, title) or (trilateral and label in ('미국', '중국', '러시아'))
                or (north_russia and label in ('북한', '러시아'))):
            actors.append(label)
    if _summit_proposal_headline(title) and all(label in actors for label in ('미국', '중국', '러시아')):
        return '미국·중국·러시아'
    if set(actors) == {'러시아', '이란'}:
        return '이란·러시아'
    if set(actors) == {'러시아', '북한'}:
        return '북한·러시아'
    return '·'.join(actors) if actors else _headline_group(title)


def _information_resumption_headline(title):
    return bool(re.search(r'정보.{0,8}(?:지원|공유|제공).{0,18}(?:재개|복원|재시작|정상화)|'
                          r'\b(?:intelligence|information).{0,15}(?:support|sharing|provision).{0,20}(?:resum\w*|restor\w*)|'
                          r'\b(?:resum\w*|restor\w*).{0,20}(?:intelligence|information).{0,15}(?:support|sharing|provision)', title))


def _settlement_pressure_headline(title):
    return bool(re.search(r'(?:종전|휴전).{0,12}합의(?:할\s*때|해야|(?:를)?\s*(?:촉구|압박))|'
                          r'종전\s*협상\s*재촉|젤렌스키.{0,22}합의해야', title))


def _meeting_participation_request(title):
    return bool(re.search(r'회담.{0,35}(?:우리도|우크라이나(?:도)?).{0,12}참여해야', title))


def _near_military_authorization(title):
    # A reported near-approval and an expected future resumption are statements.
    return bool(re.search(r'\b(?:came|was|were)\s+(?:(?:reportedly|very)\s+)*close\s+to\s+'
                          r'(?:ordering|approving|authorizing)\s+(?:military\s+)?strikes?\b', title))


def _attack_denial_with_blockade(title):
    return bool(re.search(r'(?:공격|공습)(?:을|를)?\s*하지\s*않(?:을|겠)', title)
                and re.search(r'봉쇄(?:는|를)?\s*(?:유지|계속)', title))


def _statement_with_actual_action(title):
    stage = (_settlement_pressure_headline(title) or _meeting_participation_request(title)
             or _information_resumption_headline(title) or _near_military_authorization(title)
             or _attack_denial_with_blockade(title))
    return bool(stage and re.search(
        r'(?:공습|공격|폭격|타격|요격)(?:을|를)?\s*(?:했다(?!는)|했으며|하고\s*있|진행\s*중)|'
        r'(?:피격|파괴)(?:됐|되었|당했)|\b(?:attacked|struck|bombed)\b', title))


def _primary_topic(row):
    title = _headline(row)
    kind = non_military_kind(row)
    if kind in ('diplomatic_contact', 'diplomatic_analysis', 'diplomatic_position', 'diplomatic_plan', 'diplomatic_statement', 'diplomatic_appeal'):
        if kind == 'diplomatic_analysis' and _bargain_question_headline(title):
            return _diplomatic_group(title) + ' · 정상회담·담판 가능성 해설'
        if kind == 'diplomatic_position' and _harm_intent_denial_headline(title):
            return _diplomatic_group(title) + ' · 위해 의도 부인·설명'
        if kind == 'diplomatic_position' and _negotiation_stalemate_headline(title):
            return _diplomatic_group(title) + ' · 협상 교착·지연 보도'
        if kind == 'diplomatic_position' and _settlement_pressure_headline(title):
            return _diplomatic_group(title) + ' · 종전 합의 촉구·압박'
        if kind == 'diplomatic_position' and _meeting_participation_request(title):
            return _diplomatic_group(title) + ' · 회담 참여 요구'
        proposal = _ceasefire_proposal_stage(title)
        if proposal and kind in ('diplomatic_position', 'diplomatic_plan'):
            return _diplomatic_group(title) + ' · ' + ('휴전 제안 부인' if proposal == 'denied' else '휴전 제안')
        if kind == 'diplomatic_position' and _negotiation_intent_stage(title) == 'denied':
            return _diplomatic_group(title) + ' · 협상 지속·재개 의향 부인'
        if kind == 'diplomatic_position' and _meeting_intent_stage(title) == 'denied':
            return _diplomatic_group(title) + ' · 회담 의향 부인'
        if kind == 'diplomatic_position' and _participation_exclusion_headline(title):
            return _diplomatic_group(title) + ' · 협상 참여·배제 입장'
        if kind == 'diplomatic_position' and _summit_openness_denied(title):
            return _diplomatic_group(title) + ' · 정상회담 의향 부인'
        if kind == 'diplomatic_position' and _meeting_uncertainty_headline(title):
            return _diplomatic_group(title) + ' · 회담 여부 미정 발언'
        if kind == 'diplomatic_position' and _summit_possibility_reaction(title):
            # A named excluded counterpart is not a confirmed participant.
            actors = re.sub(r'젤렌스키(?:\s*대통령)?(?:이|가)?\s*아닌', '', title)
            return _diplomatic_group(actors) + ' · 회담 가능성에 대한 반응'
        label = ('협상 지속·재개 의향' if kind == 'diplomatic_plan' and _negotiation_intent_stage(title) == 'willing' else
                 '조건부 회담 의향' if kind == 'diplomatic_plan' and _meeting_intent_stage(title) == 'conditional' else
                 '회담 용의 발언' if kind == 'diplomatic_plan' and _meeting_intent_stage(title) == 'willing' else
                 '정상회담 의향·논의' if kind == 'diplomatic_plan' and _summit_openness_headline(title) else
                 '담판 제안·논의' if kind == 'diplomatic_plan' and _bargain_proposal_headline(title) else
                 '조건부 공격 중단 제안' if kind == 'diplomatic_plan' and _conditional_pause_proposal(title) else
                 '정상회담 제안·논의' if kind == 'diplomatic_plan' and _summit_proposal_headline(title) else KIND_LABELS[kind])
        return _diplomatic_group(title) + ' · ' + label
    if kind == 'operational_disruption':
        return _headline_group(title) + ' · ' + KIND_LABELS[kind]
    if kind in ('maritime_shipping', 'maritime_routing'):
        places = [label for label, pattern in (('한국', r'한국|\bkorea(?:n)?\b'),
                  ('홍해', r'홍해|\bred sea\b'), ('호르무즈', r'호르무즈|\bhormuz\b'))
                  if re.search(pattern, title)]
        if kind == 'maritime_routing' and re.search(r'수에즈|\bsuez\b', title):
            places.append('수에즈')
        return ('·'.join(places) or '해상 운송') + ' · ' + KIND_LABELS[kind]
    if kind == 'oil_market':
        area = '호르무즈' if re.search(r'호르무즈|\bhormuz\b', title) else '원유시장'
        return area + ' · ' + KIND_LABELS[kind]
    if kind == 'oil_pressure':
        return _diplomatic_group(title) + ' · ' + KIND_LABELS[kind]
    if kind == 'military_position':
        if _attack_denial_with_blockade(title):
            return _diplomatic_group(title) + ' · 공격 부인·봉쇄 유지 입장'
        return _diplomatic_group(title) + ' · ' + KIND_LABELS[kind]
    if kind == 'corporate_spending':
        return '석유기업 · ' + KIND_LABELS[kind]
    if kind == 'market_reaction':
        area = '걸프 증시' if re.search(r'걸프|\bgulf\b', title) else '증시'
        return area + ' · ' + KIND_LABELS[kind]
    if kind == 'market_effect':
        us_prices = re.search(r'(?:미국|美|united states|u\.s\.).{0,12}(?:물가|cpi|inflation)', title)
        return ('미국·물가' if us_prices else '물가·경제지표') + ' · 전쟁 파급 보도'
    if kind == 'reaction':
        group = _headline_group(title)
        if group == '우크라이나·러시아' and re.search(r'트럼프|미국|\btrump\b|\bu\.s\.', title):
            group = '미국·우크라이나·러시아'
        return group + ' · ' + KIND_LABELS[kind]
    if kind in ('military_statement', 'military_discussion', 'military_analysis', 'ceasefire_position', 'military_report', 'fuel_shipping', 'trade_proposal'):
        return _headline_group(title) + ' · ' + KIND_LABELS[kind]
    if kind == 'support_statement':
        if _information_resumption_headline(title):
            stage = '정상화' if '정상화' in title else '재개'
            return _diplomatic_group(title) + ' · 정보 제공·공유 ' + stage + ' 보도'
        label = '정보 지원·종전 의향 발언' if re.search(r'종전|peace|end.{0,8}war', title) else '지원 정책 발언'
        return _headline_group(title) + ' · ' + label
    if kind is None and _headline_drone_action(row):
        return _headline_group(title) + ' · 드론 공습 보도'
    if kind is None and _maritime_attack_expansion(row):
        if re.search(r'공격\s*강화', title):
            return _headline_group(title) + ' · 선박 공격 강화 보도'
        area = '호르무즈' if re.search(r'호르무즈|\bhormuz\b', title) else '해상'
        return area + ' · ' + _headline_action_label(row)
    if kind is None and _headline_attack_casualties(row):
        houthi = re.search(r'후티|\bhouthi', title)
        yemen = re.search(r'예멘|\byemen(?:i)?\b', title)
        government = re.search(r'예멘\s*정부군|\byemen(?:i)?\s+government\s+(?:forces|troops)\b', title)
        group = ('후티·예멘 정부군' if houthi and government else '후티·예멘' if houthi and yemen
                 else _headline_group(title))
        return group + ' · 공습·공격 피해 보도'
    if kind is None and _headline_refinery_action(row):
        return '우크라이나·러시아 · 정유시설 공격 보도'
    if kind is None and _headline_energy_operation(row):
        return _headline_group(title) + ' · ' + _headline_action_label(row)
    if _energy_facility_headline(row):
        return _headline_group(title) + ' · ' + (KIND_LABELS[kind] if kind else _headline_action_label(row))
    if kind is None and _riyadh_missile_headline(row):
        # Do not turn an attack claim into an interception confirmation, or
        # distinct publishers' headlines into one shared emergency template.
        return '사우디·후티 · 리야드 미사일 보도'
    attack_denied = bool(re.search(
        r'(?:공격|피격|타격)(?:(?:을|를|하지|받지|당하지)|\s*(?:보도|주장|설)(?:을|를)?)?\s*(?:부인|안\s*했|않|하지\s*않)|'
        r'\b(?:not|never)\s+(?:been\s+)?(?:attacked|struck|hit|bombed)\b|'
        r'\bno\s+(?:attack|strike)\b|\b(?:denies|denied)\b.{0,50}\b(?:attack|attacked|struck|hit)\b', title))
    if kind is None and maritime_attack_tally(row):
        area = '호르무즈' if re.search(r'호르무즈|\bhormuz\b', title) else '해상'
        return area + ' · 선박 피격 집계 보도'
    if kind is None and _maritime_attack_headline(row):
        prior_topic = _topic(row)
        if prior_topic.endswith(' · 유조선 피격'):
            return prior_topic
        area = '호르무즈' if re.search(r'호르무즈|\bhormuz\b', title) else '해상'
        return area + ' · 선박 피격 보도'
    if (kind is None and re.search(r'아람코|\baramco\b', title)
            and re.search(r'공격(?!적)|피격|\b(?:attack(?:s|ed)?|struck|hit)\b', title)
            and not attack_denied and not re.search(r'요격|intercept', title)):
        saudi = bool(re.search(r'사우디|\bsaudi\b', title))
        houthi = bool(re.search(r'후티|\bhouthi', title))
        group = ('사우디·후티' if houthi else '사우디·아람코') if saudi else ('후티·아람코' if houthi else '아람코')
        target = '아람코 본사' if re.search(r'본사|headquarters|\bhq\b', title) else (
            '아람코 시설' if re.search(r'시설|정유소|공장|refinery|facilit', title) else '아람코')
        return group + ' · ' + target + ' 공격 보도'
    return None


def _ceasefire_rejection_headline(title):
    # The object of a rejected request is not a completed act of restraint.
    # Keep refusal/withdrawal and its negation in the displayed source headline.
    return bool(re.search(
        r'(?:휴전|공격(?:을)?\s*중단).{0,35}(?:거부|거절|일축|반기|걷어[찼차]|철회|폐기)', title))


def _military_actions(title):
    return list(re.finditer(
        r'(?:공습|공격|폭격)\s*(?:개시|재개|감행)|(?:공습|공격|폭격)에\s*(?:나섰|돌입)|미사일\s*발사|'
        r'보복\s*(?:공습|공격)\s*(?:개시|실시)|'
        r'\band\s+(?:attacks?|strikes?|bombs?)\b|'
        r'\b(?:launches?|launched|conducts?|conducted|resumes?|resumed)\s+(?:new\s+)?(?:attacks?|strikes?|airstrikes?)', title))


def _headline_drone_action(row):
    """A reported drone operation is separate from a body's earlier ceasefire."""
    title = _headline(row)
    for clause in re.split(r'…|\.{3}|[;；]', title):
        if not re.search(r'우크라|러시아|미국|이란|이스라엘|후티', clause):
            continue
        if not re.search(r'드론.{0,55}(?:공습|공격|폭격|타격)', clause):
            continue
        if re.search(r'계획|검토|추진|논의|협의|예정|준비|가능성|예고|시사|예상|부인|허위|가짜|'
                     r'안\s*(?:했|한|해)|하지\s*않|한\s*적\s*없|하겠다|할\s*(?:것|예정)|'
                     r'해설|분석|조사\s*보고서|[?？]|비난|규탄|요구|촉구', clause):
            continue
        return True
    return False


def _headline_energy_operation(row):
    """Bind a named actor to a finite action, excluding plans and denials."""
    return bool(re.search(
        r'\b(?:russia(?:n)?|ukrain(?:e|ian)|iran(?:ian)?|israel(?:i)?|houthis?)\b'
        r'(?:\s+(?:forces|troops|military))?\s+'
        r'(?:expanded|expands?|resumed|resumes?|launched|launch(?:es)?|conducted|conducts?)\s+'
        r'(?:new\s+)?(?:attacks?|strikes?|airstrikes?)\s+(?:on|against)\s+'
        r'(?:[a-z-]+\s+){0,2}(?:energy|nuclear)\s+(?:facilities|infrastructure|sites)\b', _headline(row)))


def _headline_attack_casualties(row):
    """A current attack/casualty clause cannot inherit an old negotiation topic."""
    title = _headline(row)
    if re.search(r'조사\s*보고서|집계|해설|분석|계획|검토|가능성|우려|예상|예고|시사|규탄|비난|부인|허위|가짜|[?？]|'
                 r'하지\s*않|한\s*적\s*없|사망\s*보도.{0,8}(?:아냐|사실무근)', title):
        return False
    english_toll = re.search(
        r'\bdeath\s+toll\s+(?:from|after|in)\b.{0,90}\b(?:attacks?|strikes?|bombing)\b.{0,90}'
        r'\b(?:rises?|rose|climbs?|climbed|reaches?|reached)\s+(?:to\s+)?\d[\d,]*\b', title)
    if english_toll and not re.search(r'\b(?:may|might|could|expected|projected|unconfirmed|den(?:y|ies|ied))\b', title):
        return True
    return bool(re.search(
        r'(?:공습|공격|폭격|타격)(?:으로|에|…|\.{3})\s*.{0,45}'
        r'(?:사상자\s*속출|\d[\d,]*\s*(?:여\s*)?명\s*(?:사망|부상))', title))


def _diplomatic_appeal_headline(title):
    target = r'(?:negotiations?|talks|freedom of navigation|pre-crisis.{0,20}conditions|ceasefire)'
    return bool(re.search(r'\b(?:calls?\s+for|urges?|demands?|appeals?\s+for)\b.{0,70}' + target, title)
                or re.search(r'(?:협상|항행|항해|휴전).{0,35}(?:요구|촉구)', title))


def _operational_disruption_headline(title):
    event = r'(?:event|forum|conference|summit|행사|포럼|회의|사막의\s*다보스)'
    change = r'(?:postpon\w*|cancel\w*|(?:연기|취소)(?!\s*(?:여부|검토|논의|가능성|부인|미정|하지|않|안\s)))'
    # Bind the changed schedule to the event, not an earlier cancelled flight.
    changed_event = (re.search(r'\b(?:postpon\w*|cancel\w*)\b.{0,65}' + event, title)
                     or re.search(r'(?:연기|취소)(?:된|하는|할)\s*.{0,25}' + event, title)
                     or re.search(event + r'(?:(?!…|\.{3}|[;；]).){0,25}' + change, title))
    # A separate completed action remains military news even beside a delay.
    if re.search(r'(?:공습|폭격|공격|타격|요격)(?:을|를)?\s*(?:했다|했으며|하고\s*있|진행\s*중)|'
                 r'(?:공습|공격|폭격)에\s*(?:나섰|돌입)|'
                 r'(?:피격|파괴)(?:됐|되었|당했)|\b(?:attacked|struck|bombed)\b', title):
        return False
    # Nominal damage and flight cancellations can describe the delay's background.
    return bool(changed_event
                and (re.search(r'\bafter\b.{0,35}\battacks?\b|(?:공격|공습).{0,18}(?:이후|여파)|'
                               r'(?:공격|공습|폭격)(?:에|으로)(?!\s*(?:나섰|돌입))|'
                               r'(?:공격|공습)\s*후|공세\s*속|(?:공항|항만|항구)\s*피격|'
                               r'항공편\s*(?:\d+(?:\.\d+)?%\s*)?취소', title)
                     or _military_actions(title)))


def _conditional_pause_proposal(title):
    return bool((re.search(r'(?:대가|조건).{0,50}(?:공격|공습)(?:을|를)?\s*중단.{0,25}제안', title)
                 or _conditional_pause_exchange(title)) and not _conditional_pause_exchange_denied(title))


def _conditional_pause_exchange(title):
    return re.search(r'(?:주면|지원하면|제공하면|공급하면|받으면)(?:(?!…|\.{3}|[;；]).){0,35}'
                     r'(?:공격|공습|폭격)(?:을|를)?\s*중단', title)


def _conditional_pause_exchange_denied(title):
    offer = _conditional_pause_exchange(title)
    return bool(offer and re.search(r'하지\s*않|않겠다|부인|거부', title[offer.end():]))


def _negotiation_intent_stage(title):
    match = re.search(r'협상(?:을|를)?\s*(?:지속|계속|재개)(?:할)?\s*(?:의지|의향)', title)
    if not match:
        return None
    return 'denied' if re.match(r'(?:가|는|를)?\s*(?:없|부인)', title[match.end():]) else 'willing'


def _condemnation_object_spans(title):
    """A nominal action condemned by a speaker is not a new action predicate."""
    return list(re.finditer(
        r'(?:(?:공습|공격|폭격)\s*(?:개시|재개|감행)|미사일\s*발사)(?:를|을)\s*'
        r'(?:(?!…|\.{3}|[,，;；]|발표|선언).){0,70}?(?:규탄|비난|비판)', title))


def _fuel_shipping_headline(title):
    return bool(re.search(r'이란|\biran(?:ian)?\b', title)
                and re.search(r'봉쇄|\bblockade\b', title)
                and re.search(r'연료|lpg|\b(?:fuel|crude)\b', title)
                and re.search(r'선적|운송|수출|\b(?:shipments?|cargo(?:es)?|export(?:s|ed)?)\b', title))


def _maritime_attack_expansion(row):
    """A reported expansion differs from its plan, denial or price consequence."""
    for clause in re.split(r'…|\.{3}|[;；]', _headline(row)):
        if (re.search(r'호르무즈|선박|상선|유조선|\b(?:hormuz|ships?|vessels?|tankers?)\b', clause)
                and re.search(r'공격\s*(?:확대|강화)|\b(?:expands?|expanded)\s+attacks?\b', clause)
                and not re.search(r'예고|계획|검토|논의|가능성|우려|부인|하지\s*않|[?？]|'
                                  r'\b(?:plans?|may|might|could|denies?|denied)\b', clause)):
            return True
    return False


def _oil_shipping_kind(title):
    # Threatened supply recovery is the effect's object, not an attack threat.
    if re.search(r'(?:공격|공습|보복)(?:을|를)?\s*(?:확대\s*)?(?:예고|시사|경고|위협|검토)|'
                 r'\b(?:warns?|threatens?)\b.{0,30}\b(?:attacks?|strikes?)\b', title):
        return None
    if (re.search(r'선박|상선|유조선|\b(?:ships?|vessels?|tankers?)\b', title)
            and re.search(r'우회|경유|귀항|\b(?:rerout\w*|divert\w*)\b', title)
            and not re.search(r'피격|공격|공습|폭격|미사일|\b(?:attack\w*|struck|bombed|missiles?)\b', title)):
        # A tanker identifies a vessel, not its current cargo or oil amount.
        return 'maritime_routing'
    if (re.search(r'선박|상선|유조선|\b(?:ships?|vessels?|tankers?)\b', title)
            and re.search(r'원유|연료|석유|\b(?:oil|crude|fuel)\b', title)
            and re.search(r'운송|선적|\b(?:transport\w*|shipments?|cargo(?:es)?)\b', title)
            and re.search(r'호르무즈|홍해|봉쇄|\b(?:hormuz|red sea|blockade)\b', title)
            and not re.search(r'피격|공격|공습|폭격|미사일|\b(?:attack\w*|struck|bombed|missiles?)\b', title)):
        return 'maritime_shipping'
    oil_price = re.search(r'유가|(?:원유|석유)\s*가격|\boil prices?\b', title)
    if (oil_price and re.search(r'공급|공격|봉쇄|\b(?:supply|attacks?|blockade)\b', title)
            and re.search(r'최고치|최저치|상승|하락|유지|\b(?:high|low|rise\w*|fall\w*|stay\w*)\b', title)):
        return 'oil_market'
    if (oil_price and re.search(r'중간선거|\bmidterm', title)
            and re.search(r'압박|겨냥|응징|목표|속내|끌어올|\b(?:pressure|target\w*|aim\w*)\b', title)
            and not re.search(r'공격|공습|폭격|미사일|드론|\b(?:attacks?|strikes?|missiles?|drones?)\b', title)):
        return 'oil_pressure'
    return None


def _rejection_future_action_spans(title):
    if not _ceasefire_rejection_headline(title):
        return []
    return list(re.finditer(
        r'(?:공격|공습|폭격|타격)(?:을|를)?\s*(?:재개|개시|감행)(?:하겠다|할\s*(?:것|계획|수\s*있)|하기로)|'
        r'미사일\s*발사(?:하겠다|할\s*(?:것|계획|수\s*있)|하기로)', title))


def _headline_refinery_action(row):
    title = _headline(row)
    if not re.search(r'젤렌스키|우크라이나', title):
        return False
    for action in re.finditer(
            r'(?:러시아|러)\s*(?:정유\s*시설|정유소|정유\s*공장)\s*'
            r'(?:공격|공습|폭격|타격)(?:을|를)?\s*(?:재개|개시|감행)', title):
        tail = title[action.end():]
        if not re.match(r'\s*(?:하겠다|할|하기로|하지\s*않|안\s*했|부인|설\b|여부|가능성)', tail):
            return True
    return False


def mixed_restraint_attack(row):
    title = html.unescape(str(row.get('title_original') or row.get('title') or '')).lower()
    if _ceasefire_rejection_headline(title):
        return False
    title = title.replace('’', "'").replace('‘', "'")
    korean_restraint = r'공격(?:을)?\s*(?:자제|중단|멈|안)'
    english_restraint = r'\b(?:halt(?:ed)?|stopp?ed|paus(?:e|ed))\s+(?:energy\s+)?(?:attacks?|strikes?)\b'
    contrast_clause = r'하지만|했지만|했으나|그러나|반면|에도|…|\.\.\.|\b(?:despite|but|while|although|yet)\b'
    # A failed ceasefire is not evidence that either party is exercising
    # restraint. Mask only that phrase; an explicit separate restraint clause
    # still has to retain its subject and the opponent's continuing attack.
    restraint_title = re.sub(
        r'''(?:휴전|ceasefire|truce)["'’”\s]*(?:이|가)?\s*(?:(?:has|have|had|is|was)\s+)?'''
        r'(?:붕괴|결렬|파기|무산|실패|깨졌|무너(?:졌|진|지)|끝났|종료|collaps(?:e[ds]?|ing)|fail(?:ed|s)?|broken|ended)',
        '', title)
    restraint = bool(re.search(r'휴전|ceasefire|truce|' + korean_restraint + '|' + english_restraint, restraint_title))
    contrast = bool(re.search(contrast_clause, title))
    actor = r'(?:러시아|러는|러\s|이란|이스라엘|후티|우크라이나|미국|russia|iran|israel|houthi|ukraine|u\.s\.)'
    ongoing = bool(re.search(actor + r'.{0,35}(?:공격|공습|타격|attack|strike).{0,12}(?:계속|지속|재개|continu|resum)', title)
                   or re.search(actor + r'.{0,25}(?:계속|지속|continu|resum).{0,20}(?:공격|공습|타격|attack|strike)', title))
    # The opponent can inherit the preceding predicate as well as its object:
    # "공격 자제했지만 러는 아냐" / "halted attacks but Russia didn't".
    # Require that action, contrast, opponent and denial occur in that order;
    # an unrelated "reconstruction is not complete" must not erase a ceasefire.
    korean_actor = r'(?<![가-힣a-z])(?:러시아|러|이란|이스라엘|후티|우크라이나|미국)(?:는|은|도|가|이)?'
    korean_denial = r'(?:아냐|아님|아니(?:다|야|었|라)?|그렇지\s*않|안\s*(?:했|해|하))'
    inherited = bool(re.search(korean_restraint + r'.{0,35}(?:' + contrast_clause + r').{0,8}'
                               + korean_actor + r'\s*(?:계속|지속|' + korean_denial + ')', title))
    english_actor = r'\b(?:russia|moscow|iran|tehran|israel|houthi(?:s)?|ukraine|kyiv|u\.s\.|us)\b'
    english_denial = (r"(?:(?:did|does|has|have|had|is|was|were|will|would|do)\s+not\b|"
                      r"(?:did|does|has|have|had|is|was|were|do)n't\b|won't\b)")
    inherited_english = bool(re.search(english_restraint + r'.{0,55}(?:' + contrast_clause + r').{0,8}'
                                       + english_actor + r'\s+' + english_denial, title))
    return restraint and contrast and (ongoing or inherited or inherited_english)


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


def _military_discussion_spans(title):
    # "공습 재개 놓고 이견" is a nominal subject of discussion, whereas a
    # separate "공습 재개…추가 공격 논의" clause still reports resumed attacks.
    return list(re.finditer(
        r'(?:공습|공격|군사\s*대응|미사일\s*발사)(?:\s*(?:재개|개시|실시|확대))?\s*(?:를|을)?\s*'
        r'(?:논의|검토|협의|놓고\s*(?:이견|논의|갈등|고심))|'
        r'\b(?:discuss(?:es|ed|ing)?|consider(?:s|ed|ing)?|at\s+odds\s+over|disagrees?\s+(?:on|over))\s+'
        r'(?:(?:the\s+)?resumption\s+of|resuming|restarting)\s+(?:attacks?|strikes?|airstrikes?)\b', title))


def _refinery_restart_statement_spans(title):
    """Scope a leader's quoted restart policy without hiding other action clauses."""
    statements = []
    quotes = list(re.finditer(r'"([^"\n]+)"|“([^”\n]+)”', title))
    for quote in quotes:
        prefix = re.split(r'…|\.{3}|[;；]', title[:quote.start()])[-1]
        if not re.search(r'젤렌스키|우크라이나', prefix):
            continue
        words = quote.group(1) or quote.group(2)
        if not re.search(r'(?:러시아|러)\s*(?:정유\s*시설|정유소|정유\s*공장)', words):
            continue
        # A nominal quote plus a prospective cue is a policy statement. A
        # completed/ongoing verb (재개했다/재개하고 있다) must keep its action.
        group = 1 if quote.group(1) else 2
        restart = re.compile(r'(?:공격|공습|타격)(?:을|를)?\s*재개(?P<future>하겠다|할\s*(?:것|계획))?\s*$').search(
            title, quote.start(group), quote.end(group))
        tail = title[quote.end():quote.end() + 65]
        if restart and (restart.group('future') or re.search(r'시사|방침|예고|계획|선언', tail)):
            statements.append(restart)
    # A declaration may be outside the quote: the quoted words can instead be
    # the leader's refusal of another government's request. Only the explicit
    # restart-policy span is non-action; a separate launch or completed restart
    # still wins in non_military_kind. Body background is not consulted here.
    for declaration in re.finditer(
            r'(?:러시아|러)\s*(?:정유\s*시설|정유소|정유\s*공장)(?:에\s*대한)?\s*'
            r'(?:공격|공습|타격)(?:을|를)?\s*재개(?:하기로|하겠다고|할\s*것이라고)?\s*'
            r'(?:선언|방침|계획|예고|시사)', title):
        if (re.search(r'젤렌스키|우크라이나', title[:declaration.start()])
                and not any(q.start() <= declaration.start() < q.end() for q in quotes)):
            statements.append(declaration)
    return statements


def _military_analysis_headline(title):
    military = re.search(r'미사일|공습|공격|폭격|방패|방공|요격|\b(?:missile|attack|airstrike|shield|defen[cs]e)', title)
    question = re.search(r'왜|어째서|\b(?:why|how)\b', title) and re.search(r'\?|까요|는가|했나', title)
    rumor_question = re.search(r'(?:공격설|공습설|폭격설).{0,20}(?:힘\s*얻나|확산되나|가능성|[?？])', title)
    # A labelled dilemma feature describes the attack's implications. Its
    # background noun does not identify a new operation at publication time.
    marked_feature = re.search(r'\[디브리핑\]', title) and re.search(r'딜레마', title)
    if (marked_feature or rumor_question) and re.search(
            r'(?:공습|공격|폭격|타격|요격)(?:을|를)?\s*'
            r'(?:개시|재개|감행|실시|완료|성공|했|하고\s*있|진행\s*중)|'
            r'(?:미사일|드론)(?:\s*\d+\s*(?:발|대))?(?:을|를)?\s*발사|'
            r'(?:피격|파괴)(?:됐|되었|당했)', title):
        return False
    return bool(military and (question or marked_feature or rumor_question))


def _military_report_headline(title):
    # In "폭격 조사보고서", bombing is the subject of an investigation. The
    # noun phrase does not assert a new attack when the report is published or
    # delayed. Actual action predicates in other clauses are checked first.
    return bool(re.search(
        r'(?:폭격|공습|공격|타격)(?:\s*(?:사건|의혹|에\s*대한))?\s*'
        r'(?:조사\s*(?:보고서|결과)|진상\s*조사)|'
        r'\b(?:bombing|airstrikes?|attacks?|strikes?)\s+(?:investigation|inquiry)\s+report\b', title))


def _report_with_completed_action(title):
    return bool(_military_report_headline(title) and re.search(
        r'(?:공습|폭격|공격|타격)(?:했다(?!는)|하고\s*있다)|'
        r'\b(?:russia|ukraine|iran|israel|houthis?)\s+(?:attacks|strikes|bombs|attacked|bombed)\b', title))


def _diplomatic_deal_statement(title):
    return bool(re.search(r'\b(?:diesel|energy|gas|oil)\b', title)
                and re.search(r'\b(?:calls?|called)\b.{0,60}\b(?:deal|waiver|trade)\b\s+'
                              r'(?:an?\s+).{0,30}\b(?:incentive|gift|lifeline|mistake)\b', title))


def _harm_intent_denial_headline(title):
    """A denial of political intent is not execution of a background attack."""
    return bool(re.search(
        r"\b(?:is\s+not|isn't|isn’t|was\s+not|wasn't|wasn’t|not|never)\s+"
        r'(?:out|trying|seeking|aiming)\s+to\s+(?:hurt|harm|damage)\b|'
        r'(?:해치려는|해하려는|해칠\s*의도).{0,12}(?:아니|없)', title))


def _negotiation_stalemate_headline(title):
    return bool(re.search(r'\b(?:talks|negotiations)\b.{0,40}\b(?:stalemate|deadlock)\b|'
                          r'\b(?:stalemated|deadlocked)\b.{0,20}\b(?:talks|negotiations)\b|'
                          r'협상.{0,20}(?:교착|장기화|지연)', title))


def _ceasefire_proposal_stage(title):
    proposal = re.search(r'휴전(?:을|를)?\s*(?:제안|제의)|'
                         r'\b(?:propos(?:e[sd]?|ing)|offer(?:s|ed|ing)?)\b.{0,45}\b(?:ceasefire|truce)\b|'
                         r'\b(?:ceasefire|truce)\s+proposal\b', title)
    if not proposal:
        return None
    denied = re.search(r'(?:휴전(?:을|를)?\s*)?(?:제안|제의).{0,8}(?:부인|사실무근|하지\s*않|안\s*했)|'
                       r'\bden(?:y|ies|ied)\b.{0,25}\b(?:propos\w*|offer\w*)\b|'
                       r'\b(?:did|does|has)\s+not\s+(?:propos\w*|offer\w*)\b', title)
    return 'denied' if denied else 'proposed'


def _military_withdrawal_position(title):
    military = re.search(r'전쟁|병력|미군|군대|\b(?:war|troops|forces)\b', title)
    corporate = re.search(r'기업|직원|공장|\b(?:compan\w*|employees?|factor\w*)\b', title)
    modal = re.search(r'철수할\s*수\s*(?:있|없)|철수\s*가능성|'
                      r'\b(?:can(?:not)?|could|may|might)\s+(?:not\s+)?withdraw\b', title)
    return bool(military and modal and not corporate)


def _corporate_spending_headline(title):
    companies = re.search(r'석유\s*기업|에너지\s*기업|\b(?:oil majors|oil companies|energy companies)\b', title)
    spending = re.search(r'투자|자본\s*배분|배당|지출|\b(?:spending|capex|capital expenditure|dividends?)\b', title)
    return bool(companies and spending)


def _market_attack_claim_reaction(title):
    move = re.search(r'\b(?:bourses?|stocks?|shares?|equities)\b.{0,35}'
                     r'\b(?:retreat\w*|fall\w*|drop\w*|declin\w*|slid\w*|rise\w*|rall\w*)\b|'
                     r'(?:증시|주가).{0,20}(?:하락|상승|반락|반등)', title)
    claim_background = re.search(r'\bafter\b.{0,70}\bclaim(?:s|ed|ing)?\b.{0,25}\battacks?\b|'
                                 r'공격(?:을|를)?\s*주장(?:하자|한\s*후|\s*이후)', title)
    return bool(move and claim_background)


def _diplomatic_headline_kind(title):
    intent = _negotiation_intent_stage(title)
    if intent:
        return 'diplomatic_position' if intent == 'denied' else 'diplomatic_plan'
    if re.search(r'협상(?:을|를)?\s*(?:(?:재개|개최|개시)(?:를|을)?\s*)?(?:논의|검토|추진|계획)|'
                 r'(?:종전|평화|휴전)\s*협상.{0,15}(?:진전되나|가능성)|'
                 r'(?:종전|평화|휴전)\s*협상.{0,18}진전.{0,25}발표\s*가능성', title):
        return 'diplomatic_plan'
    """A contact, dispute or labelled analysis does not assert peace progress."""
    # Separate completed operations remain actions even in a contact headline.
    if re.search(r'(?:공습|폭격|공격|타격|요격)(?:을|를)?\s*(?:했다|했으며|하고\s*있|진행\s*중)|'
                 r'(?:피격|파괴)(?:됐|되었|당했)|\b(?:attacked|struck|bombed)\b', title):
        return None
    proposal = _ceasefire_proposal_stage(title)
    if proposal:
        return 'diplomatic_position' if proposal == 'denied' else 'diplomatic_plan'
    if re.search(r'\[[^\]]*월드뷰\]', title) and re.search(r'외교|우크라|\b(?:diplomac|ukrain)', title):
        return 'diplomatic_analysis'
    actor = re.search(r'젤렌스키|우크라|트럼프|미국|위트코프|쿠슈너|이란|러시아|푸틴|크렘린|라브로프|'
                      r'\b(?:zelenskyy?|zelenskiy|ukrain\w*|trump|witkoff|kushner|iran(?:ian)?|russia\w*|putin|kremlin|lavrov)\b|\bu\.s\.', title)
    if not actor:
        return None
    if _bargain_question_headline(title):
        return 'diplomatic_analysis'
    if _harm_intent_denial_headline(title) or _negotiation_stalemate_headline(title):
        return 'diplomatic_position'
    if (_summit_possibility_reaction(title) or _meeting_uncertainty_headline(title)
            or _summit_openness_denied(title) or _meeting_intent_stage(title) == 'denied'):
        return 'diplomatic_position'
    if re.search(r'항복\s*압박|\b(?:surrender|capitulat\w*)\b.{0,30}\bpressure\b|'
                 r'\bpressure\b.{0,30}\b(?:surrender|capitulat\w*)\b', title):
        return 'diplomatic_position'
    if re.search(r'(?:종전|평화|휴전)\s*협상.{0,18}(?:러시아|러|우크라이나).{0,12}'
                 r'(?:떠나길|이탈).{0,12}(?:원치\s*않|원하지\s*않)', title):
        return 'diplomatic_position'
    if _summit_proposal_headline(title) or _bargain_proposal_headline(title):
        return 'diplomatic_plan'
    if _participation_exclusion_headline(title):
        return 'diplomatic_position'
    if re.search(r'(?:평화\s*협상|종전\s*협상|휴전\s*협상)(?:을|를)?\s*'
                 r'(?:(?:재개|개최|개시)(?:를|을)?\s*)?(?:추진|논의|검토|계획)|'
                 r'회동(?:을|를|도)?\s*(?:추진|논의|검토|계획)|'
                 r'\b(?:plans?|planning|discuss\w*)\b.{0,35}\b(?:peace talks|meeting)\b|'
                 r'\b(?:peace talks|meeting)\b.{0,25}\b(?:under discussion|planned)\b', title):
        return 'diplomatic_plan'
    if _diplomatic_deal_statement(title):
        return 'diplomatic_statement'
    if re.search(r'통화|대화|회담|접촉|(?:종전|평화|휴전)\s*협상|\bpeace\s+talks\b|'
                 r'\bforeign ministers?\b.{0,20}\bhold talks\b|\b(?:speaks?|spoke|talks?|talked)\s+(?:to|with)\b|'
                 r'\b(?:calls?|called)\s+(?:(?:u\.s\.|us)\s+)?'
                 r'(?:envoys?|witkoff|kushner|trump|zelenskyy?|zelenskiy)\b(?![\'’]s\b)', title):
        return 'diplomatic_contact'
    return None


def non_military_kind(row):
    title = html.unescape(str(row.get('title_original') or row.get('title') or row.get('title_ko') or '')).lower()
    new_peace = re.search(r'(?:휴전|종전|평화협정).{0,12}(?:합의|체결|이행|발효)|'
                          r'\b(?:ceasefire|peace deal).{0,20}(?:agreed|signed|implemented)', title)
    if mixed_restraint_attack(row):
        return 'mixed_restraint'
    if (_headline_drone_action(row) or _headline_attack_casualties(row)
            or _maritime_attack_expansion(row) or _headline_energy_operation(row)):
        return None
    # Require an explicit new-action predicate before background weapon nouns
    # can turn a sanctions listing or a condemnation into a military event.
    discussion = _military_discussion_spans(title)
    statements = _refinery_restart_statement_spans(title) + _energy_facility_statement_spans(title)
    future = _rejection_future_action_spans(title)
    condemnation = _condemnation_object_spans(title)
    actions = _military_actions(title)
    if any(not any(span.start() <= action.start() and action.end() <= span.end()
                   for span in discussion + statements + future + condemnation) for action in actions):
        return None
    if _report_with_completed_action(title) or _statement_with_actual_action(title):
        return None
    if _settlement_pressure_headline(title) or _meeting_participation_request(title):
        return 'diplomatic_position'
    if _near_military_authorization(title):
        return 'military_statement'
    if _attack_denial_with_blockade(title):
        return 'military_position'
    if not new_peace and _military_withdrawal_position(title):
        return 'military_position'
    if not new_peace and _corporate_spending_headline(title):
        return 'corporate_spending'
    if not new_peace and _market_attack_claim_reaction(title):
        return 'market_reaction'
    if (not new_peace and not (statements or future or condemnation or _ceasefire_rejection_headline(title))
            and not re.search(r'\b(?:attacked|struck|bombed)\b', title)):
        if _diplomatic_appeal_headline(title):
            return 'diplomatic_appeal'
        if _operational_disruption_headline(title):
            return 'operational_disruption'
        if _conditional_pause_proposal(title):
            return 'diplomatic_plan'
        if _conditional_pause_exchange_denied(title):
            return 'ceasefire_position'
    if _military_report_headline(title):
        return 'military_report'
    if condemnation:
        return 'reaction'
    if _fuel_shipping_headline(title):
        return 'fuel_shipping'
    oil_kind = _oil_shipping_kind(title)
    if oil_kind and not new_peace:
        return oil_kind
    if _energy_trade_proposal_headline(title):
        return 'trade_proposal'
    if statements or future:
        return 'military_statement'
    if _ceasefire_rejection_headline(title):
        return 'ceasefire_position'
    if discussion:
        return 'military_discussion'
    if _military_analysis_headline(title):
        return 'military_analysis'
    if refinery_attack_denial(row):
        return 'attack_pause'
    if re.search(r'제재|\bsanctions?\b|restrictive measures', title):
        if not re.search(r'공항.*피격|드론.*공격|\b(?:attacked|struck|bombed)\b', title):
            return 'sanctions'
    if re.search(r'규탄|비난|\bcondemn(?:s|ed|ing)?\b|\bdenounc(?:e[sd]?|ing)\b', title):
        return 'reaction'
    # The new event can be a statement even when its background describes real
    # or historical attacks. An explicit newly launched attack above wins.
    if re.search(r'(?:보복|공격|공습|군사작전|타격).{0,18}(?:시사|예고|경고|위협|검토|가능성)|'
                 r'\b(?:warns?|threatens?|considers?).{0,55}(?:retaliat|attack|strike)|'
                 r'\bretaliation.{0,30}(?:warning|threat)', title):
        return 'military_statement'
    if not new_peace and (_information_resumption_headline(title) or re.search(r'정보.{0,8}(?:지원|공유).{0,18}(?:유지|계속|부인|중단하지\s*않)|'
                 r'\b(?:intelligence|information).{0,15}(?:support|sharing).{0,20}(?:maintain|continu)|'
                 r'\b(?:maintains?|continues?).{0,20}(?:intelligence|information).{0,15}(?:support|sharing)', title)):
        return 'support_statement'
    # An inflation report about war costs is not a new diplomatic event.
    prices = re.search(r'소비자물가|물가|\bcpi\b|\binflation\b|consumer prices', title)
    if prices and re.search(r'전쟁|\bwar\b', title) and not new_peace:
        return 'market_effect'
    # A commercial side deal in a peace-talks context keeps the existing
    # transaction topic; the talks noun alone must not erase that distinction.
    return _diplomatic_headline_kind(title) if not new_peace and not previous._lukoil_side_deal(row) else None


def _clear_market_event_cache(row):
    row['non_military_kind'] = 'market_effect'
    row['signals_ko'] = []
    row['forced_tags'] = []
    row['tags'] = [KIND_LABELS['market_effect']]
    row.pop('newidea_marks', None)
    row.pop('deep_signal', None)


def _headline_event_label(row, kind):
    title = _headline(row)
    if kind == 'military_position' and _attack_denial_with_blockade(title):
        return '공격 부인·봉쇄 유지 입장'
    if kind == 'diplomatic_analysis' and _bargain_question_headline(title):
        return '정상회담·담판 가능성 해설'
    if kind == 'diplomatic_position' and _harm_intent_denial_headline(title):
        return '위해 의도 부인·설명'
    if kind == 'diplomatic_position' and _negotiation_stalemate_headline(title):
        return '협상 교착·지연 보도'
    if kind == 'diplomatic_position' and _settlement_pressure_headline(title):
        return '종전 합의 촉구·압박'
    if kind == 'diplomatic_position' and _meeting_participation_request(title):
        return '회담 참여 요구'
    if kind in ('diplomatic_position', 'diplomatic_plan') and _ceasefire_proposal_stage(title):
        return '휴전 제안 부인' if _ceasefire_proposal_stage(title) == 'denied' else '휴전 제안'
    return KIND_LABELS[kind] if kind else _headline_action_label(row)


def _headline_event_cache_required(row, kind):
    return (kind in ('support_statement', 'military_position', 'corporate_spending', 'market_reaction', 'maritime_routing', 'ceasefire_position', 'military_report', 'reaction', 'fuel_shipping', 'military_analysis', 'trade_proposal',
                    'diplomatic_contact', 'diplomatic_analysis', 'diplomatic_position', 'diplomatic_plan', 'diplomatic_statement', 'diplomatic_appeal', 'operational_disruption', 'maritime_shipping', 'oil_market', 'oil_pressure')
            or (kind == 'military_statement' and (
                _refinery_restart_statement_spans(_headline(row)) or _ceasefire_rejection_headline(_headline(row))
                or _near_military_authorization(_headline(row))))
            or _energy_facility_headline(row)
            or (kind is None and _headline_refinery_action(row))
            or (kind is None and _headline_drone_action(row))
            or (kind is None and _maritime_attack_expansion(row))
            or (kind is None and _headline_attack_casualties(row))
            or (kind is None and _headline_energy_operation(row))
            or (_maritime_attack_headline(row) and not maritime_attack_tally(row)))


def _clear_headline_event_cache(row, kind):
    # These tags and signals can come from the article's earlier ceasefire
    # background. They do not describe the current restart declaration.
    if kind:
        row['non_military_kind'] = kind
    else:
        row.pop('non_military_kind', None)
    row['tags'] = [_headline_event_label(row, kind)]
    row['forced_tags'] = []
    row['signals_ko'] = []
    row.pop('newidea_marks', None)
    row.pop('deep_signal', None)


def score_item(row, now):
    stamp = watch.parse_pub(row.get('published'))
    age = watch.age_minutes(row, now)
    if stamp is None or stamp > now + dt.timedelta(minutes=5) or age > 3 * 60:
        return 0, []
    kind = non_military_kind(row)
    if kind is None and _headline_energy_operation(row):
        _clear_headline_event_cache(row, kind)
        score, _ = source_score._original_score(row, now)
        return score, list(row['tags'])
    if kind == 'market_effect':
        _clear_market_event_cache(row)
        score, _ = source_score._original_score(row, now)
        return score, list(row['tags'])
    if kind in ('support_statement', 'military_position', 'corporate_spending', 'market_reaction', 'maritime_routing', 'diplomatic_contact', 'diplomatic_analysis', 'diplomatic_position', 'diplomatic_plan', 'diplomatic_statement', 'diplomatic_appeal', 'operational_disruption', 'maritime_shipping', 'oil_market', 'oil_pressure'):
        _clear_headline_event_cache(row, kind)
        score, _ = source_score._original_score(row, now)
        return score, list(row['tags'])
    score, tags = _score(row, now)
    if _headline_event_cache_required(row, kind):
        _clear_headline_event_cache(row, kind)
        return score, list(row['tags'])
    if kind and score > 0:
        row['non_military_kind'] = kind
        row['signals_ko'] = []
        tags = [tag for tag in tags if tag not in ('확전', '확전위험', '재확전위험', '휴전·평화')]
        tags = [tag for tag in tags if tag != '공격확대예고']
        tags.append(KIND_LABELS[kind])
        tags = list(dict.fromkeys(tags))
    return score, tags


def final_color(row):
    if non_military_kind(row):
        return 'yellow'
    if _statement_with_actual_action(_headline(row)):
        return 'red'
    if _headline_energy_operation(row):
        return 'red'
    if re.search(r'(?:공습|공격|폭격)에\s*(?:나섰|돌입)', _headline(row)):
        return 'red'
    if _report_with_completed_action(_headline(row)):
        return 'red'
    if _headline_refinery_action(row):
        return 'red'
    if _headline_drone_action(row):
        return 'red'
    if _maritime_attack_expansion(row):
        return 'red'
    if _headline_attack_casualties(row):
        return 'red'
    if _energy_facility_headline(row) and _military_actions(_headline(row)):
        return 'red'
    if _ceasefire_rejection_headline(_headline(row)) and _military_actions(_headline(row)):
        return 'red'
    title = _headline(row)
    if (_military_actions(title) and (_operational_disruption_headline(title)
            or re.search(r'유가|원유|연료|\b(?:oil|crude|fuel)\b', title)
            or _conditional_pause_exchange(title) or _negotiation_intent_stage(title)
            or _summit_openness_headline(title) or _summit_openness_denied(title) or _bargain_proposal_headline(title)
            or _meeting_uncertainty_headline(title) or _meeting_intent_stage(title)
            or _participation_exclusion_headline(title) or _harm_intent_denial_headline(title)
            or _negotiation_stalemate_headline(title) or _ceasefire_proposal_stage(title)
            or _bargain_question_headline(title) or _information_resumption_headline(title)
            or _settlement_pressure_headline(title) or _meeting_participation_request(title)
            or _near_military_authorization(title) or _attack_denial_with_blockade(title))):
        return 'red'
    return 'red' if maritime_attack_tally(row) else _color(row)


def topic_label(row):
    primary = _primary_topic(row)
    if primary:
        return primary
    topic = _topic(row)
    kind = non_military_kind(row)
    if kind:
        topic = topic.split(' · ')[0]
        topic += ' · ' + KIND_LABELS[kind]
    return topic


def verdict(items):
    if items and all(maritime_attack_tally(row) for row in items):
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 일정 기간의 선박 피격 건수에 관한 집계 보도\n'
            '- <b>현재 단계:</b> 기사 공표시각과 집계 기간을 구분 — 공표시각에 새 피격이 발생했다는 뜻은 아님\n'
            '- <b>조건부 영향:</b> 추가 피격·운항 차질이 확인되면 해운·보험 위험프리미엄 상승 가능\n'
            '- <b>다음:</b> 집계 원자료·기간 → 개별 피격의 발생시각·원인·공격 주체 → 실제 추가 피해'
        )
    kinds = [non_military_kind(row) for row in items]
    if kinds and all(kinds):
        if 'maritime_routing' in kinds:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 우회·귀항·운송 경로에 관한 보도 — 공표시각을 새 공격이나 봉쇄 개시시각으로 보지 않음\n'
                '- <b>시장:</b> 선박 종류·척수·항로·검토 여부를 실제 적재물·원유 물량·운임과 구분\n'
                '- <b>다음:</b> 항로·선박 원자료 → 실제 운항·귀항 확인 → 별도 공급·운임 변화 확인'
            )
        if 'market_reaction' in kinds:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 증시 움직임을 보도한 기사 — 배경으로 인용된 공격 주장을 독립 확인한 것은 아님\n'
                '- <b>시장:</b> 기사 속 시장·기간·등락과 별도 군사행동의 확인 수준을 구분\n'
                '- <b>다음:</b> 시장 원자료·비교 기준 → 인용 발언 원문 → 별도 실제 공격·피해 확인'
            )
        if 'corporate_spending' in kinds:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 기업의 투자·자본배분에 관한 보도 — 실제 지출·배당 결정과 집행은 별도 확인 필요\n'
                '- <b>시장:</b> 기사 속 현금·투자 검토를 현재 유가 변화나 새 군사행동의 증거로 바꾸지 않음\n'
                '- <b>다음:</b> 기업 원문·공시 → 투자·자본배분 결정 → 실제 집행과 현금흐름 확인'
            )
        if set(kinds) & {'maritime_shipping', 'oil_market', 'oil_pressure'}:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 운송·공급·가격·압박 목적에 관한 보도 — 별도의 실제 공격·휴전 이행은 각각 확인 필요\n'
                '- <b>시장:</b> 기사 속 가격 기간·선박 건수·운송 경로와 실제 공급 차질을 구분\n'
                '- <b>다음:</b> 운송·가격 원자료 → 공급·운항 변화 → 별도 군사행동·공식 합의 확인'
            )
        if set(kinds) & {'diplomatic_appeal', 'operational_disruption'}:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 요구·촉구·제안과 행사 일정 변경 보도 — 실제 협상 개최·양측 휴전 이행·새 군사작전은 별도 확인 필요\n'
                '- <b>시장:</b> 발언의 요구 대상과 행사 차질을 구분하고 운항·공급·가격의 실제 변화는 별도 확인\n'
                '- <b>다음:</b> 발언·일정 원문 → 공식 결정 → 실제 협상·운영 변화·작전 확인'
            )
        if set(kinds) & {'diplomatic_contact', 'diplomatic_analysis', 'diplomatic_position', 'diplomatic_plan', 'diplomatic_statement'}:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 접촉·갈등·해설·제안·추진·평가 발언 단계 — 실제 협상 개최·양측 휴전 합의·이행은 별도 확인 필요\n'
                '- <b>시장:</b> 외교 접촉이나 해설만으로 정유시설 공격·공급 차질·가격 방향의 변화를 확정할 수 없음\n'
                '- <b>다음:</b> 발언·접촉 원문 → 당사자 공식 결정 → 실제 협상·작전·휴전 이행 확인'
            )
        if 'trade_proposal' in kinds:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 제안·검토 단계 — 에너지 거래 재개 구상은 양측 휴전 이행을 뜻하지 않음\n'
                '- <b>시장:</b> 협상 당사자의 수용·거부와 실제 수출입·공급 변화는 별도 확인 필요\n'
                '- <b>다음:</b> 제안 원문·당사자 반응 → 공식 합의 → 실제 거래·휴전 이행의 독립 확인'
            )
        if 'fuel_shipping' in kinds:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 비난·선적 보도와 별도의 군사작전을 구분 — 기사 공표시각에 새 공격이 발생했다는 뜻은 아님\n'
                '- <b>시장:</b> 선적의 집계 기간·수량·추정 목적지와 실제 운항·공급 차질은 각각 확인 필요\n'
                '- <b>다음:</b> 발언·선적 원자료 → 봉쇄 집행·개별 운항 → 별도 공격·피해의 독립 확인'
            )
        if 'ceasefire_position' in kinds:
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> 휴전·공격 중단의 수용·거부·철회·재개 방침을 구분한 보도\n'
                '- <b>현재 단계:</b> 해당 입장과 발언을 새 휴전 발표나 양측 공격 중단 이행으로 해석할 수 없음\n'
                '- <b>시장:</b> 발언과 실제 작전·시설 피해·운영 차질은 각각 확인 필요\n'
                '- <b>다음:</b> 요구·거부·재개 방침 원문 → 공식 명령 → 실제 작전·휴전 이행의 독립 확인'
            )
        if set(kinds) == {'market_effect'}:
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> 전쟁과 물가 지표의 연결을 다룬 보도\n'
                '- <b>현재 단계:</b> 물가·시장 파급 보도 — 새로운 교전·휴전 이행 여부는 별도 확인 필요\n'
                '- <b>시장:</b> 기사에 인용된 지표와 에너지 가격의 기간·출처를 각각 확인\n'
                '- <b>다음:</b> 공식 지표·공표일 → 에너지 가격·기간 → 전쟁 영향의 독립 확인'
            )
        if 'military_report' in kinds:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 조사·보고서 공표 단계와 다른 조치·발언을 구분 — 공표·연기 자체는 새 공격 개시를 뜻하지 않음\n'
                '- <b>시장:</b> 조사 대상 사건·발생시각과 보고서의 공표 일정·내용을 각각 확인\n'
                '- <b>다음:</b> 원 보고서·공표일 → 조사 대상 사건·책임 주체 → 별도 군사작전의 독립 확인'
            )
        if set(kinds) & {'military_discussion', 'military_analysis'}:
            core = ' / '.join(dict.fromkeys(KIND_LABELS[kind] for kind in kinds))
            return (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                '- <b>현재 단계:</b> 발언·논의·해설 단계 — 새로운 군사작전 개시는 별도 확인 필요\n'
                '- <b>시장:</b> 논의·해설만으로 추가 공격·운영 차질이나 가격 방향을 확정할 수 없음\n'
                '- <b>다음:</b> 원문·공식 결정 → 실제 작전·운영 변화 → 독립 확인'
            )
        if set(kinds) & {'military_statement', 'support_statement', 'military_position'} and not set(kinds) & {'attack_pause', 'mixed_restraint'}:
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> 군사 대응·지원 정책·종전 의향에 관한 발언\n'
                '- <b>현재 단계:</b> 발언·검토 단계 — 발언 자체로 새로운 군사작전 개시나 양측 휴전 이행을 확인할 수 없음\n'
                '- <b>시장:</b> 군사 명령·실제 공격·운영 차질과 시장가격은 별도 확인 필요\n'
                '- <b>다음:</b> 발언 원문·공식 명령 → 실제 작전·지원 정책 → 휴전 합의·이행 여부'
            )
        statement = bool(set(kinds) & {'attack_pause', 'mixed_restraint'})
        core = ('공격 자제·중단 발언과 상대 공격 지속 관련 보도' if statement else
                '제재·외교적 규탄·군사개입 검토 관련 보도')
        market_line = ('한쪽의 자제 발언만으로 유가·해운·보험 위험프리미엄 하락을 단정할 수 없음' if statement else
                       '거래 제한·협상 제약의 영향은 가능하나 유가·해운·보험료 방향은 별도 관측 필요')
        next_line = ('발언 원문·양측 공식 동의 → 실제 공격·피해·운영 제한 → 휴전 이행 여부' if statement else
                     '제재 발효·대상 확인 → 공식 군사 명령 여부 → 실제 작전·운영 영향')
        return (
            '<b>투자 판정</b>\n'
            f'- <b>핵심:</b> {core}\n'
            + ('- <b>현재 단계:</b> 일방적 자제 발언·상대 공격 지속 주장 — 양측 휴전 이행 미확인\n' if statement else
               '- <b>현재 단계:</b> 발언·경제·외교 조치와 검토 단계 — 새로운 군사작전 개시는 확인되지 않음\n')
            + ('- <b>확인:</b> 공격 중단 발언만으로 양측 휴전 합의·실제 이행이 확인되지는 않음\n' if statement else '')
            +
            f'- <b>시장:</b> {market_line}\n'
            f'- <b>다음:</b> {next_line}'
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


def _source_aliases(state):
    aliases = state.get('source_aliases', {})
    if not isinstance(aliases, dict) or any(
            not isinstance(alias, str) or not alias or not isinstance(target, str)
            or not target or alias == target for alias, target in aliases.items()):
        raise RuntimeError('War watch has invalid source alias history; state preserved')
    return aliases


def _publisher_host(row):
    for key in ('source_url', 'resolved_url', 'link'):
        host = (urllib.parse.urlparse(row.get(key) or '').hostname or '').lower().removeprefix('www.')
        if host and host not in ('news.google.com', 'bing.com'):
            return host
    return ''


def _same_source_article(left, right):
    """Collapse only one publisher's matching ordered headline and publication."""
    source = str(left.get('source') or '').strip().casefold()
    if not source or source != str(right.get('source') or '').strip().casefold():
        return False
    hosts = (_publisher_host(left), _publisher_host(right))
    if all(hosts) and hosts[0] != hosts[1]:
        return False
    if any((row.get('source_metadata') or {}).get('publication_status') == 'conflict'
           for row in (left, right)):
        return False
    stamps = [watch.parse_pub(row.get('published')) for row in (left, right)]
    return bool(stamps[0] is not None and stamps[0] == stamps[1]
                and watch.evidence.title_matches(left, right.get('title_original') or right.get('title')))


def _origin_rank(row):
    metadata = row.get('source_metadata') or {}
    url = row.get('resolved_url') or row.get('link')
    publisher = watch.evidence.publisher_matches(row, url)
    exact_body = bool(row.get('body_verified') and publisher
                      and watch.evidence.title_matches(row, metadata.get('title')))
    return exact_body, metadata.get('publication_status') == 'verified', publisher


def _dedupe_source_articles(items):
    groups = []
    for row in items:
        group = next((group for group in groups if _same_source_article(group[0], row)), None)
        if group is None:
            groups.append([row])
        else:
            group.append(row)
    visible = []
    for group in groups:
        winner = max(group, key=_origin_rank)
        visible.append(winner)
        for row in group:
            if row is not winner:
                row['render_withheld'] = 'duplicate_source_article'
                row['duplicate_of'] = winner['id']
                row['duplicate_basis'] = 'same_publisher_ordered_headline_publication'
    return visible


def _distinct_publisher_headlines(items):
    """Select one matching headline without asserting cross-publisher identity."""
    selected = []
    for row in items:
        source = str(row.get('source') or '').strip().casefold()
        title = _headline(row)
        if source:
            title = re.sub(r'\s+[-|]\s+' + re.escape(source) + r'\s*$', '', title)
        key = re.findall(r'[^\W_]+', title, re.UNICODE)
        collision = False
        for other, other_key in selected:
            other_source = str(other.get('source') or '').strip().casefold()
            hosts = (_publisher_host(row), _publisher_host(other))
            if (key and key == other_key and source and other_source and source != other_source
                    and all(hosts) and hosts[0] != hosts[1]):
                collision = True
                break
        if collision:
            row['render_withheld'] = 'same_headline_distinct_publisher'
        else:
            selected.append((row, key))
    return [row for row, _ in selected]


def build_alert(items, markets, now):
    state = watch.load_state()
    aliases, seen = _source_aliases(state), set(state.get('seen', []))
    for row in items:
        # These annotations belong to this render, not an earlier replay.
        if row.get('render_withheld') in ('duplicate_source_article', 'source_alias_already_seen', 'discovery_publication_stale',
                                        'discovery_publication_unverified', 'discovery_publication_future',
                                        'same_headline_distinct_publisher'):
            row.pop('render_withheld')
            row.pop('duplicate_of', None)
            row.pop('duplicate_basis', None)
        target = aliases.get(row.get('id'))
        if target in seen:
            row['render_withheld'] = 'source_alias_already_seen'
            row['duplicate_of'] = target
    targets = [row for row in items[:8] if row.get('render_withheld') != 'source_alias_already_seen']
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(items)))) as executor:
        list(executor.map(body_parallel._safe_enrich, targets))
    visible = []
    for row in items:
        if row.get('render_withheld') == 'source_alias_already_seen':
            continue
        metadata = row.get('source_metadata') or {}
        dates = [dt.datetime.fromisoformat(value['at_kst']) for value in metadata.get('publication_candidates', [])]
        if dates and (min(dates) < now - dt.timedelta(hours=3) or max(dates) > now + dt.timedelta(minutes=5)):
            row['render_withheld'] = 'origin_publication_stale_or_future'
            continue
        stamp = watch.parse_pub(row.get('published'))
        if stamp is None or stamp > now + dt.timedelta(minutes=5):
            row['render_withheld'] = 'discovery_publication_unverified' if stamp is None else 'discovery_publication_future'
            continue
        age = watch.age_minutes(row, now)
        if age is not None and age > 3 * 60:
            row['render_withheld'] = 'discovery_publication_stale'
            continue
        visible.append(row)
    visible = _dedupe_source_articles(visible)
    visible = _distinct_publisher_headlines(visible)
    if not visible:
        return ''
    for row in items:
        kind = non_military_kind(row)
        if kind == 'market_effect':
            _clear_market_event_cache(row)
        if _headline_event_cache_required(row, kind):
            _clear_headline_event_cache(row, kind)
        if maritime_attack_tally(row):
            # Older maritime templates describe one specific projectile cluster.
            # The current headline instead reports a population over a period.
            row['signals_ko'] = []
            row['tags'] = list(dict.fromkeys(
                '선박피격집계' if tag == '유조선피격' else tag for tag in row.get('tags', [])))
        if kind:
            row['non_military_kind'] = kind
            row['tags'] = [tag for tag in row.get('tags', []) if tag not in ('확전', '확전위험', '공격확대예고')]
            row['tags'].append(_headline_event_label(row, kind))
            row['tags'] = list(dict.fromkeys(row['tags']))
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
        primary = _primary_topic(row)
        if primary:
            lines[start] = re.sub(r'(<b>\d+\.\s*).*?(</b>)',
                                  lambda match: match.group(1) + html.escape(primary) + match.group(2),
                                  lines[start], count=1)
        if kind in ('attack_pause', 'mixed_restraint') or primary:
            # Preserve the original speaker and both clauses instead of the
            # older template's invented promise to increase Ukrainian strikes.
            lines[start + 1] = html.escape(_display_headline(row))
        for i in range(start + 1, end):
            line_urls = {html.unescape(value) for value in re.findall(r'<a href="([^"]+)"', lines[i])}
            if not line_urls & {row.get('link'), row.get('resolved_url')}:
                continue
            if ' KST · ' in lines[i] and '<b>' in lines[i]:
                tail = re.split(r'</b>\s*·\s*', lines[i], maxsplit=1)
                if len(tail) == 2:
                    lines[i] = _publication_label(row, now) + ' · ' + tail[1]
            if kind:
                lines[i] = lines[i].replace(' · 확전 · ', ' · ' + _headline_event_label(row, kind) + ' · ')
            if not row.get('body_verified') and 'news.google.com/' in str(row.get('link')):
                lines[i] = lines[i].replace(' 원문</a>', ' 검색 링크</a>')
                lines[i] += ' · 제목 기준·본문 미확인'
            elif not row.get('body_verified'):
                lines[i] += ' · RSS 입력 기준·본문 미확인'
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
    yellow_kinds = {non_military_kind(row) for row in rendered_rows if final_color(row) == 'yellow'}
    if yellow_kinds == {'market_effect'}:
        yellow_label = '물가·시장 파급 보도'
    elif yellow_kinds and yellow_kinds <= {'maritime_shipping', 'oil_market', 'oil_pressure'}:
        yellow_label = '운항·원유시장·경제 압박 보도'
    elif 'market_effect' in yellow_kinds:
        yellow_label += '·시장 파급'
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
    result = '\n'.join(lines)
    if rendered_rows and '<b>투자 판정</b>' in result:
        # The older builder receives all candidates but displays at most four.
        # A deferred attack must not set the verdict of four diplomatic items.
        result = result.split('<b>투자 판정</b>', 1)[0] + verdict(rendered_rows)
    return result.strip() + '\n'


def finalize():
    """Remember proved aliases only after their rendered target is delivered."""
    if not watch.PENDING.exists():
        return
    pending = json.loads(watch.PENDING.read_text(encoding='utf-8'))
    state = watch.load_state()
    aliases = dict(_source_aliases(state))
    ids = pending.get('ids', [])
    if watch.AUDIT.exists():
        receipt = json.loads(watch.AUDIT.read_text(encoding='utf-8'))
        rendered = {row['id']: row for row in receipt['articles'] if row.get('rendered')}
        if len(ids) != len(set(ids)) or set(ids) != set(rendered):
            raise RuntimeError('WAR_INTEGRITY_GATE: alias finalization pending differs from rendered IDs')
        for row in receipt['articles']:
            if row.get('render_withheld') != 'duplicate_source_article':
                continue
            target = rendered.get(row.get('duplicate_of'))
            if target is None:
                continue
            if (row.get('rendered') or row['id'] == target['id']
                    or not _same_source_article(row, target)):
                raise RuntimeError('WAR_INTEGRITY_GATE: source alias lacks matching publisher evidence')
            aliases[row['id']] = target['id']
    seen = list(dict.fromkeys(list(state.get('seen', [])) + list(ids)))[-1200:]
    state.update(seen=seen, updated_at=dt.datetime.now(watch.KST).isoformat(timespec='seconds'))
    if aliases or 'source_aliases' in state:
        # Targets use the existing seen retention window. Unrendered aliases
        # never enter seen and never suppress an undelivered target.
        state['source_aliases'] = {alias: target for alias, target in aliases.items() if target in seen}
    watch.STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


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
        primary = _primary_topic(row)
        if primary and html.escape(primary) not in lines[start]:
            raise RuntimeError('WAR_INTEGRITY_GATE: rendered topic differs from headline event')
        queried = dt.datetime.fromisoformat(receipt['queried_at_kst'])
        age = watch.age_minutes(row, queried)
        if age is not None and age > 3 * 60:
            raise RuntimeError('WAR_INTEGRITY_GATE: stale discovery publication in rendered source')
        if non_military_kind(row) in ('military_statement', 'support_statement', 'military_position', 'corporate_spending', 'market_reaction', 'maritime_routing', 'military_discussion', 'military_analysis', 'market_effect', 'ceasefire_position', 'military_report', 'reaction', 'fuel_shipping', 'trade_proposal', 'diplomatic_contact', 'diplomatic_analysis', 'diplomatic_position', 'diplomatic_plan', 'diplomatic_statement', 'diplomatic_appeal', 'operational_disruption', 'maritime_shipping', 'oil_market', 'oil_pressure') and (
                row.get('classification_color') != 'yellow' or not lines[start].startswith('🟡')):
            raise RuntimeError('WAR_INTEGRITY_GATE: statement presented as a new attack or implemented peace')
        marker = {'red': '🔴', 'green': '🟢', 'yellow': '🟡'}.get(row.get('classification_color'), '')
        if marker and not lines[start].startswith(marker):
            raise RuntimeError('WAR_INTEGRITY_GATE: final marker differs from event stage')
        if (row.get('non_military_kind') == 'attack_pause' or refinery_attack_denial(row)) and any(
                phrase in block for phrase in ('공격 확대 방침', '공격확대예고')):
            raise RuntimeError('WAR_INTEGRITY_GATE: attack denial rewritten as escalation')
        if (row.get('non_military_kind') == 'mixed_restraint' or mixed_restraint_attack(row)) and (
                row.get('non_military_kind') != 'mixed_restraint'
                or row.get('classification_color') != 'yellow' or not lines[start].startswith('🟡')):
            raise RuntimeError('WAR_INTEGRITY_GATE: unilateral restraint shown as bilateral peace')
        if primary and (start + 1 >= end or lines[start + 1] != html.escape(_display_headline(row))):
            raise RuntimeError('WAR_INTEGRITY_GATE: rendered headline differs from source headline')
        stamp = watch.parse_pub(row.get('published'))
        if stamp is None or stamp > queried + dt.timedelta(minutes=5):
            raise RuntimeError('WAR_INTEGRITY_GATE: unverified or future discovery publication in rendered source')
        current_kind = non_military_kind(row)
        if _headline_event_cache_required(row, current_kind):
            source_line = next((i for i in range(start + 2, end)
                                if any(url in lines[i] for url in urls) and ' KST' in lines[i]), None)
            if source_line is not None and any(line.strip() for line in lines[start + 2:source_line]):
                raise RuntimeError('WAR_INTEGRITY_GATE: headline event contains background summary')
            if (row.get('tags') != [_headline_event_label(row, current_kind)]
                    or row.get('signals_ko') or row.get('forced_tags')):
                raise RuntimeError('WAR_INTEGRITY_GATE: headline event retains background event cache')
        if (current_kind is None and _ceasefire_rejection_headline(_headline(row))
                and _military_actions(_headline(row)) and (
                    row.get('classification_color') != 'red' or not lines[start].startswith('🔴'))):
            raise RuntimeError('WAR_INTEGRITY_GATE: separate actual action hidden by ceasefire position')
        if current_kind is None and _headline_refinery_action(row) and (
                row.get('classification_color') != 'red' or not lines[start].startswith('🔴')):
            raise RuntimeError('WAR_INTEGRITY_GATE: refinery attack headline hidden by background stage')
        if current_kind is None and _headline_drone_action(row) and (
                row.get('classification_color') != 'red' or not lines[start].startswith('🔴')):
            raise RuntimeError('WAR_INTEGRITY_GATE: drone attack headline hidden by background stage')
        if current_kind is None and _maritime_attack_expansion(row) and (
                row.get('classification_color') != 'red' or not lines[start].startswith('🔴')):
            raise RuntimeError('WAR_INTEGRITY_GATE: maritime attack expansion hidden by market background')
        if current_kind is None and _headline_attack_casualties(row) and (
                row.get('classification_color') != 'red' or not lines[start].startswith('🔴')):
            raise RuntimeError('WAR_INTEGRITY_GATE: attack casualties hidden by background stage')
        if current_kind is None and _energy_facility_headline(row) and _military_actions(_headline(row)) and (
                row.get('classification_color') != 'red' or not lines[start].startswith('🔴')):
            raise RuntimeError('WAR_INTEGRITY_GATE: separate actual action hidden by energy facility plan')
        if not row.get('body_verified') and '본문 미확인' not in block:
            raise RuntimeError('WAR_INTEGRITY_GATE: unverified source body lacks visible limitation')
    if set(matched) != set(ids):
        raise RuntimeError('WAR_INTEGRITY_GATE: duplicated or omitted rendered source')
    if rows and all(non_military_kind(row) for row in rows) and '<b>투자 판정</b>' in text:
        actual_verdict = '<b>투자 판정</b>' + text.split('<b>투자 판정</b>', 1)[1]
        if actual_verdict.strip() != verdict(rows).strip():
            raise RuntimeError('WAR_INTEGRITY_GATE: final verdict differs from rendered headline stages')
    for row in receipt['markets']:
        price, close, pct = row['price'], row['previous_close'], row['pct']
        if not all(math.isfinite(value) for value in (price, close, pct)) or price <= 0 or close <= 0:
            raise RuntimeError('WAR_INTEGRITY_GATE: invalid market operands')
        if not math.isclose(pct, (price / close - 1) * 100, rel_tol=1e-12, abs_tol=1e-9):
            raise RuntimeError('WAR_INTEGRITY_GATE: market change differs from saved operands')
        if row.get('previous_close_date_verified') is False and '전일' in row.get('basis', ''):
            raise RuntimeError('WAR_INTEGRITY_GATE: undated comparison close labelled as previous day')


watch.parse_pub = parse_pub
watch.score_item, watch.topic_label, watch.build_alert = score_item, topic_label, build_alert
watch.finalize = finalize
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
