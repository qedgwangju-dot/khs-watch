from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data/qlex_wac_ir_watch_state.json"
OUT = ROOT / "out"
PENDING = OUT / "qlex_wac_ir_watch_state_pending.json"
ALERT = OUT / "qlex_wac_ir_alert.md"
STATUS = OUT / "qlex_wac_ir_status.md"
UA = "Mozilla/5.0 (compatible; AlteogenQlexWACWatch/1.0)"
CHANNEL_URL = "https://t.me/s/alteogenIR"
MAX_FRESH_DAYS = 7


@dataclass
class Post:
    post_id: int
    url: str
    published: str
    text: str


@dataclass
class Metrics:
    month: int | None = None
    wac_m: float | None = None
    krw_eok: float | None = None
    mom_pct: float | None = None
    share_pct: float | None = None
    prev_share_pct: float | None = None
    share_delta_pp: float | None = None
    cumulative_m: float | None = None
    cumulative_month: int | None = None


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.6,en;q=0.5",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(2_000_000)
        enc = response.headers.get_content_charset() or "utf-8"
    return raw.decode(enc, errors="replace")


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", value)
    value = re.sub(r"(?is)<br\s*/?>", "\n", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s+", "\n", value)
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def parse_posts(page: str) -> list[Post]:
    markers = list(re.finditer(r'data-post=["\']alteogenIR/(\d+)["\']', page, re.I))
    posts: list[Post] = []
    for idx, marker in enumerate(markers):
        post_id = int(marker.group(1))
        end = markers[idx + 1].start() if idx + 1 < len(markers) else min(len(page), marker.start() + 120_000)
        block = page[marker.start():end]

        time_match = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', block, re.I)
        published = time_match.group(1).strip() if time_match else ""

        text = ""
        msg_marker = re.search(r'tgme_widget_message_text[^>]*>', block, re.I)
        if msg_marker:
            frag_start = msg_marker.end()
            footer = re.search(r'<div[^>]+class=["\'][^"\']*tgme_widget_message_footer', block[frag_start:], re.I)
            frag_end = frag_start + footer.start() if footer else min(len(block), frag_start + 30_000)
            text = strip_html(block[frag_start:frag_end])
        if not text:
            text = strip_html(block)

        if text:
            posts.append(Post(post_id=post_id, url=f"https://t.me/alteogenIR/{post_id}", published=published, text=text))
    return posts


def parse_iso(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return stamp.astimezone(KST)
    except Exception:
        return None


def number(value: str) -> float:
    return float(value.replace(",", ""))


def parse_metrics(text: str) -> Metrics | None:
    low = text.lower()
    if not ("keytruda qlex" in low or "키트루다 큐렉스" in low or "qlex" in low):
        return None
    if "wac" not in low:
        return None

    m = Metrics()
    month_match = re.search(r"(?:지난\s*달\s*\()?\s*(\d{1,2})\s*월\)?[^\n]{0,80}?WAC", text, re.I)
    if not month_match:
        month_match = re.search(r"(\d{1,2})\s*월\s*WAC", text, re.I)
    if month_match:
        m.month = int(month_match.group(1))

    wac_match = re.search(r"WAC\s*[:：]?\s*\$\s*([0-9,.]+)\s*(?:M|MN|MILLION)\b", text, re.I)
    if not wac_match:
        wac_match = re.search(r"\$\s*([0-9,.]+)\s*(?:M|MN|MILLION)\b[^\n]{0,50}?WAC", text, re.I)
    if wac_match:
        m.wac_m = number(wac_match.group(1))
        after = text[wac_match.end():wac_match.end() + 160]
        krw_match = re.search(r"약\s*([0-9,.]+)\s*억\s*원", after)
        if krw_match:
            m.krw_eok = number(krw_match.group(1))

    mom_match = re.search(r"직전\s*월\s*대비\s*(?:약\s*)?([0-9.]+)\s*%\s*증가", text)
    if mom_match:
        m.mom_pct = float(mom_match.group(1))

    share_patterns = (
        r"(?:키트루다\s*)?프랜차이즈[^\n]{0,100}?(?:점유율|비중)\s*(?:약\s*)?[:：]?\s*([0-9.]+)\s*%",
        r"(?:SC|피하주사)\s*(?:비중|점유율)\s*[:：]?\s*([0-9.]+)\s*%",
        r"점유율\s*(?:약\s*)?[:：]?\s*([0-9.]+)\s*%",
    )
    for pattern in share_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            m.share_pct = float(match.group(1))
            break

    prev_share_match = re.search(r"직전\s*월\s*(?:약\s*)?([0-9.]+)\s*%", text)
    if prev_share_match:
        m.prev_share_pct = float(prev_share_match.group(1))

    delta_match = re.search(r"([0-9.]+)\s*%\s*[pP]\s*증가", text)
    if delta_match:
        m.share_delta_pp = float(delta_match.group(1))
    elif m.share_pct is not None and m.prev_share_pct is not None:
        m.share_delta_pp = round(m.share_pct - m.prev_share_pct, 2)

    cumulative = re.search(r"1\s*[~\-–]\s*(\d{1,2})\s*월[^\n$]{0,120}?\$\s*([0-9,.]+)\s*(M|MN|MILLION|B|BN|BILLION)\b", text, re.I)
    if cumulative:
        m.cumulative_month = int(cumulative.group(1))
        value = number(cumulative.group(2))
        unit = cumulative.group(3).lower()
        m.cumulative_m = value * 1000.0 if unit in {"b", "bn", "billion"} else value

    if m.wac_m is None and m.share_pct is None:
        return None
    return m


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"initialized": False, "last_post_id": 0, "last_month": None, "last_wac_m": None, "last_share_pct": None, "last_cumulative_m": None}


def fmt_usd_m(value: float) -> str:
    if value >= 1000:
        return f"{value/1000:.3f}B달러"
    return f"{value:,.1f}M달러"


def build_alert(post: Post, metrics: Metrics, state: dict) -> str:
    month = metrics.month or metrics.cumulative_month
    title_month = f"{month}월" if month else "월간"
    title_bits: list[str] = []
    if metrics.wac_m is not None:
        title_bits.append(f"WAC {fmt_usd_m(metrics.wac_m)}")
    if metrics.share_pct is not None:
        title_bits.append(f"피하주사(SC) 비중 {metrics.share_pct:.1f}%")
    title = " · ".join(title_bits) or "월간 처방지표 업데이트"

    lines = ["[바이오 감시] KEYTRUDA QLEX 월간 WAC·피하주사 비중", "", f"**{title_month} {title}**", ""]

    if metrics.wac_m is not None:
        detail = f"- **월간 처방액:** {fmt_usd_m(metrics.wac_m)}"
        if metrics.krw_eok is not None:
            detail += f" · 알테오젠 IR 원문 약 {metrics.krw_eok:,.0f}억원"
        if metrics.mom_pct is not None:
            detail += f" · 전월 대비 +{metrics.mom_pct:.1f}%"
        elif state.get("last_wac_m"):
            old = float(state["last_wac_m"])
            if old > 0:
                detail += f" · 직전 감시값 대비 {(metrics.wac_m / old - 1) * 100:+.1f}%"
        lines.append(detail)

    if metrics.share_pct is not None:
        detail = f"- **피하주사 비중:** {metrics.share_pct:.1f}%"
        prev = metrics.prev_share_pct
        if prev is None and state.get("last_share_pct") is not None:
            prev = float(state["last_share_pct"])
        if prev is not None:
            delta = metrics.share_delta_pp
            if delta is None:
                delta = metrics.share_pct - prev
            detail += f" · 직전월 {prev:.1f}% 대비 {delta:+.1f}%p"
        lines.append(detail)

    if metrics.cumulative_m is not None:
        cum_month = metrics.cumulative_month or month
        lines.append(f"- **누적 추정:** 1~{cum_month}월 약 {fmt_usd_m(metrics.cumulative_m)}")

    lines += [
        "",
        "- **해석:** WAC은 도매구입가격 기준 처방액 지표로 Merck의 실제 순매출과 다릅니다. 누적값도 Merck 공식매출과 월별 WAC을 결합한 추정치로 봐야 합니다.",
        "- **알테오젠:** QLEX 확산 속도가 빨라질수록 판매 마일스톤·후속 로열티·ALT-B4 공급의 기반이 커지는 방향입니다.",
        "- **다음 확인:** 다음 달 WAC·피하주사 비중 → Merck 분기 QLEX 공식 매출과 실제 차이 검산",
        "- **원문 확인:** 알테오젠 공식 IR 텔레그램 게시물 직접 추적",
        f"- 원문: {post.url}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (ALERT, STATUS, PENDING):
        path.unlink(missing_ok=True)

    state = load_state()
    now = dt.datetime.now(KST)
    try:
        page = fetch(CHANNEL_URL)
        posts = parse_posts(page)
    except Exception as exc:
        STATUS.write_text(f"status=error fetch={type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise

    candidates: list[tuple[Post, Metrics]] = []
    for post in posts:
        metrics = parse_metrics(post.text)
        if metrics is not None:
            candidates.append((post, metrics))

    candidates.sort(key=lambda row: row[0].post_id)
    latest = candidates[-1] if candidates else None

    pending = dict(state)
    pending["last_check_kst"] = now.isoformat(timespec="seconds")
    pending["channel_posts_seen"] = len(posts)
    pending["wac_posts_seen"] = len(candidates)

    changed = False
    if latest:
        post, metrics = latest
        stamp = parse_iso(post.published)
        fresh = True if stamp is None else (now - stamp <= dt.timedelta(days=MAX_FRESH_DAYS))
        same_post = int(state.get("last_post_id") or 0) >= post.post_id
        same_metrics = metrics.month == state.get("last_month") and metrics.wac_m == state.get("last_wac_m") and metrics.share_pct == state.get("last_share_pct")

        if fresh and not same_post and not same_metrics:
            ALERT.write_text(build_alert(post, metrics, state), encoding="utf-8")
            changed = True

        pending["initialized"] = True
        pending["last_post_id"] = post.post_id
        pending["last_post_url"] = post.url
        pending["last_post_published"] = post.published
        pending["last_month"] = metrics.month
        pending["last_wac_m"] = metrics.wac_m
        pending["last_share_pct"] = metrics.share_pct
        pending["last_prev_share_pct"] = metrics.prev_share_pct
        pending["last_share_delta_pp"] = metrics.share_delta_pp
        pending["last_cumulative_m"] = metrics.cumulative_m
        pending["last_cumulative_month"] = metrics.cumulative_month
    else:
        pending.setdefault("initialized", True)

    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(f"status=ok changed={'true' if changed else 'false'} posts={len(posts)} wac_posts={len(candidates)} latest_post={pending.get('last_post_id', 0)} at={pending['last_check_kst']}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
