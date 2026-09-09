#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ALERT = Path("out/pjm_data_center_policy_alert.txt")


def classify(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("consumer", "ratepayer", "transmission", "affordability", "cost allocation", "costs")):
        return "비용부담·송전망"
    if any(k in low for k in ("large load", "registry", "iras", "connect and manage", "connect data center", "connect data centre")):
        return "대형부하 접속·등록"
    if any(k in low for k in ("elcc", "capacity credit", "effective load carrying")):
        return "ELCC·용량인정"
    if any(k in low for k in ("backstop", "rbp", "auction", "procurement", "reliability")):
        return "RBP 조달·FERC 심사"
    return "기타 정책 변화"


def main() -> None:
    if not ALERT.exists():
        return
    text = ALERT.read_text(encoding="utf-8").strip()
    if not text:
        return

    lines = text.splitlines()
    try:
        start = lines.index("<b>🆕 신규 확인</b>")
    except ValueError:
        return

    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i] == "<b>📊 투자 해석</b>"),
        len(lines),
    )
    section = lines[start + 1:end]

    summary = next((ln for ln in section if ln.startswith("• 새 자료 ")), None)
    source_rows = [ln for ln in section if "<a href=" in ln and ("[공식]" in ln or "[보도]" in ln)]
    if not source_rows:
        return

    chosen: list[tuple[str, str]] = []
    used_themes: set[str] = set()
    for row in source_rows:
        theme = classify(row)
        if theme in used_themes:
            continue
        used_themes.add(theme)
        chosen.append((theme, row))
        if len(chosen) >= 4:
            break

    rebuilt = ["<b>🆕 핵심 신규 변화</b>"]
    if summary:
        rebuilt.append(summary)

    row_re = re.compile(
        r'^• <b>\[(?P<badge>공식|보도)\] (?P<source>.*?)</b> · (?P<title>.*?)\s+<a href="(?P<url>[^"]+)">원문</a>$'
    )
    for theme, row in chosen:
        m = row_re.match(row)
        if not m:
            rebuilt.append(row)
            continue
        badge = m.group("badge")
        source = m.group("source")
        title = m.group("title").strip()
        url = m.group("url")
        rebuilt.append(f"• <b>{theme}</b> · [{badge}] {source}")
        rebuilt.append(f"  ↳ <a href=\"{url}\">원문 보기</a> · {title}")

    total_match = re.search(r"새 자료 <b>(\d+)건</b>", summary or "")
    total = int(total_match.group(1)) if total_match else len(source_rows)
    hidden = max(0, total - len(chosen))
    if hidden:
        rebuilt.append(f"• <i>나머지 {hidden}건은 중복·추적 상태에 저장해 다음 변화 판정에 반영합니다.</i>")

    # Keep a blank line before the next major section.
    new_lines = lines[:start] + rebuilt + [""] + lines[end:]
    ALERT.write_text("\n".join(new_lines).strip() + "\n", encoding="utf-8")
    print(f"pjm_alert_grouped themes={len(chosen)} hidden={hidden}")


if __name__ == "__main__":
    main()
