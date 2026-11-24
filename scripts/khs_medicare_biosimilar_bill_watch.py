#!/usr/bin/env python3
"""One-owner S.5797 Medicare Part B biosimilar bill watch in existing KHS policy workflow.

Uses Senate official press and the U.S. GPO's Congress bill-status XML, with
event-level keys and a remote uncertain reservation BEFORE any Telegram POST.
Neither other watchers nor their delivery/seen states are imported or changed.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text
from khs_policy_telegram_delivery import validate_telegram_send_receipt

KST = ZoneInfo("Asia/Seoul")
UA = "KHS-MedicareBiosimilar-Policy/1.0 (GitHub Actions)"
STATE_PATH = "data/khs_medicare_partb_biosimilar_state.json"
OFFICIAL_SENATE = (
    "https://www.bennet.senate.gov/2026/11/20/"
    "bennet-cornyn-introduce-legislation-to-lower-prescription-drug-costs-and-increase-access-to-biosimilars/"
)
OFFICIAL_STATUS = "https://www.govinfo.gov/bulkdata/BILLSTATUS/119/s/BILLSTATUS-119s5797.xml"
BILL_PAGE = "https://www.congress.gov/bill/119th-congress/senate-bill/5797"
SECONDARY_STATUS = "https://regs.datadawn.org/openregs/legislation/119-s-5797"
BILL_ID = "S.5797"
INIT_KEY = "congress119|S5797|introduced|2026-11-19"
BOT_EXPECTED = "khs88798879_bot"


def normalized(raw: str) -> str:
    raw = re.sub(r"(?is)<(?:script|style|noscript)\b[^>]*>.*?</(?:script|style|noscript)>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", raw))).strip().lower()


def senate_release_verified(raw: str) -> bool:
    t = normalized(raw)
    return all(x in t for x in (
        "increasing access to biosimilars act", "michael bennet",
        "john cornyn", "medicare part b", "shared savings",
        "biosimilar",
    )) and ("prescription drug costs" in t or "lower-cost" in t)


def _local_tag(tag: str) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _first_text(parent: ET.Element, label: str) -> str:
    for node in parent.iter():
        if _local_tag(node.tag) == label and node.text:
            return node.text.strip()
    return ""


def read_bill_actions(raw: str) -> list[dict]:
    root = ET.fromstring(raw)
    bill = next((n for n in root.iter() if _local_tag(n.tag) == "bill"), None)
    if bill is None:
        raise ValueError("Missing official bill node")
    # Strict ID + unique subject; never mistake a different biosimilar bill.
    if _first_text(bill, "number") != "5797" or _first_text(bill, "congress") != "119":
        raise ValueError("Official bill number/congress mismatch")
    title = _first_text(bill, "title").lower()
    if "biosimilar" not in title:
        raise ValueError("Official bill subject mismatch")
    events = []
    for actions in bill.iter():
        if _local_tag(actions.tag) != "actions":
            continue
        for node in actions:
            if _local_tag(node.tag) != "item":
                continue
            when = _first_text(node, "actionDate")
            description = _first_text(node, "text")
            if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", when) or not description:
                continue
            events.append({"date": when, "text": description})
    if not events:
        raise ValueError("Official bill actions missing")
    return events


def classify_material_stage(action: dict) -> str:
    t = " ".join(str(action.get("text") or "").lower().split())
    # New event stages only. Generic referrals and old 2024 act language do
    # not become enacted law, and cosponsor noise is not a decision.
    if "became public law" in t or ("signed by president" in t):
        return "enacted"
    if re.search(r"\bpassed house\b|\bhouse passed\b|\bagreed to in house\b", t):
        return "passed_house"
    if re.search(r"\bpassed senate\b|\bsenate passed\b|\bagreed to in senate\b", t):
        return "passed_senate"
    if ("committee on finance" in t or "committee" in t) and any(
        word in t for word in ("ordered to be reported", "reported by", "reported with")
    ):
        return "committee_reported"
    return ""


def stage_message(stage: str, item: dict) -> str:
    titles = {
        "committee_reported": "상원 재무위원회 보고 단계",
        "passed_senate": "상원 통과",
        "passed_house": "하원 통과",
        "enacted": "법률 제정",
    }
    label = titles[stage]
    action = str(item["text"]).replace("\n", " ").strip()
    return (
        "[미국 의료정책 감시] 메디케어 Part B 바이오시밀러 법안 후속\n\n"
        "■ 법안: Increasing Access to Biosimilars Act, S.5797(119대 의회).\n"
        "■ 이전: 2026년 11월 19일 발의·상원 재무위원회 회부.\n"
        f"■ 신규: {item['date']} 미국 현지 의회 기록 기준 {label}.\n"
        f"■ 공식 조치: {action}\n"
        "■ 의미: 실제 의료기관 추가 지급·보험재정 절감과 제약사 매출은 "
        "향후 집행 설계·시범사업 개시·채택에 달려 있습니다.\n"
        "■ 주의: 의회 단계와 시범사업 실행·실제 지급을 동일시하지 않습니다.\n"
        "■ 미국 의회 공식 기록: " + OFFICIAL_STATUS + "\n"
        "■ 법안 조회: " + BILL_PAGE
    )


def introduced_message(*, status_verified: bool) -> str:
    status = ("연방 정부 법안 상태 XML과 상원 발표를 대조함"
              if status_verified else "상원의원 공식 발표 확인, 의회 상태 XML 직접 조회 제한")
    return (
        "[미국 의료정책 감시] 바이오시밀러 사용 장려법 S.5797 — 발의, 미시행\n\n"
        "■ 최초 사건: 2026년 11월 19일(미국 현지) "
        "민주당 마이클 베넷·공화당 존 코닌의 초당적 메디케어 Part B 법안 발의 및 상원 재무위원회 회부.\n"
        "■ 공식 발표: 2026년 11월 20일 베넷 상원의원 보도자료. "
        "사건 발생일과 발표일이 다릅니다.\n"
        "■ 핵심: 저렴한 바이오시밀러 사용으로 절감한 지출에 연동해 "
        "의료기관에 추가 보상하고, 절감액 일부를 환자 본인부담금 완화에 쓸 수 있도록 제안.\n"
        "■ 기존 제도: 메디케어 Part B는 일반적으로 약제 평균판매가격에 "
        "연동한 지급액과 환자 본인부담이 있어 고가 약제 선호 유인이 생길 수 있습니다.\n"
        "■ 단계: 발의·위원회 회부만 확인. 통과·시행·약가 인하·"
        "한국 업체의 실제 미국 매출 증가는 아직 확정되지 않았습니다.\n"
        "■ 향후 관문: 상원 위원회 심사 → 상·하원 통과 → 법률 제정 → "
        "보건복지부 시범사업 설계·시행 → 실제 사용량 및 지급액 확인.\n"
        "■ 3년 시범사업·예산중립성·자율 참여 세부조건은 제공 메모와 "
        "이전 회기 법안에 있으나 2026년 새 법안 전문을 직접 확인하지 못해 독립 검증 전입니다.\n"
        "■ 다른 이슈: 메디케어 어드밴티지 별 등급에 따른 보험사 보너스 삭감 개편과 별개의 정책입니다.\n"
        "■ 원문 검증: " + status + ".\n"
        "■ 상원 공식 발표: " + OFFICIAL_SENATE + "\n"
        "■ 미국 의회 법안: " + BILL_PAGE
    )


def collect_source():
    body, error = fetch_text(OFFICIAL_SENATE, UA, timeout=14, attempts=1)
    if error or not senate_release_verified(body or ""):
        return False, "official_source_unavailable_or_incomplete"
    return True, "official_press_verified"


def collect_actions():
    body, error = fetch_text(OFFICIAL_STATUS, UA, timeout=12, attempts=1, accept="application/xml")
    if error or not body:
        return None, "source_unavailable"
    try:
        return read_bill_actions(body), "official_verified"
    except (ValueError, ET.ParseError):
        return None, "invalid_official_status_document"


def _api_headers(token: str) -> dict:
    return {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": UA}


def _github_request(url: str, token: str, payload: dict | None = None):
    headers = _api_headers(token)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, data=data,
                                 method="PUT" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def remote_state(repo: str, github_token: str):
    url = "https://api.github.com/repos/" + repo + "/contents/" + STATE_PATH + "?ref=main"
    try:
        result = _github_request(url, github_token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"version": 1, "events": {}}, None
        raise
    if not isinstance(result, dict) or result.get("encoding") != "base64":
        raise ValueError("Remote state unreadable")
    state = json.loads(base64.b64decode(result["content"]).decode("utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("events"), dict):
        raise ValueError("Existing remote state corrupt; not resetting")
    return state, str(result["sha"])


def remote_write(repo: str, github_token: str, state: dict, sha: str | None):
    url = "https://api.github.com/repos/" + repo + "/contents/" + STATE_PATH
    raw = (json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    payload = {"message": "Update only S5797 Medicare biosimilar alert receipt state",
               "branch": "main", "content": base64.b64encode(raw).decode("ascii")}
    if sha:
        payload["sha"] = sha
    return _github_request(url, github_token, payload)


def reserve(repo: str, github_token: str, key: str, run_id: str, source: str) -> bool:
    # Persist potential delivery ambiguity before any POST. Concurrent jobs
    # cannot claim the same key because GitHub compares the existing blob SHA.
    for attempt in range(5):
        state, sha = remote_state(repo, github_token)
        if key in state["events"]:
            return False
        state["events"][key] = {
            "status": "delivery_unconfirmed", "phase": "reserved_before_post",
            "run_id": run_id, "official_source": source,
            "reserved_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        }
        try:
            remote_write(repo, github_token, state, sha)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 422) or attempt == 4:
                raise
    return False


def acknowledge(repo: str, github_token: str, key: str, run_id: str, message_id: int):
    for attempt in range(5):
        state, sha = remote_state(repo, github_token)
        prev = state["events"].get(key) or {}
        if prev.get("run_id") != run_id or prev.get("status") != "delivery_unconfirmed":
            raise RuntimeError("Reservation changed, no receipt overwrite")
        state["events"][key] = {
            **prev, "status": "sent", "phase": "telegram_receipt_verified",
            "message_id": message_id, "recipient_verified": True,
            "sent_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        }
        try:
            remote_write(repo, github_token, state, sha)
            return
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 422) or attempt == 4:
                raise
    raise RuntimeError("Delivery confirmation state could not be persisted")


def verify_bot(token: str):
    req = urllib.request.Request("https://api.telegram.org/bot" + token + "/getMe",
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    username = str((data.get("result") or {}).get("username") or "")
    if data.get("ok") is not True or username.casefold() != BOT_EXPECTED.casefold():
        raise RuntimeError("Wrong policy Telegram bot")


def format_medical_alert(message: str) -> dict:
    """Only this medical subwatch: preserve every body line; use native clickable text."""
    text = ""
    entities = []
    sources = []
    source_labels = {
        "CMS 원문", "독립 시장 보도", "공식 최종규칙",
        "미국 의회 공식 기록", "법안 조회", "상원 공식 발표", "미국 의회 법안",
    }

    def units(value: str) -> int:
        return len(value.encode("utf-16-le")) // 2

    def append(value: str, kind: str = "", url: str = ""):
        nonlocal text
        if kind:
            entity = {"type": kind, "offset": units(text), "length": units(value)}
            if url:
                entity["url"] = url
            entities.append(entity)
        text += value

    for index, line in enumerate(line for line in message.splitlines() if line.strip()):
        label, colon, body = line.partition(": ")
        if (label.removeprefix("■ ") in source_labels and colon
                and body.startswith(("https://", "http://")) and not any(c.isspace() for c in body)
                and urllib.parse.urlsplit(body).hostname):
            sources.append((label.removeprefix("■ "), body))
            continue
        if text:
            append("\n\n")
        if index == 0:
            append(line, "bold")
        elif line.startswith("■ ") and colon:
            append(label, "bold")
            append(colon + body)
        else:
            append(line)
    if sources:
        append("\n\n")
        append("원문 및 출처", "bold")
        for label, url in sources:
            append("\n• ")
            append(label + " 바로가기", "text_link", url)
    # Do not silently clip a report or reserve its delivery if it cannot fit.
    if not text or units(text) > 4096:
        raise ValueError("Medical policy alert exceeds Telegram single-message limit; no truncation")
    return {"text": text, "entities": entities}


def medical_layout_receipt_verified(receipt: dict, layout: dict) -> bool:
    """Check what Telegram returned, separately from the existing delivery receipt."""
    result = receipt.get("result") or {}
    if result.get("text") != layout["text"]:
        return False
    def links(items):
        return sorted((x.get("offset"), x.get("length"), x.get("url"))
                      for x in items if x.get("type") == "text_link")
    return links(result.get("entities") or []) == links(layout["entities"])


def assert_medical_alert_layout(message: str, expected_urls: list[str]):
    layout = format_medical_alert(message)
    visible = layout["text"]
    encoded = visible.encode("utf-16-le")
    links = [e for e in layout["entities"] if e["type"] == "text_link"]
    assert [e["url"] for e in links] == expected_urls
    for e in links:
        label = encoded[e["offset"] * 2:(e["offset"] + e["length"]) * 2].decode("utf-16-le")
        assert label.endswith(" 바로가기") and "http" not in label
        assert e["url"] not in visible
    for line in message.splitlines():
        if line and not any(line.endswith(": " + url) for url in expected_urls):
            assert line in visible, "Medical alert body lost a line"
    assert all(e["type"] in ("bold", "text_link") for e in layout["entities"])
    assert "\n\n■ " in visible
    assert medical_layout_receipt_verified({"result": layout}, layout)
    assert not medical_layout_receipt_verified({"result": {"text": visible[:-1]}}, layout)


def test_medical_alert_send_payload(message: str):
    import io
    import unittest.mock as mock
    layout = format_medical_alert(message)
    fake = {"ok": True, "result": {"chat": {"id": 123}, "message_id": 99, **layout}}
    with mock.patch(__name__ + ".urllib.request.urlopen",
                    return_value=io.BytesIO(json.dumps(fake).encode("utf-8"))) as network:
        assert send_once("offline-token", "123", message) == 99
        assert network.call_count == 1
        params = urllib.parse.parse_qs(network.call_args.args[0].data.decode("utf-8"))
        assert params["text"] == [layout["text"]]
        assert json.loads(params["entities"][0]) == layout["entities"]
        assert params["disable_web_page_preview"] == ["true"]
    try:
        format_medical_alert("x" * 4097)
    except ValueError:
        pass
    else:
        raise AssertionError("Oversized medical alert must not be silently truncated")
    unicode_layout = format_medical_alert("제목 😀\n■ 본문: 한글 & < >\n■ CMS 원문: https://www.cms.gov/")
    e = next(e for e in unicode_layout["entities"] if e["type"] == "text_link")
    data = unicode_layout["text"].encode("utf-16-le")
    assert data[e["offset"]*2:(e["offset"]+e["length"])*2].decode("utf-16-le") == "CMS 원문 바로가기"
    print("medical_policy_clickable_links_full_body_offline=passed")


def send_once(token: str, chat: str, message: str) -> int:
    layout = format_medical_alert(message)
    payload = urllib.parse.urlencode({"chat_id": chat, "text": layout["text"],
                                     "entities": json.dumps(layout["entities"], ensure_ascii=False),
                                     "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request("https://api.telegram.org/bot" + token + "/sendMessage",
                                 data=payload, method="POST")
    # Intentionally no POST retry: response loss cannot prove the bot did not send.
    with urllib.request.urlopen(req, timeout=25) as response:
        receipt = json.loads(response.read().decode("utf-8"))
    message_id = validate_telegram_send_receipt(receipt, configured_chat=chat, route="policy")
    print("medical_alert_layout_receipt=" + ("verified" if medical_layout_receipt_verified(receipt, layout) else "unconfirmed"))
    return message_id


def deliver(event: dict, repo: str, github_token: str, bot: str, chat: str):
    state, _ = remote_state(repo, github_token)
    if event["key"] in state["events"]:
        entry = state["events"][event["key"]]
        print("s5797_event=deduped state=" + str(entry.get("status", "unknown")))
        return
    # Preflight is safe and cannot be confused with a Telegram send receipt.
    format_medical_alert(event['message'])
    verify_bot(bot)
    run_id = str(os.getenv("GITHUB_RUN_ID") or "manual") + ":" + str(
        os.getenv("GITHUB_RUN_ATTEMPT") or "1")
    if not reserve(repo, github_token, event["key"], run_id, event["source"]):
        print("s5797_event=deduped_remote")
        return
    try:
        mid = send_once(bot, chat, event["message"])
    except Exception as exc:
        # Reservation stays uncertain until reconciliation, not marked sent.
        raise RuntimeError("S5797 Telegram response unconfirmed; do not automatically resend") from None
    try:
        acknowledge(repo, github_token, event["key"], run_id, mid)
    except Exception:
        raise RuntimeError("S5797 Telegram accepted but GitHub receipt persistence unconfirmed") from None
    print("s5797_telegram_delivery_confirmed=true message_id=" + str(mid) +
          " recipient_verified=true stage=" + event["stage"])


def new_events(actions: list[dict] | None, senate_verified: bool) -> list[dict]:
    events = []
    if senate_verified:
        events.append({"key": INIT_KEY, "stage": "introduced",
                       "source": OFFICIAL_SENATE,
                       "message": introduced_message(status_verified=actions is not None)})
    if actions is None:
        return events
    for action in actions:
        stage = classify_material_stage(action)
        if not stage:
            continue
        key = f"congress119|S5797|{stage}|{action['date']}"
        events.append({"key": key, "stage": stage, "source": OFFICIAL_STATUS,
                       "message": stage_message(stage, action)})
    # Never report a future stage before initial introduction has been confirmed.
    return events if senate_verified else []


def self_test():
    sample = (
        "<html>Michael Bennet and John Cornyn Introduce Legislation "
        "Increasing Access to Biosimilars Act lowering prescription drug costs. "
        "Medicare Part B shared savings provides lower-cost drugs for patients.</html>"
    )
    assert senate_release_verified(sample)
    assert not senate_release_verified("<title>Increasing Access to Biosimilars Act</title>")
    sample_xml = """
    <billStatus><bill><congress>119</congress><number>5797</number>
    <title>Increasing access to biosimilar biological products under Medicare</title>
    <actions><item><actionDate>2026-11-19</actionDate>
    <text>Read twice and referred to the Committee on Finance.</text></item>
    <item><actionDate>2026-12-09</actionDate>
    <text>Committee on Finance ordered to be reported with an amendment.</text>
    </item></actions></bill></billStatus>"""
    parsed = read_bill_actions(sample_xml)
    assert parsed[0]["date"] == "2026-11-19"
    assert classify_material_stage(parsed[0]) == ""
    assert classify_material_stage(parsed[1]) == "committee_reported"
    assert len(new_events(parsed, True)) == 2
    assert new_events(parsed, False) == []
    try:
        read_bill_actions(sample_xml.replace("<number>5797</number>", "<number>5798</number>"))
    except ValueError:
        pass
    else:
        raise AssertionError("Different bill number must be rejected")
    assert len(introduced_message(status_verified=False)) < 4096
    for status_verified in (True, False):
        assert_medical_alert_layout(introduced_message(status_verified=status_verified),
                                    [OFFICIAL_SENATE, BILL_PAGE])
    for stage in ('committee_reported', 'passed_senate', 'passed_house', 'enacted'):
        assert_medical_alert_layout(stage_message(stage, parsed[1]), [OFFICIAL_STATUS, BILL_PAGE])
    long_action = 'Official action & < > ' + 'complete detail ' * 40
    full_stage = stage_message('committee_reported', {'date': '2026-12-09', 'text': long_action})
    assert long_action.strip() in format_medical_alert(full_stage)['text']
    test_medical_alert_send_payload(introduced_message(status_verified=True))
    import unittest.mock as mock
    existing = {"version": 1, "events": {INIT_KEY: {"status": "sent", "message_id": 52}}}
    with mock.patch(__name__ + ".remote_state", return_value=(existing, "oldsha")), \
         mock.patch(__name__ + ".verify_bot", side_effect=AssertionError("no duplicate bot call")), \
         mock.patch(__name__ + ".send_once", side_effect=AssertionError("no duplicate send")):
        deliver({"key": INIT_KEY, "stage": "introduced", "message": "test",
                 "source": OFFICIAL_SENATE}, "repo", "gh", "tg", "chat")
    with mock.patch(__name__ + ".remote_state", return_value=({
            "version": 1, "events": {INIT_KEY: {
                "run_id": "other", "status": "delivery_unconfirmed"}}
         }, "sha")), mock.patch(__name__ + ".remote_write") as writer:
        try:
            acknowledge("repo", "gh", INIT_KEY, "run-one", 701)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Must never overwrite another run's state")
        writer.assert_not_called()
    print("s5797_biosimilar_policy_offline_regressions=passed")


def main():
    if "--self-test" in sys.argv:
        self_test()
        return 0
    senate_ok, senate_status = collect_source()
    actions, official_status = collect_actions()
    if "--source-check" in sys.argv:
        print("s5797_live_source_check senate=" + senate_status
              + " bill_status=" + official_status + " telegram=not_called")
        return 0 if senate_ok else 2
    if not senate_ok:
        print("s5797=source_failed event_not_assumed_absent status=" + senate_status)
        return 2
    if os.environ.get("TELEGRAM_DRY_RUN", "false").lower() == "true":
        print("s5797=normal_skip_dry_run")
        return 0
    repo = str(os.environ.get("GITHUB_REPOSITORY") or "")
    github_token = str(os.environ.get("GH_TOKEN") or "")
    bot = str(os.environ.get("KHS_AI_POLICY_TELEGRAM_BOT_TOKEN") or "")
    chat = str(os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID") or "")
    if not all((repo, github_token, bot, chat)):
        print("s5797=missing_existing_policy_route_or_git_authorization")
        return 2
    try:
        for event in new_events(actions, senate_ok):
            deliver(event, repo, github_token, bot, chat)
    except Exception as exc:
        print("s5797=delivery_failure state_requires_reconciliation cause="
              + type(exc).__name__)
        return 2
    print("s5797=checked senate=" + senate_status + " official_bill=" + official_status
          + " stages=" + str(len(new_events(actions, senate_ok))))
    return 0 if official_status == "official_verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())
