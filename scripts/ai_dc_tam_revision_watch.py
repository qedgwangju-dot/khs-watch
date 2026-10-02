#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "ai_dc_tam_revision_state.json"
OUT = ROOT / "out"
ALERT = OUT / "ai_dc_tam_revision_alert.txt"
PENDING = OUT / "ai_dc_tam_revision_pending_state.json"
STATUS = OUT / "ai_dc_tam_revision_status.md"

KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 khs-ai-dc-tam-watch/1.0"
GOOGLE_NEWS = "https://news.google.com/rss/search"

BASELINE = {
    "source": "BofA Global Research 2차 공개보도 기준",
    "as_of": "2026-10-01",
    "ai_dc_system_tam_2030_usd_t": 2.2,
    "ai_dc_system_tam_prior_usd_t": 1.8,
    "ai_dc_cagr_pct": 40.0,
    "server_cpu_tam_2030_usd_b": 210.6,
    "server_cpu_tam_2026_usd_b": 61.4,
    "cloud_capex_2026_usd_t": 1.0,
    "cloud_capex_2027_usd_t": 1.4,
    "cloud_capex_2030_low_usd_t": 2.0,
    "cloud_capex_2030_high_usd_t": 3.0,
    "training_cpu_per_gpu": 0.25,
    "agentic_cpu_per_gpu": 1.0,
}

QUERIES = (
    'BofA AI data center systems market 2030',
    'Bank of America data center systems TAM AI 2030',
    'BofA server CPU 2030 agentic AI',
    'BofA cloud capex 2027 AI infrastructure',
    'Vivek Arya AI data center systems 2030',
)

SEED_URLS = (
    ("Yahoo Finance", "https://ca.finance.yahoo.com/news/ai-spending-will-fuel-wins-for-micron-nvidia-intel-and-other-chip-stocks-bofa-analyst-193925832.html"),
    ("Investing.com", "https://www.investing.com/news/stock-market-news/bofa-lifts-server-cpu-tam-to-210bn-on-the-rise-of-ai-agents-4857499?ampMode=1"),
    ("Finvaulta", "https://finvaulta.com/research/bank-of-america/rise-of-the-agents-raising-cpu-tam-again-to-210bn-2026-08-12"),
    ("StreetSignal", "https://streetsignal.substack.com/p/streetsignal-morning-call-9302026-09e"),
)

TRUSTED = (
    "Investing.com", "Yahoo Finance", "Reuters", "Bloomberg", "CNBC",
    "Financial Times", "Barron's", "MarketWatch",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def gnews_url(query: str) -> str:
    return GOOGLE_NEWS + "?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def decode_news(url: str) -> str:
    if "news.google.com" not in url:
        return url
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(url, interval=0.1)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http"):
                return decoded
    except Exception:
        pass
    return ""


def parse_date(value: str):
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def trusted_source(source: str) -> bool:
    low = source.lower()
    return any(x.lower() in low for x in TRUSTED)


def article_text(url: str) -> str:
    if not url:
        return ""
    try:
        return clean(fetch(url, 18).decode("utf-8", errors="ignore"))[:45000]
    except Exception:
        return ""


def collect(now: datetime) -> list[dict]:
    out = []
    cutoff = now - timedelta(days=90)
    for query in QUERIES:
        try:
            root = ET.fromstring(fetch(gnews_url(query), 20))
        except Exception:
            continue
        for item in root.findall("./channel/item")[:30]:
            title = clean(item.findtext("title") or "")
            desc = clean(item.findtext("description") or "")
            link = clean(item.findtext("link") or "")
            source_node = item.find("source")
            source = clean(source_node.text if source_node is not None else "")
            pub = parse_date(clean(item.findtext("pubDate") or ""))
            if pub and pub < cutoff:
                continue
            if not trusted_source(source):
                continue
            direct = decode_news(link)
            body = article_text(direct)
            blob = clean(f"{title} {desc} {body}")
            low = blob.lower()
            if "bofa" not in low and "bank of america" not in low and "vivek arya" not in low:
                continue
            if "data center" not in low and "server cpu" not in low and "cloud capex" not in low:
                continue
            ident = hashlib.sha256((direct or link or title).encode("utf-8")).hexdigest()[:24]
            out.append({
                "id": ident,
                "title": title,
                "source": source,
                "url": direct or link,
                "published_at": pub.isoformat() if pub else "",
                "text": blob,
            })
    for source, url in SEED_URLS:
        try:
            blob = article_text(url)
            if not blob:
                continue
            low = blob.lower()
            if "bofa" not in low and "bank of america" not in low and "vivek arya" not in low:
                continue
            ident = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
            out.append({
                "id": ident,
                "title": clean(blob[:220]),
                "source": source,
                "url": url,
                "published_at": "",
                "text": blob,
            })
        except Exception:
            pass

    uniq = {}
    for row in out:
        uniq[row["id"]] = row
    return list(uniq.values())


def num(s: str) -> float | None:
    try:
        return float(str(s).replace(",", ""))
    except Exception:
        return None


def extract_metrics(text: str) -> dict:
    low = text.lower()
    out = {}
    if "bofa" not in low and "bank of america" not in low and "vivek arya" not in low:
        return out

    patterns = [
        ("ai_dc_system_tam_2030_usd_t", [
            r"(?:2030[^.]{0,120}?)?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)[^.]{0,120}?(?:data center systems|ai data center|data-center systems)",
            r"(?:data center systems|ai data center|data-center systems)[^.]{0,120}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)[^.]{0,80}?2030",
        ], 0.5, 5.0),
        ("server_cpu_tam_2030_usd_b", [
            r"(?:server cpu|cpu)[^.]{0,120}?(?:2030[^.]{0,80}?)?\$?([0-9]{2,4}(?:\.[0-9]+)?)\s*(?:billion|bn)",
            r"\$?([0-9]{2,4}(?:\.[0-9]+)?)\s*(?:billion|bn)[^.]{0,120}?(?:server cpu|cpu)[^.]{0,80}?2030",
        ], 50, 600),
        ("cloud_capex_2026_usd_t", [
            r"2026[^.]{0,100}?(?:capex|capital spending)[^.]{0,80}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)",
            r"(?:capex|capital spending)[^.]{0,80}?2026[^.]{0,80}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)",
        ], 0.3, 3.0),
        ("cloud_capex_2027_usd_t", [
            r"2027[^.]{0,100}?(?:capex|capital spending)[^.]{0,80}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)",
            r"(?:capex|capital spending)[^.]{0,80}?2027[^.]{0,80}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)",
        ], 0.3, 4.0),
    ]
    for key, pats, lo, hi in patterns:
        for pat in pats:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            v = num(m.group(1))
            if v is not None and lo <= v <= hi:
                out[key] = v
                break

    m = re.search(r"(?:annual pace|cagr|annual growth)[^.]{0,50}?([0-9]{1,2}(?:\.[0-9]+)?)%", text, re.I)
    if m:
        v = num(m.group(1))
        if v and 10 <= v <= 80:
            out["ai_dc_cagr_pct"] = v

    if re.search(r"(?:1\s*:\s*4|one cpu for every four gpus|four gpus.*one cpu)", text, re.I):
        out["training_cpu_per_gpu"] = 0.25
    if re.search(r"(?:1\s*:\s*1|one-to-one|1-to-1)", text, re.I) and ("agent" in low or "agentic" in low):
        out["agentic_cpu_per_gpu"] = 1.0
    return out


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def pct(new: float, old: float) -> float:
    return (new / old - 1) * 100 if old else 0.0


def fetch_fx() -> dict:
    from fx_api import daily_krw, historical_krw
    try:
        q = daily_krw()
        quality = "교차검증 일일 기준환율"
    except Exception as exc:
        target = datetime.now(timezone.utc).astimezone(KST).date()
        q = historical_krw("USD", target)
        quality = f"ECB 일일 기준환율 · 보조 검증 실패 대체 ({type(exc).__name__})"
    return {
        "usdkrw": float(q.rate),
        "basis": q.basis,
        "source": q.source,
        "quality": quality,
    }


def krw_from_usd_t(value_t: float, fx: float) -> str:
    won = value_t * 1_000_000_000_000 * fx
    eok = int(round(won / 100_000_000))
    jo, rem = divmod(eok, 10000)
    return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"


def krw_from_usd_b(value_b: float, fx: float) -> str:
    won = value_b * 1_000_000_000 * fx
    eok = int(round(won / 100_000_000))
    jo, rem = divmod(eok, 10000)
    return f"약 {jo:,}조{rem:,}억원" if jo and rem else (f"약 {jo:,}조원" if jo else f"약 {eok:,}억원")


def material_changes(old: dict, new: dict) -> list[dict]:
    rules = {
        "ai_dc_system_tam_2030_usd_t": ("2030 AI 데이터센터 시스템 시장", "pct", 5.0),
        "ai_dc_cagr_pct": ("AI 데이터센터 시스템 성장률", "pp", 3.0),
        "server_cpu_tam_2030_usd_b": ("2030 서버 CPU 시장", "pct", 10.0),
        "cloud_capex_2026_usd_t": ("2026 클라우드 설비투자", "pct", 10.0),
        "cloud_capex_2027_usd_t": ("2027 클라우드 설비투자", "pct", 10.0),
        "agentic_cpu_per_gpu": ("에이전틱 AI CPU/GPU 비율", "abs", 0.25),
    }
    out = []
    for key, (label, mode, threshold) in rules.items():
        if key not in old or key not in new:
            continue
        before, after = float(old[key]), float(new[key])
        delta = after - before if mode in {"pp", "abs"} else pct(after, before)
        if abs(delta) >= threshold:
            out.append({"key": key, "label": label, "before": before, "after": after, "delta": delta, "mode": mode})
    return out


def fmt(key: str, value: float, fx: float | None = None) -> str:
    if key.endswith("_usd_t"):
        base = f"{value:.2f}조달러"
        return f"{base} ({krw_from_usd_t(value, fx)})" if fx else base
    if key.endswith("_usd_b"):
        base = f"{value:,.1f}억달러" if value < 100 else f"{value:,.0f}억달러"
        return f"{base} ({krw_from_usd_b(value, fx)})" if fx else base
    if key.endswith("_pct"):
        return f"{value:.1f}%"
    if "cpu_per_gpu" in key:
        return f"GPU 1개당 CPU {value:.2f}개"
    return f"{value:g}"


def build_alert(metrics: dict, changes: list[dict], evidence: list[dict], fx: dict) -> str:
    rate = float(fx["usdkrw"])
    lines = [
        "🚨 AI 데이터센터 시장규모·클라우드 설비투자 전망 변경",
        "",
        "▶ 핵심",
    ]
    for ch in changes[:6]:
        unit = "%p" if ch["mode"] == "pp" else ("개" if ch["mode"] == "abs" else "%")
        lines.append(f"• {ch['label']}: {fmt(ch['key'], ch['before'], rate)} → {fmt(ch['key'], ch['after'], rate)} ({ch['delta']:+.1f}{unit})")

    lines += [
        "",
        "■ 현재 기준",
        f"• 2030 AI 데이터센터 시스템 시장: {fmt('ai_dc_system_tam_2030_usd_t', metrics['ai_dc_system_tam_2030_usd_t'], rate)}",
        f"• 2030 서버 CPU 시장: {fmt('server_cpu_tam_2030_usd_b', metrics['server_cpu_tam_2030_usd_b'], rate)}",
        f"• 2026 클라우드 설비투자: {fmt('cloud_capex_2026_usd_t', metrics['cloud_capex_2026_usd_t'], rate)}",
        f"• 2027 클라우드 설비투자: {fmt('cloud_capex_2027_usd_t', metrics['cloud_capex_2027_usd_t'], rate)}",
        f"• 에이전틱 AI: GPU 1개당 CPU {metrics['agentic_cpu_per_gpu']:.2f}개 기준",
        "",
        "■ 의미",
        "• 이 알림은 데이터센터 건설 GW가 아니라 GPU·CPU·메모리·네트워크에 실제로 들어갈 시스템 지출 전망이 상향·하향되는지를 추적합니다.",
        "• 전력 병목 감시와 분리해 수요 측 전망 자체가 꺾이는지 먼저 확인합니다.",
        "• BofA 리포트 원문이 공개되지 않는 경우 신뢰 보도에 나온 수치를 증권사 추정으로만 표시합니다.",
        "",
        "■ 원화 환산 기준",
        f"• 1달러 = {rate:,.2f}원",
        f"• 기준: {fx.get('basis','확인 불가')}",
        f"• 출처: {fx.get('source','확인 불가')} · {fx.get('quality','')}",
    ]
    if evidence:
        source_ko = {
            "Yahoo Finance": "야후 파이낸스",
            "Investing.com": "인베스팅닷컴",
            "Finvaulta": "핀볼타",
            "StreetSignal": "스트리트시그널",
            "Reuters": "로이터",
            "Bloomberg": "블룸버그",
            "CNBC": "CNBC",
            "Financial Times": "파이낸셜타임스",
            "Barron's": "배런스",
            "MarketWatch": "마켓워치",
        }
        lines += ["", "■ 확인 자료"]
        for row in evidence[:4]:
            lines.append(f"• {source_ko.get(row['source'], '신뢰 자료')}: 전망 변경 근거 확인")
            if row.get("url"):
                lines.append(f"원문: {row['url']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (ALERT, PENDING, STATUS):
        p.unlink(missing_ok=True)

    now = datetime.now(timezone.utc)
    old = load_state()
    first = not bool(old)
    metrics = dict(old.get("metrics") or BASELINE)
    for k, v in BASELINE.items():
        if k in {"source", "as_of"}:
            continue
        metrics.setdefault(k, v)

    try:
        fx = fetch_fx()
    except Exception as exc:
        fx = {}
        print(f"ai_dc_tam_fx_error={type(exc).__name__}: {exc}")

    rows = collect(now)
    seen = set(old.get("seen_ids") or [])
    new_rows = [r for r in rows if r["id"] not in seen]

    # 본문 접근이 일시 실패해도 다음 실행에서 다시 숫자를 추출할 수 있도록
    # 신규 기사뿐 아니라 현재 조회 가능한 신뢰자료 전체를 매번 재검증한다.
    candidates = []
    for row in rows:
        parsed = extract_metrics(row["text"])
        if parsed:
            candidates.append((row, parsed))

    proposed = dict(metrics)
    evidence = []
    # 동일 숫자가 서로 다른 신뢰자료 2곳 이상에서 확인될 때만 기준을 갱신한다.
    # 과거 정적 기준과 새 전망이 동수면 게시시각이 더 최근인 전망을 우선한다.
    keys = set()
    for _, parsed in candidates:
        keys.update(parsed)

    def published_score(row: dict) -> float:
        raw = str(row.get("published_at") or "")
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    for key in keys:
        buckets = {}
        for row, parsed in candidates:
            if key not in parsed:
                continue
            v = round(float(parsed[key]), 4)
            buckets.setdefault(v, []).append(row)
        qualified = [(value, support) for value, support in buckets.items() if len(support) >= 2]
        if not qualified:
            continue
        value, support = max(
            qualified,
            key=lambda item: (max((published_score(r) for r in item[1]), default=0.0), len(item[1])),
        )
        proposed[key] = value
        evidence.extend(support)

    changes = material_changes(metrics, proposed)
    notify = bool(changes)

    pending = {
        "initialized": True,
        "metrics": proposed,
        "baseline_source": BASELINE["source"],
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "seen_ids": list(dict.fromkeys(list(seen) + [r["id"] for r in rows]))[-1000:],
        "fx": fx,
        "last_collection": {
            "trusted_rows": len(rows),
            "new_rows": len(new_rows),
            "candidate_metric_rows": len(candidates),
            "material_changes": len(changes),
        },
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if notify and not first:
        if not fx.get("usdkrw"):
            print("ai_dc_tam_alert_blocked_no_krw=true")
        else:
            ALERT.write_text(build_alert(proposed, changes, list({r["id"]: r for r in evidence}.values()), fx), encoding="utf-8")

    STATUS.write_text(
        "# AI 데이터센터 TAM·설비투자 전망 감시\n\n"
        f"- 최초 기준선: **{'예' if first else '아니오'}**\n"
        f"- 신뢰자료 수집: **{len(rows)}건**\n"
        f"- 신규 자료: **{len(new_rows)}건**\n"
        f"- 숫자 후보: **{len(candidates)}건**\n"
        f"- 중요 전망 변경: **{len(changes)}건**\n"
        f"- 알림: **{'예' if notify and not first else '아니오'}**\n",
        encoding="utf-8",
    )
    print(f"ai_dc_tam_watch first={first} rows={len(rows)} candidates={len(candidates)} changes={len(changes)} alert={notify and not first}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
