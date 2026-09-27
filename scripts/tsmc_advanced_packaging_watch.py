from __future__ import annotations

import argparse
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

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_STATE = ROOT / "data" / "tsmc_advanced_packaging_watch_state.json"
HBM_STATE = ROOT / "data" / "tsmc_hbm_cross_watch_state.json"
PACKAGE_ALERT = ROOT / "out" / "tsmc_advanced_packaging_alert.html"
HBM_ALERT = ROOT / "out" / "tsmc_hbm_cross_alert.html"
PACKAGE_STATUS = ROOT / "out" / "tsmc_advanced_packaging_status.json"
HBM_STATUS = ROOT / "out" / "tsmc_hbm_cross_status.json"

UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
WATCH_VERSION = 1
LTN_CANONICAL_URL = "https://ec.ltn.com.tw/article/breakingnews/5586843"
LTN_ALT_URL = "https://stock.ltn.com.tw/article/gqpj9vhyk1ku"
NSTC_OFFICIAL_URL = "https://www.nstc.gov.tw/folksonomy/list/d3c30297-bb63-44c5-ad30-38a65b203288%3Fl%3Dch"

SEARCHES = [
    ('"台積電" "嘉義" "先進封裝"', "zh"),
    ('"台積電" "嘉科" "先進封裝"', "zh"),
    ('"台積電" "嘉科" (P1 OR P2 OR P3 OR P4 OR P5 OR P6 OR P7 OR P8 OR P9 OR P10)', "zh"),
    ('"TSMC" "Chiayi" "advanced packaging"', "en"),
    ('"TSMC" CoWoS capacity advanced packaging', "en"),
    ('"TSMC" SoIC capacity advanced packaging', "en"),
    ('"TSMC" advanced packaging tester bottleneck shortage', "en"),
    ('"TSMC" CoWoS substrate HBM bottleneck shortage', "en"),
    ('site:nstc.gov.tw 嘉義園區 擴建', "zh"),
]

TRUSTED = (
    "tsmc.com", "investor.tsmc.com", "nstc.gov.tw", "stsp.gov.tw",
    "reuters", "bloomberg", "cna.com.tw", "中央社",
    "ec.ltn.com.tw", "stock.ltn.com.tw", "自由時報", "自由財經",
    "trendforce", "digitimes", "udn.com", "經濟日報",
)

EVIDENCE_RANK = {
    "reported": 1,
    "supply_chain_report": 2,
    "top_tier_report": 3,
    "official": 4,
}

PHASE_RANK = {
    "reported_intent": 1,
    "public_comment": 2,
    "environmental_review": 3,
    "approved": 4,
    "construction": 5,
    "tool_move_in": 6,
    "pilot_production": 7,
    "mass_production": 8,
}

PHASE_KO = {
    "reported_intent": "공급망 투자 의향 보도",
    "public_comment": "부지 확대 의견수렴",
    "environmental_review": "환경영향평가",
    "approved": "공식 승인·투자결정",
    "construction": "착공",
    "tool_move_in": "장비 반입",
    "pilot_production": "시험생산",
    "mass_production": "양산",
}


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul"))


def clean(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", value).strip()


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_pub(value):
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def rss_url(query, lang):
    enc = urllib.parse.quote(query)
    if lang == "zh":
        return f"https://news.google.com/rss/search?q={enc}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    return f"https://news.google.com/rss/search?q={enc}&hl=en-US&gl=US&ceid=US:en"


def decode_google(url):
    if "news.google.com" not in (url or ""):
        return url
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(url, interval=0.15)
        if isinstance(result, dict) and result.get("status"):
            direct = str(result.get("decoded_url") or "").strip()
            if direct.startswith("http") and "news.google.com" not in direct:
                return direct
    except Exception:
        pass
    return ""


def evidence_state(source, url):
    text = ((source or "") + " " + (url or "")).lower()
    if any(x in text for x in ("tsmc.com", "nstc.gov.tw", "stsp.gov.tw")):
        return "official"
    if any(x in text for x in ("reuters", "bloomberg", "cna.com.tw", "中央社")):
        return "top_tier_report"
    if any(x in text for x in ("ec.ltn.com.tw", "stock.ltn.com.tw", "自由時報", "自由財經", "trendforce", "digitimes")):
        return "supply_chain_report"
    return "reported"


def source_rank(source, url):
    return EVIDENCE_RANK.get(evidence_state(source, url), 0)


def read_events():
    rows = {}
    for query, lang in SEARCHES:
        try:
            root = ET.fromstring(fetch(rss_url(query, lang)))
        except Exception:
            continue
        for item in root.findall("./channel/item"):
            title = clean(item.findtext("title") or "")
            desc = clean(item.findtext("description") or "")
            link = clean(item.findtext("link") or "")
            source_node = item.find("source")
            source = clean(source_node.text if source_node is not None and source_node.text else "")
            pub = parse_pub(clean(item.findtext("pubDate") or ""))
            low = (title + " " + desc).lower()
            if not any(k in low for k in ("tsmc", "台積電", "台积电")):
                continue
            if not any(k in low for k in (
                "advanced packaging", "cowos", "soic", "先進封裝", "先进封装",
                "嘉義", "嘉义", "chiayi", "tester", "substrate", "封測", "封测",
            )):
                continue
            direct = decode_google(link)
            if not direct:
                continue
            host = (urllib.parse.urlparse(direct).hostname or "").lower()
            trust_text = (source + " " + host).lower()
            if not any(x in trust_text for x in TRUSTED):
                continue
            if "一共10座" in title or ("10座" in title and "嘉" in title and "封裝" in title):
                direct = LTN_CANONICAL_URL
                source = "LTN"
            key = hashlib.sha256((title + "|" + source).encode()).hexdigest()[:24]
            rows[key] = {
                "id": key,
                "title": title,
                "description": desc,
                "source": source or host or "출처 미표시",
                "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                "direct_link": direct,
                "rank": source_rank(source, direct),
            }
    return sorted(rows.values(), key=lambda x: (x.get("published_at_kst") or "", x.get("rank", 0)))


def article_text(event):
    url = event.get("direct_link") or ""
    if url == LTN_CANONICAL_URL:
        url = LTN_ALT_URL
    try:
        raw = fetch(url, timeout=16).decode("utf-8", errors="ignore")
        return clean(raw)[:60000]
    except Exception:
        return ""


def strong_current_status(text):
    low = text.lower()
    patterns = (
        ("mass_production", r"(?:正式|已|開始|开始|began|started|is now)[^。.;]{0,35}(?:量產|量产|mass production)"),
        ("pilot_production", r"(?:正式|已|開始|开始|began|started)[^。.;]{0,35}(?:試產|试产|pilot production|trial production)"),
        ("tool_move_in", r"(?:正式|已|開始|开始|啟動|启动|began|started)[^。.;]{0,35}(?:進機|进机|設備進駐|设备进驻|tool move[- ]?in|equipment move[- ]?in)"),
        ("construction", r"(?:正式|已|開始|开始|動工|动工|開工|开工|groundbreaking|construction (?:has )?(?:begun|started))"),
        ("approved", r"(?:正式)?(?:核定|批准|通過|通过|approved|investment decision)"),
    )
    for status, pat in patterns:
        if re.search(pat, low, re.I):
            return status
    return ""


def phase3_status(text):
    low = text.lower()
    phase_tokens = list(re.finditer(r"(?:嘉科)?三期|third phase|二期擴大|二期扩大", low, re.I))
    if not phase_tokens:
        return ""
    best = ""
    for token in phase_tokens:
        window = low[max(0, token.start() - 120): min(len(low), token.end() + 180)]
        if re.search(r"徵求意見|征求意见|意見徵集|意见征集|public comment|provide opinions", window, re.I):
            best = max((best, "public_comment"), key=lambda x: PHASE_RANK.get(x, 0))
        if re.search(r"環評|环评|環境影響|环境影响|environmental (?:impact|review)", window, re.I):
            best = max((best, "environmental_review"), key=lambda x: PHASE_RANK.get(x, 0))
        current = strong_current_status(window)
        if current:
            best = max((best, current), key=lambda x: PHASE_RANK.get(x, 0))
    return best


def parse_fab_statuses(text, ev_state, source_url):
    result = {}
    for num in range(1, 11):
        for match in re.finditer(rf"\bP{num}\b", text, re.I):
            window = text[max(0, match.start() - 90): min(len(text), match.end() + 150)]
            if re.search(r"預計|预计|計畫|计划|planned|expected|target(?:ed)?", window, re.I) and not re.search(
                r"已|正式|開始|开始|began|started|動工|动工|開工|开工", window, re.I
            ):
                continue
            status = strong_current_status(window)
            if status:
                result[f"P{num}"] = {
                    "status": status,
                    "evidence_state": ev_state,
                    "source_url": source_url,
                }
                break
    return result


def monthly_capacity(text, tech):
    tech_pat = re.escape(tech)
    patterns = [
        rf"{tech_pat}[^。.;]{{0,100}}?(?:月產能|月产能|monthly capacity)[^0-9]{{0,20}}?([0-9]+(?:\.[0-9]+)?)\s*(萬|万)\s*(?:片|wafers?)",
        rf"(?:月產能|月产能|monthly capacity)[^。.;]{{0,100}}?{tech_pat}[^0-9]{{0,20}}?([0-9]+(?:\.[0-9]+)?)\s*(萬|万)\s*(?:片|wafers?)",
        rf"{tech_pat}[^。.;]{{0,100}}?([0-9]+(?:\.[0-9]+)?)\s*k\s*(?:wafers?|wpm)[^。.;]{{0,50}}?(?:month|monthly|per month)",
        rf"(?:month|monthly|per month)[^。.;]{{0,50}}?{tech_pat}[^0-9]{{0,20}}?([0-9]+(?:\.[0-9]+)?)\s*k\s*(?:wafers?|wpm)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        n = float(m[1])
        unit = m[2] if m.lastindex and m.lastindex >= 2 else ""
        if unit in ("萬", "万"):
            return int(round(n * 10000))
        return int(round(n * 1000))
    return None


def bottleneck_status(text, key):
    low = text.lower()
    terms = {
        "tester": ("tester", "test equipment", "테스터", "測試機", "测试机"),
        "substrate": ("substrate", "abf", "기판", "載板", "载板"),
        "hbm": ("hbm",),
        "cowos": ("cowos",),
    }[key]
    if not any(t.lower() in low for t in terms):
        return ""
    if re.search(r"shortage|bottleneck|insufficient|tight supply|缺貨|缺货|不足|瓶頸|瓶颈|供不應求|供不应求", low, re.I):
        return "tight"
    if re.search(r"easing|ease|improv(?:e|ing)|緩解|缓解|改善|供需平衡", low, re.I):
        return "easing"
    if re.search(r"resolved|cleared|解除|消除", low, re.I):
        return "cleared"
    return ""


def extract_patch(event):
    base = clean(f"{event.get('title','')} {event.get('description','')}")
    page = article_text(event)
    text = (base + " " + page).strip()
    low = text.lower()
    if not any(k in low for k in ("tsmc", "台積電", "台积电")):
        return {}
    if not any(k in low for k in (
        "advanced packaging", "cowos", "soic", "先進封裝", "先进封装",
        "嘉義", "嘉义", "chiayi", "tester", "substrate", "封測", "封测",
    )):
        return {}

    source_url = event.get("direct_link") or ""
    source_name = event.get("source") or ""
    if "一共10座" in (event.get("title") or "") or ("10座" in (event.get("title") or "") and "嘉" in (event.get("title") or "")):
        source_url = LTN_CANONICAL_URL
        source_name = "LTN"
    ev = evidence_state(source_name, source_url)
    patch = {
        "last_evidence_state": ev,
        "last_source_url": source_url,
        "last_source_name": source_name,
        "last_source_published_at_kst": event.get("published_at_kst") or "",
        "last_event_title": event.get("title") or "",
    }

    if any(k in low for k in ("嘉義", "嘉义", "chiayi", "嘉科")):
        for pat in (
            r"(?:一共|共|總計|总计|total(?: of)?)\s*(\d{1,2})\s*(?:座|fabs?)",
            r"(?:坐擁|坐拥|將有|将有|will have)[^0-9]{0,12}(\d{1,2})\s*(?:座|fabs?)",
        ):
            m = re.search(pat, text, re.I)
            if m:
                n = int(m[1])
                if 1 <= n <= 20:
                    patch["chiayi_total_fabs"] = n
                    patch["fab_count_evidence_state"] = ev
                    break
        for pat in (
            r"(?:再加碼|再加码|追加|新增|再建|additional|adding|another)[^0-9]{0,18}(\d{1,2})\s*(?:座|fabs?)",
            r"(\d{1,2})\s*(?:座|fabs?)[^。.;]{0,35}(?:新增|追加|additional|more)",
        ):
            m = re.search(pat, text, re.I)
            if m:
                n = int(m[1])
                if 1 <= n <= 10:
                    patch["chiayi_additional_fabs"] = n
                    patch["fab_count_evidence_state"] = ev
                    break

        ph = phase3_status(text)
        if ph:
            patch["chiayi_phase3_status"] = ph
            patch["phase3_evidence_state"] = ev

        fabs = parse_fab_statuses(text, ev, source_url)
        if fabs:
            patch["fabs"] = fabs

    cowos = monthly_capacity(text, "CoWoS")
    if cowos:
        patch["cowos_capacity_wpm"] = cowos
        patch["cowos_capacity_evidence_state"] = ev
    soic = monthly_capacity(text, "SoIC")
    if soic:
        patch["soic_capacity_wpm"] = soic
        patch["soic_capacity_evidence_state"] = ev

    b = {}
    for key in ("tester", "substrate", "hbm", "cowos"):
        status = bottleneck_status(text, key)
        if status:
            b[key] = {"status": status, "evidence_state": ev, "source_url": source_url}
    if b:
        patch["bottlenecks"] = b
    return patch


def merge_evidenced_scalar(out, patch, field, evidence_field):
    if field not in patch:
        return
    new_ev = patch.get(evidence_field, patch.get("last_evidence_state", "reported"))
    old_ev = out.get(evidence_field, "reported")
    if field not in out or EVIDENCE_RANK.get(new_ev, 0) >= EVIDENCE_RANK.get(old_ev, 0):
        out[field] = patch[field]
        out[evidence_field] = new_ev


def merge_state(current, patch):
    out = json.loads(json.dumps(current or {}, ensure_ascii=False))
    merge_evidenced_scalar(out, patch, "chiayi_total_fabs", "fab_count_evidence_state")
    merge_evidenced_scalar(out, patch, "chiayi_additional_fabs", "fab_count_evidence_state")
    merge_evidenced_scalar(out, patch, "cowos_capacity_wpm", "cowos_capacity_evidence_state")
    merge_evidenced_scalar(out, patch, "soic_capacity_wpm", "soic_capacity_evidence_state")

    if patch.get("chiayi_phase3_status"):
        new = patch["chiayi_phase3_status"]
        old = out.get("chiayi_phase3_status")
        new_ev = patch.get("phase3_evidence_state", patch.get("last_evidence_state", "reported"))
        old_ev = out.get("phase3_evidence_state", "reported")
        if (
            not old
            or PHASE_RANK.get(new, 0) > PHASE_RANK.get(old, 0)
            or (
                PHASE_RANK.get(new, 0) == PHASE_RANK.get(old, 0)
                and EVIDENCE_RANK.get(new_ev, 0) >= EVIDENCE_RANK.get(old_ev, 0)
            )
        ):
            out["chiayi_phase3_status"] = new
            out["phase3_evidence_state"] = new_ev

    fabs = dict(out.get("fabs") or {})
    for fab, item in (patch.get("fabs") or {}).items():
        old = fabs.get(fab) or {}
        if (
            not old
            or PHASE_RANK.get(item.get("status"), 0) > PHASE_RANK.get(old.get("status"), 0)
            or (
                PHASE_RANK.get(item.get("status"), 0) == PHASE_RANK.get(old.get("status"), 0)
                and EVIDENCE_RANK.get(item.get("evidence_state"), 0) >= EVIDENCE_RANK.get(old.get("evidence_state"), 0)
            )
        ):
            fabs[fab] = item
    if fabs:
        out["fabs"] = fabs

    bottlenecks = dict(out.get("bottlenecks") or {})
    for key, item in (patch.get("bottlenecks") or {}).items():
        old = bottlenecks.get(key) or {}
        if EVIDENCE_RANK.get(item.get("evidence_state"), 0) >= EVIDENCE_RANK.get(old.get("evidence_state"), 0):
            bottlenecks[key] = item
    if bottlenecks:
        out["bottlenecks"] = bottlenecks

    if patch.get("last_source_url"):
        new_ev = patch.get("last_evidence_state", "reported")
        old_ev = out.get("last_evidence_state", "reported")
        if EVIDENCE_RANK.get(new_ev, 0) >= EVIDENCE_RANK.get(old_ev, 0):
            for k in ("last_evidence_state", "last_source_url", "last_source_name", "last_source_published_at_kst", "last_event_title"):
                if patch.get(k) not in (None, ""):
                    out[k] = patch[k]
    return out


def material_changes(old, new):
    reasons = []
    if old.get("chiayi_total_fabs") != new.get("chiayi_total_fabs") and new.get("chiayi_total_fabs") is not None:
        reasons.append(f"嘉義 첨단패키징 공장 총계 {old.get('chiayi_total_fabs','미확인')}→{new['chiayi_total_fabs']}개")
    if old.get("chiayi_additional_fabs") != new.get("chiayi_additional_fabs") and new.get("chiayi_additional_fabs") is not None:
        reasons.append(f"추가 공장 {old.get('chiayi_additional_fabs','미확인')}→{new['chiayi_additional_fabs']}개")
    if old.get("chiayi_phase3_status") != new.get("chiayi_phase3_status") and new.get("chiayi_phase3_status"):
        reasons.append(
            "嘉科 확대 단계 "
            + PHASE_KO.get(old.get("chiayi_phase3_status"), old.get("chiayi_phase3_status", "미확인"))
            + "→"
            + PHASE_KO.get(new.get("chiayi_phase3_status"), new.get("chiayi_phase3_status"))
        )
    for field, label in (("cowos_capacity_wpm", "CoWoS 월 생산능력"), ("soic_capacity_wpm", "SoIC 월 생산능력")):
        a, b = old.get(field), new.get(field)
        if a != b and b is not None:
            if a:
                reasons.append(f"{label} {int(a):,}→{int(b):,}장")
            else:
                reasons.append(f"{label} {int(b):,}장 신규 확인")
    old_fabs, new_fabs = old.get("fabs") or {}, new.get("fabs") or {}
    for fab in sorted(set(old_fabs) | set(new_fabs)):
        a = (old_fabs.get(fab) or {}).get("status")
        b = (new_fabs.get(fab) or {}).get("status")
        if a != b and b:
            reasons.append(f"{fab} {PHASE_KO.get(a, a or '미확인')}→{PHASE_KO.get(b, b)}")
    old_b, new_b = old.get("bottlenecks") or {}, new.get("bottlenecks") or {}
    labels = {"tester": "테스터", "substrate": "기판", "hbm": "HBM", "cowos": "CoWoS"}
    for key in sorted(set(old_b) | set(new_b)):
        a = (old_b.get(key) or {}).get("status")
        b = (new_b.get(key) or {}).get("status")
        if a != b and b:
            reasons.append(f"{labels.get(key,key)} 병목 {a or '미확인'}→{b}")
    if (
        old.get("fab_count_evidence_state") != "official"
        and new.get("fab_count_evidence_state") == "official"
        and new.get("chiayi_total_fabs")
    ):
        reasons.append("嘉義 총 공장 수가 공급망 보도→공식 확인으로 승격")
    return reasons


def hbm_cross_reasons(old, new):
    reasons = []
    for field, label in (("cowos_capacity_wpm", "CoWoS 월 생산능력"), ("soic_capacity_wpm", "SoIC 월 생산능력")):
        a, b = old.get(field), new.get(field)
        if a != b and b is not None:
            if a:
                reasons.append(f"{label} {int(a):,}→{int(b):,}장")
            else:
                reasons.append(f"{label} {int(b):,}장 신규 확인")
    old_fabs, new_fabs = old.get("fabs") or {}, new.get("fabs") or {}
    for fab in sorted(set(old_fabs) | set(new_fabs)):
        a = (old_fabs.get(fab) or {}).get("status")
        b = (new_fabs.get(fab) or {}).get("status")
        if a != b and PHASE_RANK.get(b, 0) >= PHASE_RANK["tool_move_in"]:
            reasons.append(f"{fab}가 {PHASE_KO.get(b,b)} 단계로 진입")
    old_b, new_b = old.get("bottlenecks") or {}, new.get("bottlenecks") or {}
    labels = {"tester": "테스터", "substrate": "기판", "hbm": "HBM", "cowos": "CoWoS"}
    for key in ("tester", "substrate", "hbm", "cowos"):
        a = (old_b.get(key) or {}).get("status")
        b = (new_b.get(key) or {}).get("status")
        if a != b and b:
            reasons.append(f"{labels[key]} 병목 {a or '미확인'}→{b}")
    return reasons


def load_state(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"watch_version": WATCH_VERSION, "current_state": {}}


def save_state(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def href(url, label="원문"):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def evidence_ko(state):
    return {
        "official": "공식자료",
        "top_tier_report": "주요 통신·중앙사 보도",
        "supply_chain_report": "공급망·업계 보도",
        "reported": "보도 단계",
    }.get(state or "", "확인 단계")


def package_alert_text(new, reasons, checked):
    lines = [
        "🚨 <b>TSMC 첨단패키징·嘉義 상태 변화</b>",
        "━━━━━━━━━━━━━━━━",
        "• 이번 변화: <b>" + html.escape(" · ".join(reasons)) + "</b>",
    ]
    if new.get("chiayi_total_fabs") is not None:
        extra = f" · 추가 {new.get('chiayi_additional_fabs')}개" if new.get("chiayi_additional_fabs") is not None else ""
        lines.append(f"• 嘉義 공장 수: <b>총 {new['chiayi_total_fabs']}개{extra}</b>")
        lines.append("• 공장 수 확인 수준: " + evidence_ko(new.get("fab_count_evidence_state")))
    if new.get("chiayi_phase3_status"):
        lines.append("• 嘉科 확대 단계: <b>" + html.escape(PHASE_KO.get(new["chiayi_phase3_status"], new["chiayi_phase3_status"])) + "</b>")
        lines.append("• 확대 단계 확인 수준: " + evidence_ko(new.get("phase3_evidence_state")))
    if new.get("cowos_capacity_wpm"):
        lines.append(f"• CoWoS 월 생산능력: {int(new['cowos_capacity_wpm']):,}장")
    if new.get("soic_capacity_wpm"):
        lines.append(f"• SoIC 월 생산능력: {int(new['soic_capacity_wpm']):,}장")
    changed_fabs = [r for r in reasons if re.match(r"P\d+ ", r)]
    if changed_fabs:
        lines.append("• 공장별 단계: " + html.escape(" · ".join(changed_fabs)))
    lines.append("• 다음 확인: TSMC 공식 투자결정·환경영향평가·착공·장비 발주/반입·시험생산·양산·실제 월 생산능력")
    lines.append("• 중복 방지: 같은 기사 재배포·제목 변경만으로는 다시 알리지 않습니다.")
    if new.get("last_source_url"):
        lines.append("• 근거: " + html.escape(new.get("last_source_name") or "출처") + " · " + href(new["last_source_url"]))
    lines.append("• 조회: " + checked.strftime("%Y-%m-%d %H:%M KST"))
    return "\n".join(lines) + "\n"


def hbm_alert_text(new, reasons, checked):
    lines = [
        "🚨 <b>HBM 교차 알림 | TSMC 첨단패키징 병목 변화</b>",
        "━━━━━━━━━━━━━━━━",
        "• HBM 알림 사유: <b>" + html.escape(" · ".join(reasons)) + "</b>",
        "• 전파 경로: CoWoS·SoIC 실제 처리능력/병목 → GPU·ASIC 패키지 출하 → HBM 탑재·출하 가능량",
        "• 알림 기준: 실제 생산능력 숫자 변화, 장비 반입·양산 진입, 테스터·기판·HBM·CoWoS 병목 변화만 교차 알림합니다.",
        "• 제외: 부지 검토·공장 의향·같은 기사 재배포만으로는 HBM 알림을 울리지 않습니다.",
    ]
    if new.get("cowos_capacity_wpm"):
        lines.append(f"• CoWoS 월 생산능력: {int(new['cowos_capacity_wpm']):,}장")
    if new.get("soic_capacity_wpm"):
        lines.append(f"• SoIC 월 생산능력: {int(new['soic_capacity_wpm']):,}장")
    if new.get("last_source_url"):
        lines.append("• 근거: " + html.escape(new.get("last_source_name") or "출처") + " · " + href(new["last_source_url"]))
    lines.append("• 조회: " + checked.strftime("%Y-%m-%d %H:%M KST"))
    return "\n".join(lines) + "\n"


def run(mode):
    checked = now_kst()
    state_path = PACKAGE_STATE if mode == "package" else HBM_STATE
    alert_path = PACKAGE_ALERT if mode == "package" else HBM_ALERT
    status_path = PACKAGE_STATUS if mode == "package" else HBM_STATUS
    state = load_state(state_path)
    current = dict(state.get("current_state") or {})
    candidate = dict(current)
    last_event = None

    cutoff = checked - timedelta(days=21)
    events = read_events()
    for event in events:
        try:
            dt = datetime.fromisoformat(event.get("published_at_kst") or "")
        except Exception:
            continue
        if dt < cutoff or dt > checked + timedelta(minutes=10):
            continue
        patch = extract_patch(event)
        if not patch:
            continue
        before = candidate
        candidate = merge_state(candidate, patch)
        if candidate != before:
            last_event = event

    reasons = material_changes(current, candidate) if mode == "package" else hbm_cross_reasons(current, candidate)
    state["watch_version"] = WATCH_VERSION
    state["last_checked_at_kst"] = checked.isoformat(timespec="seconds")
    state["current_state"] = candidate
    if last_event:
        state["last_evidence_url"] = last_event.get("direct_link") or ""
        state["last_evidence_published_at_kst"] = last_event.get("published_at_kst") or ""

    alert_path.parent.mkdir(exist_ok=True)
    if reasons:
        text = package_alert_text(candidate, reasons, checked) if mode == "package" else hbm_alert_text(candidate, reasons, checked)
        alert_path.write_text(text, encoding="utf-8")
        state["last_alert_reasons"] = reasons
        state["last_alert_at_kst"] = checked.isoformat(timespec="seconds")
    else:
        alert_path.unlink(missing_ok=True)

    save_state(state_path, state)
    save_state(status_path, {
        "mode": mode,
        "checked_at_kst": checked.isoformat(timespec="seconds"),
        "events_scanned": len(events),
        "changes": reasons,
        "current_state": candidate,
    })
    print(f"tsmc_advanced_packaging_watch mode={mode} changes={len(reasons)}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["package", "hbm"], required=True)
    run(p.parse_args().mode)


if __name__ == "__main__":
    main()
