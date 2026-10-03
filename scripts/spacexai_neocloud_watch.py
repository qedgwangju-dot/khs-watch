#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT = Path("out")
STATE = Path("data/spacexai_neocloud_state.json")
PENDING = OUT / "spacexai_neocloud_pending_state.json"
ALERT = OUT / "spacexai_neocloud_alert.txt"
STATUS = OUT / "spacexai_neocloud_status.md"

FORMAT_VERSION = 1
MAX_NEWS_AGE_DAYS = 7
UA = "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*"}

SPACEX_S1 = "https://www.sec.gov/Archives/edgar/data/1181412/000162828026039276/spaceexplorationtechnologi.htm"
SPACEX_GOOGLE_FWP = "https://www.sec.gov/Archives/edgar/data/1181412/000162828026041150/spacexagreementfwp.htm"
SPACEX_10Q = "https://www.sec.gov/Archives/edgar/data/1181412/000162828026052535/spcx-20260630.htm"
SPACEX_Q2_RELEASE = "https://www.sec.gov/Archives/edgar/data/1181412/000162828026052515/earningsreleaseq22608042.htm"
ANTHROPIC_OFFICIAL = "https://www.anthropic.com/news/higher-limits-spacex"
SPACEXAI_ANTHROPIC = "https://x.ai/news/anthropic-compute-partnership"
THE_INFORMATION = "https://www.theinformation.com/articles/spacexs-ai-unit-turned-ai-cloud-firm"
MARKETWATCH = "https://www.marketwatch.com/story/spacex-is-inching-closer-to-this-lofty-100-billion-milestone-11536cfc"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK0001181412.json"

TRUSTED_NEWS = (
    "Reuters", "Bloomberg", "Financial Times", "The Information", "CNBC",
    "MarketWatch", "Business Insider", "TechCrunch", "Wall Street Journal",
)

QUERIES = (
    '"SpaceXAI" compute customer Microsoft Google Anthropic cloud',
    '"SpaceX" compute capacity Microsoft Google Anthropic GPU cloud',
    '"SpaceXAI" neocloud GPU contract',
    '"SpaceX" "$1.1 billion" compute December',
    '"SpaceXAI" 420000 GPUs November',
)

CURRENT_REPORTED_CONTEXT = [
    {
        "label": "Microsoft 협상",
        "detail": "The Information은 SpaceX AI 부문이 2026년 여름 Microsoft와 컴퓨팅 용량 임대 협상을 진행했다고 보도. 계약 성사 여부는 불명확하며 Microsoft는 논평을 거절.",
        "status": "보도·미확정",
        "url": THE_INFORMATION,
    },
    {
        "label": "12월 신규 월 11억달러 계약",
        "detail": "SpaceX CFO Bret Johnsen이 2026년 9월 Goldman Sachs 행사에서 12월 시작 예정인 월 11억달러 규모 계약을 언급했다고 MarketWatch와 The Information이 보도. 상대방은 공개되지 않음.",
        "status": "CFO 발언 보도·상대방 미공개",
        "url": MARKETWATCH,
    },
    {
        "label": "11월 GPU 증설",
        "detail": "The Information은 SpaceXAI가 2026년 11월 약 42만개의 NVIDIA GPU를 추가 가동할 계획이라고 보도. 실제 인도·가동 완료는 향후 별도 확인 대상.",
        "status": "보도·계획",
        "url": THE_INFORMATION,
    },
    {
        "label": "과거 Colossus 가동률",
        "detail": "The Information은 Colossus의 2025년 가동률이 40% 미만이었고 2026년 봄에도 유휴 자원이 상당했다고 보도. 회사 공식 지표가 아니므로 역사적 배경으로만 사용.",
        "status": "보도·비공식 추정",
        "url": THE_INFORMATION,
    },
]


def fetch(url: str, timeout: int = 25) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def page_text(url: str) -> str:
    return " ".join(BeautifulSoup(fetch(url).content, "html.parser").get_text(" ", strip=True).split())


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_number(text: str, pattern: str, cast=float):
    m = re.search(pattern, text, re.I)
    if not m:
        raise RuntimeError(f"pattern missing: {pattern}")
    return cast(m.group(1).replace(",", ""))


def official_snapshot() -> dict:
    s1 = page_text(SPACEX_S1)
    g = page_text(SPACEX_GOOGLE_FWP)
    q = page_text(SPACEX_10Q)
    e = page_text(SPACEX_Q2_RELEASE)
    a = page_text(ANTHROPIC_OFFICIAL)

    guards = [
        ("S-1 Anthropic", "Cloud Services Agreements with Anthropic", s1),
        ("Google FWP", "Cloud Service Agreement with Google", g),
        ("10-Q", "Nameplate Compute Draw", q),
        ("Q2 release", "contracted sales", e),
        ("Anthropic official", "SpaceX", a),
    ]
    for label, needle, body in guards:
        if needle.lower() not in body.lower():
            raise RuntimeError(f"{label} identity guard failed")

    anth_monthly = parse_number(s1, r"pay us\s*\$?([0-9]+(?:\.[0-9]+)?)\s*billion per month")
    anth_gpus = parse_number(s1, r"approximately\s+([0-9,]+)\s+NVIDIA GPUs", int)
    if "through May 2029" not in s1 or "90 days" not in s1:
        raise RuntimeError("Anthropic contract terms missing")

    google_monthly_m = parse_number(g, r"pay us\s*\$?([0-9]+(?:\.[0-9]+)?)\s*million per month")
    google_gpus = parse_number(g, r"approximately\s+([0-9,]+)\s+NVIDIA GPUs", int)
    if "from October 2026 through June 2029" not in g:
        raise RuntimeError("Google service period missing")
    if "September 30, 2026" not in g or "one-month grace period" not in g or "December 31, 2026" not in g:
        raise RuntimeError("Google delivery/termination terms missing")

    m = re.search(r"Nameplate Compute Draw.*?([0-9]+(?:\.[0-9]+)?)\s+.*?0\.4", q, re.I)
    if not m:
        raise RuntimeError("Nameplate compute draw missing")
    nameplate_gw = float(m.group(1))

    contracted_sales_b = parse_number(e, r"\$([0-9]+(?:\.[0-9]+)?)\s+billion of contracted sales")

    anth_site_mw = None
    am = re.search(r"more than\s+([0-9,]+)\s+megawatts", a, re.I)
    if am:
        anth_site_mw = int(am.group(1).replace(",", ""))

    return {
        "anthropic": {
            "monthly_usd_b": anth_monthly,
            "gpus": anth_gpus,
            "through": "2029-05",
            "termination": "상호 90일 통지 해지 가능",
            "site_mw_min": anth_site_mw,
            "official_url": SPACEX_S1,
        },
        "google": {
            "monthly_usd_b": google_monthly_m / 1000.0,
            "gpus": google_gpus,
            "start": "2026-10",
            "through": "2029-06",
            "delivery_deadline": "2026-09-30",
            "delivery_grace": "1개월",
            "termination": "2026-12-31 이후 상호 90일 통지 해지 가능",
            "official_url": SPACEX_GOOGLE_FWP,
        },
        "spacex_ai": {
            "nameplate_compute_draw_gw": nameplate_gw,
            "nameplate_date": "2026-06-30",
            "contracted_sales_usd_b_q2_disclosure": contracted_sales_b,
            "note": "Nameplate compute draw는 실제 전력사용량·가동률이 아님",
        },
    }


def fx_snapshot(old: dict) -> dict:
    try:
        from fx_api import daily_krw
        q = daily_krw()
        return {"usdkrw": float(q.rate), "basis": q.basis, "source": q.source}
    except Exception:
        prior = old.get("fx") or {}
        if prior.get("usdkrw"):
            return {**prior, "source": str(prior.get("source") or "") + " · 직전 저장값"}
        raise


def krw_from_usd_b(value_b: float, fx: float) -> str:
    eok = int(round(value_b * 1_000_000_000 * fx / 100_000_000))
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def parse_pub(value: str) -> dt.datetime | None:
    try:
        d = parsedate_to_datetime(value)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:
        return None


def source_trusted(source: str) -> bool:
    low = (source or "").lower()
    return any(x.lower() in low for x in TRUSTED_NEWS)


def rss_rows(raw: bytes, fallback_source: str) -> list[dict]:
    root = ET.fromstring(raw)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=MAX_NEWS_AGE_DAYS)
    out = []
    for item in root.findall(".//item")[:40]:
        title = " ".join((item.findtext("title") or "").split())
        link = " ".join((item.findtext("link") or "").split())
        pub = parse_pub(item.findtext("pubDate") or "")
        source = ""
        src = item.find("source")
        if src is not None:
            source = " ".join((src.text or "").split())
        if not source and " - " in title:
            source = title.rsplit(" - ", 1)[-1].strip()
        source = source or fallback_source

        parsed = urllib.parse.urlparse(link)
        if parsed.netloc.endswith("bing.com"):
            target = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
            if target.startswith("http"):
                link = target

        low = title.lower()
        if not pub or pub < cutoff or not source_trusted(source):
            continue
        if not any(k in low for k in ("spacex", "spacexai", "xai", "colossus")):
            continue
        if not any(k in low for k in ("compute", "cloud", "gpu", "capacity", "microsoft", "anthropic", "google", "contract")):
            continue
        ident = hashlib.sha256(f"{source}|{title}".encode("utf-8")).hexdigest()[:24]
        out.append({
            "id": ident,
            "title": title,
            "source": source,
            "url": link,
            "published": pub.isoformat(),
        })
    return out


def search_news() -> tuple[list[dict], list[str]]:
    rows, errors = [], []
    google_ok = True
    for q in QUERIES:
        if google_ok:
            try:
                url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
                    "q": q + " when:7d", "hl": "en-US", "gl": "US", "ceid": "US:en",
                })
                rows.extend(rss_rows(fetch(url, 15).content, "Google News"))
                continue
            except Exception as exc:
                google_ok = False
                errors.append(f"Google News {type(exc).__name__} → Bing RSS 대체")
        try:
            url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": q, "format": "RSS"})
            rows.extend(rss_rows(fetch(url, 15).content, "Bing News"))
        except Exception as exc:
            errors.append(f"Bing News {type(exc).__name__}")
    return list({x["id"]: x for x in rows}.values()), errors


def sec_recent() -> tuple[list[dict], list[str]]:
    try:
        data = fetch(SEC_SUBMISSIONS, 20).json()
        recent = (data.get("filings") or {}).get("recent") or {}
        rows = []
        for form, accession, doc, filing_date in zip(
            recent.get("form") or [],
            recent.get("accessionNumber") or [],
            recent.get("primaryDocument") or [],
            recent.get("filingDate") or [],
        ):
            if filing_date < "2026-09-01":
                continue
            if form not in {"8-K", "10-Q", "10-K", "S-1", "S-1/A", "424B4", "FWP", "425"}:
                continue
            rows.append({
                "id": accession,
                "form": form,
                "filing_date": filing_date,
                "url": "https://www.sec.gov/Archives/edgar/data/1181412/" + accession.replace("-", "") + "/" + doc,
            })
        return rows, []
    except Exception as exc:
        return [], [f"SEC submissions {type(exc).__name__}"]


def official_changes(old: dict, new: dict) -> list[str]:
    if not old:
        return ["SpaceXAI 외부 컴퓨트 사업 기준선 신규 연결"]
    out = []
    prev = old.get("official") or {}
    checks = [
        ("Anthropic 월 계약금", "anthropic", "monthly_usd_b"),
        ("Anthropic GPU", "anthropic", "gpus"),
        ("Google 월 계약금", "google", "monthly_usd_b"),
        ("Google GPU", "google", "gpus"),
        ("AI 명목 컴퓨트 전력", "spacex_ai", "nameplate_compute_draw_gw"),
        ("공시 계약매출", "spacex_ai", "contracted_sales_usd_b_q2_disclosure"),
    ]
    for label, section, key in checks:
        before = (prev.get(section) or {}).get(key)
        after = (new.get(section) or {}).get(key)
        if before is not None and after is not None and before != after:
            out.append(f"{label} {before}→{after}")
    return out


def render(official: dict, changes: list[str], new_news: list[dict], new_sec: list[dict], fx: dict, show_context: bool) -> str:
    rate = float(fx["usdkrw"])
    anth = official["anthropic"]
    google = official["google"]
    sx = official["spacex_ai"]
    anth_ann = float(anth["monthly_usd_b"]) * 12
    google_ann = float(google["monthly_usd_b"]) * 12
    combined_m = float(anth["monthly_usd_b"]) + float(google["monthly_usd_b"])
    combined_ann = combined_m * 12

    lines = [
        "<b>☁️ SpaceXAI 외부 컴퓨트·네오클라우드 감시</b>",
        "확정 계약과 협상·보도 단계를 분리합니다.",
        "",
        "<b>📌 확정 사실 · 공식 공시</b>",
        f"• Anthropic │ 월 <b>${anth['monthly_usd_b']:.2f}B</b> ({krw_from_usd_b(float(anth['monthly_usd_b']), rate)}) · 연환산 ${anth_ann:.2f}B ({krw_from_usd_b(anth_ann, rate)})",
        f"  └ 약 <b>{anth['gpus']:,} NVIDIA GPU</b> · {anth['through']}까지 · {html.escape(anth['termination'])}",
        f"• Google │ 월 <b>${google['monthly_usd_b']:.2f}B</b> ({krw_from_usd_b(float(google['monthly_usd_b']), rate)}) · 연환산 ${google_ann:.2f}B ({krw_from_usd_b(google_ann, rate)})",
        f"  └ 약 <b>{google['gpus']:,} NVIDIA GPU</b> · {google['start']}~{google['through']} · {html.escape(google['termination'])}",
        f"  └ 납품조건: {google['delivery_deadline']}까지 약정 GPU 미제공 시 {google['delivery_grace']} 유예 후 해지 또는 월요금 비례감액 가능",
        f"• 두 공개 계약 단순 합계 │ 월 <b>${combined_m:.2f}B</b> · 연환산 <b>${combined_ann:.2f}B</b> ({krw_from_usd_b(combined_ann, rate)})",
        "  └ 단순 월요금 합산이며 해지권이 있어 전체 명목 계약기간 금액을 확정 backlog로 보지 않음",
        f"• SpaceX AI 명목 컴퓨트 전력 │ <b>{sx['nameplate_compute_draw_gw']:.1f}GW</b> · {sx['nameplate_date']}",
        f"  └ {html.escape(sx['note'])}",
        f"• Q2 공시 Cloud Services Agreements 계약매출 │ <b>${sx['contracted_sales_usd_b_q2_disclosure']:.1f}B</b> · 월요금 장기 단순합계와 별도 공시 지표",
    ]

    if changes:
        lines += ["", "<b>🔄 이번 확정 변화</b>"]
        lines += [f"• {html.escape(x)}" for x in changes[:8]]

    if show_context:
        lines += ["", "<b>🟡 보도·미확정 / 향후 확인 대상</b>"]
        for row in CURRENT_REPORTED_CONTEXT:
            lines.append(f"• <b>{html.escape(row['label'])}</b> │ {html.escape(row['status'])}")
            lines.append(f"  └ {html.escape(row['detail'])}")
            lines.append(f'  └ <a href="{html.escape(row["url"], quote=True)}">보도 원문</a>')

    if new_sec:
        lines += ["", "<b>🧾 신규 SEC 공시 후보</b>"]
        for row in new_sec[:6]:
            lines.append(f'• {html.escape(row["filing_date"])} · {html.escape(row["form"])} · <a href="{html.escape(row["url"], quote=True)}">공시 확인</a>')
        lines.append("• 계약상대·월요금·GPU·납품조건은 공식 문구 확인 후 확정 항목으로 승격")

    if new_news:
        lines += ["", "<b>📰 신규 보도 후보 · 계약 확정 아님</b>"]
        for row in new_news[:6]:
            lines.append(f'• [{html.escape(row["source"])}] {html.escape(row["title"])} · <a href="{html.escape(row["url"], quote=True)}">원문</a>')
        lines.append("• 회사 공시·공식 발표 확인 전에는 확정 계약/매출로 승격하지 않음")

    lines += [
        "",
        "<b>🔔 앞으로 알림하는 변화</b>",
        "• 신규 외부 고객 계약 · 월요금/계약기간/해지권 변경",
        "• Microsoft 협상이 실제 서명·공시 단계로 전환",
        "• GPU 5만개 이상 또는 100MW 이상 외부 임대·증설",
        "• Google 11만 GPU 납품조건·감액·해지권 발동 여부",
        "• 12월 월 11억달러 계약의 고객 실명·계약서·실제 개시 확인",
        "• Colossus 유휴용량의 외부 매출 전환과 내부 Grok 수요의 용량 회수",
        "",
        "<b>⚠️ 실패모드</b>",
        "• 해지권 행사 → 명목 월요금이 장기 반복매출로 이어지지 않음",
        "• GPU·전력·네트워크 납품 지연 → 서비스 개시 지연 또는 비례감액",
        "• 외부 고객과 Grok 내부수요 동시 급증 → 추가 데이터센터·전력 설비투자 부담",
        "• Anthropic·Google 고객 집중 → 대형 계약 변동이 AI 부문 매출에 크게 반영",
        "",
        f"💱 1달러 = {rate:,.2f}원 · {html.escape(str(fx.get('source','')))}",
        "",
        "<b>🔗 공식 원문</b>",
        f'• <a href="{SPACEX_S1}">SpaceX S-1 · Anthropic 계약</a>',
        f'• <a href="{SPACEX_GOOGLE_FWP}">SpaceX SEC FWP · Google 계약</a>',
        f'• <a href="{SPACEX_10Q}">SpaceX 2Q26 10-Q · 명목 컴퓨트 전력</a>',
        f'• <a href="{SPACEX_Q2_RELEASE}">SpaceX 2Q26 실적발표 · 계약매출</a>',
        f'• <a href="{ANTHROPIC_OFFICIAL}">Anthropic · SpaceX 컴퓨트 파트너십</a>',
        f'• <a href="{SPACEXAI_ANTHROPIC}">SpaceXAI · Anthropic 파트너십</a>',
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (PENDING, ALERT, STATUS):
        p.unlink(missing_ok=True)

    old = load_state()
    official = official_snapshot()
    fx = fx_snapshot(old)
    news, news_errors = search_news()
    sec_rows, sec_errors = sec_recent()
    errors = news_errors + sec_errors

    baseline = not old.get("initialized")
    format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
    changes = official_changes(old, official)

    old_news = set(old.get("seen_news_ids", []))
    old_sec = set(old.get("seen_sec_accessions", []))
    new_news = [] if baseline else [x for x in news if x["id"] not in old_news]
    new_sec = [] if baseline else [x for x in sec_rows if x["id"] not in old_sec]
    should_alert = baseline or format_upgrade or bool(changes) or bool(new_news) or bool(new_sec)

    pending = {
        "initialized": True,
        "format_version": FORMAT_VERSION,
        "official": official,
        "reported_context": CURRENT_REPORTED_CONTEXT,
        "seen_news_ids": list(dict.fromkeys(old.get("seen_news_ids", []) + [x["id"] for x in news]))[-2000:],
        "seen_sec_accessions": list(dict.fromkeys(old.get("seen_sec_accessions", []) + [x["id"] for x in sec_rows]))[-500:],
        "fx": fx,
        "last_changes": changes[:20],
        "last_new_news": new_news[:20],
        "last_new_sec": new_sec[:20],
        "errors": errors[:20],
        "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if should_alert:
        ALERT.write_text(render(official, changes, new_news, new_sec, fx, baseline or format_upgrade), encoding="utf-8")

    STATUS.write_text(
        "# SpaceXAI 외부 컴퓨트·네오클라우드 감시\n\n"
        f"- 확정 Anthropic 월요금: **${official['anthropic']['monthly_usd_b']:.2f}B**\n"
        f"- 확정 Google 월요금: **${official['google']['monthly_usd_b']:.2f}B**\n"
        f"- AI 명목 컴퓨트 전력: **{official['spacex_ai']['nameplate_compute_draw_gw']:.1f}GW**\n"
        f"- 신규 확정 변화: **{len(changes)}건**\n"
        f"- 신규 SEC 후보: **{len(new_sec)}건**\n"
        f"- 신규 보도 후보: **{len(new_news)}건**\n"
        f"- 알림: **{'예' if should_alert else '아니오'}**\n"
        f"- 오류: **{'; '.join(errors) if errors else '없음'}**\n",
        encoding="utf-8",
    )
    print(
        f"spacexai_neocloud baseline={baseline} format_upgrade={format_upgrade} "
        f"changes={len(changes)} new_sec={len(new_sec)} new_news={len(new_news)} "
        f"alert={should_alert} errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
