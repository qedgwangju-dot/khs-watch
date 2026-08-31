#!/usr/bin/env python3
"""LNG 공급 위기 감시 v8.

v7 정확도 규칙을 유지하면서 Telegram 표시를 개선한다.
1) 영문 뉴스 제목은 한국어로 번역해서만 표시한다.
2) 원문 URL을 길게 노출하지 않고 Telegram HTML의 '원문' 링크로 표시한다.
3) 번역 서비스 실패 시 영문 원문을 노출하지 않고 사건 유형 기반 한국어 요약으로 대체한다.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v7 as v7


SOURCE_KO = {
    "reuters": "로이터",
    "bloomberg.com": "블룸버그",
    "bloomberg": "블룸버그",
    "associated press": "AP통신",
    "ap news": "AP통신",
    "financial times": "파이낸셜타임스",
    "the wall street journal": "월스트리트저널",
    "wall street journal": "월스트리트저널",
    "bbc": "BBC",
    "cnbc": "CNBC",
    "nikkei asia": "닛케이아시아",
    "s&p global commodity insights": "S&P 글로벌 커머디티 인사이트",
    "argus media": "아거스미디어",
    "montel": "몬텔",
    "upstream": "업스트림",
    "the guardian": "가디언",
    "afp": "AFP통신",
    "yonhap": "연합뉴스",
    "qatarenergy": "카타르에너지",
    "qatar energy": "카타르에너지",
    "european commission": "유럽연합 집행위원회",
    "gas infrastructure europe": "유럽가스인프라협회(GIE)",
    "international energy agency": "국제에너지기구(IEA)",
    "korea gas corporation": "한국가스공사",
    "ministry of trade, industry and energy": "산업통상자원부",
}

# 현재 확인된 대표 영문 기사. 번역 서비스 장애와 무관하게 정확한 한국어로 표시한다.
KNOWN_TRANSLATIONS = {
    "US forces strike two Iranian launchers on Iran's Larak island, US official says - Reuters":
        "미군, 이란 라라크섬의 발사대 2곳 타격…미 당국자 확인",
    "US Strikes Iranian Rocket Launchers in First Attack in Weeks - Bloomberg.com":
        "미군, 수주 만에 처음으로 이란 로켓 발사대 타격",
}

ALLOWED_ASCII = {"LNG", "JKM", "TTF", "EU", "GIE", "IEA", "AP", "BBC", "CNBC", "S&P"}
_TRANSLATION_CACHE: dict[str, str] = {}


def source_name_ko(source: str) -> str:
    normalized = core.normalize_text(source)
    for key, value in SOURCE_KO.items():
        if key in normalized:
            return value
    # 알 수 없는 영문 매체명은 제목과 달리 고유 브랜드일 수 있으므로 그대로 두지 않고 '해외 매체'로 표시한다.
    if re.search(r"[A-Za-z]", source):
        return "해외 매체"
    return source


def fallback_korean_title(item: core.NewsItem) -> str:
    subtype = item.subtype
    category = item.category
    polarity = item.polarity

    subtype_text = {
        "force_majeure": "불가항력 선언·연장 관련 변화",
        "export_resume": "LNG 수출 재개·회복",
        "production_restart": "LNG 생산 재가동·회복",
        "production_outage": "LNG 생산·수출 차질",
        "facility_damage": "핵심 에너지·군사 시설 공격 또는 피해 발생",
        "hormuz_reopen": "호르무즈 통항 재개",
        "hormuz_closure": "호르무즈 통항 차질·봉쇄 위험 확대",
        "insurance": "선박 보험·전쟁위험 비용 변화",
        "reroute": "LNG 선박 우회 운항 변화",
        "storage": "가스 재고·비축 변화",
        "jkm_price": "아시아 LNG 가격 변화",
        "cargo_tender": "LNG 현물 조달·입찰 변화",
        "korea_supply": "한국 LNG 수급 관련 변화",
    }.get(subtype)
    if subtype_text:
        return subtype_text

    base = {
        "qatar_supply": "카타르 LNG 생산·수출",
        "hormuz_shipping": "호르무즈·홍해 운송",
        "europe_storage": "유럽 가스 재고",
        "asia_procurement": "동북아 LNG 조달",
        "korea_supply": "한국 LNG 수급",
    }.get(category, "LNG 수급")
    return f"{base} {'악화' if polarity == 'worsening' else '완화'} 관련 확정 변화"


def _translate_google(text: str) -> str:
    params = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "auto",
            "tl": "ko",
            "dt": "t",
            "q": text,
        }
    )
    request = urllib.request.Request(
        f"https://translate.googleapis.com/translate_a/single?{params}",
        headers={"User-Agent": "Mozilla/5.0 khs-lng-alert/8.0"},
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    pieces = payload[0] if isinstance(payload, list) and payload else []
    return "".join(str(piece[0]) for piece in pieces if isinstance(piece, list) and piece and piece[0]).strip()


def _has_untranslated_english(text: str) -> bool:
    scrubbed = text
    for token in ALLOWED_ASCII:
        scrubbed = scrubbed.replace(token, "")
    # 2글자 이상의 영문 단어가 남으면 불완전 번역으로 간주한다.
    return bool(re.search(r"[A-Za-z]{2,}", scrubbed))


def translate_title_ko(item: core.NewsItem) -> str:
    title = item.title.strip()
    if not re.search(r"[A-Za-z]", title):
        return title
    if title in KNOWN_TRANSLATIONS:
        return KNOWN_TRANSLATIONS[title]
    if title in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[title]

    translated = ""
    try:
        translated = _translate_google(title)
    except Exception:
        translated = ""

    replacements = (
        ("Larak Island", "라라크섬"),
        ("Larak island", "라라크섬"),
        ("Strait of Hormuz", "호르무즈 해협"),
        ("Red Sea", "홍해"),
        ("QatarEnergy", "카타르에너지"),
        ("Qatar", "카타르"),
        ("Iranian", "이란"),
        ("Iran", "이란"),
        ("United States", "미국"),
        ("U.S.", "미국"),
        ("US", "미국"),
        ("Europe", "유럽"),
        ("Korea", "한국"),
        ("Japan", "일본"),
        ("Reuters", "로이터"),
        ("Bloomberg.com", "블룸버그"),
        ("Bloomberg", "블룸버그"),
    )
    for before, after in replacements:
        translated = translated.replace(before, after)

    if not translated or _has_untranslated_english(translated):
        translated = fallback_korean_title(item)
    _TRANSLATION_CACHE[title] = translated
    return translated


def build_regular_alert_v8(
    groups: list[dict[str, object]],
    quotes: dict[str, core.Quote],
    new_signals: set[str],
    cleared_signals: set[str],
) -> tuple[str, str, dict[str, object]]:
    context = core.classify_alert_context(groups, new_signals, cleared_signals)
    title = "⚠️ LNG·천연가스 수급 경보"
    lines: list[str] = []

    if groups:
        lines.append("[새 확정 변화]")
        for group in groups[:3]:
            polarity = "악화" if group["polarity"] == "worsening" else "완화"
            lines.append(
                f"• {html.escape(core.category_label(str(group['category'])))}: {polarity} "
                f"({html.escape(str(group['verification']))})"
            )
            for item in group["evidence"][:2]:
                source = html.escape(source_name_ko(item.source))
                translated = html.escape(translate_title_ko(item))
                link = html.escape(item.link, quote=True)
                lines.append(f"  - {source}: {translated}  <a href=\"{link}\">원문</a>")
    else:
        lines.extend(["[새 확정 변화]", "• 공급·운송 관련 새 확정 뉴스 없음"])

    if new_signals or cleared_signals:
        lines.extend(["", "[가격 신호]"])
        for signal in sorted(new_signals):
            lines.append(f"• 진입: {html.escape(core.signal_label(signal))}")
        for signal in sorted(cleared_signals):
            lines.append(f"• 이탈: {html.escape(core.signal_label(signal, cleared=True))}")
        for quote in quotes.values():
            lines.append(f"• {html.escape(core.format_quote(quote))}")
        lines.append("• 가격값은 각 지정 원천의 검증 규칙을 통과한 값만 사용합니다.")

    korea, investment, one_line = core.impact_text(context)
    lines.extend(
        [
            "",
            "[한국 영향]",
            html.escape(korea),
            "",
            "[투자 영향]",
            html.escape(investment),
            "",
            f"핵심 한 줄: {html.escape(one_line)}",
        ]
    )
    metadata = {
        "version": 8,
        "kind": "material_change",
        "context": context,
        "news_event_ids": [group["event_id"] for group in groups],
        "new_market_signals": sorted(new_signals),
        "cleared_market_signals": sorted(cleared_signals),
        "quotes": {key: asdict(quote) for key, quote in quotes.items()},
        "telegram_format": "HTML",
        "headline_language": "ko",
        "raw_urls_hidden": True,
    }
    return title, "\n".join(lines), metadata


# v7의 시장값·뉴스 정확도 규칙은 그대로 유지하고 출력 포맷만 v8로 교체한다.
core.fetch_market_quotes = v7.fetch_market_quotes_v7
core.format_quote = v7.v6.format_quote_v6
core.signal_label = v7.te.signal_label_v4
core.build_setup_test = v7.build_setup_test_v7
core.build_regular_alert = build_regular_alert_v8


if __name__ == "__main__":
    raise SystemExit(core.main())
