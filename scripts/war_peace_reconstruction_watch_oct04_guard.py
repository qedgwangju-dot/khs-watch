#!/usr/bin/env python3
"""2026-10-04 전쟁 감시 최종 의미·중복·출처 귀속 게이트.

기존 수집/상태/Telegram 경로는 그대로 두고 마지막 판정층만 보강한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import re
import urllib.parse

import war_peace_reconstruction_watch_diplomacy_flash as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_orig_emergency_marks = prev._emergency_marks
_orig_marks = prev._marks
_orig_korean_title = prev._korean_title
_orig_signals = prev._signals
_orig_score_item = watch.score_item
_orig_item_id = watch.item_id
_orig_topic_label = watch.topic_label
_orig_final_color = prev._final_item_color
_orig_verdict = guard._verdict
_orig_semantic_fix = prev._semantic_output_fix
_orig_verify_alert = runner.verify_alert


def _title(row):
    return prev._display_title_text(row)


def _text(row):
    return prev._text(row)


def _published_day(row):
    try:
        pub = watch.parse_pub(row.get("published", ""))
        if pub:
            return pub.astimezone(watch.KST).date().isoformat()
    except Exception:
        pass
    return dt.datetime.now(watch.KST).date().isoformat()


def _week_key():
    iso = dt.datetime.now(watch.KST).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _future_refinery_policy(row):
    # 원제목뿐 아니라 검색 스니펫/본문에 미래형 공격 방침이 있으면 잡는다.
    # 다만 이미 발생한 피격·화재와 구분하기 위해 '향후/계획/예고' 동사가 반드시 필요하다.
    t = _text(row)
    future = any(x in t for x in (
        "will hit", "will strike", "will attack", "plans to strike", "plans to attack",
        "double down on attacking", "vows to strike", "vows to attack",
        "will keep hitting", "will continue hitting", "will intensify strikes",
        "공격하겠다", "타격하겠다", "공격할 것", "타격할 것",
        "공격 확대", "타격 확대", "공격 늘리", "공격을 늘리", "보복 공격 예고",
        "공격을 강화", "타격을 강화", "계속 공격", "계속 타격",
    ))
    target = any(x in t for x in ("refinery", "refineries", "oil refinery", "정유소", "정유시설", "정유 공장"))
    actual_now = any(x in _title(row) for x in (
        "refinery hit", "refinery struck", "refinery attacked", "refinery fire",
        "정유시설 피격", "정유소 피격", "정유시설 화재", "정유소 화재",
    ))
    return future and target and not actual_now


def _aramco_houthi_claim(row):
    title = _title(row)
    text = _text(row)
    aramco_riyadh = (
        any(x in text for x in ("aramco", "아람코"))
        and any(x in text for x in ("riyadh", "리야드"))
    )
    houthi = any(x in text for x in ("houthi", "houthis", "ansar allah", "후티", "안사르 알라", "안사르알라"))
    attack = any(x in text for x in (
        "say they attacked", "says it attacked", "said it attacked", "claimed responsibility",
        "claimed it attacked", "targeted aramco", "attacked aramco",
        "공격했다고 밝혔다", "공격했다고 주장", "공격 주장", "공격했다며",
    ))
    weapon = any(x in text for x in (
        "ballistic missile", "ballistic missiles", "missile", "missiles", "drone", "drones",
        "탄도미사일", "미사일", "드론",
    ))
    return aramco_riyadh and houthi and attack and weapon


def _aramco_fire_unattributed(row):
    title = _title(row)
    text = _text(row)
    core = (
        any(x in title for x in ("aramco", "아람코"))
        and any(x in title for x in ("riyadh", "리야드"))
        and any(x in title for x in ("fire", "smoke", "blaze", "화재", "연기"))
    )
    explicit = any(x in title for x in (
        "missile attack", "drone attack", "attacked by", "strike on", "struck by",
        "미사일 공격", "드론 공격", "공격받", "피격", "공습",
    ))
    uncertain = any(x in text for x in (
        "no immediate claim of responsibility", "no claim of responsibility",
        "no immediate confirmation", "cause was not immediately known",
        "원인 미확정", "배후 미확정", "공격 주체 미확정", "공식 확인 전",
    ))
    return core and not explicit and uncertain and not _aramco_houthi_claim(row)


def _peace_conditions_commentary(row):
    t = _title(row)
    peace = any(x in t for x in (
        "conditions for peace", "peace conditions", "conditions for a peaceful solution",
        "terms for peace", "종전 조건", "평화 조건", "평화적 해결 조건",
    ))
    speaker = any(x in t for x in (
        "medvedev", "comments on", "commented on", "outlined", "names conditions",
        "메드베데프", "논평", "조건을 제시", "조건 제시",
    ))
    return peace and speaker


def _lukoil_side_deal(row):
    title = _title(row)
    text = _text(row)
    commercial = any(x in text for x in (
        "lukoil", "루코일", "oil deal", "big deal", "asset sale",
        "sale of overseas assets", "overseas asset sale", "해외자산 매각",
        "해외 자산 매각", "석유업체 빅딜", "석유 업체 빅딜", "자산 거래",
    ))
    talks = any(x in text for x in (
        "peace talks", "ukraine talks", "ceasefire talks", "종전 협상", "휴전 협상", "우크라 종전",
    ))
    title_hint = any(x in title for x in ("석유업체 빅딜", "oil deal", "lukoil", "루코일"))
    return commercial and talks and title_hint


def _hormuz_tanker_attack(row):
    title = _title(row)
    text = _text(row)
    hormuz = any(x in text for x in ("hormuz", "호르무즈"))
    tanker = any(x in text for x in ("tanker", "tankers", "crude oil tanker", "유조선"))
    hit = any(x in text for x in (
        "struck by an unknown projectile", "struck by unknown projectile", "hit by an unknown projectile",
        "tanker struck", "tankers struck", "attacked", "attack on tanker",
        "피격", "정체불명 발사체", "미확인 발사체", "유조선 공격",
    ))
    title_hit = any(x in title for x in (
        "tanker struck", "tankers struck", "tanker hit", "tankers hit", "tanker attack",
        "유조선 피격", "유조선 공격", "유조선 잇달아 피격", "유조선 2척 피격",
    ))
    recent = any(x in text for x in ("ukmto", "past 24 hours", "last 24 hours", "지난 24시간", "하루 새"))
    return hormuz and tanker and hit and (title_hit or recent)


def _kyiv_bridge_attack(row):
    t = _title(row)
    kyiv = any(x in t for x in ("kyiv", "kiev", "키이우", "키예프"))
    bridge = any(x in t for x in ("bridge", "bridges", "교량", "다리"))
    strike = any(x in t for x in (
        "strikes on", "attacks on", "bridge attack", "bridge strikes",
        "공격", "공습", "피격",
    ))
    return kyiv and bridge and strike


def _kyiv_evacuation_strike_warning(row):
    t = _title(row)
    kyiv = any(x in t for x in ("kyiv", "kiev", "키이우", "키예프"))
    leave = any(x in t for x in ("leave kyiv", "leave kiev", "evacuate", "evacuation", "떠나라", "대피"))
    threat = any(x in _text(row) for x in (
        "massive retaliatory strikes", "massive strikes", "mortal danger",
        "대규모 보복 공격", "대규모 공격", "최후통첩", "위험",
    ))
    return kyiv and leave and threat


def _new_tanker_attack_variant(row):
    t = _title(row)
    return any(x in t for x in ("another tanker", "additional tanker", "fourth tanker", "fifth tanker", "추가 유조선", "또 다른 유조선", "4번째 유조선", "5번째 유조선"))


def emergency_marks(row):
    marks = list(_orig_emergency_marks(row))
    if _aramco_fire_unattributed(row):
        marks = [m for m in marks if m != "후티리야드미사일위협"]
    return sorted(set(marks))


prev._emergency_marks = emergency_marks


def marks(row):
    out = list(_orig_marks(row))
    if _aramco_houthi_claim(row):
        out.append("후티리야드아람코공격주장")
    if _future_refinery_policy(row):
        out.append("러정유시설보복공격확대예고")
    if _aramco_fire_unattributed(row):
        out.append("리야드아람코화재원인미확정")
    if _peace_conditions_commentary(row):
        out.append("러시아종전조건입장표명")
    if _lukoil_side_deal(row):
        out.append("루코일종전협상연계상업거래")
    if _hormuz_tanker_attack(row):
        out.append("호르무즈유조선피격클러스터")
    out = [m for m in out if not (_aramco_fire_unattributed(row) and m == "후티리야드미사일위협")]
    return sorted(set(out))


prev._marks = marks


def korean_title(ms):
    if "후티리야드아람코공격주장" in ms:
        return "후티, 리야드 Aramco 시설 미사일·드론 공격 주장 — 사우디·Aramco 독립 확인 대기"
    if "리야드아람코화재원인미확정" in ms:
        return "리야드 아람코 시설 인근 화재·연기 — 공격 여부·원인·배후 미확정"
    if "러정유시설보복공격확대예고" in ms:
        return "우크라이나, 러시아 정유시설 공격 확대 예고 — 실제 신규 피격 확인과 구분"
    if "러시아종전조건입장표명" in ms:
        return "메드베데프, 우크라이나 종전 조건 재확인 — 실제 합의 진전이 아닌 러시아 측 입장 표명"
    if "루코일종전협상연계상업거래" in ms:
        return "종전 협상 과정에서 루코일 해외자산 매각 논의 — 휴전 진전과 별개의 상업거래"
    if "호르무즈유조선피격클러스터" in ms:
        return "호르무즈 유조선 피격 지속 — 미확인 발사체·선박 피해를 실제 해상안보 사건으로 추적"
    return _orig_korean_title(ms)


prev._korean_title = korean_title


def signals(ms):
    out = []
    if "후티리야드아람코공격주장" in ms:
        out.append("🔴 후티가 리야드 Aramco 시설을 탄도미사일·드론으로 공격했다고 주장 — 현장 화재·연기와 별개로 사우디·Aramco의 피해·요격·원인 공식 확인은 후속 검증")
    if "리야드아람코화재원인미확정" in ms:
        out.append("🟡 Reuters는 리야드 Aramco 시설 인근 화재·연기를 확인했지만 당시 공격 여부·원인·배후는 공식 확인 전")
    if "러정유시설보복공격확대예고" in ms:
        out.append("🟡 젤렌스키의 러시아 정유시설 공격 확대 방침·보복 예고 — 실제 신규 정유시설 피격·화재·가동중단과 분리")
    if "러시아종전조건입장표명" in ms:
        out.append("🟡 메드베데프가 우크라이나 평화 조건을 재확인한 입장 표명 — 회담 타결·휴전 합의로 승격하지 않음")
    if "루코일종전협상연계상업거래" in ms:
        out.append("🟡 푸틴·미 특사 간 루코일 해외자산 매각 논의 — 종전회담과 같은 자리에서 논의됐지만 휴전 진전 자체는 아님")
    if "호르무즈유조선피격클러스터" in ms:
        out.append("🔴 UKMTO 기준 호르무즈·오만 인근 유조선의 미확인 발사체 피격이 반복 — 동일 사건 재인용과 실제 추가 피격을 분리")

    # 이 게이트에서 의미를 확정한 사건은 상위 모듈의 범용 신호를 덧붙이지 않는다.
    # 그래야 '공격 확대 예고'가 '실제 피격', '상업거래'가 '휴전 진전'으로 다시 오염되지 않는다.
    custom = {
        "후티리야드아람코공격주장", "리야드아람코화재원인미확정",
        "러정유시설보복공격확대예고", "러시아종전조건입장표명",
        "루코일종전협상연계상업거래", "호르무즈유조선피격클러스터",
    }
    if set(ms) & custom:
        return out
    return _orig_signals(ms)


prev._signals = signals


def score_item(row, now):
    score, tags = _orig_score_item(row, now)
    ms = set(marks(row))
    tags = list(tags or [])
    yellow = {
        "러정유시설보복공격확대예고", "리야드아람코화재원인미확정",
        "러시아종전조건입장표명", "루코일종전협상연계상업거래",
    }
    if ms & yellow:
        tags = [t for t in tags if t not in ("확전", "휴전·평화", "재건", "종전·협상")]
        tags += ["협상·위협제약"]
        score = max(score, 98)
    if "러정유시설보복공격확대예고" in ms:
        tags += ["우크라이나·러시아", "확전위험", "공격확대예고"]
    if "후티리야드아람코공격주장" in ms:
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["사우디·후티", "확전", "Aramco", "공격주장", "공식확인대기"]
        score = max(score, 100)
    if "리야드아람코화재원인미확정" in ms:
        tags += ["사우디·아람코", "에너지시설위험", "원인미확정"]
    if "러시아종전조건입장표명" in ms:
        tags += ["우크라이나·러시아", "종전조건", "입장표명"]
    if "루코일종전협상연계상업거래" in ms:
        tags += ["우크라이나·러시아", "협상연계상업거래", "이해충돌점검"]
    if "호르무즈유조선피격클러스터" in ms:
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["이란·호르무즈", "확전", "해상안보", "유조선피격"]
        score = max(score, 100)
    if _kyiv_bridge_attack(row) or _kyiv_evacuation_strike_warning(row):
        tags = [t for t in tags if t not in ("휴전·평화", "재건", "종전·협상")]
        tags += ["우크라이나·러시아", "확전", "인프라위험"]
        score = max(score, 100)
    return min(score, 100), sorted(set(tags))


watch.score_item = score_item


def _stable_source_url(row):
    raw = (row.get("resolved_url") or row.get("link") or "").strip()
    if not raw:
        return None
    try:
        p = urllib.parse.urlparse(raw)
        host = p.netloc.lower().replace("www.", "")
        path = re.sub(r"/+$", "", p.path or "/")
        if any(x in host for x in ("reuters.com", "apnews.com", "ukmto.org")) and path:
            return host + path.lower()
    except Exception:
        return None
    return None


def item_id(row):
    if _hormuz_tanker_attack(row):
        key = f"hormuz|tanker-attack-cluster|{_published_day(row)}"
        if _new_tanker_attack_variant(row):
            norm = re.sub(r"\W+", " ", _title(row)).strip()
            key += "|additional|" + norm[:80]
        return hashlib.sha256(("event|" + key).encode()).hexdigest()[:20]
    if _future_refinery_policy(row):
        return hashlib.sha256(("event|ukraine-russia|refinery-retaliation-policy|" + _week_key()).encode()).hexdigest()[:20]
    if _lukoil_side_deal(row):
        return hashlib.sha256(("event|ukraine-russia|lukoil-side-deal|" + _week_key()).encode()).hexdigest()[:20]
    if _aramco_fire_unattributed(row):
        return hashlib.sha256(("event|saudi-aramco|riyadh-unattributed-fire|" + _published_day(row)).encode()).hexdigest()[:20]
    if _peace_conditions_commentary(row):
        return hashlib.sha256(("event|ukraine-russia|peace-conditions-commentary|" + _published_day(row)).encode()).hexdigest()[:20]
    stable = _stable_source_url(row)
    if stable:
        return hashlib.sha256(("url|" + stable).encode()).hexdigest()[:20]
    return _orig_item_id(row)


watch.item_id = item_id


def topic_label(row):
    ms = set(marks(row))
    if "후티리야드아람코공격주장" in ms:
        return "사우디·후티 · Aramco 공격 주장"
    if "리야드아람코화재원인미확정" in ms:
        return "사우디·아람코 · 화재 원인 미확정"
    if "러정유시설보복공격확대예고" in ms:
        return "우크라이나·러시아 · 정유시설 보복 공격 예고"
    if "러시아종전조건입장표명" in ms:
        return "우크라이나·러시아 · 종전 조건 입장"
    if "루코일종전협상연계상업거래" in ms:
        return "우크라이나·러시아 · 종전협상 연계 상업거래"
    if "호르무즈유조선피격클러스터" in ms:
        return "이란·호르무즈 · 유조선 피격"
    return _orig_topic_label(row)


watch.topic_label = topic_label
try:
    prev.clean_mod.clean_topic_label = topic_label
except Exception:
    pass


def final_color(row):
    ms = set(marks(row))
    if "후티리야드아람코공격주장" in ms:
        return "red"
    if ms & {
        "러정유시설보복공격확대예고", "리야드아람코화재원인미확정",
        "러시아종전조건입장표명", "루코일종전협상연계상업거래",
    }:
        return "yellow"
    if "호르무즈유조선피격클러스터" in ms:
        return "red"
    if _kyiv_bridge_attack(row) or _kyiv_evacuation_strike_warning(row):
        return "red"
    return _orig_final_color(row)


prev._final_item_color = final_color
prev._emergency_color = final_color
guard._enhanced_body_color = final_color
guard.prev._strict_body_color = final_color
guard.prev.core._body_color = final_color


_PEACE_MARKS = {
    "아라치위트코프뉴욕회동확인", "이란뉴욕대표단외교전권", "뉴욕중재종전합의안협의",
    "미구체조치시외교재개환영", "이란직접협상확인", "정식휴전합의", "종전합의",
    "크렘린에너지휴전긍정평가", "아라치미국체류추가협상",
}


def verdict(items):
    colors = [final_color(x) for x in items]
    red = "red" in colors
    yellow = "yellow" in colors
    all_marks = {m for x in items for m in marks(x)}
    peace = bool(all_marks & _PEACE_MARKS)
    if any(_kyiv_bridge_attack(x) or _kyiv_evacuation_strike_warning(x) for x in items):
        red = True
    if red and peace:
        return (
            "<b>투자 판정</b>\n"
            "- <b>핵심:</b> 실제 공격과 구체적 외교 진전이 동시에 존재\n"
            "- <b>현재 단계:</b> 혼재 단계 — 협상 문구보다 실제 교전 감소·합의 이행이 우선\n"
            "- <b>시장:</b> 군사 위험과 완화 기대가 충돌해 유가·해운·보험 변동성이 확대될 수 있음\n"
            "- <b>다음:</b> 실제 공격 빈도 → 공식 합의문 → 이행 여부"
        )
    if red:
        return (
            "<b>투자 판정</b>\n"
            "- <b>핵심:</b> 신규 변화의 중심은 실제 공격·해상안보·운영 위험\n"
            "- <b>현재 단계:</b> 군사·안보 위험 지속 — 상업거래나 조건 제시를 휴전 진전으로 보지 않음\n"
            "- <b>시장:</b> 유가·해운·보험 위험프리미엄 상승 압력\n"
            "- <b>다음:</b> 추가 공격 → 시설·선박 피해 → 운항 제한 → 실제 교전 강도"
        )
    if yellow:
        return (
            "<b>투자 판정</b>\n"
            "- <b>핵심:</b> 공격 확대 예고·협상 조건·원인 미확정 위험·상업거래를 실제 공격이나 휴전 진전과 분리\n"
            "- <b>현재 단계:</b> 경계·협상 제약 단계 — 실제 행동 확인 전 방향성 과대평가 금지\n"
            "- <b>시장:</b> 확인 전에는 위험프리미엄의 방향보다 변동성 확대 요인\n"
            "- <b>다음:</b> 실제 공격 발생 → 공식 책임 확인 → 협상 결과 → 운영 영향"
        )
    return _orig_verdict(items)


guard._verdict = verdict


def semantic_fix(text):
    text = _orig_semantic_fix(text)
    lines = text.splitlines()
    item_re = re.compile(r"^(?:[🔴🟢🟡]\s+)?\[(속보|신규|후속)\]\s+<b>(\d+)\.\s+([^<]+)</b>")
    positions = [i for i, line in enumerate(lines) if item_re.search(line)]
    rendered = []
    for n, i in enumerate(positions):
        end = positions[n + 1] if n + 1 < len(positions) else len(lines)
        for j in range(i + 1, end):
            if lines[j] in ("<b>시장 파급</b>", "<b>시장 반응</b>", "<b>투자 판정</b>"):
                end = j
                break
        block = "\n".join(lines[i:end]).lower()
        m = item_re.search(lines[i])
        if not m:
            continue
        level, idx = m.group(1), m.group(2)
        marker = None
        topic = None
        if any(x in block for x in ("리야드 aramco 시설 미사일·드론 공격 주장", "리야드 aramco 시설을 탄도미사일·드론으로 공격했다고 주장")):
            marker, topic = "🔴", "사우디·후티 · Aramco 공격 주장"
        elif any(x in block for x in ("유조선 피격 지속", "유조선 잇달아 피격", "유조선 2척 피격")):
            marker, topic = "🔴", "이란·호르무즈 · 유조선 피격"
        elif any(x in block for x in ("정유시설 공격 확대 예고", "실제 신규 피격 확인과 구분")):
            marker, topic = "🟡", "우크라이나·러시아 · 정유시설 보복 공격 예고"
        elif any(x in block for x in ("아람코 시설 인근 화재·연기", "공격 여부·원인·배후 미확정")):
            marker, topic = "🟡", "사우디·아람코 · 화재 원인 미확정"
        elif any(x in block for x in ("종전 조건 재확인", "실제 합의 진전이 아닌 러시아 측 입장 표명")):
            marker, topic = "🟡", "우크라이나·러시아 · 종전 조건 입장"
        elif any(x in block for x in ("루코일 해외자산 매각", "휴전 진전과 별개의 상업거래")):
            marker, topic = "🟡", "우크라이나·러시아 · 종전협상 연계 상업거래"
        if marker:
            lines[i] = f"{marker} [{level}] <b>{idx}. {topic}</b>"
            rendered.append((marker, block))

    if rendered:
        lines = [line for line in lines if not (
            "<b>공격·확전</b>" in line or "<b>재건·휴전</b>" in line or
            "<b>실물 공급회복</b>" in line or "<b>협상 제약·불확실성</b>" in line or
            "<b>군사위협·협상 제약</b>" in line
        )]
        badges = []
        all_headers = "\n".join(lines).lower()
        if any(m == "🔴" for m, _ in rendered) or "🔴 [신규]" in all_headers or "🔴 [속보]" in all_headers:
            badges.append("🔴 <b>공격·확전</b>")
        if "🟢 [신규]" in all_headers or "🟢 [속보]" in all_headers or "🟢 [후속]" in all_headers:
            if any(x in all_headers for x in ("실물물동량", "원유공급회복", "원유 물동량 회복")):
                badges.append("🟢 <b>실물 공급회복</b>")
            else:
                badges.append("🟢 <b>재건·휴전</b>")
        if any(m == "🟡" for m, _ in rendered) or "🟡 [신규]" in all_headers or "🟡 [속보]" in all_headers:
            badges.append("🟡 <b>군사위협·협상 제약</b>")
        if badges and lines:
            lines.insert(1, "  |  ".join(dict.fromkeys(badges)))
    return "\n".join(lines)


prev._semantic_output_fix = semantic_fix


def verify_alert(test_mode=False):
    _orig_verify_alert(test_mode=test_mode)
    if not watch.ALERT.exists():
        return
    text = watch.ALERT.read_text(encoding="utf-8")
    low = text.lower()
    issues = []
    if "후티의 리야드 탄도미사일 공격·요격 신호" in text and "fire-smoke-seen-near-aramco" in low:
        issues.append("아람코 원인 미확정 화재를 후티 미사일 공격으로 귀속")
    if "🟢" in text and any(x in low for x in ("루코일 해외자산 매각", "석유업체 빅딜")):
        issues.append("상업거래를 휴전 진전으로 표시")
    if "🔴" in text and "정유시설 공격 확대 예고" in text:
        issues.append("미래 공격 예고를 실제 피격으로 표시")
    if "🔴" in text and "종전 조건 재확인" in text:
        issues.append("종전 조건 입장표명을 실제 확전으로 표시")
    if issues:
        raise RuntimeError("WAR_OCT04_QUALITY_GATE: " + " | ".join(issues))


runner.verify_alert = verify_alert


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()
