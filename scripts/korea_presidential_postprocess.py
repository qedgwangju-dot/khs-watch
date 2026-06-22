#!/usr/bin/env python3
"""Normalize Korean presidential personnel alerts for Telegram/GitHub output."""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")
REPORT_PATH = OUT_DIR / "khs_policy_watch.md"
ALERT_PATH = OUT_DIR / "khs_policy_watch_alert.md"
TITLE_PATH = OUT_DIR / "khs_policy_watch_alert_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"

ROLE_TAIL = (
    "비서실장|정책실장|안보실장|수석비서관|수석|대변인|차장|"
    "장관 후보자|장관|차관|위원장|검찰총장|국세청장|관세청장|금융감독원장|사무처장"
)
INVALID_NAME_CANDIDATES = {"국민", "정부", "이번", "오늘", "모두", "해당", "신임"}

SECTOR_RULES: list[tuple[str, list[str]]] = [
    ("금융/자본시장/가계부채", ["금융위원장", "금융감독원장", "금감원장", "금융위원회", "금융감독원", "금감원", "기재부 금융", "자본시장", "가계부채", "부동산 PF", "PF", "은행", "증권", "보험"]),
    ("공정거래/플랫폼/유통", ["공정거래위원장", "공정거래위원회", "공정위", "플랫폼 규제", "대기업집단", "온라인 플랫폼", "가맹", "유통", "하도급"]),
    ("산업정책/반도체/AI", ["산업부", "산업통상자원부", "과기정통부", "과학기술정보통신부", "AI", "인공지능", "반도체", "첨단전략산업", "데이터센터", "국가전략기술", "R&D"]),
    ("에너지/전력망/원전", ["에너지", "전력망", "원전", "원자력", "전기요금", "LNG", "가스", "재생에너지", "송전", "배전", "전력기기"]),
    ("국토/부동산/건설", ["국토부", "국토교통부", "주택공급", "부동산", "재개발", "재건축", "SOC", "철도", "공항", "건설", "교통", "인프라"]),
    ("재정/예산/세제", ["기재부", "기획재정부", "예산실", "세제실", "추경", "법인세", "상속세", "조세특례", "국고", "재정", "세제", "예산"]),
    ("외교/통상/대중·대미", ["외교부", "통상교섭", "관세", "수출통제", "한미", "한중", "대만", "중동", "공급망", "경제안보", "통상", "대중", "대미"]),
    ("디지털/사이버/개인정보", ["개인정보위", "개인정보보호위원회", "방통위", "방송통신위원회", "사이버안보", "사이버", "클라우드", "망 이용대가", "데이터 규제", "디지털"]),
    ("바이오/보건의료", ["복지부", "보건복지부", "식약처", "식품의약품안전처", "의약품", "건강보험", "의료개혁", "병원", "약가", "임상", "보건의료"]),
    ("노동/연금/복지", ["고용부", "고용노동부", "노조", "최저임금", "근로시간", "국민연금", "연금", "복지 재정", "노동"]),
    ("교육/AI인재/R&D", ["교육부", "AI인재", "인재양성", "대학", "교육개혁", "R&D", "연구개발", "과학기술"]),
    ("환경/탄소/배출권", ["환경부", "탄소", "배출권", "온실가스", "기후", "환경규제", "ESG"]),
    ("방송통신/미디어", ["방통위", "방송통신", "미디어", "방송", "통신", "콘텐츠 심의", "OTT"]),
    ("농식품/방역", ["농식품부", "농림축산식품부", "농업", "식품", "방역", "축산", "쌀"]),
    ("재난안전/치안", ["행안부", "행정안전부", "재난", "안전", "치안", "경찰", "소방"]),
    ("문화콘텐츠/관광", ["문체부", "문화체육관광부", "문화", "콘텐츠", "관광", "K컬처", "게임"]),
    ("북한/통일/대북정책", ["통일부", "북한", "대북", "남북", "통일", "비핵화"]),
    ("지방균형/지역개발/재개발", ["지방균형", "균형발전", "지역개발", "재개발", "지방시대", "혁신도시"]),
    ("해양수산/항만/북극항로", ["해양수산", "해수부", "북극항로", "항만", "해양수도", "수산", "해운"]),
    ("국가안보/방산", ["국가안보실", "국가안전보장회의", "자주국방", "군 구조", "육군", "방산", "국방"]),
    ("검찰개혁/사법", ["민정수석", "검찰", "중수청", "공소청", "법무부", "사법", "수사"]),
    ("대통령실 정책 컨트롤타워", ["대통령비서실", "대통령실", "수석", "차장", "비서실", "정책실장", "비서실장"]),
]

POLICY_COLOR_RULES: list[tuple[str, list[str]]] = [
    ("금융규제·자본시장 관리 색채", ["금융위원장", "금융감독원장", "금감원", "자본시장", "가계부채", "부동산 PF", "은행", "증권", "보험"]),
    ("공정거래·플랫폼 규제 색채", ["공정거래위원장", "공정위", "대기업집단", "온라인 플랫폼", "가맹", "유통", "하도급"]),
    ("산업정책·첨단기술 드라이브", ["산업부", "과기정통부", "반도체", "AI", "첨단전략산업", "데이터센터", "국가전략기술"]),
    ("에너지 안보·전력 인프라 색채", ["에너지", "전력망", "원전", "전기요금", "LNG", "재생에너지"]),
    ("주택공급·SOC·건설 정책 색채", ["국토부", "주택공급", "부동산", "SOC", "철도", "공항", "건설", "재개발"]),
    ("재정집행·세제 개편 색채", ["기재부", "예산실", "세제실", "추경", "법인세", "상속세", "조세특례", "재정"]),
    ("외교통상·공급망 재편 색채", ["외교부", "통상교섭", "관세", "수출통제", "한미", "한중", "중동", "경제안보", "공급망"]),
    ("디지털 규제·사이버안보 색채", ["개인정보위", "방통위", "사이버안보", "클라우드", "망 이용대가", "데이터 규제"]),
    ("의료개혁·약가·보건재정 색채", ["복지부", "식약처", "의약품", "건강보험", "의료개혁", "약가", "임상"]),
    ("노동시장·연금개혁 색채", ["고용부", "노조", "최저임금", "근로시간", "국민연금", "연금"]),
    ("교육·인재·R&D 색채", ["교육부", "AI인재", "인재양성", "R&D", "연구개발"]),
    ("탄소·환경규제 색채", ["환경부", "탄소", "배출권", "온실가스", "기후"]),
    ("방송통신·미디어 규제 색채", ["방통위", "방송통신", "미디어", "OTT"]),
    ("농식품·방역 정책 색채", ["농식품부", "농림축산식품부", "방역", "농업", "축산"]),
    ("재난안전·치안 색채", ["행안부", "재난", "안전", "치안", "경찰", "소방"]),
    ("문화콘텐츠·관광 색채", ["문체부", "문화", "콘텐츠", "관광", "게임"]),
    ("대북·통일정책 색채", ["통일부", "북한", "대북", "남북", "통일"]),
    ("지방균형·지역개발 색채", ["지방균형", "균형발전", "지역개발", "재개발", "지방시대"]),
    ("해양수산·북극항로 추진 색채", ["해양수산", "해수부", "북극항로", "항만", "해양수도", "수산", "해운"]),
    ("안보·방산 컨트롤타워 색채", ["국가안보실", "국가안전보장회의", "자주국방", "군 구조", "방산", "국방"]),
    ("검찰·사법개혁 색채", ["민정수석", "검찰", "중수청", "공소청", "법무부", "사법"]),
    ("대통령실 정책 컨트롤타워 색채", ["대통령비서실", "대통령실", "정책실장", "비서실장", "수석비서관"]),
]


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def base_title(title: str) -> str:
    return re.sub(r"\s+20\d{2}[.]\d{1,2}[.]\d{1,2}$", "", title).strip()


def fetch_article_body(item: dict) -> str:
    fallback = clean_text(item.get("summary") or item.get("title") or "")
    link = item.get("link") or ""
    if not link.startswith("http"):
        return fallback[:900]
    try:
        req = urllib.request.Request(link, headers={"User-Agent": "KHS-policy-watch contact=github-actions"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
    except Exception:
        return fallback[:900]

    plain = clean_text(raw)
    title = base_title(item.get("title") or "")
    if title and title in plain:
        plain = plain.split(title, 1)[1]
    starts = [idx for marker in ("이재명 대통령은", "대통령은 오늘", "정부는 오늘") if (idx := plain.find(marker)) >= 0]
    if starts:
        plain = plain[min(starts):]
    for marker in ("<자료출처", "자료출처=", "저작권정책", "이전다음기사 영역", "관련기사", "정책 NOW"):
        cut = plain.find(marker)
        if cut > 0:
            plain = plain[:cut]
    return clean_text(plain or fallback)[:1400]


def is_personnel(item: dict) -> bool:
    return "korea_presidential_personnel" in (item.get("matched") or {})


def clean_role(role: str) -> str:
    role = clean_text(role)
    role = re.sub(r"^(?:이재명 대통령은 오늘|대통령은 오늘|정부는 오늘)[, ]*", "", role)
    role = re.sub(r"^먼저[, ]*", "", role)
    role = re.sub(r"^신임\s+", "", role)
    role = re.sub(r"^에는?\s*", "", role)
    role = role.strip(" ,·")
    return role


def extract_presenter(title: str) -> str:
    clean = base_title(title)
    match = re.search(r"관련\s+(?P<name>[가-힣]{2,4})\s+(?P<role>[^\s]+(?:\s*[^\s]+)?)(?:\s+서면)?\s+브리핑", clean)
    if not match:
        return "확인 불가"
    name = match.group("name")
    role = clean_text(match.group("role"))
    return f"{name} {role} 브리핑"


def extract_appointees(text: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    patterns = [
        re.compile(rf"(?P<role>[^.。\n]{{0,70}}?(?:{ROLE_TAIL}))(?:에|에는)\s+(?P<name>[가-힣]{{2,4}})\s+(?:前|전|現|현)?[^.。\n]{{0,90}}?(?:임명|지명|내정)"),
        re.compile(r"(?P<role>국가안보실\s*제\d차장(?:\s*겸\s*[^.。\n]{1,45}?사무처장)?)은\s+(?P<name>[가-힣]{2,4})\s+[^.。\n]{0,90}?(?:입니다|임명)"),
        re.compile(r"(?P<role>제\d차장)은\s+(?P<name>[가-힣]{2,4})\s+[^.。\n]{0,90}?(?:입니다|임명)"),
    ]
    for sentence in re.split(r"(?<=[.。])\s+", text):
        for pattern in patterns:
            for match in pattern.finditer(sentence):
                role = clean_role(match.group("role"))
                name = match.group("name")
                if not role or not name or name in INVALID_NAME_CANDIDATES:
                    continue
                pair = (role, name)
                if pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)
    return pairs


def format_appointees(pairs: list[tuple[str, str]]) -> str:
    if not pairs:
        return "확인 불가(원문 직접 확인 필요)"
    return "; ".join(f"{role} - {name}" for role, name in pairs)


def matched_labels(text: str, rules: list[tuple[str, list[str]]], fallback: str) -> list[str]:
    found = [label for label, terms in rules if any(term in text for term in terms)]
    return found or [fallback]


def sectors_for(text: str) -> list[str]:
    return matched_labels(text, SECTOR_RULES, "한국 대통령실/고위급 인사")


def policy_color_for(text: str, presenter: str) -> str:
    labels = matched_labels(text, POLICY_COLOR_RULES, "정책 색깔 확인 불가(원문 후속 정책 필요)")
    if presenter != "확인 불가":
        labels.append(f"발표 라인: {presenter}")
    return "; ".join(dict.fromkeys(labels))


def importance_for(text: str) -> str:
    high_terms = [
        "대통령비서실", "국가안보실", "경제안보", "수석비서관", "정책실장",
        "안보실장", "비서실장", "금융위원장", "공정거래위원장", "금융감독원장",
        "국토교통부", "기획재정부", "산업통상자원부", "과학기술정보통신부",
    ]
    return "상" if any(term in text for term in high_terms) else "중"


def render_personnel(idx: int, item: dict, now: dt.datetime) -> list[str]:
    body = fetch_article_body(item)
    title = item.get("title", "")
    text = f"{title} {body}"
    pairs = extract_appointees(body)
    presenter = extract_presenter(title)
    source = item.get("source") or "공식 출처"
    link = item.get("link") or ""
    published = item.get("published_kst") or "확인 불가"
    return [
        f"## {idx}. [{importance_for(text)}·확정] {title.strip()}",
        "- 상태 변화: 대통령실/청와대 공식 인사 임명 확인",
        f"- 인선/임명 대상: {format_appointees(pairs)}",
        f"- 발표/라인: {presenter}",
        f"- 정책 색깔/이력 힌트: {policy_color_for(text, presenter)}",
        f"- 원문/출처: [{source}]({link}) · 원천시각 {published} · 조회 {now:%H:%M KST}",
        "- 한국장 영향: 시간표",
        "- 영향 경로: 정책 인선, 정책 타임라인",
        f"- 영향 섹터: {', '.join(sectors_for(text))}",
        "- 반영 가능성: 중간. 공식 인사 발표라 정보 자체는 공개 반영됐을 수 있지만, 개별 섹터 영향은 후속 정책·업무지시 전까지 제한적입니다.",
        "- 반대 근거: 인선 자체는 확정이나 매출·마진·할인율을 직접 바꾸는 정책 발표는 아직 아닙니다.",
        "- 즉시 체크: 취임 직후 업무지시, 부처 정책 발표 일정, 예산·입법·규제 후속 조치",
        f"- 핵심 근거: {body[:260]}",
        "",
    ]


def render_general(idx: int, item: dict, now: dt.datetime) -> list[str]:
    matched_terms = sorted({term for terms in (item.get("matched") or {}).values() for term in terms})
    matched_keys = ", ".join((item.get("matched") or {}).keys()) or "정책/규제"
    return [
        f"## {idx}. [{item.get('importance', '중')}·{item.get('status', '확정')}] {item.get('title', '').strip()}",
        f"- 상태 변화: {matched_keys} 신호 확인 ({', '.join(matched_terms[:8])})",
        f"- 원문/출처: [{item.get('source', 'source')}]({item.get('link', '')}) · 원천시각 {item.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}",
        f"- 한국장 영향: {', '.join(item.get('impacts') or ['의사결정 영향 제한적'])}",
        f"- 영향 경로: {', '.join(item.get('paths') or ['정책 타임라인'])}",
        f"- 영향 섹터: {', '.join(item.get('sectors') or ['정책/규제 일반'])}",
        "- 반영 가능성: 낮음~중간. 공식 원문/신뢰 소스 확인 후 한국장 확산 여부를 장전 레이더에서 재확인해야 합니다.",
        "- 반대 근거: 제목·요약 기반 1차 감시라 원문 세부 조건, 시행일, 예외 조항, 개별 프로젝트 적용 여부 확인이 필요합니다.",
        "- 즉시 체크: 원문 전문, 시행일/마감일, 한국 밸류체인 노출, 관련 해외 티커·ETF 반응",
        "",
    ]


def add_coverage_line(path: Path) -> None:
    if not path.exists():
        return
    body = path.read_text(encoding="utf-8")
    if "대통령실/청와대 고위급 인사 브리핑:" in body:
        return
    checks = []
    for label, pattern in [
        ("대통령실", r"- Korea President briefings: ([^\n]+)"),
        ("정책브리핑", r"- Korea Policy Briefing presidential briefings: ([^\n]+)"),
    ]:
        match = re.search(pattern, body)
        checks.append(f"{label} {match.group(1).strip()}" if match else f"{label} 확인 불가")
    line = "대통령실/청와대 고위급 인사 브리핑: " + ", ".join(checks)
    lines = body.splitlines()
    if lines and lines[0].startswith("🚨"):
        lines.insert(1, line)
        if len(lines) == 2 or lines[2] != "":
            lines.insert(2, "")
    else:
        lines.insert(0, line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    now = dt.datetime.now(tz=KST)
    if not ALERTS_JSON_PATH.exists():
        add_coverage_line(REPORT_PATH)
        add_coverage_line(ALERT_PATH)
        return 0
    try:
        alerts = json.loads(ALERTS_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        add_coverage_line(REPORT_PATH)
        add_coverage_line(ALERT_PATH)
        return 0

    personnel_count = sum(1 for item in alerts if is_personnel(item))
    if personnel_count == 0:
        add_coverage_line(REPORT_PATH)
        add_coverage_line(ALERT_PATH)
        return 0

    lines = [
        f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}",
        f"대통령실/청와대 고위급 인사 브리핑: 공식 인사 {personnel_count}건 확인",
        "",
    ]
    for idx, item in enumerate(alerts, 1):
        lines.extend(render_personnel(idx, item, now) if is_personnel(item) else render_general(idx, item, now))
    lines.extend([
        "💡 워치 판단: 이번 실행의 대통령실/청와대 인사 신호는 돈 버는 능력이나 할인율보다 정책 인선과 시간표를 바꾸는 재료입니다. 실제 투자 재료화 여부는 후속 업무지시·정책 발표·예산/입법 일정에서 재확인해야 합니다.",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ])
    normalized = "\n".join(lines) + "\n"
    REPORT_PATH.write_text(normalized, encoding="utf-8")
    ALERT_PATH.write_text(normalized, encoding="utf-8")
    TITLE_PATH.write_text(f"KHS 정책 워치: 대통령실/청와대 고위급 인사 {personnel_count}건 확인\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
