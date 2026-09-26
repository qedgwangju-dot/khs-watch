from __future__ import annotations

import datetime as dt
import json
import re

import jemperli_altb4_watch as base


CURRENT_EVENT_START = dt.date(2026, 8, 24)
CURRENT_EVENT_END = dt.date(2026, 9, 7)
CURRENT_EVENT_KEY = base.digest('jemperli|us|rectal|priority_review')
CANADA_EVENT_START = dt.date(2026, 9, 24)
CANADA_EVENT_END = dt.date(2026, 10, 8)
CANADA_EVENT_KEY = base.digest('jemperli|canada|rectal|snds_review_accepted')
CANADA_GSK_URL = 'https://ca.gsk.com/en-ca/media/press-releases/gsk-s-jemperli-dostarlimab-accepted-for-review-by-health-canada-for-patients-with-dmmrmsi-h-locally-advanced-rectal-cancer/'


def is_current_rectal_priority_story(item: base.Item) -> bool:
    low = item.full.lower()
    if 'jemperli' not in low and 'dostarlimab' not in low:
        return False
    stamp = base.parse_published(item.published)
    if stamp is not None:
        day = stamp.date()
        if not (CURRENT_EVENT_START <= day <= CURRENT_EVENT_END):
            return False
    regulatory_signal = any(
        x in low
        for x in (
            'priority review',
            'supplemental biologics license',
            'sbla',
            'accepted for priority review',
        )
    )
    return regulatory_signal


def is_canada_rectal_review_story(item: base.Item) -> bool:
    low = item.full.lower()
    if 'jemperli' not in low and 'dostarlimab' not in low:
        return False
    stamp = base.parse_published(item.published)
    if stamp is not None:
        day = stamp.date()
        if not (CANADA_EVENT_START <= day <= CANADA_EVENT_END):
            return False
    country_signal = any(x in low for x in ('health canada', 'canada', 'canadian', 'santé canada'))
    rectal_signal = any(x in low for x in ('rectal', '직장암'))
    review_signal = any(
        x in low
        for x in (
            'accepted for review',
            'accepted for review by health canada',
            'supplemental new drug submission',
            'snds',
            'notice of compliance with conditions',
            'noc/c',
            'project orbis',
            'présentation supplémentaire de drogue nouvelle',
        )
    )
    return country_signal and rectal_signal and review_signal


def _jurisdiction(item: base.Item) -> str:
    low = item.full.lower()
    if any(x in low for x in ('health canada', 'canada', 'canadian', 'santé canada')):
        return 'canada'
    if any(x in low for x in ('fda', 'united states', 'u.s.', ' us ')):
        return 'us'
    if any(x in low for x in ('ema', 'european commission', 'european union', ' eu ')):
        return 'eu'
    if any(x in low for x in ('mhra', 'united kingdom', ' uk ')):
        return 'uk'
    return 'global'


def _stage(item: base.Item) -> str:
    low = item.full.lower()
    if any(x in low for x in ('approved', 'approval', '승인')):
        return 'approved'
    if 'pdufa' in low:
        return 'pdufa'
    if 'priority review' in low or '우선 검토' in low:
        return 'priority_review'
    if any(x in low for x in ('sbla', 'snds', 'submission', 'filed', 'accepted for review', 'accepted')):
        return 'regulatory_filing'
    if any(x in low for x in ('subcutaneous', 'alt-b4', 'hybrozyme', 'berahyaluronidase', '피하주사')):
        return 'sc_altb4'
    if any(x in low for x in ('azur-1', 'azur-2', 'azur-4', 'domenica', 'jade', 'phase 2', 'phase 3')):
        return 'clinical_update'
    if any(x in low for x in ('sales', 'revenue', '매출')):
        return 'sales'
    return 'material'


def event_key(item: base.Item) -> str:
    low = item.full.lower()

    if is_canada_rectal_review_story(item):
        return CANADA_EVENT_KEY
    if is_current_rectal_priority_story(item):
        return CURRENT_EVENT_KEY

    indication = 'rectal' if any(x in low for x in ('rectal', '직장암')) else 'other'
    return base.digest(f'jemperli|{_jurisdiction(item)}|{indication}|{_stage(item)}')


_original_is_relevant = base.is_relevant


def is_relevant(item: base.Item) -> bool:
    if not _original_is_relevant(item):
        return False
    # 사건의 성격을 식별하지 못한 재보도는 Telegram으로 보내지 않는다.
    # 이후 공식자료/제목에 허가·임상·매출 등 구체 신호가 붙으면 다시 포착된다.
    return _stage(item) != 'material'


def _enrich_with_current_gsk_release(item: base.Item, body: str, resolved: str) -> tuple[str, str, bool]:
    official_url = ''
    if is_canada_rectal_review_story(item):
        official_url = CANADA_GSK_URL
    elif is_current_rectal_priority_story(item):
        official_url = base.CURRENT_GSK_URL
    if not official_url:
        return body, resolved, False
    try:
        page, final = base.fetch(official_url, timeout=20)
        official_body = base.extract_article_text(page)
        if official_body:
            return f'{body} {official_body}'.strip(), base.canonicalize_url(final or official_url), True
    except Exception:
        pass
    return body, resolved, False


def build_item_summary(item: base.Item) -> str:
    body, resolved = base.fetch_body(item)
    body, resolved, enriched = _enrich_with_current_gsk_release(item, body, resolved)
    full = f'{item.full} {body}'.strip()
    low = full.lower()
    official = base.source_class(item) == '공식자료' or enriched

    rectal = any(x in low for x in ('rectal cancer', 'locally advanced rectal', '직장암'))
    priority = 'priority review' in low or '우선 검토' in low
    canada_review = is_canada_rectal_review_story(item) or ('health canada' in low and rectal and 'project orbis' in low)

    if canada_review:
        headline = 'GSK Jemperli, 캐나다 직장암 추가 허가 신청 심사 접수'
    elif rectal and priority:
        headline = 'GSK Jemperli, 미국 직장암 적응증 우선 검토'
    else:
        jurisdiction = {'canada':'캐나다', 'us':'미국', 'eu':'유럽', 'uk':'영국'}.get(_jurisdiction(item), '')
        stage = _stage(item)
        action = {
            'approved': '승인',
            'pdufa': '허가 결정 일정 업데이트',
            'priority_review': '우선 검토',
            'regulatory_filing': '허가 신청·심사 접수',
            'sc_altb4': 'ALT-B4 피하주사 개발 업데이트',
            'clinical_update': '임상 결과 업데이트',
            'sales': '매출 업데이트',
        }.get(stage, '새 변화')
        where = f'{jurisdiction} ' if jurisdiction else ''
        headline = f'GSK Jemperli, {where}{action}'

    population = (
        '이전 치료를 받지 않은 2·3기 dMMR/MSI-H 국소 진행성 직장암'
        if rectal and ('stage ii' in low or 'stage iii' in low)
        else 'Jemperli 개발·허가 대상 환자군'
    )

    regulatory: list[str] = []
    if canada_review and any(x in low for x in ('supplemental new drug submission', 'snds')):
        regulatory.append('추가 신약 허가 신청(SNDS) 심사 접수')
    if 'supplemental biologics license' in low or 'sbla' in low:
        regulatory.append('추가 생물학적 제제 허가 신청(sBLA) 접수')
    if priority:
        regulatory.append('우선 검토')
    if 'february 2027' in low and ('pdufa' in low or 'action date' in low):
        regulatory.append('허가 결정 예정일(PDUFA) 2027년 2월')
    if base.contains_any(full, ('National Priority Voucher', "Commissioner's National Priority Voucher")):
        regulatory.append('국가 우선 바우처 적용 시 결정 시점 추가 단축 가능')
    if canada_review and any(x in low for x in ('notice of compliance with conditions', 'noc/c')):
        regulatory.append('조건부 허가 심사 정책(NOC/c) 적용')
    if 'project orbis' in low:
        regulatory.append('국제 공동심사 프로그램(Project Orbis) 병행')
    regulatory_line = ' · '.join(regulatory) if regulatory else '규제 단계 추가 확인 필요'

    trial_parts: list[str] = []
    if 'azur-1' in low:
        trial_parts.append('AZUR-1 단일군 2상')
    if re.search(r'\b154\s+(?:patients|participants)', full, re.I):
        trial_parts.append('154명')
    if canada_review and ('500mg' in low or '500 mg' in low):
        trial_parts.append('500mg 정맥주사·3주 간격·9회(약 6개월)')
    if 'clinical complete response' in low or 'ccr12' in low:
        trial_parts.append('12개월 임상적 완전반응(cCR12) 지속')
    if any(x in low for x in ('eliminate the need for chemotherapy', 'eliminating or delaying the need for chemotherapy')):
        trial_parts.append('일부 환자에서 화학요법·방사선·수술 회피 또는 지연 가능성')
    if 'safety' in low and 'consistent' in low:
        trial_parts.append('안전성은 기존 프로파일과 대체로 일관')
    trial_line = ' · '.join(trial_parts) if trial_parts else '임상 핵심 수치·결과 추가 확인 필요'

    alteogen_line = (
        '이번 건은 정맥주사 Jemperli의 적응증 확대이며 ALT-B4 피하주사 허가 자체는 아닙니다. '
        '다만 적응증 확대는 향후 ALT-B4 기반 피하주사 개발·허가가 성공할 경우 '
        '전환 가능한 환자·매출 기반을 넓히는 요인입니다.'
    )

    if canada_review:
        next_line = '캐나다 보건부 심사 결과 + 2026년 후속 학회 AZUR-1 상세 데이터 + Jemperli 피하주사(ALT-B4) 개발 진행'
    elif rectal and priority:
        next_line = '미국 식품의약국 최종 결정 + Jemperli 피하주사(ALT-B4) 임상 개시·허가 신청·승인'
    else:
        next_line = '후속 미국 식품의약국·유럽의약품청 허가, 주요 임상 결과, ALT-B4 피하주사 개발 진행'

    lines = [
        f'**{headline}**',
        '',
        f'- **규제:** {population}\n  {regulatory_line}',
        '',
        f'- **임상:** {trial_line}',
        '',
        f'- **알테오젠:** {alteogen_line}',
        '',
        f'- **다음 확인:** {next_line}',
        '',
        f"- **원문 확인:** {'GSK 공식자료 본문 직접 열람' if official and body else ('기사 본문 직접 열람' if body else '원문 본문 자동 추출 불완전')}",
        f'- 원문: {resolved}',
    ]
    return '\n'.join(lines)


def migrate_state_once() -> None:
    state = base.load_state()
    if int(state.get('dedupe_version') or 1) >= 4:
        return
    seen_events = set(state.get('seen_event_keys') or [])
    # 이번 직장암 우선검토 사건은 이미 사용자에게 전달된 기존 사건이므로
    # 새 중복키 체계 도입 시 재송출되지 않도록 기준선에 등록한다.
    seen_events.add(CURRENT_EVENT_KEY)
    seen_events.add(CANADA_EVENT_KEY)
    state['seen_event_keys'] = base.cap(seen_events)
    state['dedupe_version'] = 4
    base.STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')



_original_gsk_official_items = base.gsk_official_items


def gsk_official_items() -> list[base.Item]:
    items = _original_gsk_official_items()
    items.append(
        base.Item(
            'GSK 공식',
            'Jemperli(dostarlimab), 캐나다 보건부의 dMMR/MSI-H 국소 진행성 직장암 추가 허가 신청 심사 접수',
            CANADA_GSK_URL,
            'Thu, 24 Sep 2026 12:00:00 GMT',
        )
    )
    return items

def main() -> int:
    migrate_state_once()
    base.event_key = event_key
    base.is_relevant = is_relevant
    base.build_item_summary = build_item_summary
    base.gsk_official_items = gsk_official_items
    return base.main()


if __name__ == '__main__':
    raise SystemExit(main())
