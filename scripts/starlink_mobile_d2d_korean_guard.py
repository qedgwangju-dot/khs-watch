#!/usr/bin/env python3
"""Fail-closed Korean-only Starlink D2D Telegram text with immutable source URLs."""
from __future__ import annotations
from collections import Counter
import pathlib
import re
import sys
from space_launch_translate_local import translate_english_text

HEAD="📡 Starlink Mobile·미국 위성-휴대전화 직접통신 감시"
SOURCE="• 원문: "
TITLE="• 제목: "
MARKER=re.compile(r"^\[(?:거래 계약·승인 대기|기존 주파수 이전과 구분|위성망 승인과 구분|통신사 대응|AST SpaceMobile 연결|경제성·실패 경로|주파수·인허가|위성·FCC|기존 통신사|경쟁 위성기업|지상망·설비투자)\]")
ENG=re.compile(r"[A-Za-z][A-Za-z'-]*")
KR=re.compile(r"[가-힣]")
NUM=re.compile(r"\d[\d,.]*")

def source_urls(text:str)->list[str]:
 out=[]
 for line in text.splitlines():
  if line.startswith(SOURCE):
   url=line[len(SOURCE):].strip()
   if not re.match(r"^https://[a-z0-9.-]+/",url,re.I):
    raise RuntimeError("HTTPS 원문 링크가 아니거나 호스트 누락")
   out.append(url)
 return out

def title_lines(text:str)->list[str]:
 return [s for s in text.splitlines() if s.startswith(TITLE)]

def tags(text:str)->list[str]:
 return [s for s in text.splitlines() if MARKER.match(s)]

def koreanize(text:str,translate=translate_english_text)->str:
 lines=[]
 for line in text.splitlines():
  if line.startswith(TITLE):
   body=line[len(TITLE):]
   if len(ENG.findall(body))>=4 and not KR.search(body):
    body=translate(body).strip()
   line=TITLE+body
  lines.append(line)
 return "\n".join(lines).rstrip()+"\n"

def validate(original:str,result:str)->None:
 if not original.startswith(HEAD) or not result.startswith(HEAD):
  raise RuntimeError("정확한 감시 제목 누락")
 if tags(original)!=tags(result):
  raise RuntimeError("사건 범주 또는 제목 변경")
 if source_urls(original)!=source_urls(result):
  raise RuntimeError("원문 URL 변경/누락/순서 변경")
 left=title_lines(original)
 right=title_lines(result)
 if len(left)!=len(right):
  raise RuntimeError("기사 제목 개수 변경")
 for before,after in zip(left,right):
  if len(ENG.findall(after[len(TITLE):]))>=4 and not KR.search(after):
   raise RuntimeError("영문 제목 번역되지 않음")
  if Counter(NUM.findall(before))!=Counter(NUM.findall(after)):
   raise RuntimeError("기사 제목 숫자가 번역 과정에서 변경됨")
 if chr(96)*3 in result or "__SOURCE_URL" in result or "<script" in result:
  raise RuntimeError("차단해야 할 텍스트 형식")
 if len(result.strip())<30:
  raise RuntimeError("비정상적으로 짧은 알림")

def self_test()->int:
 baseline=(HEAD+"\n기준: 2026-10-09 17:00 KST\n"
   "[거래 계약·승인 대기]\n• 800MHz 면허 이전은 아직 FCC 승인 대기\n"
   "• 원문: https://graingp.com/press?a=1&b=2\n")
 validate(baseline,koreanize(baseline))
 orig=(HEAD+"\n[주파수·인허가] Grain→SpaceX 800MHz\n"
   "• 제목: SpaceX agrees to acquire Grain 800 MHz spectrum licenses\n"
   "• 원문: https://news.google.com/rss/articles/abc123?a=1&b=2\n")
 trans=(HEAD+"\n[주파수·인허가] Grain→SpaceX 800MHz\n"
   "• 제목: SpaceX, Grain의 800 MHz 주파수 면허 인수에 합의\n"
   "• 원문: https://news.google.com/rss/articles/abc123?a=1&b=2\n")
 validate(orig,trans)
 for reason,bad in (("english",orig),("number",trans.replace("800 MHz","900 MHz")),
             ("url",trans.replace("abc123","other")),
             ("tag",trans.replace("[주파수·인허가]","[다른주제]"))):
  try:validate(orig,bad)
  except RuntimeError:pass
  else:raise AssertionError("차단 실패: "+reason)
 print("starlink_mobile_d2d_korean_guard_self_test=ok")
 return 0

def main()->int:
 if len(sys.argv)==2 and sys.argv[1]=="--self-test":return self_test()
 if len(sys.argv)!=3:
  print("usage: starlink_mobile_d2d_korean_guard.py INPUT OUTPUT | --self-test",file=sys.stderr)
  return 2
 src=pathlib.Path(sys.argv[1])
 dest=pathlib.Path(sys.argv[2])
 original=src.read_text(encoding="utf-8")
 result=koreanize(original)
 validate(original,result)
 dest.write_text(result,encoding="utf-8")
 print("starlink_mobile_d2d_korean_guard=passed")
 return 0

if __name__=="__main__":
 raise SystemExit(main())
