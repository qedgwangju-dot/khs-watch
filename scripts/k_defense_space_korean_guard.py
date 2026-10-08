#!/usr/bin/env python3
"""Translate English titles only, while preserving URLs and source data exactly."""
from __future__ import annotations

import pathlib
import re
import sys

from space_launch_translate_local import translate_english_text

HANGUL=re.compile(r"[가-힣]")
WORDS=re.compile(r"[A-Za-z]+")
SOURCE_PREFIX="• 원문: "
TITLE_PREFIX="• 제목: "
EXACT_TAGS=("[조직·정책]","[정찰위성]","[군 위성통신]","[전력지원]","[우주감시·인증]")

def normalize_report(original:str)->str:
    lines=[]
    for line in original.splitlines():
        if line.startswith(TITLE_PREFIX):
            title=line[len(TITLE_PREFIX):].strip()
            if len(WORDS.findall(title))>=4 and not HANGUL.search(title):
                title=translate_english_text(title).strip()
                if not HANGUL.search(title):
                    raise RuntimeError("영문 기사 제목 번역 실패: 영어 알림 차단")
            line=TITLE_PREFIX+title
        lines.append(line)
    return "\n".join(lines).rstrip()+"\n"

def urls(text:str)->list[str]:
    return [s[len(SOURCE_PREFIX):].strip()
            for s in text.splitlines() if s.startswith(SOURCE_PREFIX)]

def taglines(text:str)->list[str]:
    return [s for s in text.splitlines() if s.startswith(EXACT_TAGS)]

def validate(original:str,after:str)->None:
    if not after.startswith("🛰️ 국내 국방우주·전력지원체계 웹감시"):
        raise RuntimeError("알림 제목 불일치")
    if urls(original)!=urls(after):
        raise RuntimeError("원문 링크 변형·누락")
    if taglines(original)!=taglines(after):
        raise RuntimeError("주제·정책 분류 누락")
    if len([s for s in after.splitlines() if s.startswith(TITLE_PREFIX)]) != \
       len([s for s in original.splitlines() if s.startswith(TITLE_PREFIX)]):
        raise RuntimeError("기사 제목 개수 불일치")
    for line in after.splitlines():
        if line.startswith(TITLE_PREFIX):
            title=line[len(TITLE_PREFIX):]
            if len(WORDS.findall(title))>=4 and not HANGUL.search(title):
                raise RuntimeError("영문 기사 제목이 번역되지 않음")
    if any(x in after for x in ("<script", "</script", "__SOURCE_URL")):
        raise RuntimeError("링크 또는 문구 형식 오류")

def test()->int:
    original=("🛰️ 국내 국방우주·전력지원체계 웹감시\n"
        "기준: 2026-10-08 15:00 KST\n\n"
        "[정찰위성] 군 정찰위성\n"
        "• 제목: New Defence Satellite Program Wins Another Contract - Reuters\n"
        "• 확인 수준: 독립된 복수 보도 | 출처: Reuters\n"
        "• 원문: https://example.com/article?a=1&b=2\n")
    translated=("🛰️ 국내 국방우주·전력지원체계 웹감시\n"
        "기준: 2026-10-08 15:00 KST\n\n"
        "[정찰위성] 군 정찰위성\n"
        "• 제목: 새로운 군 정찰위성 사업이 추가 계약을 확보 - Reuters\n"
        "• 확인 수준: 독립된 복수 보도 | 출처: Reuters\n"
        "• 원문: https://example.com/article?a=1&b=2\n")
    validate(original,translated)
    try:
        validate(original,original)
    except RuntimeError:
        pass
    else:
        raise AssertionError("영문 제목 차단 실패")
    baseline=("🛰️ 국내 국방우주·전력지원체계 웹감시\n"
       "[정책 기준선] 국방부는 우주전략사령부 단계적 창설 방침\n"
       "• 원문: https://www.mnd.go.kr/mnd/497/subview.do\n")
    validate(baseline,normalize_report(baseline))
    print("k_defense_space_korean_guard_self_test=ok")
    return 0

def main()->int:
    if len(sys.argv)==2 and sys.argv[1]=="--self-test":
        return test()
    if len(sys.argv)!=3:
        print("usage: k_defense_space_korean_guard.py INPUT OUTPUT | --self-test",file=sys.stderr)
        return 2
    source=pathlib.Path(sys.argv[1])
    target=pathlib.Path(sys.argv[2])
    original=source.read_text(encoding="utf-8")
    translated=normalize_report(original)
    validate(original,translated)
    target.write_text(translated,encoding="utf-8")
    print("k_defense_space_korean_guard=passed")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
