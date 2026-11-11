#!/usr/bin/env python3
"""Starlink Mobile / US direct-to-device competition: fail-closed Telegram watch.

This watcher keeps the 2026-07 T-Mobile->Grain 800 MHz FCC approval separate
from the still-pending 2026-10 Grain->SpaceX license assignment. News RSS is
discovery, not a regulatory docket or proof of a completed acquisition.
"""
from __future__ import annotations
import datetime as dt
import email.utils
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/starlink_mobile_d2d_watch_state.json"
PENDING=ROOT/"out/starlink_mobile_d2d_watch_pending.json"
ALERT=ROOT/"out/starlink_mobile_d2d_watch_telegram.txt"
SUMMARY=ROOT/"out/starlink_mobile_d2d_watch_status.md"
NOW=dt.datetime.now(dt.timezone.utc)
KST=ZoneInfo("Asia/Seoul")
HEADER="📡 Starlink Mobile·미국 위성-휴대전화 직접통신 감시"
RECENT=dt.timedelta(hours=84)
MAX_ITEMS=4
AGENT="Mozilla/5.0 (compatible; khs-starlink-mobile-watch/1.0)"
SOURCES=(
 ("SpaceX 공식 발표","https://www.spacex.com/updates/starship-moon-announcement",("BUILDING THE WORLD","800 MHz","14 megahertz")),
 ("Grain Management 매각 공식 발표","https://graingp.com/grain-management-announces-definitive-agreement-to-sell-nationwide-800-mhz-spectrum-portfolio-to-spacex/",("SpaceX","800 MHz","FCC approval")),
 ("Grain Management 배포 보도자료","https://www.prnewswire.com/news-releases/grain-management-announces-definitive-agreement-to-sell-nationwide-800-mhz-spectrum-portfolio-to-spacex-302902974.html",("SpaceX","800 MHz","FCC approval")),
 ("AT&T·T-Mobile·Verizon 합작법인 공식 발표","https://about.att.com/story/2026/jv-help-end-dead-zones.html",("October 01, 2026","AT&T","Verizon")),
 ("T-Mobile 주파수 매각 공식 발표","https://www.t-mobile.com/news/business/t-mobile-completes-sale-of-800-mhz-spectrum-portfolio-to-grain-management",("Grain","800","2026")),
 ("AT&T·AST SpaceMobile 상업계약 공식 발표","https://about.att.com/story/2024/ast-spacemobile-commercial-agreement.html",("AST SpaceMobile","2030")),
 ("FCC 2026년 10월 D2D 별도 승인 DA-26-1078","https://docs.fcc.gov/public/attachments/DA-26-1078A1.txt",("15,000","SpaceX")),
 ("FCC D2D 공식 결정문 안내","https://www.fcc.gov/document/spacex-approved-ngso-mss-system-direct-device-services",("SpaceX","direct-to-device")),
 ("NASA Falcon 9·Dragon Crew-15~17 확정 계약","https://www.nasa.gov/missions/station/commercial-crew/nasa-awards-spacex-three-crew-flights-to-space-station/",("946 million","Crew-15","2030")),
 ("SpaceX Falcon 9 페어링 공식 제원","https://www.spacex.com/vehicles/falcon-9/fairing",("5.2","13.1")),
 ("Starlink 휴대전화 직접통신 공식 발사체 경로","https://www.starlink.com/bs/business/direct-to-cell",("Falcon 9","Starship")),
 ("AT&T 배당락·주당 배당금 공식 발표","https://about.att.com/story/2026/november-stock-dividend.html",("0.2775","Oct. 12, 2026")),
 ("Verizon 2026년 10월 9일 배당락 공식 내역","https://www.verizon.com/about/investors/dividend-history",("10/09/2026","0.7075")),
 ("퀄컴 Starlink Mobile 5G 계약 공식 발표","https://www.qualcomm.com/news/releases/2026/11/spacex-selects-qualcomm-to-accelerate-starlink-mobile-s-nationwi",("SpaceX","QRU100","QDU100","2027")),
 ("AT&T·AST 지상망-위성망 전환 시험 공식 발표","https://about.att.com/story/2026/att-ast-spacemobile-engineering-connected-world.html",("AST SpaceMobile","Ericsson","Nokia","October 21, 2026")),
 ("글로벌스타 아마존 인수 종결 대기 공식 발표","https://investors.globalstar.com/news-releases/news-release-details/globalstar-announces-third-quarter-2026-financial-results",("Amazon","2027","pending transaction")),
 ("퀄컴 공식 뉴스룸 계약 공지","https://www.qualcomm.com/news/releases",("SpaceX Selects Qualcomm","Nov 4, 2026")),
 ("퀄컴 공식 기술 홈페이지 계약 공지","https://docs.qualcomm.com/nav",("SpaceX selects Qualcomm","Starlink Mobile")),
 ("퀄컴 직접 발행 BusinessWire 보도자료","https://www.businesswire.com/news/home/20261104680757/en/",("Qualcomm Technologies","SpaceX","QRU100","QDU100","2027")),
 ("퀄컴 보도자료 Nasdaq 합법 재게시","https://www.nasdaq.com/press-release/spacex-selects-qualcomm-accelerate-starlink-mobiles-nationwide-5g-network-2026-11-04",("Source: Qualcomm","SpaceX","QRU100","QDU100","2027")),
 ("퀄컴 보도자료 Yahoo BusinessWire 재게시","https://ca.finance.yahoo.com/news/spacex-selects-qualcomm-accelerate-starlink-133500564.html",("Business Wire","SpaceX","QRU100","QDU100","2027")),
 ("아마존 레오 5105기 D2D 신청 공식 안내","https://www.aboutamazon.com/news/amazon-leo/amazon-leo-direct-to-device-satellite-service-explained",("5,105","FCC","2028")),
 ("라쿠텐·AST 합작법인 공식 발표","https://global.rakuten.com/corp/news/press/2026/1109_01.html",("Rakuten AST","148 billion","2029","51%","49%")),
 ("라쿠텐·AST 합작법인 미국 SEC 첨부 공시","https://www.sec.gov/Archives/edgar/data/1780312/000149315226050865/ex99-1.htm",("Rakuten AST","148","2029","51%","49%")),
)
FCC_JULY="https://docs.fcc.gov/public/attachments/DA-26-653A1.pdf"
FCC_JAN="https://docs.fcc.gov/public/attachments/DOC-417881A1.pdf"
OFFICIAL_BASE=(
 ("[거래 계약·승인 대기]","SpaceX와 Grain Management가 전국 단위 800MHz 면허 묶음(시장별 최대 14MHz의 쌍방향 주파수)을 인수하는 계약을 2026년 10월 8일 발표했습니다. Grain→SpaceX 이전은 FCC 승인 대기이며 거래 완료가 아닙니다.","https://graingp.com/grain-management-announces-definitive-agreement-to-sell-nationwide-800-mhz-spectrum-portfolio-to-spacex/"),
 ("[기존 주파수 이전과 구분]","FCC가 2026년 7월 1일 승인한 거래는 T-Mobile→Grain 800MHz 이전 및 역방향 600MHz 교환입니다. 이번 Grain→SpaceX 거래에 그 승인을 적용하지 않습니다.",FCC_JULY),
 ("[위성망 승인과 구분]","FCC 2026년 1월 발표는 Gen2 위성 7,500기 추가 승인(총 15,000기)입니다. 위성망 승인과 800MHz 면허 이전 승인을 합쳐 해석하지 않습니다.",FCC_JAN),
 ("[10월 신규 휴대전화 직접통신 위성망]","FCC는 2026년 10월 6일 DA-26-1078로 별도의 휴대전화 직접통신 위성망 최대 1만5,000기(고도 약 326~335km)를 조건부 승인했습니다. 이는 1월의 Gen2 광대역 승인과 별도이고, 800MHz Grain→SpaceX 면허 이전 승인이 아닙니다.","https://docs.fcc.gov/public/attachments/DA-26-1078A1.pdf"),
 ("[통신사 대응]","AT&T·T-Mobile·Verizon의 위성-휴대전화 직접통신 합작법인은 2026년 10월 1일 출범을 발표했습니다. 3사는 기존 위성통신 협력계약을 유지할 수 있습니다.","https://about.att.com/story/2026/jv-help-end-dead-zones.html"),
 ("[AST SpaceMobile 연결]","AST SpaceMobile(ASTS)은 AT&T와 2030년까지 이어지는 상업계약이 있고 Verizon과도 상업계약을 발표했습니다. 경쟁사 신사업 진입이 이 기존 계약의 즉시 해지를 의미하지 않습니다.","https://about.att.com/story/2024/ast-spacemobile-commercial-agreement.html"),
)
TRADE_PRICE_NOTE="SpaceX-Grain 거래금액: 당사자 공식 발표에서 미공개. 외신 추정액을 확정 계약금으로 사용하지 않습니다."
QUALCOMM_AGREEMENT_KEY="ground:starlink_qualcomm_dragonwing:agreement:20261104"
AST_HANDOFF_KEY="interoperability:att_ast:handoff_test:20261021"
RAKUTEN_AST_JV_KEY="venture:rakuten_ast:jv_agreement:20261106"
# These two keys were recorded after a *single* four-part Telegram delivery
# (2026-11-12 03:46 KST, messages 196-199). Keep them for audit/history.
RAKUTEN_AST_OLD_KEYS=("asts:supply:705f6e169ba906",
                      "asts:supply:1336bf5717e9a5")
RAKUTEN_AST_ORIGINAL="https://global.rakuten.com/corp/news/press/2026/1109_01.html"
RAKUTEN_AST_SEC="https://www.sec.gov/Archives/edgar/data/1780312/000149315226050865/ex99-1.htm"
QUALCOMM_PRIMARY="퀄컴 Starlink Mobile 5G 계약 공식 발표"
AST_HANDOFF_PRIMARY="AT&T·AST 지상망-위성망 전환 시험 공식 발표"
QUALCOMM_RELEASE_URL="https://www.qualcomm.com/news/releases/2026/11/spacex-selects-qualcomm-to-accelerate-starlink-mobile-s-nationwi"
AST_HANDOFF_RELEASE_URL="https://about.att.com/story/2026/att-ast-spacemobile-engineering-connected-world.html"

def official_qualcomm_agreement_notice(source_note:str="회사 직접 발표 확인")->str:
 return "\n".join((
  "[지상망·설비투자] 지난 공식 계약 누락 보완: SpaceX·퀄컴",
  "• 자료 확인 경로: "+source_note+". 다른 언론이 같은 퀄컴 보도자료를 재전송한 것은 독립된 계약 두 건이 아닙니다.",
  "• 발표: 2026년 11월 4일. Starlink Mobile 미국 지상 5G 기지국에 Qualcomm Dragonwing QRU100 무선장치 처리 플랫폼·QDU100 분산장치 플랫폼 및 1계층 소프트웨어를 공급하는 다년 계약 발표.",
  "• 규격·일정: 64T64R 다중안테나 체계. 2027년부터 미국 전국망 구축을 시작할 계획이며 수년에 걸친 수만 개 기지국은 목표 규모이지 설치 완료 물량이 아닙니다.",
  "• 계약금액·단가·확정 설치 대수: 미공개. 기지국 부지 8만 곳 이용권 확보 협상은 별개이며 확정 부지 매입·장비 발주와 혼동하지 않습니다.",
  "• 국내 공급망: 케이엠더블유·에치에프알·쏠리드·오이솔루션·RFHIC는 유진투자증권이 거론한 후보로, 이번 계약의 확정 공급사가 아닙니다.",
  "• 먼저 볼 지표: SpaceX·퀄컴의 실제 장비 발주·기지국 설치·가동 수, 국내 업체 고객 승인·계약 공시, 2027년 구축 개시.",
  "• 원문: "+QUALCOMM_RELEASE_URL,
  "• 원문: https://www.reuters.com/business/media-telecom/qualcomm-signs-major-5g-infrastructure-deal-with-spacex-starlink-mobile-network-2026-11-04/",
 ))

def official_ast_handoff_notice()->str:
 return "\n".join((
  "[경쟁 위성기업] 지난 고객 검증 누락 보완: AT&T·AST SpaceMobile",
  "• 시험: 2026년 10월 21일 미국 워싱턴주에서 일반 스마트폰의 지상 이동통신망→AST BlueBird 위성망 연결 전환에 성공했다고 11월 2일 공식 발표했습니다.",
  "• 에릭슨은 지상 무선·중심망 및 전환 자동화를, 노키아는 AST 위성 접속·이동성 소프트웨어를 지원했습니다. 전환 시간은 초 단위에서 밀리초 단위로 개선됐다고 발표했습니다.",
  "• 현재 단계: 기술 검증 성공 → 실제 이용자 베타 서비스 준비 → 상용 서비스 목표. 상용 고객·매출·전국 구축 완료를 뜻하지 않습니다.",
  "• 먼저 볼 지표: 베타 서비스 개시·상용 접속 품질·BlueBird 가동 위성·통신사 매출 배분.",
  "• 원문: "+AST_HANDOFF_RELEASE_URL,
  "• 원문: https://www.satellitetoday.com/connectivity/2026/11/03/att-and-ast-spacemobile-demonstrate-handoff-between-cellular-d2d-networks/",
 ))

def newly_verified_official_notices(seen:dict,verified:list[str],initial:bool)->list[tuple[str,str]]:
 if initial:return []
 new=[]
 if QUALCOMM_AGREEMENT_KEY not in seen:
  issuer_sources=(
   QUALCOMM_PRIMARY,"퀄컴 공식 뉴스룸 계약 공지","퀄컴 공식 기술 홈페이지 계약 공지",
   "퀄컴 직접 발행 BusinessWire 보도자료","퀄컴 보도자료 Nasdaq 합법 재게시",
   "퀄컴 보도자료 Yahoo BusinessWire 재게시",
  )
  found=next((name for name in issuer_sources if name in verified),None)
  if found:
   how=("퀄컴 회사 홈페이지 원문" if found==QUALCOMM_PRIMARY else
        "발행사 확인 BusinessWire 배포 원문" if "BusinessWire 보도자료" in found else
        "퀄컴 명의 공식 게시목록·발행 보도자료 합법 재게시(회사 상세 페이지 직접 접근 불가)")
   new.append((QUALCOMM_AGREEMENT_KEY,official_qualcomm_agreement_notice(how)))
 if AST_HANDOFF_KEY not in seen and AST_HANDOFF_PRIMARY in verified:
  new.append((AST_HANDOFF_KEY,official_ast_handoff_notice()))
 return new
# Existing October 2026 facts are a baseline, not novel future FCC approvals.
# In particular, do NOT seed license:grain_spacex_800:fcc_approval or :close.
KNOWN_BASELINE_KEYS=(
 "license:grain_spacex_800:agreement",
 "fcc:DA-26-36:gen2:permission",
 "carriers:att_tmus_vz_joint_venture:venture",
 "asts:att_verizon_contract:supply",
 # 5,105 Amazon Leo D2D satellites were proposed, not approved or launched.
 "competitor:amazon_leo_d2d5105:application",
)
NOISE=re.compile(r"lawsuit|class action|option volume|price target|buy rating|stock split|earnings preview|crypto|celebrity|trump coin|meme stock",re.I)
TRUSTED=(
 "Reuters","Financial Times","The Wall Street Journal","Bloomberg","The Washington Post",
 "The Verge","SpaceNews","Via Satellite","AP News","Associated Press",
 "CNBC","Barron's","MarketWatch","Fierce Network","Fierce Wireless",
 "IEEE","TechCrunch","Reuters","연합뉴스","전자신문","한국경제","서울경제",
 "ZDNet","Axios","Ars Technica",
)
STOP=set(("spacex starlink mobile satellite wireless carriers carrier direct spectrum mhz ghz "
          "fcc us america united states company service phone smartphones device devices "
          "telecom satellites network announces announced say says after with from under "
          "has a an of to its the this will new deal following agreement news stock stocks "
          "million billion how expand expansion launch launches more is for by and ").split())
TOKEN=re.compile(r"[a-z0-9]+")
NO_CHANGE=re.compile(r"what to know|how shares moved|stock plunges|stocks drop|stock slides|"
                     r"why shares|analyst says|investors react|sector outlook|opinion",re.I)

TOPICS={
 "license": {
  "title":"[주파수·인허가] Grain→SpaceX 800MHz",
  "queries":(
    '"SpaceX" "Grain" ("800 MHz" OR spectrum OR FCC) when:4d',
    '"SpaceX" "800 MHz" (approval OR closes OR blocked OR contract) when:4d',
    'site:fcc.gov "SpaceX" "Grain" "800 MHz" when:10d',
  ),
  "meaning":"면허 이전 승인·거래 종결 후 위성망과 지상망 연결, 가입자 전환율·평균판매단가가 실제 매출을 좌우합니다.",
  "risk":"FCC 이전 승인 지연, 지상 기지국 투자와 건물 내부 품질 검증 지연",
  "indicator":"FCC WT 사건번호·면허 양도 승인·거래 종결 공시·실내 통화 품질",
 },
 "fcc": {
  "title":"[위성·FCC] Gen2·2GHz 직접통신",
  "queries":(
    '"SpaceX" ("FCC" OR authorization) ("satellites" OR "2 GHz") when:4d',
    '"Starlink Mobile" (Gen2 OR 2GHz OR FCC OR capacity) when:4d',
    '"SpaceX" ("DA-26-1078" OR "S00735" OR "25-340") when:14d',
    '"Starlink Mobile" ("15,000" OR D2D) (approval OR authorization) when:7d',
    'site:fcc.gov "SpaceX" "D2D" "25-340" when:14d',
    '"SpaceX" "FCC" ("October 29" OR "Oct 29") ("D2D" OR spectrum) when:30d',
    '"Starlink" "FCC" ("25 MHz" OR "482 MHz") ("vote" OR "rules") when:30d',
  ),
  "meaning":"허가된 위성 기수와 실제 운용 기수·단말 호환성은 다릅니다. 상용 가입자와 단말당 트래픽을 확인합니다.",
  "risk":"발사·주파수 간섭·위성 용량·단말 호환성과 통신품질 인증 지연",
  "indicator":"FCC 허가 범위·실제 발사/가동 기수·휴대전화 속도·전파 간섭",
 },
 "carriers": {
  "title":"[기존 통신사] AT&T·T-Mobile·Verizon 합작법인",
  "queries":(
    '"AT&T" "Verizon" "T-Mobile" (satellite OR joint venture OR direct to device) when:4d',
    '"satellite joint venture" (Paul Roth OR AT&T OR Verizon) when:4d',
  ),
  "meaning":"합작법인 지분투자·주파수 공동 활용과 기존 가입자 유지, 위성망 도매·소매 매출을 구분합니다.",
  "risk":"경쟁법·주파수 공유 규제, 각 회사 기존 위성 협력사와의 중복 투자",
  "indicator":"법인 투자액·신규 계약 주체·가입자 해지율·월 가입자당 매출",
 },
 "asts": {
  "title":"[경쟁 위성기업] AST SpaceMobile(ASTS)",
  "queries":(
    '"AST SpaceMobile" (AT&T OR Verizon OR satellite OR commercial) when:4d',
    '"AST SpaceMobile" (SpaceX OR Starlink OR FCC OR BlueBird) when:4d',
  ),
  "meaning":"기존 AT&T·Verizon 계약의 실제 사용량·도매수입과 BlueBird 상용서비스 가동 시점을 구분합니다.",
  "risk":"위성 발사·안테나 전력·스펙트럼 상호운용성·서비스 품질 인증 지연",
  "indicator":"가동 BlueBird 기수·상용 가입자당 사용량·인식 매출·계약 연장",
 },
 "rakuten_ast": {
  "title":"[일본 위성직접통신] 라쿠텐·AST 합작법인",
  "queries":(
    '"Rakuten AST" ("joint venture" OR incorporated OR grant OR satellites OR service) when:7d',
    '"Rakuten" "AST SpaceMobile" (J-LEO OR contract OR satellite OR funding) when:7d',
    '라쿠텐 AST 스페이스모바일 (합작법인 OR 보조금 OR 위성 OR 상용화) when:7d',
  ),
  "meaning":"합작 합의와 법인 설립·정부지원금 수령·실제 위성 발주·2029년 국내망 운용 개시를 분리합니다.",
  "risk":"자금 교부·위성 제조·일본 무선 허가·발사 일정과 서비스 인증 지연",
  "indicator":"법인 등록·지원금 실제 수령·위성 공급계약 금액·발사/운용 위성 수·2029년 3월 서비스 개시",
 },
 "ground": {
  "title":"[지상망·설비투자] 기지국·철탑·전송망",
  "queries":(
    '"SpaceX" ("cell towers" OR "base stations" OR terrestrial OR fiber) when:4d',
    '"Starlink Mobile" (tower lease OR ground infrastructure OR cellular infrastructure) when:4d',
    '"SpaceX" ("80,000" OR "80000") ("cell sites" OR towers OR wireless) when:20d',
    '"SpaceX" ("Crown Castle" OR "American Tower") (leases OR sites OR negotiations) when:14d',
  ),
  "meaning":"실제 기지국 임차·안테나·광섬유 전송망·관제 계약이 나와야 철탑 및 장비 업체 매출로 연결됩니다.",
  "risk":"장소·송전·임차 비용, 통신 음영지역과 건물 실내 품질 개선 속도",
  "indicator":"계약 철탑 수·기지국 개통 수·가구당 평균판매단가·설비투자액",
 },
 "mobile_entry": {
  "title":"[Starlink Mobile·시장 진입] 부스트모바일·지상망 이용",
  "queries":(
    '"SpaceX" "Boost Mobile" (talks OR buy OR acquisition OR network) when:6d',
    '"SpaceX" "EchoStar" ("Boost Mobile" OR "MVNO" OR "network access") when:6d',
  ),
  "meaning":"부스트모바일 인수 협상과 AT&T·T-Mobile 지상망 이용권을 구분합니다. 인수만으로 기존 망 이용계약이 자동 승계되지는 않습니다.",
  "risk":"기존 망 제공 사업자의 사전 동의·인수 조건·고객 이탈·통합 비용",
  "indicator":"인수계약 서명·AT&T/T-Mobile 동의·망 이용계약·인수 종결·가입자 전환",
 },
 "qualcomm_5g": {
  "title":"[지상망·설비투자] Starlink Mobile·퀄컴 지상 5G",
  "queries":(
    '"SpaceX" "Qualcomm" ("Dragonwing" OR "QRU100" OR "QDU100") when:14d',
    '"Starlink Mobile" ("Qualcomm" OR "Dragonwing") ("5G" OR "base station") when:14d',
    '"SpaceX" "Qualcomm" (site deployments OR activated OR operational) when:7d',
  ),
  "meaning":"확정 칩·기초 소프트웨어 공급과 실제 기지국 설치·가동을 분리합니다. 국내 장비사는 고객 검증·계약 전까지 후보입니다.",
  "risk":"철탑 이용권·전력·전송망·장비 통합 지연과 비중국 공급망 경쟁, 2027년 계획의 이행 불확실성",
  "indicator":"2027년 설치·개통된 실제 기지국 수, 장비 납품·고객 승인·국내 공급사 수주",
 },
 "asts_handoff": {
  "title":"[경쟁 위성기업] AT&T·AST 지상망/위성망 연결 전환",
  "queries":(
    '"AST SpaceMobile" "AT&T" ("handoff" OR "handover" OR "beta") when:14d',
    '"AST SpaceMobile" "Ericsson" "Nokia" (handoff OR satellite) when:14d',
    '"AT&T" "AST SpaceMobile" (commercial launch OR beta service) when:7d',
  ),
  "meaning":"연결 전환 시험 성공과 실제 이용자 베타·상용 서비스를 분리해 상용 매출 전환을 감시합니다.",
  "risk":"위성 운용·전파 간섭·연결 전환 실패와 전국 상용화 지연",
  "indicator":"베타 서비스 개시·실사용자 연결 유지·상용 접속·계약 매출",
 },
 "korean_vendor": {
  "title":"[지상망·설비투자] 국내 통신장비의 Starlink 고객 공급",
  "queries":(
    '스페이스X 스타링크 (케이엠더블유 OR 에치에프알 OR 쏠리드 OR 오이솔루션 OR RFHIC) (납품 OR 수주 OR 고객 검증) when:7d',
    '"Starlink Mobile" ("KMW" OR "RFHIC" OR "HFR" OR "OE Solutions") (contract OR supplier OR qualification) when:7d',
  ),
  "meaning":"증권사 공급망 후보와 실제 SpaceX·퀄컴 고객 승인·수주·납품을 구분합니다.",
  "risk":"실제 고객명 비공개, 대형 무선장비 경쟁사·규제, 수주 없이 주가만 먼저 반응할 위험",
  "indicator":"공급사 공시·고객사 납품 확인·제품 모델·계약금액·실제 출하",
 },
 "amazon_leo": {
  "title":"[경쟁사·FCC] 아마존 레오·글로벌스타 위성직접통신",
  "queries":(
    '"Amazon Leo" "Globalstar" (FCC OR acquisition OR spectrum OR closes) when:14d',
    '"Amazon" "Globalstar" ("25 MHz" OR "transfer approval" OR "closing") when:14d',
    '아마존 글로벌스타 FCC (승인 OR 인수 OR 주파수) when:14d',
    '"Amazon Leo" ("5,105" OR "5105") ("D2D" OR "direct-to-device") FCC when:14d',
  ),
  "meaning":"글로벌스타 인수 관련 FCC 면허이전 승인과 거래 종결·위성직접통신 상용화를 분리합니다.",
  "risk":"다른 국가 승인·거래 종결 조건·시스템 허가·위성 발사 미완료",
  "indicator":"FCC 인수 관련 원문·아마존/글로벌스타 종결 발표·별도 D2D 승인·실제 서비스",
 },
}
LABELS={
 "agreement":"계약 발표(규제승인·거래 종결 미확인)",
 "fcc_approval":"FCC가 해당 800MHz 이전을 승인했다는 보도(공식 결정문 직접 확인 전 미확정)",
 "close":"해당 800MHz 거래 종결 보도(공시·당사자 원문 직접 확인 전 미확정)",
 "deny":"해당 800MHz 승인 거부·지연 보도(결정문 직접 확인 전 미확정)",
 "permission":"별도의 위성망·2GHz FCC 승인·조정 보도(800MHz 매각 승인과 다름)",
 "proposal":"FCC 규제·주파수 정책 제안 또는 심의 예정 보도(최종 승인 아님)",
 "deny":"FCC 거부·지연·연기 보도(공식 원문 확인 전 잠정)",
 "new_service":"상용서비스·위성망 추가 구축 보도(실제 개통·고객 수 별도 확인)",
 "venture":"합작법인 확대·협력 발표(신규 매출과 다름)",
 "supply":"위성 공급·계약·발사 보도(검수 매출과 다름)",
 "jv_agreement":"합작법인 설립에 합의(법인 설립 완료·지원금 수령과 다름)",
 "jv_established":"법인 설립 완료 보도(등기·발표 원문 별도 확인)",
 "grant_disbursed":"정부지원금 실제 교부 보도(총 지원 한도와 다름)",
 "satellites_delivered":"합작법인 대상 위성 납품 보도(계약/검수 원문 별도 확인)",
 "service_launched":"일본 내 상용 위성통신 개시 보도(실제 가입자·매출 별도 확인)",
 "rollout_report":"Starlink 지상 기지국 실제 개통 보도(공식 설치·가동 수 별도 확인)",
 "handoff_test":"지상망·위성망 전환 시험 보도(상용 서비스 아님)",
 "beta_report":"실사용자 베타 서비스 개시 보도(공식 개시·규모 확인 전)",
 "commercial_report":"상용 서비스 개시 보도(공식 계약·매출 확인 전)",
 "supplier_report":"국내 통신장비 납품·고객 검증 보도(양사 공식 확인 전)",
 "tower":"지상망·철탑 계약/투자 보도(규모 확인 필요)",
 "site_talks":"기지국 부지 이용권 협상 보도(8만 곳 목표·미계약)",
 "site_agreement":"기지국 부지 이용계약 체결 보도(계약 원문 확인 전)",
 "boost_talks":"부스트모바일 인수 또는 망 이용 협상 보도(미체결)",
 "boost_agreement":"부스트모바일 인수·망 이용 계약 보도(계약 원문 확인 전)",
 "boost_close":"부스트모바일 인수 종결 보도(공식 종결 확인 전)",
 "transfer_approved":"아마존의 글로벌스타 인수 관련 FCC 이전 승인 보도(거래 종결 아님)",
 "acquisition_agreement":"아마존·글로벌스타 인수 계약 보도(종결과 다름)",
 "acquisition_close":"아마존·글로벌스타 인수 종결 보도(당사자 확인 전)",
 "d2d_application":"아마존 5,105기 위성직접통신 인허가 신청(위성 발사·허가 아님)",
 "d2d_permission_report":"아마존 5,105기 위성직접통신 승인 보도(FCC 결정문 직접 확인 전)",
 "d2d_deployment_report":"아마존 위성직접통신 실제 배치 보도(운용 위성·사업자 원문 확인 전)",
}
MONTHS={"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
        "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}

class HTMLText(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.hide=0
 def handle_starttag(self,tag,attrs):
  if tag in ("script","style","noscript"):self.hide+=1
 def handle_endtag(self,tag):
  if tag in ("script","style","noscript") and self.hide:self.hide-=1
 def handle_data(self,text):
  if not self.hide and text.strip():self.parts.append(text)

def http_read(url:str,attempts:int=2)->bytes:
 if urlsplit(url).scheme!="https":raise ValueError("HTTPS only")
 error=None
 for i in range(attempts):
  req=Request(url,headers={"User-Agent":AGENT,"Accept":"text/html,application/rss+xml,*/*"})
  try:
   with urlopen(req,timeout=20) as response:
    final=urlsplit(response.geturl())
    if final.scheme!="https":raise RuntimeError("unexpected non-HTTPS redirect")
    data=response.read(2500000)
    if not data:raise RuntimeError("empty response")
    return data
  except (HTTPError,URLError,TimeoutError,socket.timeout,RuntimeError) as e:
   error=e
   if isinstance(e,HTTPError) and e.code not in (429,500,502,503,504):break
   if i+1<attempts:time.sleep(2**i)
 raise RuntimeError(f"source unavailable ({type(error).__name__})")

def verified_primary_sources()->tuple[list[str],list[str]]:
 verified=[]
 failed=[]
 for name,url,markers in SOURCES:
  try:
   raw=http_read(url)
   parser=HTMLText()
   parser.feed(raw.decode("utf-8",errors="replace"))
   txt=" ".join(parser.parts)
   txt=html.unescape(re.sub(r"\s+"," ",txt)).casefold()
   if not all(marker.casefold() in txt for marker in markers):
    raise ValueError("required exact company/date/frequency markers absent")
   verified.append(name)
  except Exception as e:
   failed.append(f"{name}: {type(e).__name__}")
 return verified,failed

def distinct_primary_organizations(names:list[str])->set[str]:
 # An issuer's release and its press-distribution mirror are not independent
 # corporate confirmations, even if both URLs are live and parse correctly.
 groups=set()
 for name in names:
  if name.startswith("Grain Management"):groups.add("grain")
  elif name.startswith("SpaceX"):groups.add("spacex")
  elif name.startswith("AT&T"):groups.add("att")
  elif name.startswith("T-Mobile"):groups.add("tmobile")
  elif name.startswith("라쿠텐"):groups.add("rakuten")
  elif name.startswith("AST 합작법인"):groups.add("ast")
  elif name.startswith("퀄컴"):groups.add("qualcomm")
  elif name.startswith("글로벌스타"):groups.add("globalstar")
  elif name.startswith("FCC "):groups.add("fcc")
  elif name.startswith("NASA "):groups.add("nasa")
  elif name.startswith("Starlink "):groups.add("starlink")
  elif name.startswith("SpaceX "):groups.add("spacex")
 return groups

def rss(query:str)->list[dict]:
 locale={"hl":"ko","gl":"KR","ceid":"KR:ko"} if re.search(r"[가-힣]",query) else {"hl":"en","gl":"US","ceid":"US:en"}
 params=urlencode({"q":query,**locale})
 root=ET.fromstring(http_read("https://news.google.com/rss/search?"+params))
 rows=[]
 for e in root.findall(".//item"):
  title=html.unescape(re.sub(r"<[^>]+>"," ",e.findtext("title") or "")).strip()
  url=(e.findtext("link") or "").strip()
  src=e.find("source")
  source=(src.text or "").strip() if src is not None else ""
  if not title or not url.startswith("https://"):continue
  try:
   date=email.utils.parsedate_to_datetime(e.findtext("pubDate") or "")
   if not date.tzinfo:date=date.replace(tzinfo=dt.timezone.utc)
   date=date.astimezone(dt.timezone.utc)
  except Exception:continue
  rows.append({"title":title,"url":url,"publisher":source,"pub":date})
 return rows

def independent_publisher(item:dict)->bool:
 # Google News merely tags publishers. A government-looking RSS source is not
 # direct verification of an FCC proceeding and is excluded from media pairs.
 s=item["publisher"].lower()
 if any(x in s for x in ("fcc","federal communications commission","prnewswire",
                       "business wire","globenewswire","spacex","grain management")):
  return False
 return any(x.lower() in s for x in TRUSTED)

def stem_title(title:str)->str:
 return re.sub(r"\s+[-|]\s+[^-|]{1,60}$","",title).lower().strip()

def rakuten_ast_story(title:str)->bool:
 t=stem_title(title)
 return bool(
  (re.search(r"rakuten|라쿠텐|楽天",t) and
   re.search(r"ast[ -]?spacemobile|ast[ -]?space|ast스페이스|ast 스페이스|\bast\b",t))
  or re.search(r"rakuten[ -]?ast|라쿠텐[ -]?ast",t)
 )

def migrate_rakuten_ast_state(state:dict)->bool:
 seen=state["seen"]
 previous=[seen[k] for k in RAKUTEN_AST_OLD_KEYS if k in seen]
 if previous and RAKUTEN_AST_JV_KEY not in seen:
  # Keep the actual original delivery timestamp; never stamp "now" or
  # pretend a new message was sent during migration.
  seen[RAKUTEN_AST_JV_KEY]=min(previous)
  return True
 return False

def stage(topic:str,title:str)->str|None:
 t=stem_title(title)
 if NOISE.search(t) or NO_CHANGE.search(t):return None
 if topic=="license":
  if not re.search(r"spacex|starlink",t) or not re.search(r"grain|800[\s-]*mhz",t):return None
  if not re.search(r"spectrum|license|800[\s-]*mhz|grain",t):return None
  # This is NOT the old T-Mobile -> Grain deal.
  if re.search(r"t-mobile (?:sells|sold|transfers?|swaps?|completes).{0,60}grain",t):return None
  if re.search(r"fcc (?:approves?|approved|authori[sz]es?|grants?)",t):
   if re.search(r"(?:grain|800[\s-]*mhz).{0,55}(?:license|transfer|sale|acquisit|assign|deal)|"
                r"(?:license|transfer|sale|acquisit|assign|deal).{0,55}(?:grain|800[\s-]*mhz)",t):
    if not re.search(r"(15,?000|7500|7,?500|gen2).*satellit",t):
     return "fcc_approval"
  if re.search(r"reject|denied|block|investigation|delay",t):return "deny"
  if re.search(r"complet(?:e|ed|ion)|clos(?:e|ed|ing) (?:the )?(?:deal|transaction|purchase)|"
               r"finaliz(?:e|ed)|sale closed",t):
   return "close"
  if re.search(r"acquir|buy|bought|purchas|agreement|deal|signs",t):return "agreement"
  return None
 if topic=="fcc":
  if not re.search(r"spacex|starlink",t):return None
  if not re.search(r"fcc|regulator|license|authoriz|2[ -]?ghz|gen2|d2d|direct[- ]to[- ]device|spectrum",t):return None
  # Never report a vote, petition or proposed application as granted.
  if re.search(r"\b(to vote|votes? on|will vote|to consider|considering|"
               r"propos(?:e|es|ed|al)|seeks?|appl(?:ies|ication)|"
               r"file[ds]?|request[sd]?|pending|under review)\b",t) and not re.search(
               r"\b(approv(?:e|ed|es)|authori[sz](?:e|ed|es)|grant(?:s|ed)?|"
               r"clears?|cleared|green light)\b",t):
   return "proposal"
  if re.search(r"\b(reject(?:s|ed)?|den(?:ies|ied|y)|blocks?|"
               r"delay(?:s|ed)?|defer(?:s|red)?)\b",t):
   return "deny"
  if re.search(r"\b(approv(?:e|ed|es)|authori[sz](?:e|ed|es)|"
               r"grant(?:s|ed)?|clears?|cleared)\b",t):
   # "FCC to approve" is not an actual approval.
   if re.search(r"\b(to approve|will approve|plans? to approve|may approve)\b",t):
    return "proposal"
   return "permission"
  if re.search(r"launch(?:ed|es)?|deploy(?:ed|s)?|commercial|test(?:ing)?",t):
   return "new_service"
  return None
 if topic=="carriers":
  if not re.search(r"at&t|verizon|t-mobile",t):return None
  if not re.search(r"joint venture|venture|satellite|d2d|direct.to.device",t):return None
  return "venture"
 if topic=="asts":
  # Rakuten's November 6 agreement is a joint venture, not two new
  # satellite-supply contracts. Route it to its own stable event ID.
  if rakuten_ast_story(t):return None
  # A connectivity handoff is not a new satellite supply agreement.
  if re.search(r"handoff|hand.?over|망 전환|연결 전환",t):return None
  if not re.search(r"ast spacemobile|bluebird|asts",t):return None
  if not re.search(r"contract|deal|satellite|commercial|service|verizon|at&t|launch",t):return None
  return "supply"
 if topic=="rakuten_ast":
  if not rakuten_ast_story(t):return None
  if re.search(r"actual commercial service (?:starts|launches)|service went live|"
               r"begins commercial operation|国内運用開始|상용 서비스 개시",t) and not re.search(
               r"target|plan|will|expected|to begin|予定|목표|예정",t):
   return "service_launched"
  if re.search(r"satellites (?:delivered|handed over)|위성 (?:인도|납품 완료)",t):
   return "satellites_delivered"
  if re.search(r"grant (?:received|disbursed|paid)|subsidy actually paid|"
               r"지원금 (?:수령|지급 완료)|補助金.*交付",t):
   return "grant_disbursed"
  if re.search(r"incorporat(?:ed|ion) completed|company registration completed|"
               r"법인 설립 완료|등기 완료|法人設立完了",t):
   return "jv_established"
  if re.search(r"joint venture|joint-venture|\bjv\b|rakuten ast|"
               r"合弁|합작법인|합작 투자|設立",t):
   return "jv_agreement"
  return None
 if topic=="ground":
  if not re.search(r"spacex|starlink",t) or re.search(r"boost mobile|echostar|globalstar",t):return None
  if re.search(r"80,?000|80\s*thousand",t) and re.search(r"cell sites?|tower sites?|sites? for wireless",t):
   if re.search(r"signs?|signed|secured|executed|agreement concluded",t):return "site_agreement"
   if re.search(r"talks?|negotiat|seek|pursu|access|aim|plan",t):return "site_talks"
  if not re.search(r"tower|terrestrial|fiber|base station|ground",t):return None
  if not re.search(r"deal|lease|contract|invest|capex|construction|build|deploy|plan",t):return None
  return "tower"
 if topic=="mobile_entry":
  if not re.search(r"spacex|starlink",t) or "boost mobile" not in t:return None
  if re.search(r"acquisition complete|acquisition closes|completed purchase|deal closes|transaction closed",t):return "boost_close"
  if re.search(r"signs? (?:a )?definitive|signed agreement|agrees to acquire|acquisition agreement",t):return "boost_agreement"
  if re.search(r"talks?|discuss|negotia|consider|weigh|seek|could buy|access|purchase|acquisition",t):return "boost_talks"
  return None
 if topic=="qualcomm_5g":
  if not re.search(r"spacex|starlink|스페이스x|스타링크",t) or not re.search(r"qualcomm|dragonwing|퀄컴",t):return None
  if not re.search(r"5g|dragonwing|qru100|qdu100|base station|기지국|terrestrial",t):return None
  # Announced build-out is not a live cell-site deployment.
  if re.search(r"sites? (?:went |goes? )?live|activated|now operational|deployed [0-9,]+ sites|기지국.*개통|기지국.*가동",t) and not re.search(r"plans?|aims?|expected|to deploy|will deploy|예정|목표",t):
   return "rollout_report"
  if re.search(r"selects?|selected|signed|agrees?|deal|contract|supply|supplies|공급계약|체결|선정",t):return "agreement"
  return None
 if topic=="asts_handoff":
  if not re.search(r"ast spacemobile|asts|bluebird|스페이스모바일",t) or not re.search(r"at&t|에이티앤티",t):return None
  if re.search(r"beta service|beta launch|베타.*(개시|출시)",t) and not re.search(r"prepar|plan|target|ahead|예정|목표",t):return "beta_report"
  if re.search(r"commercial service (?:begins|starts|launches)|commercial launch confirmed|상용 서비스.*(개시|출시)",t) and not re.search(r"prepar|plan|target|ahead|예정|목표",t):return "commercial_report"
  if re.search(r"handoff|handover|hand-over|연결 전환|망 전환",t):return "handoff_test"
  return None
 if topic=="korean_vendor":
  if not re.search(r"spacex|starlink|스페이스x|스페이스X|스타링크",t):return None
  if not re.search(r"케이엠더블유|에치에프알|쏠리드|오이솔루션|rfhic|\bkmw\b|\bhfr\b|oe solutions",t):return None
  if re.search(r"could|may|potential|opportunit|candidate|benefit|possible|기대|가능성|후보|전망|관심|수혜주",t):return None
  if re.search(r"sign(?:ed|s)?|contract|selected|awarded|supplier|qualified|납품|수주|선정|체결|고객 검증|고객승인",t):return "supplier_report"
  return None
 if topic=="amazon_leo":
  if not re.search(r"amazon|아마존",t):return None
  if re.search(r"5,?105",t) and re.search(r"leo|d2d|direct.to.device|레오",t):
   if re.search(r"deployed|operational|가동|배치 완료",t) and not re.search(r"plan|expected|will deploy|예정|목표",t):return "d2d_deployment_report"
   if re.search(r"fcc.*(approv|authoriz|grant)|(?:approv|authoriz|grant).*fcc|fcc.*승인|승인.*fcc",t) and not re.search(r"requested|application|filed|seeks|신청|요청",t):return "d2d_permission_report"
   if re.search(r"application|filed|filing|request|seek|proposed|신청|제안",t):return "d2d_application"
   return None
  if not re.search(r"globalstar|글로벌스타",t):return None
  if re.search(r"acquisition complete|acquisition closes|deal closes|closed transaction|merger complete|인수 완료|인수 종결",t):return "acquisition_close"
  if re.search(r"fcc|federal communications commission|regulator|연방통신위원회",t) and re.search(r"approv|clears?|clearance|authoriz|consent|grants?|승인",t):
   return "transfer_approved"
  if re.search(r"agrees to acquire|acquisition agreement|purchase agreement|인수 계약 체결",t):return "acquisition_agreement"
  return None

def keywords(title:str)->set[str]:
 s=re.sub(r"(\d+)\s*(mhz|ghz)",r"\1\2",stem_title(title))
 return {w for w in TOKEN.findall(s) if len(w)>=3 and w not in STOP}

def match_articles(a:dict,b:dict,topic:str|None=None,status:str|None=None)->bool:
 if a["publisher"].strip().lower()==b["publisher"].strip().lower():return False
 if abs((a["pub"]-b["pub"]).total_seconds())>72*3600:return False
 if topic in {"mobile_entry","amazon_leo","rakuten_ast"} and status:
  # One press source may generate differently worded English/Korean titles.
  # Compare the same parties and the same transaction stage, never topic alone.
  if stage(topic,a["title"])!=status or stage(topic,b["title"])!=status:return False
  return True
 x,y=keywords(a["title"]),keywords(b["title"])
 common=x&y
 # Shared issuer names and the same event-specific objects, not generic SpaceX.
 return len(common)>=2 and len(common)/max(1,len(x|y))>=0.24

def event_id(category:str,status:str,title:str)->str:
 t=stem_title(title)
 if category=="license":return f"license:grain_spacex_800:{status}"
 if category=="fcc":
  if re.search(r"da[\s-]*26[\s-]*1078|s00735|25[\s-]*340|direct[- ]to[- ]device|d2d|mobile[- ]satellite|direct[- ]to[- ]cell|mobile[\s-]+network",t):
   if re.search(r"15,?000|15k|fifteen thousand",t) or re.search(r"da[\s-]*26[\s-]*1078|s00735",t):
    return f"fcc:DA-26-1078:D2D:{status}"
  if re.search(r"da[\s-]*26[\s-]*36|gen2[\s-]+broadband|additional[\s-]+7,?500",t):
   return f"fcc:DA-26-36:gen2:{status}"
  if re.search(r"2[\s-]*ghz",t):return f"fcc:other_2ghz:{status}"
  # A bare 15,000 is ambiguous: do not cross-deduplicate two separate
  # satellite authorizations merely because both involve 15k spacecraft.
  if re.search(r"15,?000|15k",t):return f"fcc:ambiguous_15000:{status}"
 if category=="carriers" and re.search(r"joint venture|venture",t):
  return f"carriers:att_tmus_vz_joint_venture:{status}"
 if category=="rakuten_ast":
  if status=="jv_agreement":return RAKUTEN_AST_JV_KEY
  # Later milestones are separate from the 2026-11-06 agreement.
  # A new actual payment or delivery may have its own dated release.
  return "venture:rakuten_ast:"+status+":"+hashlib.sha256("|".join(
    sorted(keywords(title))).encode()).hexdigest()[:12]
 if category=="asts" and re.search(r"verizon|at&t",t):
  return f"asts:att_verizon_contract:{status}"
 if category=="ground":
  if re.search(r"80,?000|80\s*thousand",t) and re.search(r"cell site|tower site|wireless",t):
   return f"ground:spacex_80000_sites:{status}"
  if re.search(r"tower|terrestrial",t):
   return f"ground:starlink_terrestrial:{status}"
 if category=="qualcomm_5g":
  if status=="agreement":return QUALCOMM_AGREEMENT_KEY
  return "ground:starlink_qualcomm_dragonwing:"+status+":"+hashlib.sha256(t.encode()).hexdigest()[:14]
 if category=="asts_handoff":
  if status=="handoff_test":return AST_HANDOFF_KEY
  return f"interoperability:att_ast:{status}"
 if category=="korean_vendor":
  vendor=next((ident for ident,pattern in (
   ("kmw",r"케이엠더블유|\bkmw\b"),
   ("hfr",r"에치에프알|\bhfr\b"),
   ("solid",r"쏠리드"),
   ("oe_solutions",r"오이솔루션|oe solutions"),
   ("rfhic",r"rfhic"),
  ) if re.search(pattern,t)), "unknown")
  return f"vendor:starlink:{vendor}:{status}"
 if category=="mobile_entry":return f"mobile:starlink_boost:{status}"
 if category=="amazon_leo":
  if status.startswith("d2d_"):return f"competitor:amazon_leo_d2d5105:{'application' if status=='d2d_application' else status}"
  return f"competitor:amazon_globalstar:{status}"
 # To allow different deployments/contracts, use stable material headwords,
 # without date or publisher-specific wording.
 terms=sorted(keywords(title))
 return f"{category}:{status}:"+hashlib.sha256("|".join(terms).encode()).hexdigest()[:14]

def bootstrap()->str:
 sections=[HEADER, "기준: "+NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST"),
  "최초 1회 정책·사업 기준선입니다. 과거 기사를 새 수주나 승인으로 알리는 것이 아닙니다."]
 for heading,meaning,url in OFFICIAL_BASE:
  sections.append("\n"+heading+"\n• "+meaning+"\n• 원문: "+url)
 sections += [
  "\n[경제성·실패 경로]\n• "+TRADE_PRICE_NOTE,
  "• 위성 직접통신만으로 도심 실내망 구축이 완료되는 것은 아닙니다. 지상 기지국·전송망·요금제·가입자 확보를 따로 추적합니다.",
  "• 먼저 볼 지표: Grain→SpaceX FCC 승인, 실제 기지국·철탑 계약, ASTS 가동률, AT&T·VZ·TMUS 가입자 이탈률.",
  "• 매출 구분: 주파수 매입은 자산취득이며 장비·건설업체 매출과 통신 가입자 반복매출을 혼합하지 않습니다."
 ]
 return "\n".join(sections).strip()+"\n"

FCC_D2D_ORDER_KEY="fcc:DA-26-1078:D2D:permission"
FCC_D2D_OFFICIAL_URL="https://docs.fcc.gov/public/attachments/DA-26-1078A1.pdf"
FCC_JAN_GEN2_URL="https://docs.fcc.gov/public/attachments/DA-26-36A1.pdf"

def regulatory_correction_notice()->str:
 return "\n".join([
  "[신규 규제 승인·중요 정정] Starlink Mobile 위성 1만5,000기",
  "• FCC는 2026년 10월 6일 DA-26-1078, 사건번호 25-340, 호출부호 S00735로 새로운 휴대전화 직접통신 위성망 최대 1만5,000기를 조건부 승인했습니다.",
  "• 승인 궤도: 고도 약 326~335km, 9개 궤도군. 전체가 현재 가동 중이라는 의미는 아닙니다.",
  "• 배치 마감: 2032년 10월 7일까지 절반(7,500기), 2035년 10월 7일까지 전체 1만5,000기. 단순 승인 기수를 가입자 수·매출로 환산하지 않습니다.",
  "• 매우 중요한 구분: 2026년 1월 9일 DA-26-36은 별도의 Gen2 광대역 위성 7,500기 추가 승인(총 1만5,000기)입니다. 10월의 D2D 결정과 같은 사건이 아닙니다.",
  "• 주파수 단계도 별도: 2026년 7월 T-Mobile→Grain 800MHz 이전 승인과 10월 Grain→SpaceX 800MHz 계약은 다릅니다. 후자는 아직 FCC 이전 승인 대기입니다.",
  "• 매출 연결: D2D 위성 발사·망 검증→실제 휴대전화 연결 품질·가입자 유치→위성통신 반복 요금매출. 지상망 기지국 투자는 별도입니다.",
  "• 숨은 역풍: 초저궤도 위성 유지·교체 주기, 2GHz 간섭 조정·인증, 실내 통화 품질, 주파수 거래 종결과 지상망 설비투자 부담.",
  "• 먼저 볼 지표: 2026년 11월 초 이행보증 일정, 실제 위성 발사·가동 수, EchoStar 주파수 이전 2단계, Grain→SpaceX FCC 승인.",
  "• 원문: "+FCC_D2D_OFFICIAL_URL,
  "• 원문: "+FCC_JAN_GEN2_URL,
  "• 원문: https://graingp.com/grain-management-announces-definitive-agreement-to-sell-nationwide-800-mhz-spectrum-portfolio-to-spacex/",
 ])

FACTCHECK_20261011_KEY="factcheck:20261011:carrier_close_falcon9_dragon"
NASA_NEW_CREW_URL="https://www.nasa.gov/missions/station/commercial-crew/nasa-awards-spacex-three-crew-flights-to-space-station/"
SPACEX_FAIRING_URL="https://www.spacex.com/vehicles/falcon-9/fairing"
STARLINK_D2C_URL="https://www.starlink.com/bs/business/direct-to-cell"
US_CARRIER_20261009_URL="https://www.fool.com/coverage/stock-market-today/2026/10/09/stock-market-today-oct-9-at-and-t-slides-on-spacex-spectrum-deal-threat/"

def should_send_historical_factcheck(initial:bool, state:dict, official:list[str])->bool:
 return (not initial
         and FACTCHECK_20261011_KEY not in state.get("seen", {})
         and "NASA Falcon 9·Dragon Crew-15~17 확정 계약" in official
         and "Grain Management 매각 공식 발표" in official)

AT_T_DIVIDEND_URL="https://about.att.com/story/2026/november-stock-dividend.html"
VERIZON_DIVIDEND_URL="https://www.verizon.com/about/investors/dividend-history"
T_DAILY_RAW_URL="https://www.investing.com/equities/at-t-historical-data"
VZ_DAILY_RAW_URL="https://www.investing.com/equities/verizon-communications-historical-data"
TMUS_DAILY_URL="https://stockanalysis.com/stocks/tmus/history/"
DIVIDEND_DISPLAY_CORRECTION_KEY="factcheck:20261011:raw_vs_dividend_adjusted_mobile_telegram"


def daily_price_return(close:float,previous_close:float,ex_dividend:float=0)->tuple[float,float]:
 if close<=0 or previous_close<=0 or ex_dividend<0 or ex_dividend>=previous_close:
  raise ValueError("Invalid market-data input")
 return ((close / previous_close-1)*100,
         (close / (previous_close-ex_dividend)-1)*100)


def price_dividend_display_correction()->str:
  """A compact, natural-width Korean report; eight sources beside their claims.

  Facts and source URLs are unchanged. No manual line wraps or tiny numbered
  Telegram messages. The sending client handles the real device screen width.
  """
  t_raw,t_adj=daily_price_return(22.18,24.87,0.2775)
  vz_raw,vz_adj=daily_price_return(41.65,46.35,0.7075)
  tm_raw,_=daily_price_return(148.58,171.31)
  return "\n".join([
   "[주가 기준 정정] 10월 9일 미국 통신 3사",
   "핵심: 통신 3사 주가는 급락했으나 Starlink Mobile 미국 독자망은 아직 개통 전입니다.",
   "",
   "[주가] 10/9 정규장 · 전일 종가 대비",
   f"AT&T(T) 22.18달러 · {t_raw:+.2f}%  배당락 조정: {t_adj:+.2f}%",
   f"버라이즌(VZ) 41.65달러 · {vz_raw:+.2f}%  배당락 조정: {vz_adj:+.2f}%",
   f"T-Mobile(TMUS) 148.58달러 · {tm_raw:+.2f}%",
   "※ 10/9 배당락: T 주당 0.2775달러, VZ 주당 0.7075달러. 원수익률과 배당 조정 수익률은 서로 다른 비교 기준입니다.",
   "• 원문: "+T_DAILY_RAW_URL,
   "• 원문: "+VZ_DAILY_RAW_URL,
   "• 원문: "+TMUS_DAILY_URL,
   "• 원문: "+AT_T_DIVIDEND_URL,
   "• 원문: "+VERIZON_DIVIDEND_URL,
   "",
   "[사업] 인수계약·위성 허가 ≠ 상용 개통",
   "Grain→SpaceX 800MHz 인수계약 체결, FCC 이전 승인 대기. D2D 1만5,000기는 허가 규모이지 실제 가동 위성 수가 아닙니다.",
   "",
   "[발사] Falcon 9·Starship 병행 경로",
   "Falcon 9 페어링: 외경 5.2m·높이 약 13.1m. 위성 길이 7m만으로 적재 불가 단정 금지(접힌 폭·적재 형상 별도 검증).",
   "Starlink 직접통신은 Falcon 9로 선발사한 뒤 Starship으로 대형화하는 경로입니다. 1만5,000기는 발사 완료량이 아닙니다.",
   "• 원문: "+SPACEX_FAIRING_URL,
   "• 원문: "+STARLINK_D2C_URL,
   "",
   "[NASA] Falcon 9·Dragon 계속 운용",
   "Crew-15~17 추가 3회, 9억4,600만 달러(10/11 환산 약 1조2,685억원). 계약 수행기간 2030년까지로 Falcon 9·Dragon 즉시 퇴역 주장과 양립하지 않습니다.",
   "• 원문: "+NASA_NEW_CREW_URL,
   "",
   "[재평가·역풍] Starship의 원가 우위는 위성당 질량·발사당 기수·재사용 회전시간 검증이 선행되어야 합니다. 열차폐·Raptor·회수 지연은 D2D 배치를 늦출 수 있으나 기존 Falcon 9 계약 전체의 즉시 중단을 뜻하지 않습니다.",
   "[추적 지표] Falcon 9 발사 빈도 · Crew-15~17 이행 · Starship 2단 재사용 · D2D 실제 가동 기수 · Grain→SpaceX FCC 이전 승인",
  ])


def should_send_price_correction(initial:bool,state:dict,official:list[str])->bool:
 return (not initial
         and FACTCHECK_20261011_KEY in state.get("seen",{})
         and DIVIDEND_DISPLAY_CORRECTION_KEY not in state.get("seen",{})
         and "AT&T 배당락·주당 배당금 공식 발표" in official
         and "Verizon 2026년 10월 9일 배당락 공식 내역" in official
         and "NASA Falcon 9·Dragon Crew-15~17 확정 계약" in official)


def user_claims_factcheck()->str:
 # Keep the historical method for compatibility, now with the correct
 # price-return methodology and the compact, fully sourced structure.
 return price_dividend_display_correction()

def render(topic:str,status:str,item:dict,pair:dict)->str:
 if topic=="rakuten_ast":
  if status=="jv_agreement":
   return "\n".join((
    "[합작 합의·설립 예정] 일본 Rakuten AST",
    "■ 2026년 11월 6일 라쿠텐과 AST SpaceMobile이 합작법인 설립에 합의했고, 11월 9일 공동 발표했습니다. 법인 설립은 11월 예정입니다.",
    "■ 지분율은 라쿠텐 51%·AST 49%, 법인 자본금 1억 엔입니다.",
    "■ 일본 J-LEO 사업에서 약 3년에 걸쳐 최대 1,480억 엔 지원 예정입니다. 전액 수령·AST 확정 매출은 아닙니다.",
    "■ AST가 일본 위성직접통신용 위성을 공급하며, 국내 위성망 구축과 운용 개시 목표는 2029년 3월 말입니다.",
    "■ 확인 지표: 실제 법인 등기·정부지원금 교부·위성 발주/납품 금액·실제 발사·운용과 서비스 개시.",
    "• 원문: "+RAKUTEN_AST_ORIGINAL,
    "• 원문: "+RAKUTEN_AST_SEC,
   ))
  meta=TOPICS[topic]
  return "\n".join((
   meta["title"]+" — 후속 단계 보도",
   "■ 현재 상태: "+LABELS[status],
   "■ 제목: "+item["title"],
   "■ 언론 출처: "+item["publisher"]+"·"+pair["publisher"]+
   " / 당사자 공식 원문 추가 확인 전.",
   "■ 기존 11월 6일 합작 합의와 새로운 지원금 수령·위성 인도·서비스 개시는 다른 사건입니다.",
   "■ 확인할 지표: "+meta["indicator"],
   "• 원문: "+item["url"],
   "• 원문: "+RAKUTEN_AST_ORIGINAL,
  ))
 meta=TOPICS[topic]
 timestamp=item["pub"].astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
 lines=[
  meta["title"],
  "상태 | "+LABELS[status],
  "• 제목: "+item["title"],
  "근거 | "+item["publisher"]+"·"+pair["publisher"]+" | "+timestamp,
  "  여러 매체가 동일 최초 보도를 재인용했을 수 있습니다. 협상·승인·계약·종결은 당사자 원문 확인 전까지 확정하지 않습니다.",
  "",
  "매출 | "+meta["meaning"],
  "역풍 | "+meta["risk"],
  "지표 | "+meta["indicator"],
 ]
 if topic=="license":lines.append("금액 | "+TRADE_PRICE_NOTE)
 lines.extend(("• 원문: "+item["url"],"• 원문: "+pair["url"]))
 return "\n".join(lines)

def load_state()->tuple[dict,bool]:
 if not STATE.exists():return {"version":1,"created_at":NOW.isoformat(),"seen":{}},True
 try:
  s=json.loads(STATE.read_text(encoding="utf-8"))
  if not isinstance(s,dict) or not isinstance(s.get("seen"),dict):raise ValueError("schema")
  if any(not isinstance(k,str) or not isinstance(v,str) for k,v in s["seen"].items()):raise ValueError("dedup schema")
  return s,False
 except Exception as exc:
  raise RuntimeError("기존 중복방지 상태 손상: 알림 대신 실패 처리(수동 복구 필요)") from exc

def collect(rss_fn=rss)->tuple[dict,list[str],int]:
 collected={name:{} for name in TOPICS}
 errors=[]
 good=0
 for name,topic in TOPICS.items():
  for query in topic["queries"]:
   try:
    items=rss_fn(query)
    good+=1
    for item in items:
     age=NOW-item["pub"]
     lookback=dt.timedelta(days=15) if name in {"ground","amazon_leo"} else dt.timedelta(days=7)
     if age>lookback or age<dt.timedelta(minutes=-15):continue
     sta=stage(name,item["title"])
     if not sta:continue
     k=f'{item["publisher"].lower()}|{stem_title(item["title"])}'
     collected[name][k]=(sta,item)
   except Exception as exc:
    errors.append(f"{name}: {type(exc).__name__}")
 return collected,errors,good

def choose_events(group:dict,seen:dict,bootstrap_run:bool,force:bool=False)->tuple[list[str],dict]:
 alerts=[]
 updated=dict(seen)
 emitted_this_scan=set()
 for topic,candidates in group.items():
  ordered=sorted(candidates.values(),key=lambda z:z[1]["pub"],reverse=True)
  for status,item in ordered:
   # A single RSS headline is not a license, signed contract, or FCC approval.
   if not independent_publisher(item):continue
   eid=event_id(topic,status,item["title"])
   # Original commercial-release and handoff-test notices are emitted only
   # after checking their issuer originals; recycled RSS cannot premark them.
   if (topic=="qualcomm_5g" and status=="agreement") or (topic=="asts_handoff" and status=="handoff_test"):
    continue
   # A headline saying merely "15,000 SpaceX satellites" without specifying
   # DA-26-36 Gen2 broadband vs DA-26-1078 mobile D2D is unsafe.
   if eid.startswith("fcc:ambiguous_15000:"):continue
   if eid in emitted_this_scan:continue
   if eid in updated and not force:continue
   peers=[p for s,p in ordered if s==status and
          independent_publisher(p) and match_articles(item,p,topic,status)]
   if not peers:continue
   if bootstrap_run:
    updated[eid]=NOW.isoformat()
    continue
   backfill=(eid in {
      "ground:spacex_80000_sites:site_talks",
      "competitor:amazon_globalstar:transfer_approved",
   } and NOW-item["pub"]<=dt.timedelta(days=15))
   if NOW-item["pub"]>RECENT and not backfill:continue
   report=render(topic,status,item,peers[0])
   if backfill and NOW-item["pub"]>RECENT:report="[지난 보도 누락 보완 · 신규 계약 확정 아님]\n"+report
   alerts.append((item["pub"],eid,report))
   emitted_this_scan.add(eid)
   updated[eid]=NOW.isoformat()
 alerts.sort(key=lambda z:z[0],reverse=True)
 # Do not lose validated unreported events; keep them unread for next cycle.
 chosen=alerts[:MAX_ITEMS]
 for _,eid,_ in alerts[MAX_ITEMS:]:
  updated.pop(eid,None)
 return [x[2] for x in chosen],updated

def test()->int:
 assert stage("license","SpaceX to buy Grain's 800 MHz spectrum, subject to FCC approval")=="agreement"
 assert stage("license","FCC approves 15,000 SpaceX satellites for mobile, 800 MHz Grain deal pending")!="fcc_approval"
 assert stage("license","T-Mobile completes transfer of 800MHz licenses to Grain Management") is None
 assert stage("license","FCC approves Grain-to-SpaceX 800 MHz spectrum license transfer")=="fcc_approval"
 assert stage("license","SpaceX completes Grain 800MHz spectrum deal")=="close"
 assert stage("license","SpaceX's Grain 800 MHz spectrum purchase is delayed")=="deny"
 assert stage("fcc","FCC approves SpaceX 15,000 Gen2 satellites in 2GHz")=="permission"
 assert stage("fcc","FCC to vote on SpaceX Starlink D2D spectrum proposal October 29")=="proposal"
 assert stage("fcc","SpaceX files FCC application for new 15,000 D2D satellites")=="proposal"
 assert stage("fcc","FCC grants SpaceX approval to operate 15,000 D2D satellites")=="permission"
 assert stage("fcc","SpaceX approval pending at FCC on 2 GHz D2D")=="proposal"
 assert stage("fcc","FCC to approve SpaceX D2D launch request")=="proposal"
 assert event_id("fcc","permission","FCC approves SpaceX 15,000 D2D direct-to-device satellites (DA-26-1078)")=="fcc:DA-26-1078:D2D:permission"
 assert event_id("fcc","permission","FCC approves additional 7,500 Gen2 broadband satellites (DA-26-36)")=="fcc:DA-26-36:gen2:permission"
 assert event_id("fcc","permission","FCC approves SpaceX 15,000 D2D direct-to-device satellites")!=event_id("fcc","permission","FCC approves additional 7,500 Gen2 broadband satellites")
 assert event_id("fcc","permission","FCC approves 15,000 SpaceX satellites")=="fcc:ambiguous_15000:permission"
 assert "fcc:DA-26-1078:D2D:permission" not in KNOWN_BASELINE_KEYS
 assert FCC_D2D_ORDER_KEY=="fcc:DA-26-1078:D2D:permission"
 assert "FCC는 2026년 10월 6일" in regulatory_correction_notice()
 assert "2026년 1월 9일" in regulatory_correction_notice()
 assert "Grain→SpaceX 800MHz 계약" in regulatory_correction_notice()
 assert event_id("license","agreement","SpaceX to buy Grain 800MHz") == event_id("license","agreement","SpaceX acquires Grain 800 MHz spectrum")
 a={"title":"SpaceX and Grain sign nationwide 800 MHz spectrum deal", "publisher":"Reuters","pub":NOW,"url":"https://a.example"}
 b={"title":"Grain spectrum 800MHz agreement with SpaceX across the US", "publisher":"Financial Times","pub":NOW,"url":"https://b.example"}
 c={"title":a["title"],"publisher":"Reuters","pub":NOW,"url":"https://c.example"}
 assert match_articles(a,b) and not match_articles(a,c)
 assert not independent_publisher({"publisher":"FCC"})
 assert not independent_publisher({"publisher":"PRNewswire"})
 assert not independent_publisher({"publisher":"Unknown stock blog"})
 records={"license":{"a":("agreement",a),"b":("agreement",b)}}
 first,updated=choose_events(records,{},True)
 assert not first and "license:grain_spacex_800:agreement" in updated
 second,_=choose_events(records,updated,False)
 assert not second
 other,post=choose_events(records,{},False)
 assert len(other)==1 and "협상·승인·계약·종결은 당사자 원문" in other[0]
 assert "매출 | " in other[0] and "역풍 | " in other[0] and "지표 | " in other[0]
 assert other[0].count("• 원문: ")==2
 assert "거래금액: 당사자 공식 발표에서 미공개" in bootstrap()
 assert "2026년 7월 1일" in bootstrap()
 assert "2026년 10월 1일" in bootstrap()
 assert "DA-26-1078" in bootstrap()
 ambiguous={"title":"FCC approves 15,000 SpaceX satellites", "publisher":"Reuters","pub":NOW,"url":"https://ambiguous.example/a"}
 ambiguous2={"title":"FCC approves 15,000 SpaceX satellites", "publisher":"Financial Times","pub":NOW,"url":"https://ambiguous.example/b"}
 ambiguous_result,_=choose_events({"fcc":{"x":("permission",ambiguous),"y":("permission",ambiguous2)}},{},False)
 assert not ambiguous_result, "Ambiguous 15k title must not create regulatory approval alert"
 assert STATE!=PENDING!=ALERT
 assert distinct_primary_organizations(["Grain Management 매각 공식 발표", "Grain Management 배포 보도자료"])=={"grain"}
 assert distinct_primary_organizations(["Grain Management 배포 보도자료", "AT&T·AST SpaceMobile 상업계약 공식 발표"])=={"grain","att"}
 assert FACTCHECK_20261011_KEY not in KNOWN_BASELINE_KEYS
 sources=["NASA Falcon 9·Dragon Crew-15~17 확정 계약", "Grain Management 매각 공식 발표"]
 assert should_send_historical_factcheck(False,{"seen":{}},sources)
 assert not should_send_historical_factcheck(False,{"seen":{FACTCHECK_20261011_KEY:"2026-10-11"}},sources)
 assert not should_send_historical_factcheck(True,{"seen":{}},sources)
 assert not should_send_historical_factcheck(False,{"seen":{}},sources[:1])

 assert daily_price_return(22.18,24.87,0.2775)[0] < -10.8
 assert abs(daily_price_return(22.18,24.87,0.2775)[1] + 9.81)<0.02
 assert abs(daily_price_return(41.65,46.35,0.7075)[0] + 10.14)<0.01
 assert abs(daily_price_return(41.65,46.35,0.7075)[1] + 8.75)<0.02
 assert "AT&T(T) 22.18달러 · -10.82%" in user_claims_factcheck()
 assert "  배당락 조정: -9.81%" in user_claims_factcheck()
 assert "버라이즌(VZ) 41.65달러 · -10.14%" in user_claims_factcheck()
 assert "  배당락 조정: -8.75%" in user_claims_factcheck()
 assert "Falcon 9·Dragon 즉시 퇴역" in user_claims_factcheck()
 assert "위성 길이 7m" in user_claims_factcheck()
 assert "• 원문: "+NASA_NEW_CREW_URL in user_claims_factcheck()
 assert user_claims_factcheck().count("• 원문: ")==8
 assert "주가 |" not in user_claims_factcheck()
 assert not should_send_price_correction(False,{"seen":{}},[])
 assert should_send_price_correction(False,{"seen":{FACTCHECK_20261011_KEY:"2026-10-11"}},
     ["AT&T 배당락·주당 배당금 공식 발표",
      "Verizon 2026년 10월 9일 배당락 공식 내역",
      "NASA Falcon 9·Dragon Crew-15~17 확정 계약"])
 assert not should_send_price_correction(False,{"seen":{
      FACTCHECK_20261011_KEY:"2026-10-11",
      DIVIDEND_DISPLAY_CORRECTION_KEY:"2026-10-11"}},
     ["AT&T 배당락·주당 배당금 공식 발표",
      "Verizon 2026년 10월 9일 배당락 공식 내역",
      "NASA Falcon 9·Dragon Crew-15~17 확정 계약"])
 assert "license:grain_spacex_800:agreement" in KNOWN_BASELINE_KEYS
 assert stage("ground","SpaceX in talks to access 80,000 cell sites for wireless network")=="site_talks"
 assert stage("ground","SpaceX signs definitive 80,000 cell sites agreement")=="site_agreement"
 assert stage("mobile_entry","SpaceX in talks to buy Boost Mobile or access its network")=="boost_talks"
 assert stage("mobile_entry","SpaceX signs a definitive agreement to acquire Boost Mobile")=="boost_agreement"
 assert stage("amazon_leo","FCC approves Amazon Leo acquisition of Globalstar")=="transfer_approved"
 assert stage("amazon_leo","美FCC 아마존 글로벌스타 인수 관련 면허 이전 승인")=="transfer_approved"
 assert independent_publisher({"publisher":"The Washington Post"})
 boost1={"title":"SpaceX in talks to buy Boost Mobile or use its network, Washington Post reports","publisher":"Reuters","pub":NOW,"url":"https://reuters.example"}
 boost2={"title":"SpaceX could buy Boost Mobile as part of its big mobile carrier plans","publisher":"The Verge","pub":NOW,"url":"https://verge.example"}
 assert match_articles(boost1,boost2,"mobile_entry","boost_talks")
 assert not match_articles(boost1,boost2,"mobile_entry","boost_agreement")
 amazon1={"title":"美FCC 아마존 글로벌스타 인수 승인","publisher":"연합뉴스","pub":NOW,"url":"https://yna.example"}
 amazon2={"title":"FCC approves Amazon Globalstar acquisition","publisher":"Reuters","pub":NOW,"url":"https://reuters.example"}
 assert match_articles(amazon1,amazon2,"amazon_leo","transfer_approved")
 assert not match_articles(amazon1,amazon2,"amazon_leo","acquisition_close")
 assert event_id("ground","site_talks","SpaceX access 80,000 cell sites")=="ground:spacex_80000_sites:site_talks"
 assert event_id("mobile_entry","boost_talks","SpaceX in talks to buy Boost Mobile")=="mobile:starlink_boost:boost_talks"
 assert event_id("mobile_entry","boost_agreement","SpaceX signs Boost Mobile acquisition agreement")!=event_id("mobile_entry","boost_talks","SpaceX in talks to buy Boost Mobile")
 assert event_id("amazon_leo","transfer_approved","FCC approves Amazon Leo acquisition Globalstar")=="competitor:amazon_globalstar:transfer_approved"
 assert stage("qualcomm_5g","SpaceX selects Qualcomm Dragonwing 5G for nationwide base stations")=="agreement"
 assert stage("qualcomm_5g","SpaceX Qualcomm to deploy Dragonwing 5G base stations in 2027") is None
 assert stage("qualcomm_5g","SpaceX Qualcomm Dragonwing 5G sites now operational")=="rollout_report"
 assert stage("asts_handoff","AT&T AST SpaceMobile complete handoff of satellite and terrestrial networks")=="handoff_test"
 assert stage("asts","AT&T AST SpaceMobile complete handoff of satellite and terrestrial networks") is None
 assert stage("asts_handoff","AT&T AST SpaceMobile plan beta service next year") is None
 assert stage("asts_handoff","AT&T AST SpaceMobile beta service begins")=="beta_report"
 assert stage("korean_vendor","SpaceX Starlink KMW named potential supplier winner") is None
 assert stage("korean_vendor","SpaceX Starlink RFHIC signs supply contract")=="supplier_report"
 assert stage("korean_vendor","SpaceX Qualcomm supplier candidates KMW RFHIC") is None
 assert event_id("korean_vendor","supplier_report","SpaceX Starlink KMW signs supply contract")=="vendor:starlink:kmw:supplier_report"
 assert event_id("korean_vendor","supplier_report","SpaceX Starlink HFR signs supply contract")=="vendor:starlink:hfr:supplier_report"
 assert event_id("korean_vendor","supplier_report","SpaceX Starlink RFHIC signs supply contract")=="vendor:starlink:rfhic:supplier_report"
 assert event_id("qualcomm_5g","agreement","SpaceX selects Qualcomm Dragonwing 5G")==QUALCOMM_AGREEMENT_KEY
 assert event_id("asts_handoff","handoff_test","AT&T AST SpaceMobile satellite handoff")==AST_HANDOFF_KEY
 assert "2027년부터" in official_qualcomm_agreement_notice()
 assert "기지국 부지 8만 곳" in official_qualcomm_agreement_notice()
 assert "시험" in official_ast_handoff_notice() and "상용" in official_ast_handoff_notice()
 primary=[QUALCOMM_PRIMARY,AST_HANDOFF_PRIMARY]
 notices=newly_verified_official_notices({},primary,False)
 assert [k for k,_ in notices]==[QUALCOMM_AGREEMENT_KEY,AST_HANDOFF_KEY]
 assert not newly_verified_official_notices({},primary,True)
 assert not newly_verified_official_notices({QUALCOMM_AGREEMENT_KEY:"sent",AST_HANDOFF_KEY:"sent"},primary,False)
 assert not newly_verified_official_notices({},[],False)
 assert all(block.count("• 원문: ")==2 for _,block in notices)
 initial_pairs={"qualcomm_5g":{"x":("agreement",{"title":"SpaceX selects Qualcomm Dragonwing 5G","publisher":"Reuters","pub":NOW,"url":"https://a.example"}),
                                "y":("agreement",{"title":"Qualcomm chosen by SpaceX for Dragonwing 5G","publisher":"The Verge","pub":NOW,"url":"https://b.example"})}}
 initial_rss,initial_seen=choose_events(initial_pairs,{},False)
 assert not initial_rss and not initial_seen
 assert stage("amazon_leo","Amazon Leo files FCC application for 5,105 D2D satellites")=="d2d_application"
 assert stage("amazon_leo","FCC approves Amazon Leo 5,105 D2D satellites")=="d2d_permission_report"
 assert stage("amazon_leo","Amazon Leo plans to deploy 5,105 D2D satellites") is None
 assert stage("amazon_leo","FCC approves Amazon acquisition of Globalstar")=="transfer_approved"
 assert event_id("amazon_leo","d2d_application","Amazon Leo files 5,105 satellites") in KNOWN_BASELINE_KEYS
 assert event_id("amazon_leo","d2d_permission_report","FCC approves Amazon Leo 5,105 D2D") not in KNOWN_BASELINE_KEYS
 assert newly_verified_official_notices({},["퀄컴 공식 뉴스룸 계약 공지"],False)[0][0]==QUALCOMM_AGREEMENT_KEY
 assert newly_verified_official_notices({},["퀄컴 공식 기술 홈페이지 계약 공지"],False)[0][0]==QUALCOMM_AGREEMENT_KEY
 issuer_notice=newly_verified_official_notices({},["퀄컴 직접 발행 BusinessWire 보도자료"],False)
 assert issuer_notice[0][0]==QUALCOMM_AGREEMENT_KEY
 assert "BusinessWire 배포 원문" in issuer_notice[0][1]
 republication=newly_verified_official_notices({},["퀄컴 보도자료 Nasdaq 합법 재게시"],False)
 assert "합법 재게시" in republication[0][1]
 assert not newly_verified_official_notices({QUALCOMM_AGREEMENT_KEY:"sent"},["퀄컴 보도자료 Yahoo BusinessWire 재게시"],False)
 assert rakuten_ast_story("Yomiuri: Rakuten, AST SpaceMobile to launch joint venture for satellite-smartphone services")
 assert rakuten_ast_story('Rakuten and AST SpaceMobile Establish "Rakuten AST" Joint Venture in Japan')
 assert stage("asts","Yomiuri: Rakuten, AST SpaceMobile to launch joint venture") is None
 assert stage("asts",'Rakuten and AST SpaceMobile Establish "Rakuten AST" Joint Venture') is None
 assert stage("rakuten_ast","Yomiuri: Rakuten, AST SpaceMobile to launch joint venture for satellite-smartphone services")=="jv_agreement"
 assert stage("rakuten_ast",'Rakuten and AST SpaceMobile Establish "Rakuten AST" Joint Venture in Japan')=="jv_agreement"
 assert stage("rakuten_ast","Rakuten AST joint venture planned to start service in 2029")=="jv_agreement"
 assert stage("rakuten_ast","Rakuten AST company registration completed in Japan")=="jv_established"
 assert stage("rakuten_ast","Rakuten AST grant received from Japan MIC")=="grant_disbursed"
 assert event_id("rakuten_ast","jv_agreement","Yomiuri: Rakuten AST SpaceMobile JV")==RAKUTEN_AST_JV_KEY
 assert event_id("rakuten_ast","jv_agreement","Rakuten AST joint venture announcement")==RAKUTEN_AST_JV_KEY
 assert event_id("rakuten_ast","jv_established","Rakuten AST completed incorporation")!=RAKUTEN_AST_JV_KEY
 old_state={"seen":{RAKUTEN_AST_OLD_KEYS[0]:"2026-11-11T18:46:13Z",
                    RAKUTEN_AST_OLD_KEYS[1]:"2026-11-11T18:46:13Z",
                    "other:existing:event":"2026-11-10T01:00:00Z"}}
 assert migrate_rakuten_ast_state(old_state)
 assert old_state["seen"][RAKUTEN_AST_JV_KEY]=="2026-11-11T18:46:13Z"
 assert all(k in old_state["seen"] for k in RAKUTEN_AST_OLD_KEYS)
 assert not migrate_rakuten_ast_state(old_state)
 rakuten1={"title":"Yomiuri: Rakuten AST SpaceMobile to launch joint venture for satellite-smartphone services",
           "publisher":"MarketWatch","pub":NOW,"url":"https://news.google.com/rss/articles/yomiuri"}
 rakuten2={"title":'Rakuten and AST SpaceMobile Establish "Rakuten AST" Joint Venture to Build D2D Network',
           "publisher":"Financial Times","pub":NOW,"url":"https://news.google.com/rss/articles/rakuten"}
 group={"rakuten_ast":{"a":("jv_agreement",rakuten1),"b":("jv_agreement",rakuten2)}}
 assert match_articles(rakuten1,rakuten2,"rakuten_ast","jv_agreement")
 alerts,added=choose_events(group,{},False)
 assert len(alerts)==1 and len(added)==1 and RAKUTEN_AST_JV_KEY in added
 from space_launch_telegram_send import readable_messages
 compact=readable_messages(HEADER+"\n기준: 회귀검사\n\n"+alerts[0]+"\n")
 assert len(compact)==1, "One Rakuten–AST agreement must fit one readable Telegram message"
 assert "51%" in compact[0][0] and "1,480억" in compact[0][0]
 assert [x["url"] for x in compact[0][1] if x["type"]=="text_link"]==[
    RAKUTEN_AST_ORIGINAL,RAKUTEN_AST_SEC
 ]
 assert "51%" in alerts[0] and "1,480억" in alerts[0] and "2029년 3월" in alerts[0]
 prior_alerts,unchanged=choose_events(group,old_state["seen"],False)
 assert prior_alerts==[] and unchanged==old_state["seen"]
 forced,_=choose_events(group,old_state["seen"],False,force=True)
 assert len(forced)==1
 assert "license:grain_spacex_800:fcc_approval" not in KNOWN_BASELINE_KEYS
 assert "license:grain_spacex_800:close" not in KNOWN_BASELINE_KEYS
 print("starlink_mobile_d2d_self_test=ok approvals_separated=1 government_rss_excluded=1 media_duo=1 no_duplicates=1 known_baseline=1")
 return 0

def main()->int:
 if os.environ.get("STARLINK_D2D_SELF_TEST")=="1":return test()
 state,initial=load_state()
 rakuten_migrated=migrate_rakuten_ast_state(state)
 official,failed=verified_primary_sources()
 groups,errors,good=collect()
 if good<5:
  raise RuntimeError(f"뉴스조회 불충분: {good} 성공·{len(errors)} 실패; 상태 유지")
 # Government/legal/official primary sources are checked independently of RSS.
 # On startup insist on two real corporate originals; do not send cached claims.
 organizations=distinct_primary_organizations(official)
 if len(organizations)<2:
  raise RuntimeError(f"독립된 공식 발행기관 {len(organizations)}곳: 알림 차단. {failed}")
 force=os.getenv("FORCE_NOTIFY","").strip().lower() in ("true","1","yes")
 events,next_seen=choose_events(groups,state["seen"],initial,force)
 # One-time missed official milestones; do not infer customer awards from RSS.
 # Pending keys are persisted only after Telegram confirms delivery.
 official_new=newly_verified_official_notices(state["seen"],official,initial)
 for key,notice in reversed(official_new):
  events.insert(0,notice)
  next_seen[key]=NOW.isoformat()
 # One-time correction of the old report's close/adjusted-close basis.
 # Strictly require issuer dividend originals and NASA's crew agreement.
 if should_send_price_correction(initial,state,official):
  events.insert(0,price_dividend_display_correction())
  next_seen[DIVIDEND_DISPLAY_CORRECTION_KEY]=NOW.isoformat()
 # Correct the pre-existing program error: two DISTINCT FCC grants each
 # concern 15,000 spacecraft (Jan Gen2 broadband, Oct D2D S00735).
 # Deliver one explicit clarification only after directly reading an FCC
 # primary publication, with independent FCC order and original Grain sources.
 correction=False
 oct_fcc_primary=any(
  s.startswith("FCC 2026년 10월 D2D 별도 승인")
  or s.startswith("FCC D2D 공식 결정문 안내")
  for s in official
 )
 if (not initial and FCC_D2D_ORDER_KEY not in state["seen"]
      and oct_fcc_primary and "Grain Management 매각 공식 발표" in official):
  correction=True
  # Prefer the regulator's actual Order over recycled commentary of it.
  events=[s for s in events if not (
   s.startswith(TOPICS["fcc"]["title"])
   and ("15,000" in s or "15k" in s or "D2D" in s)
  )]
  events.insert(0,regulatory_correction_notice())
  next_seen[FCC_D2D_ORDER_KEY]=NOW.isoformat()
 # One-time fact check of claims that conflate 2026-10-09 regular closes,
 # Falcon 9 fairing diameter and satellite length, and Dragon retirement.
 # We insist on a live first-party NASA document plus the established Grain
 # original before sending historical data as a carefully labelled correction.
 claim_verified = ("NASA Falcon 9·Dragon Crew-15~17 확정 계약" in official
                  and "Grain Management 매각 공식 발표" in official)
 factcheck_20261011=False
 if should_send_historical_factcheck(initial,state,official):
  events.insert(0,user_claims_factcheck())
  next_seen[FACTCHECK_20261011_KEY]=NOW.isoformat()
  factcheck_20261011=True
 # Idempotent migration fixes an original bug: the first broadcast delivered
 # known October headlines while an empty dedup state could replay them later.
 # Never pre-mark the still-pending FCC assignment approval or sale closing.
 seeded=0
 for k in KNOWN_BASELINE_KEYS:
  if k not in next_seen:
   next_seen[k]=NOW.isoformat()
   seeded+=1
 state["seen"]=next_seen
 # Avoid 48 contentless commits/day and related repo push-trigger storms.
 if initial or events or seeded or rakuten_migrated:
  state["updated_at"]=NOW.isoformat()
  state["official_sources_verified"]=official
 if initial:
  report=bootstrap()
 elif events:
  report=HEADER+"\n기준: "+NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")+"\n\n"+"\n\n".join(events)+"\n"
 else:report=""
 ALERT.parent.mkdir(parents=True,exist_ok=True)
 if report:ALERT.write_text(report,encoding="utf-8")
 else:ALERT.unlink(missing_ok=True)
 PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 SUMMARY.write_text("\n".join([
  "# Starlink Mobile·미국 이동통신 경쟁 감시",
  f"- 점검 시각: {NOW.astimezone(KST).isoformat()}",
  f"- 공식 발표 원문 검증: {len(official)}/{len(SOURCES)} (독립 발행기관 {len(organizations)}곳: {', '.join(official)})",
  f"- 원천 접근 실패: {len(failed)}건 (발행기관·오류 종류만 기록): {'; '.join(failed)}",
  f"- 뉴스 피드 정상: {good}/{sum(len(x['queries']) for x in TOPICS.values())}",
  f"- 뉴스 피드 장애: {len(errors)}",
  f"- 최초 기준선: {initial}, 이번 알림 사건: {len(events)}",
  f"- 라쿠텐·AST 기존 2개 중복 키 보존·대표 사건 키 연결: {rakuten_migrated}",
  f"- 이번 검사에서 같은 논리적 사건을 두 번 알리지 않음",
  f"- 퀄컴 계약·AST 전환시험 신규 공식 근거: {[key for key,_ in official_new]}",
  f"- 10월 6일 별도 FCC 직접통신 허가 정정 알림: {correction}",
  f"- 10월 11일 주가·Falcon/Dragon 팩트체크: {factcheck_20261011} | NASA+Grain 공식 원문: {claim_verified}",
  f"- FCC DA-26-1078 공식 원문 검증: {oct_fcc_primary}",
  "- FCC 2026-07 T-Mobile→Grain 승인과 2026-10 Grain→SpaceX 승인 대기를 혼동하지 않음",
  "- 언론 교차 보도는 정부 승인·거래 종결로 확정하지 않음",
  "- 중복 기록은 Telegram 전송 성공 뒤에만 반영",
  ""
 ]),encoding="utf-8")
 print(f"starlink_mobile_d2d_scan=ok official_verified={len(official)} rss_ok={good} initial={initial} events={len(events)} alert={bool(report)}")
 return 0

if __name__=="__main__":
 raise SystemExit(main())
