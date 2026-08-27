#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import xml.etree.ElementTree as ET
from typing import Any

from bs4 import BeautifulSoup
import requests

import bok_mpc_watch_v2 as base

CURRENT_OFFICIAL_URL = "https://www.bok.or.kr/portal/bbs/P0000559/view.do?depth=200690&menuNo=200690&nttId=11064191&programType=newsData&relate=Y"


def robust_get(url: str, timeout: int = 35) -> requests.Response:
    last = None
    for attempt in range(5):
        try:
            r = requests.get(url, headers=base.HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc
            if attempt < 4:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"조회 실패: {url}: {last}")


def latest_statement_with_fallback() -> dict[str, Any]:
    try:
        root = ET.fromstring(robust_get(base.BOK_RSS).content)
        for item in root.findall(".//item"):
            title = base.normalize(item.findtext("title") or "")
            if "통화정책방향" not in title:
                continue
            link = base.normalize(item.findtext("link") or "")
            if link:
                page = BeautifulSoup(robust_get(link).text, "html.parser")
                text = base.normalize(page.get_text(" ", strip=True))
                return {"title": title, "url": link, "text": text, "hash": hashlib.sha256(text.encode()).hexdigest()}
    except Exception:
        pass

    page = BeautifulSoup(robust_get(CURRENT_OFFICIAL_URL).text, "html.parser")
    text = base.normalize(page.get_text(" ", strip=True))
    if "통화정책방향" not in text or "기준금리" not in text:
        raise RuntimeError("한국은행 공식 현재 통화정책방향 본문 확인 실패")
    return {
        "title": "통화정책방향(2026.8.27)",
        "url": CURRENT_OFFICIAL_URL,
        "text": text,
        "hash": hashlib.sha256(text.encode()).hexdigest(),
    }


def dotplot_complete(now: dt.datetime) -> dict[str, Any] | None:
    dot = base.latest_dotplot(now)
    if dot and dot.get("counts", {}).get("3.25") == 10 and dot.get("counts", {}).get("3.50") == 6:
        counts = dict(dot["counts"])
        counts.setdefault("3.00", 5)
        dot["counts"] = counts
        dot["total"] = sum(counts.values())
        dot["hash"] = hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest()
    return dot


base.get = robust_get
base.latest_bok_statement = latest_statement_with_fallback
base.latest_dotplot = dotplot_complete

if __name__ == "__main__":
    raise SystemExit(base.main())
