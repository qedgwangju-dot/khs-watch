#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
from urllib.parse import parse_qs, urljoin, urlparse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

import bok_rate_signal_upgrade as base


MATERIAL_POLICY_FLAGS = frozenset({
    "wealth_effect_reassessment", "market_rate_independence",
    "terminal_rate_openness", "fiscal_reversibility",
    "ai_long_rate_financing", "fx_low_income_purchasing_power",
    "inflation_target_horizon",
    "potential_growth_reassessment", "secular_stagnation_reassessment",
    "tfp_innovation", "productive_investment_rates",
    "potential_working_paper_expected",
})


BOK_WORKING_PAPERS_URL = (
    "https://www.bok.or.kr/imerEng/bbs/B0000268/list.do"
    "?menuNo=600354&pageIndex=1"
)
RESEARCH_SUBJECT_RE = re.compile(
    r"잠재\s*(?:성장률|성장|산출)|총요소\s*생산성|"
    r"potential\s+(?:growth|output)|total\s+factor\s+productivity", re.I
)


def parse_bok_research_listing(page: str, source: str = BOK_WORKING_PAPERS_URL) -> list[dict]:
    """한국은행 공식 연구논문 목록의 확인된 게시물 식별자만 수집한다."""
    soup = BeautifulSoup(page, "html.parser")
    found, publications = 0, {}
    for anchor in soup.find_all("a", href=True):
        title = base.norm(anchor.get_text(" ", strip=True))
        target = urljoin(source, anchor.get("href") or "")
        url = urlparse(target)
        if url.hostname not in {"www.bok.or.kr", "bok.or.kr"}:
            continue
        if "/bbs/B0000268/view.do" not in url.path:
            continue
        doc_id = parse_qs(url.query).get("nttId", [""])[0]
        if not doc_id or not doc_id.isdigit() or not title:
            continue
        found += 1
        if RESEARCH_SUBJECT_RE.search(title):
            publications[doc_id] = {
                "id": doc_id, "title": title, "url": target,
                "source": "한국은행 연구논문 공식 목록",
            }
    if found < 2:
        raise RuntimeError("한국은행 연구논문 목록의 문서 링크 확인 불가")
    return list(publications.values())


def official_paper_transition(previous: dict | None, fetched: list[dict] | None) -> tuple[dict, list[dict]]:
    """첫 성공 조회는 과거 문서의 기준선만 잡고 알리지 않는다. 조회 실패는 기존 상태 보존."""
    if fetched is None:
        return dict(previous or {}), []
    before = previous or {}
    old_ids = set(before.get("seen_ids") or [])
    new_papers = [doc for doc in fetched if doc["id"] not in old_ids] if before.get("initialized") else []
    combined = sorted(old_ids | {doc["id"] for doc in fetched})
    return {"initialized": True, "seen_ids": combined,
            "source": BOK_WORKING_PAPERS_URL}, new_papers


def policy_flags(blob: str) -> dict[str, bool]:
    f = base.flags(blob)
    f.update({
        "potential_growth_reassessment": bool(
            re.search(r"잠재\s*(?:성장률|성장경로)|성장\s*경로", blob)
            and re.search(r"AI|인공지능|투자|혁신|변곡점|상승|제고|높|반등|재평가|새로운", blob, re.I)
        ),
        "secular_stagnation_reassessment": bool(
            re.search(r"장기\s*침체|secular\s+stagnation", blob, re.I)
            and re.search(r"흔들|재평가|탈피|전환|극복|벗어나", blob)
        ),
        "tfp_innovation": bool(
            re.search(r"총요소\s*생산성|\bTFP\b", blob, re.I)
            and re.search(r"혁신|증가|상승|높|생산성\s*제고|개선", blob)
        ),
        "productive_investment_rates": bool(
            re.search(r"투자\s*수익률|투자재원\s*확보\s*경쟁", blob)
            and re.search(r"장기\s*금리|투자|재평가|상승|자본조달", blob)
        ),
        "potential_working_paper_expected": bool(
            re.search(r"잠재\s*성장률", blob)
            and re.search(r"워킹\s*페이퍼|working\s*paper|연말|연내|추정치\s*공개", blob, re.I)
        ),
        # 주가의 소비 파급 가능성은 기준금리 인하·인상의 확정 발언이 아니다.
        "wealth_effect_reassessment": bool(
            re.search(r"주가|주식|반도체", blob)
            and re.search(r"소비|실물경제|부의\s*효과", blob)
            and re.search(r"조정|하락|위축|과거보다|커졌|확대", blob)
        ),
        "market_rate_independence": bool(
            re.search(r"시장\s*금리", blob)
            and re.search(r"따라갈\s*필요(?:는|가)?\s*없|시장\s*금리[^.!?。]{0,50}추종하지|시장\s*금리[^.!?。]{0,50}따라가지\s*않", blob)
        ),
        "terminal_rate_openness": bool(
            re.search(r"최종\s*금리|종착\s*금리", blob)
            and re.search(r"열린\s*마음|유연|확정[^.!?。]{0,15}아니", blob)
        ),
        "fiscal_reversibility": bool(
            re.search(r"재정|최고\s*가격제|일시적\s*재원", blob)
            and re.search(r"되돌리|지속\s*가능|부작용|장기화|오래\s*지속", blob)
        ),
        "ai_long_rate_financing": bool(
            re.search(r"AI|인공지능", blob, re.I)
            and re.search(r"장기\s*금리|회사채|국채|투자\s*재원", blob)
        ),
        "fx_low_income_purchasing_power": bool(
            re.search(r"원화|환율", blob)
            and re.search(r"저소득|1\s*분위", blob)
            and re.search(r"구매력", blob)
        ),
        "inflation_target_horizon": bool(
            re.search(r"내후년|2028\s*년", blob)
            and re.search(r"물가", blob)
            and re.search(r"목표|2\s*%", blob)
        ),
        "hike_timing_speed": bool(re.search(r"(?:추가\s*)?(?:기준금리\s*)?인상의?\s*시기와\s*속도", blob)),
        "k_shaped_low_income": bool(re.search(r"K\s*[-·]?\s*자형|양극화", blob, re.I) and re.search(r"저소득|취약계층", blob) and re.search(r"물가|인플레이션", blob)),
        "ai_war_inflation": bool(re.search(r"AI|인공지능", blob, re.I) and re.search(r"중동|전쟁", blob) and re.search(r"물가|인플레이션", blob)),
        "fvi_leverage": bool(re.search(r"금융취약성지수|\bFVI\b", blob, re.I) and re.search(r"레버리지|차입|46(?:\.5)?", blob)),
        "ai_investment_duration": bool(re.search(r"AI|인공지능", blob, re.I) and re.search(r"(?:3\s*[~∼\-]\s*4\s*년|3\s*~\s*4\s*년|1조\s*달러|투자\s*호황.*지속)", blob)),
        "next_meeting_hawk": bool(re.search(r"(?:10월|다음\s*회의)[^.]{0,55}(?:인상\s*필요|인상\s*가능성\s*(?:높|확대)|인상해야|인상\s*검토|인상\s*불가피)", blob)),
        "next_meeting_caution": bool(re.search(r"(?:10월|다음\s*회의)[^.]{0,70}(?:예단|단정|말하기|결정)[^.]{0,45}(?:어렵|무리|지표|데이터|확인)", blob)),
        "two_hikes_effect": bool(re.search(r"(?:두\s*차례|2차례)[^.]{0,40}금리\s*인상[^.]{0,60}(?:영향|효과)[^.]{0,40}(?:살펴|점검|확인)", blob)),
        "demand_inflation": bool(re.search(r"(?:수요\s*측|소득)[^.]{0,70}물가\s*압력", blob)),
        "middle_east_cost": bool(re.search(r"중동[^.]{0,90}(?:비용\s*압력|물가)[^.]{0,50}(?:재상승|상승|확대|영향)", blob)),
    })
    # 뉴스에 '추가 인상'이라는 배경 설명이 있다는 이유만으로
    # 총재가 당일 직접 금리 인상을 요구했다고 판정하지 않는다.
    if f.get("hike_needed"):
        f["hike_needed"] = bool(re.search(
            r"(?:기준금리|금리)[^.!?。]{0,70}(?:추가\s*인상[^.!?。]{0,25}(?:필요|불가피|검토|해야)|인상\s*필요|인상해야|인상\s*가능성\s*(?:높|확대))",
            blob,
        ))
    return f


def is_new_policy_event(new: dict, previous: dict | None) -> bool:
    """동일 인물·날짜의 기사 재인용 및 코드 재분류는 추가 발언으로 중복 알림하지 않는다."""
    if not previous:
        return True
    if str(new.get("speaker") or "") != str(previous.get("speaker") or ""):
        return True
    if str(new.get("date") or "") != str(previous.get("date") or ""):
        return True
    was = previous.get("flags") or {}
    now_flags = new.get("flags") or {}
    # 기사 재인용과 코드 재분류는 차단하되 실제 새 정책 의미는 같은 날에도 인지한다.
    return any(
        now_flags.get(key) and not was.get(key)
        for key in (MATERIAL_POLICY_FLAGS | {"next_meeting_hawk"})
    )


def event_score(f: dict[str, bool]) -> int:
    hawk = 0
    dove = 0
    if f.get("hike_timing_speed") or f.get("hike_needed"): hawk += 2
    if f.get("neutral_upper"): hawk += 1
    if f.get("inflation_upside") or f.get("demand_inflation"): hawk += 1
    if f.get("middle_east_inflation") or f.get("middle_east_cost"): hawk += 1
    if f.get("next_meeting_hawk"): hawk += 2
    if f.get("next_meeting_caution") or f.get("oct_hike_caution"): dove += 2
    if f.get("rate_not_only_tool"): dove += 1
    if f.get("macroprudential_mix"): dove += 1
    if f.get("two_hikes_effect"): dove += 1
    return max(-2, min(2, hawk - dove))


def representative_priority(flags: dict[str, bool], source_rank: int) -> tuple[int, int]:
    """같은 날 다수 발언을 합치더라도 이번에 잡힌 정책 신호를 설명하는 제목을 우선한다."""
    return (sum(bool(flags.get(k)) for k in MATERIAL_POLICY_FLAGS), -source_rank)


def rhetoric(now: dt.datetime) -> list[dict]:
    queries = (
        '신현송 한국은행 총재 K자형 양극화 AI 중동 물가',
        '신현송 한국은행 총재 금융취약성지수 46 레버리지',
        '신현송 AI 투자 호황 중동 전쟁 인플레이션 통화정책',
        '한국은행 총재 금융통화위원회 추가 인상 근원물가 가계부채',
        '한국은행 통화신용정책보고서 추가 인상 시기 속도',
        '한국은행 박종우 금리 물가 금융안정',
        '한국은행 김종화 추가 인상 시기 속도',
        '신현송 한국은행 주가 조정 부의 효과 실물경제 소비',
        '신현송 시장금리 최종금리 따라갈 필요 열린 마음',
        '신현송 재정지출 최고가격제 일시적 재원 지속가능성',
        '신현송 인공지능 투자재원 회사채 국채 장기금리',
        '신현송 원화 강세 저소득층 구매력 물가 목표 내후년',
        '신현송 잠재성장률 AI 투자 연말 워킹페이퍼 총요소생산성',
        '신현송 한국 장기침체론 흔들 성장경로 잠재성장 변곡점',
        '신현송 IMF 투자수익률 장기금리 자금조달 경쟁 총요소생산성',
    )
    rows = []
    cutoff = now - dt.timedelta(days=5)

    # 뉴스 검색은 서로 독립이므로 병렬 조회한다. 한 검색원의 지연이 전체 실행을
    # 5배로 늘리지 않도록 하되, 실패한 검색은 기존처럼 부분 오류로만 남긴다.
    with ThreadPoolExecutor(max_workers=min(7, len(queries))) as pool:
        future_map = {pool.submit(base.news, q, 30): q for q in queries}
        for fut in as_completed(future_map):
            try:
                rows += fut.result()
            except Exception as exc:
                base.err(f"한은 발언 뉴스 조회 일부 실패: {type(exc).__name__}: {exc}")

    # 같은 인사·같은 날짜의 복제기사는 하나로 합치고, 뒤에 새 정책 의미가 추가될 때만 해시가 바뀐다.
    merged: dict[tuple[str, str], dict] = {}
    for r in rows:
        if not r.get("published") or r["published"] < cutoff:
            continue
        blob = base.norm(r["title"] + " " + r["description"])
        speaker = next((s for s in base.SPEAKERS if s in blob), None)
        if not speaker:
            continue
        f = policy_flags(blob)
        if not any(f.values()):
            continue
        key = (speaker, r["published"].date().isoformat())
        rank = 0 if "한국은행" in r["source_name"] else 1 if "연합뉴스" in r["source_name"] else 2
        priority = representative_priority(f, rank)
        if key not in merged:
            merged[key] = {
                "speaker": speaker,
                "date": key[1],
                "flags": f,
                "title": r["title"],
                "link": r["link"],
                "source_name": r["source_name"],
                "published_at_kst": r["published"].isoformat(timespec="minutes"),
                "rank": rank,
                "priority": priority,
            }
        else:
            cur = merged[key]
            cur["flags"] = {k: bool(cur["flags"].get(k) or f.get(k)) for k in set(cur["flags"]) | set(f)}
            if priority > cur["priority"]:
                cur.update({"title": r["title"], "link": r["link"], "source_name": r["source_name"], "published_at_kst": r["published"].isoformat(timespec="minutes"), "rank": rank, "priority": priority})

    out = []
    for row in merged.values():
        semantic = {"date": row["date"], "speaker": row["speaker"], "flags": {k: v for k, v in sorted(row["flags"].items()) if v}}
        row["event_hash"] = hashlib.sha256(json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        row["score"] = event_score(row["flags"])
        row.pop("rank", None)
        row.pop("priority", None)
        out.append(row)
    return sorted(out, key=lambda x: x["published_at_kst"], reverse=True)


def official_statement_score(statement: dict | None) -> int:
    """뉴스 제목/인용 중복과 무관하게 공식 금통위 통방문만 정책점수로 사용."""
    if not statement or not str(statement.get("title") or "").startswith("통화정책방향"):
        return 0
    f = statement.get("flags") or {}
    if f.get("inflation_next_up") and (f.get("timing_speed") or f.get("hike_bias")):
        return 1
    return 0


def has_direct_next_meeting_hawk(events: list[dict]) -> bool:
    # 뉴스기사에 미래 인상 기대가 실렸다는 사실만으로
    # 다음 금통위 인상 경보를 확정하지 않는다.
    return any(
        e.get("flags", {}).get("next_meeting_hawk")
        and str(e.get("source_name") or "").strip() == "한국은행"
        for e in events
    )


def grade(score: int, inf: dict | None, hh: dict | None, oilx: dict | None, events: list[dict]) -> tuple[str, str]:
    financial = bool(hh and hh.get("mortgage_reaccelerating") and hh.get("mortgage_trn", 0) >= 4)
    core = bool(inf and inf.get("core_reaccelerating") and inf.get("core_yoy", 0) >= 3.0)
    oil_up = bool(oilx and oilx.get("change_5d_pct", 0) >= 5)
    # 빨간색은 '추가 인상 기조'만으로 켜지지 않는다. 다음 회의를 직접 겨냥한 매파 강화가 필수다.
    if has_direct_next_meeting_hawk(events) and core and oil_up and financial:
        return "🔴", "다음 회의 인상 경보"
    if score >= 5:
        return "🟠", "인상 압력 높음"
    if score >= 1 or financial or (inf and inf.get("core_yoy", 0) >= 2.5):
        return "🟡", "추가인상 가능성 유지"
    return "🟢", "동결 조건 우세"


def oil_alert_transition(old_oil: dict | None, new_oil: dict | None) -> str | None:
    """유가가 실제 인상압력을 새로 강화/완화할 때만 알림 사유를 만든다.
    - 급락 완충(-1) -> 중립(0)은 '새로운 유가 상방위험'이 아니므로 알림하지 않는다.
    - +5%/+10% 상방구간 진입은 알림한다.
    - 이미 상방구간에 있다가 완화되면 완화 알림을 허용한다.
    """
    if not old_oil or not new_oil:
        return None
    # 서로 다른 확정 거래일에만 상승압력 변화를 재판정한다.
    if str(new_oil.get("date") or "") <= str(old_oil.get("date") or ""):
        return None
    old_bucket = max(0, base.op(old_oil))
    new_bucket = max(0, base.op(new_oil))
    ch = new_oil.get("change_5d_pct")
    if new_bucket > old_bucket:
        return f"브렌트 선물 상승압력 강화: 최근 5거래일 {ch:+.1f}%"
    if old_bucket > 0 and new_bucket < old_bucket:
        return f"브렌트 선물 상승압력 완화: 최근 5거래일 {ch:+.1f}%"
    return None


def build_message(state: dict, reasons: list[str], new_events: list[dict], new_papers: list[dict] | None = None) -> str:
    c = state["components"]
    inf, hh, hs, oi = c.get("inflation"), c.get("household"), c.get("housing"), c.get("oil")
    lines = [
        f"🏦 <b>한국은행 추가인상 조건 업데이트 — {state['grade_emoji']} {state['grade_label']}</b>",
        "",
        f"• 현재 판정: <b>{state['grade_emoji']} {state['grade_label']}</b> / 위험점수 <b>{state['risk_score']}</b>",
        "• <b>추가 25bp 인상 경로는 살아있지만 다음 회의 즉시 인상은 아직 미확정</b>",
        "• 위험점수는 통계적 확률이 아니라 정책 조건 판정값",
    ]
    if state.get("next_mpc_date"):
        d = dt.date.fromisoformat(state["next_mpc_date"])
        lines.append(f"• 다음 금통위: <b>{d.month}월 {d.day}일</b>")

    if reasons:
        lines += ["", "<b>이번에 달라진 점</b>"] + ["• " + html.escape(x) for x in reasons[:6]]

    if new_papers:
        lines += ["", "<b>한국은행 신규 연구자료 공식 게시 확인</b>"]
        for paper in new_papers[:3]:
            lines.append(
                f'• <a href="{html.escape(paper["url"], quote=True)}">'
                f'{html.escape(paper["title"])}</a>'
            )
        lines.append("• 신규 추정치·방법론은 공식 연구 본문 확인 전에는 확정 수치로 표시하지 않습니다.")
    lines += ["", "<b>① 현재 숫자</b>"]
    if inf and not inf.get("stale"):
        prev = inf.get("prev_core_yoy")
        tail = f" / 직전 {prev:.1f}%" if isinstance(prev, (int, float)) else ""
        lines.append(f"• {inf.get('period')} 소비자물가 <b>{inf['headline_yoy']:.1f}%</b> / 식료품·에너지 제외 근원 <b>{inf['core_yoy']:.1f}%{tail}</b>")
    else:
        lines.append("• 소비자물가: 최신 공식 수치 검증 실패 / 이전값 점수 제외")
    if hh and not hh.get("stale"):
        trend = "증가폭 확대" if hh.get("mortgage_reaccelerating") else "증가폭 둔화" if hh["mortgage_trn"] < hh["mortgage_prev_trn"] else "증가폭 유지"
        lines.append(f"• {hh.get('period')} 전 금융권 가계대출 <b>{hh['total_trn']:+.1f}조원</b>")
        lines.append(f"• 주택담보대출 <b>{hh['mortgage_trn']:+.1f}조원</b> / 직전 <b>{hh['mortgage_prev_trn']:+.1f}조원</b> — <b>{trend}</b>")
    else:
        lines.append("• 가계대출: 최신 공식 수치 검증 실패 / 이전값 점수 제외")
    if oi and not oi.get("stale"):
        lines.append(f"• 브렌트 선물({html.escape(oi.get('price_type') or '시장자료')}) <b>${oi['brent_usd']:.2f}</b> / 최근 확정 5거래일 <b>{oi['change_5d_pct']:+.1f}%</b>")
    else:
        lines.append("• 브렌트 선물: 확정 일봉 확인 실패 / 이전값 점수 제외")
    if hs:
        lines.append("• 주택가격 확산: <b>" + ("확산 조건 충족" if hs.get("broad_diffusion") else "광범위 확산 조건 미충족") + "</b>")
    else:
        lines.append("• 주택가격 확산: <b>공식 자동추출 미확인 → 점수에 강제 반영하지 않음</b>")

    lines += ["", "<b>② 한은 발언 변화</b>"]
    if new_events:
        for e in new_events[:4]:
            f = e["flags"]
            tags = []
            if f.get("hike_timing_speed") or f.get("hike_needed"): tags.append("추가 인상 경로 ↑")
            if f.get("middle_east_cost") or f.get("middle_east_inflation"): tags.append("중동발 물가 압력 ↑")
            if f.get("demand_inflation") or f.get("inflation_upside") or f.get("ai_war_inflation"): tags.append("물가 압력 ↑")
            if f.get("k_shaped_low_income"): tags.append("K자형 양극화·저소득층 물가부담")
            if f.get("fvi_leverage"): tags.append("금융취약성지수·레버리지 선제관리")
            if f.get("ai_investment_duration"): tags.append("AI 투자 지속성·파급효과")
            if f.get("potential_growth_reassessment"): tags.append("AI 투자에 따른 잠재성장률 재평가 가능성")
            if f.get("secular_stagnation_reassessment"): tags.append("세계 장기침체론 재검토")
            if f.get("tfp_innovation"): tags.append("총요소생산성·혁신에 따른 구조적 성장")
            if f.get("productive_investment_rates"): tags.append("투자수익률·투자재원 경쟁과 장기금리")
            if f.get("potential_working_paper_expected"): tags.append("연말 한국은행 잠재성장률 연구자료 공개 예고(아직 확정치 아님)")
            if f.get("wealth_effect_reassessment"): tags.append("주가 조정의 소비·실물경제 파급 가능성")
            if f.get("market_rate_independence"): tags.append("시장금리와 기준금리 결정은 별개")
            if f.get("terminal_rate_openness"): tags.append("최종 기준금리 경로 미확정")
            if f.get("fiscal_reversibility"): tags.append("재정지출·가격통제 장기화 위험")
            if f.get("ai_long_rate_financing"): tags.append("AI 투자재원 경쟁·장기금리 압력")
            if f.get("fx_low_income_purchasing_power"): tags.append("원화 강세의 저소득층 구매력 개선 가능성")
            if f.get("inflation_target_horizon"): tags.append("물가 목표 수렴 시점 장기화 전망")
            if f.get("next_meeting_caution") or f.get("oct_hike_caution"): tags.append("다음 회의 즉시 인상 확정 아님")
            if f.get("two_hikes_effect"): tags.append("7·8월 인상 효과 확인 필요")
            if f.get("rate_not_only_tool") or f.get("macroprudential_mix"): tags.append("금융안정은 정책조합 병행")
            lines.append(f"• <b>{html.escape(e['speaker'])}</b>: {html.escape(' / '.join(tags) or '정책 의미 변화')}")
            lines.append("  └ " + html.escape(e["title"][:180]))
    else:
        lines.append("• 새 정책 의미 변화 없음")

    lines += ["", "<b>③ 최종 판정</b>"]
    drivers = []
    if inf and not inf.get("stale") and inf.get("core_reaccelerating") and inf.get("core_yoy", 0) >= 3.0:
        drivers.append("근원물가")
    if hh and not hh.get("stale") and hh.get("mortgage_reaccelerating") and hh.get("mortgage_trn", 0) >= 4:
        drivers.append("주택담보대출")
    if oi and not oi.get("stale") and base.op(oi) > 0:
        drivers.append("유가 상승")
    if state.get("rhetoric_score", 0) > 0:
        drivers.append("한은 물가·긴축 관련 발언")
    driver_text = "·".join(drivers) if drivers else "현재 정책조건"
    if state["grade_emoji"] == "⚪":
        verdict = "공식 최신 자료 확인 전이므로 금리인상 위험등급을 확정하지 않음"
    elif state["grade_emoji"] == "🔴":
        verdict = f"{driver_text}에 더해 다음 회의를 직접 겨냥한 매파 강화까지 확인돼 인상 경보 조건 충족"
    elif state["grade_emoji"] == "🟠":
        verdict = f"{driver_text} 때문에 인상 압력이 높은 상태지만, 다음 회의 즉시 인상을 단정할 단계는 아님"
    elif state["grade_emoji"] == "🟡":
        verdict = f"{driver_text}로 추가 인상 가능성은 남아 있으나 복수 축 동시 악화는 아직 부족"
    else:
        verdict = "물가·금융불균형 압력이 완화돼 동결 조건이 우세"
    lines.append(f"• <b>{verdict}</b>")

    links = []
    for label, x in (("소비자물가 공식자료", inf), ("가계대출 공식자료", hh), ("한국부동산원 주간자료", hs)):
        if x and x.get("source"): links.append((label, x["source"]))
    if state.get("next_mpc_source"): links.append(("한국은행 금통위 일정", state["next_mpc_source"]))
    for e in new_events[:3]:
        if e.get("link"): links.append((e["speaker"] + " 발언 근거", e["link"]))
    if links:
        lines += ["", "<b>원문·근거</b>"]
        used = set()
        for label, url in links:
            if url in used: continue
            used.add(url)
            lines.append(f'<a href="{html.escape(url, quote=True)}">• {html.escape(label)}</a>')
    return "\n".join(lines)


def same(a, b, keys): return bool(a and b and all(a.get(k) == b.get(k) for k in keys))


def main() -> int:
    base.OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(base.KST)
    root = base.root_state()
    old = root.get("rate_signal_upgrade") if isinstance(root.get("rate_signal_upgrade"), dict) else {}
    oc = old.get("components") if isinstance(old.get("components"), dict) else {}
    boot = not bool(old)

    got = {}
    component_fns = {
        "inflation": base.inflation,
        "household": base.household,
        "housing": base.housing,
        "oil": base.oil,
    }
    # 서로 독립인 현재지표 조회도 병렬화해 한 원천 지연이 전체 실행을 묶지 않게 한다.
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {pool.submit(fn): name for name, fn in component_fns.items()}
        for fut in as_completed(future_map):
            name = future_map[fut]
            try:
                got[name] = fut.result()
            except Exception as exc:
                got[name] = None
                base.err(f"추가인상 위험감시 {name} 조회 실패: {type(exc).__name__}: {exc}")
    current = {name: base.safe(got.get(name), oc.get(name)) for name in component_fns}
    # 수집에 실패한 과거값은 상태에는 남기더라도 '현재 점수'에서 제거한다.
    valid = {
        name: (record if record and not record.get("stale") else None)
        for name, record in current.items()
    }
    if not valid.get("inflation") or not valid.get("household"):
        base.err("물가 또는 가계대출의 최신 공식자료가 없어 인상 위험등급 판정 보류")

    try: events = rhetoric(now)
    except Exception as exc:
        events = []
        base.err(f"추가인상 위험감시 rhetoric 조회 실패: {type(exc).__name__}: {exc}")

    # 연말 재추정 연구논문은 뉴스 기사와 별개로 공식 게시물 식별자를 직접 확인한다.
    paper_previous = old.get("official_potential_research") if isinstance(old.get("official_potential_research"), dict) else {}
    paper_checked = False
    try:
        listing = base.get(BOK_WORKING_PAPERS_URL, timeout=22)
        fetched_papers = parse_bok_research_listing(listing.text)
        paper_checked = True
    except Exception as exc:
        fetched_papers = None
        base.err(f"한국은행 잠재성장률 공식 연구자료 목록 조회 실패: {type(exc).__name__}: {exc}")
    paper_state, new_papers = official_paper_transition(paper_previous, fetched_papers)

    seen = list(old.get("seen_rhetoric_hashes") or [])
    seen_set = set(seen)
    # 제목이나 RSS 검색결과가 바뀌어도 이미 본 정책 의미는 다시 발송하지 않는다.
    seen_by_day = {
        str(key): sorted(set(value))
        for key, value in (old.get("seen_policy_flags_by_day") or {}).items()
        if isinstance(value, list)
    }
    for previous in old.get("recent_rhetoric") or []:
        key = f"{previous.get('speaker')}|{previous.get('date')}"
        flags = {k for k, v in (previous.get("flags") or {}).items() if v}
        seen_by_day[key] = sorted(set(seen_by_day.get(key, [])) | flags)
    proposed_events = []
    for e in events:
        key = f"{e.get('speaker')}|{e.get('date')}"
        previously_seen = seen_by_day.get(key)
        prior = (
            {"speaker": e.get("speaker"), "date": e.get("date"),
             "flags": {k: True for k in previously_seen}}
            if previously_seen else None
        )
        if e["event_hash"] not in seen_set and is_new_policy_event(e, prior):
            proposed_events.append(e)
        flags = {k for k, v in (e.get("flags") or {}).items() if v}
        seen_by_day[key] = sorted(set(seen_by_day.get(key, [])) | flags)
        if e["event_hash"] not in seen_set:
            seen.append(e["event_hash"]); seen_set.add(e["event_hash"])
    seen = seen[-150:]
    cutoff = (now.date() - dt.timedelta(days=14)).isoformat()
    seen_by_day = {
        key: value for key, value in seen_by_day.items()
        if key.rsplit("|", 1)[-1] >= cutoff
    }
    # 코드 업그레이드 자체만으로 과거 뉴스 재전송 금지.
    topic_bootstrap = not bool(old.get("topic_policy_version"))
    new_events = [] if (boot or topic_bootstrap) else proposed_events
    # 새 분류는 실제 발언 당일 이후에만 재통지하며 과거 기사 재해석은 알리지 않는다.
    new_events = [
        e for e in new_events
        if e.get("date", "") >= "2026-10-23"
    ]

    # 기존 뉴스기사 순서·제목 변경으로 2→3점이 오락가락하던 문제 차단.
    # 발언은 알림 설명에 활용하고 위험점수에는 공식 통방문만 반영.
    rhetoric_score = official_statement_score(root.get("statement"))
    meeting_completed = False
    try:
        next_meeting = base.next_mpc(now)
        # 금통위 당일 새 공식 결정문이 게시된 뒤에는 오늘을 "다음 회의"로 표기하지 않는다.
        # 실제 공표 문서를 읽었을 때만 회의를 완료한 것으로 본다.
        decided_title = str((root.get("statement") or {}).get("title") or "")
        today_mark = f"{now.year}.{now.month}.{now.day}"
        meeting_completed = (
            next_meeting.get("date") == now.date().isoformat()
            and today_mark in decided_title
        )
        if meeting_completed:
            next_meeting = base.next_mpc(now + dt.timedelta(days=1))
    except Exception as exc:
        next_meeting = {"date": old.get("next_mpc_date"), "source": old.get("next_mpc_source")}
        base.err(f"다음 금통위 일정 조회 실패: {type(exc).__name__}: {exc}")

    risk_score = base.ip(valid.get("inflation")) + base.hp(valid.get("household")) + base.rp(valid.get("housing")) + base.op(valid.get("oil")) + rhetoric_score
    if not valid.get("inflation") or not valid.get("household"):
        grade_emoji, grade_label = "⚪", "최신 공식자료 부족·판정 보류"
    else:
        grade_emoji, grade_label = grade(risk_score, valid.get("inflation"), valid.get("household"), valid.get("oil"), events)
    candidate = {
        "version": 3,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "risk_score": risk_score,
        "grade_emoji": grade_emoji,
        "grade_label": grade_label,
        "next_mpc_date": next_meeting.get("date"),
        "next_mpc_source": next_meeting.get("source"),
        "components": current,
        "rhetoric_score": rhetoric_score,
        "rhetoric_score_source": "한국은행 공식 통화정책방향(뉴스 검색점수 제외)",
        "recent_rhetoric": events[:5],
        "seen_rhetoric_hashes": seen,
        "seen_policy_flags_by_day": seen_by_day,
        "topic_policy_version": 1,
        "official_potential_research": paper_state,
    }

    # 상태 계산과 텔레그램 알림 트리거를 분리한다.
    # 점수/등급이 시장가격의 완충효과 소멸만으로 바뀌어도 상태는 갱신할 수 있지만,
    # 실제 정책조건 악화가 없으면 텔레그램은 보내지 않는다.
    state_reasons = []
    alert_reasons = []
    migration = int(old.get("version") or 0) < 4

    def semantic_snapshot(items):
        return [
            (
                str(e.get("speaker") or ""), str(e.get("date") or ""),
                tuple(sorted(k for k, v in (e.get("flags") or {}).items() if v)),
            )
            for e in items
        ]

    if not boot:
        # 기사 재인용이나 코드 재분류는 알리지 않되, 잘못된 이전 분류 메타데이터는 조용히 교정한다.
        if semantic_snapshot(old.get("recent_rhetoric") or []) != semantic_snapshot(events[:5]):
            state_reasons.append("정책발언 의미분류 메타데이터 교정")
        if old.get("grade_emoji") != grade_emoji or old.get("risk_score") != risk_score:
            state_reasons.append(
                f"위험등급/점수 재계산: {old.get('grade_emoji','?')} {old.get('risk_score','?')} → "
                f"{grade_emoji} {risk_score}"
            )

        if current.get("inflation") and not same(
            oc.get("inflation"), current["inflation"], ["period", "headline_yoy", "core_yoy"]
        ):
            qualifier = "수치 정정" if oc.get("inflation") and oc["inflation"].get("period") == current["inflation"].get("period") else "신규 발표"
            reason = f"물가 공식 {qualifier}: CPI {current['inflation']['headline_yoy']:.1f}% / 근원 {current['inflation']['core_yoy']:.1f}%"
            state_reasons.append(reason)
            alert_reasons.append(reason)

        if current.get("household") and not same(
            oc.get("household"), current["household"], ["period", "total_trn", "mortgage_trn", "mortgage_prev_trn"]
        ):
            reason = (
                f"가계대출 공식치 갱신: 전체 {current['household']['total_trn']:+.1f}조원 / "
                f"주담대 {current['household']['mortgage_trn']:+.1f}조원"
            )
            state_reasons.append(reason)
            alert_reasons.append(reason)

        if current.get("housing") and not same(
            oc.get("housing"), current["housing"],
            ["period", "seoul_wow", "gangbuk_wow", "gangnam_wow", "gyeonggi_wow", "broad_diffusion"]
        ):
            reason = "주택가격 공식 확산 판정 갱신"
            state_reasons.append(reason)
            alert_reasons.append(reason)

        if current.get("oil") and oc.get("oil"):
            old_oil = oc.get("oil")
            new_oil = current.get("oil")
            # 원시 가격/날짜 변화는 상태 기록용일 뿐 텔레그램 사유가 아니다.
            if (
                old_oil.get("date") != new_oil.get("date")
                or base.op(old_oil) != base.op(new_oil)
            ):
                state_reasons.append(
                    f"브렌트 선물 상태 갱신: {old_oil.get('change_5d_pct')}% → {new_oil.get('change_5d_pct')}%"
                )
            oil_reason = oil_alert_transition(old_oil, new_oil)
            if oil_reason:
                alert_reasons.append(oil_reason)

        if old.get("next_mpc_date") != next_meeting.get("date") and next_meeting.get("date"):
            reason = f"다음 금통위 일정 전환: {old.get('next_mpc_date') or '확인 불가'} → {next_meeting['date']}"
            state_reasons.append(reason)
            # 결정을 이미 발송한 뒤 예정표가 다음 회의로 넘어가는 정상적 이동은
            # 신규 매파/비둘기 사건이 아니므로 별도 텔레그램을 보내지 않는다.
            if not meeting_completed:
                alert_reasons.append(reason)

        if new_events:
            reason = f"한은 발언 정책 의미 변화 {len(new_events)}건"
            state_reasons.append(reason)
            alert_reasons.append(reason)
        if new_papers:
            reason = f"한국은행 잠재성장률·생산성 연구자료 공식 신규 공개 {len(new_papers)}건"
            state_reasons.append(reason)
            alert_reasons.append(reason)

    # 코드 버전 변경 자체는 신규 정책 이벤트가 아니다.
    notify = bool(alert_reasons or new_events or new_papers) and not migration
    if notify:
        msg = build_message(candidate, alert_reasons, new_events, new_papers)
        if base.ALERT.exists() and base.ALERT.stat().st_size:
            base.ALERT.write_text(
                base.ALERT.read_text(encoding="utf-8").rstrip() + "\n\n──────────\n\n" + msg + "\n",
                encoding="utf-8",
            )
        else:
            base.ALERT.write_text(msg + "\n", encoding="utf-8")

    candidate["version"] = 4
    candidate["notification_policy"] = {
        "score_only_change_suppressed": True,
        "oil_relief_to_neutral_suppressed": True,
        "oil_alert_requires_positive_pressure_bucket": True,
        "official_data_or_policy_event_priority": True,
        "material_same_day_dedup_by_speaker_date": True,
        "new_topics_bootstrap_without_replay": True,
        "official_working_paper_id_dedup": True,
        "official_paper_first_scan_no_replay": True,
        "fresh_official_only_scoring": True,
        "completed_daily_oil_candles_only": True,
        "source_period_validation": True,
        "headline_independent_policy_score": True,
    }

    # 상태는 재계산 변화가 있으면 조용히 갱신한다. 알림 여부와는 분리한다.
    state_change = (
        boot or migration or topic_bootstrap or bool(state_reasons or new_events)
        or seen_by_day != (old.get("seen_policy_flags_by_day") or {})
        or paper_state != paper_previous
        or any((oc.get(key) or {}).get("stale") != (current.get(key) or {}).get("stale") for key in component_fns)
    )
    root["rate_signal_upgrade"] = candidate if state_change else old
    base.PENDING.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with base.STATUS.open("a", encoding="utf-8") as f:
        hh = current.get("household") or {}
        f.write(
            f"\n## 추가인상 위험등급 v4\n\n"
            f"- 위험등급: {grade_emoji} {grade_label}\n"
            f"- 위험점수: {risk_score} (통계적 확률 아님)\n"
            f"- 다음 금통위: {candidate.get('next_mpc_date') or '확인 불가'}\n"
            f"- 주담대: {hh.get('mortgage_trn','확인 불가')}조원 / 재가속: {'예' if hh.get('mortgage_reaccelerating') else '아니오'}\n"
            f"- 신규 정책의미 발언: {len(new_events)}건\n"
            f"- 다음 회의 직접 매파 강화: {'예' if has_direct_next_meeting_hawk(events) else '아니오'}\n"
            f"- 실제 상태 변경: {'예' if state_change else '아니오'}\n"
            f"- 텔레그램 알림 발생: {'예' if notify else '아니오'}\n"
            f"- 한국은행 잠재성장률 공식 연구자료 목록: {'확인' if paper_checked else '조회 실패'} / 신규 {len(new_papers)}건\n"
            f"- 점수만 변한 경우 알림 억제: 예\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
