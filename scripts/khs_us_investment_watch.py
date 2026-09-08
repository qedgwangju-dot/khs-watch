#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
STATE = DATA / "khs_us_investment_seen.json"
PENDING = OUT / "khs_us_investment_pending_seen.json"
ALERT = OUT / "khs_us_investment_alert.html"
KST = ZoneInfo("Asia/Seoul")

QUERIES = [
    '"대미투자" 엔시날 when:3d',
    '"한미전략투자" I-SPV OR SPV when:3d',
    '"대미투자" PPA OR EPC OR 가스터빈 when:3d',
    '"대미투자" 반도체 OR 삼성전자 OR SK하이닉스 when:3d',
    '"대미투자" 원전 OR AP1000 OR APR1400 when:3d',
    '"대미투자" "알래스카 LNG" when:3d',
    '"대미투자" 관세 OR 301조 OR 232조 when:3d',
]
TRUSTED = ["산업통상", "연합뉴스", "뉴시스", "뉴스1", "이데일리", "헤럴드경제", "한국경제", "중앙일보", "Reuters"]
MATERIAL = ["확정", "의결", "합의", "계약", "체결", "승인", "증액", "감액", "사업비", "I-SPV", "PPA", "EPC", "가스터빈", "수주", "반도체", "원전", "LNG", "관세", "301조", "232조", "제외", "포함"]


def _load() -> dict:
    if not STATE.exists():
        return {"bootstrap": False, "seen": {}}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"bootstrap": False, "seen": {}}


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 KHS-US-Investment-Watch"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _rss(query: str) -> list[dict]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    root = ET.fromstring(_fetch(url))
    rows = []
    for node in root.findall(".//item"):
        title = html.unescape(re.sub(r"\s+", " ", node.findtext("title") or "")).strip()
        source = (node.findtext("source") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = node.findtext("pubDate") or ""
        try:
            published = email.utils.parsedate_to_datetime(pub)
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except Exception:
            published = dt.datetime.now(dt.timezone.utc)
        blob = f"{title} {source}"
        if not any(x.lower() in blob.lower() for x in TRUSTED):
            continue
        if not any(x.lower() in blob.lower() for x in MATERIAL):
            continue
        rows.append({"title": title, "source": source or "신뢰자료", "link": link, "published": published.isoformat()})
    return rows


def _key(row: dict) -> str:
    raw = f"{row['title']}|{row['link']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _tags(title: str) -> list[str]:
    low = title.lower()
    out = []
    for tag, terms in [
        ("1호/엔시날", ["엔시날", "1호"]),
        ("투자구조", ["i-spv", "spv", "지분", "소유권", "의결권"]),
        ("PPA/전력판매", ["ppa", "전력판매"]),
        ("한국기업 수주", ["epc", "가스터빈", "수주"]),
        ("반도체", ["반도체", "삼성전자", "sk하이닉스"]),
        ("원전", ["원전", "ap1000", "apr1400"]),
        ("알래스카 LNG", ["알래스카", "lng"]),
        ("관세", ["301조", "232조", "관세"]),
        ("사업비", ["사업비", "증액", "감액"]),
    ]:
        if any(t in low for t in terms):
            out.append(tag)
    return out or ["대미투자"]


def _meaning(tags: list[str]) -> str:
    if "투자구조" in tags:
        return "지분·의결권·손실분담이 실제 투자 회수액과 위험을 바꿉니다."
    if "PPA/전력판매" in tags:
        return "계약 GW·기간·가격이 잠기면 발전소 현금흐름을 계산할 수 있습니다."
    if "한국기업 수주" in tags:
        return "본계약부터 국내 기업의 수주잔고·매출로 연결됩니다."
    if "반도체" in tags:
        return "미국 팹이 구체화되면 관세우대와 국내 설비투자 분산을 함께 봐야 합니다."
    if "원전" in tags:
        return "노형·사업 주도권에 따라 한국의 시공·기자재·운영 몫이 달라집니다."
    if "알래스카 LNG" in tags:
        return "장기구매계약·세제·금융종결이 실제 착공을 결정합니다."
    if "관세" in tags:
        return "관세 변화는 한국 수출기업의 마진과 할인율을 직접 바꿉니다."
    if "사업비" in tags:
        return "사업비가 늘면 투자수익률과 초과비용 부담이 핵심이 됩니다."
    return "프로젝트 확정도와 집행 시간표가 한 단계 바뀐 신호입니다."


def _fixed_project_cost_block() -> list[str]:
    return [
        "<b>💰 대미투자 프로젝트 기준 사업비</b>",
        "",
        "🔥 <b>엔시날 가스복합발전</b>",
        "• 6.3GW · <b>223억달러</b>",
        "└ GW당 <b>35.40억달러 ≈ 4조7,630억원</b>",
        "",
        "⚛️ <b>미국 대형원전</b>",
        "• 8기 · <b>1,200억달러</b>",
        "└ 기당 <b>150억달러 ≈ 20조1,840억원</b>",
        "",
        "🧊 <b>알래스카 LNG</b>",
        "• <b>670억달러 ≈ 90조1,552억원</b>",
        "",
        "📦 <b>3개 프로젝트 합계</b>",
        "• <b>2,093억달러 ≈ 281조6,341억원</b>",
        "",
        "<b>⚠️ 꼭 구분할 숫자</b>",
        "• 첫 송금: <b>22억달러+α ≈ 2조9,603억원+α</b>",
        "• 엔시날 총사업비 223억달러의 <b>약 9.9%</b>",
        "• 첫 송금 전액이 엔시날에 들어간다는 의미는 아님",
        "• 3개 후보사업 총액은 전략투자 2,000억달러보다 <b>93억달러 ≈ 12조5,141억원</b> 큼",
        "└ 총사업비와 한국 정부 실제 투자액은 다를 수 있어 미국 측·민간·PF 자금 비중 확인 필요",
        "",
        "<i>원화 환산 기준: 1달러=1,345.6원 · 2026-09-08 15:30</i>",
    ]


def _bootstrap(now: dt.datetime) -> str:
    parts = [
        "<b>🇺🇸 대미투자 | 텍사스 엔시날 1호 확정 보도</b>",
        "",
        "<b>무엇이 바뀌었나</b>",
        "• 대미투자 첫 사업으로 <b>텍사스 엔시날 6.3GW 가스복합발전</b>이 확정됐다는 보도가 나왔습니다.",
        "• 현재 협상안 총사업비는 <b>223억달러</b>. 미국의 250억달러 요구 뒤 223억달러에서 타협한 것으로 전해졌습니다.",
        "• <b>삼성전자·SK하이닉스 미국 메모리 팹은 이번 프로젝트에서 제외</b>되고 별도 FDI로 다뤄지는 것으로 보도됐습니다.",
        "",
        "<b>사업 구조</b>",
        "• 1단계 발전을 먼저 가동한 뒤 복합화력을 순차 확대해 선투자 위험을 낮추는 방식입니다.",
        "• 전력은 ERCOT 판매 또는 인근 AI 데이터센터 장기 PPA·오프그리드 직접공급을 검토합니다.",
        "",
        "<b>지금 가장 중요한 것</b>",
        "• I-SPV: 지분·의결권·수익배분·추가 공사비·손실분담",
        "• PPA: 고객 실명·계약 GW·기간·전력가격",
        "• 한국 기업: EPC·가스터빈 본계약과 금액·대수",
        "",
        "<b>후속 사업</b>",
        "• 미국 대형원전과 Alaska LNG는 이번 1호에서 빠지고 별도 검토합니다.",
        "• 반도체 투자 요구가 2,000억달러 패키지에 포함되는지도 계속 확인합니다.",
        "",
    ]
    parts += _fixed_project_cost_block()
    parts += [
        "",
        "<b>다음 확인</b>",
        "1) 정부 최종 발표  2) I-SPV 원문  3) PPA  4) EPC·가스터빈 본계약  5) 추가 증액 여부",
        "",
        '<b>출처</b> · <a href="https://biz.heraldcorp.com/article/10864870">헤럴드경제</a> · <a href="https://www.edaily.co.kr/News/Read?newsId=02499366645577824&mediaCodeNo=257">이데일리</a>',
        f"<i>조회 {now.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')} · 공식 최종문서가 나오면 공식 확정으로 갱신</i>",
    ]
    return "\n".join(parts)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    if ALERT.exists():
        ALERT.unlink()
    state = _load()
    now = dt.datetime.now(dt.timezone.utc)
    if not state.get("bootstrap"):
        ALERT.write_text(_bootstrap(now) + "\n", encoding="utf-8")
        state["bootstrap"] = True
        PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("bootstrap_alert=true")
        return 0

    seen = state.setdefault("seen", {})
    rows = []
    for q in QUERIES:
        try:
            rows.extend(_rss(q))
        except Exception as exc:
            print(f"rss_error={type(exc).__name__}")
    rows.sort(key=lambda r: r["published"], reverse=True)
    fresh = []
    for row in rows:
        key = _key(row)
        if key in seen:
            continue
        seen[key] = now.isoformat()
        fresh.append(row)
        if len(fresh) >= 5:
            break
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not fresh:
        print("new_alerts=0")
        return 0

    parts = ["<b>🇺🇸 대미투자 | 중요 업데이트</b>", ""]
    for idx, row in enumerate(fresh, 1):
        tags = _tags(row["title"])
        parts += [
            f"<b>{idx}. {html.escape(row['title'])}</b>",
            f"• 구분: {' / '.join(html.escape(x) for x in tags[:3])}",
            f"• 의미: {html.escape(_meaning(tags))}",
            f"• 출처: <a href=\"{html.escape(row['link'], quote=True)}\">{html.escape(row['source'])}</a>",
            "",
        ]
    parts += _fixed_project_cost_block()
    parts += [
        "",
        f"<i>조회 {now.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')} · 같은 사건의 단순 주가 반응은 제외</i>",
    ]
    ALERT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"new_alerts={len(fresh)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
