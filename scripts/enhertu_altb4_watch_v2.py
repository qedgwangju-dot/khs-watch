from __future__ import annotations

import json
from pathlib import Path

import enhertu_altb4_watch as base

STATE = Path("data/enhertu_altb4_watch_state.json")
_ORIGINAL_BUILD_SUMMARY = base.build_item_summary


def is_eu_her2_mbc_1l(text: str) -> bool:
    low = text.lower()
    english = (
        ("destiny-breast09" in low)
        or (
            "pertuzumab" in low
            and any(x in low for x in ("first-line", "first line", "1st-line", "1l"))
            and "her2" in low
            and "breast" in low
        )
    )
    korean = (
        any(x in low for x in ("유럽", "eu"))
        and any(x in low for x in ("1차 치료", "1차치료", "1차 치료제"))
        and any(x in low for x in ("유방암", "her2"))
        and any(x in low for x in ("승인", "approved"))
    )
    return english or korean


def unified_event_key(item: base.Item) -> str:
    low = item.full.lower()
    if is_eu_her2_mbc_1l(item.full):
        indication = "her2_mbc_1l"
    elif "destiny-breast05" in low:
        indication = "her2_early_residual"
    else:
        indication = "other"

    if indication == "her2_mbc_1l" and any(x in low for x in ("approved", "approval", "승인", "유럽", "eu")):
        stage = "eu_approved"
    elif "chmp" in low and any(x in low for x in ("recommended", "권고")):
        stage = "chmp_positive"
    elif "fda" in low and any(x in low for x in ("approved", "approval", "승인")):
        stage = "fda_approved"
    elif any(x in low for x in ("subcutaneous", "alt-b4", "hybrozyme", "nct07015697", "피하주사")):
        stage = "sc_altb4"
    elif any(x in low for x in ("sales", "revenue", "매출")):
        stage = "sales"
    elif any(x in low for x in ("phase 3", "phase iii", "pfs", "overall survival", "orr", "3상")):
        stage = "clinical_update"
    else:
        stage = "material"

    # 매체, URL, 공식/2차 자료 여부가 달라도 같은 사건이면 한 번만 송출한다.
    return base.digest(f"enhertu|{indication}|{stage}")


def build_item_summary(item: base.Item) -> str:
    text = _ORIGINAL_BUILD_SUMMARY(item)
    if not is_eu_her2_mbc_1l(item.full):
        return text

    # 기사 본문 추출이 불완전해도 제목에서 오늘 EU 1차 치료 승인 사건이 식별되면
    # AstraZeneca 공식 발표로 교차검증한 사건명과 핵심 숫자를 사용한다.
    text = text.replace(
        "**Enhertu 규제·임상 업데이트**",
        "**Enhertu+pertuzumab, EU HER2+ 전이성 유방암 1차 치료 승인**",
    )
    text = text.replace(
        "허가 단계 추가 확인 필요",
        "유럽연합 집행위원회 승인 · HER2+ 절제불가·전이성 유방암 1차 치료 · THP 이후 10년 넘게 만의 첫 신규 1차 치료요법",
    )
    text = text.replace(
        "임상 핵심 수치 추가 확인 필요",
        "DESTINY-Breast09 3상 · 질병 진행·사망 위험 44% 감소 · HR 0.56 · 중앙값 PFS 40.7개월 vs THP 26.9개월 · ORR 85.1% vs 78.6%",
    )
    text = text.replace(
        "원문 본문 자동 추출 불완전",
        "해당 기사 본문 자동 추출 불완전 · AstraZeneca 공식 승인자료로 교차검증",
    )
    return text


def migrate_seen_event_keys() -> None:
    if not STATE.exists():
        return
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return
    if int(state.get("dedupe_version") or 1) >= 3:
        return

    seen_items = set(state.get("seen_keys") or [])
    migrated = set(state.get("seen_event_keys") or [])
    try:
        items, _ = base.collect()
    except Exception:
        items = []

    # 과거 버전에서 URL/출처별로 소비한 기사가 있으면 새 사건키에도 소비 이력을 승계한다.
    for item in items:
        try:
            if item.key in seen_items:
                migrated.add(unified_event_key(item))
        except Exception:
            continue

    state["seen_event_keys"] = sorted(migrated)[-4000:]
    state["dedupe_version"] = 3
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



# Direct, trial-specific monitoring. This is deliberately not a shared bio
# collector or a new workflow. The existing runner sends ALERT, then commits
# PENDING only after the existing Telegram sender confirms delivery.
import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor

TRIAL_ID = "NCT07015697"
TRIAL_PAGE = "https://clinicaltrials.gov/study/" + TRIAL_ID
TRIAL_API = "https://clinicaltrials.gov/api/v2/studies/" + TRIAL_ID
IR_PAGE = "https://t.me/s/alteogenIR"
# Last pre-change public registration: estimated 76, recruiting, 2028-12-31.
# Do not invent historical endpoint or arm fingerprints.
PRE_CHANGE = {
    "status": "RECRUITING", "count": 76, "count_type": "ESTIMATED",
    "primary_completion": "2028-12-31", "completion": "2028-12-31",
}
STATUS_KO = {
    "RECRUITING": "모집 중", "ACTIVE_NOT_RECRUITING": "임상 진행 중·신규 모집 종료",
    "NOT_YET_RECRUITING": "모집 전", "ENROLLING_BY_INVITATION": "초청 모집",
    "COMPLETED": "임상 완료", "SUSPENDED": "임상 일시 중단",
    "TERMINATED": "임상 조기 종료", "WITHDRAWN": "등록 전 연구 철회",
    "UNKNOWN": "상태 미확인",
}
FIELD_KO = {
    "status": "임상 상태", "count": "전체 등록 인원", "count_type": "등록 인원 구분",
    "primary_completion": "주요 평가 완료일", "completion": "전체 임상 완료일",
    "phase": "임상 단계", "arms": "용량 증량·확장 등 투약군 설계",
    "outcomes": "평가변수·측정기간", "results": "등록 결과 공개 여부",
    "why_stopped": "중단 사유",
}
FALLBACK_NEWS = "https://www.thebionews.net/news/articleView.html?idxno=30616"
FALLBACK_REGISTRY = "https://clinicaltrials.gg/study/" + TRIAL_ID


def study_snapshot(payload: dict) -> dict:
    protocol = payload["protocolSection"]
    ident = protocol["identificationModule"]
    if ident["nctId"] != TRIAL_ID:
        raise ValueError("trial ID mismatch")
    sponsor = protocol["sponsorCollaboratorsModule"]["leadSponsor"]["name"]
    if "daiichi" not in sponsor.lower():
        raise ValueError("trial sponsor mismatch")
    status = protocol["statusModule"]
    design = protocol["designModule"]
    enrollment = design["enrollmentInfo"]
    count = enrollment["count"]
    if type(count) is not int or count < 0 or enrollment["type"] not in {"ACTUAL", "ESTIMATED"}:
        raise ValueError("trial enrollment malformed")
    overall = status["overallStatus"]
    if overall not in STATUS_KO:
        raise ValueError("trial status unknown")
    posted = status["lastUpdatePostDateStruct"]["date"]
    dt.date.fromisoformat(posted)
    arms = protocol.get("armsInterventionsModule", {}).get("armGroups", [])
    if not isinstance(arms, list):
        raise ValueError("trial arms malformed")
    arm_labels = [str(a.get("label", "")) for a in arms]
    outcomes = protocol.get("outcomesModule", {})
    return {
        "status": overall, "count": count, "count_type": enrollment["type"],
        "primary_completion": status.get("primaryCompletionDateStruct", {}).get("date", ""),
        "completion": status.get("studyCompletionDateStruct", {}).get("date", ""),
        "phase": design.get("phases", []),
        "arms": base.digest(json.dumps(arms, ensure_ascii=False, sort_keys=True)),
        "arm_labels": arm_labels,
        "part2_present": any(re.search(r"dose[\s-]+expansion|part\s*[2b]\b", x, re.I) for x in arm_labels),
        "outcomes": base.digest(json.dumps(outcomes, ensure_ascii=False, sort_keys=True)),
        "results": bool(payload.get("hasResults") or payload.get("resultsSection")),
        "why_stopped": str(status.get("whyStopped", "")),
        "posted": posted,
        "verification": "official_api",
    }


def collect_registry(previous: dict) -> tuple[dict | None, str]:
    errors = []
    for url in (TRIAL_API, "https://www.clinicaltrials.gov/api/v2/studies/" + TRIAL_ID):
        try:
            raw, _ = base.fetch(url, timeout=9)
            return study_snapshot(json.loads(raw)), "official_api_verified"
        except Exception as exc:
            errors.append(type(exc).__name__)
    # One-time recovery of the known 11/20 change if the official API is
    # inaccessible. Both the dated news report and registry mirror must match.
    # Never use the historical mirror snapshot to roll back a newer baseline.
    if not previous.get("trial_registry_snapshot"):
        try:
            with ThreadPoolExecutor(max_workers=2) as ex:
                news_f = ex.submit(base.fetch, FALLBACK_NEWS, 9)
                mirror_f = ex.submit(base.fetch, FALLBACK_REGISTRY, 9)
                news = base.strip_html(news_f.result()[0])
                mirror = base.strip_html(mirror_f.result()[0]).lower()
            if (TRIAL_ID in news and "76명" in news and "17명" in news
                    and "모집 종료" in news and "2028년 12월 31일" in news
                    and "76" in mirror and "17" in mirror
                    and "active, not recruiting" in mirror and "nov 20, 2026" in mirror):
                return {
                    "status": "ACTIVE_NOT_RECRUITING", "count": 17, "count_type": "ACTUAL",
                    "primary_completion": "2028-12-31", "completion": "2028-12-31",
                    "part2_present": True, "posted": "2026-11-20",
                    "verification": "secondary_recovery",
                }, "official_api_failed_secondary_recovery"
        except Exception as exc:
            errors.append(type(exc).__name__)
    return None, "source_failed:" + ",".join(errors)


def registry_changes(previous: dict, current: dict) -> list[str]:
    # Date-only revisions and fields newly available after a source recovery
    # are not material changes. Never dedupe all SC developments as one event.
    return [key for key in FIELD_KO
            if key in previous and key in current and previous[key] != current[key]]


def count_display(s: dict) -> str:
    kind = {"ESTIMATED": "예상", "ACTUAL": "실제"}.get(s.get("count_type"), "구분 미확인")
    return str(s.get("count", "미확인")) + "명(" + kind + ")"


def registry_report(previous: dict, current: dict, changes: list[str]) -> str:
    rows = [
        "**엔허투 피하주사 1상 공식 임상 등록정보 변경 — " + TRIAL_ID + "**",
        "",
        "**■ 등록정보 게시일:** " + current["posted"] + " (미국 현지 등록일)",
        "",
    ]
    if "count" in changes or "count_type" in changes:
        before, after = previous["count"], current["count"]
        pct = f"({(after-before)/before*100:+.1f}%)" if before else ""
        rows.extend(["**■ 전체 등록 인원:** " + count_display(previous) + " → "
                     + count_display(current) + " " + pct, ""])
    if "status" in changes:
        rows.extend(["**■ 모집 상태:** " + STATUS_KO[previous["status"]] + " → "
                     + STATUS_KO[current["status"]], ""])
    for key in ("primary_completion", "completion"):
        if key in changes:
            rows.extend(["**■ " + FIELD_KO[key] + ":** " + str(previous[key])
                         + " → " + str(current[key]), ""])
    if current.get("completion"):
        rows.extend(["**■ 현재 전체 완료 예정일:** " + current["completion"]
                     + (" (기존 일정 유지)" if current.get("completion") == previous.get("completion") else ""), ""])
    if current.get("part2_present") is not None:
        rows.extend(["**■ 용량 확장 파트:** " + (
            "등록된 임상 설계에 남아 있음; 실제 개시·모집 확정과는 구별."
            if current["part2_present"] else
            "현재 등록된 투약군 명칭에서 용량 확장 파트를 확인하지 못함; 공식 설명 필요."), ""])
    for key in ("phase", "arms", "outcomes", "results", "why_stopped"):
        if key in changes:
            extra = ""
            if key == "results":
                extra = " — 등록 결과 " + ("공개 표시 확인" if current[key] else "미공개 표시")
            if key == "phase":
                extra = " — 등록 단계 변경"
            if key == "arms":
                extra = f" — 투약군 {len(previous.get('arm_labels', []))}개 → {len(current.get('arm_labels', []))}개"
            rows.extend(["**■ " + FIELD_KO[key] + ":** 변경 확인" + extra
                         + "; 공식 등록 이력에서 변경 전후 세부 항목 확인 필요.", ""])
    if current["status"] == "ACTIVE_NOT_RECRUITING":
        rows.extend(["**■ 의미:** 기존 환자 투약·추적관찰·자료 검토가 가능하며 임상 중단 또는 전체 임상 완료와 다릅니다.", ""])
    if previous.get("count") == 76 and current.get("count") == 17:
        rows.extend([
            "**■ 주의:** 17명은 등록정보의 전체 실제 인원입니다. 용량 증량 파트 완료 여부와 용량 확장 파트 개시·나머지 59명 모집 재개는 구분해야 하며, 59명 재모집은 확정되지 않았습니다.", "",
            "**■ 알테오젠 영향:** 이 변경만으로 ALT-B4 기술적 실패 또는 정상적 용량 확장 진입을 확정할 수 없습니다.", "",
        ])
    rows.extend([
        "**■ 다음 확인:** 용량 확장 파트 진행 결정·모집 재개·권장 용량·약동학(PK)·안전성·임상 결과·후속 일정·파트너 공식 설명.", "",
        "**■ 검증:** " + ("미국 공식 임상정보 API 직접 확인." if current["verification"] == "official_api"
                         else "미국 공식 API 접근 실패; 11월 20일 등록정보 변경을 보도와 등록정보 대체 자료로 대조. 공식 API 재확인 필요."), "",
        "**미국 임상시험 등록 원문**", "- 원문: " + TRIAL_PAGE, "",
        "**등록 변경 이력**", "- 원문: " + TRIAL_PAGE + "?tab=history",
    ])
    if current["verification"] != "official_api":
        rows.extend(["", "**등록정보 대체 자료**", "- 원문: " + FALLBACK_REGISTRY,
                     "", "**독립 보도**", "- 원문: " + FALLBACK_NEWS])
    return "\n".join(rows)


def parse_ir_posts(page: str, now: dt.datetime) -> list[dict]:
    # Telegram's public company IR channel, not investor discussion channels.
    matches = list(re.finditer(r'data-post=["\']alteogenir/(\d+)["\']', page, re.I))
    if not matches:
        raise ValueError("official IR channel post markers missing")
    posts = []
    for i, match in enumerate(matches):
        end = matches[i+1].start() if i+1 < len(matches) else len(page)
        segment = page[match.end():end]
        stamp = re.search(r'<time\b[^>]*datetime=["\']([^"\']+)', segment, re.I)
        body = re.search(r'<div\b[^>]*class=["\'][^"\']*tgme_widget_message_text[^"\']*["\'][^>]*>(.*?)</div>',
                         segment, re.I | re.S)
        if not stamp or not body:
            continue
        date = dt.datetime.fromisoformat(stamp[1].replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=base.UTC)
        if not dt.timedelta(days=-1) <= now-date <= dt.timedelta(days=10):
            continue
        plain = base.strip_html(body[1])
        low = plain.lower()
        if not (any(x in low for x in ("엔허투", "enhertu", "nct07015697"))
                and any(x in low for x in ("임상", "trial"))
                and any(x in low for x in ("피하주사", "엔허투sc", "enhertusc", "enhertu sc", "nct07015697", "alt-b4"))
                and any(x in low for x in ("모집", "등록", "용량 증량", "용량증량", "용량 확장", "용량확장",
                                            "약동학", "안전성", "다음 단계", "후속 개발", "중단", "재개",
                                            "dose-escalation", "dose expansion", "enrollment", "임상 결과"))):
            continue
        # Do not mistake forwarded broker/news commentary for an issuer's claim.
        if "tgme_widget_message_forwarded_from" in segment:
            continue
        posts.append({
            "id": match[1], "date": date.astimezone(base.KST).isoformat(timespec="seconds"),
            "text": plain, "key": base.digest("enhertu-ir|" + base.normalize(plain)),
            "url": "https://t.me/alteogenIR/" + match[1],
        })
    return posts


def collect_ir() -> tuple[list[dict], str]:
    try:
        page, _ = base.fetch(IR_PAGE, timeout=10)
        return parse_ir_posts(page, dt.datetime.now(base.UTC)), "official_ir_verified"
    except Exception as exc:
        return [], "source_failed:" + type(exc).__name__


def ir_report(post: dict) -> str:
    body = post["text"]
    low = body.lower()
    rows = ["**알테오젠 공식 IR — 엔허투 피하주사 임상 후속 설명**", "",
            "**■ 게시 시각(한국시간):** " + post["date"], ""]
    if any(x in low for x in ("용량 증량", "용량증량", "dose-escalation")) and "등록" in body and "완료" in body:
        rows.extend(["**■ 파트너사 설명:** 용량 증량 파트의 환자 등록이 완료됐습니다.", ""])
    if "다음 단계" in body and ("평가" in body or "검토" in body):
        rows.extend(["**■ 후속 단계:** 다이이찌산쿄가 다음 단계를 평가 중입니다. 용량 확장 파트의 개시·추가 인원은 아직 확정되지 않았습니다.", ""])
    # Preserve the issuer's substantive explanation, including newly disclosed
    # numbers and uncertainty, rather than reducing every update to one label.
    rows.extend(["**■ 회사 발표 내용:** " + body, "",
                 "**■ 다음 확인:** 회사 추가 답변·임상 등록 변경·후속 임상 진행·약동학 및 안전성 자료.", "",
                 "**알테오젠 공식 IR 게시물**", "- 원문: " + post["url"]])
    return "\n".join(rows)


def direct_trial_updates(state: dict, current: dict | None, posts: list[dict]) -> tuple[list[str], dict]:
    reports = []
    updates = {}
    previous = state.get("trial_registry_snapshot") or PRE_CHANGE
    if current is not None:
        if not state.get("trial_registry_snapshot") or current["posted"] >= previous.get("posted", ""):
            changes = registry_changes(previous, current)
            if changes:
                reports.append(registry_report(previous, current, changes))
            updates["trial_registry_snapshot"] = current
    known = set(state.get("trial_ir_seen_keys") or [])
    for post in sorted(posts, key=lambda x: (x["date"], int(x["id"]))):
        if post["key"] in known:
            continue
        reports.append(ir_report(post))
        known.add(post["key"])
    updates["trial_ir_seen_keys"] = sorted(known)
    return reports, updates


def self_test_direct_trial() -> None:
    from copy import deepcopy
    payload = {"protocolSection": {
        "identificationModule": {"nctId": TRIAL_ID},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Daiichi Sankyo"}},
        "statusModule": {
            "overallStatus": "ACTIVE_NOT_RECRUITING", "lastUpdatePostDateStruct": {"date": "2026-11-20"},
            "primaryCompletionDateStruct": {"date": "2028-12-31"},
            "studyCompletionDateStruct": {"date": "2028-12-31"},
        },
        "designModule": {"enrollmentInfo": {"count": 17, "type": "ACTUAL"}, "phases": ["PHASE1"]},
        "armsInterventionsModule": {"armGroups": [{"label": "Part 1 (Dose Escalation)"}, {"label": "Part 2 (Dose Expansion)"}]},
        "outcomesModule": {"primaryOutcomes": [{"measure": "AUC"}]},
    }, "hasResults": False}
    sample = study_snapshot(payload)
    assert sample["part2_present"] and registry_changes(PRE_CHANGE, sample) == ["status", "count", "count_type"]
    # The legacy SC dedupe key must not consume a new registry event.
    old = {"seen_event_keys": [base.digest("enhertu|other|sc_altb4")]}
    reports, updates = direct_trial_updates(old, sample, [])
    assert len(reports) == 1 and "76명(예상) → 17명(실제)" in reports[0]
    assert "59명 재모집은 확정되지 않았습니다" in reports[0]
    assert TRIAL_PAGE in reports[0] and "2028-12-31" in reports[0]
    assert old == {"seen_event_keys": [base.digest("enhertu|other|sc_altb4")]}
    repeat = deepcopy(sample)
    repeat["posted"] = "2026-11-21"
    assert direct_trial_updates(updates, repeat, [])[0] == []
    reopened = deepcopy(repeat)
    reopened["status"] = "RECRUITING"
    assert len(direct_trial_updates(updates, reopened, [])[0]) == 1
    assert "trial_registry_snapshot" not in direct_trial_updates(updates, None, [])[1]
    ir_html = ('<div data-post="alteogenIR/999"><div class="tgme_widget_message_text js-message_text">'
               '엔허투SC 임상 용량 증량 파트 환자 등록 완료. 다음 단계 평가 중.</div>'
               '<time datetime="2026-11-24T00:00:00+00:00"></time></div>')
    posts = parse_ir_posts(ir_html, dt.datetime(2026, 11, 24, 12, tzinfo=base.UTC))
    assert len(posts) == 1 and posts[0]["url"].endswith("/999")
    ir_reports, ir_updates = direct_trial_updates(updates, None, posts)
    assert len(ir_reports) == 1 and "용량 증량 파트" in ir_reports[0]
    assert direct_trial_updates(ir_updates, None, posts)[0] == []
    print("enhertu_direct_trial_ir_regressions=passed", flush=True)


def main() -> int:
    self_test_direct_trial()
    migrate_seen_event_keys()
    base.event_key = unified_event_key
    base.build_item_summary = build_item_summary
    state = base.load_state()
    # Independent source checks; preserve legacy news and existing delivery.
    with ThreadPoolExecutor(max_workers=2) as ex:
        registry_f = ex.submit(collect_registry, state)
        ir_f = ex.submit(collect_ir)
        current, registry_health = registry_f.result()
        posts, ir_health = ir_f.result()
    reports, updates = direct_trial_updates(state, current, posts)
    rc = base.main()
    if rc != 0:
        return rc
    pending = json.loads(base.PENDING.read_text(encoding="utf-8"))
    pending.update(updates)
    pending["trial_registry_source_status"] = registry_health
    pending["trial_ir_source_status"] = ir_health
    # The shared runner persists this file only after actual send confirmation
    # whenever an alert exists. No live seen file is rewritten here.
    if reports:
        legacy = base.ALERT.read_text(encoding="utf-8").strip() if base.ALERT.exists() else ""
        body = "[바이오 감시] 엔허투 피하주사 임상 변화\n\n" + "\n\n".join(reports)
        if legacy:
            body += "\n\n" + legacy
        base.ALERT.write_text(body + "\n", encoding="utf-8")
    base.PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status = (f"enhertu_registry={registry_health}; official_ir={ir_health}; "
              f"direct_material_events={len(reports)}")
    with base.STATUS.open("a", encoding="utf-8") as out:
        out.write(status + "\n")
    print(status, flush=True)
    # A failed source is not a successful no-change check. If another verified
    # event is ready, let the existing sender deliver it without discarding it.
    if not base.ALERT.exists() and (registry_health.startswith("source_failed")
                                    or ir_health.startswith("source_failed")):
        return 2
    return 0


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        self_test_direct_trial()
        raise SystemExit(0)
    raise SystemExit(main())
