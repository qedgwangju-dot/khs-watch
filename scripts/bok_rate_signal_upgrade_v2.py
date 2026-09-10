#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json

import bok_rate_signal_upgrade as v1


def main() -> int:
    v1.OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(v1.KST)
    root = v1.root_state()
    old = root.get("rate_signal_upgrade") if isinstance(root.get("rate_signal_upgrade"), dict) else {}
    oc = old.get("components") if isinstance(old.get("components"), dict) else {}
    boot = not bool(old)

    got = {}
    for name, fn in (("inflation", v1.inflation), ("household", v1.household), ("housing", v1.housing), ("oil", v1.oil)):
        try:
            got[name] = fn()
        except Exception as exc:
            got[name] = None
            v1.err(f"추가인상 위험감시 {name} 조회 실패: {type(exc).__name__}: {exc}")
    current = {name: v1.safe(got[name], oc.get(name)) for name in got}

    try:
        rhetoric = v1.rhetoric(now)
    except Exception as exc:
        rhetoric = []
        v1.err(f"추가인상 위험감시 rhetoric 조회 실패: {type(exc).__name__}: {exc}")

    seen = list(old.get("seen_rhetoric_hashes") or [])
    seen_set = set(seen)
    new_rhetoric = [event for event in rhetoric if event["event_hash"] not in seen_set]
    if boot:
        new_rhetoric = []
    for event in rhetoric:
        if event["event_hash"] not in seen_set:
            seen.append(event["event_hash"])
            seen_set.add(event["event_hash"])
    seen = seen[-150:]

    rhetoric_score = max(-2, min(2, sum(event.get("score", 0) for event in rhetoric[:5])))
    try:
        next_meeting = v1.next_mpc(now)
    except Exception as exc:
        next_meeting = {"date": old.get("next_mpc_date"), "source": old.get("next_mpc_source")}
        v1.err(f"다음 금통위 일정 조회 실패: {type(exc).__name__}: {exc}")

    risk_score = (
        v1.ip(current.get("inflation"))
        + v1.hp(current.get("household"))
        + v1.rp(current.get("housing"))
        + v1.op(current.get("oil"))
        + rhetoric_score
    )
    grade_emoji, grade_label = v1.grade(
        risk_score,
        current.get("inflation"),
        current.get("household"),
        current.get("oil"),
        rhetoric_score,
    )

    candidate = {
        "version": 2,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "risk_score": risk_score,
        "grade_emoji": grade_emoji,
        "grade_label": grade_label,
        "next_mpc_date": next_meeting.get("date"),
        "next_mpc_source": next_meeting.get("source"),
        "components": current,
        "rhetoric_score": rhetoric_score,
        "recent_rhetoric": rhetoric[:5],
        "seen_rhetoric_hashes": seen,
    }

    reasons: list[str] = []
    if not boot:
        if old.get("grade_emoji") != grade_emoji or old.get("risk_score") != risk_score:
            reasons.append(
                f"위험등급/점수 변화: {old.get('grade_emoji','?')} {old.get('grade_label','')} "
                f"{old.get('risk_score','?')} → {grade_emoji} {grade_label} {risk_score}"
            )
        if current.get("inflation") and not v1.same(
            oc.get("inflation"), current["inflation"], ["period", "headline_yoy", "core_yoy"]
        ):
            reasons.append(
                f"물가 갱신: CPI {current['inflation']['headline_yoy']:.1f}% / "
                f"근원 {current['inflation']['core_yoy']:.1f}%"
            )
        if current.get("household") and not v1.same(
            oc.get("household"), current["household"], ["period", "total_trn", "mortgage_trn", "mortgage_prev_trn"]
        ):
            reasons.append(
                f"가계대출 갱신: 전체 {current['household']['total_trn']:+.1f}조원 / "
                f"주담대 {current['household']['mortgage_trn']:+.1f}조원"
            )
        if current.get("housing") and not v1.same(
            oc.get("housing"), current["housing"],
            ["period", "seoul_wow", "gangbuk_wow", "gangnam_wow", "gyeonggi_wow", "broad_diffusion"]
        ):
            reasons.append("주택가격 확산 판정 갱신")
        if current.get("oil") and oc.get("oil") and v1.op(current["oil"]) != v1.op(oc["oil"]):
            reasons.append(f"브렌트유 압력구간 변화: 5거래일 {current['oil']['change_5d_pct']:+.1f}%")
        if old.get("next_mpc_date") != next_meeting.get("date") and next_meeting.get("date"):
            reasons.append(f"다음 금통위 일정 전환: {old.get('next_mpc_date') or '확인 불가'} → {next_meeting['date']}")
        if new_rhetoric:
            reasons.append(f"한은 발언 정책 의미 변화 {len(new_rhetoric)}건")

    material_change = bool(reasons or new_rhetoric)
    if material_change:
        msg = v1.message(candidate, reasons, new_rhetoric)
        if v1.ALERT.exists() and v1.ALERT.stat().st_size:
            v1.ALERT.write_text(
                v1.ALERT.read_text(encoding="utf-8").rstrip() + "\n\n──────────\n\n" + msg + "\n",
                encoding="utf-8",
            )
        else:
            v1.ALERT.write_text(msg + "\n", encoding="utf-8")

    # 최초 도입 때는 현재 상태를 기준선으로 저장하되 알림은 보내지 않는다.
    # 이후에는 실제 정책 의미/핵심 수치가 바뀌지 않으면 기존 상태를 그대로 유지해
    # 매시간 조회시각만 바뀌는 불필요한 Git 상태 커밋을 만들지 않는다.
    if boot or material_change:
        stored = candidate
    else:
        stored = old

    root["rate_signal_upgrade"] = stored
    v1.PENDING.write_text(json.dumps(root, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with v1.STATUS.open("a", encoding="utf-8") as f:
        hh = current.get("household") or {}
        f.write(
            f"\n## 추가인상 위험등급\n\n"
            f"- 위험등급: {grade_emoji} {grade_label}\n"
            f"- 위험점수: {risk_score} (통계적 확률 아님)\n"
            f"- 다음 금통위: {candidate.get('next_mpc_date') or '확인 불가'}\n"
            f"- 주담대: {hh.get('mortgage_trn','확인 불가')}조원 / 재가속: "
            f"{'예' if hh.get('mortgage_reaccelerating') else '아니오'}\n"
            f"- 새 한은 발언 의미변화: {len(new_rhetoric)}건\n"
            f"- 실제 상태 변경: {'예' if (boot or material_change) else '아니오'}\n"
            f"- 최초 기준선 설정: {'예(알림 미송출)' if boot else '아니오'}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
