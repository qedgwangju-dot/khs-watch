from __future__ import annotations

import hashlib
import json
import pathlib
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "hbm_monthly_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"

# HSK 8542323000 = 복합구조칩 집적회로. HBM 전용 세번은 아니므로
# 항상 'HBM 대용지표'로만 표현한다.
HSK = "8542323000"
KSTAT_ITEM_URL = (
    "https://m.stat.kita.net/stat/pstat/popupItem.screen?"
    "CTR_GB=KTS&HS_YN=Y&MTI_YN=Y&SITC_YN=Y&canAddSearch=Y&"
    "chartPageNum=1&listCount=20&pageNum=1&s_ie_gbn=E&"
    "s_item_name=%EB%B3%B5%ED%95%A9%EA%B5%AC%EC%A1%B0%EC%B9%A9+%EC%A7%91%EC%A0%81%ED%9A%8C%EB%A1%9C&"
    "s_item_type=HS&s_item_value=8542323000&s_measure=1000&s_term_gb=M&stat_yn=Y"
)
KSTAT_MAIN_URL = "https://stat.kita.net/newMain.screen"
KSTAT_REGION_ITEM_URL = "https://stat.kita.net/stat/kts/prod/ProdItemImpExpList.screen"
KSTAT_REGION_COUNTRY_URL = "https://stat.kita.net/stat/kts/prod/ProdCtrImpExpList.screen"
KSTAT_ITEM_COUNTRY_URL = "https://stat.kita.net/stat/kts/pum/PumCtrImpExpList.screen"

# 공개 웹에서 월별 MCP/HBM 수출 차트를 꾸준히 올리는 보조 모니터.
# 숫자의 공식 원천은 K-stat/관세청이며, 이 채널은 공개 차트 발견용으로만 사용한다.
PUBLIC_CHANNEL = "https://t.me/s/Brain_And_Body_Research"
CHANNEL_QUERIES = [
    PUBLIC_CHANNEL,
    PUBLIC_CHANNEL + "?q=" + urllib.parse.quote("복합구조칩 집적회로"),
    PUBLIC_CHANNEL + "?q=" + urllib.parse.quote("HBM"),
    PUBLIC_CHANNEL + "?q=" + urllib.parse.quote("MCP"),
]

PRIMARY = (
    "복합구조칩 집적회로",
    "mcp",
    "hbm",
)
SECONDARY = (
    "삼성전자",
    "sk하이닉스",
    "하이닉스",
    "충남",
    "아산",
    "충북",
    "청주",
    "이천",
    "대만",
    "말레이시아",
)


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def relevant(text: str) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in PRIMARY) and any(k.lower() in low for k in SECONDARY)


def extract_public_posts() -> tuple[list[dict], list[str]]:
    posts: dict[str, dict] = {}
    errors: list[str] = []
    for url in CHANNEL_QUERIES:
        try:
            html = fetch(url)
            soup = BeautifulSoup(html, "html.parser")
            for wrap in soup.select(".tgme_widget_message_wrap"):
                msg = wrap.select_one(".tgme_widget_message")
                if msg is None:
                    continue
                data_post = (msg.get("data-post") or "").strip()
                if not data_post:
                    continue
                text_el = wrap.select_one(".tgme_widget_message_text")
                text = clean(text_el.get_text(" ", strip=True) if text_el else "")
                if not relevant(text):
                    continue
                time_el = wrap.select_one("time[datetime]")
                dt_raw = (time_el.get("datetime") if time_el else "") or ""
                try:
                    dt = datetime.fromisoformat(dt_raw.replace("Z", "+00:00"))
                    dt_kst = dt.astimezone(ZoneInfo("Asia/Seoul"))
                    published = dt_kst.isoformat(timespec="seconds")
                    published_month = dt_kst.strftime("%Y-%m")
                except Exception:
                    published = ""
                    published_month = ""
                post_url = "https://t.me/" + data_post
                post_id = hashlib.sha256(data_post.encode()).hexdigest()[:20]
                posts[post_id] = {
                    "id": post_id,
                    "data_post": data_post,
                    "url": post_url,
                    "text": text[:1400],
                    "published_at_kst": published,
                    "published_month": published_month,
                }
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")
    rows = sorted(posts.values(), key=lambda x: (x.get("published_at_kst") or "", x["data_post"]))
    return rows, errors


def probe_kstat() -> dict:
    result = {
        "ok": False,
        "update_month": "",
        "item_page_ok": False,
        "errors": [],
    }
    try:
        html = fetch(KSTAT_MAIN_URL)
        text = clean(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
        months = re.findall(r"(?:업데이트\s*[:：]?\s*|최신정보\s*)(20\d{2})[.년\-/ ]+(0?[1-9]|1[0-2])", text)
        if months:
            y, m = months[0]
            result["update_month"] = f"{int(y):04d}-{int(m):02d}"
        result["ok"] = True
    except Exception as e:
        result["errors"].append(f"K-stat 메인: {type(e).__name__}: {e}")

    try:
        html = fetch(KSTAT_ITEM_URL)
        text = clean(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
        result["item_page_ok"] = HSK in text or "복합구조칩 집적회로" in text
    except Exception as e:
        result["errors"].append(f"K-stat HSK 페이지: {type(e).__name__}: {e}")
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


def build_alert(now: datetime, report_month: str, posts: list[dict], kstat: dict) -> str:
    recent = [p for p in posts if p.get("published_month") == report_month]
    # 최신 공개 차트 묶음을 우선 표시한다.
    recent = recent[-12:]
    lines = [
        "📊 HBM 월간 수출 대용지표 업데이트",
        "",
        f"확인 시각: {now.isoformat(timespec='seconds')}",
        f"공개자료 게시월: {report_month}",
        f"추적 세번: HSK {HSK} 복합구조칩 집적회로",
        "주의: 이 세번에는 HBM 외 메모리도 포함될 수 있어 HBM 확정 매출이 아니라 출하 대용지표입니다.",
        "",
        "이번 달 새 공개 차트",
    ]
    for p in recent:
        text = p["text"]
        if len(text) > 360:
            text = text[:357].rstrip() + "..."
        lines += [f"• {text}", f"  원문: {p['url']}"]

    lines += [
        "",
        "공식 원천 확인",
        f"• K-stat 업데이트 표기: {kstat.get('update_month') or '자동 확인 불가'}",
        f"• HSK {HSK} 직접 페이지: {KSTAT_ITEM_URL}",
        f"• 지자체×품목: {KSTAT_REGION_ITEM_URL}",
        f"• 지자체×국가: {KSTAT_REGION_COUNTRY_URL}",
        f"• 품목×국가: {KSTAT_ITEM_COUNTRY_URL}",
        "",
        "체크포인트",
        "• 삼성전자: 충남/아산 관련 MCP 수출과 대만·말레이시아향 흐름",
        "• SK하이닉스: 충북/청주·경기/이천 관련 MCP 수출 흐름",
        "• 단일 월만으로 HBM 점유율 역전을 확정하지 않고 다음 달 지속성을 확인",
        "• Bernstein식 분기 매출 추정은 공개된 동일 회귀식·입력 숫자가 확인될 때만 별도 계산",
    ]
    if kstat.get("errors"):
        lines += ["", "⚠️ 공식 페이지 자동 확인 일부 실패", " | ".join(kstat["errors"][:3])]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    now_iso = now.isoformat(timespec="seconds")
    current_month = now.strftime("%Y-%m")
    state, first_run = load_state()

    posts, post_errors = extract_public_posts()
    kstat = probe_kstat()

    # 너무 오래된 게시물은 상태 크기를 줄이기 위해 120일 이내만 보존한다.
    cutoff = now - timedelta(days=120)
    kept_posts = []
    for p in posts:
        try:
            dt = datetime.fromisoformat(p.get("published_at_kst") or "")
            if dt >= cutoff:
                kept_posts.append(p)
        except Exception:
            kept_posts.append(p)

    last_sent_month = str(state.get("last_sent_month") or "")
    current_month_posts = [p for p in kept_posts if p.get("published_month") == current_month]

    should_alert = (
        (not first_run)
        and now.day >= 20
        and bool(current_month_posts)
        and current_month != last_sent_month
    )

    pending = {
        "updated_at_kst": now_iso,
        "last_sent_month": current_month if should_alert else (current_month if first_run else last_sent_month),
        "latest_kstat_update_month": kstat.get("update_month") or "",
        "recent_posts": kept_posts,
        "source_errors": post_errors + list(kstat.get("errors") or []),
    }
    write_json(OUT / "hbm_monthly_pending_state.json", pending)

    if first_run:
        (OUT / "hbm_monthly_rebaseline.txt").write_text(
            f"Initial baseline at {now_iso}; current month {current_month} marked as baseline; no Telegram alert sent.\n",
            encoding="utf-8",
        )

    if should_alert:
        alert = build_alert(now, current_month, kept_posts, kstat)
        (OUT / "hbm_monthly_alert.md").write_text(alert, encoding="utf-8")

    status = [
        "# HBM Monthly Export Proxy Watch",
        f"- checked_at_kst: {now_iso}",
        f"- hsk: {HSK}",
        f"- current_month: {current_month}",
        f"- first_run_baseline: {str(first_run).lower()}",
        f"- last_sent_month_before_run: {last_sent_month or 'none'}",
        f"- current_month_relevant_posts: {len(current_month_posts)}",
        f"- kstat_update_month: {kstat.get('update_month') or 'unknown'}",
        f"- should_alert: {str(should_alert).lower()}",
        f"- source_errors: {len(post_errors) + len(kstat.get('errors') or [])}",
    ]
    for e in (post_errors + list(kstat.get("errors") or []))[:8]:
        status.append(f"  - {e}")
    (OUT / "hbm_monthly_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
