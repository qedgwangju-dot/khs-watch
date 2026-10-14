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
KIND_LABELS = {'sanctions': '제재·압박', 'reaction': '외교반응·개입검토',
               'attack_pause': '공격 중단·부인 발언', 'mixed_restraint': '자제 발언·상대 공격 주장',
               'military_statement': '군사 대응·보복 발언', 'support_statement': '지원 정책 발언',
               'military_discussion': '공습 재개 논의·이견', 'military_analysis': '군사·안보 해설',
               'market_effect': '전쟁의 물가 파급 보도'}


def _headline(row):
    return html.unescape(str(row.get('title_original') or row.get('title') or row.get('title_ko') or '')).lower()


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


def _riyadh_missile_headline(row):
    """The headline identifies this report; body background is a separate event."""
    title = _headline(row)
    return bool(re.search(r'리야드|\briyadh\b', title)
                and re.search(r'미사일|\bmissiles?\b', title)
                and re.search(r'후티|\bhouthi', title))


def _display_headline(row):
    original = str(row.get('title_original') or row.get('title') or '')
    return original if _riyadh_missile_headline(row) or re.search(r'[가-힣]', original) else str(row.get('title_ko') or original)


def _headline_group(title):
    """Use actors in the current headline, before background actors or caches."""
    us = bool(re.search(r'미국|트럼프|(?:^|\s)美(?:\s|,)|\b(?:trump|united states)\b|'
                        r'\bu\.s\.(?=\s|$)|^us(?=\s|:|,)', title))
    if re.search(r'후티|\bhouthi', title):
        if us:
            return '미국·후티'
        return '사우디·후티' if re.search(r'사우디|\bsaudi\b', title) else '후티'
    if re.search(r'우크라|러시아|\b(?:ukrain|russia)', title):
        return '우크라이나·러시아'
    if re.search(r'이란|\biran\b', title):
        if re.search(r'이스라엘|네타냐후|\b(?:israel|netanyahu)\b', title):
            return '미국·이스라엘·이란' if us else '이스라엘·이란'
        return '미국·이란' if us else '이란'
    if re.search(r'이스라엘|네타냐후|\b(?:israel|netanyahu)\b', title):
        return '미국·이스라엘' if us else '이스라엘'
    return '전쟁·외교'


def _primary_topic(row):
    title = _headline(row)
    kind = non_military_kind(row)
    if kind == 'market_effect':
        us_prices = re.search(r'(?:미국|美|united states|u\.s\.).{0,12}(?:물가|cpi|inflation)', title)
        return ('미국·물가' if us_prices else '물가·경제지표') + ' · 전쟁 파급 보도'
    if kind in ('military_statement', 'military_discussion', 'military_analysis'):
        return _headline_group(title) + ' · ' + KIND_LABELS[kind]
    if kind == 'support_statement':
        label = '정보 지원·종전 의향 발언' if re.search(r'종전|peace|end.{0,8}war', title) else '지원 정책 발언'
        return _headline_group(title) + ' · ' + label
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


def mixed_restraint_attack(row):
    title = html.unescape(str(row.get('title_original') or row.get('title') or '')).lower()
    title = title.replace('’', "'").replace('‘', "'")
    korean_restraint = r'공격(?:을)?\s*(?:자제|중단|멈|안)'
    english_restraint = r'\b(?:halt(?:ed)?|stopp?ed|paus(?:e|ed))\s+(?:energy\s+)?(?:attacks?|strikes?)\b'
    contrast_clause = r'하지만|했지만|했으나|그러나|반면|에도|…|\.\.\.|\b(?:despite|but|while|although|yet)\b'
    restraint = bool(re.search(r'휴전|ceasefire|truce|' + korean_restraint + '|' + english_restraint, title))
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


def _military_analysis_headline(title):
    military = re.search(r'미사일|공습|공격|방패|방공|요격|\b(?:missile|attack|airstrike|shield|defen[cs]e)', title)
    question = re.search(r'왜|어째서|\b(?:why|how)\b', title) and re.search(r'\?|까요|는가|했나', title)
    return bool(military and question)


def non_military_kind(row):
    title = html.unescape(str(row.get('title_original') or row.get('title') or row.get('title_ko') or '')).lower()
    if mixed_restraint_attack(row):
        return 'mixed_restraint'
    # Require an explicit new-action predicate before background weapon nouns
    # can turn a sanctions listing or a condemnation into a military event.
    discussion = _military_discussion_spans(title)
    actions = list(re.finditer(
        r'공습\s*(?:개시|재개|감행)|공격\s*(?:개시|재개|감행)|미사일\s*발사|'
        r'보복\s*(?:공습|공격)\s*(?:개시|실시)|'
        r'\band\s+(?:attacks?|strikes?|bombs?)\b|'
        r'\b(?:launches?|launched|conducts?|conducted|resumes?|resumed)\s+(?:new\s+)?(?:attacks?|strikes?|airstrikes?)',
        title))
    if any(not any(span.start() <= action.start() and action.end() <= span.end()
                   for span in discussion) for action in actions):
        return None
    if discussion:
        return 'military_discussion'
    if _military_analysis_headline(title):
        return 'military_analysis'
    if refinery_attack_denial(row):
        return 'attack_pause'
    if re.search(r'제재|\bsanctions?\b|restrictive measures', title):
        if not re.search(r'공항.*피격|드론.*공격|\b(?:attacked|struck|bombed)\b', title):
            return 'sanctions'
    if re.search(r'규탄|비난|\bcondemns?\b|\bdenounces?\b', title):
        return 'reaction'
    # The new event can be a statement even when its background describes real
    # or historical attacks. An explicit newly launched attack above wins.
    if re.search(r'(?:보복|공격|공습|군사작전|타격).{0,18}(?:시사|예고|경고|위협|검토|가능성)|'
                 r'\b(?:warns?|threatens?|considers?).{0,55}(?:retaliat|attack|strike)|'
                 r'\bretaliation.{0,30}(?:warning|threat)', title):
        return 'military_statement'
    if re.search(r'정보.{0,8}(?:지원|공유).{0,18}(?:유지|계속|부인|중단하지\s*않)|'
                 r'\b(?:intelligence|information).{0,15}(?:support|sharing).{0,20}(?:maintain|continu)|'
                 r'\b(?:maintains?|continues?).{0,20}(?:intelligence|information).{0,15}(?:support|sharing)', title):
        return 'support_statement'
    # An inflation report about war costs is not a new diplomatic event.
    prices = re.search(r'소비자물가|물가|\bcpi\b|\binflation\b|consumer prices', title)
    new_peace = re.search(r'(?:휴전|종전|평화협정).{0,12}(?:합의|체결|이행|발효)|'
                          r'\b(?:ceasefire|peace deal).{0,20}(?:agreed|signed|implemented)', title)
    if prices and re.search(r'전쟁|\bwar\b', title) and not new_peace:
        return 'market_effect'
    return None


def _clear_market_event_cache(row):
    row['non_military_kind'] = 'market_effect'
    row['signals_ko'] = []
    row['forced_tags'] = []
    row['tags'] = [KIND_LABELS['market_effect']]
    row.pop('newidea_marks', None)
    row.pop('deep_signal', None)


def score_item(row, now):
    kind = non_military_kind(row)
    if kind == 'market_effect':
        _clear_market_event_cache(row)
        score, _ = source_score._original_score(row, now)
        return score, list(row['tags'])
    score, tags = _score(row, now)
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
        if set(kinds) == {'market_effect'}:
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> 전쟁과 물가 지표의 연결을 다룬 보도\n'
                '- <b>현재 단계:</b> 물가·시장 파급 보도 — 새로운 교전·휴전 이행 여부는 별도 확인 필요\n'
                '- <b>시장:</b> 기사에 인용된 지표와 에너지 가격의 기간·출처를 각각 확인\n'
                '- <b>다음:</b> 공식 지표·공표일 → 에너지 가격·기간 → 전쟁 영향의 독립 확인'
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
        if set(kinds) & {'military_statement', 'support_statement'} and not set(kinds) & {'attack_pause', 'mixed_restraint'}:
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


def build_alert(items, markets, now):
    state = watch.load_state()
    aliases, seen = _source_aliases(state), set(state.get('seen', []))
    for row in items:
        # These annotations belong to this render, not an earlier replay.
        if row.get('render_withheld') in ('duplicate_source_article', 'source_alias_already_seen'):
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
        visible.append(row)
    visible = _dedupe_source_articles(visible)
    if not visible:
        return ''
    for row in items:
        kind = non_military_kind(row)
        if kind == 'market_effect':
            _clear_market_event_cache(row)
        if maritime_attack_tally(row):
            # Older maritime templates describe one specific projectile cluster.
            # The current headline instead reports a population over a period.
            row['signals_ko'] = []
            row['tags'] = list(dict.fromkeys(
                '선박피격집계' if tag == '유조선피격' else tag for tag in row.get('tags', [])))
        if kind:
            row['non_military_kind'] = kind
            row['tags'] = [tag for tag in row.get('tags', []) if tag not in ('확전', '확전위험', '공격확대예고')]
            row['tags'].append(KIND_LABELS[kind])
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
    yellow_kinds = {non_military_kind(row) for row in rendered_rows if final_color(row) == 'yellow'}
    if yellow_kinds == {'market_effect'}:
        yellow_label = '물가·시장 파급 보도'
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
    return '\n'.join(lines).strip() + '\n'


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
        if non_military_kind(row) in ('military_statement', 'support_statement', 'military_discussion', 'military_analysis', 'market_effect') and (
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
