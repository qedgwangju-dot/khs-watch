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
                if not role or not name:
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


def sectors_for(text: str) -> list[str]:
    checks = [
        ("경제안보/통상/공급망", ["경제안보", "관세", "공급망", "통상", "중동"]),
        ("해양수산/항만/북극항로", ["해양수산", "해수부", "북극항로", "항만", "해양수도"]),
        ("국가안보/방산", ["국가안보실", "국가안전보장회의", "자주국방", "군 구조", "육군"]),
        ("검찰개혁/사법", ["민정수석", "검찰", "중수청", "공소청", "법무부"]),
        ("보건복지/노동", ["사회수석", "보건의료", "노동", "약사"]),
        ("대통령실 정책 컨트롤타워", ["대통령비서실", "수석", "차장", "비서실"]),
    ]
    found = [label for label, terms in checks if any(term in text for term in terms)]
    return found or ["한국 대통령실/고위급 인사"]


def importance_for(text: str) -> str:
    high_terms = [
        "대통령비서실", "국가안보실", "경제안보", "수석비서관", "정책실장",
        "안보실장", "비서실장", "금융위원장", "공정거래위원장",
    ]
    return "상" if any(term in text for term in high_terms) else "중"


def render_personnel(idx: int, item: dict, now: dt.datetime) -> list[str]:
    body = fetch_article_body(item)
    text = f"{item.get('title', '')} {body}"
    pairs = extract_appointees(body)
    source = item.get("source") or "공식 출처"
    link = item.get("link") or ""
    published = item.get("published_kst") or "확인 불가"
    return [
        f"## {idx}. [{importance_for(text)}·확정] {item.get('title', '').strip()}",
        "- 상태 변화: 대통령실/청와대 공식 인사 임명 확인",
        f"- 인선/임명 대상: {format_appointees(pairs)}",
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
