#!/usr/bin/env python3
"""Best-effort, once-per-KST-day pre-open status for existing Telegram watchers.

This sends only a status derived from the current scheduled run's saved source
evidence. It never turns missing or misaligned source data into a market value.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
from decimal import Decimal
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
CONFIG = {
    "us": {
        "title": "미국 증시 자금흐름",
        "status": Path("out/us_fund_flow_status.md"),
        "evidence": None,
        "saved": Path("data/us_fund_flow_state.json"),
        "factual_pending": Path("out/us_fund_flow_pending_state.json"),
        "state": Path("data/us_fund_flow_daily_status_state.json"),
        "pending": Path("out/us_fund_flow_daily_status_pending.json"),
        "receipt": Path("out/us_fund_flow_daily_status_receipt.json"),
        "alert": Path("out/us_fund_flow_alert.html"),
    },
    "kofia": {
        "title": "국내 증시 대기자금",
        "status": Path("out/kofia_liquidity_status.md"),
        "evidence": Path("out/kofia_liquidity_source_evidence.json"),
        "saved": Path("data/kofia_liquidity_state.json"),
        "factual_pending": Path("out/kofia_liquidity_pending_state.json"),
        "state": Path("data/kofia_liquidity_daily_status_state.json"),
        "pending": Path("out/kofia_liquidity_daily_status_pending.json"),
        "receipt": Path("out/kofia_liquidity_daily_status_receipt.json"),
        "alert": Path("out/kofia_liquidity_alert.html"),
    },
}


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def _source_periods_from_us_status(text):
    periods = []
    for line in text.splitlines():
        if line.startswith("- ") and " | " in line:
            parts = line[2:].split(" | ")
            if len(parts) >= 2 and parts[1].strip() not in ("none", "unknown"):
                periods.append(f"{parts[0].strip()}: {parts[1].strip()}")
    return periods[:6]


def _source_periods_from_saved(state):
    values = (state or {}).get("values") or {}
    periods = []
    for value in values.values():
        if isinstance(value, dict) and value.get("period"):
            item = f"{value.get('source', '원천')}: {value['period']}"
            if item not in periods:
                periods.append(item)
    return periods[:6]


def _usd_billion_with_krw(value, fx):
    amount = Decimal(str(value))
    return f"{amount * 10:+,.1f}억달러 (약 {amount * fx / 1000:+,.1f}조원)"


def _us_horizon_details(status_text, saved):
    """Repeat only period values whose source period and fingerprint were rechecked."""
    fx_match = re.search(r"^- USD/KRW:\s*([\d.]+)\s*\((\d{8})\)\s*$", status_text, re.M)
    if not fx_match:
        return ["• 1M/3M 비교: 이번 조회의 원화 환산 기준을 확인하지 못해 수치 표시 보류"]
    fx = Decimal(fx_match.group(1))
    observed = {}
    for line in status_text.splitlines():
        match = re.fullmatch(r"- (ICI combined|ICI mmf|FINRA margin) \| (.+?) \| ([0-9a-f]{12})", line)
        if match:
            observed[match.group(1)] = (match.group(2), match.group(3))
    specs = (
        ("ICI|combined", "ICI combined", "ICI 국내주식형 주간 순유입 합계", "domestic_flow_horizons", "value_bn"),
        ("ICI|mmf", "ICI mmf", "ICI MMF 잔액 차이", "asset_balance_horizons", "change_bn"),
        ("FINRA|margin", "FINRA margin", "FINRA 마진부채 잔액 차이", "margin_debt_horizons", "change_bn"),
    )
    lines = [f"• 1M/3M 마지막 검증값(이번 조회에서 원천 기간·지문 재확인, 새 수치 아님; USD/KRW {fx:,.2f}, {fx_match.group(2)}):"]
    values = (saved or {}).get("values") or {}
    for key, label, title, field, amount_field in specs:
        entry = values.get(key) or {}
        current = observed.get(label)
        if not current or current != (entry.get("period"), str(entry.get("fingerprint") or "")[:12]):
            lines.append(f"• {title}: 1M/3M 확인 불가 (이번 조회와 저장 원천의 기간·지문 불일치)")
            continue
        periods = (entry.get("metrics") or {}).get(field) or {}
        rendered = []
        for horizon in ("m1", "m3"):
            item = periods.get(horizon) or {}
            value = item.get(amount_field)
            horizon_label = "1M" if horizon == "m1" else "3M"
            if value is None:
                reason = item.get("reason")
                detail = "동일 정의 주간 이력이 목표일까지 이어지지 않음" if reason == "weekly_history_does_not_cover_target_window" else "원자료 비교구간 확인 불가"
                rendered.append(f"{horizon_label} 확인 불가 ({detail})")
            else:
                rendered.append(f"{horizon_label} {_usd_billion_with_krw(value, fx)}")
        lines.append(f"• {title} ({entry['period']}): " + " / ".join(rendered))
    lines.append("• 쉽게 읽기(주식형): 순유입은 주가 상승 압력, 순유출은 하락 압력으로 작용할 수 있지만 가격 방향을 확정하지 않습니다.")
    lines.append("• 주식형은 주간 순유입 합계, MMF·마진부채는 시점 간 잔액 차이입니다. 10/14 ICI 집합투자신탁 활동 주석을 포함합니다.")
    lines.append("• MMF 잔액 변화는 주식 자금 유입·유출이나 직접 이동을 뜻하지 않습니다; 마진부채 증가는 레버리지 확대이지 상승 방향 확정이 아닙니다.")
    lines.append("• ↑/↓는 지표값의 증감 부호이지 주가 방향 표시가 아닙니다.")
    return lines


def _kofia_horizon_details(status_text, evidence, saved):
    if evidence.get("phase") != "validated" or evidence.get("changed") is not False:
        return []
    fingerprint = str(evidence.get("fingerprint") or "")
    status_fingerprint = re.search(r"^- fingerprint ([0-9a-f]{64})\s*$", status_text, re.M)
    if not status_fingerprint or fingerprint != status_fingerprint.group(1) or fingerprint != saved.get("fingerprint"):
        return ["• 1M/3M 잔액 차이: 이번 조회와 저장 원천의 지문 대조 실패로 표시 보류"]
    dates = evidence.get("latest_dates") or {}
    snapshot = saved.get("snapshot_date")
    labels = {"deposit": "투자자예탁금", "mmf": "MMF", "cma": "CMA", "credit": "신용융자"}
    result = []
    for key, label in labels.items():
        match = re.search(rf"^- {key} (\d{{8}}):.*?/ 1M ([^/\n]+) / 3M ([^/\n]+)\s*$", status_text, re.M)
        if not match or match.group(1) != snapshot or dates.get(key) != snapshot:
            return ["• 1M/3M 잔액 차이: 네 지표의 이번 조회 기준일·기간값 대조 실패로 표시 보류"]
        result.append(f"• {label} ({snapshot}): 1M {match.group(2).strip()} / 3M {match.group(3).strip()}")
    return ["• 1M/3M 마지막 공식값 재확인(새 기준일 아님, 달력월 목표일 직전 공표 잔액 대비):", *result]


def build_us_message(now, reason):
    cfg = CONFIG["us"]
    status_text = cfg["status"].read_text(encoding="utf-8") if cfg["status"].exists() else ""
    saved = read_json(cfg["saved"]) or {}
    if reason == "source_collection_failed":
        state = "자료 미갱신 · 오늘 정기 조회가 정상 완료되지 않았습니다."
        errors = [line[2:].strip() for line in status_text.splitlines() if line.startswith("- error:")]
        details = [f"• 조회 오류/미확인: {item[:240]}" for item in errors[:3]]
        details.append("• 검증되지 않은 숫자나 이전 값을 오늘 수치로 대체하지 않았습니다.")
    elif reason == "source_validation_failed":
        state = "원천 재검증 실패 · 수치 보고 보류"
        details = ["• 원자료 대조를 통과하지 못해 전체 수치 보고를 보류했습니다."]
        periods = _source_periods_from_us_status(status_text)
        if periods:
            details.append("• 조회된 원천기간: " + ", ".join(periods))
    elif reason == "telegram_delivery_unconfirmed":
        state = "전송 확인 실패 · 해당 실행의 Telegram 영수증을 확인하지 못했습니다."
        details = ["• 재전송 여부가 확인되지 않아 자동으로 다시 보내지 않았습니다."]
    elif cfg["alert"].exists():
        state = "수치 보고 전송 미확인 · 최종 발송 영수증이 없습니다."
        details = ["• 수치 보고 후보는 있었지만 Telegram 발송 확인을 완료하지 못했습니다."]
    elif not status_text:
        state = "자료 미갱신 · 오늘 정기 조회 결과가 생성되지 않았습니다."
        details = ["• 마지막 저장 원천기간(현재 조회값 아님): " + (", ".join(_source_periods_from_saved(saved)) or "확인 불가")]
    else:
        updates_match = __import__("re").search(r"^- updates:\s*(\d+)\s*$", status_text, __import__("re").M)
        parsed_match = __import__("re").search(r"^- parsed sources:\s*(\d+)\s*$", status_text, __import__("re").M)
        errors = [line[2:].strip() for line in status_text.splitlines() if line.startswith("- error:")]
        periods = _source_periods_from_us_status(status_text)
        if errors:
            state = "일부 원천 미확인 · 신규 통합 수치 보고 보류"
            details = [f"• 조회 오류/미확인: {item[:240]}" for item in errors[:3]]
        elif parsed_match and int(parsed_match.group(1)) == 0:
            state = "자료 확인 대기 · 유효 원천값 없음"
            details = ["• 이번 실행에서 검증된 원천 시계열을 확인하지 못했습니다."]
        elif updates_match and int(updates_match.group(1)) == 0:
            state = "변경 없음 · 이번 조회에서 새 공식 수치·정정·경보 전환 없음"
            details = ["• 최신 검증 원천기간: " + (", ".join(periods) or "확인 불가")]
        elif updates_match:
            state = "수치 변화 확인 · 정기 보고 생성/전송은 확인되지 않음"
            details = ["• 최신 검증 원천기간: " + (", ".join(periods) or "확인 불가")]
        else:
            state = "자료 확인 대기 · 상태 문구를 판정할 수 없음"
            details = ["• 원천 상태 산출물이 예상 형식과 달라 변경 없음으로 추정하지 않았습니다."]
    return "\n".join([
        f"🇺🇸 [{cfg['title']} | 오전 상태]",
        f"• 확인 시각: {now:%Y-%m-%d %H:%M KST}",
        f"• 판정: {state}",
        *details,
        *(_us_horizon_details(status_text, saved) if status_text and saved else []),
        "• 이 메시지는 상태 안내입니다. 실제 현금 유입·유출을 새로 입증하는 수치 보고가 아닙니다.",
    ])


def _kst_date_from_receipt(receipt):
    if not isinstance(receipt, dict):
        return None
    raw = receipt.get("timestamp_utc") or receipt.get("telegram_date_utc")
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST).date().isoformat()
    except ValueError:
        return None


def build_kofia_message(now, reason):
    cfg = CONFIG["kofia"]
    status_text = cfg["status"].read_text(encoding="utf-8") if cfg["status"].exists() else ""
    evidence = read_json(cfg["evidence"]) or {}
    saved = read_json(cfg["saved"]) or {}
    phase = evidence.get("phase", "missing")
    dates = evidence.get("latest_dates") or {}
    checked = evidence.get("finished_at_kst") or evidence.get("started_at_kst")
    if reason == "source_collection_failed":
        state = "자료 미갱신 · 오늘 공식 조회가 정상 완료되지 않았습니다."
        details = ["• 검증되지 않은 숫자나 이전 값을 오늘 조회값으로 대체하지 않았습니다."]
        if phase == "failed":
            error = str(evidence.get("error") or "오류 내용 확인 불가").splitlines()[0][:240]
            details.append(f"• 오류: {error}")
    elif reason == "source_validation_failed":
        state = "원천 재검증 실패 · 통합 수치 보고 보류"
        details = ["• 공식 원자료 대조를 통과하지 못했습니다."]
        if dates:
            details.append("• 조회된 공식 기준일: " + ", ".join(f"{key}={value}" for key, value in sorted(dates.items())))
    elif reason == "report_validation_failed":
        state = "최종 보고 검증 실패 · 수치 보고 보류"
        details = ["• 해석 또는 최종 본문 검증이 완료되지 않았습니다."]
        if dates:
            details.append("• 조회된 공식 기준일: " + ", ".join(f"{key}={value}" for key, value in sorted(dates.items())))
    elif reason == "telegram_delivery_unconfirmed":
        state = "전송 확인 실패 · 해당 실행의 Telegram 영수증을 확인하지 못했습니다."
        details = ["• 자동 재전송은 하지 않았습니다."]
    elif cfg["alert"].exists():
        state = "수치 보고 전송 미확인 · 최종 발송 영수증이 없습니다."
        details = ["• 수치 보고 후보는 있었지만 Telegram 발송 확인을 완료하지 못했습니다."]
    elif phase == "validated" and evidence.get("changed") is False and not evidence.get("narrative_correction"):
        state = "변경 없음 · 핵심 4개 지표의 공식 기준일과 수치가 기존 확인값과 같습니다."
        details = [f"• 최신 동기화 기준일: {evidence.get('snapshot_date') or dates.get('deposit') or '확인 불가'}"]
    elif phase == "alignment_pending":
        state = "기준일 불일치 · 통합 수치 보고 보류"
        details = ["• 공식 최신 기준일: " + ", ".join(f"{key}={value}" for key, value in sorted(dates.items()))]
    elif phase == "failed":
        state = "자료 미갱신 · 공식 조회/검증 실행 실패"
        error = str(evidence.get("error") or "오류 내용 확인 불가").splitlines()[0][:240]
        details = [f"• 오류: {error}"]
    elif phase == "validated":
        state = "변화 감지 · 정기 수치 보고/발송은 확인되지 않음"
        details = ["• 공식 기준일: " + ", ".join(f"{key}={value}" for key, value in sorted(dates.items()))]
    else:
        state = "자료 미갱신 · 실행 근거가 없어 변경 없음으로 판정하지 않음"
        prior_date = saved.get("snapshot_date")
        details = [f"• 마지막 저장 기준일(오늘 조회값 아님): {prior_date or '확인 불가'}"]
    return "\n".join([
        f"📊 [{cfg['title']} | 오전 상태]",
        f"• 확인 시각: {now:%Y-%m-%d %H:%M KST}",
        f"• 판정: {state}",
        *( [f"• 원자료 조회 완료: {checked}"] if checked else [] ),
        *details,
        *_kofia_horizon_details(status_text, evidence, saved),
        "• 잔액 변화는 실제 순매수·신규 자금 유입 또는 상품 간 직접 이동을 뜻하지 않습니다.",
    ])


def _validate_destination(expected, actual_chat):
    expected = str(expected).strip()
    if expected.lstrip("-").isdigit():
        if type(actual_chat.get("id")) is not int or actual_chat["id"] != int(expected):
            raise RuntimeError("Telegram acknowledged a different chat id")
    elif expected.startswith("@"):
        if str(actual_chat.get("username") or "").lower() != expected[1:].lower():
            raise RuntimeError("Telegram acknowledged a different channel")
    else:
        raise RuntimeError("Unsupported Telegram recipient format")


def _telegram_json(url, data=None, timeout=30):
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError("Telegram returned a non-object response")
    return result


def in_workflow_run_window(now, family):
    minute_of_day = now.hour * 60 + now.minute
    start = 7 * 60
    return start <= minute_of_day < 8 * 60


def send_message(topic, cfg, message, now):
    day = now.date().isoformat()
    prior = read_json(cfg["state"])
    if prior is not None:
        if not isinstance(prior, dict):
            raise RuntimeError("Daily status state is not an object; refusing duplicate-prone send")
        if prior.get("date_kst") == day and prior.get("message_id"):
            print(f"preopen_daily_status_suppressed=true topic={topic} date_kst={day} reason=already_sent_today")
            return
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not token or not chat_id or not expected:
        raise RuntimeError("Telegram route secrets or expected bot are missing")
    identity = _telegram_json(f"https://api.telegram.org/bot{token}/getMe")
    actual = str((identity.get("result") or {}).get("username") or "")
    if identity.get("ok") is not True or actual.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    result = _telegram_json(f"https://api.telegram.org/bot{token}/sendMessage", payload)
    item = result.get("result") or {}
    message_id = item.get("message_id")
    if result.get("ok") is not True or type(message_id) is not int or message_id <= 0:
        raise RuntimeError("Telegram response lacks an acknowledged message id")
    if str((item.get("from") or {}).get("username") or "").lower() != actual.lower():
        raise RuntimeError("Telegram acknowledgement sender differs from the verified bot")
    _validate_destination(chat_id, item.get("chat") or {})
    if item.get("text") != message:
        raise RuntimeError("Telegram acknowledgement text differs from the submitted status")
    telegram_date = item.get("date")
    if type(telegram_date) is not int or telegram_date <= 0:
        raise RuntimeError("Telegram acknowledgement lacks server timestamp")
    receipt = {
        "topic": topic,
        "date_kst": day,
        "at_kst": now.isoformat(timespec="seconds"),
        "bot_username": actual,
        "message_id": message_id,
        "telegram_date_utc": dt.datetime.fromtimestamp(telegram_date, dt.timezone.utc).isoformat(),
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "run_id": os.getenv("GITHUB_RUN_ID"),
        "code_sha": os.getenv("GITHUB_SHA"),
        "status": message.splitlines()[2] if len(message.splitlines()) > 2 else None,
    }
    cfg["receipt"].parent.mkdir(parents=True, exist_ok=True)
    cfg["receipt"].write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cfg["pending"].write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"preopen_daily_status_sent=true topic={topic} date_kst={day} bot=@{actual} message_id={message_id}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=sorted(CONFIG), required=True)
    args = parser.parse_args()
    now = dt.datetime.now(KST).replace(microsecond=0)
    cfg = CONFIG[args.family]
    reason = os.getenv("PREOPEN_STATUS_REASON", "scheduled_check")
    if os.getenv("GITHUB_EVENT_NAME") == "workflow_run":
        if not in_workflow_run_window(now, args.family):
            print(f"preopen_daily_status_suppressed=true topic={args.family} at_kst={now:%H:%M} reason=outside_final_morning_window")
            return
    cfg["pending"].parent.mkdir(parents=True, exist_ok=True)
    cfg["receipt"].parent.mkdir(parents=True, exist_ok=True)
    for path in (cfg["pending"], cfg["receipt"]):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    factual_pending = read_json(cfg["factual_pending"]) or {}
    factual_saved = read_json(cfg["saved"]) or {}
    factual_receipt = (
        factual_pending.get("delivery_receipt")
        if args.family == "kofia"
        else factual_pending.get("factual_delivery_receipt")
    )
    if not factual_receipt:
        factual_receipt = factual_saved.get(
            "delivery_receipt" if args.family == "kofia" else "factual_delivery_receipt"
        )
    if _kst_date_from_receipt(factual_receipt) == now.date().isoformat():
        print(f"preopen_daily_status_suppressed=true topic={args.family} date_kst={now.date().isoformat()} reason=factual_report_already_delivered_today")
        return
    if args.family == "kofia":
        message = build_kofia_message(now, reason)
    else:
        message = build_us_message(now, reason)
    if len(message) > 3500:
        raise RuntimeError(f"Daily status exceeds Telegram-safe length: {len(message)}")
    send_message(args.family, cfg, message, now)


if __name__ == "__main__":
    main()
