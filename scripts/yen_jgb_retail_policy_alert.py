#!/usr/bin/env python3
"""Detect material Japanese retail-JGB tax-policy changes without forcing a yen direction."""
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

UTC = dt.timezone.utc
KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 khs-yen-jgb-retail-policy/1.0"
MAX_AGE_HOURS = 12
COOLDOWN_HOURS = 24
STATE = pathlib.Path("data/yen_jgb_retail_policy_state.json")
PENDING = pathlib.Path("out/yen_jgb_retail_policy_pending.json")
BODY = pathlib.Path("out/yen_jgb_retail_policy_alert.html")
TITLE = pathlib.Path("out/yen_jgb_retail_policy_title.txt")
SUMMARY = pathlib.Path("out/yen_jgb_retail_policy_watch.md")
TRANSLATE = "https://translate.googleapis.com/translate_a/single"

QUERIES = (
    ("en", 'Japan retail JGB tax incentives individual investors Katayama'),
    ("en", 'Japanese government bonds retail investors tax reform NISA inheritance tax'),
    ("ja", '個人向け国債 税制優遇 税制改正 片山'),
    ("ja", '個人向け国債 NISA 相続税 財務省'),
    ("ko", '일본 개인 국채 세제 혜택 재무상'),
    ("ko", '일본 국채 개인투자자 세제 개편 NISA 상속세'),
)

JGB = ("jgb", "japanese government bond", "japanese government bonds", "government bond", "国債", "個人向け国債", "일본 국채", "개인 국채")
RETAIL = ("retail investor", "retail investors", "individual investor", "individual investors", "個人投資家", "個人向け", "개인 투자자", "개인투자자", "개인용")
TAX = ("tax incentive", "tax incentives", "tax break", "tax benefits", "tax benefit", "tax reform", "tax-free", "nisa", "inheritance tax", "税制優遇", "税制改正", "非課税", "相続税", "세제 혜택", "세제혜택", "세제 개편", "세제개정", "비과세", "상속세")
REVIEW = ("consider", "considering", "carefully consider", "discuss", "discussion", "request", "requests", "study", "review", "検討", "議論", "要望", "세제 혜택 방안", "검토", "논의", "요청")
DECISION = ("decide", "decided", "approve", "approved", "adopt", "adopted", "include in tax reform", "enact", "enacted", "決定", "了承", "採用", "盛り込", "확정", "결정", "승인", "도입", "시행")
GOVERNMENT = ("finance minister", "ministry of finance", "government", "katayama", "財務相", "財務省", "政府", "片山", "재무상", "재무성", "정부", "가타야마")

MAJOR = ("reuters", "bloomberg", "kyodo", "共同通信", "nikkei", "日本経済新聞", "financial times", "nhk", "associated press", "ap news", "wall street journal", "wsj")
OFFICIAL = ("ministry of finance", "財務省", "mof.go.jp")

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


def has(text: str, words: tuple[str, ...]) -> bool:
    low = html.unescape(text or "").lower()
    return any(w.lower() in low for w in words)


def source_level(item: Item) -> int:
    src = item.source.lower()
    if any(x in src for x in OFFICIAL):
        return 3
    if any(x in src for x in MAJOR) or "reuters" in item.text.lower():
        return 1
    return 0


def classify(item: Item) -> tuple[str, int] | None:
    text = item.text
    if not (has(text, JGB) and has(text, RETAIL) and has(text, GOVERNMENT)):
        return None
    if not has(text, TAX):
        return None
    if has(text, DECISION):
        return "일본 국채 개인투자 세제지원 확정·구체화", 5
    if has(text, REVIEW):
        return "일본 국채 수요 확충·개인투자자 세제지원 검토", 3
    return None


def google_url(lang: str, q: str) -> str:
    if lang == "ja":
        p = {"q": q, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}
    elif lang == "ko":
        p = {"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    else:
        p = {"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(p)


def fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def pubdate(s: str) -> dt.datetime | None:
    try:
        x = email.utils.parsedate_to_datetime(s)
    except Exception:
        return None
    if x.tzinfo is None:
        x = x.replace(tzinfo=UTC)
    return x.astimezone(UTC)


def parse_rss(text: str) -> list[Item]:
    root = ET.fromstring(text)
    out: list[Item] = []
    for n in root.findall(".//item"):
        title = (n.findtext("title") or "").strip()
        link = (n.findtext("link") or "").strip()
        desc = (n.findtext("description") or "").strip()
        source_node = n.find("source")
        source = (source_node.text or "").strip() if source_node is not None else ""
        when = pubdate((n.findtext("pubDate") or "").strip())
        if title and link and when:
            out.append(Item(title, link, source, desc, when))
    return out


def translate(title: str) -> str:
    if re.search(r"[가-힣]", title):
        return re.sub(r"\s+-\s+[^-]+$", "", title).strip()
    clean = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
    try:
        p = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": clean})
        data = json.loads(fetch(f"{TRANSLATE}?{p}", timeout=8))
        result = "".join(str(x[0]) for x in (data[0] or []) if isinstance(x, list) and x and x[0]).strip()
        if re.search(r"[가-힣]", result):
            return result
    except Exception:
        pass
    return "일본 정부, 개인투자자용 국채 세제지원 방안 검토 관련 주요 보도"


def load_state() -> dict:
    try:
        x = json.loads(STATE.read_text(encoding="utf-8"))
        return x if isinstance(x, dict) else {}
    except Exception:
        return {}


def save(path: pathlib.Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def should_send(item: Item, topic: str, score: int, level: int, state: dict, now: dt.datetime) -> bool:
    if item.item_id in set(state.get("seen", [])):
        return False
    if level == 0:
        return False
    prev = state.get("cluster") or {}
    elapsed = now.timestamp() - float(prev.get("sent_epoch") or 0)
    return elapsed >= COOLDOWN_HOURS * 3600 or score > int(prev.get("score") or 0) or level > int(prev.get("level") or 0)


def impact_lines(topic: str) -> list[str]:
    finalized = "확정" in topic
    return [
        "원문 성격: " + ("세제지원이 확정·구체화된 단계" if finalized else "세제 혜택을 신중히 검토·논의하는 단계 — 확정·시행 아님"),
        "수급: 개인의 JGB 수요 확대 가능 → BOJ 국채매입 감액을 보완할 국내 소화 기반 강화 가능",
        "할인율: JGB 수요가 늘면 장기금리 급등 압력을 완화할 수 있으나, 세제안·규모가 미정이면 효과도 미확정",
        "엔화·엔캐리: 국내채권 선호 증가는 해외자산 매수 감소로 엔화에 우호적일 수 있지만 JGB 금리 안정·하락은 금리차를 유지할 수 있어 방향 단정 금지",
        "시간표: 세제개정 요청 → 여당·정부 협의 → NISA·상속세·이자과세 등 적용대상 → 시행시점 확인",
    ]


def main(now: dt.datetime | None = None) -> int:
    now = (now or dt.datetime.now(UTC)).astimezone(UTC)
    unique: dict[str, Item] = {}
    errors: list[str] = []
    for lang, q in QUERIES:
        try:
            for item in parse_rss(fetch(google_url(lang, q))):
                unique[item.item_id] = item
        except Exception as e:
            errors.append(f"{lang}:{type(e).__name__}")
    cutoff = now - dt.timedelta(hours=MAX_AGE_HOURS)
    candidates: list[tuple[Item, str, int, int]] = []
    for item in unique.values():
        if not (cutoff <= item.published <= now + dt.timedelta(minutes=10)):
            continue
        c = classify(item)
        if not c:
            continue
        topic, score = c
        candidates.append((item, topic, score, source_level(item)))
    candidates.sort(key=lambda x: (x[3], x[2], x[0].published), reverse=True)
    state = load_state()
    selected = next((x for x in candidates if should_send(*x, state, now)), None)
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(f"# JGB 개인투자 세제정책 감시\n- 후보: {len(candidates)}\n- 오류: {len(errors)}\n", encoding="utf-8")
    for p in (BODY, TITLE, PENDING):
        if p.exists():
            p.unlink()
    if not selected:
        return 0
    item, topic, score, level = selected
    rank = "공식 확인" if level >= 3 else "미확인 주요보도"
    headline = translate(item.title)
    TITLE.write_text(f"⚠️ 엔화 정책 촉매 알림 — {rank}\n", encoding="utf-8")
    lines = [
        f"조회 시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        "가격 조건과 별개인 JGB 수요·재정정책 선행 경보입니다.",
        "",
        f"1) {topic} · {rank}",
        f"출처: {html.escape(item.source or '주요매체')} · {item.published.astimezone(KST).strftime('%m-%d %H:%M KST')} · <a href=\"{html.escape(item.link, quote=True)}\">원문</a>",
        f"원문 번역: {html.escape(headline)}",
        *[html.escape(x) for x in impact_lines(topic)],
        "",
        "주의: 세제 검토와 세제 확정을 구분하며, 이 정책만으로 엔화 방향을 단정하지 않습니다.",
    ]
    BODY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    new_state = {
        "seen": (list(state.get("seen", [])) + [item.item_id])[-200:],
        "cluster": {"topic": topic, "score": score, "level": level, "sent_epoch": now.timestamp(), "headline": item.title},
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
    }
    save(PENDING, new_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
