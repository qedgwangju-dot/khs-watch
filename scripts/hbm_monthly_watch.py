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

# HSK 8542323000 = 복합구조칩 집적회로. HBM 전용 세번이 아니므로
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

# Bernstein 2026-08 자료의 삼성전자 회귀식.
# x = 충남→대만+말레이시아 복합구조칩 메모리 월 수출액(백만달러)
# y = 삼성전자 해당 분기 HBM 매출 추정치(백만달러)
BERNSTEIN_SLOPE = 5.5459
BERNSTEIN_INTERCEPT = -240.89
BERNSTEIN_MODEL_LABEL = "Bernstein 2026-08 회귀식"

# 원화 환산은 실행 시점의 최신 공개 일일 기준환율을 사용한다.
# Frankfurter v2는 중앙은행 환율 데이터를 모아 제공하며 API key가 필요 없다.
FX_URL = "https://api.frankfurter.dev/v2/rate/USD/KRW"
FX_SOURCE = "Frankfurter v2 중앙은행 기준환율 집계"

# 공개 웹에서 월별 MCP/HBM 수출 차트를 꾸준히 올리는 보조 모니터.
# 숫자의 공식 원천은 K-stat/관세청이며, 이 채널은 차트·수치 발견용 보조 출처다.
PUBLIC_CHANNEL = "https://t.me/s/Brain_And_Body_Research"
CHANNEL_QUERIES = [
    PUBLIC_CHANNEL,
    PUBLIC_CHANNEL + "?q=" + urllib.parse.quote("복합구조칩 집적회로"),
    PUBLIC_CHANNEL + "?q=" + urllib.parse.quote("HBM"),
    PUBLIC_CHANNEL + "?q=" + urllib.parse.quote("MCP"),
    PUBLIC_CHANNEL + "?q=" + urllib.parse.quote("충남 아산"),
    PUBLIC_CHANNEL + "?q=" + urllib.parse.quote("충북 청주 이천"),
]

PRIMARY = ("복합구조칩 집적회로", "mcp", "hbm")
SECONDARY = (
    "삼성전자", "sk하이닉스", "하이닉스", "전국", "충남", "아산",
    "충북", "청주", "이천", "대만", "말레이시아",
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
                    "text": text[:1800],
                    "published_at_kst": published,
                    "published_month": published_month,
                }
        except Exception as e:
            errors.append(f"{url}: {type(e).__name__}: {e}")
    return sorted(posts.values(), key=lambda x: (x.get("published_at_kst") or "", x["data_post"])), errors


def probe_kstat() -> dict:
    result = {"ok": False, "update_month": "", "item_page_ok": False, "errors": []}
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


def fetch_usdkrw():
    from fx_api import daily_krw
    try:
        q = daily_krw()
        return {"rate": q.rate, "date": q.basis, "source": q.source, "error": ""}
    except RuntimeError as exc:
        return {"rate": None, "date": "", "source": "환율 API", "error": str(exc)}


def load_state() -> tuple[dict, bool]:
    if not DATA.exists():
        return {}, True
    try:
        return json.loads(DATA.read_text(encoding="utf-8")), False
    except Exception:
        return {}, True


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def post_bucket(text: str) -> str:
    low = text.lower()
    if "삼성전자" in low or "충남" in low or "아산" in low:
        return "samsung"
    if "sk하이닉스" in low or "하이닉스" in low or "충북" in low or "청주" in low or "이천" in low:
        return "skhynix"
    if "전국" in low:
        return "overall"
    return "other"


def pct_hits(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    patterns = {
        "mom": [r"MoM\s*([+-]?\d+(?:\.\d+)?)%", r"전월\s*대비\s*([+-]?\d+(?:\.\d+)?)%"],
        "yoy": [r"YoY\s*([+-]?\d+(?:\.\d+)?)%", r"전년\s*(?:동월|동기)?\s*대비\s*([+-]?\d+(?:\.\d+)?)%"],
        "qoq_proxy": [r"(?:4월|3개월\s*전)\s*대비\s*([+-]?\d+(?:\.\d+)?)%", r"QoQ\s*([+-]?\d+(?:\.\d+)?)%"],
        "unit_mom": [r"(?:중량당|단위\s*중량당|수출단가|단위당)\s*(?:가치|단가)?[^%]{0,40}?전월\s*대비\s*([+-]?\d+(?:\.\d+)?)%"],
    }
    for key, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, text, re.I)
            if m:
                try:
                    out[key] = float(m.group(1))
                    break
                except Exception:
                    pass
    return out


def usd_million_hits(text: str) -> list[float]:
    values: list[float] = []
    patterns = [
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*[Bb](?:n|illion)?", 1000.0),
        (r"([0-9]+(?:\.[0-9]+)?)\s*(?:billion|십억)\s*(?:미국\s*)?달러", 1000.0),
        (r"([0-9]+(?:\.[0-9]+)?)\s*억\s*달러", 100.0),
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*[Mm](?:n|illion)?", 1.0),
    ]
    for pat, mult in patterns:
        for m in re.finditer(pat, text, re.I):
            try:
                values.append(float(m.group(1)) * mult)
            except Exception:
                pass
    return values


def summarize_bucket(posts: list[dict], bucket: str) -> dict:
    selected = [p for p in posts if post_bucket(p.get("text") or "") == bucket]
    joined = " ".join(p.get("text") or "" for p in selected)
    pcts = pct_hits(joined)
    return {
        "posts": selected,
        "mom": pcts.get("mom"),
        "yoy": pcts.get("yoy"),
        "qoq_proxy": pcts.get("qoq_proxy"),
        "unit_mom": pcts.get("unit_mom"),
        "usd_mn_candidates": usd_million_hits(joined),
    }


def fmt_pct(v: float | None) -> str:
    return "자동 추출 불가" if v is None else f"{v:+.2f}%"


def fmt_usd_mn(v: float | None) -> str:
    if v is None:
        return "자동 추출 불가"
    return f"${v/1000:.2f}B" if abs(v) >= 1000 else f"${v:.0f}M"


def fmt_krw_from_usd_mn(v_mn: float | None, rate: float | None) -> str:
    if v_mn is None or rate is None:
        return "원화 환산 불가"
    won = v_mn * 1_000_000 * rate
    eok_total = int(round(won / 100_000_000))
    if abs(eok_total) >= 10_000:
        sign = "-" if eok_total < 0 else ""
        eok_abs = abs(eok_total)
        jo, eok = divmod(eok_abs, 10_000)
        return f"약 {sign}{jo:,}조{eok:,}억원" if eok else f"약 {sign}{jo:,}조원"
    if abs(eok_total) >= 1:
        return f"약 {eok_total:,}억원"
    return f"약 {won:,.0f}원"


def fmt_usd_krw(v_mn: float | None, rate: float | None) -> str:
    if v_mn is None:
        return "자동 추출 불가"
    return f"{fmt_usd_mn(v_mn)} ({fmt_krw_from_usd_mn(v_mn, rate)})"


def choose_samsung_x(summary: dict) -> float | None:
    vals = [v for v in summary.get("usd_mn_candidates") or [] if v > 0]
    unique = sorted({round(v, 6) for v in vals})
    return unique[0] if len(unique) == 1 else None


def bernstein_estimate(x_mn: float | None) -> float | None:
    return None if x_mn is None else BERNSTEIN_SLOPE * x_mn + BERNSTEIN_INTERCEPT


def source_lines(posts: list[dict], limit: int = 8) -> list[str]:
    out: list[str] = []
    for p in posts[-limit:]:
        text = p.get("text") or ""
        if len(text) > 260:
            text = text[:257].rstrip() + "..."
        out += [f"• {text}", f"  원문: {p.get('url')}"]
    return out


def all_usd_values(posts: list[dict]) -> list[float]:
    vals: list[float] = []
    for p in posts:
        vals.extend(usd_million_hits(p.get("text") or ""))
    return sorted({round(v, 6) for v in vals if v > 0})


def build_alert(now: datetime, report_month: str, posts: list[dict], kstat: dict, fx: dict) -> str:
    recent = [p for p in posts if p.get("published_month") == report_month][-20:]
    overall = summarize_bucket(recent, "overall")
    samsung = summarize_bucket(recent, "samsung")
    skhynix = summarize_bucket(recent, "skhynix")
    rate = fx.get("rate")

    samsung_x = choose_samsung_x(samsung)
    samsung_y = bernstein_estimate(samsung_x)

    fx_line = (
        f"원화 환산 환율: 1달러 = {rate:,.2f}원 ({fx.get('source')}, 기준일 {fx.get('date') or '미표시'})"
        if rate is not None
        else f"원화 환산 환율: 조회 실패 — {fx.get('error') or '원인 미상'}"
    )

    lines = [
        "📊 HBM 월간 수출 대용지표 업데이트",
        "",
        f"확인 시각: {now.isoformat(timespec='seconds')}",
        f"공개자료 게시월: {report_month}",
        f"추적 세번: HSK {HSK} 복합구조칩 집적회로",
        fx_line,
        "주의: HSK 8542323000은 HBM 전용 통계가 아니며 MCP·기타 복합 메모리가 포함될 수 있습니다. 아래 숫자는 HBM 확정 매출이 아니라 출하 대용지표입니다.",
        "",
        "1) 전국 HBM 대용지표",
        f"• 전월 대비: {fmt_pct(overall.get('mom'))}",
        f"• 3개월 전/분기 대응월 대비: {fmt_pct(overall.get('qoq_proxy'))}",
        f"• 전년 동월 대비: {fmt_pct(overall.get('yoy'))}",
        "• 해석: 삼성 개별 지표가 강해도 전국 지표가 약하면 '삼성 점유율 이동'과 '전체 HBM 수요 증가'를 구분합니다.",
        "",
        "2) 삼성전자 HBM 대용지표 — 충남/아산 중심",
        f"• 수출액 후보: {fmt_usd_krw(samsung_x, rate)}",
        f"• 전월 대비: {fmt_pct(samsung.get('mom'))}",
        f"• 3개월 전/분기 대응월 대비: {fmt_pct(samsung.get('qoq_proxy'))}",
        f"• 전년 동월 대비: {fmt_pct(samsung.get('yoy'))}",
        f"• 중량당 가치/수출단가 전월 대비: {fmt_pct(samsung.get('unit_mom'))}",
        "",
        "3) Bernstein 회귀식 검산 — 삼성전자",
        f"• 식: y = {BERNSTEIN_SLOPE}x {BERNSTEIN_INTERCEPT:+.2f}",
        "• x 정의: 충남→대만+말레이시아 복합구조칩 메모리 월 수출액(백만달러)",
    ]

    if samsung_x is not None and samsung_y is not None:
        lines += [
            f"• 입력 x = {samsung_x:,.0f}M달러 = {fmt_krw_from_usd_mn(samsung_x, rate)}",
            f"• 계산 y = {samsung_y:,.0f}M달러 ≈ ${samsung_y/1000:.2f}B = {fmt_krw_from_usd_mn(samsung_y, rate)}",
            "• 성격: 회사 가이던스가 아니라 Bernstein 역사적 상관관계 기반 보조 추정치",
        ]
    else:
        lines += [
            "• 입력 x: 자동 확정 불가 — 충남→대만+말레이시아 합산 수출액을 텍스트에서 단일 값으로 식별하지 못해 회귀값을 임의 계산하지 않음",
            "• 성격: 정확한 x가 확인되는 달에만 회귀값 계산",
        ]

    lines += [
        "",
        "4) SK하이닉스 HBM 대용지표 — 충북/청주 + 경기/이천",
        f"• 전월 대비: {fmt_pct(skhynix.get('mom'))}",
        f"• 3개월 전/분기 대응월 대비: {fmt_pct(skhynix.get('qoq_proxy'))}",
        f"• 전년 동월 대비: {fmt_pct(skhynix.get('yoy'))}",
        f"• 중량당 가치/수출단가 전월 대비: {fmt_pct(skhynix.get('unit_mom'))}",
        "• Rubin향 선적 지연 등 원인은 기사·회사자료로 별도 확인되기 전까지 '가능성'으로만 표시",
        "",
        "5) 비교 판정",
        "• 삼성 수출 증가만으로 HBM 전체 수요 증가를 단정하지 않음",
        "• 전국 대용지표, 삼성, SK하이닉스를 반드시 같은 달 기준으로 나란히 비교",
        "• 단일 월 점유율 역전은 확정하지 않고 최소 다음 달 지속성까지 확인",
        "• 중량당 가치 상승은 같은 규격 가격 상승과 제품 혼합(HBM4 비중 상승)을 구분",
        "",
        "6) 달러 금액 원화 환산표",
    ]

    values = all_usd_values(recent)
    if samsung_y is not None:
        values = sorted(set(values + [round(samsung_y, 6)]))
    if values:
        for v in values[:15]:
            lines.append(f"• {fmt_usd_mn(v)} = {fmt_krw_from_usd_mn(v, rate)}")
    else:
        lines.append("• 이번 달 공개 텍스트에서 자동 추출된 달러 금액 없음")

    lines += [
        "",
        "7) 공식 원천·보조 원천",
        f"• K-stat 업데이트 표기: {kstat.get('update_month') or '자동 확인 불가'}",
        f"• K-stat HSK 직접 페이지: {KSTAT_ITEM_URL}",
        f"• 지자체×품목: {KSTAT_REGION_ITEM_URL}",
        f"• 지자체×국가: {KSTAT_REGION_COUNTRY_URL}",
        f"• 품목×국가: {KSTAT_ITEM_COUNTRY_URL}",
        f"• 원화 환산: {fx.get('source')} / 기준일 {fx.get('date') or '자동 확인 불가'}",
        "• Brain and Body Research 공개 차트는 숫자 발견·교차확인용 보조 출처로만 사용",
        "",
        "8) 이번 달 원문 근거",
    ]
    lines += source_lines(recent, limit=10) or ["• 관련 공개 텍스트 없음"]

    errors = list(kstat.get("errors") or [])
    if fx.get("error"):
        errors.append(fx["error"])
    if errors:
        lines += ["", "⚠️ 자동 확인 일부 실패", " | ".join(errors[:4])]

    lines += [
        "",
        "핵심: 회귀식 숫자와 전국 지표를 반드시 같이 보고, 달러 금액은 같은 보고서 안에서 기준 환율·기준일을 명시해 원화로 함께 환산합니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    now_iso = now.isoformat(timespec="seconds")
    current_month = now.strftime("%Y-%m")
    state, first_run = load_state()

    posts, post_errors = extract_public_posts()
    kstat = probe_kstat()
    fx = fetch_usdkrw()

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

    source_errors = post_errors + list(kstat.get("errors") or [])
    if fx.get("error"):
        source_errors.append(fx["error"])

    pending = {
        "updated_at_kst": now_iso,
        "last_sent_month": current_month if should_alert else (current_month if first_run else last_sent_month),
        "latest_kstat_update_month": kstat.get("update_month") or "",
        "recent_posts": kept_posts,
        "usdkrw": fx,
        "bernstein_model": {
            "label": BERNSTEIN_MODEL_LABEL,
            "slope": BERNSTEIN_SLOPE,
            "intercept": BERNSTEIN_INTERCEPT,
            "x_definition": "충남→대만+말레이시아 복합구조칩 메모리 월 수출액(백만달러)",
            "y_definition": "삼성전자 해당 분기 HBM 매출 보조 추정치(백만달러)",
        },
        "source_errors": source_errors,
    }
    write_json(OUT / "hbm_monthly_pending_state.json", pending)

    if first_run:
        (OUT / "hbm_monthly_rebaseline.txt").write_text(
            f"Initial baseline at {now_iso}; current month {current_month} marked as baseline; no Telegram alert sent.\n",
            encoding="utf-8",
        )

    if should_alert:
        (OUT / "hbm_monthly_alert.md").write_text(
            build_alert(now, current_month, kept_posts, kstat, fx), encoding="utf-8"
        )

    rate = fx.get("rate")
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
        f"- bernstein_formula: y={BERNSTEIN_SLOPE}x{BERNSTEIN_INTERCEPT:+.2f}",
        f"- usdkrw: {rate if rate is not None else 'unavailable'}",
        f"- usdkrw_date: {fx.get('date') or 'unknown'}",
        f"- source_errors: {len(source_errors)}",
    ]
    for e in source_errors[:8]:
        status.append(f"  - {e}")
    (OUT / "hbm_monthly_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
