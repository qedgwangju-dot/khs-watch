#!/usr/bin/env python3
from __future__ import annotations

import argparse
import pathlib
import re

# Longest/specific phrases first. These are visible-text labels only; HTML tags/URLs
# are deliberately excluded from replacement.
TERM_MAP = [
    ("Circle Reserve Fund(BlackRock)", "Circle Reserve Fund(서클 준비금 펀드·블랙록 운용)"),
    ("SOFR(New York Fed)", "SOFR(미 국채 담보 익일물 조달금리) · New York Fed(뉴욕 연방준비은행)"),
    ("TBX(ProShares)", "TBX(미 7~10년 국채 가격 일간 -1배 상품) · ProShares(프로셰어즈)"),
    ("Circle 2Q26 10-Q(SEC)", "Circle 2026년 2분기 10-Q(미국 분기보고서)"),
    ("Senior Manager, Business Development (Payments)", "Senior Manager, Business Development (Payments)(결제 사업개발 시니어 매니저)"),
    ("Circle Reserve Fund", "Circle Reserve Fund(서클 준비금 펀드)"),
    ("Samsung Business Insights", "Samsung Business Insights(삼성 비즈니스 인사이트)"),
    ("Samsung Careers", "Samsung Careers(삼성 채용)"),
    ("Samsung Wallet", "Samsung Wallet(삼성월렛)"),
    ("Galaxy Card", "Galaxy Card(갤럭시 카드)"),
    ("Business Development", "Business Development(사업개발)"),
    ("Yahoo Finance", "Yahoo Finance(야후 파이낸스)"),
    ("New York Fed", "New York Fed(뉴욕 연방준비은행)"),
    ("ProShares", "ProShares(프로셰어즈)"),
    ("BlackRock", "BlackRock(블랙록)"),
    ("Farside", "Farside(파사이드)"),
    ("River", "River(리버)"),
    ("Stablecoin", "Stablecoin(스테이블코인)"),
    ("stablecoin", "stablecoin(스테이블코인)"),
    ("BNPL", "BNPL(후불결제)"),
    ("fintech", "fintech(핀테크)"),
    ("issuer", "issuer(카드 발급사)"),
    ("go-to-market", "go-to-market(시장 출시)"),
    ("CRCL", "CRCL(서클 주식 티커)"),
    ("USDC", "USDC(서클 달러 스테이블코인)"),
    ("USDXX", "USDXX(서클 준비금 펀드 티커)"),
    ("SOFR", "SOFR(미 국채 담보 익일물 조달금리)"),
    ("TBX", "TBX(미 7~10년 국채 가격 일간 -1배 상품)"),
    ("BTC", "BTC(비트코인)"),
    ("ETF", "ETF(상장지수펀드)"),
    ("NFC", "NFC(근거리무선통신)"),
]

TAG_SPLIT = re.compile(r"(<[^>]+>)")


def koreanize_segment(segment: str) -> str:
    out = segment
    for source, replacement in TERM_MAP:
        # Do not append another Korean gloss when the source is already immediately
        # followed by a parenthetical explanation.
        pattern = re.compile(re.escape(source) + r"(?!\s*\()")
        out = pattern.sub(replacement, out)
    return out


def koreanize_html_visible_text(text: str) -> str:
    parts = TAG_SPLIT.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = koreanize_segment(parts[i])
    return "".join(parts)


def process(path: pathlib.Path) -> None:
    if not path.exists():
        return
    original = path.read_text(encoding="utf-8")
    updated = koreanize_html_visible_text(original)
    path.write_text(updated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    for raw in args.paths:
        process(pathlib.Path(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
