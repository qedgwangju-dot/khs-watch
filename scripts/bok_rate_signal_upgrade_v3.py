#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re

import bok_rate_signal_upgrade as base


def policy_flags(blob: str) -> dict[str, bool]:
    f = base.flags(blob)
    f.update({
        "hike_timing_speed": bool(re.search(r"추가\s*인상의?\s*시기와\s*속도", blob)),
        "next_meeting_hawk": bool(re.search(r"(?:10월|다음\s*회의)[^.]{0,55}(?:인상\s*필요|인상\s*가능성\s*(?:높|확대)|인상해야|인상\s*검토|인상\s*불가피)", blob)),
        "next_meeting_caution": bool(re.search(r"(?:10월|다음\s*회의)[^.]{0,70}(?:예단|단정|말하기|결정)[^.]{0,45}(?:어렵|무리|지표|데이터|확인)", blob)),
        "two_hikes_effect": bool(re.search(r"(?:두\s*차례|2차례)[^.]{0,40}금리\s*인상[^.]{0,60}(?:영향|효과)[^.]{0,40}(?:살펴|점검|확인)", blob)),
        "demand_inflation": bool(re.search(r"(?:수요\s*측|소득)[^.]{0,70}물가\s*압력", blob)),
        "middle_east_cost": bool(re.search(r"중동[^.]{0,90}(?:비용\s*압력|물가)[^.]{0,50}(?:재상승|상승|확대|영향)", blob)),
    })
    return f


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


def rhetoric(now: dt.datetime) -> list[dict]:
    queries = (
        '한국은행 김종화 "추가 인상의 시기와 속도"',
        '한국은행 박종우 "성장보다 물가" 중동',
        '한국은행 박종우 10월 금리 지표 확인',
        '한국은행 통화신용정책보고서 추가 인상 시기 속도 중동 물가',
        '한국은행 금통위원 추가 인상 근원물가 가계부채',
    )
    rows = []
    cutoff = now - dt.timedelta(days=5)
    for q in queries:
        try:
            rows += base.news(q, 30)
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
            }
        else:
            cur = merged[key]
            cur["flags"] = {k: bool(cur["flags"].get(k) or f.get(k)) for k in set(cur["flags"]) | set(f)}
            if rank < cur["rank"]:
                cur.update({"title": r["title"], "link": r["link"], "source_name": r["source_name"], "published_at_kst": r["published"].isoformat(timespec="minutes"), "rank": rank})

    out = []
    for row in merged.values():
        semantic = {"date": row["date"], "speaker": row["speaker"], "flags": {k: v for k, v in sorted(row["flags"].items()) if v}}
        row["event_hash"] = hashlib.sha256(json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        row["score"] = event_score(row["flags"])
        row.pop("rank", None)
        out.append(row)
    return sorted(out, key=lambda x: x["published_at_kst"], reverse=True)


def has_direct_next_meeting_hawk(events: list[dict]) -> bool:
    return any(e.get("flags", {}).get("next_meeting_hawk") for e in events)


def grade(score: int, inf: dict | None, hh: dict | None, oilx: dict | None, events: list[dict]) -> tuple[str, str]:
    financial = bool(hh and hh.get("mortgage_reaccelerating") and hh.get("mortgage_trn", 0) >= 4)
    core = bool(inf and inf.get("core_reaccelerating") and inf.get("core_yoy", 0) >= 3.0)
    oil_up = bool(oilx and oilx.get("change_5d_pct", 0) >= 5)
    # 빨간색은 '추가 인상 기조'만으로 켜지지 않는다. 다음 회의를 직접 겨냥한 매파 강화가 필수다.
    if has_direct_next_meeting_hawk(events) and core and oil_up and financial:
        return "🔴", "다음 회의 인상 경보"
    if score >= 5:
        return "🟠", "인상 압력 확대"
    if score >= 1 or financial or (inf and inf.get("core_yoy", 0) >= 2.5):
        return "🟡", "추가인상 살아있음"
    return "🟢", "동결 우세"


def build_message(state: dict, reasons: list[str], new_events: list[dict]) -> str:
    c = state["components"]
    inf, hh, hs, oi = c.get("inflation"), c.get("household"), c.get("housing"), c.get("oil")
    lines = [
        "🚨 <b>한국은행 추가인상 압력 확대 — 근원물가·주담대·중동 물가위험</b>",
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

    lines += ["", "<b>① 현재 숫자</b>"]
    if inf:
        prev = inf.get("prev_core_yoy")
        tail = f" / 직전 {prev:.1f}%" if isinstance(prev, (int, float)) else ""
        lines.append(f"• 소비자물가 <b>{inf['headline_yoy']:.1f}%</b> / 식료품·에너지 제외 근원 <b>{inf['core_yoy']:.1f}%{tail}</b>")
    if hh:
        lines.append(f"• 전 금융권 가계대출 <b>{hh['total_trn']:+.1f}조원</b> — 총량은 둔화")
        lines.append(f"• 주택담보대출 <b>{hh['mortgage_trn']:+.1f}조원</b> / 직전 <b>{hh['mortgage_prev_trn']:+.1f}조원</b> — <b>재가속</b>")
    if oi:
        lines.append(f"• 브렌트유 <b>${oi['brent_usd']:.2f}</b> / 최근 5거래일 <b>{oi['change_5d_pct']:+.1f}%</b>")
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
            if f.get("demand_inflation") or f.get("inflation_upside"): tags.append("수요·근원물가 압력 ↑")
            if f.get("next_meeting_caution") or f.get("oct_hike_caution"): tags.append("다음 회의 즉시 인상 확정 아님")
            if f.get("two_hikes_effect"): tags.append("7·8월 인상 효과 확인 필요")
            if f.get("rate_not_only_tool") or f.get("macroprudential_mix"): tags.append("금융안정은 정책조합 병행")
            lines.append(f"• <b>{html.escape(e['speaker'])}</b>: {html.escape(' / '.join(tags) or '정책 의미 변화')}")
            lines.append("  └ " + html.escape(e["title"][:180]))
    else:
        lines.append("• 새 정책 의미 변화 없음")

    lines += ["", "<b>③ 최종 판정</b>"]
    if state["grade_emoji"] == "🔴":
        verdict = "다음 회의를 직접 겨냥한 매파 강화까지 확인돼 인상 경보 조건 충족"
    elif state["grade_emoji"] == "🟠":
        verdict = "근원물가·주담대·유가와 추가 인상 기조가 겹쳐 인상 압력은 확대됐지만, 다음 회의 즉시 인상을 단정할 단계는 아님"
    elif state["grade_emoji"] == "🟡":
        verdict = "추가 인상 경로는 남아 있으나 복수 축 동시 악화는 아직 부족"
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
    for name, fn in (("inflation", base.inflation), ("household", base.household), ("housing", base.housing), ("oil", base.oil)):
        try: got[name] = fn()
        except Exception as exc:
            got[name] = None
            base.err(f"추가인상 위험감시 {name} 조회 실패: {type(exc).__name__}: {exc}")
    current = {name: base.safe(got[name], oc.get(name)) for name in got}

    try: events = rhetoric(now)
    except Exception as exc:
        events = []
        base.err(f"추가인상 위험감시 rhetoric 조회 실패: {type(exc).__name__}: {exc}")

    seen = list(old.get("seen_rhetoric_hashes") or [])
    seen_set = set(seen)
    new_events = [e for e in events if e["event_hash"] not in seen_set]
    if boot: new_events = []
    for e in events:
        if e["event_hash"] not in seen_set:
            seen.append(e["event_hash"]); seen_set.add(e["event_hash"])
    seen = seen[-150:]

    rhetoric_score = max(-2, min(2, sum(e.get("score", 0) for e in events[:5])))
    try: next_meeting = base.next_mpc(now)
    except Exception as exc:
        next_meeting = {"date": old.get("next_mpc_date"), "source": old.get("next_mpc_source")}
        base.err(f"다음 금통위 일정 조회 실패: {type(exc).__name__}: {exc}")

    risk_score = base.ip(current.get("inflation")) + base.hp(current.get("household")) + base.rp(current.get("housing")) + base.op(current.get("oil")) + rhetoric_score
    grade_emoji, grade_label = grade(risk_score, current.get("inflation"), current.get("household"), current.get("oil"), events)
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
        "recent_rhetoric": events[:5],
        "seen_rhetoric_hashes": seen,
    }

    reasons = []
    if not boot:
        if old.get("grade_emoji") != grade_emoji or old.get("risk_score") != risk_score:
            reasons.append(f"위험등급/점수 변화: {old.get('grade_emoji','?')} {old.get('risk_score','?')} → {grade_emoji} {risk_score}")
        if current.get("inflation") and not same(oc.get("inflation"), current["inflation"], ["period", "headline_yoy", "core_yoy"]):
            reasons.append(f"물가 갱신: CPI {current['inflation']['headline_yoy']:.1f}% / 근원 {current['inflation']['core_yoy']:.1f}%")
        if current.get("household") and not same(oc.get("household"), current["household"], ["period", "total_trn", "mortgage_trn", "mortgage_prev_trn"]):
            reasons.append(f"가계대출 갱신: 전체 {current['household']['total_trn']:+.1f}조원 / 주담대 {current['household']['mortgage_trn']:+.1f}조원")
        if current.get("housing") and not same(oc.get("housing"), current["housing"], ["period", "seoul_wow", "gangbuk_wow", "gangnam_wow", "gyeonggi_wow", "broad_diffusion"]):
            reasons.append("주택가격 확산 판정 갱신")
        if current.get("oil") and oc.get("oil") and base.op(current["oil"]) != base.op(oc["oil"]):
            reasons.append(f"브렌트유 압력구간 변화: 5거래일 {current['oil']['change_5d_pct']:+.1f}%")
        if old.get("next_mpc_date") != next_meeting.get("date") and next_meeting.get("date"):
            reasons.append(f"다음 금통위 일정 전환: {old.get('next_mpc_date') or '확인 불가'} → {next_meeting['date']}")
        if new_events:
            reasons.append(f"한은 발언 정책 의미 변화 {len(new_events)}건")

    material_change = bool(reasons or new_events)
    if material_change:
        msg = build_message(candidate, reasons, new_events)
        if base.ALERT.exists() and base.ALERT.stat().st_size:
            base.ALERT.write_text(base.ALERT.read_text(encoding="utf-8").rstrip() + "\n\n──────────\n\n" + msg + "\n", encoding="utf-8")
        else:
            base.ALERT.write_text(msg + "\n", encoding="utf-8")

    root["rate_signal_upgrade"] = candidate if (boot or material_change) else old
    base.PENDING.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with base.STATUS.open("a", encoding="utf-8") as f:
        hh = current.get("household") or {}
        f.write(
            f"\n## 추가인상 위험등급 v3\n\n"
            f"- 위험등급: {grade_emoji} {grade_label}\n"
            f"- 위험점수: {risk_score} (통계적 확률 아님)\n"
            f"- 다음 금통위: {candidate.get('next_mpc_date') or '확인 불가'}\n"
            f"- 주담대: {hh.get('mortgage_trn','확인 불가')}조원 / 재가속: {'예' if hh.get('mortgage_reaccelerating') else '아니오'}\n"
            f"- 신규 정책의미 발언: {len(new_events)}건\n"
            f"- 다음 회의 직접 매파 강화: {'예' if has_direct_next_meeting_hawk(events) else '아니오'}\n"
            f"- 실제 상태 변경: {'예' if (boot or material_change) else '아니오'}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
