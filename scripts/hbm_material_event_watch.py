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
        "short_title": "HBM4·HBM4E 가격 전망",
        "brief_facts": (
            "HBM4 가격: 2026년 2.05달러/Gb 이상 → 2027년 3~5.5달러/Gb 전망. HBM4E는 5달러/Gb 초과 초기 제시·논의 단계.",
            "2026년 2.05달러 최소치 대비 HBM4 상승폭 +46~168%; 실제 기준가격이 더 높으면 상승률 축소. 전체 가격대가 100% 이상 상승한다는 뜻 아님.",
            "전체 HBM 혼합 평균판매단가: 2026년 1.67달러/Gb → 2027년 3.70달러/Gb(+121.6%, 현장 기사 +122%). 9/29 TrendForce 공식 +121% 전망과 동일한 방향이며 HBM4 개별 가격과 분모가 다름.",
            "확인 지표: 고객별 계약 갱신·가격·용량, 8단/12단 비중, 고객 검증·실제 양산 출하. 보도 당일 참고 환율은 11/18 서울외국환중개 15:30 기준 1달러=1,333.00원.",
        ),
        "brief_caution": "가격은 전망·초기 제시가로 확정 납품가격, HBM4E 고객 승인, 2027년 실현 매출이 아님. 행사 유료 발표자료 전문 미확보.",
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
        "short_title": "DRAM 분기별 가격·NAND 하락 전환",
        "brief_facts": (
            "범용 DRAM 평균판매단가 전분기비: 2026년 4분기 +10~15% → 2027년 1분기 +5~10% → 2분기 +3~8% → 3·4분기 각각 +0~5%. 상승률 둔화이지 가격 하락 확정이 아님.",
            "전체 NAND 계약가 하락 시작 예상은 기존 2027년 하반기(3분기) → 2027년 2분기. 11월 17일 TrendForce 선행 자료로 이미 감지한 전망이며 실현 가격 하락·계약 취소·새로운 독립 상향/하향이 아님.",
            "배경: AI 서버·HBM 증산으로 범용 DRAM 웨이퍼가 부족한 반면, NAND는 YMTC 공정 전환·중국 증설·소비자 수요 약세 가능성.",
            "확인 지표: 분기별 DRAM/NAND 계약가, DDR4/DDR5 현물가, YMTC 실제 비트 생산, 중국·북미 기업용 SSD 주문·재고. 현물가·계약가·고객별 SSD 가격은 별개.",
        ),
        "brief_caution": "2027년 예상 경로이지 확정 거래·매출 아님; 11월 17일 선행 NAND 신호는 중복 전송 금지.",
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
        "short_title": "HBM4 비중·고객·TSV 공급능력",
        "brief_facts": (
            "전체 HBM 출하 중 HBM4 비중 2026년 31%→2027년 51%(+20%p). 2027년 하반기 8단이 12단보다 주력이 될 가능성; 제품 구성에 따른 평균단가 상승과 개별 가격 인상은 구분.",
            "HBM 최종 수요처: 구글 TPU 등 2026년 22%→2027년 31%(+9%p), NVIDIA는 2027년 42%로 최대. 메모리 공급사의 고객별 확정 계약비중이 아님.",
            "HBM용 TSV 웨이퍼 처리능력(2026년 말→2027년 말): 삼성전자 월 18만→28만장(+10만, +55.6%), SK하이닉스 월 20만→26만장(+6만, +30%). 실제 양품 HBM 출하량 또는 전체 DRAM 웨이퍼 능력과 다름.",
            "HBM의 웨이퍼 자원 소모는 범용 DRAM의 약 3~4배, 메모리 3사의 HBM 웨이퍼 배분율 2026년 23%→2027년 약 30% 전망.",
            "2027년 전망: 추론 반도체 출하 +78%, 전체 AI 반도체 +54%, 클라우드 설비투자 +60%, 첨단 패키징 매출 +118%. 서로 다른 분모로 미확정 발주·양산·매출과 구분.",
        ),
        "brief_caution": "고객 비중·생산능력·수요 증가는 TrendForce 전망이며 회사의 실제 계약·완성품 출하·매출 확정이 아님.",
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
        "short_title": "2028년 증설·공급과잉 위험",
        "brief_facts": (
            "설비투자 시나리오: 삼성 P5 1·2단계 각각 월 웨이퍼 20만장 목표, SK하이닉스 용인 월 30만장 목표, CXMT 2028년 이후 월 10만~20만장 추가 증설 검토. 가동·출하 확정 아님.",
            "CXMT 2026년 월 3만장→2027년 월 3만6,000장 현장 수치는 과거 회사 전체 월 20만장 중반~30만장 이상 추정과 불일치. 공장·제품·분모 확인 전 전체 생산능력으로 단정 금지.",
            "미국 데이터센터의 허가·전력 접속·공사 지연은 2028년 이후 잠재 수요 위험이며 이미 취소된 주문·매출 감소 확정이 아님.",
            "확인 순서: P5·용인·중국 장비 반입→전원 인가→웨이퍼 투입→HBM/범용 DRAM 수율·출하, 서버 실수요·기업용 SSD 주문·재고, 2028년 분기 계약가 변화.",
        ),
        "brief_caution": "11/16 키움증권 공급과잉 전망과 별개 시나리오. P5 물량 중복 합산 금지, 장비 반입·고객 승인 이전 매출 확정 금지.",
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
    {
        "key": "20261119_munhwa_skhynix_20high_hybrid_bonder_report",
        "date": "2026-11-19",
        "max_age_days": 30,
        "group": "hybrid_equipment",
        "label": "문화일보 단독: SK하이닉스 20단 HBM 하이브리드 본더 투입 보도",
        "short_title": "20단 HBM 하이브리드 본더 투입 보도",
        "brief_facts": (
            "2026년 11월 19일 문화일보 단독 보도: SK하이닉스 20단 HBM용 하이브리드 본더 '투입'. 확인 단계는 언론 보도이며, SK하이닉스 공식 구매계약·설치·양산 확정과 구분.",
            "기존 대비: 2026년 2월 Applied Materials·Besi 키넥스 파일럿 평가 보도가 존재. 이번 건이 장비 신규 반입·증설인지, 기존 평가의 후속인지 원문·발주처로 확인 필요.",
            "다음 확인: 장비 제조사·대수·공급금액·실제 반입→설치·파일럿 가동→수율·신뢰성 검증→고객 승인→20단 HBM 양산·출하·매출.",
        ),
        "brief_caution": (
            "기사 제목만으로 공급사·대수·계약·양산을 확정하지 않음. "
            "원문 확보 실패 시 발송하지 않고 확인 대기. 20단 기술 개발과 양품 양산은 다른 단계."
        ),
        "sources": (
            ("문화일보 11월 19일 단독 기사", "https://munhwa.com/article/11632525",
             "단일 언론 원보도·독립 회사 확인 전"),
        ),
        "context_links": (
            ("SK하이닉스 공식 기술 설명", "https://news.skhynix.com/en/tech-note-series-ep2/"),
            ("2026년 2월 파일럿 보도", "https://www.greened.kr/news/articleViewAmp.html?idxno=337399"),
        ),
        "need": (
            ("SK하이닉스", "SK hynix"), ("20단", "20-layer", "20-high"),
            ("HBM",), ("하이브리드 본더", "하이브리드본더", "hybrid bonder"),
            ("투입", "도입", "반입", "평가", "설치"),
        ),
        "facts": (
            "2026년 11월 19일 문화일보 단독 제목상 SK하이닉스가 20단 HBM용 하이브리드 본더를 투입한다는 보도. 장비 투입·구매·설치의 정확한 단계는 기사 본문과 발주처 공식 근거로 추가 확인.",
            "기존 대비 2026년 2월 Applied Materials·Besi 장비 파일럿 평가 보도가 선행하므로 이번 건이 처음 도입된 장비인지, 추가 도입·평가 확대인지 확인 전 단정 금지.",
            "향후 독립 확인할 항목: 제조사·발주 상대방·설비 대수·계약금액·설치·성능검증·양품 수율·고객 승인·20단 HBM 양산 및 매출 시점.",
        ),
        "caution": (
            "단독 언론 보도이며 SK하이닉스의 장비 계약·납품·20단 HBM 양산 공식 확인 전. "
            "기존 MR-MUF 16단 생산과 20단 하이브리드 본딩 기술 검증을 혼동하지 않음."
        ),
    },
    {
        "key": "20261119_hbm_hybrid_bonder_supplier_names_correction",
        "date": "2026-11-19",
        "max_age_days": 30,
        "requires_prior_keys": ("20261119_munhwa_skhynix_20high_hybrid_bonder_report",),
        "group": "hybrid_equipment",
        "label": "정정·업체 실명: SK하이닉스 평가용 하이브리드 본더 제조사·모델",
        "short_title": "하이브리드 본더 평가 업체 실명·모델 보완",
        "brief_facts": (
            "① 한화세미텍: SHB2 Nano(2세대 하이브리드 본더) — 2026년 4월 SK하이닉스 라인 반입·품질 평가 보도. 회사는 2월 개발 완료·상반기 고객사 시험 계획 발표. 평가용 장비 공급과 양산 장비 확정 수주를 구분.",
            "② 어플라이드 머티어리얼즈(AMAT)·베시(Besi): Kinex(키넥스) 통합 공정 시스템 — AMAT 표면처리·계측 + 베시의 Datacon 8800 CHAMEO ultra plus AC 하이브리드 본더; 2026년 초 SK하이닉스 파일럿 평가 보도.",
            "③ 한미반도체(042700): 2026년 6월 SK하이닉스 대상 442억원 수주품은 TC Bonder 4.5 Griffin(열압착 본더)이며, 이번 20단 하이브리드 본더 공급계약이 아님. 세메스는 삼성전자 중심 개발 업체로 SK 납품 확정과 구분.",
            "11월 19일 문화일보의 이번 추가 투입 장비 제조사는 해당 기사 원문·발주처 계약으로 별도 확인 전. 위 업체명은 기존 평가 공급 관계를 교차확인한 것.",
        ),
        "brief_caution": "2026년 2~6월 보도·공식 제품자료에 근거한 공급망 보완 알림. 11월 19일 신규 계약 상대방·대수·금액, 고객 승인·20단 HBM 양산 확정 아님. 원천 조회 실패나 독립 출처 부족 시 발송 보류.",
        "sources": (
            ("아이뉴스24 기존 SK하이닉스 장비 평가 보도", "https://www.inews24.com/v/1959204", "독립 언론 보도"),
            ("녹색경제신문 SK하이닉스 Kinex·Besi 보도", "https://www.greened.kr/news/articleView.html?idxno=337399", "별도 언론 보도"),
            ("한화세미텍 공식 SHB2 Nano 자료", "https://www.hanwhasemitech.com/ko-mo/media/news/detail.asp?board_id=3470", "장비업체 공식자료"),
        ),
        "need": (("SK하이닉스",), ("하이브리드",), ("한화세미텍",), ("베시",)),
        "facts": (
            "한화세미텍 2세대 SHB2 Nano 2026년 4월 SK하이닉스 반입·평가 관련 디일렉·아이뉴스24·딜사이트 보도와 한화세미텍 2월 개발 공식자료를 구분.",
            "어플라이드 머티어리얼즈와 베시의 Kinex 통합시스템 및 베시 Datacon 8800 CHAMEO ultra plus AC는 SK하이닉스 2026년 초 파일럿 평가 보도 단계.",
            "한미반도체 TC Bonder 4.5 Griffin 442억원 계약은 하이브리드 본더 계약이 아니며 이번 문화일보 추가 투입 공급사 단정 금지.",
            "11월 19일 문화일보 본문 내 특정 신규 계약 상대방은 독립 확인 전이며 20단 제품 양산·고객 검증 통과는 확인되지 않음.",
        ),
        "caution": "기존 평가 공급업체의 실명 보완으로, 신규 공급계약 확정 공시나 20단 HBM 양산을 의미하지 않음.",
        "evidence_groups": (
            ("한화 SHB2 회사 공식 장비",
             (
                ("한화세미텍 공식 신제품", "https://www.hanwhasemitech.com/ko-mo/media/news/detail.asp?board_id=3470",
                 (("SHB2 Nano",), ("0.1",), ("고객사",)), "공식 제품 발표"),
                ("한화세미텍 공식 대체본", "https://eco.hanwhatechwin.co.kr/ko/media/news/detail.asp?board_id=3470",
                 (("SHB2 Nano",), ("고객사",), ("하이브리드",)), "동일 회사 공식 재게시"),
             )),
            ("한화→SK하이닉스 평가용 반입",
             (
                ("아이뉴스24 한화 평가 보도", "https://www.inews24.com/v/1959204",
                 (("한화세미텍",), ("SK하이닉스",), ("2세대",), ("하이브리드",)), "독립 언론 보도"),
                ("딜사이트 한화 평가 보도", "https://dealsite.co.kr/articles/172804",
                 (("한화세미텍",), ("SK하이닉스",), ("SHB2",), ("4월",)), "별도 언론 보도"),
                ("디일렉 한화 통합 시스템 보도", "https://www.thelec.kr/news/articleView.html?idxno=57884",
                 (("한화세미텍",), ("SK하이닉스",), ("SHB2",), ("4월",)), "별도 언론 보도"),
             )),
            ("AMAT·Besi→SK하이닉스 파일럿 평가",
             (
                ("녹색경제신문 Kinex·Besi 원보도", "https://www.greened.kr/news/articleView.html?idxno=337399",
                 (("SK하이닉스",), ("베시",), ("키넥스",), ("Datacon",)), "별도 언론 보도"),
                ("녹색경제신문 원보도 AMP", "https://www.greened.kr/news/articleViewAmp.html?idxno=337399",
                 (("SK하이닉스",), ("베시",), ("키넥스",), ("Datacon",)), "동일 언론 AMP"),
                ("Bits&Chips 하이브리드 로드맵 취재", "https://bits-chips.com/article/besi-faces-longer-wait-as-sk-hynix-pushes-hybrid-bonding-to-hbm5/",
                 (("SK Hynix",), ("Besi",), ("Applied Materials",), ("pilot",)), "독립 전문매체"),
                ("아이뉴스24 AMAT·Besi 이전 평가", "https://www.inews24.com/v/1959204",
                 (("SK하이닉스",), ("어플라이드",), ("BESI",), ("하이브리드",)), "아이뉴스24 동일 기사 재활용"),
             )),
        ),
    },
    {
        "key": "20261118_nvidia_fy27q3_memory_supply_capacity_390bn",
        # Backfill starts on Nov 19 KST; the original announcement is Nov 17 US
        # (Nov 18 in Korea). This is not a newly published Nov 19 filing.
        "date": "2026-11-19",
        "max_age_days": 45,
        "group": "nvidia_commitments",
        "label": "엔비디아 2027 회계연도 3분기 공급·생산능력 약정 증가 — 메모리 다년 조달",
        "short_title": "엔비디아 메모리 장기조달 · 공급약정 +39.8%",
        "brief_facts": (
            "약정(11월17일 발표·10월25일 기준): 2,790억달러 → 3,900억달러(+1,110억달러·+39.8%). 증가분 대부분은 다년 메모리 확보 관련.",
            "기간별(엔비디아 회계연도): 2027 잔여 690억달러 / 2028 2,030억달러(전체의 52.1%) / 2029 920억달러 / 2030 100억달러 / 2031 80억달러 / 2032 이후 80억달러.",
            "전체 미래약정 5,180억달러 = 위 공급·생산능력 약정 + 클라우드 280억달러 + 미개시 데이터센터 임차 740억달러 + 지분투자 200억달러 + 설비투자 60억달러. 별개 항목을 HBM 계약에 합산하지 않음.",
            "실적(FY27 3분기): 매출 1,158억달러(전년 +103%·전분기 +20%), 데이터센터 1,076억달러(전년 +110%). FY27 4분기 매출 전망 1,300억달러(±3%).",
            "수요 연결: Vera Rubin NVL72 출하 개시; GPU는 HBM4, Vera CPU는 저전력 D램·SOCAMM. 공급약정의 HBM4 비중·삼성전자/하이닉스별 금액·물량은 미공개.",
            "국내 업체: SK하이닉스 M15X 연말 최대 가동 목표·4분기 HBM4 출하·매출이 HBM3E 추월 예상. 삼성전자 HBM4 확대·HBM4E 추진; 3분기 HBM4 매출 3배 이상·HBM 내 60%와 FY28 성장전망 70→75%는 뉴스1 보도(공식 개별 수치 미확인).",
        ),
        "brief_caution": (
            "위 공급·생산능력 약정은 엔비디아의 미래 지출 약정으로, 전액 HBM4 "
            "또는 삼성·SK의 확정 매출이 아님. 발주 전 조정·취소 가능. "
            "원화는 조회시점 환율로 환산하며 기사 당시 환산액과 구별."
        ),
        "sources": (
            ("엔비디아 공식 SEC 제출 CFO 설명", "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000088/q3fy27cfocommentary.htm", "공식 원천"),
        ),
        "need": (("supply commitments",), ("390",), ("279",), ("memory supply",)),
        "facts": (
            "엔비디아 2026년 11월 17일 공식 CFO Commentary 3분기 약정 279→390십억달러(+111십억달러, +39.8%). 주로 메모리 다년 조달.",
            "2028 회계연도 203십억달러와 2029 회계연도 92십억달러는 전체 공급·생산능력 약정 배분이지 해당 연도 HBM4 확정 구매액이 아님.",
            "Vera Rubin 출하와 SK하이닉스·삼성전자 HBM4 공급 확대 전망을 연결하되 고객별 공급계약·단가·물량·매출 확정으로 승격하지 않음.",
        ),
        "caution": "SEC 공식 자료 및 독립 언론 보도 교차확인 전 발송 보류; 불확실한 전송은 상태 확정 금지.",
        "verified_kind": "official_nvidia_supply_commitment_with_independent_press_not_hbm_contract",
        "verified_source_caption": "공식 제출·독립 보도",
        "context_links": (
            ("SEC 공시", "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000088/q3fy27cfocommentary.htm"),
            ("엔비디아 실적", "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-Third-Quarter-Fiscal-2027/"),
            ("SK하이닉스 실적", "https://news.skhynix.com/en/q3-2026-business-results/"),
            ("삼성전자 실적", "https://news.samsung.com/kr/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90-2026%EB%85%84-3%EB%B6%84%EA%B8%B0-%EC%8B%A4%EC%A0%81-%EB%B0%9C%ED%91%9C"),
        ),
        "evidence_groups": (
            ("엔비디아 SEC 공식 발표·정확한 금액 및 기간",
             (
                ("미 SEC 8-K 첨부 CFO 설명",
                 "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000088/q3fy27cfocommentary.htm",
                 (("supply commitments",), ("$390 billion",), ("$279 billion",),
                  ("multi-year",), ("memory supply",), ("2028",), ("2029",),
                  ("203",), ("92",)),
                 "NVIDIA SEC 8-K 공식 별첨 99.2"),
                # Reprints of the exact issuer-authored SEC CFO commentary.
                # Do not count reprints as a second independent publisher;
                # the separate news outlet evidence lane remains mandatory.
                ("MarketScreener CFO 설명 동일 재게시",
                 "https://www.marketscreener.com/news/nvidia-third-quarter-2027-cfo-commentary-ce785edcdc81f420",
                 (("supply commitments",), ("$390 billion",), ("$279 billion",),
                  ("multi-year",), ("memory supply",), ("2028",), ("2029",),
                  ("203",), ("92",)),
                 "SEC 공시의 CFO 설명 동일 재게시·SEC 원문 직접 열람 아님"),
                ("Fintel SEC 8-K 동일 재게시",
                 "https://fintel.io/doc/sec-nvidia-corporation-1045810-8k-2026-november-17-20774-6201",
                 (("supply commitments",), ("$390 billion",), ("$279 billion",),
                  ("multi-year",), ("memory supply",), ("2028",), ("2029",),
                  ("203",), ("92",)),
                 "SEC 공시 동일 재게시·SEC 원문 직접 열람 아님"),
                ("StockTitan SEC 8-K 동일 재게시",
                 "https://www.stocktitan.net/sec-filings/NVDA/8-k-nvidia-corp-reports-material-event-1b8846aa7232.html",
                 (("supply commitments",), ("$390 billion",), ("$279 billion",),
                  ("multi-year",), ("memory supply",), ("2028",), ("2029",),
                  ("203",), ("92",)),
                 "SEC 공시 동일 재게시·SEC 원문 직접 열람 아님"),
             )),
            ("독립 언론의 동일 공식 숫자 보도",
             (
                ("뉴스1 11월 18일 원보도",
                 "https://www.news1.kr/industry/general-industry/6357997",
                 (("엔비디아",), ("3900", "3천900"), ("2790", "2천790"),
                  ("메모리",), ("2028",), ("2029",)),
                 "뉴스1 독립 보도"),
                ("연합뉴스 11월 18일 보도",
                 "https://www.yna.co.kr/view/AKR20261118027500009",
                 (("엔비디아",), ("3900", "3천900"), ("2790", "2천790"),
                  ("메모리",), ("2028",)),
                 "연합뉴스 독립 보도"),
                ("머니투데이 11월 18일 보도",
                 "https://www.mt.co.kr/index.php/tech/2026/11/18/2026111807254685008",
                 (("엔비디아",), ("3900", "3천900"), ("2790", "2천790"),
                  ("메모리",), ("2028",)),
                 "머니투데이 독립 보도"),
             )),
        ),
    },
    {
        "key": "20261121_samsung_memory_2029_booking_2031_lta_report",
        "date": "2026-11-21",
        "max_age_days": 45,
        "group": "samsung_memory_lta",
        "label": "삼성전자 2027~2029 메모리 계약 확보 보도·2031 장기공급 요청",
        "short_title": "삼성 메모리 2029년까지 대부분 계약 확보 보도·2031년 협의",
        "brief_facts": (
            "신규(11/21 단독 기사): 2027~2029년 메모리 생산능력 대부분 계약 확보 주장; 일부 고객은 2031년까지 추가 공급·계약 연장 요청. 삼성 공식 계약률 미공개.",
            "회사 발표(10/29): 주요 고객 10곳 다년 계약 완료, 추가 10곳 협상(일부 최종 단계). 2030년까지 생산능력의 60~70% 장기계약 확보 목표.",
            "가격·선수금: 기존 계약의 최저가격 보장선 적용(회사 발언 인용). 선수금·가격 상한은 업계 협의 보도; 실제 약정 물량·금액·납입 미공개.",
            "2027년 제품: HBM 공급 목표물량 판매 완료(회사 발표) / 범용 D램 웨이퍼 사실상 완판(업계 보도). HBM 증산으로 범용 D램 생산 여력 감소 가능.",
            "수급(업계 추정): 주요사 공급 충족률 60~70%(요청량 대비), D램 비트 공급 증가율 최대 연 20~25%. 장기계약 목표 60~70%(생산능력 대비)와 분모가 다름.",
            "낸드(업계 보도): 소비자용 공급 충족률 70%, 기업용 SSD 50% 초과(정확한 수요 분모 미공개). 키옥시아 2027년 낸드 수요 전망 상향 언급.",
        ),
        "brief_caution": (
            "2029년 완판·2031년 계약은 취재·협의 단계(삼성 공식 확인 전). "
            "Wccftech 재인용은 별도 독립 입증이 아님. "
            "2027~2029년 계약률·2031년 신규 체결 건수·고객·단가·물량·매출 미공개. "
            "수요 둔화·설비투자 증설·가격 재협상 위험 유의."
        ),
        "sources": (
            ("이코노미트리뷴 11월21일 원보도",
             "https://www.economytribune.co.kr/news/articleView.html?idxno=3904497",
             "단일 업계 관계자 보도·삼성 계약 공시 아님"),
        ),
        "facts": (
            "원보도 기준 2027~2029년 생산능력 대부분 계약 확보 주장 및 일부 고객 2031년 장기공급 요청은 취재·협의 단계.",
            "10월29일 실적발표의 이미 체결된 10곳·별도 협상 중 10곳·2030년 생산능력 60~70% 장기계약 목표는 독립 기준.",
            "2027년 범용 D램 웨이퍼 완판, 업계 공급 충족률 60~70%, 비트 공급 연간 최대 20~25%, 소비자 낸드 70%·기업용 SSD 50% 초과는 취재 수치·공식 통계 확인 전.",
        ),
        "caution": "단독 업계 보도·재인용은 별도 독립 확인이 아니며 구매계약·양산·매출 인식을 구별.",
        "verified_kind": "reported_2029_capacity_booking_with_company_official_2026q3_context_not_firm_contract",
        "verified_source_caption": "삼성 공식 실적·컨퍼런스콜 검증·원보도(또는 명시적 재인용)",
        "context_links": (
            ("이코노미트리뷴 원문",
             "https://www.economytribune.co.kr/news/articleView.html?idxno=3904497"),
            ("삼성전자 3분기 공식 실적",
             "https://news.samsung.com/kr/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90-2026%EB%85%84-3%EB%B6%84%EA%B8%B0-%EC%8B%A4%EC%A0%81-%EB%B0%9C%ED%91%9C"),
        ),
        "evidence_groups": (
            ("삼성 공식 사업 실적·HBM 제품 기준",
             (
                ("삼성전자 공식 3분기 발표",
                 "https://news.samsung.com/kr/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90-2026%EB%85%84-3%EB%B6%84%EA%B8%B0-%EC%8B%A4%EC%A0%81-%EB%B0%9C%ED%91%9C",
                 (("삼성전자",), ("2026",), ("HBM4",), ("SSD",), ("시설투자",)),
                 "삼성 공식 실적·2029년 완판 공식 확정자료 아님"),
                ("삼성 글로벌 공식 3분기 발표",
                 "https://news.samsung.com/global/samsung-electronics-announces-third-quarter-2026-results",
                 (("Samsung Electronics",), ("2026",), ("HBM4",), ("SSD",), ("investment", "capital")),
                 "삼성 공식 동일 실적 영문본·2029년 완판 공식 확정자료 아님"),
             )),
            ("10개 체결·10개 협상 원래 발표 확인",
             (
                ("연합뉴스 10월29일 삼성 컨퍼런스콜 취재",
                 "https://www.yna.co.kr/view/AKR20261029089951003",
                 (("삼성전자",), ("10곳", "10개"), ("협상",), ("60",), ("HBM",)),
                 "독립 언론의 10월29일 공식 발언 취재"),
                ("머니투데이 10월29일 컨퍼런스콜 취재",
                 "https://www.mt.co.kr/en/industry/2026/10/29/2026102910584736816",
                 (("Samsung",), ("10",), ("negotiat",), ("60",), ("memory",)),
                 "별도 언론의 10월29일 공식 발언 취재"),
                ("StockAnalysis 컨퍼런스콜 전사",
                 "https://stockanalysis.com/quote/krx/005930/transcripts/718820-q3-2026/",
                 (("Samsung",), ("10 major",), ("10 other",), ("60%",), ("memory",)),
                 "제삼자 공개 컨퍼런스콜 전사"),
             )),
            ("11월21일 원보도 신규 기간·공급 부족 주장",
             (
                ("이코노미트리뷴 11월21일 단독 원보도",
                 "https://www.economytribune.co.kr/news/articleView.html?idxno=3904497",
                 (("삼성전자",), ("2029",), ("2031",), ("2027",),
                  ("10곳", "10개"), ("60",), ("HBM",), ("50%",),
                  ("20~25", "20∼25", "20-25")),
                 "업계 단독 보도·계약 상대방 공개 확인 전"),
                ("Wccftech 원보도 명시 재인용",
                 "https://wccftech.com/samsungs-memory-production-reportedly-almost-fully-booked-through-2029-as-customers-seek-supply-deals-until-2031/",
                 (("Samsung",), ("2029",), ("2031",), ("2027",),
                  ("Economy Tribune",), ("60%",), ("HBM",)),
                 "이코노미트리뷴 의존 재인용·독립 취재 아님·세부 낸드 수치 원문 제공 기준"),
             )),
        ),
    },
    {
        "key": "20261122_citi_dram_nand_2027_asp_revision_repost",
        "date": "2026-11-22",
        "max_age_days": 35,
        "group": "citi_price_revision",
        "label": "씨티 2027 DRAM·NAND ASP·서버 RDIMM 가격 전망 변경: 전달 메모",
        "short_title": "씨티 2027년 DRAM 상향·NAND 하향(전달본)",
        "brief_facts": (
            "DRAM 평균판매단가(2027년 전년비): +23%→+35%(+12%p). 분기 전분기비 기존 +3%/+2%/+4%/+2%→+5%/+1%/+7%/+11%.",
            "NAND 평균판매단가(2027년 전년비): +45%→+25%(-20%p). 분기 기존 +5%/+3%/+2%/+1%→-3%/-1%/0%/+3%.",
            "서버 DDR5 64GB RDIMM 현물 전망: 2026년 9~10월 약 3,300달러→2027년 상반기 약 2,000달러(-39.4%); 현재 실제 시세 미확인.",
            "씨티 기존 11/3 수급 전망(2027년): DRAM 공급 +24%·수요 +28%·부족률 -3.8%, NAND 공급 +22%·수요 +26%·부족률 -3.3%.",
            "트렌드포스 11/19 공식 반대 전망: 2027년 NAND 계약가격 1분기 0~5% 하락·2분기부터 전 품목 약세, 비트 공급 +25~30%(기존 별도 알림 발송).",
        ),
        "brief_caution": (
            "11/22 KK Kontemporaries 전달본 기준(씨티 원본 미확인·독립 확인 전). "
            "HBM 약 +100% 가격 인상 가정의 비교기준 미확인. "
            "계약 평균판매단가≠현물가격, 연간 전년비≠분기 전분기비; "
            "두 기관 전망은 실제 거래·확정 실적이 아님."
        ),
        "sources": (
            ("KK Kontemporaries 씨티 메모 재게시",
             "https://theddari.com/ja/trends/telegram/2098793993/2855",
             "2026-11-22 사회관계망 전달문·씨티 원본 아님"),
            ("동일 게시물 다른 언어 경로",
             "https://theddari.com/trends/telegram/2098793993/2855",
             "동일 전달문 대체 경로·독립 출처 아님"),
            ("KK Kontemporaries 원 게시물 직접 보기",
             "https://t.me/kkkontemp/2855?embed=1",
             "2026-11-22 동일 Telegram 게시물·씨티 보고서 원본 아님"),
        ),
        "need": (
            ("씨티", "Citi"), ("2027",), ("DRAM",), ("NAND",),
            ("+35%",), ("+23%",), ("+25%",), ("+45%",),
            ("DDR5",), ("64GB",), ("RDIMM", "RRIMM"),
            ("3,300", "3300"), ("2,000", "2000"),
        ),
        "context_links": (
            ("씨티 11월3일 과거 수급 전망",
             "https://www.investing.com/news/stock-market-news/citi-expects-continued-memory-undersupply-in-2027-4995860"),
            ("트렌드포스 11월19일 공식 NAND 전망",
             "https://www.trendforce.com/presscenter/news/20261119-13314.html"),
        ),
        "facts": (
            "11월22일 공개 전달 메모의 씨티 2027년 DRAM ASP 기존 +23%→+35%, NAND ASP 기존 +45%→+25%는 씨티 원본 미확인·전언 단계.",
            "2027년 분기별 DRAM 전분기 대비 +5/+1/+7/+11%, NAND -3/-1/0/+3%; 64GB DDR5 RDIMM 현물 3,300→2,000달러 전망과 계약가 전망을 구별.",
            "11월3일 씨티 과거 수급 부족 DRAM -3.8%, NAND -3.3%는 11월19일 트렌드포스 NAND 공급과잉 전망과 시점·기관·분모가 다른 별도 추정.",
        ),
        "caution": "11월19일 트렌드포스 공식 뉴스는 이미 별도 메모리 감시에서 발송되어 재발송하지 않음; 씨티 원본 미확보.",
    },
    {
        "key": "20261123_fnnews_samsung_skhynix_supplier_direct_ma_possible",
        "date": "2026-11-23",
        "not_before_kst": "2026-11-23T11:14:32+09:00",
        "max_age_days": 30,
        "group": "supplier_ownership",
        "label": "삼성·SK하이닉스 소부장 직접 인수 가능성 제기 — 인수 확정 전",
        "short_title": "삼성·SK 핵심 소부장 직접 인수 가능성 보도",
        "brief_facts": (
            "11/23 파이낸셜뉴스: AI·로봇 공급망 확보를 위한 삼성·SK 소부장 지분투자·경영권 인수 가능성 제기(투자은행 업계 관측). 아직 계약 아님.",
            "기사에 언급된 기존 협력사(인수 대상 확정 아님): 엘티씨·자회사 엘에스이(SK 세정), 브이엠(SK 식각), 엑시콘(삼성 메모리 검사), 예스티(HBM 가압·냉각).",
            "투자 배경(기사 제시): 2040년까지 삼성 2,100조원·SK 1,100조원 장기 반도체 투자 청사진. 기업 인수가격 또는 신규 확정 인수예산이 아님.",
            "기존 공식 확인: SK 10/29 일본 파트너스데이 20개 이상 협력사 참여. 기존 공급·공동개발≠지분취득.",
            "다음 확인: 인수 주체·대상·지분율·인수가격·계약 → 실제 납입·완료 → 공급 물량·매출. 기사에는 개별 거래조건 미공개.",
        ),
        "brief_caution": (
            "‘나서나’는 질문형 보도이며 특정 업체 인수 확정·주가 수혜 아님. "
            "기존 장비 납품·협력 관계와 신규 인수계약을 구분."
        ),
        "sources": (
            ("파이낸셜뉴스 Daum 11월23일 기사",
             "https://v.daum.net/v/20261123111432176",
             "단일 언론 보도·삼성/SK 공식 M&A 확인 아님"),
        ),
        "context_links": (
            ("SK하이닉스 일본 공급망 공식 발표",
             "https://news.skhynix.com/en/2026-partners-day-japan/"),
            ("SK하이닉스 공식 3분기 실적",
             "https://news.skhynix.com/en/q3-2026-business-results/"),
        ),
        "requires_source_text_chars": 550,
        "need": (
            ("삼성", "삼전", "Samsung"),
            ("하이닉스", "닉스", "SK hynix"),
            ("소부장", "소재·부품·장비", "semiconductor equipment"),
            ("인수", "M&A", "acquisition"),
            ("공급망", "supply chain"),
            ("AI", "인공지능"),
            ("로봇", "robot"),
        ),
        "facts": (
            "언론 제목은 인수 가능성을 질문하는 표현이며 특정 기업 지분취득 확정 사실이 아님.",
            "인수 대상 실명·금액·지분율·계약 당사자·당국 승인·실제 납입은 공식 증빙 대조 필요.",
            "SK하이닉스 공식 협력사 지원 및 공급망 협력과 직접 인수는 다른 단계.",
        ),
        "caution": "인수 가능성을 확정 M&A로 승격하지 않으며 공식 지분취득 결정·계약·납입을 후속 확인.",
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
    "hybrid_equipment": "SK하이닉스 20단 HBM · 하이브리드 본더 검증·도입 단계",
    "nvidia_commitments": "엔비디아 공급·생산능력 약정 및 HBM4 수요 검증",
    "samsung_memory_lta": "삼성전자 메모리 장기계약·2029~2031 확인 단계",
    "citi_price_revision": "씨티 2027년 메모리 가격 전망·트렌드포스 반대 근거",
    "supplier_ownership": "삼성·SK 핵심 소부장 직접 인수 가능성·공식 계약 구분",
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
    if report.get("evidence_groups"):
        # A supplier-name correction needs an issuer product source AND distinct
        # independent customer-evaluation reporting for both equipment families.
        gaps, proven = [], []
        for lane, choices in report["evidence_groups"]:
            accepted = None
            for label, url, terms, lineage in choices:
                try:
                    body = fetcher(url)
                    if text_matches(body, terms):
                        accepted = (label, url, lineage)
                        break
                    gaps.append({"key": report["key"], "lane": lane, "origin": label,
                                 "status": "required_article_facts_not_verified"})
                except Exception as exc:
                    gaps.append({"key": report["key"], "lane": lane, "origin": label,
                                 "status": "source_unavailable", "error_type": type(exc).__name__})
            if accepted is None:
                gaps.append({"key": report["key"], "lane": lane, "status": "required_independent_evidence_missing"})
                return None, gaps
            proven.append(accepted)
        hosts = [(urlparse(item[1]).hostname or "").lower().removeprefix("www.") for item in proven]
        if len(set(hosts)) != len(proven):
            gaps.append({"key": report["key"], "status": "independent_publishers_insufficient"})
            return None, gaps
        label, url, lineage = proven[1]
        return {
            "key": report["key"], "group": report["group"], "label": report["label"],
            "date": report["date"], "facts": report["facts"], "caution": report["caution"],
            "source": url, "source_label": label, "lineage": lineage,
            "verified_kind": (
                "issuer_statement_verbatim_reprint_with_independent_press_not_contract"
                if report.get("group") == "nvidia_commitments"
                and "sec.gov" not in proven[0][1]
                else report.get("verified_kind", "multi_origin_reported_supplier_evaluation_not_new_contract")
            ),
            "verified_source_links": tuple((item[0], item[1]) for item in proven),
            "short_title": report.get("short_title"), "brief_facts": report.get("brief_facts"),
            "brief_caution": report.get("brief_caution"),
            "verified_source_caption": (
                "엔비디아 CFO 설명 동일 공시 재게시·독립 보도"
                if report.get("group") == "nvidia_commitments" and "sec.gov" not in proven[0][1]
                else report.get("verified_source_caption", "업체별 확인 근거")
            ),
            "context_links": report.get("context_links", ()),
        }, gaps
    gaps = []
    for label, url, lineage in report["sources"]:
        try:
            body = fetcher(url)
            if report.get("group") == "supplier_ownership" and len(body) < report.get("requires_source_text_chars", 0):
                gaps.append({"key": report["key"], "origin": label,
                             "status": "incomplete_publisher_body", "chars": len(body)})
                continue
            if not text_matches(body, report["need"]):
                gap = {"key": report["key"], "origin": label,
                       "status": "required_article_facts_not_verified"}
                if report.get("group") == "citi_price_revision":
                    # Record only expected missing tokens, never publisher body,
                    # credentials or user data. A partial page must not send.
                    low_body = body.casefold()
                    gap["missing_required"] = [
                        terms[0] for terms in report["need"]
                        if not any(term.casefold() in low_body for term in terms)
                    ]
                    gap["response_text_chars"] = len(body)
                gaps.append(gap)
                continue
            return {"key": report["key"], "group": report["group"], "label": report["label"],
                    "date": report["date"], "facts": report["facts"], "caution": report["caution"],
                    "source": url, "source_label": label, "lineage": lineage,
                    "verified_kind": "reported_not_issuer_confirmed",
                    "short_title": report.get("short_title"),
                    "brief_facts": report.get("brief_facts"),
                    "brief_caution": report.get("brief_caution"),
                    "context_links": report.get("context_links", ())}, gaps
        except Exception as exc:
            gaps.append({"key": report["key"], "origin": label,
                         "status": "source_unavailable", "error_type": type(exc).__name__})
    return None, gaps

def render_samsung_memory_lta(items: list[dict], checked_at: str) -> str:
    """Compact one-event Samsung LTA display; never remove underlying evidence or change the dedupe key."""
    parts = []
    for item in items:
        lines = [
            "<b>[HBM | 삼성 메모리 장기계약]</b>",
            "확인 " + html.escape(checked_at[:16].replace("T", " ")) + " KST",
            "<b>■ " + html.escape(item.get("short_title") or item["label"]) + "</b>",
        ]
        lines.extend("• " + html.escape(value) for value in
                     (item.get("brief_facts") or item["facts"]))
        lines.append("• 주의: " + html.escape(item.get("brief_caution") or item["caution"]))
        evidence = item.get("verified_source_links") or (
            (item.get("source_label", "기사"), item["source"]),)
        links = []
        for label, url in evidence:
            host = (urlparse(url).hostname or "").lower()
            if "news.samsung.com" in host:
                short = "삼성 실적"
            elif "yna.co.kr" in host:
                short = "컨퍼런스콜"
            elif "economytribune.co.kr" in host:
                short = "단독 원문"
            elif "wccftech.com" in host:
                short = "Wccftech(재인용)"
            else:
                short = label
            links.append('<a href="' + html.escape(url, quote=True) +
                         '">' + html.escape(short) + '</a>')
        # A verified reprint is NOT an original publisher fetch. Preserve the
        # original link separately and label the actual read path as a reprint.
        if not any("economytribune.co.kr" in (urlparse(url).hostname or "").lower()
                   for _, url in evidence):
            for label, url in item.get("context_links", ()):
                if "economytribune.co.kr" in (urlparse(url).hostname or "").lower():
                    links.append('<a href="' + html.escape(url, quote=True) +
                                 '">원문(직접 확인 전)</a>')
                    break
        lines.append("근거: " + " · ".join(links))
        parts.append("\n".join(lines))
    return ("\n\n" + BREAK + "\n\n").join(parts).strip() + ("\n" if parts else "")


def render_citi_price_revision(items: list[dict], checked_at: str) -> str:
    """Compact the Citi price-revision view only; keep sources and delivery dedupe unchanged."""
    pages = []
    for item in items:
        lines = [
            "<b>[HBM | 씨티 메모리 가격 전망]</b>",
            "확인 " + html.escape(checked_at[:16].replace("T", " ")) + " KST",
            "<b>■ " + html.escape(item.get("short_title") or item["label"]) + "</b>",
        ]
        lines.extend("• " + html.escape(fact) for fact in
                     (item.get("brief_facts") or item["facts"]))
        lines.append("• 주의: " + html.escape(item.get("brief_caution") or item["caution"]))
        source = item.get("source") or ""
        links = []
        if source:
            links.append('<a href="' + html.escape(source, quote=True) +
                         '">씨티 전망 전달문</a>')
        for label, url in item.get("context_links", ()):
            if "investing.com" in (urlparse(url).hostname or ""):
                short = "씨티 11/3"
            elif "trendforce.com" in (urlparse(url).hostname or ""):
                short = "트렌드포스 11/19"
            else:
                short = label
            links.append('<a href="' + html.escape(url, quote=True) +
                         '">' + html.escape(short) + '</a>')
        if links:
            lines.append("근거: " + " · ".join(links))
        pages.append("\n".join(lines))
    return ("\n\n" + BREAK + "\n\n").join(pages).strip() + ("\n" if pages else "")


def render_supplier_ownership(items: list[dict], checked_at: str) -> str:
    """One compact, evidence-linked supplier M&A *possibility* notice; no changes to collection or dedupe."""
    sections = []
    for item in items:
        lines = [
            "<b>[HBM | 삼성·SK 소부장 인수 가능성]</b>",
            "확인 " + html.escape(checked_at[:16].replace("T", " ")) + " KST",
            "<b>■ " + html.escape(item.get("short_title") or item["label"]) + "</b>",
        ]
        lines.extend("• " + html.escape(fact) for fact in
                     (item.get("brief_facts") or item["facts"]))
        lines.append("• 주의: " + html.escape(item.get("brief_caution") or item["caution"]))
        url = item.get("source") or ""
        if url:
            lines.append('원문: <a href="' + html.escape(url, quote=True) +
                         '">파이낸셜뉴스(11/23)</a>')
        sections.append("\n".join(lines))
    return ("\n\n" + BREAK + "\n\n").join(sections).strip() + ("\n" if sections else "")


def render(group: str, items: list[dict], checked_at: str) -> str:
    """Readable, source-linked Telegram digest; keep all material facts visible.

    Break only at entire-event boundaries; never chop an item mid-sentence or
    silently truncate because the 4096-unit Telegram HTML limit is near.
    """
    if group == "samsung_memory_lta":
        return render_samsung_memory_lta(items, checked_at)
    if group == "citi_price_revision":
        return render_citi_price_revision(items, checked_at)
    if group == "supplier_ownership":
        return render_supplier_ownership(items, checked_at)
    if group == "nvidia_commitments":
        # Only the NVIDIA supply-commitment notice uses the compact display.
        header = ("<b>[HBM 감시 | 엔비디아 공급약정 변화]</b>\n"
                  f"확인 {html.escape(checked_at[:16].replace('T', ' '))} KST")
    else:
        header = ("<b>[HBM 기존 감시 | 중요 신규 변화]</b>\n"
                  f"<b>{html.escape(GROUPS[group])}</b>\n"
                  f"확인 {html.escape(checked_at[:16].replace('T', ' '))} KST · 전망/실적 단계 구분")
    sections = []
    for item in items:
        name = item.get("short_title") or item["label"]
        lines = [f"<b>■ {html.escape(name)}</b>"]
        if not item.get("brief_facts"):
            lines.append(f"• 최초 보도 {html.escape(item['date'])} · {html.escape(item['lineage'])}")
        lines.extend("• " + html.escape(line) for line in
                     (item.get("brief_facts") or item["facts"]))
        caution = item.get("brief_caution") or item["caution"]
        lines.append("• 주의: " + html.escape(caution))
        if item.get("verified_source_links"):
            lines.append("• " + item.get("verified_source_caption", "업체별 확인 근거") + ": " + " · ".join(
                f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
                for label, url in item["verified_source_links"]))
        else:
            lines.append(f'• <a href="{html.escape(item["source"], quote=True)}">근거 기사</a>'
                         f' ({html.escape(item["source_label"])})')
        if item.get("context_links"):
            related = " · ".join(
                f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
                for label, url in item["context_links"]
            )
            lines.append("• 비교 근거: " + related)
        sections.append("\n".join(lines))
    # The downstream currency guard may expand each USD price with KRW;
    # reserve room before GitHub's 3600-unit safe Telegram chunk limit.
    pages = []
    page = header
    for section in sections:
        candidate = page + "\n\n" + section
        if len(candidate.encode("utf-16-le")) // 2 > (3100 if group == "roadshow" else 2600) and page != header:
            pages.append(page)
            page = header + " · 계속\n\n" + section
        else:
            page = candidate
    if page != header:
        pages.append(page)
    return ("\n\n" + BREAK + "\n\n").join(pages).strip() + "\n"

def apply(previous: dict, checked_at: str, fetcher=fetch_article) -> tuple[dict, list[str], dict]:
    result = copy.deepcopy(previous)
    sub = result.get("hbm_material_event_watch") or {}
    existing = set(sub.get("seen_keys") or [])
    new = []
    gaps = []
    for report in REPORTS:
        if report["key"] in existing:
            continue
        if not set(report.get("requires_prior_keys") or ()) <= existing:
            continue
        # A publication scheduled in the future must not be fetched or sent.
        if date.fromisoformat(checked_at[:10]) < date.fromisoformat(report["date"]):
            continue
        if report.get("not_before_kst") and datetime.fromisoformat(checked_at) < datetime.fromisoformat(report["not_before_kst"]):
            continue
        if (date.fromisoformat(checked_at[:10]) - date.fromisoformat(report["date"])).days > report.get("max_age_days", MAX_AGE_DAYS):
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
                for group in ("glass", "hbm", "intel", "allocation", "financial", "cycle", "roadshow", "hybrid_equipment", "nvidia_commitments", "samsung_memory_lta", "citi_price_revision", "supplier_ownership")
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
