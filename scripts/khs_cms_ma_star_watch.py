#!/usr/bin/env python3
"""Isolated CMS Medicare Advantage Stars proposal/final-rule lane for KHS policy watch.

Never sends on a push/dry run. Separate original CMS policy date, market reaction,
measurement, ratings and payment years. Uses a durable GitHub reservation BEFORE
a Telegram POST, then upgrades to sent only after an actual matching chat receipt.
No shared policy collector, state or Telegram formatter is modified.
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
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text

KST = ZoneInfo("Asia/Seoul")
OFFICIAL_FACT = ("https://www.cms.gov/newsroom/fact-sheets/"
    "contract-year-2028-policy-technical-changes-medicare-advantage-program-medicare-prescription-drug")
OFFICIAL_PRESS = ("https://www.cms.gov/newsroom/press-releases/"
    "cms-proposes-reforms-strengthen-competition-elevate-care-quality-expand-beneficiary-choice-medicare")
FEDERAL_REGISTER = ("https://www.federalregister.gov/api/v1/documents.json?"
    "conditions%5Bterm%5D=CMS-4214&order=newest&per_page=25")
MARKET_REPORT = "https://sg.finance.yahoo.com/news/health-insurer-stocks-slide-medicare-133027672.html"
PROPOSED_KEY = "cms-4214-p2|star-ratings|proposed|2026-11-20"
STATE_PATH = "data/khs_cms_ma_star_watch_state.json"
EXPECTED_BOT = "khs88798879_bot"
UA = "KHS-MA-Stars-Watch/1.0 (+github-actions; official-source-validation)"
GITHUB_API = "https://api.github.com"
SCHEMA_VERSION = 1


def plain(raw: str) -> str:
    raw = re.sub(r"(?is)<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip().lower()


def proposal_verified(body: str) -> bool:
    text = plain(body)
    return (
        "cms-4214-p2" in text and "medicare advantage" in text
        and "star ratings" in text and "2028" in text
        and ("2030 star ratings" in text or "15 measures" in text)
        and "propos" in text
    )


def detect_final_rule(payload: object) -> list[dict]:
    """Strictly separate a new actual final rule from the Nov 20 proposal."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Federal Register response schema unavailable")
    out = []
    for item in payload["results"]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        abstract = str(item.get("abstract") or "")
        typ = str(item.get("type") or "").lower()
        publication = str(item.get("publication_date") or "")
        document_id = str(item.get("document_number") or "")
        url = str(item.get("html_url") or "")
        label = (title + " " + abstract).lower()
        if (
            typ in {"rule", "final rule"} and publication >= "2026-11-20"
            and ("contract year 2028" in label or "cms-4214-f" in label)
            and "medicare advantage" in label and "star" in label
            and re.fullmatch(r"20\d{2}-\d{5}", document_id)
            and url.startswith("https://www.federalregister.gov/")
        ):
            out.append({"key": "cms-ma-stars-final|" + document_id,
                        "publication": publication, "url": url})
    return out


def proposal_message() -> str:
    return (
        "[미국 CMS 메디케어 어드밴티지 정책] 별 등급 개편안 — 미확정\n\n"
        "■ 정책 발표: 2026년 11월 20일 CMS가 CMS-4214-P2 개편안을 제안했습니다. "
        "2026년 11월 23일 보험주 급락은 별도의 시장 반응일입니다.\n"
        "■ 평가 변경: 품질 평가 항목을 15개로 줄이고 추가 보상 요인을 폐지하며, "
        "등급 개선 관련 보호를 최고 등급 4.5성 이상 계약으로 제한하는 방안을 제시했습니다.\n"
        "■ 일정: 2028년 측정 실적 → 2030년 별 등급 → 2031년 보험사 품질 보너스 지급에 영향. "
        "현재 확정 시행이나 즉시 지급 중단이 아닙니다.\n"
        "■ 규모: TD Cowen이 인용한 CMS 추산은 2028~2037년 업계 전체 "
        "1,070억달러(약 143.3조원), 2031년 약 115억달러(약 15.4조원) 감소입니다. "
        "개별 보험사 확정 손실이 아닙니다.\n"
        "■ 시장 영향: 11월 23일 장전 UNH -6.5%, HUM -5.1%, CVS -4.5%, ELV -1.1% 보도. "
        "Mizuho는 무대응·원안 확정 가정에서 4성 이상 가입자 비중 "
        "51.5% → 28.0%를 추정했습니다.\n"
        "■ 다음 확인: 의견수렴 → 최종 규칙 → 측정 지표·별 등급 → 품질 보너스 반영. "
        "제안·확정·시행·실제 지급액을 구별합니다.\n"
        "■ 원화 환산: 2026-11-23 유럽중앙은행 계열 참고환율 1달러≈1,339.22원 기준.\n"
        "■ CMS 원문: " + OFFICIAL_FACT + "\n"
        "■ 독립 시장 보도: " + MARKET_REPORT
    )


def final_message(event: dict) -> str:
    return (
        "[미국 CMS 메디케어 어드밴티지 별 등급] 후속 최종규칙 확인\n\n"
        "■ 단계: 2026년 11월 20일 제안과 구별되는 연방관보 최종규칙이 공개됐습니다.\n"
        "■ 최종규칙 게시일: " + event["publication"] + "\n"
        "■ 문서번호: " + event["key"].split("|")[-1] + "\n"
        "■ 주의: 최종 규칙의 세부 평가·삭감 규모와 시행 시점이 원안과 "
        "같은지는 첨부 규칙 전문을 따로 대조해야 합니다. 기존 1,070억 달러를 "
        "확정 감액으로 승격하지 않습니다.\n"
        "■ 공식 최종규칙: " + event["url"]
    )


def fetch_official():
    failures = []
    for url in (OFFICIAL_FACT, OFFICIAL_PRESS):
        body, error = fetch_text(url, UA, timeout=12, attempts=1)
        if error is None and proposal_verified(body or ""):
            return url, failures
        failures.append("cms_source_unavailable_or_incomplete")
    return None, failures


def fetch_final():
    body, error = fetch_text(
        FEDERAL_REGISTER, UA, timeout=12, attempts=1, accept="application/json"
    )
    if error:
        return [], "source_unavailable"
    try:
        return detect_final_rule(json.loads(body or "")), "ok"
    except (ValueError, TypeError, json.JSONDecodeError):
        return [], "invalid_schema"


def _api_headers(token: str) -> dict:
    return {"Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": UA}


def _github_request(url: str, token: str, *, body: dict | None = None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdr = _api_headers(token)
    if data is not None:
        hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdr,
        method="PUT" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def load_remote(repo: str, token: str):
    url = GITHUB_API + "/repos/" + repo + "/contents/" + STATE_PATH + "?ref=main"
    try:
        payload = _github_request(url, token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"schema_version": SCHEMA_VERSION, "events": {}}, None
        raise
    if not isinstance(payload, dict) or payload.get("encoding") != "base64":
        raise RuntimeError("CMS watch state content invalid")
    content = base64.b64decode(payload["content"]).decode("utf-8")
    state = json.loads(content)
    if not isinstance(state, dict) or not isinstance(state.get("events"), dict):
        raise RuntimeError("CMS watch state JSON invalid; no baseline reset")
    return state, payload["sha"]


def write_remote(repo: str, token: str, state: dict, sha: str | None):
    url = GITHUB_API + "/repos/" + repo + "/contents/" + STATE_PATH
    encoded = base64.b64encode(
        (json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    ).decode("ascii")
    update = {"message": "Update only CMS Medicare Advantage Stars delivery state",
              "branch": "main", "content": encoded}
    if sha:
        update["sha"] = sha
    return _github_request(url, token, body=update)


def claim(repo: str, token: str, key: str, run_id: str, source: str) -> bool:
    # GitHub optimistic commit acts as the cross-run lock. Never send before
    # a durable uncertain-delivery reservation is committed on main.
    for attempt in range(5):
        state, sha = load_remote(repo, token)
        if key in state["events"]:
            return False
        state["events"][key] = {
            "status": "delivery_unconfirmed", "phase": "reserved_before_post",
            "run_id": run_id, "source_url": source,
            "at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        }
        try:
            write_remote(repo, token, state, sha)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 422) or attempt == 4:
                raise
    return False


def confirm(repo: str, token: str, key: str, run_id: str, message_id: int):
    for attempt in range(5):
        state, sha = load_remote(repo, token)
        current = state["events"].get(key)
        if not isinstance(current, dict) or current.get("run_id") != run_id:
            raise RuntimeError("CMS event reservation changed; receipt not overwritten")
        state["events"][key] = {
            **current, "status": "sent", "phase": "api_ack_verified",
            "telegram_message_id": message_id, "destination_verified": True,
            "confirmed_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        }
        try:
            write_remote(repo, token, state, sha)
            return
        except urllib.error.HTTPError as exc:
            if exc.code not in (409, 422) or attempt == 4:
                raise
    raise RuntimeError("CMS event receipt not persisted; reservation left intact")


def verify_bot(token: str):
    url = "https://api.telegram.org/bot" + token + "/getMe"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        v = json.loads(r.read().decode("utf-8"))
    actual = str((v.get("result") or {}).get("username") or "")
    if v.get("ok") is not True or actual.casefold() != EXPECTED_BOT.casefold():
        raise RuntimeError("CMS event policy Telegram bot identity mismatch")


def send_once(token: str, chat_id: str, message: str) -> int:
    if len(message) > 4096:
        raise ValueError("CMS alert exceeds Telegram single-message limit")
    params = urllib.parse.urlencode({
        "chat_id": chat_id, "text": message,
        "disable_web_page_preview": "true"
    }).encode("utf-8")
    req = urllib.request.Request("https://api.telegram.org/bot" + token + "/sendMessage",
        data=params, method="POST")
    # NEVER repeat POST if response is lost.
    with urllib.request.urlopen(req, timeout=25) as r:
        result = json.loads(r.read().decode("utf-8"))
    from khs_policy_telegram_delivery import validate_telegram_send_receipt
    return validate_telegram_send_receipt(
        result, configured_chat=chat_id, route="policy"
    )


def handle_event(event: dict, repo: str, github_token: str, bot_token: str, chat: str):
    key, message, source = event["key"], event["message"], event["source"]
    state, _ = load_remote(repo, github_token)
    if key in state["events"]:
        previous = state["events"][key]
        print("cms_ma_stars_event=deduped status=" + str(previous.get("status", "unknown")))
        return
    # All preflight checks occur before the durable claim.
    verify_bot(bot_token)
    run_id = str(os.environ.get("GITHUB_RUN_ID") or "manual") + "-" + str(
        os.environ.get("GITHUB_RUN_ATTEMPT") or "1")
    if not claim(repo, github_token, key, run_id, source):
        print("cms_ma_stars_event=deduped_concurrent_run")
        return
    try:
        message_id = send_once(bot_token, chat, message)
    except Exception as exc:
        # Leave the durable marker in delivery_unconfirmed. It may have sent.
        raise RuntimeError("CMS Telegram receipt uncertain; no automatic retry: "
                           + type(exc).__name__) from None
    try:
        confirm(repo, github_token, key, run_id, message_id)
    except Exception:
        raise RuntimeError(
            "CMS Telegram API acknowledged, but GitHub checkpoint not confirmed; "
            "no automatic resend"
        ) from None
    print(f"cms_ma_stars_delivered=true destination_verified=true message_id={message_id}")


def self_test():
    good = ("CMS-4214-P2 Medicare Advantage proposes 15 measures for Star Ratings "
            "reward factor 2028 measurement period 2030 Star Ratings.")
    assert proposal_verified(good)
    assert not proposal_verified("CMS-4214-P2 Medicare Advantage existing 2027 final rule")
    assert not proposal_verified("unrelated Star Ratings proposed 2028 2030")
    rules = {"results": [
        {"type": "Proposed Rule", "title": "Contract Year 2028 Medicare Advantage Star Ratings",
         "document_number": "2026-23960", "publication_date": "2026-11-20",
         "html_url": "https://www.federalregister.gov/d/2026-23960"},
        {"type": "Rule", "title": "Contract Year 2028 Medicare Advantage Star Ratings",
         "document_number": "2027-01234", "publication_date": "2027-04-01",
         "html_url": "https://www.federalregister.gov/d/2027-01234"},
    ]}
    assert len(detect_final_rule(rules)) == 1
    assert detect_final_rule(rules)[0]["key"] == "cms-ma-stars-final|2027-01234"
    msg = proposal_message()
    for value in ("2026년 11월 20일", "2026년 11월 23일", "2028년", "2030년",
                  "2031년", "1,070억달러", "115억달러", "51.5% → 28.0%", "미확정"):
        assert value in msg, value
    assert len(msg) <= 4096
    # Confirm must never mark a different runner's reservation as delivered.
    import unittest.mock as mock
    state = {"schema_version": 1, "events": {PROPOSED_KEY: {
        "status": "delivery_unconfirmed", "run_id": "old-run"}}}
    with mock.patch(__name__ + ".load_remote", return_value=(state, "old-sha")), \
         mock.patch(__name__ + ".write_remote") as write:
        try:
            confirm("example/repo", "offline-token", PROPOSED_KEY, "other-run", 123)
        except RuntimeError:
            pass
        else:
            raise AssertionError("cross-run overwrite must be blocked")
        write.assert_not_called()
    with mock.patch(__name__ + ".verify_bot", side_effect=AssertionError("must not send")), \
         mock.patch(__name__ + ".load_remote", return_value=({
             "schema_version": 1, "events": {PROPOSED_KEY: {"status": "sent"}}
         }, "sha")):
        handle_event({"key": PROPOSED_KEY, "message": msg, "source": OFFICIAL_FACT},
                     "repo/x", "gh", "tg", "123")
    print("cms_ma_stars_offline_regressions=passed")


def main() -> int:
    if "--self-test" in sys.argv:
        self_test()
        return 0
    if os.getenv("TELEGRAM_DRY_RUN", "false").lower() == "true":
        print("cms_ma_stars=normal_skip_dry_run")
        return 0
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    github_token = os.getenv("GH_TOKEN", "").strip()
    bot = os.getenv("KHS_AI_POLICY_TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("KHS_POLICY_TELEGRAM_CHAT_ID", "").strip()
    if not repo or not github_token or not bot or not chat:
        print("cms_ma_stars=failed reason=existing_policy_route_or_github_token_missing")
        return 2

    source, failures = fetch_official()
    if source is None:
        print("cms_ma_stars=source_unavailable official_verified=false "
              + "source_attempts=" + str(len(failures)))
        return 2  # A fetch failure is not the absence of a policy event.
    events = [{"key": PROPOSED_KEY, "message": proposal_message(), "source": source}]
    final_rules, final_status = fetch_final()
    for final in final_rules:
        events.append({"key": final["key"], "message": final_message(final),
                       "source": final["url"]})
    try:
        for event in events:
            handle_event(event, repo, github_token, bot, chat)
    except Exception as exc:
        # Never expose Telegram tokens, recipient IDs or signed GitHub URLs.
        print("cms_ma_stars=failed delivery_state_must_be_checked reason="
              + type(exc).__name__)
        return 2
    print("cms_ma_stars=checked proposal_source=verified "
          + "final_rule_source=" + final_status
          + " final_rules_found=" + str(len(final_rules)))
    return 0 if final_status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
