#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

from currency_krw_guard import validate_text as validate_currency_krw_text

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "khs_us_investment_alert.html"
DELIVERY = ROOT / "out" / "khs_us_investment_delivery.json"
STATE = ROOT / "data" / "khs_us_investment_seen.json"


def _api_json(url: str, *, data: bytes | None = None, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram HTTP {exc.code}: {body}") from exc


def _resolve() -> tuple[str, dict]:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not token:
        raise RuntimeError("KHS887900_BOT_TOKEN secret is missing")

    identity = _api_json(f"https://api.telegram.org/bot{token}/getMe")
    username = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or username.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{username or 'unknown'}")

    def get_chat(chat_id: str) -> dict | None:
        if not chat_id:
            return None
        query = urllib.parse.urlencode({"chat_id": chat_id})
        try:
            result = _api_json(f"https://api.telegram.org/bot{token}/getChat?{query}")
            return result.get("result") if result.get("ok") else None
        except Exception:
            return None

    chat_id = (os.getenv("TELEGRAM_CHAT_ID_DIRECT") or "").strip()
    if not chat_id:
        raise RuntimeError("Configured Telegram chat route secret is missing")
    chat = get_chat(chat_id)
    if not chat or chat.get("id") is None:
        raise RuntimeError(f"@{expected} valid but configured Telegram chat route is unreachable")
    return username, chat


def _visible_len(text: str) -> int:
    plain = re.sub(r"<[^>]+>", "", text)
    plain = plain.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return len(plain)


def _split_html(text: str, limit: int = 3300) -> list[str]:
    lines = text.splitlines()
    chunks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            chunks.append("\n".join(current).strip())
            current.clear()

    for line in lines:
        candidate = "\n".join(current + [line]).strip()
        if current and _visible_len(candidate) > limit:
            flush()
        if _visible_len(line) > limit:
            raise RuntimeError(f"single Telegram line exceeds safe limit: {_visible_len(line)}")
        current.append(line)
    flush()

    if not chunks:
        return []
    if len(chunks) == 1:
        return chunks

    rendered: list[str] = []
    total = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        prefix = f"<b>대미투자 알림 {i}/{total}</b>\n" if i > 1 else ""
        rendered.append(prefix + chunk)
    return rendered


def resolve_mode() -> int:
    output = os.getenv("GITHUB_OUTPUT")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    try:
        username, chat = _resolve()
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write("ready=true\n")
                f.write("reason=ok\n")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write(f"Telegram 경로 확인: @{username}\n")
        print(f"telegram_route_valid=true bot=@{username} chat_type={chat.get('type', 'unknown')}")
        return 0
    except Exception as exc:
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write("ready=false\n")
                f.write(f"reason={type(exc).__name__}\n")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write(f"Telegram 경로 대기: {exc}\n")
        print(f"telegram_route_valid=false reason={exc}")
        return 0


def _event_facts(family: str) -> set[str]:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"US investment state unavailable: {exc}") from exc
    return {
        str(x)
        for x in (((state.get("event_states") or {}).get(family) or {}).get("facts") or [])
    }


def _validate_alert_contract(text: str) -> None:
    plain = re.sub(r"<[^>]+>", "", text)
    plain = plain.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    nuclear_facts = _event_facts("nuclear_build")
    stake_facts = _event_facts("westinghouse_stake")

    legacy_signature = (
        "대미투자 | 내용 변화" in plain
        and "자동 용량 계산" in plain
        and "AP1000" in plain
        and "APR1400" in plain
    )
    if legacy_signature:
        raise RuntimeError("Blocked legacy article-led US-investment alert format")

    project_power_context = any(
        token in plain.lower()
        for token in ("project power", "ap1000", "apr1400", "한미 원전", "미국 원전")
    )
    if project_power_context and (
        re.search(r"(?:1\s*,\s*300|1300)\s*억\s*달러", plain)
        or re.search(r"\$?\s*130\s*billion", plain, re.I)
    ):
        raise RuntimeError(
            "Blocked unsupported Project Power 130B total: 120B framework cap and 10B conditional upfront are not additive"
        )

    if project_power_context and re.search(
        r"총사업(?:비|규모)[^\n]{0,80}(?:1\s*,\s*200|1200)\s*억\s*달러",
        plain,
    ):
        raise RuntimeError(
            "Blocked Project Power framework cap mislabeled as total project cost"
        )

    site_claimed_done = bool(
        re.search(
            r"(?:1단계\s*)?AP1000[^\n]{0,80}부지[^\n]{0,40}(?:선정|확정)[^\n]{0,20}(?:완료|확정)",
            plain,
            re.I,
        )
        or re.search(
            r"부지\s*(?:선정|확정)\s*:\s*(?:완료|확정)",
            plain,
            re.I,
        )
    )
    if (
        project_power_context
        and site_claimed_done
        and "nuclear_federal_site_status:selected" not in nuclear_facts
    ):
        raise RuntimeError("Blocked Project Power site completion before specific-site selection is in verified state")

    if (
        project_power_context
        and re.search(r"(?:공식\s*)?프레임워크\s*:\s*완료", plain, re.I)
        and "nuclear_framework_signature_status:signed" not in nuclear_facts
    ):
        raise RuntimeError("Blocked Project Power framework completion before verified signature")

    if (
        project_power_context
        and re.search(r"(?:최종\s*서명|최종\s*계약|본계약)\s*:\s*(?:완료|체결|확정)", plain, re.I)
        and "nuclear_definitive_agreement_status:signed" not in nuclear_facts
    ):
        raise RuntimeError("Blocked Project Power definitive-agreement completion before verified state")

    if (
        project_power_context
        and re.search(r"(?:예외\s*적용|타협협정[^\n]{0,30}예외)[^\n]{0,20}(?:완료|체결|확정)", plain, re.I)
        and "nuclear_settlement_waiver_status:executed" not in nuclear_facts
    ):
        raise RuntimeError("Blocked Project Power settlement-waiver completion before verified state")

    if (
        project_power_context
        and re.search(r"(?:EPC|설계.?조달.?시공)[^\n]{0,30}(?:본계약|계약)?[^\n]{0,20}(?:완료|체결|확정)", plain, re.I)
        and "nuclear_phase1_epc_status:signed" not in nuclear_facts
    ):
        raise RuntimeError("Blocked Project Power EPC completion before verified state")

    upfront_executed_claim = bool(
        re.search(
            r"선지급[^\n]{0,100}(?:실제\s*)?(?:지급|송금|집행)[^\n]{0,20}(?:완료|확정|했다|됨)",
            plain,
        )
    )
    if (
        project_power_context
        and upfront_executed_claim
        and "nuclear_upfront_payment_status:executed" not in nuclear_facts
    ):
        raise RuntimeError("Blocked Project Power upfront-payment execution before verified state")

    if (
        ("Westinghouse" in plain or "웨스팅하우스" in plain)
        and re.search(r"지분(?:투자|인수)?[^\n]{0,40}(?:거래)?종결[^\n]{0,15}(?:완료|확정)", plain, re.I)
        and "equity_closing_status:completed" not in stake_facts
    ):
        raise RuntimeError("Blocked Westinghouse equity closing before verified state")

    if "미국 대형원전 3트랙 웹감시" in plain:
        raise RuntimeError("Blocked legacy three-track nuclear recap alert format")

    if re.search(r"미분류\s*-\d+\s*기", plain):
        raise RuntimeError("Blocked impossible negative unclassified reactor count")

    total8 = bool(re.search(r"(?:전체|총)\s*8\s*기|원전\s*(?:최대\s*)?8\s*기", plain))
    ap8 = bool(re.search(r"AP1000[^\\n]{0,80}\b8\s*기", plain, re.I))
    apr8 = bool(re.search(r"APR1400[^\\n]{0,80}\b8\s*기", plain, re.I))
    if total8 and ap8 and apr8:
        raise RuntimeError("Blocked reactor composition double count: total 8 but AP1000 8 + APR1400 8")

    if re.search(r"APR1400[^\\n]{0,80}2\s*기\s*(?:→|->|에서)\s*8\s*기", plain, re.I):
        raise RuntimeError("Blocked unsupported APR1400 2-to-8 state transition")

    if re.search(r"에너지\s*패키지[^\n]{0,80}540\s*억\s*달러", plain):
        raise RuntimeError("Blocked Alaska 54B leakage into energy-package amount")

    if re.search(r"알래스카\s*LNG\s*보도수치\s*2[, ]?000\s*억\s*달러", plain, re.I):
        raise RuntimeError("Blocked overall 200B leakage into Alaska amount")

    if "9월 30일 발표 대기 상태" in plain:
        raise RuntimeError("Blocked stale pre-announcement Alaska status")

    if "알래스카 LNG" in plain and "검토 착수" not in plain and "Project North" not in plain:
        raise RuntimeError("Alaska alert missing official Project North review-stage baseline")

    if (
        ("24억달러" in plain or "24억 달러" in plain)
        and any(x in plain for x in ["첫 송금", "첫 자금 집행", "첫 투자금"])
        and "실제 송금일·금액 확정으로는 아직 승격하지 않음" in plain
    ):
        raise RuntimeError("Blocked stale funding judgment after completed 24B transfer")

    if re.search(r"원전\s*(?:최대\s*)?8\s*기", plain) and "프레임워크" not in plain:
        raise RuntimeError("Nuclear 8-unit alert missing framework qualification")

    # Final delivery gate: every foreign-currency amount must have the
    # KRW conversion immediately after it in parentheses.
    validate_currency_krw_text(plain)


def self_test_mode() -> int:
    semantic_bad_cases = [
        (
            "대미투자 | 내용 변화\n자동 용량 계산\nAP1000 6기 APR1400 2기",
            "legacy article-led",
        ),
        (
            "Project Power 총사업규모 1,300억달러(약 174조원) · AP1000 6기 + APR1400 2기",
            "130B total",
        ),
        (
            "Project Power · AP1000 1단계 부지 선정: 완료",
            "site completion",
        ),
        (
            "Project Power · 공식 프레임워크: 완료",
            "framework completion",
        ),
        (
            "Project Power · 최종 서명: 완료",
            "definitive-agreement completion",
        ),
        (
            "Project Power · 2025 타협협정 예외 적용 완료",
            "settlement-waiver completion",
        ),
        (
            "Project Power · AP1000 2기 EPC 본계약 체결 완료",
            "EPC completion",
        ),
        (
            "Project Power · 장주기 기자재 선지급 실제 집행 완료",
            "upfront-payment execution",
        ),
        (
            "Westinghouse 지분투자 거래종결: 완료",
            "equity closing",
        ),
        (
            "대미투자 송금·45영업일\n"
            "첫 자금 집행 24억달러(약 3조원)\n"
            "판정: 협의 진전 신호. 실제 송금일·금액 확정으로는 아직 승격하지 않음.",
            "stale funding judgment",
        ),
    ]

    for bad, label in semantic_bad_cases:
        try:
            _validate_alert_contract(bad)
        except RuntimeError:
            pass
        else:
            raise RuntimeError(f"semantic contract failed to block {label}: {bad}")

    good = (
        "한미 공동 팩트시트 확인\n"
        "Project Power 원전 8기 프레임워크 합의 · AP1000 6기 + APR1400 2기\n"
        "프레임워크 최종 서명: 대기 · 개별 부지 선정: 대기 · AP1000 2기 EPC 본계약: 대기\n"
        "장주기 기자재 선지급 검토 상한 100억달러(약 13조원) · 실제 집행과 구분\n"
        "Westinghouse 지분 5~10% · 거래종결 전\n"
        "첫 송금 24억달러(약 3조원) 송금 완료 · 후속 자금요청 추적"
    )
    _validate_alert_contract(good)
    print("telegram_alert_contract_self_test=passed project_power_fail_closed=true")
    return 0

def send_mode() -> int:
    if not ALERT.exists() or not ALERT.read_text(encoding="utf-8").strip():
        print("telegram_alert=none")
        return 0

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    username, chat = _resolve()
    text = ALERT.read_text(encoding="utf-8").strip()
    _validate_alert_contract(text)
    print("telegram_alert_semantic_contract=passed")
    chunks = _split_html(text)
    message_ids: list[int] = []

    for chunk in chunks:
        payload = urllib.parse.urlencode({
            "chat_id": str(chat["id"]),
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        result = _api_json(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, timeout=30)
        if not result.get("ok"):
            raise RuntimeError(f"Telegram rejected message: {result}")
        message_ids.append(int((result.get("result") or {}).get("message_id") or 0))

    DELIVERY.parent.mkdir(parents=True, exist_ok=True)
    DELIVERY.write_text(
        json.dumps({
            "bot": username,
            "message_ids": message_ids,
            "chat_type": chat.get("type"),
            "chunks": len(chunks),
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"telegram_delivery_confirmed=true bot=@{username} chunks={len(chunks)} message_ids={message_ids}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["resolve", "send", "self-test"])
    args = parser.parse_args()
    if args.mode == "resolve":
        return resolve_mode()
    if args.mode == "self-test":
        return self_test_mode()
    return send_mode()


if __name__ == "__main__":
    raise SystemExit(main())
