#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import korea_market_stress_watch_v4 as watch

BOK_HISTORY_URL = "https://www.bok.or.kr/portal/singl/baseRate/list.do?menuNo=200656"

_session = requests.Session()
_session.headers.update(watch.HEADERS)
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=4,
            connect=4,
            read=4,
            status=4,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
    ),
)


def retry_get(url: str, timeout: int = 35) -> requests.Response:
    last: Exception | None = None
    for attempt in range(3):
        try:
            r = _session.get(url, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"HTTP 조회 실패: {url}: {last}")


def fetch_bok_base_rate(now: dt.datetime) -> dict[str, Any]:
    soup = BeautifulSoup(retry_get(BOK_HISTORY_URL).text, "html.parser")
    candidates: list[tuple[dt.date, float]] = []

    # 공식 기준금리 추이 표의 행 단위로 날짜와 금리를 짝지어 추출한다.
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        joined = " ".join(cells)
        m = re.search(
            r"(20\d{2})[\s년.-]*?(\d{1,2})\s*월\s*(\d{1,2})\s*일[\s\S]{0,40}?([0-9]+(?:\.[0-9]+)?)\s*%?\s*$",
            joined,
        )
        if not m:
            continue
        try:
            day = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            rate = float(m.group(4))
        except Exception:
            continue
        if 0.0 <= rate <= 20.0:
            candidates.append((day, rate))

    # 행 구조가 바뀌면 페이지 전체 텍스트에서 '연도 + 월일 + 금리' 패턴을 보조 추출한다.
    if not candidates:
        text = soup.get_text(" ", strip=True)
        for m in re.finditer(
            r"(20\d{2})[\s년.-]{0,8}(\d{1,2})\s*월\s*(\d{1,2})\s*일[\s\S]{0,30}?([0-9]+(?:\.[0-9]+)?)",
            text,
        ):
            try:
                day = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                rate = float(m.group(4))
            except Exception:
                continue
            if 0.0 <= rate <= 20.0:
                candidates.append((day, rate))

    if not candidates:
        raise RuntimeError("한국은행 공식 기준금리 추이 표 파싱 실패")

    day, rate = max(candidates, key=lambda x: x[0])
    return {"date": day.isoformat(), "value": rate, "source": BOK_HISTORY_URL}


watch.get = retry_get
watch.fetch_bok_base_rate = fetch_bok_base_rate
watch.BOK_HOME_URL = BOK_HISTORY_URL

if __name__ == "__main__":
    raise SystemExit(watch.main())
