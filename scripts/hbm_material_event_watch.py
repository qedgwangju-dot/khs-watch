"""One-time verified recovery of important Nov 2026 HBM-adjacent events.
This is an extension of the existing Rubin HBM Actions -> Python -> Telegram path.
It never sends directly. hbm_delivery.py exclusively acknowledges and commits state.
"""
from __future__ import annotations

import copy
import html
import json
import pathlib
import re
import urllib.request
from datetime import datetime, date
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
PENDING = ROOT / "out/rubin_hbm_pending_state.json"
ALERT = ROOT / "out/rubin_hbm_alert.md"
AUDIT = ROOT / "out/hbm_material_event_coverage.json"
BREAK = "<<<TELEGRAM_MESSAGE_BREAK>>>"
VERSION = 1
MAX_AGE_DAYS = 14

# Fixed independently traceable facts, not automatic promotions to issuer contracts.
# Fall-back copies/reprints carry their original lineage rather than pretending to
# be independent corroboration.
REPORTS = (
    {
        "key": "20261112_samsungsem_glass_onepass_loi",
        "date": "2026-11-12",
        "group": "glass",
        "label": "삼성전기 평택 유리기판 원패스 라인 구매의향서",
        "sources": (
            ("전자신문 원보도", "https://www.etnews.com/20261112000021?m=1", "원보도"),
            ("전자신문 원보도", "https://www.etnews.com/20261112000021", "동일 원보도"),
        ),
        "need": (("삼성전기",), ("유리기판",), ("LOI", "구매의향서"),
                 ("LPKF",), ("태성",), ("싸이맥스",), ("에스디옵틱스",),
                 ("이노메트리",), ("테크밸리",), ("HB테크놀러지",)),
        "facts": (
            "2026년 10월 장비사 선정·구매의향서 전달을 보도, 2027년 하반기 장비 반입·평택 설치 목표.",
            "7곳: LPKF(유리관통전극 레이저), 태성(식각), 싸이맥스(이송), 에스디옵틱스(광학), 이노메트리·테크밸리(엑스레이·3차원 검사), HB테크놀러지(검사).",
            "2028년 양산 목표와 글로벌 고객 평가 단계는 별개; 브로드컴은 보도상 후보.",
        ),
        "caution": "LOI는 확정 구매계약·발주금액·장비 반입·양산매출이 아니며 장비사 공식 확인은 비공개.",
    },
    {
        "key": "20261112_skhynix_hbm4_reported_yield_over70",
        "date": "2026-11-12",
        "group": "hbm",
        "label": "SK하이닉스 HBM4 수율 70% 초과",
        "sources": (
            ("조선비즈 원보도", "https://biz.chosun.com/it-science/ict/2026/11/12/E5T4MINR45CA7LR5ID7H7VRQBA/?outputType=amp", "원보도"),
            ("DIGITIMES의 조선비즈 재인용", "https://www.digitimes.com/topic/semiconductors/memory_chips/", "재인용"),
        ),
        "need": (("SK하이닉스", "SK Hynix"), ("HBM4",), ("수율", "yield"), ("70%", "70 percent")),
        "facts": ("수율이 70%를 넘었다는 11월 12일 업계 소식통 보도.",),
        "caution": "SK하이닉스 공식 수율 공개 없음; 전공정·적층·패키징·최종 양품 수율의 분모 미확인, 2개 독립 출처로 과대평가 금지.",
    },
    {
        "key": "20261112_samsung_onyang_hbm_202806_acceleration",
        "date": "2026-11-12",
        "group": "hbm",
        "label": "삼성 온양 HBM 5라인 2028년 6월 조기 가동 목표",
        "sources": (
            ("머니투데이 원보도", "https://www.mt.co.kr/index.php/industry/2026/11/12/2026111211085487358", "원보도"),
            ("아이뉴스24 별도 보도", "https://inews24.com/view/2025485", "별도 보도"),
        ),
        "need": (("온양",), ("HBM",), ("2028",), ("6월",), ("46조",)),
        "facts": (
            "온양 HBM 패키징 5라인 가동 목표: 기존 2029년 → 2028년 6월로 조기화 보도.",
            "온양 관련 46조원 순차 투자 보도(건설 6조원·장비 40조원); 삼성 충청권 전체 투자계획과 중복 합산 금지.",
        ),
        "caution": "착공·설비투자와 고객 검증·최초 가동·양품 출하·매출 인식은 서로 다른 단계.",
    },
    {
        "key": "20261113_samsung_8inch_reported_2029_umc",
        "date": "2026-11-13",
        "group": "hbm",
        "label": "삼성 8인치 파운드리 철수 목표 2029년·UMC 일부 외주화",
        "sources": (
            ("DIGITIMES 원보도(DealSite 인용)", "https://www.digitimes.com/news/a20261112VL214.html", "DealSite→DIGITIMES 재인용"),
            ("한국신용신문 재인용", "https://www.creditnews.kr/news/articleView.html?idxno=32565", "재인용"),
        ),
        "need": (("삼성", "Samsung"), ("8인치", "8-inch"), ("2029",), ("UMC", "United Microelectronics")),
        "facts": ("2029년 말 철수 목표 보도는 기존 2030년 전망보다 1년 앞섰으며 일부 물량 UMC 외주화 보도.",),
        "caution": "업계·재인용 보도 단계. 삼성·UMC 공식 최종 철수 결정·외주 계약 물량·금액 미확인; HBM4와 별개의 8인치 성숙공정.",
    },
    {
        "key": "20261112_intel_kai_23_company_alliance",
        "date": "2026-11-12",
        "group": "intel",
        "label": "인텔 K-AI 풀스택 연합 초기 23개 참여사",
        "sources": (
            ("전자신문 원보도", "https://www.etnews.com/20261112000262", "원보도"),
            ("연합뉴스 별도 보도", "https://www.yna.co.kr/view/AKR20261112076500017", "별도 보도"),
        ),
        "need": (("인텔", "Intel"), ("K-AI",), ("23",), ("얼라이언스", "Alliance")),
        "facts": (
            "2026년 11월 12일 발표; 인텔 포함 초기 참여사 23곳 보도, 리벨리온·딥엑스·업스테이지·메가존클라우드 등 참여.",
            "목적: 국산 서버 기반 AI 칩·모델·소프트웨어·클라우드 연계와 소버린·피지컬 AI 협력.",
        ),
        "caution": "연합 참여는 인텔 GPU 구매계약·국산 NPU 대량 발주나 양산매출 확정이 아님.",
    },
    {
        "key": "20261112_intel_hbmfree_lpddr_inference_proposal",
        "date": "2026-11-12",
        "group": "intel",
        "label": "인텔 HBM 대신 저전력 D램 활용하는 추론 GPU 전략",
        "sources": (
            ("뉴스핌 원보도", "https://ir.newspim.com/news/view/20261112000679", "원보도"),
            ("DIGITIMES 보도", "https://www.digitimes.com/topic/semiconductors/memory_chips/", "별도 보도"),
        ),
        "need": (("인텔", "Intel"), ("HBM",), ("LPDDR", "저전력"), ("추론", "inference")),
        "facts": ("HBM을 탑재하지 않고 저전력 D램을 쓰는 일부 추론용 GPU 전략·국내 맞춤형 설계 및 파운드리 협력 제안.",),
        "caution": "제품군·워크로드별 대안. 모든 AI GPU에서 HBM이 사라지거나 전체 HBM 비트 수요가 줄었다는 확정 신호 아님.",
    },
    {
        "key": "20261112_intel_skhynix_shared_memory_collaboration",
        "date": "2026-11-12",
        "group": "intel",
        "label": "인텔·SK하이닉스 AI 공유 메모리 구조 협력",
        "sources": (
            ("조선비즈 현장 보도", "https://biz.chosun.com/en/en-it/2026/11/12/R2O5YIDCWNESZNXXKMOITVFQIU/", "원보도"),
            ("DIGITIMES 보도", "https://www.digitimes.com/topic/semiconductors/memory_chips/", "별도 보도"),
        ),
        "need": (("Intel", "인텔"), ("SK hynix", "SK하이닉스"), ("memory", "메모리"), ("shared", "share", "공유", "rack", "pool")),
        "facts": ("여러 AI 서버가 대용량 메모리를 공유하는 '메모리 랙' 등 메모리 중심 구조 협력 방향 보도.",),
        "caution": "CXL 실증·호환성·실제 고객 채택·정식 제품 공급계약·매출액은 개별 확인 필요.",
    },
)

GROUPS = {
    "glass": "삼성전기 유리기판 LOI·공정별 공급망",
    "hbm": "SK하이닉스 HBM4·삼성 온양 증설·8인치 공정 재편",
    "intel": "인텔 추론 GPU·국내 23개사·공유 메모리",
}

def text_matches(body: str, required: tuple) -> bool:
    low = body.casefold()
    return all(any(term.casefold() in low for term in terms) for terms in required)

def fetch_article(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; HBM-monitor/1.0)", "Accept-Language": "ko-KR,ko;q=0.8,en;q=0.7"}
    )
    with urllib.request.urlopen(req, timeout=13) as response:
        actual = response.geturl()
        host = (urlparse(actual).hostname or "").lower()
        expected = (urlparse(url).hostname or "").lower()
        def root(h):
            h = h.removeprefix("www.").removeprefix("ir.").removeprefix("biz.")
            return h
        if root(host) != root(expected):
            raise ValueError("publisher_host_changed")
        raw = response.read(2_500_001)
        if len(raw) > 2_500_000:
            raise ValueError("oversize_publisher_page")
        encoding = response.headers.get_content_charset() or "utf-8"
    soup = BeautifulSoup(raw.decode(encoding, errors="replace"), "html.parser")
    for tag in soup.select("script, style, noscript, svg, nav, footer, header"):
        tag.decompose()
    for selector in ("#articleBody", "#newsEndContents", ".article_body", ".article-view", "article"):
        area = soup.select_one(selector)
        if area and len(area.get_text(" ", strip=True)) >= 160:
            return html.unescape(area.get_text(" ", strip=True))
    return html.unescape(soup.get_text(" ", strip=True))

def probe(report: dict, fetcher=fetch_article) -> tuple[dict | None, list[dict]]:
    gaps = []
    for label, url, lineage in report["sources"]:
        try:
            body = fetcher(url)
            if not text_matches(body, report["need"]):
                gaps.append({"key": report["key"], "origin": label, "status": "required_article_facts_not_verified"})
                continue
            return {"key": report["key"], "group": report["group"], "label": report["label"],
                    "date": report["date"], "facts": report["facts"], "caution": report["caution"],
                    "source": url, "source_label": label, "lineage": lineage,
                    "verified_kind": "reported_not_issuer_confirmed"}, gaps
        except Exception as exc:
            gaps.append({"key": report["key"], "origin": label,
                         "status": "source_unavailable", "error_type": type(exc).__name__})
    return None, gaps

def render(group: str, items: list[dict], checked_at: str) -> str:
    lines = [
        "<b>[HBM 기존 감시 보강 | 중요 신규·누락 사건]</b>",
        f"<b>{html.escape(GROUPS[group])}</b>",
        f"확인: {html.escape(checked_at)} · 최초 보도일 기준 · 원보도/재인용 구분",
    ]
    for item in items:
        lines.extend(("", f"<b>■ {html.escape(item['label'])}</b>",
                      f"• 최초 보도: {item['date']} · 출처 단계: {html.escape(item['lineage'])}"))
        lines.extend("• " + html.escape(line) for line in item["facts"])
        lines.append("• 구분·위험: " + html.escape(item["caution"]))
        lines.append(f'• <a href="{html.escape(item["source"], quote=True)}">근거 기사</a> ({html.escape(item["source_label"])})')
    return "\n".join(lines).strip() + "\n"

def apply(previous: dict, checked_at: str, fetcher=fetch_article) -> tuple[dict, list[str], dict]:
    result = copy.deepcopy(previous)
    sub = result.get("hbm_material_event_watch") or {}
    existing = set(sub.get("seen_keys") or [])
    new = []
    gaps = []
    for report in REPORTS:
        if report["key"] in existing:
            continue
        if (date.fromisoformat(checked_at[:10]) - date.fromisoformat(report["date"])).days > MAX_AGE_DAYS:
            gaps.append({"key": report["key"], "status": "older_than_backfill_window"})
            continue
        obs, err = probe(report, fetcher)
        gaps.extend(err)
        if obs:
            new.append(obs)
            existing.add(obs["key"])
    result["hbm_material_event_watch"] = {
        "version": VERSION, "checked_at_kst": checked_at,
        "seen_keys": sorted(existing), "last_new_fact_keys": [x["key"] for x in new],
        "unconfirmed_source_count": len({x["key"] for x in gaps}),
        "unconfirmed_sources": gaps[-20:],
        "evidence_rule": "verified_publisher_body_reported_only_not_contract_or_company_yield",
    }
    rendered = [render(group, [x for x in new if x["group"] == group], checked_at)
                for group in ("glass", "hbm", "intel")
                if any(x["group"] == group for x in new)]
    audit = {"checked_at_kst": checked_at, "verified_events": len(new),
             "verified_keys": [x["key"] for x in new], "gaps": gaps[-20:],
             "durable_state_only_after_existing_hbm_delivery_receipt": True}
    return result, rendered, audit

def main() -> None:
    if not PENDING.exists():
        raise RuntimeError("Rubin HBM pending state is missing; no material-event update permitted")
    if not PENDING.parent.is_dir():
        raise RuntimeError("HBM output directory missing")
    prior = json.loads(PENDING.read_text(encoding="utf-8"))
    checked_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    result, rendered, audit = apply(prior, checked_at)
    # Do not consume these keys outside the existing acknowledged delivery.
    if rendered:
        existing = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
        content = ("\n\n" + BREAK + "\n\n").join(
            ([existing] if existing else []) + rendered
        )
        ALERT.write_text(content.strip() + "\n", encoding="utf-8")
    PENDING.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("hbm_material_events_verified=" + str(audit["verified_events"])
          + " coverage_gaps=" + str(len(audit["gaps"]))
          + " telegram_send_delegated_to=hbm_delivery")

if __name__ == "__main__":
    main()
