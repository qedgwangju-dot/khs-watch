#!/usr/bin/env python3
import datetime as dt
import html
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

import treasury_credit_flow_watch_ishares as app


_original_send = app.send_exact


def _match(pattern, text, default="확인 대기"):
    m = re.search(pattern, text, re.M)
    return m.group(1).strip() if m else default


def _direction_pair(label, text):
    m = re.search(rf"^{re.escape(label)}: ([^\n]+)\n→ ([^\n]+)", text, re.M)
    if not m:
        return "확인 대기", "세부 자료 확인 대기"
    return m.group(1).strip(), m.group(2).strip()


def _etf_flow(ticker, text):
    m = re.search(
        rf"^{ticker} \([^\n]+\) — [^\n]+\n"
        rf"• 가격: [^\n]+\n"
        rf"• 일간 자금: ([^\n]+)",
        text,
        re.M,
    )
    return m.group(1).strip() if m else "확인 대기"


def _etf_date(ticker, text):
    m = re.search(rf"^{ticker} \([^\n]+\) — ([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}})", text, re.M)
    return m.group(1) if m else "확인 대기"


def _etf_oas(ticker, text):
    m = re.search(
        rf"^{ticker} \([^\n]+\) — [^\n]+\n"
        rf"• 가격: [^\n]+\n"
        rf"• 일간 자금: [^\n]+\n"
        rf"• 최근 5회: [^\n]+\n"
        rf"• 포트폴리오 OAS: ([^\n]+)",
        text,
        re.M,
    )
    return m.group(1).strip() if m else "확인 대기"


def _rate_line(label, text):
    return _match(rf"^• {re.escape(label)}: ([^\n]+)", text)


def _plain_driver(text):
    return _match(r"^• 오늘의 주도축: ([^\n]+)", text)


def _parse_date_en(value):
    try:
        return dt.datetime.strptime(value, "%b %d, %Y").date().isoformat()
    except Exception:
        return value


def get_hyg_ytm():
    url = "https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf"
    r = requests.get(url, headers=app.base.HEADERS, timeout=(8, 20))
    r.raise_for_status()
    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    m = re.search(r"Average Yield to Maturity\s+([0-9,.]+)%?(?:\s+as of\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4}))?", text, re.I)
    if not m:
        raise RuntimeError("HYG Average Yield to Maturity not found")
    return float(m.group(1).replace(",", "")), _parse_date_en(m.group(2)) if m.group(2) else "최신"


def get_bea_growth_snapshot():
    landing_url = "https://www.bea.gov/data/gdp/gross-domestic-product"
    r = requests.get(landing_url, headers=app.base.HEADERS, timeout=(8, 20))
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    release_url = None
    for a in soup.find_all("a", href=True):
        label = " ".join(a.stripped_strings)
        href = a.get("href") or ""
        if "/news/" in href and label.startswith("GDP ("):
            release_url = urljoin(landing_url, href)
            break
    if not release_url:
        raise RuntimeError("BEA current GDP release link not found")

    rr = requests.get(release_url, headers=app.base.HEADERS, timeout=(8, 20))
    rr.raise_for_status()
    rsoup = BeautifulSoup(rr.text, "html.parser")
    nominal = None
    for tr in rsoup.find_all("tr"):
        cells = [" ".join(x.stripped_strings) for x in tr.find_all(["th", "td"])]
        if cells and "Current-dollar GDP" in cells[0]:
            nums = []
            for c in cells[1:]:
                mm = re.search(r"-?[0-9]+(?:\.[0-9]+)?", c.replace(",", ""))
                if mm:
                    nums.append(float(mm.group(0)))
            if nums:
                nominal = nums[-1]
                break
    if nominal is None:
        flat = re.sub(r"\s+", " ", rsoup.get_text(" ", strip=True))
        m = re.search(r"Current-dollar GDP\s+.*?([0-9]+\.[0-9]+)\s+Real final sales", flat, re.I)
        if m:
            nominal = float(m.group(1))
    if nominal is None:
        raise RuntimeError("BEA current-dollar GDP growth not found")

    title = " ".join((rsoup.find("h1") or rsoup).stripped_strings)
    pm = re.search(r"([1-4](?:st|nd|rd|th) Quarter)\s+(20\d{2})", title, re.I)
    if pm:
        qnum = {"1st": "Q1", "2nd": "Q2", "3rd": "Q3", "4th": "Q4"}[pm.group(1).split()[0].lower()]
        period = f"{pm.group(2)} {qnum}"
    else:
        period = "최신 분기"

    profits_url = "https://www.bea.gov/data/income-saving/corporate-profits"
    pr = requests.get(profits_url, headers=app.base.HEADERS, timeout=(8, 20))
    pr.raise_for_status()
    psoup = BeautifulSoup(pr.text, "html.parser")
    prows = []
    for tr in psoup.find_all("tr"):
        cells = [" ".join(x.stripped_strings) for x in tr.find_all(["th", "td"])]
        if len(cells) >= 2 and re.fullmatch(r"Q[1-4]\s+20\d{2}", cells[0]):
            mm = re.search(r"([0-9,.]+)\s*B", cells[1].replace("$", ""), re.I)
            if mm:
                prows.append((cells[0], float(mm.group(1).replace(",", ""))))
    if len(prows) < 2:
        flatp = re.sub(r"\s+", " ", psoup.get_text(" ", strip=True))
        prows = [(f"Q{q} {y}", float(v.replace(",", ""))) for q, y, v in re.findall(r"Q([1-4])\s+(20\d{2})\s+\$?([0-9,.]+)\s*B", flatp)]
    profit = None
    if len(prows) >= 2 and prows[1][1] != 0:
        profit = {
            "period": prows[0][0],
            "value_b": prows[0][1],
            "prev_period": prows[1][0],
            "prev_value_b": prows[1][1],
            "qoq_pct": (prows[0][1] / prows[1][1] - 1.0) * 100.0,
        }
    return {"nominal_gdp_saar": nominal, "period": period, "release_url": release_url, "profit": profit}


def get_growth_cost_snapshot():
    try:
        bea = get_bea_growth_snapshot()
        hyg_ytm, hyg_date = get_hyg_ytm()
        gap = bea["nominal_gdp_saar"] - hyg_ytm
        if gap >= 1.0:
            state = "G>R 성장 우위"
            meaning = "명목성장이 고수익채 시장 차입비용 프록시보다 1%p 이상 높아 고금리 충격을 흡수할 완충이 있음"
        elif gap >= 0:
            state = "G>R 유지·완충 얇음"
            meaning = "명목성장이 아직 차입비용 프록시를 웃돌지만 격차가 1%p 미만이라 둔화 시 쉽게 뒤집힐 수 있음"
        elif gap > -1.0:
            state = "R>G 초기 경계"
            meaning = "고수익채 시장 차입비용 프록시가 명목성장을 웃돌기 시작해 차환·이익 압박 점검 필요"
        else:
            state = "R>G 경고"
            meaning = "차입비용 프록시가 명목성장을 1%p 이상 웃돌아 고금리가 실제 기업 부담으로 전이될 위험이 커짐"
        return {
            "ok": True,
            "g": bea["nominal_gdp_saar"],
            "g_period": bea["period"],
            "r": hyg_ytm,
            "r_date": hyg_date,
            "gap": gap,
            "state": state,
            "meaning": meaning,
            "profit": bea.get("profit"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _transition_risk(gr, hyg_flow, hyg_oas):
    hyg_out = "순유출" in hyg_flow
    oas_up = "직전 대비 ↑" in hyg_oas or "직전 대비 +" in hyg_oas
    if gr.get("ok") and gr["gap"] < 0 and hyg_out and oas_up:
        return "적색 경보", "R>G + HYG 자금유출 + OAS 확대가 겹침 → 성장 완충 약화와 실제 신용위험 악화가 동시에 확인"
    if hyg_out and oas_up:
        return "주의", "HYG 자금유출 + OAS 확대 → 성장수치가 버텨도 시장은 신용위험을 먼저 가격에 반영"
    if gr.get("ok") and gr["gap"] >= 0 and not oas_up:
        return "완충 유지", "G>R이고 HYG OAS 급확대가 없어 높은 금리가 아직 신용경색으로 번진 신호는 약함"
    return "중립·추가 확인", "G-R, HYG 자금흐름, OAS가 한 방향으로 정렬되는지 추가 확인"


def improve_overview(text):
    overall, overall_reason = _direction_pair("전체 자금 방향", text)
    treasury, treasury_reason = _direction_pair("ETF 자금 방향", text)
    credit, credit_reason = _direction_pair("신용자금 방향", text)
    regime, regime_easy = _direction_pair("금리 구조", text)

    shy = _etf_flow("SHY", text)
    ief = _etf_flow("IEF", text)
    tlt = _etf_flow("TLT", text)
    lqd = _etf_flow("LQD", text)
    hyg = _etf_flow("HYG", text)
    lqd_oas = _etf_oas("LQD", text)
    hyg_oas = _etf_oas("HYG", text)

    r2 = _rate_line("2년", text)
    r10 = _rate_line("10년", text)
    r30 = _rate_line("30년", text)
    s210 = _rate_line("2년-10년 금리차", text)
    s1030 = _rate_line("10년-30년 금리차", text)
    back = _match(r"^• 뒷단 해석: ([^\n]+)", text)
    driver = _plain_driver(text)
    treasury_date = _match(r"^기준: ([0-9]{4}-[0-9]{2}-[0-9]{2}) \| 직전:", text)
    dates = {x: _etf_date(x, text) for x in ("SHY", "IEF", "TLT", "LQD", "HYG")}

    gr = get_growth_cost_snapshot()
    risk_head, risk_reason = _transition_risk(gr, hyg, hyg_oas)

    overview = [
        "[한눈에 보기]",
        f"전체 방향: {overall}",
        f"→ {overall_reason}",
        "",
        f"국채 자금: SHY {shy} | IEF {ief} | TLT {tlt}",
        f"→ {treasury}: {treasury_reason}",
        "",
        f"회사채 자금: LQD {lqd} | HYG {hyg}",
        f"→ {credit}: {credit_reason}",
        "",
        f"신용 위험: LQD OAS {lqd_oas} | HYG OAS {hyg_oas}",
        "→ 자금유출과 OAS 확대가 함께 나오면 실제 신용위험 악화, OAS가 안정적이면 선제적 위험축소로 판독",
        "",
    ]

    if gr.get("ok"):
        overview += [
            f"성장-차입비용: {gr['state']} | G 명목GDP {gr['g']:.2f}% ({gr['g_period']}, 연율) vs R HYG 만기수익률 {gr['r']:.2f}% (기준 {gr['r_date']}) | G-R {gr['gap']:+.2f}%p",
            f"→ {gr['meaning']}",
        ]
        profit = gr.get("profit")
        if profit:
            overview += [
                f"기업이익: {profit['period']} ${profit['value_b']:,.1f}B vs {profit['prev_period']} ${profit['prev_value_b']:,.1f}B | 전분기 대비 {profit['qoq_pct']:+.1f}%",
                "→ 기업이익은 G-R 산식에 직접 섞지 않고, 고금리를 버티는 이익 완충이 살아있는지 별도 확인",
            ]
    else:
        overview += [
            "성장-차입비용: 공식 최신값 자동조회 실패 → G-R 판정 보류",
            "→ 기존 ETF·OAS·수익률곡선 판정은 계속 수행하고 G-R은 추정하지 않음",
        ]

    overview += [
        f"위험 전환 경보: {risk_head}",
        f"→ {risk_reason}",
        "",
        f"금리: 2년 {r2} | 10년 {r10} | 30년 {r30}",
        f"커브: {regime} = {regime_easy}",
        f"2년-10년: {s210}",
        f"10년-30년: {s1030}",
        f"→ {back}",
        f"오늘의 주도축: {driver}",
        "",
        f"자료 기준일: SHY {dates['SHY']} | IEF {dates['IEF']} | TLT {dates['TLT']} | LQD {dates['LQD']} | HYG {dates['HYG']} | 미 재무부 {treasury_date}",
        "→ 시장자료는 각 공식 출처의 최신 영업일 값을 사용하며, 날짜가 엇갈리면 같은 날 자료처럼 합쳐 해석하지 않음",
    ]

    new_block = "\n".join(overview)
    pattern = r"\[한눈에 보기\]\n.*?\n\[미 국채 ETF\]"
    if not re.search(pattern, text, re.S):
        return text
    return re.sub(pattern, new_block + "\n\n[미 국채 ETF]", text, count=1, flags=re.S)


def fmt_html(chunk):
    out = []
    bold_prefixes = (
        "전체 방향:",
        "국채 자금:",
        "회사채 자금:",
        "신용 위험:",
        "성장-차입비용:",
        "기업이익:",
        "위험 전환 경보:",
        "금리:",
        "커브:",
        "2년-10년:",
        "10년-30년:",
        "오늘의 주도축:",
        "자료 기준일:",
        "전체 자금 방향:",
        "ETF 자금 방향:",
        "신용자금 방향:",
        "• 현재 형태:",
        "• 오늘의 주도축:",
        "• 신용 위험:",
    )
    for line in chunk.splitlines():
        escaped = html.escape(line, quote=False)
        bold = line in ("[한눈에 보기]", "[오늘의 결론]") or line.startswith(bold_prefixes)
        out.append(f"<b>{escaped}</b>" if bold else escaped)
    return "\n".join(out)


def send_readable(text):
    readable = improve_overview(text)
    (app.base.OUT / "treasury_etf_flow_telegram.txt").write_text(readable + "\n", encoding="utf-8")
    (app.base.OUT / "treasury_etf_flow_status.md").write_text("```\n" + readable + "\n```\n", encoding="utf-8")
    return _original_send(readable)


app.fmt_html = fmt_html
app.send_exact = send_readable


if __name__ == "__main__":
    app.main()
