#!/usr/bin/env python3
import argparse
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import war_peace_reconstruction_watch_barrage_energy as prev

watch = prev.watch
runner = prev.runner
base = prev.base
_prev_build_alert = watch.build_alert

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36 khs-watch-bodycolor/1.0"

# 실제 발생한 군사행동을 뜻하는 강한 표현. 휴전·협상 기사 안에 과거 공격 이력이 잠깐 나오는 것보다
# '공격 재개/보복/전면전/사상자' 같은 현재 행동 표현에 높은 우선순위를 둔다.
BODY_RED_CRITICAL = (
    "사실상 전면전", "전면전 양상", "확전", "교전을 격화", "교전 격화", "공격 재개", "공습 재개",
    "보복 공격", "보복 공습", "재보복", "미사일로 공격", "미사일 공격", "드론 공격", "무인기 공격",
    "폭격", "포격", "피격", "격침", "타격했다", "타격했다", "공격했다", "공격을 가했다",
    "사망", "숨졌다", "숨지고", "부상", "다쳤", "피란", "대피", "난타전",
    "full-scale war", "all-out war", "escalat", "fighting intensified", "attack resumed", "attacks resumed",
    "airstrikes resumed", "retaliatory attack", "retaliatory strike", "missile attack", "drone attack",
    "struck", "was hit", "were hit", "killed", "wounded", "displaced", "sunk", "bombardment", "shelling",
)
BODY_GREEN_CRITICAL = (
    "휴전 합의", "휴전 재개", "휴전 연장", "정전 합의", "종전 합의", "평화 합의", "평화협정",
    "종전 협상 재개", "평화 협상 재개", "평화협상 재개", "협상 재개 의사", "3자 협상 재개",
    "3자 회담", "삼자 회담", "긴장 완화", "단계적 완화", "공격 자제", "공격 중단", "공습 중단",
    "상호 공격 자제", "교전 중단", "적대행위 중단", "재건", "복구", "재건기금", "재건 기금",
    "ceasefire agreement", "ceasefire extended", "ceasefire resumed", "truce", "peace agreement", "peace deal",
    "peace talks restart", "restart peace talks", "resume peace talks", "trilateral talks", "de-escalation", "deescalation",
    "halt attacks", "stop attacks", "restraint on attacks", "reconstruction", "rebuilding",
)

# '공격 중단/자제' 같은 완화 문구는 공격이라는 단어가 있어도 빨강으로 세지 않는다.
DEESCAPE = (
    "공격 자제", "공격 중단", "공습 중단", "공격을 자제", "공격을 중단", "상호 공격 자제",
    "교전 중단", "적대행위 중단", "halt attacks", "stop attacks", "restraint on attacks",
)


class _ParagraphParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_p = 0
        self.skip = 0
        self.buf = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        if tag == "p" and not self.skip:
            self.in_p += 1
            self.buf = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "p" and self.in_p:
            text = re.sub(r"\s+", " ", " ".join(self.buf)).strip()
            if len(text) >= 30:
                self.paragraphs.append(text)
            self.in_p -= 1
            self.buf = []
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if self.in_p and not self.skip:
            self.buf.append(html.unescape(data))


def _request_text(url, timeout=10, max_bytes=1_500_000):
    if not url or not url.startswith(("http://", "https://")):
        return "", ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final_url = r.geturl()
            raw = r.read(max_bytes)
            ctype = r.headers.get_content_charset() or "utf-8"
        try:
            text = raw.decode(ctype, errors="replace")
        except Exception:
            text = raw.decode("utf-8", errors="replace")
        return final_url, text
    except Exception:
        return "", ""


def _bing_target(link):
    """Bing News apiclick URL에 실제 원문 주소가 url= 파라미터로 들어 있으면 추출한다."""
    try:
        p = urllib.parse.urlparse(link or "")
        if "bing.com" not in p.netloc.lower():
            return ""
        q = urllib.parse.parse_qs(p.query)
        return (q.get("url") or [""])[0]
    except Exception:
        return ""


def _title_tokens(title):
    toks = re.findall(r"[0-9A-Za-z가-힣]{2,}", (title or "").lower())
    stop = {"reuters", "뉴스", "속보", "원문", "the", "and", "for", "with", "says"}
    return {t for t in toks if t not in stop}


def _similarity(a, b):
    aa, bb = _title_tokens(a), _title_tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, min(len(aa), len(bb)))


def _resolve_via_bing(row):
    """Google News 래퍼이면 제목+출처로 Bing News RSS를 보조 조회해 실제 원문 URL을 찾는다."""
    title = (row.get("title_original") or row.get("title_ko") or "").strip()
    source = (row.get("source") or "").strip()
    if not title:
        return ""
    queries = [f'"{title}" {source}'.strip(), title]
    best = (0.0, "")
    for query in queries:
        try:
            url = "https://www.bing.com/news/search?format=rss&q=" + urllib.parse.quote(query)
            _, xml_text = _request_text(url, timeout=8, max_bytes=500_000)
            if not xml_text:
                continue
            root = ET.fromstring(xml_text)
            for item in root.findall("./channel/item")[:12]:
                t = html.unescape((item.findtext("title") or "").strip())
                link = (item.findtext("link") or "").strip()
                direct = _bing_target(link) or link
                score = _similarity(title, t)
                if source and source.lower() in t.lower():
                    score += 0.15
                if score > best[0] and direct.startswith(("http://", "https://")):
                    best = (score, direct)
            if best[0] >= 0.55:
                break
        except Exception:
            continue
    return best[1] if best[0] >= 0.35 else ""


def _resolve_original(row):
    link = (row.get("link") or "").strip()
    direct = _bing_target(link)
    if direct:
        return direct
    try:
        host = urllib.parse.urlparse(link).netloc.lower()
    except Exception:
        host = ""
    if link.startswith(("http://", "https://")) and "news.google.com" not in host:
        return link
    return _resolve_via_bing(row)


def _jsonld_article_body(page):
    # 대부분 언론사의 JSON-LD articleBody를 우선 사용한다.
    for m in re.finditer(r'"articleBody"\s*:\s*"((?:\\.|[^"\\])*)"', page or "", flags=re.I | re.S):
        try:
            text = json.loads('"' + m.group(1) + '"')
            text = html.unescape(re.sub(r"\s+", " ", text)).strip()
            if len(text) >= 250:
                return text
        except Exception:
            pass
    return ""


def _paragraph_text(page):
    try:
        parser = _ParagraphParser()
        parser.feed(page or "")
        text = "\n".join(parser.paragraphs[:35])
        text = re.sub(r"\s+", " ", text).strip()
        return text if len(text) >= 250 else ""
    except Exception:
        return ""


def _extract_body(page):
    if not page:
        return ""
    body = _jsonld_article_body(page)
    if body:
        return body[:12000]
    body = _paragraph_text(page)
    if body:
        return body[:12000]
    # 마지막 대안은 메타 설명. 본문으로 오인하지 않도록 250자 이상일 때만 사용한다.
    metas = re.findall(r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)', page, flags=re.I)
    if metas:
        text = html.unescape(max(metas, key=len)).strip()
        if len(text) >= 250:
            return text[:4000]
    return ""


def _enrich_body(row):
    if row.get("body_checked"):
        return
    row["body_checked"] = True
    original = _resolve_original(row)
    if not original:
        return
    final_url, page = _request_text(original, timeout=10)
    body = _extract_body(page)
    if body:
        row["article_text"] = body
        row["resolved_url"] = final_url or original
        row["body_verified"] = True


def _clean_for_red(text):
    t = (text or "").lower()
    for phrase in DEESCAPE:
        t = t.replace(phrase, " ")
    return t


def _body_color(row):
    """본문 확보 시 본문이 최우선. 본문이 중립이면 누적 태그로 억지 색상 지정하지 않는다."""
    body = (row.get("article_text") or "").strip()
    if not body:
        return prev._event_color(row)

    # 첫 부분에 현재 기사 핵심이 집중되므로 지나치게 긴 라이브블로그의 과거 내용 영향을 줄인다.
    sample = (body[:6500] + " " + (row.get("title_original") or "") + " " + (row.get("title_ko") or "")).lower()
    red_sample = _clean_for_red(sample)

    red_hits = sum(1 for p in BODY_RED_CRITICAL if p in red_sample)
    green_hits = sum(1 for p in BODY_GREEN_CRITICAL if p in sample)

    # 실제 전면전·확전·공격재개·사상자 같은 행동이 확인되면 협상 언급이 함께 있어도 빨강.
    hard_red = any(p in red_sample for p in (
        "사실상 전면전", "전면전 양상", "교전을 격화", "공격 재개", "공습 재개", "보복 공격", "보복 공습",
        "재보복", "미사일로 공격", "미사일 공격", "드론 공격", "난타전", "full-scale war", "all-out war",
        "attack resumed", "attacks resumed", "retaliatory attack", "retaliatory strike", "missile attack",
    ))
    casualty_red = any(p in red_sample for p in ("사망", "숨지고", "부상", "피란", "killed", "wounded", "displaced")) and red_hits >= 2
    if hard_red or casualty_red or red_hits >= 4:
        return "red"

    # 휴전·협상재개·공격중단·재건이 본문의 주된 현재 변화이면 초록.
    if green_hits >= 1 and red_hits <= 1:
        return "green"
    if green_hits >= 2 and red_hits < green_hits:
        return "green"

    # 본문을 읽었는데 공격/휴전 어느 쪽도 뚜렷하지 않은 정책·제재 기사는 무색 처리.
    return ""


def _strip_existing_colors(text):
    lines = []
    for line in (text or "").splitlines():
        # 기존 상단 범례를 제거한 뒤 본문 판정으로 다시 만든다.
        if "<b>공격·확전</b>" in line or "<b>재건·휴전</b>" in line:
            continue
        line = re.sub(r"^\s*[🔴🟢]\s+", "", line)
        lines.append(line)
    return "\n".join(lines)


def _prefix_by_number(text, items):
    lines = text.splitlines()
    for idx, row in enumerate(items[:8], 1):
        color = _body_color(row)
        if not color:
            continue
        marker = "🔴" if color == "red" else "🟢"
        patterns = (
            re.compile(rf'<b>{idx}\.\s'),
            re.compile(rf'^\[[^\]]+\]\s*(?:<b>)?{idx}\.\s'),
            re.compile(rf'^(?:🟥|🟧|🟨)?\s*(?:<b>)?{idx}\.\s'),
        )
        for j, line in enumerate(lines):
            if any(p.search(line) for p in patterns):
                lines[j] = f"{marker} {line}"
                break
    return "\n".join(lines)


def _reapply_colors(text, items):
    text = _strip_existing_colors(text)
    colors = {_body_color(x) for x in items}
    colors.discard("")
    badges = []
    if "red" in colors:
        badges.append("🔴 <b>공격·확전</b>")
    if "green" in colors:
        badges.append("🟢 <b>재건·휴전</b>")
    if badges:
        lines = text.splitlines()
        if lines:
            lines.insert(1, "  |  ".join(badges))
            text = "\n".join(lines)
    return _prefix_by_number(text, items)


def build_alert(items, markets, now):
    # 최종 송출 후보(최대 8건)만 원문 본문을 추가 조회해 5분 감시 속도를 유지한다.
    for row in items[:8]:
        _enrich_body(row)
    text = _prev_build_alert(items, markets, now)
    return _reapply_colors(text, items).strip()[:4000] + "\n"


watch.build_alert = build_alert


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()
