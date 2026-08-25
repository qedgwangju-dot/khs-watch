from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rubin_hbm_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
FX_URL = "https://api.frankfurter.dev/v2/rate/USD/KRW"

OFFICIAL_RUBIN_GB = 288
RUMORED_ULTRA_GB = 192
BREAKEVEN_GPU_GROWTH = OFFICIAL_RUBIN_GB / RUMORED_ULTRA_GB - 1
BASE_NVLINK_GPU = 72
ULTRA_NVLINK_GPU = 576
BASE_SYSTEM_GB = BASE_NVLINK_GPU * OFFICIAL_RUBIN_GB
ULTRA_SYSTEM_GB = ULTRA_NVLINK_GPU * RUMORED_ULTRA_GB
SYSTEM_HBM_GROWTH = ULTRA_SYSTEM_GB / BASE_SYSTEM_GB - 1
SEND_FRESHNESS_HOURS = 72

QUERIES = [
    (
        "rubin_spec",
        '"Rubin Ultra" (HBM OR HBM4 OR HBM4E OR 192GB OR 288GB OR 1TB OR 8-Hi OR 12-Hi)',
    ),
    (
        "hbm4e_validation",
        'HBM4E (qualification OR validation OR sample OR mass production OR production) (Samsung OR "SK hynix" OR Micron)',
    ),
    (
        "rubin_shipments",
        '"Rubin Ultra" (NVL576 OR shipment OR production OR deployment OR order OR ramp OR customer)',
    ),
    (
        "hbm_2027_contract",
        '2027 HBM (contract OR price OR pricing OR LTA OR supply OR allocation OR volume) (Samsung OR "SK hynix" OR Micron OR NVIDIA)',
    ),
    (
        "memory_migration",
        '(Rubin OR "Rubin Ultra" OR HBM) (DDR5 OR SOCAMM2 OR eSSD OR "enterprise SSD" OR "KV cache" OR offload OR pooling)',
    ),
]

CATEGORY_KO = {
    "rubin_spec": "Rubin Ultra 최종 HBM 사양",
    "hbm4e_validation": "HBM4E 고객 검증·양산",
    "rubin_shipments": "Rubin Ultra·NVL576 실제 출하",
    "hbm_2027_contract": "2027 HBM 계약가격·물량",
    "memory_migration": "DDR5·SOCAMM2·기업용 eSSD 이동",
}

OFFICIAL_SOURCE_HINTS = (
    "nvidia", "samsung newsroom", "삼성전자 뉴스룸", "sk hynix", "sk하이닉스 뉴스룸",
    "micron technology", "micron newsroom",
)
TRUSTED_SOURCE_HINTS = (
    "trendforce", "reuters", "bloomberg", "the information", "semianalysis", "digitimes",
    "tom's hardware", "toms hardware", "financial times", "wall street journal", "wsj", "cnbc",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def rss_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def parse_pubdate(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def relevant(category: str, text: str) -> bool:
    low = text.lower()
    if category == "rubin_spec":
        return "rubin ultra" in low and any(k in low for k in ("hbm", "192gb", "288gb", "1tb", "8-hi", "8hi", "12-hi", "12hi"))
    if category == "hbm4e_validation":
        return "hbm4e" in low and any(k in low for k in ("samsung", "sk hynix", "sk하이닉스", "micron")) and any(k in low for k in ("qualification", "validation", "sample", "mass production", "production", "양산", "검증", "샘플"))
    if category == "rubin_shipments":
        return ("rubin ultra" in low or "nvl576" in low) and any(k in low for k in ("shipment", "ship", "production", "deployment", "order", "ramp", "customer", "출하", "양산", "도입", "주문"))
    if category == "hbm_2027_contract":
        return "2027" in low and "hbm" in low and any(k in low for k in ("contract", "price", "pricing", "lta", "supply", "allocation", "volume", "계약", "가격", "공급", "물량"))
    if category == "memory_migration":
        return any(k in low for k in ("rubin", "hbm")) and any(k in low for k in ("ddr5", "socamm2", "essd", "enterprise ssd", "kv cache", "offload", "pooling", "오프로드", "풀링"))
    return False


def source_quality(source: str, title: str = "") -> str:
    low = (source or "").lower().strip()
    if any(k in low for k in OFFICIAL_SOURCE_HINTS):
        return "공식·회사자료"
    if any(k in low for k in TRUSTED_SOURCE_HINTS):
        return "신뢰 리서치·보도"
    return "일반 보도 — 추가 교차검증 필요"


def quality_rank(value: str) -> int:
    if value.startswith("공식"):
        return 3
    if value.startswith("신뢰"):
        return 2
    return 1


def normalized_title(title: str) -> str:
    value = clean_text(title).lower()
    # Google News titles usually append the publisher after the final ' - '.
    if " - " in value:
        value = value.rsplit(" - ", 1)[0]
    value = re.sub(r"[^a-z0-9가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def event_id(category: str, title: str, link: str) -> str:
    raw = f"{category}|{title}|{link}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def dedupe_events(events: list[dict]) -> list[dict]:
    chosen: dict[tuple[str, str], dict] = {}
    for e in events:
        key = (e.get("category") or "", normalized_title(e.get("title") or ""))
        old = chosen.get(key)
        if old is None:
            chosen[key] = e
            continue
        new_rank = quality_rank(e.get("quality") or "")
        old_rank = quality_rank(old.get("quality") or "")
        if new_rank > old_rank:
            chosen[key] = e
        elif new_rank == old_rank and (e.get("published_at_kst") or "") > (old.get("published_at_kst") or ""):
            chosen[key] = e
    return sorted(chosen.values(), key=lambda x: x.get("published_at_kst") or "")


def is_fresh_for_send(event: dict, now: datetime) -> bool:
    raw = event.get("published_at_kst") or ""
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return False
    return now - timedelta(hours=SEND_FRESHNESS_HOURS) <= dt <= now + timedelta(minutes=10)


def read_feed(category: str, query: str, lang: str) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    out: list[dict] = []
    url = rss_url(query, lang)
    try:
        root = ET.fromstring(fetch(url))
        for item in root.findall("./channel/item"):
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            desc = clean_text(item.findtext("description") or "")
            pub = clean_text(item.findtext("pubDate") or "")
            source_node = item.find("source")
            source = clean_text(source_node.text if source_node is not None and source_node.text else "")
            text = f"{title} {desc}"
            if not title or not link or not relevant(category, text):
                continue
            dt = parse_pubdate(pub)
            out.append({
                "id": event_id(category, title, link),
                "category": category,
                "title": title,
                "link": link,
                "source": source or "출처 미표시",
                "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
                "description": desc[:700],
                "quality": source_quality(source, title),
                "lang": lang,
            })
    except Exception as e:
        errors.append(f"{category}/{lang}: {type(e).__name__}: {e}")
    return out, errors


def fetch_fx() -> dict:
    result = {"rate": None, "date": "", "error": ""}
    try:
        obj = json.loads(fetch(FX_URL).decode("utf-8"))
        result["rate"] = float(obj.get("rate"))
        result["date"] = str(obj.get("date") or "")
    except Exception as e:
        result["error"] = f"USD/KRW 조회 실패: {type(e).__name__}: {e}"
    return result


def load_state() -> tuple[dict, bool]:
    if not DATA.exists():
        return {}, True
    try:
        return json.loads(DATA.read_text(encoding="utf-8")), False
    except Exception:
        return {}, True


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt_krw_usd(value: float, rate: float | None) -> str:
    if rate is None:
        return "원화 환산 불가"
    won = value * rate
    return f"약 {won:,.0f}원"


def extract_price_notes(text: str, rate: float | None) -> list[str]:
    notes: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*(GB|Gb)", text, re.I):
        usd = float(m.group(1))
        unit = m.group(2)
        key = f"{usd}/{unit}"
        if key not in seen:
            seen.add(key)
            notes.append(f"• 가격 환산: ${usd:g}/{unit} = {fmt_krw_usd(usd, rate)}/{unit}")
    for m in re.finditer(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(B|M)\b", text, re.I):
        val = float(m.group(1)) * (1_000_000_000 if m.group(2).upper() == "B" else 1_000_000)
        key = f"{val}usd"
        if key not in seen:
            seen.add(key)
            if rate is not None:
                won = val * rate
                eok = int(round(won / 100_000_000))
                if eok >= 10000:
                    jo, rem = divmod(eok, 10000)
                    krw = f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
                else:
                    krw = f"약 {eok:,}억원"
            else:
                krw = "원화 환산 불가"
            notes.append(f"• 금액 환산: {m.group(0)} = {krw}")
    return notes


def interpretation(category: str, text: str) -> list[str]:
    low = text.lower()
    lines: list[str] = []
    if category == "rubin_spec":
        lines.append("• 판정 기준: GPU당 HBM 용량 감소와 HBM 대역폭 유지 여부를 분리합니다.")
        if "192gb" in low:
            lines.append(f"• 288GB→192GB라면 GPU당 HBM은 -{(1-RUMORED_ULTRA_GB/OFFICIAL_RUBIN_GB)*100:.1f}%, 이를 상쇄하려면 GPU 출하가 최소 +{BREAKEVEN_GPU_GROWTH*100:.1f}% 필요합니다.")
            lines.append(f"• 72×288GB={BASE_SYSTEM_GB:,}GB 대비 576×192GB={ULTRA_SYSTEM_GB:,}GB라면 시스템 전체 HBM은 +{SYSTEM_HBM_GROWTH*100:.1f}%입니다. 단, 실제 NVL576 배치가 전제입니다.")
    elif category == "hbm4e_validation":
        lines.append("• 판정 기준: 샘플 출하와 고객 인증 완료·양산 개시는 구분합니다. 인증 지연이면 8단/저용량 사양 고착 위험이 커집니다.")
    elif category == "rubin_shipments":
        lines.append(f"• 핵심 상쇄선: GPU당 288GB→192GB라면 총 HBM 비트 수요를 유지하려면 GPU 출하량이 최소 +{BREAKEVEN_GPU_GROWTH*100:.1f}% 증가해야 합니다.")
    elif category == "hbm_2027_contract":
        lines.append("• 판정 기준: 계약가격 상승 + 계약물량 유지/증가가 동시에 나오면 HBM 공급자 가격결정력 확인으로 봅니다.")
    elif category == "memory_migration":
        lines.append("• 판정 기준: HBM의 초고대역폭 역할과 DDR5·SOCAMM2·기업용 eSSD의 용량 보완 역할을 구분합니다. 이동한 비트가 전부 1:1로 대체된다고 가정하지 않습니다.")
    return lines


def build_alert(now: datetime, events: list[dict], fx: dict) -> str:
    rate = fx.get("rate")
    lines = [
        "🚨 Rubin/HBM 구조 변화 감시",
        "",
        f"조회시각: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"신규 핵심 변화: {len(events)}건",
        f"기준선: 일반 Rubin 288GB HBM4 / 디스펙 상쇄선 GPU 출하 +{BREAKEVEN_GPU_GROWTH*100:.0f}%",
    ]
    if rate is not None:
        lines.append(f"원화 환산: 1달러={rate:,.2f}원 / 기준일 {fx.get('date') or '미표시'}")

    grouped: dict[str, list[dict]] = {}
    for e in events:
        grouped.setdefault(e["category"], []).append(e)

    n = 1
    for category in ("rubin_spec", "hbm4e_validation", "rubin_shipments", "hbm_2027_contract", "memory_migration"):
        group = grouped.get(category) or []
        if not group:
            continue
        lines += ["", f"■ {CATEGORY_KO[category]}"]
        for e in group[:5]:
            text = f"{e['title']} {e.get('description') or ''}"
            lines += [
                f"{n}. {e['title']}",
                f"- 출처: {e['source']} / {e['quality']}",
                f"- 공개시각: {e.get('published_at_kst') or '확인 불가'}",
            ]
            lines += interpretation(category, text)
            lines += extract_price_notes(text, rate)
            lines.append(f"- 원문: {e['link']}")
            n += 1

    lines += [
        "",
        "■ 자동 판정 원칙",
        "• 192GB 확정만으로 HBM 수요 붕괴로 판정하지 않습니다.",
        f"• GPU당 288→192GB(-33.3%)일 때 GPU 출하가 +{BREAKEVEN_GPU_GROWTH*100:.0f}% 이상이면 총 HBM 비트 수요는 상쇄 가능합니다.",
        "• HBM4E 인증·양산, 2027 계약가격·물량, NVL576 실제 배치, DDR5·SOCAMM2·기업용 eSSD 이동을 함께 봅니다.",
        "• 공식자료와 신뢰 보도가 충돌하면 '미확정'으로 표시하고 단정하지 않습니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    history_cutoff = now - timedelta(days=14)
    state, first_run = load_state()
    seen_before = set(state.get("seen_ids") or [])

    raw_events_by_id: dict[str, dict] = {}
    errors: list[str] = []
    for category, query in QUERIES:
        for lang in ("en", "ko"):
            events, errs = read_feed(category, query, lang)
            errors.extend(errs)
            for e in events:
                try:
                    dt = datetime.fromisoformat(e["published_at_kst"])
                    if dt < history_cutoff:
                        continue
                except Exception:
                    pass
                raw_events_by_id[e["id"]] = e

    raw_events = sorted(raw_events_by_id.values(), key=lambda x: x.get("published_at_kst") or "")
    current_ids = {e["id"] for e in raw_events}
    unseen_raw = [e for e in raw_events if e["id"] not in seen_before]
    fresh_unseen = [e for e in unseen_raw if is_fresh_for_send(e, now)]
    new_events = dedupe_events(fresh_unseen)

    fx = fetch_fx()
    if fx.get("error"):
        errors.append(fx["error"])

    # 첫 실행은 기존 기사 폭탄을 막기 위해 기준선만 저장한다.
    send_events = [] if first_run else new_events

    pending = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted((seen_before | current_ids))[-1200:],
        "last_unseen_raw_count": len(unseen_raw),
        "last_new_event_count": len(new_events),
        "last_send_event_count": len(send_events),
        "freshness_hours": SEND_FRESHNESS_HOURS,
        "usdkrw": fx,
        "errors": errors,
    }
    write_json(OUT / "rubin_hbm_pending_state.json", pending)

    if first_run:
        (OUT / "rubin_hbm_rebaseline.txt").write_text(
            f"Initial baseline at {now.isoformat(timespec='seconds')}; {len(raw_events)} recent items stored; no Telegram alert sent.\n",
            encoding="utf-8",
        )

    if send_events:
        send_events = send_events[-12:]
        (OUT / "rubin_hbm_alert.md").write_text(build_alert(now, send_events, fx), encoding="utf-8")

    status = [
        "# Rubin HBM Watch",
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}",
        f"- first_run_baseline: {str(first_run).lower()}",
        f"- recent_raw_events: {len(raw_events)}",
        f"- unseen_raw_events: {len(unseen_raw)}",
        f"- fresh_deduped_events: {len(new_events)}",
        f"- send_events: {len(send_events)}",
        f"- freshness_hours: {SEND_FRESHNESS_HOURS}",
        f"- break_even_gpu_growth: {BREAKEVEN_GPU_GROWTH*100:.1f}%",
        f"- base_system_hbm_gb: {BASE_SYSTEM_GB}",
        f"- ultra_system_hbm_gb_if_192: {ULTRA_SYSTEM_GB}",
        f"- source_errors: {len(errors)}",
    ]
    for e in errors[:8]:
        status.append(f"  - {e}")
    (OUT / "rubin_hbm_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
