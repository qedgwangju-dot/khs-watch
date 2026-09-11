#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import importlib.util
import pathlib
import re
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "khs_us_investment_alert.html"
CORE_PATH = ROOT / "scripts" / "khs_us_investment_watch_core.py"
KST = ZoneInfo("Asia/Seoul")


def _load_core():
    spec = importlib.util.spec_from_file_location("khs_us_investment_watch_core_finalize", CORE_PATH)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def parse_published(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return ""


def confirm_for(tags: str, source: str) -> str:
    blob = f"{tags} {source}".lower()
    official_tokens = [
        "공식정정/정부입장", "정책브리핑", "대한민국 정책브리핑", "산업통상",
        "재정경제부", "기획재정부", "ercot", "puct", "texas governor",
        "두산에너빌리티",
    ]
    if any(token in blob for token in official_tokens):
        return "공식자료 확인"
    return "신뢰 보도 확인 · 정부 공식 확정 여부는 별도 관리"


def check_for(tags: str) -> str:
    if "가스터빈·HRSG 공급망" in tags:
        return "제조사 실명 · 구매주문(PO) · 실제 기수 · 납기 · HRSG 공급사 · 장기 유지보수 계약"
    if "대미투자 첫사업/에너지패키지" in tags:
        return "정부 공식 첫 사업 선정 · 투자금·지분·수익배분 · 원전 부지·노형·기수 · 첫 자금요청·송금"
    if "ERCOT 신청/실수요 구분" in tags:
        return "감사 · 계통연계 요건 충족 · 전원 인가 승인 · 실제 가동"
    if "엔시날 단계증설" in tags:
        return "AI 고객 실명·전력구매계약(PPA) · 1.4GW 발주 · 4.9GW 후속 승인"
    if "수익배분/손실분담" in tags:
        return "리스크 풀링 유지 여부 · 손실 상계 범위 · 원리금 상환 순서"
    if "45영업일" in tags or "송금절차" in tags:
        return "사업 선정일 · 한국 통보일 · 별도 조기집행 합의 · 운영위 의결 · 실제 송금일·금액"
    if "원전" in tags:
        return "부지 · 노형 · 기수 · 발주주체 · 본계약"
    if "알래스카 LNG" in tags:
        return "장기구매계약(SPA)·오프테이크 · 최종투자결정(FID) · 금융종결 · 한국 투자액·본계약"
    if "텍사스 AI 전력" in tags or "가스발전 설비" in tags:
        return "전력구매계약(PPA) · 계통연계 · 가스터빈·스팀터빈·배열회수보일러(HRSG) 발주 · 착공 · 전원 인가"
    return "공식자료 · 계약 · 허가 · 착공 · 실제 매출 연결 여부"


def main() -> int:
    if not ALERT.exists():
        print("finalize_alert=none")
        return 0

    text = ALERT.read_text(encoding="utf-8")
    footer = re.search(r"^조회\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+KST)", text, re.M)
    lookup_time = footer.group(1) if footer else ""
    core = _load_core()
    publication_cache: dict[tuple[str, str, str], str] = {}

    def source_time(title: str, source: str, link: str) -> str:
        title_plain = clean(title)
        source_plain = clean(source)
        raw_link = html.unescape(link)
        key = (title_plain, source_plain, raw_link)
        if key in publication_cache:
            return publication_cache[key]

        timestamp = ""
        if core is not None and title_plain:
            try:
                query_title = title_plain.replace('"', " ")
                rows = core._rss(f'"{query_title}" when:7d')
                exact = next((r for r in rows if str(r.get("link") or "") == raw_link), None)
                if exact is None:
                    exact = next(
                        (
                            r for r in rows
                            if clean(str(r.get("title") or "")) == title_plain
                            and clean(str(r.get("source") or "")) == source_plain
                        ),
                        None,
                    )
                if exact is not None:
                    timestamp = parse_published(exact.get("published"))
            except Exception as exc:
                print(f"publication_time_lookup_failed={type(exc).__name__}")
        if not timestamp:
            timestamp = f"{lookup_time} (조회)" if lookup_time else "확인 불가"
        publication_cache[key] = timestamp
        return timestamp

    article_re = re.compile(
        r"(?P<title><b>\d+\.\s+.*?</b>)\n"
        r"(?P<class>• 🟧 <b>구분:\s*(?P<tags>.*?)</b>)\n"
        r"• 의미:\s*(?P<meaning>.*?)\n"
        r"• 출처:\s*<a href=\"(?P<link>[^\"]+)\">(?P<source>.*?)</a>",
        re.S,
    )

    def render_article(match: re.Match) -> str:
        tags_plain = clean(match.group("tags"))
        source_plain = clean(match.group("source"))
        timestamp = source_time(match.group("title"), match.group("source"), match.group("link"))
        return "\n".join([
            match.group("title"),
            match.group("class"),
            f'• 출처: {match.group("source")} · 시각: {timestamp} · <a href="{match.group("link")}">원문</a>',
            f"• 확인: {confirm_for(tags_plain, source_plain)}",
            f"• 핵심: {match.group('meaning').strip()}",
            f"• 체크: {html.escape(check_for(tags_plain))}",
        ])

    text, generic_count = article_re.subn(render_article, text)

    energy_re = re.compile(r"^(?P<header><b>🇺🇸 대미투자 첫사업·에너지 패키지 \| .*?</b>)\n", re.M)
    energy_match = energy_re.search(text)
    if energy_match:
        after = text[energy_match.end():energy_match.end() + 400]
        if "• 🟧 <b>구분:" not in after:
            header_plain = clean(energy_match.group("header"))
            status = "정부 공식확정 분리"
            if "정부 미확정" in header_plain:
                status = "정부 공식상태 미확정"
            elif "정부 공식단계 상승" in header_plain:
                status = "정부 공식단계 상승"
            metadata = "\n".join([
                "• 🟧 <b>구분: 대미투자 첫사업 / 에너지 패키지</b>",
                '• 출처: WSJ · 시각: 2026-09-10 (게시일) · <a href="https://www.wsj.com/world/asia/south-korea-nears-agreement-on-billions-in-u-s-investments-a-win-for-trump-2b58dc4a">원문</a>',
                f"• 확인: WSJ 합의 근접 보도 확인 · {status}",
                "• 핵심: 1,000억달러 초과 에너지 패키지 · 텍사스 가스발전 + 미국 대형원전 최대 8기",
                "• 체크: 정부 공식 첫 사업 선정 · 투자금·지분·수익배분 · 원전 부지·노형·기수 · 실제 선정 통지일 · 첫 자금요청·송금",
                "",
            ])
            text = text[:energy_match.end()] + metadata + "\n" + text[energy_match.end():]

    replacements = [
        (r'(?m)^<a href="([^"]+)">WSJ 원문</a>$', r'• 출처: WSJ · 시각: 2026-09-10 (게시일) · <a href="\1">원문</a>'),
        (r'(?m)^<a href="([^"]+)">Reuters 교차검증</a>$', r'• 출처: Reuters · 시각: 2026-09-10 (게시일) · <a href="\1">원문</a>'),
        (r'(?m)^<a href="([^"]+)">산업통상부 9월 9일 공식 설명자료</a>$', r'• 출처: 산업통상부 · 시각: 2026-09-09 (공식자료 게시일) · <a href="\1">원문</a>'),
        (r'(?m)^<a href="([^"]+)">산업통상부 9월 10일 수익배분 공식 설명자료</a>$', r'• 출처: 산업통상부 · 시각: 2026-09-10 (공식자료 게시일) · <a href="\1">원문</a>'),
        (r'(?m)^<a href="([^"]+)">2025-11-14 한미 전략적 투자 MOU 공식 설명</a>$', r'• 출처: 대한민국 정책브리핑 · 시각: 2025-11-14 (공식자료 게시일) · <a href="\1">원문</a>'),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)

    required = ["• 🟧 <b>구분:", "• 출처:", "· 시각:", ">원문</a>", "• 확인:", "• 핵심:", "• 체크:"]
    for match in re.finditer(r"(?m)^<b>\d+\.\s+.*?</b>$", text):
        block = text[match.start():]
        next_item = re.search(r"(?m)^<b>\d+\.\s+.*?</b>$", block[1:])
        if next_item:
            block = block[:next_item.start() + 1]
        positions = [block.find(token) for token in required]
        if any(pos < 0 for pos in positions) or positions != sorted(positions):
            raise RuntimeError("final alert item format validation failed")

    if energy_match:
        head = text[:1800]
        positions = [head.find(token) for token in required]
        if any(pos < 0 for pos in positions) or positions != sorted(positions):
            raise RuntimeError("energy-package header format validation failed")

    if re.search(r'(?m)^• 출처:\s*<a href="[^"]+">[^<]+</a>\s*$', text):
        raise RuntimeError("old separated source line survived final formatting")
    if re.search(r'(?m)^<a href="', text):
        raise RuntimeError("standalone source link survived final formatting")

    ALERT.write_text(text, encoding="utf-8")
    print(f"final_alert_format_enforced=true generic_items={generic_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
