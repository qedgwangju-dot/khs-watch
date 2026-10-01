#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import importlib.util
import json
import pathlib
import re
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "khs_us_investment_alert.html"
STATE = ROOT / "data" / "khs_us_investment_seen.json"
PENDING = ROOT / "out" / "khs_us_investment_pending_seen.json"
CORE_PATH = ROOT / "scripts" / "khs_us_investment_watch_core.py"
KST = ZoneInfo("Asia/Seoul")
FX = 1342.04


def _load_core():
    spec = importlib.util.spec_from_file_location("khs_us_investment_watch_core_finalize", CORE_PATH)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def _load_state() -> dict:
    for path in [PENDING, STATE]:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _parse_published(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        kst = parsed.astimezone(KST)
        now = dt.datetime.now(KST)
        age_min = max(0, int((now - kst).total_seconds() // 60))
        if age_min < 60:
            age = f"{age_min}분 전"
        elif age_min < 1440:
            age = f"{age_min // 60}시간 전"
        else:
            age = f"{age_min // 1440}일 전"
        return f"{kst.strftime('%m-%d %H:%M KST')} · {age}"
    except Exception:
        return ""


def _source_time(core, title: str, source: str, link: str, lookup_time: str) -> str:
    if core is not None:
        try:
            query_title = _clean(title).replace('"', " ")
            rows = core._rss(f'"{query_title}" when:7d')
            raw_link = html.unescape(link)
            exact = next((r for r in rows if str(r.get("link") or "") == raw_link), None)
            if exact is None:
                exact = next(
                    (
                        r for r in rows
                        if _clean(str(r.get("title") or "")) == _clean(title)
                        and _clean(str(r.get("source") or "")) == _clean(source)
                    ),
                    None,
                )
            if exact is not None:
                parsed = _parse_published(exact.get("published"))
                if parsed:
                    return parsed
        except Exception as exc:
            print(f"publication_time_lookup_failed={type(exc).__name__}")
    return f"{lookup_time} 조회" if lookup_time else "시각 확인 불가"


def _short_judgment(title: str, tags: str) -> str:
    blob = f"{title} {tags}".lower()
    if any(x in blob for x in ["사용후핵연료", "파이로", "pyroprocessing", "핵연료주기"]):
        return "미국의 신규 핵연료주기 투자 제안 보도. 정부 사업선정·투자금·사업주체·법규 검토 전까지 협의 단계."
    if "두산에너빌리티" in blob or "doosan" in blob:
        return "후보 수혜. Encinal 직접 수주·제조사 확정은 아직 아님."
    if "비에이치아이" in blob or "bhi" in blob:
        return "증권사 추정·후보 수혜. HRSG 실제 공급계약은 아직 미확정."
    if "송금절차" in blob or "45영업일" in blob or "송금" in blob:
        return "협의 진전 신호. 실제 송금일·금액 확정으로는 아직 승격하지 않음."
    if "공식정정/정부입장" in blob:
        return "정부 공식상태를 우선. 언론 선행보도와 확정 단계를 분리."
    if "ercot" in blob or "계통연계" in blob:
        return "신청량보다 승인·전원 인가·실제 가동 단계 상승을 우선."
    if "원전 프레임워크" in blob or "project power" in blob:
        return "한미 공동 팩트시트상 원전 8기 프레임워크 합의. AP1000 6기·APR1400 2기는 공식 프레임워크 수치지만 개별 부지·사업구조·일정은 후속 확정."
    if "원전" in blob:
        return "원전 관련 보도는 한미 공동 팩트시트의 프레임워크 범위와 개별 프로젝트 확정 수준을 구분."
    if "알래스카 lng" in blob or "project north" in blob:
        if "검토 착수" in blob or "project north" in blob:
            return "한미 공동 팩트시트상 Project North는 검토 착수 단계. 상업적 합리성·국내법 요건 충족 후 추진 여부를 결정하므로 한국의 투자 확정으로 표시하지 않음."
        if any(x in blob for x in ["540억", "54 billion", "발표예정", "발표 가능성", "발표 예상"]):
            return "미국측 540억달러 발표와 한미 공동 팩트시트의 검토 착수 수준을 분리. 한국 실제 투자 집행은 아직 별도 확정 필요."
        return "Project North 공식 상태·FID·금융종결·한국 실제 투자액 변화를 우선 추적."
    return "기사 반복이 아니라 사업 상태·금액·당사자·일정의 실제 변화만 추적."


def _change_area(text: str) -> str:
    marker = "<b>💰 대미투자 프로젝트 기준 사업비</b>"
    return text.split(marker, 1)[0] if marker in text else text


def _aggregate_flags(records: list[dict], text: str) -> dict[str, bool]:
    current = _change_area(text)
    blob = " ".join(f"{r['title']} {r['tags']}" for r in records).lower() + " " + current.lower()
    return {
        "pyro": any(x in blob for x in [
            "사용후핵연료·파이로 투자", "사용후핵연료", "파이로프로세싱", "pyroprocessing",
            "spent nuclear fuel", "핵연료주기", "fuel cycle",
        ]),
        "cap": any(x in blob for x in ["전략투자 한도 압박", "2천억달러", "200 billion", "한도 초과"]),
        "supply": any(x in blob for x in ["가스터빈·hrsg 공급망", "두산에너빌리티", "비에이치아이", "hrsg"]),
        "funding": any(x in blob for x in ["송금절차", "45영업일", "첫 투자금", "송금 임박", "조기송금"]),
        "energy": any(x in blob for x in ["대미투자 첫사업", "에너지 패키지", "1천억달러", "1000억달러", "2천억달러", "2000억달러", "200 billion", "원전 최대 8기"]),
        "ercot": any(x in blob for x in ["474gw", "batch zero", "ercot 신청", "계통연계"]),
        "encinal": any(x in blob for x in ["encinal", "엔시날", "6.3gw", "1.4gw", "4.9gw"]),
        "nuclear": "원전" in blob or "ap1000" in blob or "apr1400" in blob,
        "alaska": "알래스카 lng" in blob or "alaska lng" in blob,
    }


def _official_line(flags: dict[str, bool] | None = None) -> str:
    state = _load_state()
    if flags and (flags.get("alaska") or flags.get("energy")):
        states = state.get("event_states") or {}
        encinal_facts = {str(x) for x in ((states.get("encinal") or {}).get("facts") or [])}
        nuclear_facts = {str(x) for x in ((states.get("nuclear_build") or {}).get("facts") or [])}
        alaska_facts = {str(x) for x in ((states.get("alaska_lng") or {}).get("facts") or [])}
        if (
            "encinal_status:confirmed_first" in encinal_facts
            and "nuclear_framework_status:agreed" in nuclear_facts
            and "alaska_bilateral_status:review_started" in alaska_facts
        ):
            return "🏛 <b>한미 공동 팩트시트 확인 · Star 1호 확정 / Power 프레임워크 합의 / North 검토 착수</b>"
        package_facts = {str(x) for x in ((states.get("energy_package") or {}).get("facts") or [])}
        if "stage:발표실행" in alaska_facts or "stage:발표실행" in package_facts:
            return "🏛 <b>미국측 발표 확인 · 한국측 실제 집행확정 별도 관리</b>"
        if "stage:발표예정" in alaska_facts or "stage:발표예정" in package_facts:
            return "🏛 <b>미국측 발표 예정/확인 보도 · 한국측 집행확정 별도 관리</b>"
    status = (state.get("official_status") or {}).get("status")
    if status == "confirmed":
        return "🏛 <b>정부 공식단계 상승</b> · 최신 공식문서를 우선해 확정 상태를 갱신합니다."
    if status == "unconfirmed":
        return "🏛 <b>정부 공식상태: 미확정</b> · 첫 투자금·원전 세부·수익배분은 공식 확정 전입니다."
    return "🏛 <b>정부 공식확정 여부 별도 관리</b>"


def _current_state_block(flags: dict[str, bool]) -> list[str]:
    if not flags.get("nuclear"):
        return []

    state = _load_state()
    nuclear = ((state.get("event_states") or {}).get("nuclear_build") or {})
    facts = {str(x) for x in (nuclear.get("facts") or [])}

    def value(prefix: str) -> str:
        for fact in facts:
            if fact.startswith(prefix):
                return fact.split(":", 1)[1]
        return "미확인"

    total = value("nuclear_total_units:")
    ap1000 = value("ap1000_units:")
    apr1400 = value("apr1400_units:")

    if "nuclear_framework_status:agreed" in facts:
        return [
            "<b>📌 원전 공식 기준</b>",
            f"• 한미 공동 팩트시트: <b>원전 프레임워크 합의</b> · 전체 {html.escape(total)}기 = AP1000 {html.escape(ap1000)}기 + APR1400 {html.escape(apr1400)}기",
            "• 재원: <b>최대 1,200억달러</b> = 건설비 1,000억달러 + 예비비 200억달러",
            "• 다만 <b>개별 원전 부지·사업구조·건설일정은 아직 최종 확정이 아니며</b>, 각 사업별 상업적 합리성 검토·국회 절차 후 추진 여부 결정",
        ]

    official = "미확정" if "official_status:unconfirmed" in facts else (
        "공식확정" if "official_status:confirmed" in facts else "확인 중"
    )
    return [
        "<b>📌 현재 기준</b>",
        f"• 원전 구성: 전체 {html.escape(total)}기 · AP1000 {html.escape(ap1000)}기 · APR1400 {html.escape(apr1400)}기",
        f"• 정부 공식상태: <b>{official}</b>",
    ]


def _mandatory_project_block() -> list[str]:
    return [
        "<b>💰 대미투자 프로젝트 기준 사업비</b>",
        "",
        "🔥 <b>엔시날 가스복합발전</b>",
        "• 6.3GW · Reuters·이데일리 등 보도 기준 <b>223억달러 ≈ 29조9,275억원</b>",
        "• 산업통상부 9월 9일 설명자료가 인용한 한겨레 보도에는 <b>233억달러 ≈ 31조2,695억원</b>",
        "• <b>223억달러 ↔ 233억달러는 언론 보도 간 불일치이며 정부 확정액이 아님</b>",
        "└ GW당 단순환산: 223억달러 기준 <b>35.40억달러 ≈ 4조7,504억원</b> / 233억달러 기준 <b>36.98억달러 ≈ 4조9,634억원</b>",
        "",
        "⚛️ <b>미국 대형원전</b>",
        "• 최대 8기 · 기존 보도상 <b>1,200억달러 ≈ 161조448억원</b>",
        "└ 기당 <b>150억달러 ≈ 20조1,306억원</b>",
        "",
        "🧊 <b>알래스카 LNG</b>",
        "• 한국 협상 보도 기준 <b>670억달러 ≈ 89조9,167억원</b>",
        "",
        "📦 <b>3개 프로젝트 보도상 총사업비 단순합</b>",
        "• 223억달러+1,200억달러+670억달러 = <b>2,093억달러 ≈ 280조8,890억원</b>",
        "",
        "🟧 <b>WSJ 2026-09-10 에너지 패키지 신호</b>",
        "• 원전 최대 8기+텍사스 가스발전 포함 <b>1,000억달러 초과 ≈ 134조2,040억원 초과</b>",
        "• 이달 초기 집행 <b>20억달러 초과 ≈ 2조6,841억원 초과</b> 가능성 보도",
        "• 기존 별도 보도상 첫 송금 <b>22억달러+α ≈ 2조9,525억원+α</b>도 병행 추적",
        "• 전략투자 실제 납입 한도: <b>총 2,000억달러 ≈ 268조4,080억원 / 연 200억달러 ≈ 26조8,408억원</b>",
    ]


def _context_numbers(flags: dict[str, bool], records: list[dict]) -> list[str]:
    lines: list[str] = []
    titles = " ".join(r["title"].lower() for r in records)
    if flags["pyro"]:
        lines += [
            "• <b>신규 사업축</b>: 사용후핵연료 파이로프로세싱 투자 제안 보도 · 기존 원전 건설과 별도 추적",
            "• <b>전략투자 한도</b>: 총 2,000억달러 ≈ 268조4,080억원 · 연 200억달러 ≈ 26조8,408억원",
            "• 후보사업 총사업비 단순합이 2,000억달러를 넘는 것과 <b>실제 전략투자 집행액이 한도를 넘는 것은 다름</b>",
        ]
    if flags["supply"] or flags["encinal"]:
        lines.append("• Encinal <b>6.3GW = 1단계 1.4GW → 후속 4.9GW</b> · 가스터빈·HRSG 제조사 미확정")
    if "두산에너빌리티" in titles:
        lines.append("• 두산 기존 미국 계약 <b>380MW급 7기</b> · 2029년 5월부터 순차 공급 · Encinal과 별개")
    if "비에이치아이" in titles:
        lines.append("• 비에이치아이 HRSG <b>8~10기·4,000억~5,000억원</b>은 증권사 추정 · 확정 수주 아님")
    if flags["funding"]:
        lines.append("• 2025-11-14 MOU: 선정 통지 후 <b>최소 45영업일</b> · 자금요청 방식")
    if flags["ercot"]:
        lines.append("• ERCOT <b>474GW+</b>는 계통연계 요청량 · 승인·전원 인가·실제 가동과 구분")
    return lines[:5]


def _official_project_status_block() -> list[str]:
    return [
        "<b>🏛 한미 공동 팩트시트 공식 단계</b>",
        "• <b>Project Star</b>: 텍사스 엔시날 가스복합화력 <b>제1호 전략투자 공식 추진</b> · 총사업비 223억달러 · 6,472MW · 2029년 1단계 상업운전 · 2032년 전체 가동 목표",
        "• <b>Project Power</b>: 미국 대형원전 <b>8기 프레임워크 합의</b> · AP1000 6기 + APR1400 2기 · 최대 1,200억달러",
        "• <b>Project North</b>: 알래스카 LNG는 <b>투자 확정이 아니라 검토 착수</b> · 상업적 합리성 및 국내법 요건 충족 시 추진 여부 결정",
        "• 따라서 트럼프의 알래스카 투자 발표와 <b>한미 공동문서의 확정 수준은 구분</b>해서 추적",
        '<b>공식 원문</b> · <a href="https://www.korea.kr/briefing/pressReleaseView.do?newsId=156783865">산업통상부·정책브리핑 2026-10-01</a>',
    ]


def _alaska_kumkang_context() -> list[str]:
    state = _load_state()
    states = state.get("event_states") or {}
    alaska = states.get("alaska_lng") or {}
    package = states.get("energy_package") or {}
    facts = {str(x) for x in (alaska.get("facts") or [])}
    package_facts = {str(x) for x in (package.get("facts") or [])}
    announced = "stage:발표실행" in facts or "stage:발표실행" in package_facts
    bilateral_review = "alaska_bilateral_status:review_started" in facts
    if bilateral_review:
        status_lines = [
            "<b>🧊 알래스카 LNG 공식 단계</b>",
            "• 한미 공동 팩트시트: <b>Project North는 검토 착수</b> 단계이며 투자 확정이 아님",
            "• 추진 조건: <b>상업적 합리성 + 관련 국내법 요건 충족</b>",
            "• 트럼프는 한국 투자를 기정사실화해 발표했지만, 한국 정부 공식 문서는 검토 후 추진 여부를 결정한다고 명시",
        ]
    elif announced:
        status_lines = [
            "<b>🧊 9월 30일 미국측 발표 확인</b>",
            "• Reuters 2026-09-30: 트럼프가 한국의 <b>2,000억달러 미국 인프라·에너지 투자계획</b>을 공개했고 <b>알래스카 LNG 540억달러·대형원전 8기·텍사스 6GW 발전시설·807마일 가스관</b>을 포함한다고 보도",
            "• <b>미국측 발표 ≠ 한국의 즉시 집행 확정</b>: 한국측 실제 자금집행·사업성 검토·투자구조·FID·금융종결은 별도 확인",
        ]
    else:
        status_lines = [
            "<b>🧊 9월 30일 발표 예정/백악관 확인 보도</b>",
            "• Reuters·Bloomberg: 한국 대미투자 첫 사업군에 <b>알래스카 LNG 540억달러</b>가 포함될 수 있다고 보도",
            "• 한국 정부 9월22일 국회 보고 기준 알래스카 LNG는 <b>추후 협의 과제</b>였으므로 미국측 발표와 한국측 실제 집행을 분리 확인",
        ]
    return status_lines + [
        "• 한국 대미투자 약속: <b>전략투자 2,000억달러 + 조선협력 1,500억달러 = 총 3,500억달러</b>",
        "",
        "<b>🇰🇷 금강공업 강관 후보 추적</b>",
        "• 2026-09-28 데이터투자: API 5L <b>5L-0864</b> · HFW·PSL1 기준 최대 <b>X70</b> 인증범위 확인",
        "• <b>Alaska LNG 공급계약·벤더 승인·수주 확정은 아님</b> · 현재는 규격 연관성 기반 후보 단계",
        "• 금강공업 공식 공개 생산범위 <b>1/2~8인치 HFW</b> ↔ Phase One 주배관 <b>42인치·약 70만톤 API 5L X70</b>",
        "• Glenfarne 공식: Corinth Pipeworks+Europipe가 강관 약 <b>2/3 예비 공급</b> · POSCO International은 강관용 강재 일부 공급",
        "• 공개 API 인증서 표시 유효기간은 <b>2026-06-02까지</b> · 최신 API Active 상태 재확인 필요",
        "• 승격 조건: <b>API Active + vendor approval/공급계약 + 물량·규격·납기</b> 또는 32~42인치 대구경 생산·협력 구조 공식 확인",
        '• 근거: <a href="https://m.datatooza.com/article/202609281204524261e80ea65769_80">데이터투자</a> · <a href="https://www.kumkangkind.com/eng/company/network_eonyang.asp">금강공업 언양공장</a> · <a href="https://glenfarnegroup.com/glenfarne-announces-major-phase-one-alaska-lng-milestones-with-construction-line-pipe-supply-and-in-state-gas-agreements/">Glenfarne</a>',
    ]


def _next_checks(flags: dict[str, bool]) -> list[str]:
    checks: list[str] = []
    if flags["pyro"]:
        checks += [
            "미국 제안 주체·투자액·부지·처리규모",
            "한국 투자주체·2,000억달러 한도 내 배분 또는 별도 민간자금 여부",
            "한미 원자력협정·미국 동의·비확산·인허가 조건",
            "실증→상용 일정·본계약·국내기업 실명 참여",
        ]
    if flags["supply"] or flags["encinal"]:
        checks += ["제조사 실명·구매주문(PO)·실제 기수·납기", "AI 고객 실명·PPA·4.9GW 후속 승인"]
    if flags["funding"]:
        checks += ["사업 선정일·한국 통보일·자금요청·실제 송금일/금액"]
    if flags["nuclear"] and not flags["pyro"]:
        checks += ["원전 부지·노형·기수·발주주체·본계약"]
    if flags["ercot"]:
        checks += ["계통연계 승인·전원 인가·실제 가동"]
    if flags["alaska"]:
        checks += [
            "백악관·한국 정부 540억달러 공식 발표 여부·투자구조·집행주체",
            "SPA·FID·금융종결·한국 투자액",
            "금강공업 API Active·vendor approval/공급계약·대구경 생산/협력 여부",
        ]
    out: list[str] = []
    for item in checks:
        if item not in out:
            out.append(item)
    return out[:4]


def _compact_generic(text: str, core, lookup_time: str) -> str | None:
    article_re = re.compile(
        r"(?P<title><b>\d+\.\s+.*?</b>)\n"
        r"(?P<class>• 🟧 <b>구분:\s*(?P<tags>.*?)</b>)\n"
        r"• 의미:\s*(?P<meaning>.*?)\n"
        r"• 출처:\s*<a href=\"(?P<link>[^\"]+)\">(?P<source>.*?)</a>",
        re.S,
    )
    matches = list(article_re.finditer(text))
    if not matches:
        return None

    records: list[dict] = []
    for m in matches[:3]:
        records.append({
            "title": _clean(m.group("title")),
            "tags": _clean(m.group("tags")),
            "link": m.group("link"),
            "source": _clean(m.group("source")),
        })

    flags = _aggregate_flags(records, text)
    if flags["pyro"]:
        title = "🇺🇸 대미투자 | 사용후핵연료·파이로 신규 제안"
    elif flags["supply"] and flags["funding"]:
        title = "🇺🇸 대미투자 | 공급망·송금 변화"
    elif flags["supply"]:
        title = "🇺🇸 대미투자 | 가스터빈·HRSG 공급망"
    elif flags["funding"]:
        title = "🇺🇸 대미투자 | 송금·45영업일"
    elif flags["energy"]:
        title = "🇺🇸 대미투자 | 첫사업·에너지 패키지"
    elif flags["ercot"]:
        title = "🇺🇸 대미투자 | 텍사스 AI 전력"
    else:
        first = text.splitlines()[0] if text.splitlines() else "🇺🇸 대미투자 | 중요 변화"
        title = _clean(first).replace(" | 중요 업데이트", "").replace(" | 최상위 중요 업데이트", "")

    parts = [f"<b>{title}</b>", "", _official_line(flags), "", "<b>🟧 이번 신규 변화</b>"]
    for idx, r in enumerate(records, 1):
        timestamp = _source_time(core, r["title"], r["source"], r["link"], lookup_time)
        title_text = re.sub(r"^\d+\.\s*", "", r["title"])
        parts += [
            f'<b>{idx}. <a href="{html.escape(r["link"], quote=True)}">{html.escape(title_text)}</a></b>',
            f"• 판정: {_short_judgment(r['title'], r['tags'])}",
            f"• {html.escape(r['source'])} · {timestamp}",
            "",
        ]

    context = _context_numbers(flags, records)
    if context:
        parts += ["<b>📌 이번 변화 핵심</b>"] + context + [""]

    if flags["energy"] or flags["alaska"]:
        parts += _official_project_status_block() + [""]
    if flags["alaska"]:
        parts += _alaska_kumkang_context() + [""]

    baseline = _current_state_block(flags)
    if baseline:
        parts += baseline + [""]

    checks = _next_checks(flags)
    if checks:
        parts += ["<b>다음 확인</b>"] + [f"• {html.escape(x)}" for x in checks] + [""]

    if flags["pyro"]:
        parts += [
            '<b>공식 기준</b> · <a href="https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/171196/view">전략투자 MOU: 총 2,000억달러·연 200억달러</a> · <a href="https://www.motir.go.kr/kor/article/ATCLe0854704d/172177/view">산업통상부: 전략적 투자가 2,000억달러를 초과한다는 것은 사실이 아님</a>',
            "",
        ]
    elif flags["funding"] or flags["energy"] or flags["alaska"]:
        parts += [
            '<b>공식 기준</b> · <a href="https://www.korea.kr/briefing/pressReleaseView.do?newsId=156783865">2026-10-01 한미 전략투자 공동 팩트시트</a> · <a href="https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/171196/view">2025-11-14 전략적 투자 MOU</a>',
            "",
        ]
    if flags["supply"]:
        parts += [
            '<b>공급망 원천</b> · <a href="https://www.doosanenerbility.com/kr/about/news_board_view?id=21000800&page=0&pageSize=9">두산 미국 가스터빈 7기 공식</a>',
            "",
        ]

    if lookup_time:
        parts.append(f"조회 {lookup_time} · 새 변화 중심 · 핵심 사업비 블록은 고정 표시")

    return "\n".join(parts).strip() + "\n"


def _compact_energy_package(text: str, lookup_time: str) -> str | None:
    if "대미투자 첫사업·에너지 패키지" not in text:
        return None
    flags = _aggregate_flags([], text)
    parts = [
        "<b>🇺🇸 대미투자 | 첫사업·에너지 패키지</b>",
        "",
        _official_line(flags),
        "",
        "<b>🟧 공식 단계</b>",
        "• Project Star: <b>텍사스 엔시날 제1호 공식 추진</b> · 223억달러 · 6,472MW",
        "• Project Power: <b>원전 8기 프레임워크 합의</b> · AP1000 6기 + APR1400 2기 · 최대 1,200억달러",
        "• Project North: <b>알래스카 LNG 검토 착수</b> · 상업적 합리성·국내법 요건 충족 시 추진 여부 결정",
        "",
    ]
    baseline = _current_state_block(flags)
    if baseline:
        parts += baseline + [""]
    parts += [
        "<b>다음 확인</b>",
        "• 정부 공식 첫 사업 선정·투자금·지분·수익배분",
        "• 원전 부지·노형·기수·발주주체",
        "• 실제 선정 통지일·자금요청·송금일/금액",
        "",
        '<b>출처</b> · <a href="https://www.korea.kr/briefing/pressReleaseView.do?newsId=156783865">산업통상부·정책브리핑 공동 팩트시트</a> · <a href="https://www.reuters.com/legal/government/trump-expected-announce-54-billion-south-korea-investment-alaska-lng-sources-say-2026-09-30/">Reuters</a>',
    ]
    if lookup_time:
        parts += ["", f"조회 {lookup_time} · 새 변화 중심 · 핵심 사업비 블록은 고정 표시"]
    return "\n".join(parts).strip() + "\n"


def _visible_len(text: str) -> int:
    return len(_clean(text.replace("\n", " ")))


def main() -> int:
    if not ALERT.exists():
        print("finalize_alert=none")
        return 0

    text = ALERT.read_text(encoding="utf-8")
    footer = re.search(r"^조회\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+KST)", text, re.M)
    lookup_time = footer.group(1) if footer else dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    core = _load_core()

    compact = _compact_generic(text, core, lookup_time)
    if compact is None:
        compact = _compact_energy_package(text, lookup_time)
    if compact is None:
        lines = [line for line in text.splitlines() if line.strip()]
        compact = "\n".join(lines[:18]) + "\n"

    if _visible_len(compact) > 3900:
        raise RuntimeError(f"compact alert still too long: {_visible_len(compact)}")

    ALERT.write_text(compact, encoding="utf-8")
    print(f"final_alert_compacted=true visible_chars={_visible_len(compact)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
