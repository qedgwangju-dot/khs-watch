from __future__ import annotations

import json
import os
import re
from html import unescape
from xml.etree import ElementTree

from models import Document
from search.base import Fetcher


def _clean_html(value: str) -> str:
    return unescape(re.sub(r"<[^>]+>", " ", value or "")).strip()


async def collect_feed(name: str, cfg: dict, fetcher: Fetcher, session: object, since: str | None) -> list[Document]:
    xml = await fetcher.get(session, cfg["url"])
    root = ElementTree.fromstring(xml)
    docs: list[Document] = []
    nodes = root.findall(".//item") or root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}url")
    for node in nodes:
        def txt(paths: list[str]) -> str:
            for path in paths:
                found = node.find(path)
                if found is not None and found.text:
                    return found.text.strip()
            return ""
        url = txt(["link", "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"])
        published = txt(["pubDate", "{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod"])
        if since and published and published < since:
            continue
        title = txt(["title"]) or url
        body = _clean_html(txt(["description", "{http://purl.org/rss/1.0/modules/content/}encoded"]))
        docs.append(Document(name, url, title, published, body, bool(cfg.get("official")), float(cfg.get("reliability", .5))))
    return docs


async def collect_dart(name: str, cfg: dict, fetcher: Fetcher, session: object, since: str | None) -> list[Document]:
    key = os.getenv("DART_API_KEY")
    if not key:
        raise RuntimeError("DART_API_KEY is not configured")
    begin = (since or "2026-07-30")[:10].replace("-", "")
    docs: list[Document] = []
    for corp_code in ("00126380",):  # 삼성전자
        raw = await fetcher.get(session, "https://opendart.fss.or.kr/api/list.json", {
            "crtfc_key": key, "corp_code": corp_code, "bgn_de": begin, "page_count": "100"
        })
        payload = json.loads(raw)
        if payload.get("status") not in ("000", "013"):
            raise RuntimeError(f"DART error {payload.get('status')}: {payload.get('message')}")
        for item in payload.get("list", []):
            rcept_no = item["rcept_no"]
            docs.append(Document(
                name,
                f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                item.get("report_nm", ""),
                item.get("rcept_dt", ""),
                json.dumps(item, ensure_ascii=False),
                True, float(cfg.get("reliability", 1.0)),
            ))
    return docs


async def collect_source(name: str, cfg: dict, fetcher: Fetcher, session: object, since: str | None) -> list[Document]:
    if cfg["kind"] == "dart":
        return await collect_dart(name, cfg, fetcher, session, since)
    if cfg["kind"] in {"rss", "sitemap"}:
        return await collect_feed(name, cfg, fetcher, session, since)
    raise ValueError(f"Unsupported source kind: {cfg['kind']}")
