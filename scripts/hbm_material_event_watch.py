"""One-time verified recovery of important Nov 2026 HBM-adjacent events.
This is an extension of the existing Rubin HBM Actions -> Python -> Telegram path.
It never sends directly. hbm_delivery.py exclusively acknowledges and commits state.
"""
from __future__ import annotations

import copy
import html
import json
import pathlib
import re
import urllib.request
from datetime import datetime, date
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
PENDING = ROOT / "out/rubin_hbm_pending_state.json"
BASELINE = ROOT / "out/hbm_before_rubin.json"
ALERT = ROOT / "out/rubin_hbm_alert.md"
AUDIT = ROOT / "out/hbm_material_event_coverage.json"
BREAK = "<<<TELEGRAM_MESSAGE_BREAK>>>"
VERSION = 1
MAX_AGE_DAYS = 14

# Fixed independently traceable facts, not automatic promotions to issuer contracts.
# Fall-back copies/reprints carry their original lineage rather than pretending to
# be independent corroboration.
REPORTS = (
    {
        "key": "20261112_samsungsem_glass_onepass_loi",
        "date": "2026-11-12",
        "group": "glass",
        "label": "삼성전기 평택 유리기판 원패스 라인 구매의향서",
        "sources": (
            ("전자신문 원보도", "https://www.etnews.com/20261112000021?m=1", "원보도"),
            ("전자신문 원보도", "https://www.etnews.com/20261112000021", "동일 원보도"),
        ),
        "need": (("삼성전기",), ("유리기판",), ("LOI", "구매의향서"),
                 ("LPKF",), ("태성",), ("싸이맥스",), ("에스디옵틱스",),
                 ("이노메트리",), ("테크밸리",), ("HB테크놀러지",)),
        "facts": (
            "2026년 10월 장비사 선정·구매의향서 전달을 보도, 2027년 하반기 장비 반입·평택 설치 목표.",
            "7곳: LPKF(유리관통전극 레이저), 태성(식각), 싸이맥스(이송), 에스디옵틱스(광학), 이노메트리·테크밸리(엑스레이·3차원 검사), HB테크놀러지(검사).",
            "2028년 양산 목표와 글로벌 고객 평가 단계는 별개; 브로드컴은 보도상 후보.",
        ),
        "caution": "LOI는 확정 구매계약·발주금액·장비 반입·양산매출이 아니며 장비사 공식 확인은 비공개.",
    },
    {
        "key": "20261112_skhynix_hbm4_reported_yield_over70",
        "date": "2026-11-12",
        "group": "hbm",
        "label": "SK하이닉스 HBM4 수율 70% 초과",
        "sources": (
            ("조선비즈 원보도", "https://biz.chosun.com/it-science/ict/2026/11/12/E5T4MINR45CA7LR5ID7H7VRQBA/?outputType=amp", "원보도"),
            ("DIGITIMES의 조선비즈 재인용", "https://www.digitimes.com/topic/semiconductors/memory_chips/", "재인용"),
        ),
        "need": (("SK하이닉스", "SK Hynix"), ("HBM4",), ("수율", "yield"), ("70%", "70 percent")),
        "facts": ("수율이 70%를 넘었다는 11월 12일 업계 소식통 보도.",),
        "caution": "SK하이닉스 공식 수율 공개 없음; 전공정·적층·패키징·최종 양품 수율의 분모 미확인, 2개 독립 출처로 과대평가 금지.",
    },
    {
        "key": "20261112_samsung_onyang_hbm_202806_acceleration",
        "date": "2026-11-12",
        "group": "hbm",
        "label": "삼성 온양 HBM 5라인 2028년 6월 조기 가동 목표",
        "sources": (
            ("머니투데이 원보도", "https://www.mt.co.kr/index.php/industry/2026/11/12/2026111211085487358", "원보도"),
            ("아이뉴스24 별도 보도", "https://inews24.com/view/2025485", "별도 보도"),
        ),
        "need": (("온양",), ("HBM",), ("2028",), ("6월",), ("46조",)),
        "facts": (
            "온양 HBM 패키징 5라인 가동 목표: 기존 2029년 → 2028년 6월로 조기화 보도.",
            "온양 관련 46조원 순차 투자 보도(건설 6조원·장비 40조원); 삼성 충청권 전체 투자계획과 중복 합산 금지.",
        ),
        "caution": "착공·설비투자와 고객 검증·최초 가동·양품 출하·매출 인식은 서로 다른 단계.",
    },
    {
        "key": "20261113_samsung_8inch_reported_2029_umc",
        "date": "2026-11-13",
        "group": "hbm",
        "label": "삼성 8인치 파운드리 철수 목표 2029년·UMC 일부 외주화",
        "sources": (
            ("DIGITIMES 원보도(DealSite 인용)", "https://www.digitimes.com/news/a20261112VL214.html", "DealSite→DIGITIMES 재인용"),
            ("한국신용신문 재인용", "https://www.creditnews.kr/news/articleView.html?idxno=32565", "재인용"),
        ),
        "need": (("삼성", "Samsung"), ("8인치", "8-inch"), ("2029",), ("UMC", "United Microelectronics")),
        "facts": ("2029년 말 철수 목표 보도는 기존 2030년 전망보다 1년 앞섰으며 일부 물량 UMC 외주화 보도.",),
        "caution": "업계·재인용 보도 단계. 삼성·UMC 공식 최종 철수 결정·외주 계약 물량·금액 미확인; HBM4와 별개의 8인치 성숙공정.",
    },
    {
        "key": "20261112_intel_kai_23_company_alliance",
        "date": "2026-11-12",
        "group": "intel",
        "label": "인텔 K-AI 풀스택 연합 초기 23개 참여사",
        "sources": (
            ("전자신문 원보도", "https://www.etnews.com/20261112000262", "원보도"),
            ("연합뉴스 별도 보도", "https://www.yna.co.kr/view/AKR20261112076500017", "별도 보도"),
        ),
        "need": (("인텔", "Intel"), ("K-AI",), ("23",), ("얼라이언스", "Alliance")),
        "facts": (
            "2026년 11월 12일 발표; 인텔 포함 초기 참여사 23곳 보도, 리벨리온·딥엑스·업스테이지·메가존클라우드 등 참여.",
            "목적: 국산 서버 기반 AI 칩·모델·소프트웨어·클라우드 연계와 소버린·피지컬 AI 협력.",
        ),
        "caution": "연합 참여는 인텔 GPU 구매계약·국산 NPU 대량 발주나 양산매출 확정이 아님.",
    },
    {
        "key": "20261112_intel_hbmfree_lpddr_inference_proposal",
        "date": "2026-11-12",
        "group": "intel",
        "label": "인텔 HBM 대신 저전력 D램 활용하는 추론 GPU 전략",
        "sources": (
            ("뉴스핌 원보도", "https://ir.newspim.com/news/view/20261112000679", "원보도"),
            ("DIGITIMES 보도", "https://www.digitimes.com/topic/semiconductors/memory_chips/", "별도 보도"),
        ),
        "need": (("인텔", "Intel"), ("HBM",), ("LPDDR", "저전력"), ("추론", "inference")),
        "facts": ("HBM을 탑재하지 않고 저전력 D램을 쓰는 일부 추론용 GPU 전략·국내 맞춤형 설계 및 파운드리 협력 제안.",),
        "caution": "제품군·워크로드별 대안. 모든 AI GPU에서 HBM이 사라지거나 전체 HBM 비트 수요가 줄었다는 확정 신호 아님.",
    },
    {
        "key": "20261112_intel_skhynix_shared_memory_collaboration",
        "date": "2026-11-12",
        "group": "intel",
        "label": "인텔·SK하이닉스 AI 공유 메모리 구조 협력",
        "sources": (
            ("조선비즈 현장 보도", "https://biz.chosun.com/en/en-it/2026/11/12/R2O5YIDCWNESZNXXKMOITVFQIU/", "원보도"),
            ("DIGITIMES 보도", "https://www.digitimes.com/topic/semiconductors/memory_chips/", "별도 보도"),
        ),
        "need": (("Intel", "인텔"), ("SK hynix", "SK하이닉스"), ("memory", "메모리"), ("shared", "share", "공유", "rack", "pool")),
        "facts": ("여러 AI 서버가 대용량 메모리를 공유하는 '메모리 랙' 등 메모리 중심 구조 협력 방향 보도.",),
        "caution": "CXL 실증·호환성·실제 고객 채택·정식 제품 공급계약·매출액은 개별 확인 필요.",
    },
    {
        "key": "20261112_semianalysis_post_jensen_supply_non_nvidia_2028_gt70",
        "date": "2026-11-12",
        "group": "allocation",
        "label": "SemiAnalysis: 젠슨 사임 이후 HBM4 공급 우선순위·2028년 비엔비디아 비중 전망",
        "sources": (
            ("SemiAnalysis 11월 12일 원문",
             "https://newsletter.semianalysis.com/p/nvidia-and-the-world-without-jensen", "원문·리서치 추정"),
            ("원문 인용 해설: P Equity Research",
             "https://pequityresearch.substack.com/p/nvidias-future-my-question-marks", "원문 재인용·독립 전망 아님"),
        ),
        "need": (("Nvidia", "엔비디아"), ("SK Hynix", "SK하이닉스"),
                 ("2028",), ("70%", "70 percent"), ("HBM4",)),
        "facts": (
            "확정 사실: NVIDIA는 11월 12일 젠슨 황 사임·콜레트 크레스 임시 CEO 선임 발표(기존 NVIDIA 임원변화 감시에서 별도 관리).",
            "SemiAnalysis 전망: 젠슨 퇴임 뒤 메모리 공급사의 NVIDIA 우선 배정 약화, 2028년 비엔비디아 AI 칩 고객이 전체 공급능력의 70% 초과를 확보할 가능성.",
            "중요한 분모: 원문은 'total capacity'라고 표현하며 이를 전 세계 HBM4 생산능력 중 70% 확정 배정으로 볼 근거는 없습니다.",
            "2027년 SK하이닉스 HBM4 1Gb당 계약가격 추정: NVIDIA 3.0달러/Gb~3.3달러/Gb, AMD·Broadcom·Amazon·Google 3.7달러/Gb~4.1달러/Gb.",
        ),
        "caution": "모두 SemiAnalysis 추정·전망으로 계약확정·고객별 구매물량·SK하이닉스 공시 평균판매단가 아님; 공급사 확정 주문·고객별 생산능력·양산 출하 변화는 공식 자료로 별도 판정.",
    },
    {
        "key": "20261116_skhynix_2026q3_geo_customer_concentration",
        "date": "2026-11-16",
        "group": "financial",
        "label": "SK하이닉스 2026년 1~9월 미국·중국 매출과 익명 고객 집중도",
        "sources": (
            ("한국경제 분기보고서 인용 분석", "https://www.hankyung.com/article/2026111603647", "공시 인용 언론 보도"),
            ("이투데이 지역·고객 매출 보도", "https://www.etoday.co.kr/news/view/2648918", "별도 보도"),
            ("연합뉴스 원보도", "https://www.yna.co.kr/view/AKR20261116152900003", "별도 보도"),
        ),
        "need": (
            ("SK하이닉스", "SK hynix"),
            ("236조5105", "236조5천105", "236조 5,105", "236조5,105"),
            ("147조7392", "147조7천392", "147조7,392", "147조 7,392"),
            ("62.5%",),
            ("34조9778", "34조9천778", "34조9,778", "34조 9,778"),
            ("23조8509", "23조8천509", "23조8,509", "23조 8,509"),
            ("56조1378", "56조1천378", "56조1,378", "56조 1,378"),
        ),
        "facts": (
            "2026년 1~9월 연결 매출 236조5,105억원(전년 같은 기간 64조3,200억원 대비 +267.7%).",
            "미국 매출 45조1,802억원→147조7,392억원(+102조5,590억원, +227.0%).",
            "미국 매출 비중은 전년 약 70.2%→62.5%(-7.8%p). 미국 매출액 급증과 비중 하락을 구분.",
            "중국 매출 11조7,489억원→56조1,378억원(+377.8%), 올해 1~9월 전체의 23.7%.",
            "공시상 익명 최대 고객 '가': 17조3,551억원→34조9,778억원(+101.5%), 전체의 14.8%; 엔비디아는 언론·업계 추정으로만 표기.",
            "공시상 익명 주요 고객 '나': 23조8,509억원(10.1%), 고객 실명 미공개. 두 고객 합계 58조8,287억원(24.9%).",
            "제품 구성 해석: 미국은 HBM·서버 D램, 중국은 LPDDR·낸드 수요 중심이라는 언론 보도이며 지역별 제품별 확정 매출은 미공개.",
        ),
        "caution": "지역별 외부매출을 엔비디아향 확정 매출로 환산 금지. 2029년까지 '완판' 컨퍼런스콜 발언과 14개 고객이 체결한 2027~2028 전체 생산능력 50% 초과 장기공급계약은 별도 단계. 공시 접수 20261116001715 원본 웹뷰어 직접 열람 제한으로 언론 인용 수치를 대조.",
    },
    {
        # SEC filed 6-K 2026-11-16: https://www.sec.gov/Archives/edgar/data/2120882/000119312526461909/d166755d6k.htm
        "key": "20261116_skhynix_2026q3_capex_rnd_cumulative",
        "date": "2026-11-16",
        "group": "financial",
        "label": "SK하이닉스 누적 설비투자 31조·연구개발비 10조 돌파",
        "sources": (
            ("이투데이 분기보고서 자산취득·연구개발비", "https://www.etoday.co.kr/news/view/2648882", "공시 인용 언론 보도"),
            ("연합뉴스 설비투자·연구개발비", "https://www.yna.co.kr/amp/view/AKR20261116160500003", "별도 보도"),
            ("전자신문 설비투자·연구개발비", "https://www.etnews.com/20261116000525", "별도 보도"),
        ),
        "need": (
            ("SK하이닉스", "SK hynix"),
            ("10조948", "10조 948", "10조9백48"),
            ("31조2163", "31조2160", "31조2천160", "31조 2163", "31조2,160"),
            ("설비투자", "시설투자"),
        ),
        "facts": (
            "2026년 1~9월 유형자산 취득 31조2,163억200만원(미국 SEC 제출 6-K 재무제표 주석: 31,216,302백만원), 전년 연간 30조1,728억원을 초과. 같은 보고서 투자현황표는 31,216십억원(31조2,160억원)으로 표시해 금액 차이는 단위·정밀도 차이.",
            "1~9월 연구개발비 10조948억원, 전년 같은 기간 4조6,473억원 대비 +117.2%, 2025년 연간 6조7,325억원 대비 +49.9%.",
            "2026년 3분기에만 설비투자 약 13조6,213억원, 연구개발비 4조520억원; 1~9월 매출 대비 연구개발비 비중 4.3%.",
            "청주 M15X HBM4 생산능력 확대, 용인 신규 공장 투자 진행 중. 장비 반입·시험생산·고객 승인·양산 출하·매출 인식은 별도 확인.",
        ),
        "caution": "설비투자 집행은 HBM4 신규수주·가동률·잉여현금흐름 증가의 확정 증거가 아닙니다. 미 SEC 제출 6-K의 투자현황표(십억원 단위)와 유형자산 주석(백만원 단위) 표시 차이 약 3억원으로 확인; DART 국문 원문 직접 열람은 제한됨.",
    },
    {
        "key": "20261116_kiwoom_2028_conventional_memory_hbm_divergence",
        "date": "2026-11-16",
        "group": "cycle",
        "label": "키움증권: 2027년 범용 DRAM·NAND 공급과잉과 2028년 HBM 성장의 반대 방향",
        "sources": (
            ("키움증권 전망 11월 16일 재정리", "https://theddari.com/trends/telegram/3692986659/13638", "키움 자료 인용 2차 요약·원본 PDF 직접 검증 아님"),
            ("키움 보고서 해설", "https://arod2750.cafe24.com/doc/blog-naver-blog-dc56bd13aed5d90e-aae184a1dc2e", "리서치 내용 별도 정리·원본 직접 검증 아님"),
        ),
        "need": (
            ("키움증권",), ("2028",), ("DRAM", "D램", "디램"),
            ("NAND", "낸드"), ("-54%", "−54%"), ("-47%", "−47%"),
            ("HBM",), ("81조",), ("450조",),
        ),
        "facts": (
            "2026년 11월 16일 키움증권 박유악 반도체 산업 전망: NAND는 2027년 상반기, 범용 DRAM은 2027년 하반기 공급과잉 진입을 예상. 발표된 실제 수급 전환이나 확정 계약가격이 아닌 증권사 모델.",
            "DRAM 공급과잉률 모델: 2026년 -2.8%→2027년 -0.5%→2028년 +4.9%; 가격 연간 전망 +250%→+17%→-54%(2028년 전년 대비).",
            "NAND 공급과잉률 모델: 2026년 -5.8%→2027년 -4.1%→2028년 +8.4%; 가격 연간 전망 +289%→-3%→-47%(2028년 전년 대비).",
            "HBM 전체 시장 규모는 2026년 81조원(+55%)→2027년 234조원(+188%)→2028년 450조원(+92%)으로 확대 예상. 삼성전자·SK하이닉스·Micron 합산 확정 매출과는 다른 시장 추정치.",
            "원문 캡처상 CXMT의 2028년 HBM 매출은 10조~20조원 수준 예상으로, 시장점유율 10~20% 또는 확정 수주라는 뜻이 아님.",
            "반대 전망: SK하이닉스 2026년 10월 28일 공식 발표는 2027~2028년 총 생산능력 50% 초과의 14개 고객 장기계약과 2030년까지 공급 부족 전망을 제시. 기존 Goldman Sachs 2028년 공급부족 전망과도 방향이 상충.",
            "선행 확인: 스마트폰·PC 고객 메모리 재고와 탑재량, DRAM/NAND 계약가·현물가, CXMT·YMTC 웨이퍼 실제 가동량·수율, HBM4 고객 승인·실제 출하·장기계약 가격·빅테크 설비투자. 가격 전망 자체로 확정 공급과잉 경보 발송 금지.",
        ),
        "caution": "키움 공식 보고서 게시 https://bbn.kiwoom.com/rfCI5748 는 확인했으나 원본 PDF 전문 직접 확인은 제한됨. 수치는 사용자 캡처·2차 정리 근거의 증권사 예상으로만 발송. 첨부글의 HBM 출하비트 15%→가격 -2%, 20%→가격 -10%는 글쓴이의 별도 민감도 가정이며 키움 확정 전망 아님. 동일 기사 재게시·과거 전망을 실제 공급과잉 발생으로 재알림하지 않음.",
    },
    {
        "key": "20261118_trendforce_roadshow_hbm4_per_gb_price",
        "date": "2026-11-18",
        "group": "roadshow",
        "label": "TrendForce 로드쇼: HBM4 제품별 Gb당 가격과 HBM4E 초기 제시가",
        "sources": (
            ("조선비즈 로드쇼 현장 취재", "https://biz.chosun.com/it-science/ict/2026/11/18/62CPYNPGWNG4BIG5N2WUWKGKJE/", "현장 취재 원보도·TrendForce 발표 인용"),
            ("ZDNet Korea 로드쇼 취재", "https://zdnet.co.kr/view/?no=20261118120439", "별도 현장 취재·TrendForce 발표 인용"),
            ("IT之家 ZDNet 재인용", "https://www.ithome.com/1/028/814.htm", "ZDNet 재인용·독립 2차 근거 아님"),
        ),
        "need": (
            ("HBM4",), ("HBM4E",), ("2.05",),
            ("3~5.5", "3∼5.5", "3-5.5", "3–5.5", "3至5.5", "3 to 5.5"),
            ("5달러", "5달러", "5 美元", "5 dollars", "5달러"),
        ),
        "facts": (
            "2026년 11월 18일 TrendForce 서울 로드쇼 전망: HBM4 Gb당 2026년 2.05달러(약 2,733원) 이상→2027년 3~5.5달러(약 3,999~7,332원), HBM4E는 5달러(약 6,665원) 초과의 초기 제시·논의 단계; 회사별 확정 납품가격 아님.",
            "동일 2.05달러(약 2,733원) 기준 단순 계산으로 2027년 HBM4 3~5.5달러(약 3,999~7,332원)는 +46~168%이고, 2026년 2.05달러(약 2,733원) '이상'인 실제 기준가격에서는 상승률이 더 낮을 수 있음. 따라서 전체 가격대가 100% 이상 상승한다고 단정 금지.",
            "TrendForce 9월 29일 별도 공식 전망: 2027년 전체 HBM 혼합 평균판매단가 +121%; 11월 로드쇼 현장에서는 기가비트당 2026년 1.67달러(약 2,226원)→2027년 3.70달러(약 4,932원), 계산상 +121.6%(기사 반올림 +122%) 제시. HBM4 개별 제품가격과 전체 HBM 혼합 평균판매단가는 분모가 다름.",
            "가격 설정의 선행지표: HBM4 계약 갱신·고객별 가격/용량·8단과 12단 비중·고객 검증·실제 양산 출하를 확인; 기존 TrendForce +121% 전망의 소수점 반올림을 독립 신규 상향으로 중복 송출 금지.",
            "원화는 2026년 11월 18일 서울외국환중개 15:30 기준 1달러=1,333.00원으로 환산한 발표 당일 참고액이며 실행 시점 환율이나 공식 계약가격이 아님.",
        ),
        "caution": "회사 확정 가격·HBM4E 정식 고객 인증·실제 2027년 매출 아님. TrendForce 공식 행사 소개(https://seminar.trendforce.com/Roadshow/Korea2026-11/US/index/)와 9/29 공식 보고서(https://www.trendforce.com/presscenter/news/20260929-13255.html)에서 방향은 확인되지만, 11/18 행사 유료 발표자료 전체 표는 직접 확보하지 못함.",
    },
    {
        "key": "20261118_trendforce_roadshow_dram_quarter_price_path",
        "date": "2026-11-18",
        "group": "roadshow",
        "label": "TrendForce: 2027년 범용 DRAM 분기별 가격 증가율·NAND 2분기 하락 시나리오",
        "sources": (
            ("ZDNet Korea 서울 로드쇼 취재", "https://zdnet.co.kr/view/?no=20261118120439", "현장 취재 원보도"),
            ("IT之家 ZDNet 인용 비교", "https://www.ithome.com/1/028/814.htm", "원기사 재인용·독립 출처 아님"),
            ("동일 기사 원문 인용 메모", "https://theddari.com/trends/telegram/3692986659/13726", "ZDNet 원기사 요약·독립 출처 아님"),
        ),
        "need": (
            ("DRAM", "D램", "디램", "通用 DRAM"), ("NAND", "낸드", "闪存"),
            ("10~15", "10-15", "10～15", "10–15"),
            ("5~10", "5-10", "5～10", "5–10"),
            ("3~8", "3-8", "3～8", "3–8"),
            ("0~5", "0-5", "0～5", "0–5"),
            ("2분기", "第二季", "2027Q2", "Q2 2027", "Q2"),
        ),
        "facts": (
            "TrendForce 11월 18일 로드쇼 전망: 범용 DRAM 평균판매단가 전분기 대비 2026년 4분기 +10~15%, 2027년 1분기 +5~10%, 2분기 +3~8%, 3분기 +0~5%, 4분기 +0~5%; 전분기 대비 상승률 둔화이지 연간 가격 하락으로 확정한 것이 아님.",
            "전체 NAND 계약가격 하락 개시 2027년 2분기 전망은 기존 2027년 하반기 완화 전망보다 앞섰지만, 11월 17일 TrendForce 연구 요약에서 기존 감시가 이미 동일 분기 변경을 확인. 11월 18일 발언은 독립 신규 계약 취소·실제 가격 하락으로 중복 송출하지 않음.",
            "원인: AI 서버·HBM 생산을 위한 DRAM 웨이퍼 전환으로 범용 DRAM 공급 제약; NAND는 YMTC 공정 전환·중국 생산능력 확대와 소비자 수요 약세로 2027년 2분기 이후 압박 가능. 계약가·현물가·고객별 SSD 가격의 시점과 분모는 분리.",
            "선행 확인: TrendForce 분기별 계약가 수정·월별 DDR5/DDR4 현물가·YMTC 실제 비트 생산량·중국/북미 기업용 SSD 고객 주문과 재고. 전망과 실제 계약·검수·매출 인식을 혼동하지 않음.",
        ),
        "caution": "11월 17일 선행 NAND 2Q27 예고는 data/memory_spot_cycle_watch_state.json의 기존 확정 전송 사건과 중복되지 않도록 재발송 키를 만들지 않음. 이 항목의 신규 가치는 11/18 현장 DRAM 분기별 수치·발언 확인에 있음.",
    },
    {
        "key": "20261118_trendforce_roadshow_hbm_mix_customer_tsv",
        "date": "2026-11-18",
        "group": "roadshow",
        "label": "TrendForce: HBM4 비중·구글/NVIDIA 수요·삼성/SK TSV 생산능력 전망",
        "sources": (
            ("조선비즈 HBM 제품구성·고객·TSV 현장 보도", "https://biz.chosun.com/it-science/ict/2026/11/18/62CPYNPGWNG4BIG5N2WUWKGKJE/", "현장 취재 원보도"),
            ("조선비즈 동일 취재 영문판", "https://biz.chosun.com/en/en-it/2026/11/18/YCDJTCE5CVFFND7AW5NJRISJDA/", "같은 취재 영문 전재·독립 근거 아님"),
        ),
        "need": (
            ("HBM4",), ("31%",), ("51%",), ("22%",), ("42%",),
            ("18만", "180,000", "180000"), ("28만", "280,000", "280000"),
            ("20만", "200,000", "200000"), ("26만", "260,000", "260000"),
        ),
        "facts": (
            "TrendForce의 2026→2027년 전체 HBM 출하 구성 전망: 고가 HBM4 비중 31%→51%(+20%p); 2027년 하반기에는 8단 제품이 12단 제품보다 널리 사용될 가능성. 제품구성 변화로 HBM 혼합 평균판매단가가 높아지는 효과와 동일 제품의 가격 인상을 분리.",
            "HBM 최종 수요처 비중 전망: 구글 TPU용 등 2026년 22%→2027년 31%(+9%p), NVIDIA는 2027년 42%로 최대 수요처 유지. 제품별 단가·메모리 물량·반도체 공급사별 확정 계약비중과 다름.",
            "삼성전자 HBM용 TSV 웨이퍼 공정 생산능력 업계 전망: 2026년 말 월 18만장→2027년 말 월 28만장(+10만장, +55.6%); SK하이닉스 월 20만장→26만장(+6만장, +30.0%). 총 DRAM 웨이퍼 투입량·실제 양품 HBM 출하량과 구별.",
            "HBM 웨이퍼 자원 사용은 범용 DRAM의 약 3~4배라는 TrendForce 설명이며, 2026년 메모리 3사의 HBM 웨이퍼 배분율 약 23%→2027년 약 30%로 확대 예상. 웨이퍼 자원 소모 배수와 제품 완성품 출하량 배수를 혼동하지 않음.",
            "추론 반도체 출하 +78%, 전체 AI 반도체 출하 +54%, 클라우드 사업자 설비투자 +60%는 2027년 기관 전망이지 확정 주문·전력 접속·실제 매출이 아님. 첨단 패키징 매출 +118% 전망도 반도체 제조사 전체 매출과 별도.",
        ),
        "caution": "11월 18일 로드쇼 현장 인용으로 발표자료 수치·대상·전망이며 회사 2027년 계약·설비가동 확정 실적이 아님. 구글·NVIDIA는 HBM 최종 수요처 비중이고 메모리 제조사의 명시된 매출처별 비중이 아님.",
    },
    {
        "key": "20261118_trendforce_roadshow_2028_dram_supply_risk",
        "date": "2026-11-18",
        "group": "roadshow",
        "label": "TrendForce: 2028년 P5·용인·CXMT 증설과 데이터센터 지연 위험",
        "sources": (
            ("ZDNet Korea 2028년 증설 시나리오 현장 보도", "https://zdnet.co.kr/view/?no=20261118120439", "현장 취재 원보도"),
            ("ZDNet 기사 동일 원문 정리", "https://theddari.com/trends/telegram/3692986659/13726", "원보도 요약·독립 증거 아님"),
        ),
        "need": (
            ("P5",), ("용인", "Yongin"), ("CXMT",), ("2028",),
            ("20만", "200,000", "200000"), ("30만", "300,000", "300000"),
            ("10만", "100,000", "100000"),
        ),
        "facts": (
            "2028년 이후 공급 위험은 투자·준비 단계의 시나리오: TrendForce 발표 인용 보도상 삼성전자 P5 1·2단계는 각각 월 웨이퍼 20만장 규모 목표, SK하이닉스 용인은 월 30만장 확보 목표, CXMT는 2028년 이후 월 10만~20만장 추가 증설을 검토. 모두 이번에 확정된 가동률·양품 출하가 아님.",
            "CXMT 2026년 월 3만장→2027년 3만6,000장이라는 현장 보도 숫자는, 2026년 9월 ZDNet 보도의 CXMT 회사 전체 웨이퍼 월 20만장 중반~연말 30만장 이상 업계 추정과 큰 차이가 남. 사업장·대상 제품·비율 분모가 확인되기 전 회사 전체 생산능력으로 확정 사용 금지.",
            "2028년 이후 미국 데이터센터 허가·전력 접속·공사 지연 가능성은 수요 리스크 가정으로, 이미 취소된 발주물량이나 매출 감소 확정 자료가 아님.",
            "실제 역전 확인 조건: P5/용인/중국 신공장 장비 반입·전원 인가·월 웨이퍼 투입·HBM/범용 DRAM 수율, 서버 실수요·기업용 SSD 주문과 재고, 2028년 분기별 DRAM/NAND 계약가 수정 추적.",
        ),
        "caution": "이전 키움증권 11월 16일 2028년 공급과잉 모델과는 근거·시나리오가 다른 TrendForce의 증설 일정 설명. P5 단계별 웨이퍼 목표가 중복·과대 합산되지 않도록 향후 설비 공시와 대조해야 하며 실제 가동·고객 승인 이전에는 확정 매출로 계산하지 않음.",
    },
)

GROUPS = {
    "glass": "삼성전기 유리기판 LOI·공정별 공급망",
    "hbm": "SK하이닉스 HBM4·삼성 온양 증설·8인치 공정 재편",
    "intel": "인텔 추론 GPU·국내 23개사·공유 메모리",
    "allocation": "엔비디아·비엔비디아 HBM4 공급 배분·고객별 가격",
    "financial": "SK하이닉스 지역별 매출·고객 집중도·설비투자·연구개발비",
    "cycle": "2027~2028 DRAM·NAND 공급과잉 전망 vs HBM 수요·고객 계약",
    "roadshow": "TrendForce 2026.11.18 로드쇼 — HBM4 가격·2027 수급·2028 증설 위험",
}

def text_matches(body: str, required: tuple) -> bool:
    low = body.casefold()
    return all(any(term.casefold() in low for term in terms) for terms in required)

def fetch_article(url: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; HBM-monitor/1.0)", "Accept-Language": "ko-KR,ko;q=0.8,en;q=0.7"}
    )
    with urllib.request.urlopen(req, timeout=13) as response:
        actual = response.geturl()
        host = (urlparse(actual).hostname or "").lower()
        expected = (urlparse(url).hostname or "").lower()
        def root(h):
            h = h.removeprefix("www.").removeprefix("ir.").removeprefix("biz.")
            return h
        if root(host) != root(expected):
            raise ValueError("publisher_host_changed")
        raw = response.read(2_500_001)
        if len(raw) > 2_500_000:
            raise ValueError("oversize_publisher_page")
        encoding = response.headers.get_content_charset() or "utf-8"
    soup = BeautifulSoup(raw.decode(encoding, errors="replace"), "html.parser")
    for tag in soup.select("script, style, noscript, svg, nav, footer, header"):
        tag.decompose()
    for selector in ("#articleBody", "#newsEndContents", ".article_body", ".article-view", "article"):
        area = soup.select_one(selector)
        if area and len(area.get_text(" ", strip=True)) >= 160:
            return html.unescape(area.get_text(" ", strip=True))
    return html.unescape(soup.get_text(" ", strip=True))

def probe(report: dict, fetcher=fetch_article) -> tuple[dict | None, list[dict]]:
    gaps = []
    for label, url, lineage in report["sources"]:
        try:
            body = fetcher(url)
            if not text_matches(body, report["need"]):
                gaps.append({"key": report["key"], "origin": label, "status": "required_article_facts_not_verified"})
                continue
            return {"key": report["key"], "group": report["group"], "label": report["label"],
                    "date": report["date"], "facts": report["facts"], "caution": report["caution"],
                    "source": url, "source_label": label, "lineage": lineage,
                    "verified_kind": "reported_not_issuer_confirmed"}, gaps
        except Exception as exc:
            gaps.append({"key": report["key"], "origin": label,
                         "status": "source_unavailable", "error_type": type(exc).__name__})
    return None, gaps

def render(group: str, items: list[dict], checked_at: str) -> str:
    lines = [
        "<b>[HBM 기존 감시 보강 | 중요 신규·누락 사건]</b>",
        f"<b>{html.escape(GROUPS[group])}</b>",
        f"확인: {html.escape(checked_at)} · 최초 보도일 기준 · 원보도/재인용 구분",
    ]
    for item in items:
        lines.extend(("", f"<b>■ {html.escape(item['label'])}</b>",
                      f"• 최초 보도: {item['date']} · 출처 단계: {html.escape(item['lineage'])}"))
        lines.extend("• " + html.escape(line) for line in item["facts"])
        lines.append("• 구분·위험: " + html.escape(item["caution"]))
        lines.append(f'• <a href="{html.escape(item["source"], quote=True)}">근거 기사</a> ({html.escape(item["source_label"])})')
    return "\n".join(lines).strip() + "\n"

def apply(previous: dict, checked_at: str, fetcher=fetch_article) -> tuple[dict, list[str], dict]:
    result = copy.deepcopy(previous)
    sub = result.get("hbm_material_event_watch") or {}
    existing = set(sub.get("seen_keys") or [])
    new = []
    gaps = []
    for report in REPORTS:
        if report["key"] in existing:
            continue
        # A publication scheduled in the future must not be fetched or sent.
        if date.fromisoformat(checked_at[:10]) < date.fromisoformat(report["date"]):
            continue
        if (date.fromisoformat(checked_at[:10]) - date.fromisoformat(report["date"])).days > MAX_AGE_DAYS:
            gaps.append({"key": report["key"], "status": "older_than_backfill_window"})
            continue
        obs, err = probe(report, fetcher)
        gaps.extend(err)
        if obs:
            new.append(obs)
            existing.add(obs["key"])
    result["hbm_material_event_watch"] = {
        "version": VERSION, "checked_at_kst": checked_at,
        "seen_keys": sorted(existing), "last_new_fact_keys": [x["key"] for x in new],
        "unconfirmed_source_count": len({x["key"] for x in gaps}),
        "unconfirmed_sources": gaps[-20:],
        "evidence_rule": "verified_publisher_body_reported_only_not_contract_or_company_yield",
    }
    rendered = [render(group, [x for x in new if x["group"] == group], checked_at)
                for group in ("glass", "hbm", "intel", "allocation", "financial", "cycle", "roadshow")
                if any(x["group"] == group for x in new)]
    audit = {"checked_at_kst": checked_at, "verified_events": len(new),
             "verified_keys": [x["key"] for x in new], "gaps": gaps[-20:],
             "durable_state_only_after_existing_hbm_delivery_receipt": True}
    return result, rendered, audit

def require_durable_seen_keys(durable: dict, candidate: dict) -> None:
    """Fail closed when a collector drops previously acknowledged event keys.

    Calling this both before event classification and before Telegram delivery
    protects against a lost ledger at any intermediate collector stage.
    """
    previous = (durable.get("hbm_material_event_watch") or {}).get("seen_keys") or []
    upcoming = (candidate.get("hbm_material_event_watch") or {}).get("seen_keys") or []
    if not isinstance(previous, list) or not isinstance(upcoming, list):
        raise RuntimeError("HBM material dedup journal malformed; notification held")
    if any(not isinstance(key, str) or not key for key in previous + upcoming):
        raise RuntimeError("HBM material dedup journal keys malformed; notification held")
    lost = set(previous) - set(upcoming)
    if lost:
        raise RuntimeError("HBM material acknowledged seen_keys missing in collector candidate; duplicate alert blocked")


def main() -> None:
    if not PENDING.exists():
        raise RuntimeError("Rubin HBM pending state is missing; no material-event update permitted")
    if not PENDING.parent.is_dir():
        raise RuntimeError("HBM output directory missing")
    prior = json.loads(PENDING.read_text(encoding="utf-8"))
    if not BASELINE.exists():
        raise RuntimeError("HBM durable transaction baseline unavailable; duplicate alert blocked")
    durable = json.loads(BASELINE.read_text(encoding="utf-8"))
    require_durable_seen_keys(durable, prior)
    checked_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    result, rendered, audit = apply(prior, checked_at)
    # Do not consume these keys outside the existing acknowledged delivery.
    if rendered:
        existing = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
        content = ("\n\n" + BREAK + "\n\n").join(
            ([existing] if existing else []) + rendered
        )
        ALERT.write_text(content.strip() + "\n", encoding="utf-8")
    PENDING.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("hbm_material_events_verified=" + str(audit["verified_events"])
          + " coverage_gaps=" + str(len(audit["gaps"]))
          + " telegram_send_delegated_to=hbm_delivery")

if __name__ == "__main__":
    main()
