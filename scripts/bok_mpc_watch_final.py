#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Any

import bok_mpc_watch_correct as current

base = current.base
_original_latest_dotplot = current.latest_dotplot_correct
_original_build_alert = current.build_alert_correct


def _statement_date(p: dict[str, Any]) -> dt.date | None:
    title = str(p.get("title") or "")
    m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", title)
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except Exception:
        return None


def latest_dotplot_final(now: dt.datetime) -> dict[str, Any] | None:
    dot = _original_latest_dotplot(now)
    if not dot:
        return None
    dot = dict(dot)
    if "AKR20260827069200002" in str(dot.get("link") or ""):
        dot["as_of_date"] = "2026-08-27"
    return dot


def _main_direction(p: dict[str, Any]) -> str:
    before = p.get("rate_from")
    after = p.get("rate_to")
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        if after > before:
            return "인상"
        if after < before:
            return "인하"
        return "동결"
    return "결정"


def build_alert_final(p: dict[str, Any], dot: dict[str, Any] | None, correction: bool) -> str:
    statement_date = _statement_date(p)
    dot_date = None
    if dot and dot.get("as_of_date"):
        try:
            dot_date = dt.date.fromisoformat(str(dot["as_of_date"]))
        except Exception:
            dot_date = None

    # 새 금통위가 열렸지만 새 점도표가 아직 공개되지 않은 기간에는,
    # 과거 점도표를 현재 금리 대비 분포로 재해석하지 않는다.
    stale_dot = bool(statement_date and dot_date and statement_date > dot_date)
    text = _original_build_alert(p, None if stale_dot else dot, correction)

    direction = _main_direction(p)
    text = text.replace("• 표결: <b>결정 찬성", f"• 표결: <b>{direction} 결정 찬성")

    if stale_dot and dot:
        counts = dot.get("counts") or {}
        dist = " / ".join(f"{k}% {counts[k]}개" for k in sorted(counts, key=float)) if counts else ""
        ref = [
            "",
            "<b>점도표 참고</b>",
            f"• 최신 공개 점도표는 <b>{dot.get('as_of_date')} 기준</b>입니다.",
        ]
        if dist:
            ref.append(f"• 당시 분포: <b>{dist}</b>")
        ref.append("• 이번 회의보다 이전 자료이므로 <b>현재 회의의 새 포워드 가이던스로 재해석하지 않습니다.</b>")
        if dot.get("link"):
            ref.append(f'• <a href="{dot["link"]}">해당 점도표 근거</a>')
        text += "\n" + "\n".join(ref)

    return text


def _canonical_doc_id(p: dict[str, Any]) -> str:
    url = str(p.get("url") or "")
    m = re.search(r"[?&]nttId=(\d+)", url)
    if m:
        return m.group(1)
    return str(p.get("title") or url)


def _semantic_statement(p: dict[str, Any]) -> dict[str, Any]:
    opinions = []
    for op in p.get("minority_opinions") or []:
        opinions.append({
            "name": op.get("name"),
            "direction": op.get("direction"),
            "target_rate": op.get("target_rate"),
        })
    opinions.sort(key=lambda x: (str(x.get("name")), str(x.get("direction")), str(x.get("target_rate"))))
    return {
        "doc_id": _canonical_doc_id(p),
        "title": p.get("title"),
        "rate_from": p.get("rate_from"),
        "rate_to": p.get("rate_to"),
        "growth_this": p.get("growth_this"),
        "growth_next": p.get("growth_next"),
        "cpi_this": p.get("cpi_this"),
        "cpi_next": p.get("cpi_next"),
        "core_this": p.get("core_this"),
        "core_next": p.get("core_next"),
        "vote_for": p.get("vote_for"),
        "minority_opinions": opinions,
        "flags": p.get("flags") or {},
    }


def _semantic_dotplot(dot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not dot:
        return None
    return {
        "as_of_date": dot.get("as_of_date"),
        "counts": {str(k): int(v) for k, v in sorted((dot.get("counts") or {}).items(), key=lambda kv: float(kv[0]))},
        "total": dot.get("total"),
    }


def _event_hash(statement: dict[str, Any], dot: dict[str, Any] | None) -> str:
    payload = {
        "statement": _semantic_statement(statement),
        "dotplot": _semantic_dotplot(dot),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _old_event_hash(old: dict[str, Any]) -> str | None:
    if old.get("event_hash"):
        return str(old["event_hash"])
    statement = old.get("statement")
    if not isinstance(statement, dict) or not statement:
        return None
    dot = old.get("dotplot") if isinstance(old.get("dotplot"), dict) else None
    try:
        return _event_hash(statement, dot)
    except Exception:
        return None


def main_final() -> int:
    for path in (base.ALERT_PATH, base.ERROR_PATH):
        path.unlink(missing_ok=True)

    now = dt.datetime.now(base.KST)
    old = base.load_state()
    errors: list[str] = []

    try:
        statement = base.latest_bok_statement()
        parsed = base.parse_statement(statement)
    except Exception as exc:
        base.ERROR_PATH.write_text(
            f"통화정책방향 조회 실패: {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        return 2

    try:
        fresh_dot = base.latest_dotplot(now)
    except Exception as exc:
        fresh_dot = None
        errors.append(f"점도표 조회 실패: {type(exc).__name__}: {exc}")

    # 점도표 일시 조회 실패를 '점도표 삭제'라는 새 이벤트로 오인하지 않는다.
    effective_dot = fresh_dot
    if effective_dot is None and isinstance(old.get("dotplot"), dict):
        effective_dot = old.get("dotplot")

    current_event_hash = _event_hash(parsed, effective_dot)
    previous_event_hash = _old_event_hash(old)
    bootstrap = not bool(old)
    meaningful_changed = bootstrap or previous_event_hash != current_event_hash

    # 진단용: 한국은행 웹페이지 전체 텍스트 해시는 메뉴/동적 영역 때문에 바뀔 수 있다.
    # 이것만 바뀐 경우에는 절대 Telegram을 보내지 않는다.
    previous_raw_hash = old.get("statement_hash")
    current_raw_hash = parsed.get("hash")
    raw_hash_changed = bool(previous_raw_hash and current_raw_hash and previous_raw_hash != current_raw_hash)
    duplicate_suppressed = bool(raw_hash_changed and not meaningful_changed)

    if meaningful_changed:
        base.ALERT_PATH.write_text(
            base.build_alert(parsed, effective_dot, False),
            encoding="utf-8",
        )

    # 의미가 그대로면 상태 파일도 매 실행마다 시간을 갱신하지 않는다.
    # 이렇게 해야 불필요한 Git 커밋과 후속 실행 잡음도 사라진다.
    if meaningful_changed or not old.get("event_hash"):
        pending = {
            "updated_at_kst": now.isoformat(timespec="seconds"),
            "event_hash": current_event_hash,
            "statement_hash": current_raw_hash,
            "statement": parsed,
            "dotplot_hash": effective_dot.get("hash") if effective_dot else old.get("dotplot_hash"),
            "dotplot": effective_dot,
        }
    else:
        pending = old

    base.PENDING_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if errors:
        base.ERROR_PATH.write_text("\n".join(errors) + "\n", encoding="utf-8")

    status = [
        "# 한국은행 금통위 감시", "",
        f"- 확인시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        f"- 최신 문서: {parsed.get('title')}",
        f"- 기준금리: {parsed.get('rate_to', '확인 불가')}",
        f"- 성장률: {parsed.get('growth_this', '확인 불가')} / {parsed.get('growth_next', '확인 불가')}",
        f"- 소비자물가: {parsed.get('cpi_this', '확인 불가')} / {parsed.get('cpi_next', '확인 불가')}",
        f"- 근원물가: {parsed.get('core_this', '확인 불가')} / {parsed.get('core_next', '확인 불가')}",
        f"- 점도표: {(effective_dot or {}).get('counts', '확인 불가')}",
        f"- 의미 기준 새 알림: {'예' if meaningful_changed else '아니오'}",
        f"- 원문 전체 텍스트 해시 변화: {'예' if raw_hash_changed else '아니오'}",
        f"- 동일 내용 중복 억제: {'예' if duplicate_suppressed else '아니오'}",
        f"- 부분 오류: {len(errors)}건",
    ]
    base.STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")
    print(base.STATUS_PATH.read_text(encoding="utf-8"))
    return 0


base.latest_dotplot = latest_dotplot_final
base.build_alert = build_alert_final

if __name__ == "__main__":
    raise SystemExit(main_final())
