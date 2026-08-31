#!/usr/bin/env python3
import datetime as dt
import html
import io
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

BASE = "https://opendart.fss.or.kr/api"
API_KEY = os.environ.get("OPENDART_API_KEY", "").strip()


def fail(message: str, code: int = 1):
    print(f"OpenDART 오류: {message}")
    raise SystemExit(code)


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "khs-watch-opendart-bridge/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def api_url(endpoint: str, params: dict) -> str:
    q = {"crtfc_key": API_KEY}
    q.update({k: v for k, v in params.items() if v not in (None, "")})
    return f"{BASE}/{endpoint}?{urllib.parse.urlencode(q)}"


def api_json(endpoint: str, params: dict) -> dict:
    raw = fetch(api_url(endpoint, params))
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as e:
        fail(f"{endpoint} 응답 JSON 해석 실패: {e}")


def load_corp_codes():
    raw = fetch(api_url("corpCode.xml", {}), timeout=90)
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        xml_name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
        root = ET.fromstring(zf.read(xml_name))
    except Exception as e:
        fail(f"고유번호 파일 해석 실패: {e}")
    rows = []
    for node in root.findall("list"):
        rows.append({
            "corp_code": (node.findtext("corp_code") or "").strip(),
            "corp_name": (node.findtext("corp_name") or "").strip(),
            "stock_code": (node.findtext("stock_code") or "").strip(),
            "modify_date": (node.findtext("modify_date") or "").strip(),
        })
    return rows


def resolve_company(query: str):
    q = (query or "").strip()
    if not q:
        fail("회사명·종목코드·고유번호가 필요합니다.")
    if q.isdigit() and len(q) == 8:
        return {"corp_code": q, "corp_name": q, "stock_code": "", "modify_date": ""}
    rows = load_corp_codes()
    if q.isdigit() and len(q) == 6:
        hit = [r for r in rows if r["stock_code"] == q]
    else:
        hit = [r for r in rows if r["corp_name"] == q]
        if not hit:
            hit = [r for r in rows if q.casefold() in r["corp_name"].casefold()]
    if not hit:
        fail(f"회사 식별 실패: {q}")
    if len(hit) > 1:
        listed = [r for r in hit if r["stock_code"]]
        if len(listed) == 1:
            return listed[0]
        sample = ", ".join(f'{r["corp_name"]}({r["stock_code"] or r["corp_code"]})' for r in hit[:10])
        fail(f"회사명이 여러 곳과 일치합니다: {sample}")
    return hit[0]


def strip_markup(text: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>|</li>|</table>|</h\d>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def corp_from_payload(payload: dict, title_query: str):
    direct = str(payload.get("corp_code") or "").strip()
    if direct:
        if not (direct.isdigit() and len(direct) == 8):
            fail("corp_code는 8자리 숫자여야 합니다.")
        return {
            "corp_code": direct,
            "corp_name": str(payload.get("company") or title_query or direct),
            "stock_code": str(payload.get("stock_code") or ""),
            "modify_date": "",
        }
    company = payload.get("company") or payload.get("query") or title_query
    return resolve_company(company)


def do_list(payload: dict, title_query: str):
    corp = corp_from_payload(payload, title_query)
    today = dt.date.today()
    bgn = payload.get("bgn_de") or (today - dt.timedelta(days=int(payload.get("days", 30)))).strftime("%Y%m%d")
    end = payload.get("end_de") or today.strftime("%Y%m%d")
    params = {
        "corp_code": corp["corp_code"],
        "bgn_de": bgn,
        "end_de": end,
        "page_no": payload.get("page_no", 1),
        "page_count": min(int(payload.get("page_count", 100)), 100),
        "last_reprt_at": payload.get("last_reprt_at"),
        "pblntf_ty": payload.get("pblntf_ty"),
        "pblntf_detail_ty": payload.get("pblntf_detail_ty"),
        "sort": payload.get("sort", "date"),
        "sort_mth": payload.get("sort_mth", "desc"),
    }
    data = api_json("list.json", params)
    print("# OpenDART 실시간 공시 조회")
    print()
    print(f'- 회사: {corp["corp_name"]} ({corp["stock_code"] or "종목코드 미지정"})')
    print(f'- 고유번호: {corp["corp_code"]}')
    print(f'- 조회기간: {bgn} ~ {end}')
    print(f'- OpenDART 상태: {data.get("status")} / {data.get("message")}')
    if data.get("status") == "013":
        print("- 조회 결과: 해당 기간 공시 없음")
        return
    if data.get("status") != "000":
        fail(f'{data.get("status")} {data.get("message")}')
    print(f'- 전체 건수: {data.get("total_count", 0)}')
    print()
    for i, item in enumerate(data.get("list", []), 1):
        rno = item.get("rcept_no", "")
        print(f'{i}. {item.get("rcept_dt", "")} | {item.get("report_nm", "")} | 접수번호 {rno}')
        if rno:
            print(f'   DART: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rno}')
        if item.get("rm"):
            print(f'   비고: {item.get("rm")}')


def do_company(payload: dict, title_query: str):
    corp = corp_from_payload(payload, title_query)
    data = api_json("company.json", {"corp_code": corp["corp_code"]})
    print("# OpenDART 기업개황")
    print()
    if data.get("status") != "000":
        fail(f'{data.get("status")} {data.get("message")}')
    for k in ["corp_name", "corp_name_eng", "stock_name", "stock_code", "ceo_nm", "corp_cls", "jurir_no", "bizr_no", "adres", "hm_url", "ir_url", "phn_no", "fax_no", "induty_code", "est_dt", "acc_mt"]:
        print(f'- {k}: {data.get(k, "")}')


def do_document(payload: dict):
    rcept_no = str(payload.get("rcept_no") or "").strip()
    if not (rcept_no.isdigit() and len(rcept_no) == 14):
        fail("document 모드에는 14자리 rcept_no가 필요합니다.")
    raw = fetch(api_url("document.xml", {"rcept_no": rcept_no}), timeout=60)
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        snippet = raw[:500].decode("utf-8", errors="replace")
        fail(f"원문 ZIP 해석 실패. OpenDART 응답: {strip_markup(snippet)}")
    names = [n for n in zf.namelist() if not n.endswith("/")]
    chunks = []
    for name in names:
        if not name.lower().endswith((".xml", ".html", ".htm", ".txt")):
            continue
        b = zf.read(name)
        txt = None
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                txt = b.decode(enc)
                break
            except UnicodeDecodeError:
                pass
        if txt is None:
            txt = b.decode("utf-8", errors="replace")
        plain = strip_markup(txt)
        if plain:
            chunks.append(f"\n\n--- 파일: {name} ---\n{plain}")
    combined = "".join(chunks)
    limit = min(int(payload.get("max_chars", 50000)), 55000)
    print("# OpenDART 공시서류 원문")
    print()
    print(f"- 접수번호: {rcept_no}")
    print(f"- 원본 포함 파일 수: {len(names)}")
    print(f"- 텍스트 추출 파일 수: {len(chunks)}")
    print(f"- DART: https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}")
    print()
    if len(combined) > limit:
        combined = combined[:limit] + "\n\n[댓글 길이 제한으로 이후 원문 생략]"
    print(combined)


def main():
    if not API_KEY:
        fail("GitHub Secret OPENDART_API_KEY가 비어 있습니다.")
    raw = os.environ.get("OPENDART_REQUEST", "").strip()
    raw_title = os.environ.get("OPENDART_TITLE_QUERY", "").strip()
    title_query = re.sub(r"^\[OpenDART\]\s*", "", raw_title, flags=re.IGNORECASE).strip()
    payload = {}
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            fail(f"이슈 본문은 JSON 형식이어야 합니다: {e}")
    mode = str(payload.get("mode", "list")).lower()
    if mode == "list":
        do_list(payload, title_query)
    elif mode == "company":
        do_company(payload, title_query)
    elif mode == "document":
        do_document(payload)
    else:
        fail("지원 mode: list, company, document")


if __name__ == "__main__":
    main()
