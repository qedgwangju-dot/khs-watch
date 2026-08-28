#!/usr/bin/env python3
"""Alert on material Japan fiscal/JGB supply changes and always convert money to KRW."""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from krw_fx import FRED_USDJPY, FRED_USDKRW, JpyKrwQuote, format_krw, format_trillion_yen, latest_jpy_krw, yen_to_krw

UTC = dt.timezone.utc
KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 khs-japan-fiscal-jgb-supply/1.0"
MAX_AGE_HOURS = 18
COOLDOWN_HOURS = 24

STATE = pathlib.Path("data/japan_fiscal_jgb_supply_state.json")
PENDING = pathlib.Path("out/japan_fiscal_jgb_supply_pending.json")
BODY = pathlib.Path("out/japan_fiscal_jgb_supply_alert.html")
TITLE = pathlib.Path("out/japan_fiscal_jgb_supply_title.txt")
SUMMARY = pathlib.Path("out/japan_fiscal_jgb_supply_watch.md")

FY26_NEW_BONDS_TRILLION_YEN = 32.6975
FY27_DEBT_SERVICE_TRILLION_YEN = 36.6386
FY26_DEBT_SERVICE_INITIAL_TRILLION_YEN = 31.2758

MOF_FY26_ISSUANCE = "https://www.mof.go.jp/english/policy/jgbs/debt_management/plan/issuanceplan260603.pdf"
MOF_FY27_REQUEST = "https://www.mof.go.jp/about_mof/mof_budget/budget/fy2027/20260828.html"
MOF_ISSUANCE_INDEX = "https://www.mof.go.jp/english/policy/jgbs/debt_management/plan/index.htm"

QUERIES = (
    ("en", 'Japan FY2027 new bond issuance 40 trillion yen Takaichi Yomiuri'),
    ("en", 'Japan cap new government bond issuance fiscal 2027 Reuters'),
    ("en", 'Japan JGB issuance plan fiscal budget debt service long-term 20-year 30-year 40-year'),
    ("ja", '高市 新規国債 発行 40兆円 令和9年度 読売'),
    ("ja", '国債発行 計画 20年 30年 40年 財務省 令和9年度'),
    ("ko", '일본 신규 국채 발행 40조엔 다카이치 요미우리'),
    ("ko", '일본 국채 발행 규모 재정 예산 20년 30년 40년'),
    ("zh", '日本 新国债 40万亿日元 高市 读卖'),
)

MAJOR = (
    "reuters", "yomiuri", "読売", "bloomberg", "kyodo", "共同通信", "nikkei", "日本経済新聞",
    "financial times", "nhk", "wall street journal", "wsj", "associated press", "ap news",
)
OFFICIAL = ("ministry of finance", "財務省", "mof.go.jp")

NEW_ISSUANCE = (
    "new bond issuance", "new government bond issuance", "newly-issued bonds", "newly issued bonds",
    "新規国債", "新発国債", "国債発行", "신규 국채 발행", "신규국채 발행", "국채 발행 규모", "新国债发行",
)
SUPPLY_ACTION = (
    "cap", "limit", "keep", "restrain", "reduce", "cut", "increase", "raise", "target", "around",
    "抑制", "上限", "減額", "削減", "増額", "目標", "約", "제한", "억제", "축소", "증액", "목표", "약", "限制", "控制",
)
DEBT_SERVICE = ("debt service", "debt-servicing", "国債費", "국채비", "이자비용", "债务偿还")
MATURITY_SUPPLY = (
    "20-year", "30-year", "40-year", "super-long", "superlong", "超長期", "20年", "30年", "40年",
    "20년", "30년", "40년", "초장기", "超长期",
)
SUPPLY_CHANGE = ("issuance", "offering amount", "cut", "reduce", "increase", "発行", "減額", "増額", "발행", "축소", "증액", "发行")


@dataclass(frozen=True)
class Item:
    title: str
    link: str
    source: str
    description: str
    published: dt.datetime

    @property
    def text(self) -> str:
        return " ".join((self.title, self.description, self.source))

    @property
    def item_id(self) -> str:
        raw = f"{self.source}|{self.title}|{self.link}".lower()
        return hashlib.sha256(raw.encode()).hexdigest()[:24]


def has(text: str, markers: tuple[str, ...]) -> bool:
    low = html.unescape(text or "").lower()
    return any(marker.lower() in low for marker in markers)


def source_level(item: Item) -> int:
    src = item.source.lower()
    full = item.text.lower()
    if any(marker in src for marker in OFFICIAL):
        return 3
    if any(marker in src for marker in MAJOR) or "reuters" in full:
        return 1
    return 0


def classify(item: Item) -> tuple[str, int] | None:
    text = item.text
    if has(text, NEW_ISSUANCE) and has(text, SUPPLY_ACTION):
        return "일본 신규 국채 발행 목표·상한 변화", 5
    if has(text, DEBT_SERVICE) and has(text, SUPPLY_ACTION + ("record", "最高", "최대", "사상 최대")):
        return "일본 국채비·재정조달 부담 변화", 4
    if has(text, MATURITY_SUPPLY) and has(text, SUPPLY_CHANGE):
        return "일본 초장기 JGB 발행물량·만기구조 변화", 4
    return None


def google_url(lang: str, query: str) -> str:
    if lang == "ja":
        params = {"q": query, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}
    elif lang == "ko":
        params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    elif lang == "zh":
        params = {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def fetch(url: str, timeout: int = 18) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def pubdate(value: str) -> dt.datetime | None:
    try:
        result = email.utils.parsedate_to_datetime(value)
    except Exception:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def parse_rss(text: str) -> list[Item]:
    root = ET.fromstring(text)
    rows: list[Item] = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        desc = (node.findtext("description") or "").strip()
        source_node = node.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        published = pubdate((node.findtext("pubDate") or "").strip())
        if title and link and published:
            rows.append(Item(title, link, source, desc, published))
    return rows


def clean_title(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", re.sub(r"\s+-\s+[^-]+$", "", value)).strip()


def translate_conservative(title: str, topic: str) -> str:
    clean = clean_title(title)
    if re.search(r"[가-힣]", clean):
        return clean
    exact = clean.lower()
    if "40 trillion yen" in exact and "new" in exact and "bond" in exact:
        return "일본 정부, FY2027 신규 국채 발행을 약 40조엔으로 억제할 방침 — 총리 인터뷰"
    try:
        params = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": clean})
        data = json.loads(fetch("https://translate.googleapis.com/translate_a/single?" + params, timeout=8))
        result = "".join(str(x[0]) for x in (data[0] or []) if isinstance(x, list) and x and x[0]).strip()
        if re.search(r"[가-힣]", result):
            return result
    except Exception:
        pass
    return f"{topic} 관련 주요 보도"


def extract_trillion_yen(text: str) -> float | None:
    clean = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    patterns = (
        r"(\d+(?:\.\d+)?)\s*trillion\s+yen",
        r"(\d+(?:\.\d+)?)\s*兆円",
        r"(\d+(?:\.\d+)?)\s*조엔",
        r"(\d+(?:\.\d+)?)\s*万亿日元",
    )
    for pattern in patterns:
        match = re.search(pattern, clean, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def load_state() -> dict:
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def save(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def should_send(item: Item, score: int, level: int, state: dict, now: dt.datetime) -> bool:
    if item.item_id in set(state.get("seen", [])):
        return False
    if level == 0:
        return False
    prev = state.get("cluster") or {}
    elapsed = now.timestamp() - float(prev.get("sent_epoch") or 0)
    return elapsed >= COOLDOWN_HOURS * 3600 or score > int(prev.get("score") or 0) or level > int(prev.get("level") or 0)


def context_lines(topic: str, amount: float | None, quote: JpyKrwQuote) -> list[str]:
    lines: list[str] = []
    if topic == "일본 신규 국채 발행 목표·상한 변화":
        if amount is not None:
            lines.append(f"핵심 금액: FY2027 신규 국채 목표 {format_trillion_yen(amount, quote, 2)}")
            diff = amount - FY26_NEW_BONDS_TRILLION_YEN
            pct = diff / FY26_NEW_BONDS_TRILLION_YEN * 100.0
            diff_won = yen_to_krw(abs(diff) * 1_000_000_000_000.0, quote)
            direction = "상회" if diff >= 0 else "하회"
            sign = "+" if diff >= 0 else "-"
            lines.append(
                f"현재 기준 비교: FY2026 보정 신규국채 {format_trillion_yen(FY26_NEW_BONDS_TRILLION_YEN, quote, 4)} 대비 "
                f"{sign}{abs(diff):.4f}조엔 ({direction} {abs(pct):.1f}%, 약 {format_krw(diff_won)})"
            )
        else:
            lines.append("핵심 금액: 기사에서 신규 국채 목표액 자동 추출 실패 — 원문 숫자 확인 필요")
        lines.append(
            f"재정 부담: FY2027 국채비 요구 {format_trillion_yen(FY27_DEBT_SERVICE_TRILLION_YEN, quote, 4)} / "
            f"FY2026 초기 {format_trillion_yen(FY26_DEBT_SERVICE_INITIAL_TRILLION_YEN, quote, 4)}"
        )
        lines += [
            "정확한 의미: ‘40조엔으로 제한’은 현재 FY2026 보정 신규국채 32.6975조엔보다 낮다는 뜻이 아님. 현재 기준보다 높은 상한이면 재정규율 메시지와 실제 발행여력을 분리해서 봐야 함.",
            "수급: 실제 JGB 공급은 신규국채 총액뿐 아니라 차환채와 20·30·40년물 배분이 장기금리 압력을 좌우.",
            "엔화·엔캐리: JGB 금리 상승 + 미·일 단기금리차 축소 + USD/JPY 하락이 함께 나와야 엔캐리 청산 압력으로 승격. 재정 신뢰 훼손으로 엔화가 약해지면 반대 경로도 가능.",
            "시간표: FY2027 예산안 → 연말 JGB 발행계획 → 20·30·40년물 물량 → 실제 입찰 응찰배율·tail 확인.",
        ]
    elif topic == "일본 국채비·재정조달 부담 변화":
        lines += [
            f"현재 숫자: FY2027 국채비 요구 {format_trillion_yen(FY27_DEBT_SERVICE_TRILLION_YEN, quote, 4)} / FY2026 초기 {format_trillion_yen(FY26_DEBT_SERVICE_INITIAL_TRILLION_YEN, quote, 4)}",
            "정확한 의미: 이자·상환 비용 증가는 즉시 전 국채에 적용되는 것이 아니라 차환과 금리 재설정이 누적되면서 재정 부담으로 전이.",
            "엔화·엔캐리: 재정 우려에 따른 장기금리 상승과 BOJ 긴축에 따른 단기금리 상승은 의미가 다르므로 2년물·USD/JPY를 함께 확인.",
        ]
    else:
        if amount is not None:
            lines.append(f"발행 물량: {format_trillion_yen(amount, quote, 2)}")
        lines += [
            "정확한 의미: 초장기물 공급 변화는 총 신규국채액이 같아도 20·30·40년 금리와 보험사·연기금 수요에 직접 영향.",
            "엔화·엔캐리: 장기물 금리만으로 청산을 단정하지 않고 일본 2년물·미일 금리차·USD/JPY를 함께 확인.",
        ]
    lines.append(
        f"원화 환산 기준: 1엔={quote.krw_per_yen:.4f}원, 100엔={quote.krw_per_100_yen:,.2f}원 "
        f"(FRED H.10 동일 기준일 {quote.date}, USD/KRW {quote.usdkrw:,.2f} ÷ USD/JPY {quote.usdjpy:.2f})"
    )
    return lines


def main(now: dt.datetime | None = None) -> int:
    now = (now or dt.datetime.now(UTC)).astimezone(UTC)
    for path in (BODY, TITLE, PENDING):
        if path.exists():
            path.unlink()

    unique: dict[str, Item] = {}
    errors: list[str] = []
    for lang, query in QUERIES:
        try:
            for item in parse_rss(fetch(google_url(lang, query))):
                unique[item.item_id] = item
        except Exception as exc:
            errors.append(f"{lang}:{type(exc).__name__}")

    cutoff = now - dt.timedelta(hours=MAX_AGE_HOURS)
    candidates: list[tuple[Item, str, int, int]] = []
    for item in unique.values():
        if not (cutoff <= item.published <= now + dt.timedelta(minutes=10)):
            continue
        classified = classify(item)
        if not classified:
            continue
        topic, score = classified
        candidates.append((item, topic, score, source_level(item)))
    candidates.sort(key=lambda row: (row[3], row[2], row[0].published), reverse=True)

    state = load_state()
    selected = next((row for row in candidates if should_send(row[0], row[2], row[3], state, now)), None)
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(
        f"# 일본 재정·JGB 공급 정책 감시\n- 후보: {len(candidates)}\n- 검색 오류: {len(errors)}\n",
        encoding="utf-8",
    )
    if not selected:
        return 0

    item, topic, score, level = selected
    amount = extract_trillion_yen(item.text)
    try:
        quote = latest_jpy_krw()
    except Exception as exc:
        SUMMARY.write_text(
            SUMMARY.read_text(encoding="utf-8") + f"- 상태: 원화 환산 실패로 알림 송출 보류 — {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        return 2

    rank = "공식 확인" if level >= 3 else "미확인 주요보도"
    headline = translate_conservative(item.title, topic)
    TITLE.write_text(f"⚠️ 일본 재정·JGB 공급 촉매 — {rank}\n", encoding="utf-8")
    lines = [
        f"조회 시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        "",
        f"1) {topic} · {rank}",
        f"출처: {html.escape(item.source or '주요매체')} · {item.published.astimezone(KST).strftime('%m-%d %H:%M KST')} · <a href=\"{html.escape(item.link, quote=True)}\">원문</a>",
        f"원문 번역: {html.escape(headline)}",
        "확인 범위: 원문 헤드라인·Google News RSS 요약 + 일본 재무성 공식 수치",
        "원문 성격: 정부 목표·검토·보도 단계와 확정 예산·발행계획을 구분",
        "",
        *[html.escape(line) for line in context_lines(topic, amount, quote)],
        "",
        "출처 교차확인",
        f"- FY2026 JGB 발행계획 · <a href=\"{MOF_FY26_ISSUANCE}\">원문</a>",
        f"- FY2027 재무성 예산요구·국채비 · <a href=\"{MOF_FY27_REQUEST}\">원문</a>",
        f"- JGB 발행계획 목록 · <a href=\"{MOF_ISSUANCE_INDEX}\">원문</a>",
        f"- FRED USD/KRW · <a href=\"{FRED_USDKRW}\">원문</a>",
        f"- FRED USD/JPY · <a href=\"{FRED_USDJPY}\">원문</a>",
        "",
        "주의: 외화 금액은 원화 환산이 성공한 경우에만 Telegram으로 송출합니다.",
    ]
    BODY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    save(
        PENDING,
        {
            "seen": (list(state.get("seen", [])) + [item.item_id])[-300:],
            "cluster": {"topic": topic, "score": score, "level": level, "sent_epoch": now.timestamp(), "headline": item.title},
            "fx": {"date": quote.date, "usdkrw": quote.usdkrw, "usdjpy": quote.usdjpy, "krw_per_yen": quote.krw_per_yen},
            "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
