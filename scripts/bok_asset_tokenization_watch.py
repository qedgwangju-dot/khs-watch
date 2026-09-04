from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "bok_asset_tokenization_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

SOURCES = [
    {
        "name": "한국은행 보도자료",
        "url": "https://www.bok.or.kr/portal/bbs/B0000502/list.do?menuNo=201265",
        "base": "https://www.bok.or.kr",
    },
    {
        "name": "한국은행 조사연구",
        "url": "https://www.bok.or.kr/portal/bbs/P0002353/list.do?menuNo=200433",
        "base": "https://www.bok.or.kr",
    },
    {
        "name": "금융위원회 금융정책",
        "url": "https://www.fsc.go.kr/po010101",
        "base": "https://www.fsc.go.kr",
    },
    {
        "name": "한국예탁결제원",
        "url": "https://www.ksd.or.kr/ko/",
        "base": "https://www.ksd.or.kr",
    },
]

PRIMARY = (
    "자산토큰", "자산 토큰", "국채토큰", "국채 토큰", "토큰화 국채", "국채 토큰화",
    "통합원장", "통합 원장", "프로젝트 한강", "예금토큰", "예금 토큰",
    "토큰증권", "토큰 증권", "디지털화폐", "CBDC",
)
SECONDARY = (
    "참여기관", "참여 기관", "참여은행", "참여 은행", "증권사", "예탁결제원",
    "사업자", "시스템 구축", "구축사업", "입찰", "조달", "우선협상", "수주",
    "시범사업", "실증", "실거래", "2027",
)

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        ctype = r.headers.get_content_charset() or "utf-8"
    return raw.decode(ctype, errors="replace")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def relevant(text: str) -> bool:
    low = text.lower()
    primary_hit = any(k.lower() in low for k in PRIMARY)
    if not primary_hit:
        return False
    return True


def classify(text: str) -> str:
    low = text.lower()
    if any(k.lower() in low for k in ("입찰", "조달", "우선협상", "수주", "시스템 구축", "구축사업")):
        return "시스템 구축·조달"
    if any(k.lower() in low for k in ("참여기관", "참여 기관", "참여은행", "참여 은행", "증권사", "예탁결제원", "사업자")):
        return "참여기관·당사자"
    if any(k.lower() in low for k in ("국채토큰", "국채 토큰", "토큰화 국채", "국채 토큰화")):
        return "국채 토큰화"
    if any(k.lower() in low for k in ("통합원장", "통합 원장")):
        return "통합원장"
    if any(k.lower() in low for k in ("프로젝트 한강", "예금토큰", "예금 토큰")):
        return "프로젝트 한강·예금토큰"
    return "자산 토큰화"


def extract(source: dict) -> list[dict]:
    page = fetch(source["url"])
    soup = BeautifulSoup(page, "html.parser")
    rows: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        title = clean(a.get_text(" ", strip=True))
        if len(title) < 4:
            continue
        href = urllib.parse.urljoin(source["base"], a.get("href", ""))
        parent_text = clean(a.parent.get_text(" ", strip=True)) if a.parent else title
        combined = title if len(parent_text) > 400 else parent_text
        if not relevant(combined):
            continue
        key = hashlib.sha256((source["name"] + "|" + title + "|" + href).encode()).hexdigest()[:24]
        rows[key] = {
            "id": key,
            "source": source["name"],
            "title": title[:300],
            "context": combined[:500],
            "url": href,
            "category": classify(combined),
        }
    return list(rows.values())


def source_link(url: str) -> str:
    safe_url = html.escape(url, quote=True)
    if url.startswith(("https://", "http://")):
        return f'<a href="{safe_url}">원문</a>'
    return "원문 링크 없음"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    all_items: dict[str, dict] = {}
    errors: list[str] = []
    for src in SOURCES:
        try:
            for item in extract(src):
                all_items[item["id"]] = item
        except Exception as e:
            errors.append(f"{src['name']}: {type(e).__name__}: {e}")

    previous = {"items": {}}
    first_run = not DATA.exists()
    if DATA.exists():
        try:
            previous = json.loads(DATA.read_text(encoding="utf-8"))
        except Exception:
            previous = {"items": {}}

    old_ids = set((previous.get("items") or {}).keys())
    new_items = [v for k, v in all_items.items() if k not in old_ids]

    pending = {
        "updated_at_kst": now,
        "items": all_items,
        "errors": errors,
    }
    (OUT / "bok_asset_tokenization_pending_state.json").write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if first_run:
        (OUT / "bok_asset_tokenization_rebaseline.txt").write_text(
            "Initial baseline created; no Telegram alert sent.\n", encoding="utf-8"
        )

    if (not first_run) and new_items:
        priority = sorted(
            new_items,
            key=lambda x: (
                0 if x["category"] in {"참여기관·당사자", "시스템 구축·조달", "국채 토큰화"} else 1,
                x["source"],
                x["title"],
            ),
        )
        lines = [
            "🔔 <b>한국은행 자산토큰화·국채토큰화 새 공식 업데이트</b>",
            "",
            f"확인 시각: {html.escape(now)}",
        ]
        for item in priority[:8]:
            lines += [
                "",
                f"[{html.escape(item['category'])}] {html.escape(item['title'])}",
                f"출처: {html.escape(item['source'])} · {source_link(item['url'])}",
            ]
        if len(priority) > 8:
            lines += ["", f"그 외 신규 항목 {len(priority)-8}건"]
        if errors:
            lines += ["", "⚠️ 일부 공식 페이지 조회 오류: " + html.escape(" | ".join(errors[:3]))]
        (OUT / "bok_asset_tokenization_alert.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    status = [
        "# BOK Asset Tokenization Watch",
        f"- checked_at_kst: {now}",
        f"- official_items: {len(all_items)}",
        f"- new_items: {0 if first_run else len(new_items)}",
        f"- first_run_baseline: {str(first_run).lower()}",
        f"- source_errors: {len(errors)}",
    ]
    if errors:
        status.extend([f"  - {e}" for e in errors])
    (OUT / "bok_asset_tokenization_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
