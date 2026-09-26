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

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "solidigm_ipo_watch_state.json"
ALERT = ROOT / "out" / "solidigm_ipo_alert.html"
UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
WATCH_VERSION = 1

QUERIES = [
    '"Solidigm" IPO',
    '"Solidigm" Reuters IPO',
    '"Solidigm" underwriters IPO',
    '"Solidigm" "confidential filing" IPO',
    '"Solidigm" "S-1" IPO',
    '"Solidigm" valuation IPO SK hynix',
    '"Solidigm" pre-IPO SK hynix',
    'site:news.skhynix.com Solidigm IPO',
    'site:solidigm.com Solidigm IPO',
]

TRUSTED = (
    "reuters", "bloomberg", "financial times", "ft.com", "wall street journal", "wsj",
    "cnbc", "business times", "korea times", "investing.com", "seoul economic",
    "서울경제", "sk hynix", "sk하이닉스", "solidigm", "sec",
)

STAGE_RANK = {
    "exploring": 1,
    "bank_bakeoff": 2,
    "underwriters_selected": 3,
    "confidential_filing": 4,
    "public_filing": 5,
    "roadshow": 6,
    "price_range": 7,
    "priced": 8,
    "listed": 9,
}
STAGE_KO = {
    "exploring": "상장 검토",
    "bank_bakeoff": "주관사 선정 경쟁(피치 미팅)",
    "underwriters_selected": "대표주관사·주관단 선정",
    "confidential_filing": "SEC 비공개 예비서류 제출",
    "public_filing": "SEC 공개 상장신고서 제출",
    "roadshow": "수요예측·로드쇼",
    "price_range": "공모가 밴드 제시",
    "priced": "공모가 확정",
    "listed": "상장·거래 개시",
    "postponed": "상장 연기",
    "withdrawn": "상장 철회",
}

def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul"))

def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
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

def rss_url(q, lang):
    enc = urllib.parse.quote(q)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={enc}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={enc}&hl=en-US&gl=US&ceid=US:en"

def decode_google(url):
    if "news.google.com" not in (url or ""):
        return url
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(url, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            direct = str(result.get("decoded_url") or "").strip()
            if direct.startswith("http") and "news.google.com" not in direct:
                return direct
    except Exception:
        pass
    return ""

def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"watch_version": WATCH_VERSION, "current_state": {}, "seen_urls": []}

def save_state(obj):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def source_rank(source, url):
    text = ((source or "") + " " + (url or "")).lower()
    if "sec.gov" in text or "solidigm.com" in text or "skhynix.com" in text or "sk hynix" in text or "sk하이닉스" in text:
        return 100
    if "reuters" in text:
        return 95
    if "bloomberg" in text or "ft.com" in text or "financial times" in text or "wsj" in text:
        return 90
    if "cnbc" in text or "business times" in text or "korea times" in text:
        return 80
    if "investing.com" in text or "seoul economic" in text or "서울경제" in text:
        return 70
    return 20

def evidence_state(source, url):
    text = ((source or "") + " " + (url or "")).lower()
    if "sec.gov" in text or "solidigm.com" in text or "skhynix.com" in text or "sk hynix" in text or "sk하이닉스" in text:
        return "official"
    if "reuters" in text:
        return "top_tier_report"
    return "reported"

def read_events():
    rows = {}
    for q in QUERIES:
        for lang in ("en", "ko"):
            try:
                root = ET.fromstring(fetch(rss_url(q, lang)))
            except Exception:
                continue
            for item in root.findall("./channel/item"):
                title = clean(item.findtext("title") or "")
                desc = clean(item.findtext("description") or "")
                link = clean(item.findtext("link") or "")
                source_node = item.find("source")
                source = clean(source_node.text if source_node is not None and source_node.text else "")
                pub = parse_pub(clean(item.findtext("pubDate") or ""))
                text = (title + " " + desc).lower()
                if "solidigm" not in text:
                    continue
                if not any(k in text for k in ("ipo", "initial public offering", "상장", "공모", "pre-ipo", "underwriter", "주관사", "s-1", "sec")):
                    continue
                if source and not any(x in source.lower() for x in TRUSTED):
                    if not any(x in text for x in ("reuters", "sk hynix", "sk하이닉스", "solidigm")):
                        continue
                direct = decode_google(link)
                if not direct:
                    continue
                key = hashlib.sha256((title + "|" + source).encode()).hexdigest()[:24]
                rows[key] = {
                    "id": key, "title": title, "description": desc, "source": source or "출처 미표시",
                    "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                    "direct_link": direct, "rank": source_rank(source, direct),
                }
    return sorted(rows.values(), key=lambda x: (x.get("published_at_kst") or "", x.get("rank", 0)))

def article_text(event):
    url = event.get("direct_link") or ""
    try:
        raw = fetch(url, timeout=16).decode("utf-8", errors="ignore")
        return clean(raw)[:40000]
    except Exception:
        return ""

def usd_amount(text, context_pattern):
    patterns = [
        context_pattern + r"[^$]{0,100}?(?:US\$|\$)\s*([\d.]+)\s*(billion|million|B|M)\b",
        r"(?:US\$|\$)\s*([\d.]+)\s*(billion|million|B|M)\b[^.]{0,120}?" + context_pattern,
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            n = float(m[1])
            return n * (1_000_000_000 if m[2].lower() in ("billion", "b") else 1_000_000)
    return None

def stage_from_text(text):
    low = text.lower()
    if re.search(r"withdrawn|withdraws|cancelled|canceled|철회|취소", text, re.I):
        return "withdrawn"
    if re.search(r"postponed|delayed|연기|미뤘", text, re.I):
        return "postponed"
    if re.search(r"began trading|begins trading|listed on|상장\s*(?:완료|첫날|거래)", text, re.I):
        return "listed"
    if re.search(r"priced (?:its|the) ipo|ipo price|공모가\s*확정", text, re.I):
        return "priced"
    if re.search(r"price range|pricing range|공모가\s*(?:밴드|범위)", text, re.I):
        return "price_range"
    if re.search(r"roadshow|bookbuilding|수요예측|로드쇼", text, re.I):
        return "roadshow"
    if re.search(r"filed[^.]{0,80}?(?:s-1|f-1)|publicly filed|상장신고서\s*제출", text, re.I):
        return "public_filing"
    if re.search(r"confidential(?:ly)?\s+(?:filed|submitted)|draft registration statement|비공개[^.]{0,30}?(?:제출|신고)", text, re.I):
        return "confidential_filing"
    if re.search(r"selected[^.]{0,60}?(?:banks|underwriters)|appointed[^.]{0,60}?(?:banks|underwriters)|대표주관사[^.]{0,30}?(?:선정|확정)|주관사[^.]{0,30}?(?:선정|확정)", text, re.I):
        return "underwriters_selected"
    if re.search(r"bake[- ]?off|pitch meetings?|주관사[^.]{0,60}?(?:피치|경쟁|선정 절차)", text, re.I):
        return "bank_bakeoff"
    if re.search(r"weighs? (?:an )?ipo|considering (?:an )?ipo|explor(?:e|ing)[^.]{0,40}?ipo|상장\s*검토|ipo\s*검토", text, re.I):
        return "exploring"
    return ""

def extract_patch(event):
    base = clean(f"{event.get('title','')} {event.get('description','')}")
    page = article_text(event)
    text = (base + " " + page).strip()
    low = text.lower()
    if "solidigm" not in low:
        return {}

    patch = {}
    stage = stage_from_text(text)
    if stage:
        patch["stage"] = stage

    y = re.search(r"(?:as early as|earliest|이르면)\s*(20\d{2})", text, re.I)
    if y:
        patch["target_year"] = int(y[1])

    valuation = usd_amount(text, r"(?:valu(?:e|ed|ation)|기업가치)")
    if valuation is not None and valuation >= 10_000_000_000:
        patch["valuation_max_usd"] = valuation

    raise_amt = usd_amount(text, r"(?:raise|raising|proceeds|조달)")
    if raise_amt is not None and 1_000_000_000 <= raise_amt < 100_000_000_000:
        patch["raise_target_usd"] = raise_amt

    pre = usd_amount(text, r"(?:pre[- ]?ipo|프리[- ]?ipo)")
    if pre is not None:
        patch["pre_ipo_raise_usd"] = pre

    if re.search(r"primary shares|new shares|신주", text, re.I):
        patch["primary_secondary_mix"] = "primary_included"
    if re.search(r"secondary shares|existing shares|구주매출|구주", text, re.I):
        patch["primary_secondary_mix"] = "secondary_included" if "primary_secondary_mix" not in patch else "primary_and_secondary"

    stake = re.search(r"(?:post[- ]ipo|after (?:the )?ipo|상장\s*후)[^%]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,60}?(?:stake|ownership|지분)", text, re.I)
    if stake:
        patch["parent_post_ipo_stake_pct"] = float(stake[1])

    underwriters = []
    for bank in ("Goldman Sachs", "Morgan Stanley", "J.P. Morgan", "JPMorgan", "Bank of America", "BofA", "Citi", "Citigroup", "Barclays", "UBS"):
        if bank.lower() in low:
            underwriters.append(bank)
    if underwriters and stage in ("underwriters_selected", "confidential_filing", "public_filing", "roadshow", "price_range", "priced"):
        patch["underwriters"] = sorted(set(underwriters))

    use = []
    if re.search(r"u\.s\.?\s+(?:fab|factory|plant|manufacturing)|미국[^.]{0,40}?(?:공장|생산시설)", text, re.I):
        use.append("미국 NAND 생산거점")
    if re.search(r"ai[^.]{0,60}?(?:storage|ssd|data center)|기업용\s*ssd|ai\s*스토리지", text, re.I):
        use.append("AI·기업용 SSD 성장투자")
    if use and re.search(r"proceeds|fund|finance|조달자금|자금", text, re.I):
        patch["use_of_proceeds"] = sorted(set(use))

    patch["evidence_state"] = evidence_state(event.get("source"), event.get("direct_link"))
    patch["source_url"] = event.get("direct_link") or ""
    patch["source_name"] = event.get("source") or ""
    patch["source_published_at_kst"] = event.get("published_at_kst") or ""
    return patch

def merge_state(current, patch):
    out = dict(current or {})
    old_stage = out.get("stage")
    new_stage = patch.get("stage")
    for k, v in patch.items():
        if k == "stage":
            continue
        if v not in (None, "", []):
            out[k] = v
    if new_stage:
        if new_stage in ("postponed", "withdrawn"):
            out["stage"] = new_stage
        elif old_stage in ("postponed", "withdrawn") and new_stage not in ("listed",):
            pass
        elif not old_stage or STAGE_RANK.get(new_stage, 0) >= STAGE_RANK.get(old_stage, 0):
            out["stage"] = new_stage
    return out

def material_changes(old, new):
    reasons = []
    if old.get("stage") != new.get("stage"):
        reasons.append(f"상장 단계 {STAGE_KO.get(old.get('stage'), old.get('stage','미확인'))}→{STAGE_KO.get(new.get('stage'), new.get('stage','미확인'))}")
    for field, label, min_abs in (
        ("valuation_max_usd", "기업가치", 10_000_000_000),
        ("raise_target_usd", "조달 규모", 1_000_000_000),
        ("pre_ipo_raise_usd", "Pre-IPO 조달", 500_000_000),
    ):
        a, b = old.get(field), new.get(field)
        if a and b:
            pct = (float(b) / float(a) - 1) * 100
            if abs(float(b) - float(a)) >= min_abs or abs(pct) >= 10:
                reasons.append(f"{label} {pct:+.1f}%")
        elif a is None and b is not None:
            reasons.append(f"{label} 신규 확인")
    if old.get("target_year") != new.get("target_year") and new.get("target_year"):
        reasons.append(f"목표 시점 {old.get('target_year','미확인')}→{new['target_year']}")
    if old.get("underwriters") != new.get("underwriters") and new.get("underwriters"):
        reasons.append("대표주관사·주관단 확인")
    if old.get("primary_secondary_mix") != new.get("primary_secondary_mix") and new.get("primary_secondary_mix"):
        reasons.append("신주·구주매출 구조 확인")
    if old.get("parent_post_ipo_stake_pct") != new.get("parent_post_ipo_stake_pct") and new.get("parent_post_ipo_stake_pct") is not None:
        reasons.append("SK하이닉스 상장 후 지분율 확인")
    if old.get("use_of_proceeds") != new.get("use_of_proceeds") and new.get("use_of_proceeds"):
        reasons.append("조달자금 용도 확인")
    if old.get("evidence_state") != "official" and new.get("evidence_state") == "official":
        reasons.append("신뢰보도→회사·SEC 공식 확인")
    return reasons

def krw_large(usd, rate):
    if usd is None or rate is None:
        return "원화 환산 확인 불가"
    eok = int(round(float(usd) * float(rate) / 100_000_000))
    if eok >= 10000:
        jo, rem = divmod(eok, 10000)
        return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
    return f"약 {eok:,}억원"

def usd_display(usd, rate):
    if usd is None:
        return "확인 불가"
    hundred_million = float(usd) / 100_000_000
    if abs(hundred_million - round(hundred_million)) < 1e-9:
        foreign = f"{int(round(hundred_million)):,}억달러"
    else:
        foreign = f"{hundred_million:,.1f}억달러"
    return f"{foreign}({krw_large(usd, rate)})"


def fx_quote():
    try:
        from fx_api import daily_krw
        q = daily_krw()
        return q.rate, q.basis
    except Exception:
        return None, "환율 확인 불가"

def href(url, label="원문"):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'

def alert_text(old, new, reasons, checked):
    rate, fx_basis = fx_quote()
    evidence_ko = {
        "official": "회사·SEC 공식 확인",
        "top_tier_report": "Reuters 복수 관계자 보도 단계",
        "reported": "신뢰 보도 단계",
    }.get(new.get("evidence_state"), "확인 단계")
    lines = [
        "🚨 <b>Solidigm IPO 상태 변화</b>",
        "━━━━━━━━━━━━━━━━",
        f"• 현재 단계: <b>{html.escape(STAGE_KO.get(new.get('stage'), new.get('stage','확인 불가')))}</b>",
        f"• 확인 수준: <b>{html.escape(evidence_ko)}</b>",
    ]
    if new.get("target_year"):
        lines.append(f"• 목표 시점: <b>이르면 {new['target_year']}년</b>")
    if new.get("valuation_max_usd"):
        lines.append(f"• 거론 기업가치: <b>최대 {usd_display(new['valuation_max_usd'], rate)}</b>")
    if new.get("raise_target_usd"):
        lines.append(f"• 조달 가능 규모: <b>{usd_display(new['raise_target_usd'], rate)}</b>")
    if new.get("pre_ipo_raise_usd"):
        lines.append(f"• Pre-IPO 별도 검토액: {usd_display(new['pre_ipo_raise_usd'], rate)}")
    if new.get("underwriters"):
        lines.append("• 주관사: " + html.escape(", ".join(new["underwriters"])))
    if new.get("primary_secondary_mix"):
        labels = {"primary_included":"신주 포함","secondary_included":"구주매출 포함","primary_and_secondary":"신주+구주매출"}
        lines.append("• 공모 구조: " + labels.get(new["primary_secondary_mix"], new["primary_secondary_mix"]))
    if new.get("parent_post_ipo_stake_pct") is not None:
        lines.append(f"• SK하이닉스 상장 후 지분율: {new['parent_post_ipo_stake_pct']:.1f}%")
    if new.get("use_of_proceeds"):
        lines.append("• 조달자금 용도: " + html.escape(" · ".join(new["use_of_proceeds"])))
    lines.append("• 이번 변화: <b>" + html.escape(" · ".join(reasons)) + "</b>")
    lines.append("• 다음 확인: 대표주관사 선정 · SEC 비공개/공개 신고 · 공모가 밴드 · 신주/구주 비중 · SK하이닉스 잔여지분 · 자금용도")
    if new.get("source_url"):
        lines.append(f"• 근거: {html.escape(new.get('source_name') or '출처')} · {href(new['source_url'])}")
    lines.append("• 주의: 기업가치·조달액·일정은 현재 확정값이 아니라 보도 단계이며 시장 상황에 따라 변경될 수 있습니다.")
    lines.append("• 환율: " + html.escape(fx_basis))
    lines.append("• 조회: " + checked.strftime("%Y-%m-%d %H:%M KST"))
    return "\n".join(lines) + "\n"

def main():
    checked = now_kst()
    state = load_state()
    current = dict(state.get("current_state") or {})
    candidate = dict(current)
    best_source = None

    cutoff = checked - timedelta(days=10)
    for event in read_events():
        try:
            dt = datetime.fromisoformat(event.get("published_at_kst") or "")
        except Exception:
            continue
        if dt < cutoff or dt > checked + timedelta(minutes=10):
            continue
        patch = extract_patch(event)
        if not patch:
            continue
        before = dict(candidate)
        candidate = merge_state(candidate, patch)
        if candidate != before:
            best_source = event

    reasons = material_changes(current, candidate)
    # Baseline carries the current Reuters report so initial integration stays silent.
    state["watch_version"] = WATCH_VERSION
    state["last_checked_at_kst"] = checked.isoformat(timespec="seconds")
    state["current_state"] = candidate
    if best_source:
        state["last_evidence_url"] = best_source.get("direct_link") or ""
        state["last_evidence_published_at_kst"] = best_source.get("published_at_kst") or ""

    ALERT.parent.mkdir(exist_ok=True)
    if reasons:
        ALERT.write_text(alert_text(current, candidate, reasons, checked), encoding="utf-8")
        state["last_alert_reasons"] = reasons
        state["last_alert_at_kst"] = checked.isoformat(timespec="seconds")
    else:
        ALERT.unlink(missing_ok=True)

    save_state(state)
    print("solidigm_ipo_watch=true changes=" + str(len(reasons)))


if __name__ == "__main__":
    main()
