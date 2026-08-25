#!/usr/bin/env python3
"""Compatibility entrypoint for the semantic Deep Fission v3 watcher.

Additional live guards:
- suppress recycled semantic facts repeated in unrelated press releases;
- keep alert content in Korean except identifiers/official acronyms;
- preserve the same information while grouping it for fast Telegram reading.
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil

import deep_fission_watch_v3 as v3

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
OLD_STATE = DATA / "deep_fission_watch_state.json"
OLD_PENDING = OUT / "deep_fission_watch_state_pending.json"
OLD_ALERT = OUT / "deep_fission_alert.md"
OLD_STATUS = OUT / "deep_fission_status.md"
OLD_ERRORS = OUT / "deep_fission_errors.log"
FALSE_EVENT_IDS = {"customer-pipeline:2026-08-25"}


def load_old_state() -> dict:
    if not OLD_STATE.exists():
        return {}
    try:
        return json.loads(OLD_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def prepare_state() -> None:
    """Carry the semantic v3 state through filenames used by the existing workflow."""
    v3.STATE.unlink(missing_ok=True)
    state = load_old_state()
    if state.get("version") == 3:
        sent = state.get("sent_event_ids") or []
        state["sent_event_ids"] = [eid for eid in sent if eid not in FALSE_EVENT_IDS]
        v3.STATE.parent.mkdir(parents=True, exist_ok=True)
        v3.STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def install_parsons_guard() -> None:
    """Do not mark the full non-nuclear demo complete before deployment prerequisites."""
    original = v3.extract_parsons_state

    def guarded(text: str) -> dict[str, bool]:
        state = original(text)
        if not state.get("poc_depth_reached") or not state.get("prototype_underground_deployed"):
            state["non_nuclear_demo_complete"] = False
        return state

    v3.extract_parsons_state = guarded


def install_press_guard() -> None:
    """Suppress old milestones repeated as boilerplate in unrelated new releases."""
    original = v3.classify_press
    baseline = load_old_state()
    prior_press = baseline.get("press_urls") or {}
    had_185_pipeline = any(
        "18.5" in v3.norm(str(title)) and "customer pipeline" in v3.norm(str(title))
        for title in prior_press.values()
    )

    def guarded(title: str, text: str, url: str):
        events = original(title, text, url)
        title_low = v3.norm(title)
        body_low = v3.norm(text)

        # A new HR/IR/other release may repeat the old 18.5 GW company boilerplate.
        # Customer-pipeline alerts require the release title itself to signal a customer/power-site update.
        pipeline_title_signal = any(
            token in title_low
            for token in ["customer pipeline", "customer", "power site", "letter of intent", "loi", "gigawatt"]
        )
        if not pipeline_title_signal:
            events = [item for item in events if not item[0].startswith("customer-pipeline:")]

        # 18.5 GW was already officially announced on June 24, 2026.
        # Do not create a fresh event merely because a later release repeats the same number/LOI status.
        if had_185_pipeline and "18.5" in body_low:
            events = [item for item in events if not item[0].startswith("customer-pipeline:")]

        return events

    v3.classify_press = guarded


REPLACEMENTS = [
    ("고객 pipeline", "잠재 고객 프로젝트 규모"),
    ("pipeline", "잠재 고객 프로젝트 규모"),
    ("non-binding LOI", "구속력 없는 의향서(LOI)"),
    ("non-binding", "구속력 없음"),
    ("named customer", "실명 고객"),
    ("binding PPA/offtake", "구속력 있는 전력구매계약(PPA)·오프테이크 계약"),
    ("definitive agreement", "본계약"),
    ("counterparty", "계약 상대방"),
    ("Nuclear Safety Design Agreement(NSDA)", "원자력 안전설계협약(NSDA)"),
    ("Nuclear Safety Design Agreement", "원자력 안전설계협약"),
    ("DOE authorization", "DOE 승인"),
    ("authorization", "승인"),
    ("prototype reactor canister", "시제품 원자로 용기"),
    ("prototype canister", "시제품 원자로 용기"),
    ("prototype", "시제품"),
    ("commercial-scale", "상업 규모"),
    ("borehole integrity", "시추공 건전성"),
    ("borehole", "시추공"),
    ("Parsons PoC", "파슨스 개념검증(PoC)"),
    ("PoC", "개념검증(PoC)"),
    ("Combined License", "통합허가"),
    ("combined license", "통합허가"),
    ("pre-application", "사전 신청 단계"),
    ("docketing", "정식 접수"),
    ("review schedule", "심사 일정"),
    ("review", "심사"),
    ("RAI", "추가정보요청(RAI)"),
    ("hearing/EIS", "청문·환경영향평가(EIS)"),
    ("fuel loading", "연료 장전"),
    ("commercial licensing", "상업 허가"),
    ("full-power", "전출력"),
    ("full power", "전출력"),
    ("public offering", "주식 공모"),
    ("financing", "자금조달"),
    ("power purchase", "전력구매"),
    ("final investment decision", "최종투자결정(FID)"),
    ("cash flow", "현금흐름"),
    ("MW·가격·착공시점", "계약 용량(MW)·가격·착공 시점"),
    ("MW·가격·착공 시점", "계약 용량(MW)·가격·착공 시점"),
]


def koreanize(value: str) -> str:
    text = value
    for src, dst in REPLACEMENTS:
        text = text.replace(src, dst)
    text = re.sub(r"(?<!의향서\()\bLOI\b", "의향서(LOI)", text)
    text = re.sub(r"(?<!전력구매계약\()\bPPA\b", "전력구매계약(PPA)", text)
    text = re.sub(r"\bofftake\b", "오프테이크 계약", text, flags=re.I)
    text = re.sub(r"\bcontract\b", "계약", text, flags=re.I)
    text = re.sub(r"\border\b", "수주", text, flags=re.I)
    text = re.sub(r"\bcustomer\b", "고객", text, flags=re.I)
    text = re.sub(r"\bdrilling\b", "시추", text, flags=re.I)
    text = re.sub(r"\bdeployment\b", "배치", text, flags=re.I)
    text = re.sub(r"\btesting\b", "시험", text, flags=re.I)
    text = re.sub(r"\btest\b", "시험", text, flags=re.I)
    text = re.sub(r"\bcommercial\b", "상업", text, flags=re.I)
    return text


def translate_generic_release_fact(value: str) -> str:
    prefix = "신규 공식 보도자료 발표:"
    if not value.startswith(prefix):
        return value
    title = value[len(prefix):].strip().lower()
    if "public offering" in title:
        return "주식 공모 관련 신규 공식 보도자료 발표"
    if "financing" in title:
        return "자금조달 관련 신규 공식 보도자료 발표"
    if "power purchase" in title or "ppa" in title:
        return "전력구매계약(PPA) 관련 신규 공식 보도자료 발표"
    if "final investment decision" in title:
        return "최종투자결정(FID) 관련 신규 공식 보도자료 발표"
    if "combined license" in title:
        return "NRC 통합허가 관련 신규 공식 보도자료 발표"
    if "contract" in title or "order" in title:
        return "계약·수주 관련 신규 공식 보도자료 발표"
    return "Deep Fission의 중요 사업 관련 신규 공식 보도자료 발표"


def format_one_alert(block: str) -> str:
    fields: dict[str, str] = {}
    header = ""
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[Deep Fission 중요 변화"):
            header = line
            continue
        m = re.match(r"^- ([^:]+):\s*(.*)$", line)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()

    fact = translate_generic_release_fact(fields.get("새 사실", ""))
    fact = koreanize(fact)
    transition = koreanize(fields.get("이전 → 현재", ""))
    stage = koreanize(fields.get("단계", ""))
    axes = koreanize(fields.get("바뀐 축", ""))
    korea = koreanize(fields.get("한국 기업 연결", ""))
    risk = koreanize(fields.get("실패 경로", ""))
    next_check = koreanize(fields.get("다음 확인", ""))
    source = koreanize(fields.get("출처", ""))
    official_date = fields.get("공식일", "")
    verdict = koreanize(fields.get("판정", "신규 공식 변화 확인"))
    url = fields.get("링크", fields.get("원문", ""))

    parts = [header or f"[Deep Fission 중요 변화 | {v3.kst_now()}]", ""]
    parts += [
        "■ 핵심 변화",
        f"• {fact}" if fact else "• 신규 공식 변화 확인",
        f"• 이전 → 현재: {transition}" if transition else "",
        f"• 공식일: {official_date}" if official_date else "",
        "",
        "■ 투자 영향",
        f"• 판정: {verdict}",
        f"• 단계: {stage}" if stage else "",
        f"• 바뀐 축: {axes}" if axes else "",
        "",
        "■ 한국 기업 연결",
        f"• {korea}" if korea else "• 신규 직접계약 확인 필요",
        "",
        "■ 실패 경로",
        f"• {risk}" if risk else "• 실제 상업계약·매출 연결 지연 가능성 확인 필요",
        "",
        "■ 다음 확인",
        f"• {next_check}" if next_check else "• 후속 공식 자료 확인",
        "",
        f"출처: {source}" if source else "",
        f"원문: {url}" if url else "",
    ]
    return "\n".join(x for x in parts if x != "")


def format_alert_korean(text: str) -> str:
    blocks = re.split(r"(?=\[Deep Fission 중요 변화 \|)", text)
    rendered = [format_one_alert(x.strip()) for x in blocks if x.strip()]
    return "\n\n".join(rendered).strip() + ("\n" if rendered else "")


def publish_compat_artifacts() -> None:
    if v3.PENDING.exists():
        shutil.copyfile(v3.PENDING, OLD_PENDING)

    if v3.ALERT.exists() and v3.ALERT.read_text(encoding="utf-8").strip():
        text = v3.ALERT.read_text(encoding="utf-8")
        OLD_ALERT.write_text(format_alert_korean(text), encoding="utf-8")
    else:
        OLD_ALERT.unlink(missing_ok=True)

    if v3.STATUS.exists():
        shutil.copyfile(v3.STATUS, OLD_STATUS)
    if v3.ERRORS.exists():
        shutil.copyfile(v3.ERRORS, OLD_ERRORS)
    else:
        OLD_ERRORS.unlink(missing_ok=True)


def main() -> int:
    prepare_state()
    install_parsons_guard()
    install_press_guard()
    rc = v3.main()
    publish_compat_artifacts()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
