#!/usr/bin/env python3
"""Samsung MX smartphone production and component-order reduction watch.

A separate *module* in the existing memory-market Telegram workflow.
A supply-chain report is never equivalent to an official Samsung production plan.
The underlying quarter, quantity kind (production / shipment / supplier order),
reported range, and confirmation tier are recorded independently.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "samsung_mx_production_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
PENDING = OUT / "samsung_mx_production_watch_pending_state.json"
STATUS = OUT / "samsung_mx_production_watch_status.md"
FRAGMENT = OUT / "samsung_mx_production_watch_alert.html"
TELEGRAM = OUT / "memory_spot_cycle_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")

FIRST_REPORT_KST = dt.datetime(2026, 10, 8, 4, 0, tzinfo=KST)
ARTICLE = "https://www.mt.co.kr/tech/2026/10/08/2026100709554237233"
IDC_SOURCE = "https://www.idc.com/promo/smartphone-market-share/"
SAMSUNG_Q2 = "https://news.samsung.com/global/samsung-electronics-announces-second-quarter-2026-results"
SAMSUNG_Q3_GUIDANCE = "https://news.samsung.com/global/samsung-electronics-announces-earnings-guidance-for-third-quarter-2026"
TRENDFORCE_LPDDR = "https://www.trendforce.com/presscenter/news/20260514-13044.html"

BASELINE = {
    "period": "2026Q4",
    "production_cut_max_pct": 30.0,
    "production_cut_base": "비교 기준·감축 전 목표물량 비공개",
    "production_status": "머니투데이 복수 업계 관계자 인용·삼성 공식 미확정",
    "supplier_order_cut_min_pct": 20.0,
    "supplier_order_cut_max_pct": 30.0,
    "supplier_order_status": "협력사 납품량 감축 요청에 대한 언론 보도",
    "idc_q2_actual_shipments_m": 62.7,
    "q3_forecast_m_article": 59.0,
    "q4_forecast_m_article": 52.0,
    "forecast_source": "머니투데이가 IDC 추정으로 인용·IDC 공개 원표에서는 Q4 예측 직접 미확인",
    "mx_network_q2_op_krw_eok": -7000,
    "mx_network_q2_status": "삼성전자 공식 2분기 실적",
    "mx_network_q3_op_est_krw_eok": -19000,
    "mx_network_q3_status": "메리츠증권 추정·삼성 공식 미확정",
}
BASE_FACTS = [
    "samsung_2026q4_production_cut_30_reported",
    "samsung_2026q4_supplier_order_cut_20_30_reported",
    "samsung_2026q4_q4_forecast_52m_article",
]

SEARCHES = [
    ("ko", '"삼성전자" "4분기" 스마트폰 생산량 30% 감축'),
    ("ko", '"삼성전자" 협력사 납품 20 30% 감축 무선사업부'),
    ("ko", '삼성 갤럭시 생산계획 축소 부품 발주 감축 메모리'),
    ("ko", '삼성 MX사업부 4분기 생산량 수정 출하량 IDC'),
    ("ko", '삼성전자 스마트폰 생산 감축 부인 해명 공식'),
    ("en", 'Samsung Q4 2026 smartphone production cut 30 percent memory'),
    ("en", 'Samsung smartphone component supplier purchase orders cut 20 30 percent'),
    ("en", 'Samsung MX Q4 production plan revised memory cost shipments IDC'),
]

HIGH = (
    "reuters", "bloomberg", "financial times", "wall street journal", "wsj",
    "yonhap", "연합뉴스", "idc", "counterpoint", "trendforce", "omdia",
)
MID = (
    "머니투데이", "moneytoday", "mt.co.kr", "한국경제", "매일경제",
    "전자신문", "etnews", "zdnet", "the elec", "서울경제", "파이낸셜뉴스",
    "fnnews", "조선비즈", "businesskorea", "digitimes",
)
LOW = (
    "notebookcheck", "wccftech", "reddit", "note.com", "technobezz",
)
MX_WORDS = (
    "samsung", "galaxy", "삼성전자", "삼성", "갤럭시", "mx사업부",
    "mx division", "mobile experience",
)
PHONE_WORDS = (
    "smartphone", "smartphones", "handset", "handsets", "galaxy",
    "스마트폰", "휴대전화", "핸드셋", "휴대폰", "갤럭시",
)
PRODUCTION_WORDS = (
    "production", "manufacturing", "output", "builds", "build plan",
    "생산", "제조", "공장 가동",
)
SUPPLIER_WORDS = (
    "component orders", "component order", "supplier orders",
    "purchase order", "purchase orders", "parts orders", "supply volumes",
    "납품량", "협력사", "부품 발주", "발주량", "부품 주문", "공급량",
)
CUT_WORDS = (
    "cut", "cuts", "reduce", "reduces", "reduction", "lower", "lowered",
    "slash", "slashes", "scale back", "scaled back", "downsize",
    "감축", "축소", "줄이", "줄여", "줄인다", "줄일", "감소", "하향", "삭감",
)
DENIAL_WORDS = (
    "denies", "denied", "no plan to cut", "no production cut",
    "not cutting", "부인", "사실무근", "사실이 아니다", "감축 계획 없다",
)
Q4_WORDS = (
    "q4", "4q", "fourth quarter", "fourth-quarter", "4분기", "四季度",
)
UA = "Mozilla/5.0 (compatible; khs-samsung-mx-production/1.0)"


def _clean(value: str | None) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]*>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _fingerprint(item: dict) -> str:
    # This only skips identical headlines. Semantic facts are deduped separately.
    base = (_clean(item.get("title")).lower() + "|" +
            _clean(item.get("source")).lower())
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _rank(source: str) -> int:
    low = _clean(source).lower()
    if any(x in low for x in LOW):
        return 0
    if any(x in low for x in HIGH):
        return 3
    if any(x in low for x in MID):
        return 2
    return 1


def _official_url(item: dict) -> bool:
    # The word "Samsung" in a headline or a Reuters story is NOT an
    # official Samsung disclosure. Google News redirects are not official URLs.
    host = (urlparse(item.get("link") or "").hostname or "").lower()
    return host in ("news.samsung.com", "samsung.com", "www.samsung.com")


def _published(raw: str | None) -> dt.datetime | None:
    try:
        value = parsedate_to_datetime(raw or "")
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(KST)
    except Exception:
        return None


def _rss(lang: str, query: str) -> str:
    geo = {"hl": "ko", "gl": "KR", "ceid": "KR:ko"} if lang == "ko" else {
        "hl": "en-US", "gl": "US", "ceid": "US:en"
    }
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, **geo})


def _collect() -> tuple[list[dict], list[str]]:
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=12)
    items: dict[str, dict] = {}
    errors = []
    for lang, q in SEARCHES:
        try:
            req = urllib.request.Request(_rss(lang, q), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=22) as response:
                root = ET.fromstring(response.read())
        except Exception as exc:
            errors.append(f"{lang}: {type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title = _clean(node.findtext("title"))
            desc = _clean(node.findtext("description"))
            link = _clean(node.findtext("link"))
            sn = node.find("source")
            source = _clean(sn.text if sn is not None else "") or "출처 미표시"
            pub = _published(node.findtext("pubDate"))
            if not (title and link and pub and cutoff <= pub <= now + dt.timedelta(minutes=15)):
                continue
            if not any(w in f"{title} {desc}".lower() for w in MX_WORDS):
                continue
            item = {
                "title": title, "description": desc, "source": source,
                "link": link, "published_at_kst": pub.isoformat(timespec="seconds"),
            }
            items[_fingerprint(item)] = item
    return sorted(items.values(), key=lambda x: x["published_at_kst"]), errors


def _is_target_quarter(blob: str, date: dt.datetime) -> bool:
    low = blob.lower()
    if not any(q in low for q in Q4_WORDS):
        return False
    # Only infer the year for contemporary October 2026 articles; do not
    # interpret a 2027 Q4 report as 2026. Future periods get their own schema.
    if any(x in low for x in ("2027 q4", "2027q4", "2027년 4분기", "2025 q4")):
        return False
    return "2026" in low or (date.year == 2026 and date.month in (9, 10, 11, 12))


def _range_values(clause: str) -> list[tuple[float, float]]:
    values: list[tuple[float, float]] = []
    spans: list[tuple[int, int]] = []
    range_pat = r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*(?:~|～|–|—|-|to)\s*(\d{1,3}(?:\.\d+)?)\s*%"
    for match in re.finditer(range_pat, clause, re.I):
        lo, hi = float(match.group(1)), float(match.group(2))
        if 0 <= lo <= hi <= 100:
            values.append((lo, hi))
            spans.append(match.span())
    for match in re.finditer(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%", clause):
        if any(a <= match.start() < b for a, b in spans):
            continue
        value = float(match.group(1))
        if 0 <= value <= 100:
            values.append((value, value))
    return values


def _production_metrics(blob: str, date: dt.datetime) -> dict:
    low = _clean(blob).lower()
    if not any(w in low for w in MX_WORDS):
        return {}
    if not _is_target_quarter(low, date):
        return {}
    out: dict[str, tuple[float, float]] = {}
    # Evaluate facts clause-by-clause: a 175% MEMORY PRICE increase must not
    # become a 175% PHONE production cut.
    for clause in re.split(r"[!?;；。]|\s+\|\s+", low):
        if not any(w in clause for w in CUT_WORDS):
            continue
        supplier = any(w in clause for w in SUPPLIER_WORDS)
        production = any(w in clause for w in PRODUCTION_WORDS) and any(
            w in clause for w in PHONE_WORDS
        )
        kind = "supplier_orders" if supplier else ("finished_production" if production else "")
        if not kind:
            continue
        for lo, hi in _range_values(clause):
            if kind == "finished_production" and hi > 70:
                continue
            if kind == "supplier_orders" and hi > 70:
                continue
            old = out.get(kind)
            if old is None or hi > old[1]:
                out[kind] = (lo, hi)
    return out


def _event(item: dict, state: dict) -> dict | None:
    rank = _rank(item.get("source") or "")
    if rank < 2:
        return None
    date = dt.datetime.fromisoformat(item["published_at_kst"])
    blob = f"{item['title']} | {item.get('description','')}"
    low = blob.lower()
    if not _is_target_quarter(blob, date):
        return None

    official = _official_url(item)
    data = _production_metrics(blob, date)
    metrics = state.get("metrics") or {}
    reasons: list[str] = []
    updates: dict[str, object] = {}
    keys: list[str] = []
    stage = 0

    for kind, pair in data.items():
        lo, hi = pair
        if kind == "supplier_orders":
            prev = (
                float(metrics.get("supplier_order_cut_min_pct") or 0),
                float(metrics.get("supplier_order_cut_max_pct") or 0),
            )
            fact = f"samsung_2026q4_supplier_order_cut_{lo:g}_{hi:g}_" + (
                "official" if official else "reported"
            )
            material = max(abs(lo - prev[0]), abs(hi - prev[1])) >= 10
            if material or official:
                reasons.append(f"2026년 4분기 협력사 부품 납품·발주 축소 보도 {lo:g}~{hi:g}%")
                updates.update({
                    "supplier_order_cut_min_pct": lo,
                    "supplier_order_cut_max_pct": hi,
                })
                stage = max(stage, 3 if official else 2)
                keys.append(fact)
        elif kind == "finished_production":
            prev = float(metrics.get("production_cut_max_pct") or 0)
            fact = f"samsung_2026q4_production_cut_{hi:g}_" + (
                "official" if official else "reported"
            )
            material = abs(hi - prev) >= 10
            if material or official:
                reasons.append(f"2026년 4분기 스마트폰 완제품 생산 축소 {hi:g}% 보도")
                updates["production_cut_max_pct"] = hi
                stage = max(stage, 3 if official else 2)
                keys.append(fact)

    if official and ("생산" in low or "production" in low) and not data:
        if any(x in low for x in DENIAL_WORDS):
            reasons.append("삼성 공식 발표: 생산 축소 보도 부인·정정")
            stage = max(stage, 3)
            keys.append("samsung_2026q4_production_official_denial")

    # A high-trust press report is still not an official production target.
    if not reasons:
        return None
    if keys and set(keys).issubset(set(state.get("seen_fact_keys") or [])):
        return None
    return {
        "item": item, "rank": rank, "official": official,
        "stage": stage, "reasons": reasons,
        "changes": updates, "fact_keys": keys,
    }


def _baseline_alert() -> str:
    return "\n".join([
        "📉 <b>[삼성전자 MX 4분기 생산·부품 발주 축소 | 첫 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[2026년 10월 8일 언론 보도]</b>",
        "• 삼성전자 MX가 협력사에 <b>납품량 20~30% 축소를 요청</b>했다는 복수 관계자 인용 보도",
        "• 4분기 스마트폰 <b>생산량 최대 30% 축소 가능성</b> — 감축 전 기준 생산계획·해당 제품 구성 미공개",
        "• <b>🟡 공급망 보도 단계</b>. 삼성전자의 공식 확정 생산계획으로 취급하지 않음",
        "",
        "<b>[숫자 비교 — 지표를 섞지 않음]</b>",
        "• IDC 공식 2026년 2분기 삼성 브랜드 출하량: <b>6,270만대</b> (확정 관측치)",
        "• 기사 인용 IDC 3분기·4분기 수치: <b>5,900만대 → 5,200만대</b> (전망치·약 12% 감소)",
        "• 위 4분기 5,200만대 전망에 최대 30%를 또 차감한 숫자는 <b>확정 물량 아님</b>",
        "",
        "<b>[실적·원가 교차검증]</b>",
        "• 삼성전자 공식 2026년 2분기 MX·네트워크 영업손실 <b>7,000억원</b>, 부품 원가 압박 확인",
        "• 기사상 2026년 3분기 MX·네트워크 영업손실 <b>1조9,000억원</b>은 메리츠증권 추정으로 공식 실적이 아님",
        "• 삼성전자 3분기 잠정실적은 연결 매출 <b>195조원</b>·영업이익 <b>107조4,000억원</b>; 사업부 수치는 미공개",
        "• TrendForce 공식: 2026년 2분기 LPDDR5X 평균판매단가 전분기 대비 <b>78~83% 상승 전망</b>",
        "",
        "<b>[투자 파급과 실패 경로]</b>",
        "• 스마트폰용 메모리 가격결정력 강화와 완제품 업체 채산성 악화를 함께 추적",
        "• 생산량을 줄이면 카메라·인쇄회로기판·적층세라믹커패시터·디스플레이 구매물량도 둔화할 수 있으나",
        "  개별 협력사 수주 취소·공장 중단은 아직 확인하지 못함",
        "• 4분기 계절성·재고 조정·외주 생산 비중 조정과 실제 수요 급감은 분리해야 함",
        "",
        "<b>[다음 알림 조건]</b>",
        "• 삼성 공식 생산계획 확인·정정 또는 독립적인 신규 생산 감축 폭",
        "• 분기·제품군이 확인된 부품 발주 축소율의 10%포인트 이상 변경",
        "• IDC 실제 출하량 확인, 분기 전망 수정, 재고·고객사 발주 변화",
        "• MX 영업이익률 개선/악화가 공식 실적에서 확인되는지",
        "",
        f'<a href="{ARTICLE}">머니투데이 10월 8일 원보도</a>',
        f'<a href="{IDC_SOURCE}">IDC 2026년 2분기 공식 출하량</a>',
        f'<a href="{SAMSUNG_Q2}">삼성전자 2026년 2분기 공식 실적</a>',
        f'<a href="{SAMSUNG_Q3_GUIDANCE}">삼성전자 2026년 3분기 잠정실적</a>',
        f'<a href="{TRENDFORCE_LPDDR}">TrendForce 모바일 메모리 가격</a>',
    ]) + "\n"


def _change_alert(events: list[dict]) -> str:
    lines = [
        "📉 <b>[삼성전자 MX 스마트폰 생산·협력사 발주 | 신규 변화]</b>",
        "━━━━━━━━━━━━━━━━",
    ]
    for e in events[:2]:
        verdict = "🔴 삼성 공식 확인" if e["official"] else "🟠 새 공급망 물량 변화 보도"
        lines.append(f"• <b>{verdict}</b>: {html.escape(' / '.join(e['reasons']))}")
        it = e["item"]
        lines.append(f"  └ {html.escape(it['source'])} · {html.escape(it['published_at_kst'])}")
        lines.append(f'<a href="{html.escape(it["link"], quote=True)}">관련 원문</a>')
    lines += [
        "• 언론 보도, 협력사 발주량, 완제품 생산량, 시장조사기관 출하량은 서로 다른 지표입니다.",
        "• 생산량 변화가 개별 부품사의 매출 감소로 연결됐다는 사실은 주문·실적 확인 전까지 확정하지 않습니다.",
    ]
    return "\n".join(lines) + "\n"


def _append_alert(alert: str) -> None:
    if TELEGRAM.exists() and TELEGRAM.read_text(encoding="utf-8").strip():
        current = TELEGRAM.read_text(encoding="utf-8").rstrip()
        TELEGRAM.write_text(
            current + "\n\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n" + alert,
            encoding="utf-8",
        )
    else:
        TELEGRAM.write_text(alert, encoding="utf-8")


def _load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(state, dict):
            return state
    except Exception:
        pass
    return {
        "schema_version": 1, "initial_alert_sent": False,
        "seen": [], "seen_fact_keys": list(BASE_FACTS),
        "metrics": dict(BASELINE), "last_alert": None,
    }


def main() -> None:
    now = dt.datetime.now(KST)
    state = _load_state()
    known = set(state.get("seen") or [])
    keys = set(state.get("seen_fact_keys") or BASE_FACTS)
    metrics = dict(BASELINE)
    metrics.update(state.get("metrics") or {})
    items, errors = _collect()
    initial_pending = not bool(state.get("initial_alert_sent"))
    events = []

    for it in items:
        fid = _fingerprint(it)
        pub = dt.datetime.fromisoformat(it["published_at_kst"])
        if fid in known or pub <= FIRST_REPORT_KST:
            known.add(fid)
            continue
        if initial_pending:
            # Absorb existing articles at initial deployment. First baseline
            # contains only previously verified facts, not RSS-derived claims.
            known.add(fid)
            continue
        event = _event(it, {"metrics": metrics, "seen_fact_keys": list(keys)})
        known.add(fid)
        if event:
            events.append(event)
            metrics.update(event["changes"])
            keys.update(event["fact_keys"])

    events.sort(key=lambda e: (e["stage"], e["rank"], e["item"]["published_at_kst"]), reverse=True)
    state = {
        "schema_version": 1,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "initial_alert_sent": True,
        "baseline_at_kst": FIRST_REPORT_KST.isoformat(timespec="seconds"),
        "seen": sorted(known)[-700:],
        "seen_fact_keys": sorted(keys)[-200:],
        "metrics": metrics,
        "last_scan_items": len(items),
        "last_new_signal_count": len(events),
        "errors": errors[:15],
        "last_alert": (
            {"at_kst": now.isoformat(timespec="seconds"),
             "kind": "baseline" if initial_pending else "change"}
            if initial_pending or events else state.get("last_alert")
        ),
    }
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if initial_pending:
        alert = _baseline_alert()
        FRAGMENT.write_text(alert, encoding="utf-8")
        _append_alert(alert)
    elif events:
        alert = _change_alert(events)
        FRAGMENT.write_text(alert, encoding="utf-8")
        _append_alert(alert)
    else:
        FRAGMENT.unlink(missing_ok=True)

    STATUS.write_text(
        "# 삼성전자 MX 2026년 4분기 생산·발주 추적\n"
        f"- 조회: {now.isoformat(timespec='seconds')}\n"
        f"- 검색 기사: {len(items)}\n"
        f"- 신규 변화: {len(events)}\n"
        f"- 기준선 최초 송출: {str(initial_pending).lower()}\n"
        f"- 오류: {len(errors)}\n"
        "- 확정 분리: 공급망 보도 != 삼성 공식 생산계획 != IDC 실제 출하량\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
