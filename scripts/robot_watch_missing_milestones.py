#!/usr/bin/env python3
"""Additional user-supplied 2026 robotics coverage for the EXISTING alert route.

Preserves all prior workflows, recipients, timestamps and seen keys.
Reported exhibitions, RFQs, demos, policy R&D and recruiting are baselines.
Alert ONLY on new issuer/partner-source achievements, never on old promises
or unconfirmed supply-chain guesses. No dated backfills and no new bot.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import re

# The input requires both identity and the industrial/application context.
TOPICS = {
 "surgery_robot_hospital": {
   "match": (r"삼성서울병원|Samsung\s*Medical\s*Center",
             r"휴머노이드|로봇|robot", r"수술|surg"),
   "official": {"삼성서울병원","Samsung Medical Center","보건복지부","Ministry of Health and Welfare","식품의약품안전처"},
   "steps": (
      ("clinical_approval",r"임상시험\s*(?:계획\s*)?(?:승인|허가)|IRB\s*(?:approval|approved)|clinical\s*trial\s*(?:approved|authorized)"),
      ("first_patient_actual",r"첫\s*환자.{0,24}(?:수술|적용|투입)\s*(?:완료|실시|시작)|first\s*patient.{0,35}(?:treated|performed|procedure)"),
      ("clinical_trial_started",r"임상(?:시험)?\s*(?:개시|착수)|clinical\s*trial\s*(?:began|started)"),
   ),
   "tag":"삼성서울병원 수술 보조 로봇",
   "watch":"임상 승인·첫 환자 실제 사용·도구 전달 성능",
 },
 "bigwave_rainbow_northamerica": {
   "match": (r"빅웨이브로보틱스|BIGWAVE\s*Robotics",
             r"레인보우로보틱스|Rainbow\s*Robotics",
             r"북미|미국|North\s*America|US\s*customer|미시간|Detroit"),
   "official":{"빅웨이브로보틱스","BIGWAVE ROBOTICS","레인보우로보틱스","Rainbow Robotics"},
   "steps": (
     ("paid_pilot_completed",r"유료.{0,24}(?:실증|검증|PoC).{0,25}(?:완료|통과)|paid\s*pilot\s*(?:completed|passed)"),
     ("signed_customer_order",r"정식\s*(?:공급|구매)\s*계약\s*체결|구매\s*발주서\s*확정|signed\s*(?:supply|purchase)\s*(?:agreement|contract)"),
     ("first_customer_delivery",r"북미.{0,35}(?:초도|첫)\s*(?:납품|인도|출하)\s*(?:완료|개시)|first\s*(?:US|North\s*American)\s*shipment"),
   ),
   "tag":"빅웨이브·레인보우 북미 실증",
   "watch":"350건 전시 상담→유료 현장 검증→구매주문→출하",
 },
 "neoauto_rover": {
   "match":(r"네오오토|Neoauto|Neo\s*Auto",r"로버|rover|행성\s*탐사",r"감속기|actuator|구동\s*부품|gear"),
   "official":{"네오오토","Neoauto","Neo Auto","산업통상자원부","한국산업기술기획평가원","KEIT"},
   "steps": (
     ("government_rnd_test_pass",r"1\s*단계.{0,30}(?:시험|검증)\s*(?:완료|통과)|1\s*세부.{0,30}(?:검증|시험)\s*통과|국책과제.{0,55}평가\s*통과"),
     ("customer_validation_passed",r"(?:고객|우주\s*환경).{0,30}(?:성능|신뢰성)\s*(?:검증|시험)\s*통과"),
     ("binding_order",r"(?:정식\s*)?(?:공급|구매)\s*계약\s*체결|확정\s*발주서"),
   ),
   "tag":"네오오토 로버 감속기",
   "watch":"실물 조립 후 국책 1단계 통과·신뢰성 시험·실제 고객 계약",
 },
 "almec_boston": {
   "match":(r"알멕|Almac|ALMAC",r"보스턴다이내믹스|Boston\s*Dynamics|Atlas|아틀라스",r"로봇|robot|RFQ|견적|프레임"),
   "official":{"알멕","ALMAC","Boston Dynamics"},
   "steps":(
     ("customer_qualified",r"(?:고객|보스턴다이내믹스).{0,38}(?:공급업체|품질|신뢰성)\s*(?:승인|검증\s*통과)"),
     ("binding_robot_order",r"(?:보스턴다이내믹스|Boston\s*Dynamics).{0,75}(?:공급계약\s*체결|정식\s*발주|purchase\s*order)|(?:공급계약\s*체결|정식\s*발주).{0,70}(?:보스턴다이내믹스|Boston\s*Dynamics)"),
     ("first_robot_shipment",r"(?:보스턴다이내믹스|Boston\s*Dynamics).{0,75}(?:초도\s*납품|첫\s*출하)\s*(?:완료|개시)"),
   ),
   "tag":"알멕·보스턴다이내믹스",
   "watch":"견적요청서→정식 공급사 선정→구속력 있는 구매주문→초도 출하",
 },
 "cps_rainbow_robokit": {
   "match":(r"씨피시스템|CP\s*System",r"로보킷|Robokit|케이블\s*(?:보호|체인)|cable",
            r"레인보우로보틱스|Rainbow\s*Robotics|협동로봇"),
   "official":{"씨피시스템","CP System","레인보우로보틱스","Rainbow Robotics"},
   "steps":(
     ("production_contract",r"양산용.{0,35}(?:공급계약\s*체결|정식\s*발주)|정식\s*공급\s*계약\s*체결"),
     ("first_mass_shipment",r"양산용.{0,40}(?:초도\s*납품|첫\s*출하)\s*(?:완료|개시)|실제\s*양산.{0,35}납품\s*(?:완료|시작)"),
     ("repeat_order",r"후속\s*(?:수주|발주)\s*(?:확정|체결)|반복\s*발주\s*확정"),
   ),
   "tag":"씨피시스템·레인보우 케이블",
   "watch":"기존 1월 로보킷 시제품→양산 계약·실물 납품·반복 수주",
 },
 "hatchtec_encoder_hand": {
   "match":(r"해치텍|Hatchtec|Hatch\s*Tech",r"인코더|encoder|관절\s*(?:위치|정밀)",r"로봇|robot|휴머노이드"),
   "official":{"해치텍","Hatchtec","Hatch Tech"},
   "steps":(
     ("customer_qualified",r"(?:고객|휴머노이드).{0,35}(?:검증|인증|평가)\s*(?:완료|통과)"),
     ("volume_contract",r"(?:인코더|encoder).{0,45}(?:공급계약\s*체결|대량\s*발주\s*확정|양산\s*공급\s*개시)"),
   ),
   "tag":"해치텍 로봇 인코더 IC",
   "watch":"기술 적합성→고객 검증 완료→양산 물량·실제 매출",
 },
 "bytedance_robot_hardware": {
   "match":(r"바이트댄스|ByteDance|字节跳动",r"로봇|robot|휴머노이드"),
   "official":{"ByteDance","바이트댄스","字节跳动"},
   "steps":(
     ("actual_production",r"휴머노이드.{0,50}(?:양산\s*(?:시작|개시)|production\s*(?:started|commenced))"),
     ("first_customer_delivery",r"휴머노이드.{0,50}(?:첫\s*고객\s*인도\s*완료|first\s*customer\s*delivery)"),
     ("signed_customer_deal",r"휴머노이드.{0,50}(?:공급계약\s*체결|signed\s*customer\s*contract)"),
   ),
   "tag":"바이트댄스 휴머노이드",
   "watch":"Seed 팀 채용과 실제 로봇 양산·고객 유상 공급은 별개",
 },
 "amogreentech_robot_magnets": {
   "match":(r"아모그린텍|Amogreentech",r"로봇|robot|휴머노이드",r"자성|magnetic|자석|motor|모터"),
   "official":{"아모그린텍","Amogreentech"},
   "steps":(
     ("robot_customer_qualified",r"(?:로봇|휴머노이드).{0,45}(?:고객\s*승인|실제\s*고객\s*검증\s*통과)"),
     ("robot_binding_order",r"(?:로봇|휴머노이드).{0,45}(?:공급계약\s*체결|정식\s*발주|양산\s*납품\s*개시)"),
   ),
   "tag":"아모그린텍 로봇 자성소재",
   "watch":"사업 관련성→로봇 고객 실명·제품·실제 납품 계약",
 },
 "openai_data_center_robots": {
   "match":(r"OpenAI|오픈AI|오픈에이아이",r"데이터\s*센터|data\s*center",r"로봇|robot"),
   "official":{"OpenAI","OpenAI Newsroom"},
   "steps":(
     ("deployed_on_construction_site",r"실제\s*(?:건설\s*현장|데이터센터).{0,45}로봇.{0,25}(?:투입|배치)\s*(?:완료|개시)|robots?\s*(?:deployed|working)\s*on\s*data\s*center\s*construction"),
     ("paid_construction_deal",r"데이터센터.{0,45}로봇.{0,25}(?:유상\s*계약\s*체결|공급계약\s*체결)"),
   ),
   "tag":"OpenAI 데이터센터 건설 로봇",
   "watch":"올트먼의 장기 구상→실제 건설 현장 투입·계약 확인",
 },
}

# 2026-11-11 user-supplied robotics source audit: add next-stage monitoring only.
# Original reports, demonstrations, research, planned dates, targets and analysts'
# estimates are BASELINES, never retroactively presented as confirmed orders.
# Explicit first-party source names are required for confirmation-stage alerts.
NOV_2026_SIGNAL_TOPICS = {
  "wonik_robot_financing": {
    "match": [
      "원익로보틱스|원익홀딩스",
      "국민성장펀드|주주간계약|풋옵션|전환우선주|유상증자"
    ],
    "official": [
      "원익홀딩스",
      "원익로보틱스",
      "금융감독원",
      "DART",
      "KIND",
      "한국산업은행",
      "금융위원회"
    ],
    "steps": [
      [
        "shareholder_signed",
        "주주간\\s*계약.{0,18}(?:체결|완료)|투자\\s*계약.{0,24}체결"
      ],
      [
        "payment_completed",
        "(?:3[,]?500\\s*억|전환우선주).{0,90}(?:납입\\s*완료|대금\\s*납입|paid\\s*in\\s*full)"
      ],
      [
        "plant_construction",
        "(?:완주|로봇핸드).{0,75}(?:공장\\s*착공|설비\\s*반입|건설\\s*착수)"
      ],
      [
        "ipo_or_put_change",
        "(?:상장|IPO|풋옵션|매수청구권).{0,70}(?:확정|행사|기한\\s*변경|조건\\s*변경)"
      ]
    ],
    "tag": "원익로보틱스 정책자금",
    "watch": "3500억원은 8월 정부 승인 기준선→11/10 주주간계약 체결; 11/20 납입은 아직 예정. 시설 1839억원·운영 861억원·타법인 800억원, 상장 실패 풋옵션 수익률 4%와 위약 시 10%·15% 조건을 확인."
  },
  "hyzen_actuator": {
    "match": [
      "하이젠알앤엠|Higen\\s*R&M",
      "휴머노이드|로봇|액추에이터"
    ],
    "official": [
      "하이젠알앤엠",
      "Higen R&M",
      "KIND",
      "DART"
    ],
    "steps": [
      [
        "robot_customer_order",
        "(?:액추에이터|actuator).{0,80}(?:정식\\s*공급계약\\s*체결|확정\\s*구매발주|초도\\s*납품\\s*완료)"
      ],
      [
        "capacity_completed",
        "(?:자동화\\s*설비|로봇\\s*액추에이터).{0,90}(?:증설\\s*완료|생산능력\\s*확대\\s*완료|실제\\s*가동\\s*개시)"
      ]
    ],
    "tag": "하이젠 로봇 구동기",
    "watch": "액추에이터 6종 개발 완료·고객 협의와 수주를 구별. 120억원 투자 종료는 2027/6/30로 연장, 고객 양산 2027년 2~3분기는 회사 예상."
  },
  "rainbow_rby2": {
    "match": [
      "레인보우로보틱스|Rainbow\\s*Robotics",
      "RB[- ]?Y2"
    ],
    "official": [
      "레인보우로보틱스",
      "Rainbow Robotics",
      "FCC"
    ],
    "steps": [
      [
        "first_20_delivered",
        "(?:RB[- ]?Y2).{0,90}(?:초도\\s*(?:납품|인도)\\s*(?:완료|개시)|고객사\\s*인도\\s*완료)"
      ],
      [
        "industrial_pilot_passed",
        "RB[- ]?Y2.{0,85}(?:현장\\s*검증\\s*통과|실증\\s*완료|유료\\s*실증\\s*완료)"
      ],
      [
        "us_fcc_approval",
        "RB[- ]?Y2.{0,90}(?:FCC\\s*인증\\s*(?:취득|완료)|미국\\s*수출\\s*재개)"
      ],
      [
        "repeat_order",
        "RB[- ]?Y2.{0,85}(?:추가\\s*발주\\s*확정|반복\\s*구매계약\\s*체결)"
      ]
    ],
    "tag": "레인보우 RB-Y2",
    "watch": "보도상 초도 약 20대 예약 완료·대당 2억원 초중반대, 실제 양산 출하 아님. 고객 물류현장 검증·FCC 인증 및 수출 재개를 관찰."
  },
  "spg_sdd": {
    "match": [
      "에스피지|\\bSPG\\b",
      "\\bSDD\\b|\\bQDD\\b|로봇\\s*구동"
    ],
    "official": [
      "에스피지",
      "SPG"
    ],
    "steps": [
      [
        "actual_sop",
        "\\bSDD\\b.{0,85}(?:첫\\s*양산\\s*(?:개시|착수|시작)|양산\\s*돌입|mass\\s*production\\s*started)"
      ],
      [
        "first_customer_shipment",
        "\\bSDD\\b.{0,85}(?:첫\\s*고객\\s*출하|초도\\s*공급\\s*완료|공급계약\\s*체결)"
      ]
    ],
    "tag": "에스피지 SDD",
    "watch": "12월 첫 양산은 보도상 일정이며 확정 출하 아님. 성능·무게·내구성·10시간 연속 운전과 실제 고객 검사 결과를 분리."
  },
  "chips_mobilint_video_ip": {
    "match": [
      "칩스앤미디어|Chips\\s*\\&\\s*Media",
      "모빌린트|Mobilint"
    ],
    "official": [
      "칩스앤미디어",
      "Chips&Media",
      "Mobilint",
      "모빌린트"
    ],
    "steps": [
      [
        "signed_extra_ip_license",
        "(?:추가|신규).{0,55}(?:비디오|멀티미디어|VVC|AV2).{0,60}(?:라이선스\\s*계약\\s*체결|IP\\s*계약\\s*체결)"
      ],
      [
        "royalty_recognized",
        "(?:모빌린트|Mobilint).{0,90}(?:로열티\\s*(?:매출|수익)\\s*발생|IP\\s*사용료\\s*매출\\s*인식)"
      ],
      [
        "robot_shipments",
        "(?:모빌린트|Mobilint).{0,75}(?:로봇\\s*고객\\s*양산\\s*출하|휴머노이드\\s*양산\\s*납품)"
      ]
    ],
    "tag": "칩스앤미디어·모빌린트",
    "watch": "11/4 양사 차세대 영상 IP 사용권 계약과 기존 양산 칩 채택은 실사업. 신규 추가 계약·고객향 칩 출하·사용료는 별개."
  },
  "clobot_spatial_rfm": {
    "match": [
      "클로봇|Clobot",
      "공간지능|로봇\\s*파운데이션|Spatial[- ]?RFM"
    ],
    "official": [
      "클로봇",
      "Clobot",
      "한국산업기술기획평가원",
      "KEIT",
      "산업통상부"
    ],
    "steps": [
      [
        "paid_industrial_pilot",
        "(?:공간지능|RFM).{0,90}(?:유료\\s*실증\\s*완료|실제\\s*현장\\s*검증\\s*통과)"
      ],
      [
        "commercial_robot_contract",
        "(?:공간지능|RFM).{0,90}(?:상용\\s*공급계약\\s*체결|유상\\s*라이선스\\s*계약\\s*체결)"
      ],
      [
        "government_milestone",
        "(?:공간지능|RFM).{0,95}(?:정부\\s*단계평가\\s*통과|국책과제\\s*최종평가\\s*완료)"
      ]
    ],
    "tag": "클로봇 공간지능",
    "watch": "총 연구비 73억원(정부 지원 약 59억원)은 7기관·2026/8~2029/12 사업비이며 클로봇 단독 매출 아님; 실제 시제품 검증·유료 공급 별도."
  },
  "saemangeum_robot_farm": {
    "match": [
      "새만금|김제|Saemangeum",
      "로봇팜|로봇\\s*팜|Robot\\s*Farm"
    ],
    "official": [
      "대동",
      "Daedong",
      "전북특별자치도",
      "김제시",
      "농림축산식품부",
      "산업통상부",
      "새만금개발청"
    ],
    "steps": [
      [
        "budget_final",
        "(?:로봇팜|로봇\\s*팜).{0,110}(?:예산\\s*확정|국비\\s*배정\\s*확정|재원조달\\s*계약\\s*체결)"
      ],
      [
        "construction_started",
        "(?:로봇팜|로봇\\s*팜).{0,95}(?:착공\\s*개시|공사\\s*시작|건설\\s*계약\\s*체결)"
      ],
      [
        "equipment_order",
        "(?:로봇팜|로봇\\s*팜).{0,95}(?:로봇\\s*장비\\s*공급계약\\s*체결|로봇\\s*납품\\s*개시)"
      ]
    ],
    "tag": "새만금 로봇팜",
    "watch": "11/3 사업화 논의·21ha 구상은 예산 집행·발주가 아님. 3000억원 프로젝트 보도는 실제 국비/민간 조달 확인 전."
  },
  "daedonggear_robot": {
    "match": [
      "대동기어|Daedong\\s*Gear",
      "액추에이터|로봇\\s*부품|robot\\s*actuator"
    ],
    "official": [
      "대동기어",
      "Daedong Gear"
    ],
    "steps": [
      [
        "robot_qualification",
        "(?:액추에이터|actuator).{0,85}(?:고객\\s*검증\\s*통과|고객사\\s*승인\\s*완료)"
      ],
      [
        "robot_first_contract",
        "(?:액추에이터|actuator).{0,100}(?:로봇\\s*고객\\s*공급계약\\s*체결|양산\\s*첫\\s*납품\\s*완료)"
      ]
    ],
    "tag": "대동기어 액추에이터",
    "watch": "1.9조원 수주잔고는 로봇 액추에이터 전용 수주가 아님. 로봇 액추에이터 개발→고객 인증→매출을 구분."
  },
  "kimm_data_factory": {
    "match": [
      "한국기계연구원|기계연|KIMM",
      "데이터\\s*팩토리|data\\s*factory"
    ],
    "official": [
      "한국기계연구원",
      "KIMM",
      "한국전자통신연구원",
      "ETRI",
      "과학기술정보통신부"
    ],
    "steps": [
      [
        "dataset_opened",
        "(?:데이터\\s*팩토리|data\\s*factory).{0,95}(?:외부\\s*개방\\s*개시|산학연\\s*공개\\s*완료|상용\\s*제공\\s*개시)"
      ],
      [
        "robots_capacity_up",
        "(?:데이터\\s*팩토리|data\\s*factory).{0,100}(?:운영\\s*로봇\\s*확대\\s*완료|운영\\s*대수\\s*증가)"
      ]
    ],
    "tag": "기계연 휴머노이드 데이터",
    "watch": "11/3 시설 개소·휴머노이드 12대 운영 확인, 2027년 말 산학연 개방은 목표; 데이터 생산량·대외 상용 이용 확인."
  },
  "xiaomi_cyberone": {
    "match": [
      "샤오미|Xiaomi",
      "CyberOne|휴머노이드"
    ],
    "official": [
      "샤오미",
      "Xiaomi",
      "Xiaomi Robotics"
    ],
    "steps": [
      [
        "factory_deployed",
        "CyberOne.{0,105}(?:공장\\s*정식\\s*배치\\s*완료|양산\\s*현장\\s*실제\\s*투입|factory\\s*deployment\\s*completed)"
      ],
      [
        "paid_customer_order",
        "CyberOne.{0,85}(?:유상\\s*공급계약\\s*체결|초도\\s*인도\\s*완료)"
      ]
    ],
    "tag": "샤오미 CyberOne",
    "watch": "8시간 부품 분류는 SNS 인용 주장·독립 검증 전; 회사 공식 반복 가동률·실제 배치 및 유상 판매 확인."
  },
  "tesla_cybercab_transition": {
    "match": [
      "테슬라|Tesla",
      "Cybertruck|사이버트럭|Cybercab|사이버캡"
    ],
    "official": [
      "테슬라",
      "Tesla",
      "Tesla Investor Relations"
    ],
    "steps": [
      [
        "cybertruck_actual_stop",
        "Cybertruck.{0,100}(?:실제\\s*생산\\s*종료|production\\s*(?:ceased|ended|stopped))"
      ],
      [
        "cybercab_capacity_ramp",
        "Cybercab.{0,90}(?:생산능력\\s*확대\\s*완료|양산\\s*가동\\s*개시|production\\s*ramp\\s*started)"
      ]
    ],
    "tag": "테슬라 차량전환",
    "watch": "2027년 중반 텍사스 Cybertruck 생산 단계적 축소는 계획. Cybercab 여력 확대와 실제 출하·가동은 다른 단계, Optimus 생산 전환으로 연결하지 않음."
  },
  "gov_robot_localization": {
    "match": [
      "피지컬\\s*AI|Physical\\s*AI",
      "국산화|핵심\\s*부품|3\\s*조|3조"
    ],
    "official": [
      "산업통상부",
      "과학기술정보통신부",
      "기획재정부",
      "대한민국정부",
      "중소벤처기업부"
    ],
    "steps": [
      [
        "formal_budget",
        "(?:피지컬\\s*AI|로봇).{0,110}(?:예산\\s*확정|국회\\s*예산\\s*의결|정부\\s*지원금\\s*집행\\s*개시)"
      ],
      [
        "procurement",
        "(?:피지컬\\s*AI|로봇).{0,110}(?:조달\\s*계약\\s*체결|핵심부품\\s*공급업체\\s*선정\\s*확정)"
      ]
    ],
    "tag": "로봇 부품 국산화 정책",
    "watch": "2030 목표·3조원 보도는 실제 집행과 다름. 정부 확정 예산·세부사업·공개 조달·고객 기업의 수주로 나눠 감시."
  },
  "robot_standardization": {
    "match": [
      "로봇|robot",
      "규격화|표준화|standardiz|작업.충전.생산"
    ],
    "official": [
      "산업통상부",
      "국가기술표준원",
      "ISO",
      "IEC",
      "한국로봇산업진흥원"
    ],
    "steps": [
      [
        "formal_standard",
        "(?:로봇|robot).{0,110}(?:표준\\s*제정\\s*완료|공식\\s*규격\\s*확정|표준\\s*발효)"
      ],
      [
        "industrial_adoption",
        "(?:로봇|robot).{0,100}(?:공장\\s*적용\\s*완료|실증\\s*검증\\s*통과)"
      ]
    ],
    "tag": "로봇 공정·충전 표준",
    "watch": "규격화 논의·표준 제안과 실제 발효·운영 현장 적용을 구분."
  },
  "hanwha_lion_robotics": {
    "match": [
      "한화|Hanwha",
      "라이온로보틱스|Lion\\s*Robotics"
    ],
    "official": [
      "한화시스템",
      "한화그룹",
      "Hanwha Systems",
      "라이온로보틱스",
      "Lion Robotics",
      "DART",
      "KIND"
    ],
    "steps": [
      [
        "share_investment_signed",
        "(?:700\\s*억|라이온로보틱스).{0,100}(?:신주인수\\s*계약\\s*체결|지분\\s*투자\\s*계약\\s*체결)"
      ],
      [
        "actual_payment",
        "(?:라이온로보틱스|Lion\\s*Robotics).{0,85}(?:투자금\\s*납입\\s*완료|지분\\s*취득\\s*완료)"
      ],
      [
        "military_supply",
        "(?:라이보|RAIBO).{0,90}(?:군\\s*납품\\s*계약\\s*체결|실제\\s*부대\\s*배치\\s*완료)"
      ]
    ],
    "tag": "한화·라이온로보틱스",
    "watch": "700억원은 투자 협상·추진 보도. 실제 투자계약·납입·방산 구매계약 전 확정 투자 또는 양산매출로 판정 금지."
  },
  "samhyun_actuator": {
    "match": [
      "삼현|Samhyun",
      "휴머노이드|액추에이터|모터"
    ],
    "official": [
      "삼현",
      "Samhyun",
      "DART",
      "KIND"
    ],
    "steps": [
      [
        "actuator_binding_order",
        "(?:휴머노이드|액추에이터).{0,115}(?:대량\\s*공급계약\\s*체결|구매\\s*발주\\s*확정|초도\\s*납품\\s*완료)"
      ],
      [
        "automation_capacity_50k",
        "(?:액추에이터|actuator).{0,90}(?:연간\\s*5\\s*만\\s*개\\s*생산\\s*달성|연\\s*5\\s*만개\\s*양산\\s*개시|생산자동화\\s*완료)"
      ]
    ],
    "tag": "삼현 액추에이터",
    "watch": "연 5만개는 자동화 경제성 기준. 2027년 로봇 500~1000대×대당 30개는 예상 1.5만~3만개, 실제 수주/출하 아님."
  },
  "atlas_sdi_2170": {
    "match": [
      "보스턴다이내믹스|Boston\\s*Dynamics|아틀라스|Atlas",
      "삼성SDI|Samsung\\s*SDI|LG에너지솔루션|2170"
    ],
    "official": [
      "삼성SDI",
      "Samsung SDI",
      "현대자동차그룹",
      "Hyundai Motor Group",
      "Boston Dynamics",
      "보스턴다이내믹스",
      "LG에너지솔루션"
    ],
    "steps": [
      [
        "named_battery_supplier",
        "(?:아틀라스|Atlas).{0,115}(?:배터리\\s*공급계약\\s*체결|공식\\s*공급사\\s*선정\\s*확정)"
      ],
      [
        "first_cell_delivery",
        "(?:아틀라스|Atlas).{0,115}(?:배터리\\s*셀\\s*초도\\s*납품\\s*완료|원통형\\s*셀\\s*첫\\s*출하\\s*완료)"
      ]
    ],
    "tag": "아틀라스 2170 배터리",
    "watch": "전문매체 전망: 2170 셀 70개×5000mAh, 로봇당 약 1.3kWh·삼성SDI 초기 대부분 공급. 회사 공식 발주·확정 실명은 아직 별도 검증."
  },
  "nvidia_korea_groot": {
    "match": [
      "엔비디아|NVIDIA",
      "GR00T|Isaac\\s*GR00T|AI\\s*Day\\s*Seoul|가상\\s*공장"
    ],
    "official": [
      "NVIDIA",
      "엔비디아",
      "현대자동차그룹",
      "두산로보틱스",
      "LG전자"
    ],
    "steps": [
      [
        "factory_robot_deployment",
        "(?:GR00T|그루트).{0,120}(?:생산\\s*현장\\s*실제\\s*배치\\s*완료|상용\\s*공급계약\\s*체결)"
      ],
      [
        "robot_model_jointproduct",
        "(?:GR00T|그루트).{0,115}(?:공동\\s*제품\\s*양산\\s*개시|고객\\s*검증\\s*통과)"
      ]
    ],
    "tag": "엔비디아 한국 피지컬 AI",
    "watch": "AI Day Seoul 발표·가상 공장 협력과 실제 제품 탑재·고객 구매·상용 배치를 분리."
  },
  "tesla_ai6_lpddr6": {
    "match": [
      "테슬라|Tesla",
      "AI[- ]?6|LPDDR6"
    ],
    "official": [
      "Tesla",
      "테슬라",
      "Tesla Investor Relations"
    ],
    "steps": [
      [
        "memory_spec_confirmed",
        "(?:AI[- ]?6|LPDDR6).{0,95}(?:공식\\s*사양\\s*확정|용량\\s*확정\\s*발표|memory\\s*spec\\s*confirmed)"
      ],
      [
        "production_memory_order",
        "(?:AI[- ]?6|LPDDR6).{0,95}(?:양산\\s*구매\\s*계약\\s*체결|칩\\s*양산\\s*시작)"
      ]
    ],
    "tag": "테슬라 AI6·LPDDR6",
    "watch": "216GB→144GB 용량 축소는 익명 업계 보도, 공식 설계 확정·로봇 실증 아님; 대역폭 유지 주장과 추론 성능 검증 구분."
  },
  "namuga_altera_sensor": {
    "match": [
      "나무가|Namuga",
      "알테라|Altera|로봇\\s*센서"
    ],
    "official": [
      "나무가",
      "Namuga",
      "Altera"
    ],
    "steps": [
      [
        "sensor_signed_order",
        "(?:로봇|robot).{0,90}(?:센서\\s*양산\\s*공급계약\\s*체결|고객\\s*공급\\s*개시)"
      ],
      [
        "joint_robot_prototype",
        "(?:나무가|Namuga).{0,90}(?:공동\\s*시제품\\s*개발\\s*완료|고객\\s*승인\\s*완료)"
      ]
    ],
    "tag": "나무가·알테라 센서",
    "watch": "공동개발과 실제 고객 센서 양산납품·규격 인증 및 매출 인식 구분."
  },
  "lg_robot_data_500k": {
    "match": [
      "LG전자|LG\\s*Electronics",
      "로봇|robot|데이터\\s*팩토리"
    ],
    "official": [
      "LG전자",
      "LG Electronics",
      "LG AI Research",
      "LG AI연구원"
    ],
    "steps": [
      [
        "data_hours_achieved",
        "(?:로봇|robot).{0,110}(?:50\\s*만\\s*시간\\s*(?:달성|확보\\s*완료)|500[,]?000\\s*hours?\\s*achieved)"
      ],
      [
        "paid_robot_deployment",
        "(?:로봇|robot).{0,100}(?:실제\\s*양산\\s*공급계약\\s*체결|상용\\s*현장\\s*배치\\s*개시)"
      ]
    ],
    "tag": "LG 로봇 학습 데이터",
    "watch": "2027년 50만 시간 목표는 데이터 확보 계획. 실제 데이터 누적·유료 배치·작업 성공률을 나눠 확인."
  },
  "toyota_humanoid_scale": {
    "match": [
      "토요타|Toyota",
      "휴머노이드|humanoid|로봇\\s*40\\s*만"
    ],
    "official": [
      "Toyota",
      "Toyota Motor Corporation",
      "토요타"
    ],
    "steps": [
      [
        "official_robot_program",
        "(?:휴머노이드|humanoid).{0,100}(?:공식\\s*도입\\s*계획\\s*확정|공장\\s*배치\\s*계약\\s*체결)"
      ],
      [
        "actual_factory_deployment",
        "(?:휴머노이드|humanoid).{0,110}(?:공장\\s*실제\\s*배치\\s*완료|양산\\s*라인\\s*가동\\s*개시)"
      ]
    ],
    "tag": "토요타 휴머노이드 공장",
    "watch": "전 세계 공장 40만대 투입은 기사 주장만으로 공식 실행계획 확정 금지; 공식 발표·공장·시기·실제 투입 분리."
  },
  "anthropic_fable_robotics": {
    "match": [
      "Anthropic|앤트로픽|Claude\\s*Fable",
      "RoboDojo|로봇\\s*제어|robotics"
    ],
    "official": [
      "Anthropic",
      "앤트로픽"
    ],
    "steps": [
      [
        "robot_paid_deployment",
        "(?:Fable|Claude).{0,115}(?:실제\\s*고객\\s*로봇\\s*상용\\s*배치|유상\\s*로봇\\s*제어\\s*계약\\s*체결)"
      ],
      [
        "real_robot_benchmark_verified",
        "(?:Fable|Claude).{0,120}(?:물리\\s*로봇\\s*독립\\s*검증\\s*완료|현장\\s*실증\\s*검증\\s*완료)"
      ]
    ],
    "tag": "앤트로픽 로봇 제어",
    "watch": "11/9 Fable 5.2 내부 RoboDojo Sim 64.9%는 모의 로봇 제어 성능. 실제 산업 배치·유료 고객 매출이 아님."
  },
  "google_gemini_robotics": {
    "match": [
      "Google\\s*DeepMind|구글\\s*딥마인드|Gemini\\s*Robotics",
      "Gemini\\s*Robotics\\s*2[.]5|Apollo\\s*2|메르세데스|Mercedes[- ]?Benz"
    ],
    "official": [
      "Google DeepMind",
      "Google",
      "Google Blog",
      "구글 딥마인드",
      "Apptronik",
      "Mercedes-Benz",
      "메르세데스-벤츠"
    ],
    "steps": [
      [
        "mercedes_factory_poc",
        "(?:Apollo\\s*2|아폴로\\s*2).{0,150}(?:96\\s*%\\s*(?:성공|success)|실증\\s*(?:성공|완료)|factory\\s*pilot\\s*completed)"
      ],
      [
        "commercial_customer_contract",
        "(?:Gemini\\s*Robotics\\s*2[.]5|Apollo\\s*2).{0,130}(?:유상\\s*공급계약\\s*체결|정식\\s*양산\\s*채택|고객\\s*유료\\s*배치\\s*완료)"
      ]
    ],
    "tag": "Gemini Robotics 2.5",
    "watch": "11/10 Google 공식: 200여 과제 평가, 과제별 성공률 30~100% 개선·시간 20~30% 단축, Apptronik Apollo 2·벤츠 라인 작업 96% 실증. 대량 양산 또는 계약은 미확인."
  },
  "samsung_research_robot": {
    "match": [
      "삼성리서치아메리카|Samsung\\s*Research\\s*America",
      "로봇|robotics|Dexterity|Reasoning"
    ],
    "official": [
      "Samsung Research America",
      "삼성전자",
      "Samsung"
    ],
    "steps": [
      [
        "robot_product_pilot",
        "(?:로봇|robot).{0,100}(?:실제\\s*제품\\s*탑재\\s*완료|유료\\s*고객\\s*실증\\s*완료)"
      ],
      [
        "robot_tech_supply",
        "(?:로봇|robot).{0,100}(?:공식\\s*양산\\s*공급계약\\s*체결|제품\\s*상용화\\s*완료)"
      ]
    ],
    "tag": "삼성 미국 로봇연구",
    "watch": "연구인력 모집 4개 분야(추론·손조작·데이터 효율·로봇시스템)는 R&D 확장 지표. 상용 공급계약·매출과 구분."
  },
  "mit_flex_robot_learning": {
    "match": [
      "MIT|매사추세츠공과대",
      "\\bFLEX\\b|로봇\\s*명령\\s*의도|robot\\s*reason"
    ],
    "official": [
      "MIT News",
      "MIT",
      "Massachusetts Institute of Technology",
      "New York University"
    ],
    "steps": [
      [
        "onsite_verified",
        "\\bFLEX\\b.{0,100}(?:실제\\s*로봇\\s*현장\\s*검증\\s*완료|유료\\s*실증\\s*완료)"
      ],
      [
        "licensed_commercially",
        "\\bFLEX\\b.{0,90}(?:상용\\s*기술이전\\s*계약\\s*체결|정식\\s*라이선스\\s*계약\\s*체결)"
      ]
    ],
    "tag": "MIT 로봇 의도 학습",
    "watch": "11/9 FLEX는 시뮬레이션에서 사람의 의도를 추론한 연구. 현장 신뢰성·유상 기술 이전은 별개."
  },
  "robot_stretch_diode": {
    "match": [
      "로봇|robot",
      "신축성\\s*다이오드|stretchable\\s*diode|촉각\\s*신호\\s*오류"
    ],
    "official": [
      "KAIST",
      "한국과학기술원",
      "서울대학교",
      "한국연구재단",
      "과학기술정보통신부"
    ],
    "steps": [
      [
        "industrial_qualified",
        "(?:다이오드|diode).{0,110}(?:산업\\s*고객\\s*성능\\s*인증\\s*완료|상용\\s*시제품\\s*검증\\s*완료)"
      ],
      [
        "mass_supply",
        "(?:다이오드|diode).{0,105}(?:양산\\s*공급계약\\s*체결|첫\\s*상용\\s*출하\\s*완료)"
      ]
    ],
    "tag": "신축성 로봇 촉각소재",
    "watch": "신호 오류 0.3%대 연구와 실제 양산 수율·내구성·고객 채택은 별개."
  },
  "daesung_kaiser": {
    "match": [
      "대성산업|Daesung\\s*Industrial",
      "카이저드라이브|Kaiser\\s*Drive|Kaiserdrive"
    ],
    "official": [
      "대성산업",
      "Daesung Industrial",
      "Kaiserdrive",
      "카이저드라이브"
    ],
    "steps": [
      [
        "actual_binding_exclusive",
        "(?:국내\\s*독점|exclusive).{0,100}(?:판매계약\\s*체결|유통\\s*계약\\s*체결|distribution\\s*agreement\\s*signed)"
      ],
      [
        "first_paid_order",
        "(?:액추에이터|actuator|Kaiserdrive).{0,105}(?:초도\\s*유상\\s*납품\\s*완료|실제\\s*고객\\s*발주\\s*확정)"
      ]
    ],
    "tag": "대성산업·카이저드라이브",
    "watch": "11/11 국내 독점 유통 관련 보도는 공급 규모·직접 매출·판매 지역 계약 원문 확인 필요; 업무협약과 구속력 있는 구매계약 구분."
  },
  "cowin_ess_robot_system": {
    "match": [
      "코윈로보틱스|Cowin\\s*Robotics",
      "ESS|에너지\\s*저장|로봇\\s*통합"
    ],
    "official": [
      "코윈로보틱스",
      "Cowin Robotics",
      "코윈테크"
    ],
    "steps": [
      [
        "binding_ess_robot_order",
        "(?:ESS|에너지\\s*저장).{0,100}(?:로봇\\s*통합\\s*시스템\\s*공급계약\\s*체결|정식\\s*수주\\s*확정)"
      ],
      [
        "system_customer_acceptance",
        "(?:로봇\\s*통합|ESS).{0,100}(?:납품\\s*검수\\s*완료|현장\\s*시운전\\s*완료)"
      ]
    ],
    "tag": "코윈 ESS 제조로봇",
    "watch": "ESS 기업향 로봇 통합 시스템 수주는 로봇 제조라인 자동화, 휴머노이드 직접 납품과 구분. 계약금액·검수·매출 확인."
  },
  "apple_robot_roadmap": {
    "match": [
      "애플|Apple",
      "가정용\\s*로봇|home\\s*robot|헤일로|Halo|옷\\s*개는\\s*로봇"
    ],
    "official": [
      "Apple",
      "Apple Newsroom",
      "애플"
    ],
    "steps": [
      [
        "official_device_announcement",
        "(?:home\\s*robot|가정용\\s*로봇|Halo).{0,110}(?:정식\\s*출시\\s*발표|제품\\s*사양\\s*공식\\s*공개)"
      ],
      [
        "real_robot_shipments",
        "(?:가정용\\s*로봇|home\\s*robot).{0,95}(?:실제\\s*판매\\s*개시|출하\\s*시작)"
      ]
    ],
    "tag": "애플 가정용 로봇",
    "watch": "2027년 130만원대 제품·옷 개는 로봇·Halo 제어 연구는 보도/연구 단계, 공식 양산·가격·출하 미확정."
  },
  "unichem_hyundai_robot": {
    "match": [
      "유니켐|Unichem",
      "로봇|robotics"
    ],
    "official": [
      "유니켐",
      "Unichem"
    ],
    "steps": [
      [
        "binding_robot_contract",
        "(?:로봇|robot).{0,105}(?:정식\\s*공급계약\\s*체결|양산\\s*납품\\s*시작)"
      ]
    ],
    "tag": "유니켐 로봇 신사업",
    "watch": "현대차 신차 3종 부품 사업과 별개의 로봇 신사업 매출을 구분하고 확정 계약에 한해 알림."
  }
}
for _group, _spec in NOV_2026_SIGNAL_TOPICS.items():
    _spec["match"] = tuple(_spec["match"])
    _spec["official"] = set(_spec["official"])
    _spec["steps"] = tuple(tuple(p) for p in _spec["steps"])
TOPICS.update(NOV_2026_SIGNAL_TOPICS)

NOV_2026_REPLAY_END = dt.date(2026, 11, 13)
NOV_2026_RELEASES = {
    "DIRECT_NOV10_GEMINI_ROBOTICS_25": {
        "title": "구글 Gemini Robotics 2.5 공식 발표, 벤츠·Apptronik Apollo 2 현장실증 96% 성공",
        "description": "Google DeepMind Gemini Robotics 2.5 발표. Apollo 2가 Mercedes-Benz 실제 생산라인에서 부품 분류 PoC를 96% 성공률로 수행했다. 이는 고객 양산계약이나 상용 매출은 아니다. 200개 이상 작업 평가, 과제별 성공률 30~100% 상승, 수행 속도 20~30% 개선.",
        "source": "Google DeepMind",
        "link": "https://deepmind.google/blog/gemini-robotics-2-5-accelerates-real-world-physical-intelligence/",
        "published": None,
        "nov_recovery": "google_poc_20261110",
    },
    "DIRECT_NOV10_WONIK_CPS_SHA_SIGNED": {
        "title": "원익홀딩스 원익로보틱스 3500억원 자회사 증자 주주간계약 체결 정정공시, 11월20일 납입 예정",
        "description": "2026-11-10 원익홀딩스 DART 접수번호 20261110900684 정정공시를 복수 공시 재게시와 뉴스핌 기사로 대조. 산업은행과의 주주간계약은 체결됐으나 3500억원 투자금 납입은 11/20 예정이고 11/12 통지로 날짜 변경 가능. 정부 1500억원 민간 2000억원; 시설 1839억원 운영 861억원 타법인 800억원. IPO 실패 시 모회사 매수청구권 연 4% 내부수익률, 관련 위약 시 10% 또는 15% 조건. DART 웹뷰어 직접 원문은 읽지 못했으며 실제 납입 완료 아님.",
        "source": "공시 재게시 대조(공식 원문 미열람)",
        "link": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261110900684",
        "published": None,
        "nov_recovery": "wonik_shareholders_reported_20261110",
    },
}

NOV_2026_QUERIES = (
    '(원익홀딩스 OR 원익로보틱스) (주주간계약 OR 3500억원 OR 납입 완료 OR 풋옵션 OR 로봇핸드 공장)',
    '(하이젠알앤엠 OR 삼현 OR 대동기어 OR 에스피지) (액추에이터 OR SDD OR 고객 발주 OR 양산 OR 증설)',
    '(레인보우로보틱스 OR Rainbow Robotics) (RB-Y2 OR FCC) (출하 OR 예약 OR 인증 OR 고객 검증)',
    '(클로봇 OR 한국기계연구원) (공간지능 RFM OR 휴머노이드 데이터 팩토리) (검증 OR 개방 OR 사업)',
    '(칩스앤미디어 OR Mobilint OR 모빌린트) (비디오 IP OR AV2 OR VVC OR 로봇) (공급계약 OR 로열티)',
    '(새만금 OR 김제) (로봇팜 OR 로봇 팜) (현대차 OR 대동 OR 국비 OR 착공)',
    '(한화시스템 OR 한화) (라이온로보틱스 OR 라이보) (투자 계약 OR 납입 OR 군 납품)',
    '(보스턴다이내믹스 OR Atlas) (삼성SDI OR LG에너지솔루션 OR 2170) (배터리 OR 공급계약 OR 출하)',
    '(NVIDIA OR 엔비디아 OR Google DeepMind) (GR00T OR Gemini Robotics 2.5 OR Apollo 2) (고객 OR 양산 OR 실증)',
    '(Anthropic OR Claude Fable OR MIT FLEX) (RoboDojo OR 로봇 제어 OR 실제 배치 OR 상용)',
    '(테슬라 OR Tesla) (AI6 LPDDR6 OR Cybercab Cybertruck) (생산 OR 공식 사양 OR 양산)',
    '(Apple OR 애플 OR Xiaomi OR 샤오미 OR Toyota OR 토요타) (home robot OR Halo OR CyberOne OR humanoid OR 휴머노이드) (공식 OR 배치 OR 계약)',
    '(LG전자 OR 삼성리서치아메리카) (로봇 데이터 팩토리 OR 50만시간 OR 로봇 추론 OR Dexterity)',
    '(나무가 OR 대성산업 OR 카이저드라이브 OR 코윈로보틱스) (로봇 센서 OR 액추에이터 OR ESS 로봇) (계약 OR 출하)',
    '(정부 OR 산업통상부 OR 국가기술표준원) (피지컬 AI 핵심부품 국산화 OR 로봇 표준 OR 로봇 규격화) (예산 OR 조달 OR 발효)',
    '(로봇 OR robot) (신축성 다이오드 OR stretchable diode OR 촉각 신호 오류) (고객 검증 OR 상용화)',
)

RESEARCH_ONLY = re.compile(
 r"\b(?:not|no|without|not yet|unconfirmed|denied|would|could|may|"
 r"plans?|planning|planned|expect(?:s|ed)?|target(?:s|ed)?|aims?|"
 r"considering|proposed)\b|미확인|아직|부인|미체결|계획|목표|예정|"
 r"전망|추진|검토|협의|가능성|관심|시연|견적요청|채용",
 re.I)
# Keep source exact: scraped media headlines never masquerade as an
# issuer-issued first-party contract or clinical decision.
QUERIES = (
 '(삼성서울병원 OR "Samsung Medical Center") '
 '(휴머노이드 OR 로봇수술 OR surgical robot) '
 '(IRB 승인 OR 임상시험 개시 OR first patient OR 로봇 수술 실제 투입)',
 '(빅웨이브로보틱스 OR "BIGWAVE Robotics" OR 씨피시스템) '
 '(레인보우로보틱스 OR "Rainbow Robotics") '
 '(유료 실증 OR signed contract OR 로보킷 양산 OR 미국 납품 OR 반복 발주)',
 '(네오오토 OR Neoauto OR 알멕 OR ALMAC) '
 '(감속기 OR 로버 OR Boston Dynamics OR 보스턴다이내믹스) '
 '(신뢰성 시험 통과 OR 공급사 선정 OR 정식 발주 OR 공급계약 OR 첫 출하)',
 '(해치텍 OR Hatchtec OR 아모그린텍 OR Amogreentech OR ByteDance OR 바이트댄스) '
 '(인코더 OR 로봇 관절 OR 휴머노이드 OR 자성소재) '
 '(고객 인증 OR 양산 계약 OR first shipment OR production started)',
 '(OpenAI OR 오픈AI) (data center OR 데이터센터) (robot OR 로봇) '
 '(deployed OR 실제 투입 OR construction contract OR 유상 계약)',
)

def topic(text: str) -> str:
    for label,spec in TOPICS.items():
        if all(re.search(pattern,text,re.I) for pattern in spec["match"]):
            return label
    return ""

def achieved(item: dict, group: str) -> str:
    spec=TOPICS.get(group)
    if not spec or str(item.get("source") or "").strip() not in spec["official"]:
        return ""
    text=" ".join(str(item.get(k) or "") for k in ("title","description"))
    for stage,pattern in spec["steps"]:
        for found in re.finditer(pattern,text,re.I):
            near=text[max(0,found.start()-30):found.end()+22]
            if RESEARCH_ONLY.search(near):
                continue
            return stage
    return ""

def install(base) -> None:
    prev={f:getattr(base,f) for f in (
        "query_news","topic_group","score","key","category","meaning","risk",
        "verification","tag_for","select_diverse"
    )}
    labels={g:f"{spec['tag']} · 공식 단계 진전" for g,spec in TOPICS.items()}
    def query(q):
        if q in NOV_2026_RELEASES:
            if base.NOW.astimezone(base.KST).date() > NOV_2026_REPLAY_END:
                return []
            return [dict(NOV_2026_RELEASES[q])]
        return prev["query_news"](q)
    def group(text):
        return topic(text) or prev["topic_group"](text)
    def score(item):
        body=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
        t=topic(body)
        if item.get("nov_recovery"):
            return 44 if item["nov_recovery"] == "google_poc_20261110" else 39
        return (38 if achieved(item,t) else 0) if t else prev["score"](item)
    def key(item):
        body=" ".join(str(item.get(k) or "") for k in ("title","description","source"))
        t=topic(body)
        if not t:return prev["key"](item)
        if item.get("nov_recovery") == "google_poc_20261110":
            return hashlib.sha256(f"robot-coverage-v1|{t}|mercedes_factory_poc".encode()).hexdigest()
        if item.get("nov_recovery") == "wonik_shareholders_reported_20261110":
            return hashlib.sha256(f"robot-coverage-v1|{t}|shareholder_signed|reported-20261110".encode()).hexdigest()
        stage=achieved(item,t) or "baseline"
        raw=f"robot-coverage-v1|{t}|{stage}"
        return hashlib.sha256(raw.encode()).hexdigest()
    def category(text,t):
        return labels[t] if t in TOPICS else prev["category"](text,t)
    def meaning(cat):
        t=next((g for g,v in labels.items() if v==cat),None)
        if t:
            return ("기업·기관의 공식 새 이정표 확인 단계. " + TOPICS[t]["watch"]
                    + " / 계획·시연·고객 검증·계약·양산·인식 매출은 구분합니다.")
        return prev["meaning"](cat)
    def risk(cat):
        if cat in labels.values():
            return ("업계 보도를 확정 계약·매출로 오인하지 않습니다. "
                    "고객 검수·정밀도·수율·내구성·실제 출하·대금 회수 및 인증을 점검합니다.")
        return prev["risk"](cat)
    def verification(item,t,text):
        if item.get("nov_recovery") == "wonik_shareholders_reported_20261110":
            return ("DART 20261110900684 복수 공시 재게시·금융위원회 8월 승인 자료 대조. "
                    "공식 DART 웹뷰어 직접 열람 실패; 11/20 실제 납입 미확인.")
        if item.get("nov_recovery") == "google_poc_20261110":
            return ("Google DeepMind 2026-11-10 공식 블로그 직접 발표; 96%는 현장 실증 "
                    "성공률, 상용 매출/반복수주 미확인.")
        if t in TOPICS:
            return ("기업·기관 명의 공식 신규 단계 보도에 한정한 기계판정 / "
                    "고객·금액·원문·시험 조건 독립 확인 전")
        return prev["verification"](item,t,text)
    def tag(t):
        return TOPICS[t]["tag"] if t in TOPICS else prev["tag_for"](t)
    def select(items,seen,force,limit):
        selected=prev["select_diverse"](items,seen,force,limit)
        candidates=items if force else [x for x in items if x.get("key") not in seen]
        new=next((x for x in candidates if x.get("group") in TOPICS
                  and x.get("score",0)>=11),None)
        priority=[x for x in candidates if x.get("nov_recovery") and x.get("score",0)>=11]
        for x in reversed(priority):
            if not any(y.get("key")==x.get("key") for y in selected):
                selected=[x,*selected][:limit]
        if new and not any(x.get("key")==new.get("key") for x in selected):
            return [new,*selected][:limit]
        return selected
    base.query_news=query
    base.topic_group=group
    base.score=score
    base.key=key
    base.category=category
    base.meaning=meaning
    base.risk=risk
    base.verification=verification
    base.tag_for=tag
    base.select_diverse=select
    for q in (*QUERIES, *NOV_2026_RELEASES, *NOV_2026_QUERIES):
        if q not in base.QUERIES:base.QUERIES.append(q)
    # Pure no-network / no-send invariants to prevent accidental claims
    # of orders from historical demo, engineering and recruiting stories.
    for text in (
        "빅웨이브로보틱스 레인보우로보틱스 미국 350건 시연 상담",
        "삼성서울병원 수술 보조 로봇 2029년 임상시험 계획",
        "네오오토 로버 감속기 실물 조립 착수",
        "알멕 보스턴다이내믹스 RFQ 견적요청서",
        "씨피시스템 레인보우로보틱스 로보킷 케이블 시제품 공급",
        "해치텍 로봇 관절 인코더 기술 적용 가능성",
        "바이트댄스 휴머노이드 로봇 대규모 인력 채용",
    ):
        t=topic(text)
        if t:
            row={"title":text,"description":"계약·실제 양산 확정 미확인","source":"일반언론"}
            assert score(row)==0,(text,t,score(row))
