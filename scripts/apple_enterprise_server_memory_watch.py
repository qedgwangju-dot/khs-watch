#!/usr/bin/env python3
"""Apple enterprise AI server and memory procurement change-only monitor.

Discovery: news RSS metadata; it is NOT a verified article body or an Apple filing.
Never equate NVLink Fusion with HBM purchase or an internal PCC server with
an externally sold M8 server. Never promote copied stories to independent sources.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data/apple_enterprise_server_memory_watch_state.json"
OUT = ROOT / "out"
PENDING = OUT / "apple_enterprise_server_memory_watch_pending_state.json"
ALERT = OUT / "apple_enterprise_server_memory_watch_telegram.txt"
STATUS = OUT / "apple_enterprise_server_memory_watch_status.md"
KST = ZoneInfo("Asia/Seoul")

SEARCHES = (
    ("ko", '"애플" "M8 Ultra" 서버'),
    ("ko", '"애플" "NVLink Fusion" 서버'),
    ("ko", '"애플" "M8" 서버 메모리'),
    ("ko", '애플 AI 추론 기업용 서버 HBM 조달 삼성전자 하이닉스'),
    ("ko", '애플 M8 서버 고객 계약 양산 출시 취소'),
    ("en", '"Apple" "M8 Ultra" "server"'),
    ("en", '"Apple" "NVLink Fusion" server'),
    ("en", '"Apple" "M8" HBM procurement order'),
    ("en", '"Apple" enterprise inference server DRAM contract'),
    ("en", '"Apple" M8 enterprise server design win customer launch'),
    ("en", '"Apple" "M8 Ultra" delayed cancelled tapeout'),
    ("en", '"Apple" inference server MLX enterprise management'),
    ("zh", '苹果 M8 Ultra 企业服务器 NVLink 合同 量产'),
)

OFFICIAL_PUBLISHERS = {
    "Apple", "Apple Newsroom", "NVIDIA", "NVIDIA Blog", "NVIDIA Newsroom",
    "SK hynix", "SK hynix Newsroom", "Micron", "Micron Technology",
    "Samsung Electronics", "삼성전자", "Broadcom", "TSMC",
}
HIGH_PUBLISHERS = {
    "The Information", "Reuters", "Bloomberg", "Financial Times", "The Wall Street Journal",
    "Nikkei Asia", "TrendForce", "SemiAnalysis", "Omdia",
}
SECONDARY_PUBLISHERS = {
    "Wallstreetcn", "华尔街见闻", "Futunn", "富途", "MacRumors",
    "DigiTimes", "The Elec", "ZDNet", "ZDNet Korea", "전자신문",
    "서울경제", "9to5Mac", "Tom's Hardware", "BusinessKorea",
    "Reuters via Investing.com",
}
BASELINE = {
    "m8_server": "2026-09-16 보도 단계: 기업용 AI 추론 서버 2칩·4칩형, 2029년 목표",
    "nvlink": "NVIDIA NVLink Fusion 협의·검토, 공식 채택 미확인",
    "memory": "Apple 기업용 M8 서버의 HBM·서버 DRAM 계약·양산 조달량 미확인",
    "pcc": "기존 Apple Private Cloud Compute 내부 서버는 외부 판매용 M8 프로젝트와 별개",
}
BASELINE_KEYS = ["server:reported:2or4:2029", "nvlink:talks", "memory:unconfirmed"]
APPLE = ("apple", "애플", "苹果")
M8 = ("m8 ultra", "m8울트라", "m8 울트라")
SERVER = ("server", "服务器", "서버", "enterprise", "기업용", "기업용서버")
NVLINK = ("nvlink fusion",)
MEMORY = ("hbm", "nvhbm", "server dram", "서버 dram", "서버 디램", "rdimm", "socamm")
SOURCES = {
    "삼성전자": ("samsung electronics", "samsung", "삼성전자", "三星"),
    "SK하이닉스": ("sk hynix", "sk하이닉스", "sk 하이닉스", "海力士"),
    "Micron": ("micron", "마이크론", "美光"),
}
# Avoid taking explicit uncertainty, past consideration or forecasts as new signed business.
HEDGE = ("could", "might", "may", "possibly", "rumor", "rumour", "reportedly",
         "considering", "considered", "in talks", "weighing", "discussed",
         "possible", "would", "could still", "planned", "target", "aims to",
         "검토", "가능성", "협의", "예정", "추정", "계획", "可能", "考虑", "洽谈", "计划")
NEGATION = ("not adopted", "not signed", "no contract", "has not ordered", "not yet",
            "no apple order", "isn't confirmed", "hasn't confirmed", "否认", "尚未",
            "미체결", "미확정", "아직", "아니다", "부인", "없다")


def clean(value: str | None) -> str:
    s = html.unescape(value or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", s)).strip()


def norm(value: str) -> str:
    return clean(value).casefold()


def has(text: str, phrases: tuple[str, ...]) -> bool:
    return any(p in text for p in phrases)


def dateparse(value: str | None) -> dt.datetime | None:
    try:
        when = parsedate_to_datetime(value or "")
        if not when.tzinfo:
            when = when.replace(tzinfo=dt.timezone.utc)
        return when.astimezone(KST)
    except Exception:
        return None


def rss_url(locale: str, query: str) -> str:
    options = {
        "q": query,
        "hl": {"ko": "ko", "en": "en-US", "zh": "zh-CN"}[locale],
        "gl": {"ko": "KR", "en": "US", "zh": "SG"}[locale],
        "ceid": {"ko": "KR:ko", "en": "US:en", "zh": "SG:zh-Hans"}[locale],
    }
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(options)


def source_tier(publisher: str, source_url: str = "") -> str:
    # Exact publisher names; never mistake AppleInsider for Apple or a
    # named-company mention inside a headline for a company statement.
    publisher = clean(publisher)
    domain = (urlparse(source_url).hostname or "").lower()
    if publisher in OFFICIAL_PUBLISHERS and domain and any(
        domain == d or domain.endswith("." + d)
        for d in ("apple.com", "nvidia.com", "samsung.com", "skhynix.com",
                  "micron.com", "broadcom.com", "tsmc.com")
    ):
        return "회사발표색인"
    if publisher in HIGH_PUBLISHERS:
        return "신뢰보도"
    if publisher in SECONDARY_PUBLISHERS:
        return "재인용가능"
    return "기타매체"


def origin_family(row: dict) -> str:
    text = norm(row["title"] + " " + row.get("description", ""))
    publisher = norm(row.get("source", "")) or "unspecified"
    # Reuters and syndicators attributing the *same* Information scoop
    # are not independent confirmations.
    if publisher == "the information":
        return "the-information-syndicated"
    if has(text, ("the information", "더인포메이션", "据the information", "据theinformation")):
        if publisher not in ("apple", "nvidia", "samsung electronics", "micron technology"):
            return "the-information-syndicated"
    if "reuters" in text and publisher != "reuters":
        return "reuters-syndicated"
    return publisher


def facthash(kind: str, value: str) -> str:
    return hashlib.sha256((kind + "|" + value).encode("utf-8")).hexdigest()[:20]


def article_id(row: dict) -> str:
    txt = norm(row["title"])
    txt = re.sub(r"\s+[-—|]\s+[^-—|]{2,65}$", "", txt)
    return facthash(norm(row.get("source", "")), txt)


def _context(row: dict) -> tuple[str, bool, bool]:
    blob = norm(row["title"] + ". " + row.get("description", ""))
    # Source names never count as an Apple server link.
    about_apple = has(blob, APPLE)
    about_project = about_apple and has(blob, SERVER) and has(blob, M8)
    return blob, about_apple, about_project


def _active_claim(text: str, action_terms: tuple[str, ...]) -> bool:
    if has(text, NEGATION):
        return False
    return has(text, action_terms)


def classify(row: dict) -> list[dict]:
    """Extract only a genuinely changed Apple M8 business fact.

    Title+RSS snippet is discovery-level evidence, never a verified filing.
    """
    blob, about_apple, about_project = _context(row)
    if not about_apple:
        return []
    out: list[dict] = []
    src_tier = source_tier(row.get("source", ""), row.get("source_url", ""))

    def add(kind: str, value: str, label: str, significance: str,
            *, caution: str = "회사·거래상대 원문 확인 전에는 보도 단계") -> None:
        out.append({
            "key": kind + ":" + value, "kind": kind, "label": label,
            "significance": significance, "caution": caution,
            "tier": src_tier, "origin": origin_family(row),
            "source": row.get("source") or "출처 미표시",
            "url": row["link"], "published": row.get("published", ""),
            "title": row["title"],
        })

    if about_project:
        # A 2026 publication date and the old 2029 launch target are NOT changes.
        # A new target is meaningful only beside target/launch/delay language.
        m = re.search(
            r"(?:target(?:ed)?|launch(?:ing)?|release|postponed|delayed|rescheduled|"
            r"출시(?:목표)?|연기|지연|延至|推迟|上市)[^.!?;。]{0,55}?"
            r"\b(202[7-9]|203[0-5])\b",
            blob, flags=re.I,
        )
        if not m:
            m = re.search(
                r"\b(202[7-9]|203[0-5])\b[^.!?;。]{0,35}"
                r"(?:launch|release|출시|上市)", blob
            )
        if m:
            target = next((int(x) for x in m.groups() if x and x.isdigit()), 0)
            if target and target != 2029:
                add("schedule", str(target),
                    f"기업용 M8 서버 목표 시점이 {target}년으로 언급됨",
                    "출시·검증 일정 변화 후보이며 공식 일정은 별도 확인 필요")

        # Only stage-specific project language, not the generic word 'shipping'.
        stages = [
            ("canceled", ("apple canceled its m8", "apple scrapped its m8", "m8 ultra server canceled",
                           "m8 ultra server cancelled", "m8 서버 개발 취소", "苹果取消m8")),
            ("tapeout", ("m8 ultra tapeout completed", "m8 ultra taped out", "m8 ultra 테이프아웃 완료",
                         "m8 ultra 流片完成")),
            ("prototype", ("m8 ultra server prototype built", "m8 ultra server prototype tested",
                           "m8 ultra 서버 시제품 제작", "m8 ultra 服务器原型")),
            ("production", ("m8 ultra server began mass production", "m8 ultra server enters mass production",
                            "m8 ultra 서버 양산 시작", "m8 ultra 服务器量产")),
            ("shipping", ("apple begins shipping m8 ultra server", "m8 ultra enterprise server is now shipping",
                          "m8 ultra 서버 출하 개시")),
        ]
        for stage, phrases in stages:
            if has(blob, phrases) and not has(blob, NEGATION):
                add("project", stage, f"M8 Ultra 기업용 서버 단계: {stage}",
                    "새 개발·검증·상용화 단계 보도", caution="실제 고객·출하·매출과 구분 필요")

        # Actual 2/4-chip baseline doesn't trigger; 8-chip design changes do.
        m = re.search(r"(?:m8 ultra|m8울트라|m8 울트라)[^.!?;。]{0,55}?"
                      r"\b(6|8|12|16)\s*(?:-?\s*chip|개|颗|칩|处理器)", blob)
        if m:
            add("configuration", m.group(1), f"M8 Ultra {m.group(1)}칩 구성 보도",
                "기존 2칩·4칩 검토안과 다른 칩 연결 구성")

        # New verified model capacity is not inherited from M7/M5 rumors.
        m = re.search(r"(?:m8 ultra|m8울트라|m8 울트라)[^.!?;。]{0,85}?"
                      r"(\d+(?:\.\d+)?)\s*(tb|gb)\s*(?:unified )?(?:memory|dram|hbm|메모리|内存)", blob)
        if m:
            add("server-memory-design", m.group(1) + m.group(2),
                "M8 서버 메모리 사양 " + m.group(1) + m.group(2).upper() + " 언급",
                "사양 검증 단계이며 실제 메모리 업체 수주는 아님")

        if has(blob, NVLINK):
            baseline = ("consider", "considering", "discuss", "discussed", "talks", "in talks",
                        "may use", "could use", "might use", "weighs", "to use", "plans to",
                        "검토", "협의", "추진", "洽谈", "拟引入", "考虑")
            adopted = ("has adopted", "has selected", "signed a deal", "signed a contract",
                       "will integrate", "adopts nvlink", "nvlink fusion deal signed",
                       "nvlink fusion officially", "nvlink fusion 채택 확정",
                       "nvlink fusion 도입 계약", "签署nvlink fusion", "采用nvlink fusion已确认")
            declined = ("rejects nvlink", "scraps nvlink", "won't use nvlink",
                        "nvlink fusion 도입 취소", "nvlink fusion 채택 철회",
                        "放弃nvlink fusion")
            if has(blob, adopted) and not has(blob, NEGATION) and not (
                has(blob, baseline) and not has(blob, ("has adopted", "has selected",
                                                      "signed", "will integrate", "채택 확정"))
            ):
                add("nvlink", "reported-adoption",
                    "M8 서버의 NVLink Fusion 채택·계약 보도",
                    "연결기술 진전 후보, HBM·NVHBM 구매 증거는 아님")
            elif has(blob, declined) and not has(blob, NEGATION):
                add("nvlink", "reported-rejection", "M8 서버 NVLink Fusion 도입 철회 보도",
                    "대체 칩 연결기술 개발·고객 일정 위험")

        if _active_claim(blob, ("customer contract", "enterprise customer order",
                                "government server contract", "m8 ultra server order",
                                "m8 서버 수주", "m8 ultra 서버 공급계약")):
            add("commercial", "customer-contract", "외부 기업용 M8 서버 고객 계약 보도",
                "실제 외부 판매·매출의 선행 확인 대상")

        if _active_claim(blob, ("m8 ultra enterprise remote management launched",
                                "m8 ultra server mlx enterprise support",
                                "m8 서버 원격 관리 소프트웨어 출시",
                                "m8 ultra 服务器管理软件发布")):
            add("software", "enterprise-tools", "기업 M8 서버용 소프트웨어·운영도구",
                "기업 채택에 필요한 원격관리·개발도구 진전")

    # Server memory deal: separate from mobile DRAM and unrelated NVIDIA HBM.
    server_mem_context = about_apple and (
        about_project or
        has(blob, ("apple enterprise server", "apple ai inference server", "애플 기업용 서버",
                   "애플 ai 서버", "苹果企业服务器", "苹果ai服务器"))
    )
    if server_mem_context and has(blob, MEMORY):
        relevant_supplier = [name for name, variants in SOURCES.items() if has(blob, variants)]
        concrete = has(blob, ("signed", "awarded", "ordered", "placed an order", "purchased",
                              "supply agreement", "supply contract", "contract signed", "prepaid",
                              "allocated", "confirmed allocation", "공급 계약", "장기 공급계약",
                              "발주 완료", "구매 계약", "물량 배정 확정", "签署", "采购合同", "已下订单"))
        future_only = has(blob, ("plans to buy", "seeking to buy", "could buy", "may order",
                                 "considering buying", "검토 중", "구매 추진", "可能采购"))
        if relevant_supplier and concrete and not future_only and not has(blob, NEGATION):
            # A memory and supplier mention alone is never enough: require wording
            # tying Apple/M8 as buyer/client to order/supply in a short span.
            bound = re.search(
                r"(?:apple|애플|苹果|m8 ultra)[^.!?;。]{0,120}"
                r"(?:signed|awarded|ordered|placed an order|purchased|supply agreement|"
                r"supply contract|contract signed|allocated|발주 완료|구매 계약|"
                r"공급 계약|물량 배정 확정|签署|已下订单)",
                blob
            ) or re.search(
                r"(?:samsung|sk hynix|micron|삼성전자|하이닉스|마이크론)"
                r"[^.!?;。]{0,105}(?:supply|contract|납품|공급)[^.!?;。]{0,75}"
                r"(?:apple|m8 ultra|애플|苹果)",
                blob
            )
            if bound:
                kinds = []
                if "nvhbm" in blob: kinds.append("NVHBM")
                elif "hbm" in blob: kinds.append("HBM")
                if has(blob, ("server dram", "서버 dram", "서버 디램", "rdimm", "socamm")):
                    kinds.append("서버 DRAM")
                for supplier in relevant_supplier:
                    for memory in kinds:
                        add("memory-order", supplier + ":" + memory,
                            f"애플 기업 서버용 {supplier} {memory} 구매·공급계약 주장",
                            "애플 또는 공급사의 실제 계약·수량·발주 확정 여부 확인 필요",
                            caution="기사 요약만으로 계약 확정 불가; 당사자 원문·물량 교차검증 필요")

    # Single 'Xserve', 'PCC', Mac Studio or Google/NVIDIA cloud server news
    # does NOT establish an M8 enterprise hardware sale.
    return out


def fetch_items() -> tuple[list[dict], list[str], int]:
    now = dt.datetime.now(KST)
    minimum = now - dt.timedelta(days=12)
    collected, errors, ok = {}, [], 0
    for locale, q in SEARCHES:
        try:
            request = urllib.request.Request(rss_url(locale, q),
                      headers={"User-Agent": "Mozilla/5.0 (compatible; khs-apple-enterprise-watch/2.0)",
                               "Accept": "application/rss+xml,application/xml,text/xml"})
            with urllib.request.urlopen(request, timeout=16) as response:
                data = response.read(2_000_000)
            tree = ET.fromstring(data)
            ok += 1
            for item in tree.findall(".//item"):
                title = clean(item.findtext("title"))
                link = clean(item.findtext("link"))
                published = dateparse(item.findtext("pubDate"))
                publisher_node = item.find("source")
                publisher = clean(publisher_node.text if publisher_node is not None else "")
                source_url = publisher_node.get("url", "") if publisher_node is not None else ""
                if not title or not link or not published or published < minimum:
                    continue
                rec = {
                    "title": title, "link": link, "description": clean(item.findtext("description")),
                    "source": publisher, "source_url": source_url,
                    "published": published.isoformat(timespec="seconds"),
                }
                collected.setdefault(article_id(rec), rec)
        except Exception as exc:
            errors.append(f"{locale} {q[:38]}: {type(exc).__name__} {str(exc)[:100]}")
    return sorted(collected.values(), key=lambda r: r["published"], reverse=True), errors, ok


def load_state() -> dict:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(state, dict): raise ValueError("bad state")
    except FileNotFoundError:
        state = {}
    except (ValueError, OSError) as exc:
        raise RuntimeError(f"State damaged; refusing silent reinitialization: {exc}") from exc
    state.setdefault("baseline_at_utc", "2026-09-16T13:45:00+00:00")
    state.setdefault("seen", [])
    state.setdefault("seen_event_keys", list(BASELINE_KEYS))
    state.setdefault("observations", [])
    state.setdefault("metrics", {})
    state["schema_version"] = 2
    for field, value in {
        "target_year": 2029, "chip": "M8 Ultra", "processor_min": 2,
        "processor_max": 4, "nvlink_status": "talks",
        "hbm_procurement": "unconfirmed", "server_dram_procurement": "unconfirmed",
        "commercial_status": "reported_early_stage",
    }.items():
        state["metrics"].setdefault(field, value)
    return state


def write_json(path: pathlib.Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _summary(event: dict) -> str:
    when = event["published"][:16].replace("T", " ")
    return (f"• {html.escape(event['label'])}\n"
            f"  근거: {html.escape(event['source'])} / {html.escape(event['tier'])}"
            f" / {when} KST\n"
            f"  의미: {html.escape(event['significance'])}\n"
            f"  확인: {html.escape(event['caution'])}\n"
            f"  <a href=\"{html.escape(event['url'], quote=True)}\">원문 또는 뉴스 검색결과</a>")


def format_alert(rows: list[dict]) -> str:
    lines = ["<b>[애플 AI 서버·메모리 신규 변화]</b>",
             dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"), ""]
    for ev in rows[:3]:
        lines.extend([_summary(ev), ""])
    lines.extend([
        "<b>확인 단계</b>",
        "• 개발 보도 → 설계·고객 검증 → 공급계약 → 양산·판매·매출을 분리합니다.",
        "• NVLink Fusion ≠ HBM·NVHBM 구매. 모바일 LPDDR와 서버 DRAM·HBM도 분리합니다.",
        "• 검색 결과·재인용은 공식 당사자 계약이 아니며 수량·단가·고객 실명을 재검증합니다.",
        "<b>다음 확인</b>",
        "• Apple/NVIDIA 공식 채택 → M8 설계/검증 → 서버용 메모리 계약·물량 → 기업 고객 → 판매 시점",
    ])
    return "\n".join(lines) + "\n"


def process(rows: list[dict], state: dict) -> tuple[list[dict], dict]:
    """Conservative discovery; merged state written only after delivery."""
    history = set(state.get("seen", []))
    sent = set(state.get("seen_event_keys", [])) | set(BASELINE_KEYS)
    reports = list(state.get("observations", []))
    by_key: dict[str, list[dict]] = defaultdict(list)
    try:
        baseline = dt.datetime.fromisoformat(state["baseline_at_utc"].replace("Z", "+00:00")).astimezone(KST)
    except Exception:
        raise RuntimeError("Invalid baseline timestamp; refusing to send stale alerts")
    for row in rows:
        aid = article_id(row)
        if aid in history: continue
        history.add(aid)
        pub = dt.datetime.fromisoformat(row["published"]).astimezone(KST)
        if pub <= baseline: continue
        for ev in classify(row):
            # Carry forward recent corroboration observations across scans.
            by_key[ev["key"]].append(ev)
            reports.append({
                "key": ev["key"], "origin": ev["origin"], "source": ev["source"],
                "published": ev["published"], "tier": ev["tier"],
            })

    independent: dict[str, set[str]] = defaultdict(set)
    for ev in reports[-600:]:
        independent[ev["key"]].add(ev["origin"])
    output = []
    for key, events in by_key.items():
        if key in sent: continue
        ranked = sorted(events, key=lambda x: (
            2 if x["tier"] == "회사발표색인" else
            1 if x["tier"] == "신뢰보도" else 0,
            x["published"]), reverse=True)
        top = ranked[0]
        # No alert based on an isolated low-quality headline.
        if top["tier"] in ("기타매체", "재인용가능"):
            # Two copies of a rumor, even at unrelated outlets, don't prove it.
            # Require a separate first-party/high-quality originating report.
            top_origins = {x["origin"] for x in events}
            recent_evidence = [
                r for r in reports[-600:]
                if r["key"] == key and r["origin"] in independent[key]
                and r["tier"] in ("회사발표색인", "신뢰보도")
            ]
            if len(independent[key]) < 2 or not recent_evidence:
                continue
        top = dict(top)
        n = len(independent[key])
        top["significance"] += f" (독립 원보도 계열 {n}곳; 인용 기사 반복은 제외)"
        output.append(top)
        sent.add(key)

    output.sort(key=lambda r: r["published"], reverse=True)
    next_state = json.loads(json.dumps(state, ensure_ascii=False))
    next_state["seen"] = sorted(history)[-4500:]
    next_state["seen_event_keys"] = sorted(sent)[-1500:]
    next_state["observations"] = reports[-600:]
    next_state["last_scan_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    if output:
        next_state["last_alert"] = {
            "at_kst": next_state["last_scan_kst"],
            "claim_keys": [x["key"] for x in output[:3]],
            "kinds": [x["kind"] for x in output[:3]],
        }
    return output[:3], next_state


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ALERT.unlink(missing_ok=True)
    state = load_state()
    items, errors, successful = fetch_items()
    if successful < 2:
        STATUS.write_text("# 애플 AI 서버 감시\n\n- 데이터 원천 접속 실패: 정상 조회가 2곳 미만\n"
                          + "\n".join(errors) + "\n", encoding="utf-8")
        raise RuntimeError(f"Insufficient RSS sources: {successful}/{len(SEARCHES)}; no silent no-change")
    candidates, pending = process(items, state)
    pending["fetch_ok"] = successful
    pending["fetch_errors"] = errors[-30:]
    write_json(PENDING, pending)
    if candidates:
        ALERT.write_text(format_alert(candidates), encoding="utf-8")
    STATUS.write_text(
        "# 애플 AI 서버·메모리 신규 정보 감시\n\n"
        f"- 검사시각: {dt.datetime.now(KST).isoformat(timespec='seconds')}\n"
        f"- 원천 조회: {successful}/{len(SEARCHES)} 정상 / {len(errors)} 실패\n"
        f"- 최근 기사: {len(items)}개 / 의미 있는 신규 주장: {len(candidates)}개\n"
        f"- 알림: {'후보 생성' if candidates else '없음(기존 기사·미확인 신호 차단)'}\n"
        f"- 기준선: {BASELINE['m8_server']}; {BASELINE['nvlink']}; {BASELINE['memory']}\n"
        "- 판정 한계: RSS 제목·요약 수준 탐지. 공식 계약 또는 원문 전체 확인과 동등하지 않음.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
