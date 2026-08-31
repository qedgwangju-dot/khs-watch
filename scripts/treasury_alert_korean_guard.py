#!/usr/bin/env python3
"""Keep Treasury alerts Korean and add the verified Bessent policy-boundary interpretation.

The official watcher owns policy detection. This layer only upgrades the user-facing
interpretation and can emit one one-time policy-communication alert when the verified
Bessent interview changes the interpretation framework without changing Treasury's
formal buyback announcement.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "treasury_buyback_policy_alert.html"
DETAIL = ROOT / "out" / "treasury_buyback_policy_detail.json"
TITLE = ROOT / "out" / "treasury_buyback_policy_title.txt"
STATE = ROOT / "data" / "treasury_buyback_policy_state.json"
NEXT_STATE = ROOT / "data" / "treasury_buyback_policy_state_next.json"

BESSENT_REUTERS = "https://www.reuters.com/business/bessent-pushes-back-fears-over-us-debt-market-strains-2026-08-31/"
TREASURY_RELEASE = "https://home.treasury.gov/news/press-releases/sb0607"
BUYBACK_FAQ = "https://www.treasurydirect.gov/help-center/faqs/buyback-faqs/"
FRED_FX = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS"
UPGRADE_MARKER = "<b>정책 목적·경계선</b>"
UPGRADE_REVISION = 2

EXACT_TITLES = {
    "Treasury Announces Increased Sizes of Nominal Long-End Liquidity Support Buybacks Beginning September 9":
        "미 재무부, 장기 명목국채 유동성 지원 바이백 규모 확대 — 9월 9일 시행",
}


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def latest_fx() -> tuple[float, str]:
    req = urllib.request.Request(FRED_FX, headers={"User-Agent": "Mozilla/5.0 khs-watch-treasury-guard/2.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        text = response.read().decode("utf-8", errors="replace")
    rows = [line.strip().split(",") for line in text.splitlines()[1:] if "," in line]
    for row in reversed(rows):
        if len(row) >= 2 and row[1] and row[1] != ".":
            return float(row[1]), row[0]
    raise RuntimeError("FRED DEXKOUS 최신 확인값을 찾지 못했습니다.")


def fmt_krw(usd_bn: float, fx: float) -> str:
    won = usd_bn * 1_000_000_000 * fx
    jo = int(won // 1_000_000_000_000)
    eok = int(round((won - jo * 1_000_000_000_000) / 100_000_000))
    if eok >= 10000:
        jo += 1
        eok -= 10000
    if jo and eok:
        return f"약 {jo:,}조{eok:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {eok:,}억원"


def translate_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    if title in EXACT_TITLES:
        return EXACT_TITLES[title]
    low = title.lower()
    if "buyback" in low and ("long-end" in low or "long end" in low):
        if "increase" in low or "increased" in low or "expand" in low:
            return "미 재무부, 장기 명목국채 유동성 지원 바이백 규모 확대"
        if "decrease" in low or "reduce" in low:
            return "미 재무부, 장기 명목국채 유동성 지원 바이백 규모 축소"
        return "미 재무부, 장기 명목국채 유동성 지원 바이백 정책 변경"
    if "quarterly refunding" in low or "refunding" in low:
        return "미 재무부 분기 차환·자금조달 계획 발표"
    if "treasury" in low:
        return "미 재무부 공식 발표"
    return title


def policy_block() -> str:
    return "\n".join([
        "",
        "<b>정책 목적·경계선</b>",
        "• Bessent는 Reuters 인터뷰에서 자신이 시장의 균형가격을 바꿀 수 있다고 보지 않으며, 재무부 역할은 움직임의 속도를 늦춰 시장이 무질서해지는 것을 막는 것이라고 설명했습니다.",
        "• 따라서 현재 정책선은 <b>특정 금리·가격 통제</b>가 아니라 <b>유동성·변동성 완화</b>입니다.",
        "• 시장 기능이 정상인데도 특정 금리 수준에 맞춰 바이백·발행구조를 반복 조정하면 ‘유동성 지원 → 사실상 금리관리’로 정책선 이탈 경보를 올립니다.",
        "",
        "<b>Bessent 금리상승 원인설 검증</b>",
        "• Bessent는 최근 장기금리 상승의 상당 부분을 이란발 에너지 가격·인플레이션 압력과 견조한 성장으로 설명했습니다.",
        "• 유가↓ + 기대인플레이션↓ + 10년물↓ → 설명 지지",
        "• 유가↓ + 기대인플레이션↓인데 10년물 고착·상승 → 재정·국채공급·기간 프리미엄 영향이 더 강한 것으로 판정",
        "• 유가↑ + 기대인플레이션↑ + 10년물↑ → 에너지·인플레이션 설명과 부합",
        "",
        "<b>실행 확인</b>",
        "• 정책 변경 효력은 9월 9일, Bessent가 밝힌 확대 운영 시작은 9월 10일입니다.",
        "• 첫 확대 운영의 실제 매입액·총 제시액·상한 소진율과 이후 +1일·+3일·+5일 10년·30년 명목·실질금리 지속성을 확인합니다.",
        "• CTA 숏 스퀴즈가 발생해도 시장 결과로 분리하며 Bessent의 공식 정책목표로 단정하지 않습니다.",
    ])


def one_time_alert(fx: float, fx_date: str) -> str:
    return "\n".join([
        "<b>핵심 판단</b>",
        "🟢 Bessent가 장기물 바이백의 정책 목적을 명확히 했습니다. 현재 공식선은 금리를 특정 수준으로 누르는 수익률 통제가 아니라, 얇은 유동성 환경에서 가격 이동이 무질서하게 가속되는 것을 완화하는 것입니다.",
        "",
        "<b>확정 사실</b>",
        f"• 장기 비지표물 바이백: 회당 최대 20억달러({fmt_krw(2.0, fx)}) → 최소 40억달러({fmt_krw(4.0, fx)}). 미 재무부 공식 효력일은 9월 9일입니다.",
        "• Bessent는 Reuters에 확대 운영이 9월 10일부터 시작되며 아직 확대된 바이백은 집행되지 않았다고 설명했습니다.",
        "• Bessent는 자신이 시장의 균형가격을 바꿀 수 있다고 생각하지 않으며, 시장 움직임의 속도를 늦춰 무질서한 거래를 방지하는 것이 역할이라고 밝혔습니다.",
        policy_block(),
        "",
        "<b>한 줄 결론</b>",
        "현재는 ‘베센트가 10년물 4.3%를 만들겠다’가 아니라 <b>유동성·변동성 관리가 공식 정책선</b>입니다. 9월 10일 이후 정상시장에서도 금리수준에 맞춰 바이백·발행구조를 반복 조정하는지가 사실상 금리관리로 넘어가는지의 핵심 경계선입니다.",
        "",
        f"환율 기준: FRED DEXKOUS {fx_date}, 1달러={fx:,.2f}원",
        f'<a href="{BESSENT_REUTERS}">Bessent Reuters 인터뷰</a> · <a href="{TREASURY_RELEASE}">미 재무부 공식 발표</a> · <a href="{BUYBACK_FAQ}">바이백 공식 설명</a>',
    ])


def mark_revision() -> None:
    state = load_json(NEXT_STATE)
    state["bessent_policy_boundary_revision"] = UPGRADE_REVISION
    NEXT_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    state = load_json(STATE)
    revision = int(state.get("bessent_policy_boundary_revision", 0) or 0)

    if not ALERT.exists():
        if revision >= UPGRADE_REVISION:
            return 0
        fx, fx_date = latest_fx()
        TITLE.write_text(
            "🇺🇸 미 재무부 장기물 바이백 — 베센트, ‘금리 통제 아닌 변동성 완화’ 정책선 명확화\n",
            encoding="utf-8",
        )
        body = one_time_alert(fx, fx_date)
        if len(body) > 3900:
            raise RuntimeError(f"업그레이드 재무부 알림 본문이 너무 깁니다: {len(body)}")
        ALERT.write_text(body + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps({
            "type": "bessent_policy_boundary_update",
            "source": {"url": BESSENT_REUTERS, "title": "Bessent Reuters 인터뷰", "date": "2026-08-31"},
            "fx": fx,
            "fx_date": fx_date,
            "revision": UPGRADE_REVISION,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        mark_revision()
        return 0

    text = ALERT.read_text(encoding="utf-8")
    original_title = None
    source_url = ""
    if DETAIL.exists():
        try:
            detail = json.loads(DETAIL.read_text(encoding="utf-8"))
            source = detail.get("source") or {}
            original_title = source.get("title")
            source_url = str(source.get("url") or "")
        except Exception:
            pass

    if original_title:
        translated = translate_title(str(original_title))
        text = text.replace(
            f"• 공식 출처: <b>{original_title}</b>",
            f"• 공식 출처: <b>{translated}</b>",
        )

    pattern = re.compile(r"(• 공식 출처: <b>)([^<]+)(</b>)")
    def repl(match: re.Match[str]) -> str:
        shown = match.group(2).strip()
        if re.search(r"[A-Za-z]{4,}", shown):
            shown = translate_title(shown)
            if re.search(r"[A-Za-z]{4,}", shown):
                shown = "미 재무부 공식 발표"
        return match.group(1) + shown + match.group(3)
    text = pattern.sub(repl, text)

    if UPGRADE_MARKER not in text:
        text = text.rstrip() + "\n" + policy_block() + "\n"

    if source_url.rstrip("/") == TREASURY_RELEASE.rstrip("/") and TITLE.exists():
        TITLE.write_text(
            "🇺🇸 미 재무부 장기물 바이백 — 베센트, ‘금리 통제 아닌 변동성 완화’ 정책선 명확화\n",
            encoding="utf-8",
        )

    if re.search(r"• 공식 출처: <b>[^<]*\b(Treasury|Buyback|Refunding)\b", text, re.I):
        raise RuntimeError("공식 출처 제목의 한국어 변환이 완료되지 않았습니다.")
    if len(text) > 3900:
        raise RuntimeError(f"업그레이드된 재무부 알림 본문이 너무 깁니다: {len(text)}")

    ALERT.write_text(text, encoding="utf-8")
    mark_revision()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
