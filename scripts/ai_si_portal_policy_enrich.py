from __future__ import annotations
import datetime as dt
import html
import json
import pathlib
import re
import urllib.request
from urllib.parse import urlsplit

from ai_si_portal_semantic import SOURCE_URL, extract_portal_links, advance_portal_state

ROOT = pathlib.Path(__file__).resolve().parents[1]
PENDING = ROOT / "out/ai_safety_policy_watch_pending_state.json"
STATUS = ROOT / "out/ai_safety_policy_watch_status.md"
TITLE = ROOT / "out/ai_safety_policy_watch_alert_title.txt"
BODY = ROOT / "out/ai_safety_policy_watch_alert.html"

def update_portal():
    now = dt.datetime.now(dt.timezone.utc)
    state = json.loads(PENDING.read_text(encoding="utf-8"))
    previous = state.get("si_portal")
    try:
        req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as response:
            final_host = (urlsplit(response.geturl()).hostname or "").lower()
            if final_host not in {"si.gov", "www.si.gov"}:
                raise ValueError("SI.gov redirect destination is not official")
            document = response.read(1000000).decode("utf-8", "ignore")
        links = extract_portal_links(document)
        latest, confirmed = advance_portal_state(previous, links, now)
    except Exception as error:
        state.setdefault("last_collection", {})["si_portal_error"] = str(error)
        state["last_collection"]["si_portal_health"] = "확인 불가"
        PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
        with STATUS.open("a",encoding="utf-8") as output:
            output.write("\n- SI.gov: 확인 불가 (기준선 보존)\n")
        print("si_portal_health=degraded")
        return

    state["si_portal"] = latest
    def is_historical(url):
        m = re.search(r"/(20[0-9]{2})/(0[1-9]|1[0-2])/", url)
        if not m:
            return False
        year, month = int(m.group(1)), int(m.group(2))
        previous_month = (now.date().replace(day=1) - dt.timedelta(days=1)).replace(day=1)
        return dt.date(year, month, 1) < previous_month

    results = [x for x in confirmed if not is_historical(x["url"])]
    collection = state.setdefault("last_collection", {})
    collection["si_portal_health"] = "정상"
    collection.pop("si_portal_error",None)
    collection["si_portal_known_links"] = len(latest["known_links"])
    collection["si_portal_pending_candidates"] = len(latest["candidates"])
    collection["si_portal_new_events"] = 0

    old = BODY.read_text(encoding="utf-8").strip() if BODY.exists() else ""
    heading = TITLE.read_text(encoding="utf-8").strip() if TITLE.exists() else ""
    count_match = re.search(r"중요 변화\s+(\d+)건", heading)
    start = int(count_match.group(1)) if count_match else 0
    additions = []
    for item in results:
        if item["url"] in old:
            continue
        label = html.escape(item["title"])
        url = html.escape(item["url"],quote=True)
        number = start + len(additions) + 1
        additions.append(f'<b>{number}. 백악관 SI 정책 · {html.escape(item["category"])}</b>\n'
                         f'• SI.gov 새 공식 정책문서 연결: {label}\n'
                         f'• <b>검증</b>: 공식 링크 2회·10분 이상 관측. 예산·시행은 원문 재확인 필요\n'
                         f'🔗 <a href="{url}">SI.gov 연결 원문</a>')
    if additions:
        heading = heading or "📌 <b>AI 안전표준·보안산업 정책 Watch</b> · 중요 변화 0건"
        heading = re.sub(r"중요 변화\s+\d+건",f"중요 변화 {start + len(additions)}건",heading)
        TITLE.write_text(heading+"\n",encoding="utf-8")
        BODY.write_text((old+"\n\n" if old else f"<i>{now.astimezone(dt.timezone(dt.timedelta(hours=9))):%m/%d %H:%M} KST</i>\n\n")
                        +"\n\n".join(additions)+"\n",encoding="utf-8")
    collection["si_portal_new_events"] = len(additions)
    collection["new_events"] = int(collection.get("new_events") or 0) + len(additions)
    PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with STATUS.open("a",encoding="utf-8") as output:
        output.write(f"\n- SI.gov 링크 {len(latest['known_links'])}개 · 신규 중요 변화 {len(additions)}건\n")
    print(f"si_portal_health=ok links={len(latest['known_links'])} new_events={len(additions)}")

if __name__ == "__main__":
    update_portal()
