from __future__ import annotations

import re
from typing import Any


_ITEM_RE = re.compile(r"^\s*\d+\.\s+\[[^\]]+\]\s+.+")
_BULLET_RE = re.compile(r"^\s*-\s+")
_SOURCE_RE = re.compile(r"(?:^\s*-\s*(?:출처|원문/출처)\s*:|<a\s+href=)", re.I)
_CORE_PREFIX_RE = re.compile(
    r"^\s*-\s*(?:핵심|핵심 변화|한눈에 보기|요약|변화|무엇이 바뀌었나|확인 근거|판단|의미|결론|워치 판단)\s*:",
    re.I,
)
_RISK_RE = re.compile(
    r"병목|실패|역풍|위험|리스크|지연|인허가|인증|규제|보험|수율|보증|책임|제약|채택 지연|공급망|반대 근거|다음 확인|조기 경보",
    re.I,
)
_COMPANY_RE = re.compile(
    r"기업|당사자|밸류체인|매출|수주|계약|고객|수혜|양산|생산|협력|공급사|제조사|시공|기자재|장비|부품|EPC|원청|하청",
    re.I,
)
_NUMBER_LABEL_RE = re.compile(
    r"^\s*-\s*(?:숫자|규모|금액|예산|물량|수량|단가|설비투자|투자|지원|용량|전력|매출|수주|계약|기간|일정)\s*:",
    re.I,
)
_MONEY_OR_UNIT_RE = re.compile(
    r"(?:\d[\d,.]*\s*(?:조원|억원|만원|원|달러|억\s*달러|백만\s*달러|%|GW|MW|kW|MWh|GWh|기|대|곳|건))",
    re.I,
)
_CORE_LABEL_STRIP_RE = re.compile(
    r"^\s*-\s*(?:핵심|핵심 변화|한눈에 보기|요약|변화|무엇이 바뀌었나|확인 근거|판단|의미|결론|워치 판단)\s*:\s*",
    re.I,
)
_HEADING_PREFIX_STRIP_RE = re.compile(r"^\s*\d+\.\s+\[[^\]]+\]\s+")


def _clean_key(value: str) -> str:
    return re.sub(r"[\s·•:;,.!?()\[\]{}]+", "", value or "").lower()


def _chunk_lines(lines: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if not line.strip():
            if current:
                chunks.append(current)
                current = []
            continue
        if _BULLET_RE.match(line) or not current:
            if current:
                chunks.append(current)
            current = [line.rstrip()]
        else:
            current.append(line.rstrip())
    if current:
        chunks.append(current)
    return chunks


def _chunk_text(chunk: list[str]) -> str:
    return " ".join(line.strip() for line in chunk if line.strip())


def _dedupe_chunks(chunks: list[list[str]], heading: str) -> list[list[str]]:
    output: list[list[str]] = []
    seen: set[str] = set()
    heading_text = _HEADING_PREFIX_STRIP_RE.sub("", heading).strip()
    heading_key = _clean_key(heading_text)
    for chunk in chunks:
        text = _chunk_text(chunk)
        if not text:
            continue
        core_text = _CORE_LABEL_STRIP_RE.sub("", text).strip()
        if _CORE_PREFIX_RE.match(text) and _clean_key(core_text) == heading_key:
            continue
        key = "core:" + _clean_key(core_text) if _CORE_PREFIX_RE.match(text) else _clean_key(text)
        if key in seen:
            continue
        seen.add(key)
        output.append(chunk)
    return output


def _bucket(chunk: list[str]) -> str:
    text = _chunk_text(chunk)
    if _SOURCE_RE.search(text):
        return "source"
    if _CORE_PREFIX_RE.match(text) or text.startswith("💡"):
        return "core"
    if _RISK_RE.search(text):
        return "risk"
    if _NUMBER_LABEL_RE.match(text) or _MONEY_OR_UNIT_RE.search(text):
        return "numbers"
    if _COMPANY_RE.search(text):
        return "company"
    return "detail"


def _render_item(heading: str, content_lines: list[str]) -> list[str]:
    chunks = _dedupe_chunks(_chunk_lines(content_lines), heading)
    if len(chunks) <= 3:
        result = [heading]
        for chunk in chunks:
            result.extend(chunk)
        return result

    groups: dict[str, list[list[str]]] = {
        key: [] for key in ("core", "numbers", "company", "risk", "detail", "source")
    }
    for chunk in chunks:
        groups[_bucket(chunk)].append(chunk)

    labels = {
        "core": "🔎 핵심 변화",
        "numbers": "💰 숫자",
        "company": "🇰🇷 기업·매출 연결",
        "risk": "⚠️ 병목·실패모드",
        "detail": "📌 세부",
        "source": "🔗 원문",
    }
    result = [heading]
    for key in ("core", "numbers", "company", "risk", "detail", "source"):
        if not groups[key]:
            continue
        result.append(labels[key])
        for chunk in groups[key]:
            result.extend(chunk)
    return result


def improve_policy_readability(body: str) -> str:
    raw_lines = str(body or "").splitlines()
    if not any(_ITEM_RE.match(line) for line in raw_lines):
        return body

    prefix: list[str] = []
    items: list[tuple[str, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    for line in raw_lines:
        if _ITEM_RE.match(line):
            if current_heading is not None:
                items.append((current_heading, current_lines))
            current_heading = line.rstrip()
            current_lines = []
        elif current_heading is None:
            if line.strip():
                prefix.append(line.rstrip())
        else:
            current_lines.append(line)
    if current_heading is not None:
        items.append((current_heading, current_lines))

    output: list[str] = list(prefix)
    for heading, lines in items:
        if output:
            output.append("")
        output.extend(_render_item(heading, lines))
    return "\n".join(output).strip() + "\n"


def install(formatter_module: Any) -> None:
    if getattr(formatter_module, "_KHS_READABILITY_PATCHED", False):
        return
    original = formatter_module.format_policy_message

    def wrapped(title: str, body: str, *, rates=None, now=None):
        out_title, out_body = original(title, body, rates=rates, now=now)
        return out_title, improve_policy_readability(out_body)

    formatter_module.format_policy_message = wrapped
    formatter_module._KHS_READABILITY_PATCHED = True
