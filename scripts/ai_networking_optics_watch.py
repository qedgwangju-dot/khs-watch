#!/usr/bin/env python3
"""AI networking / optics structural-change web watcher.

Sources are Google News RSS queries spanning official company releases and major media.
The watcher is deliberately event-driven: first run establishes a baseline and later
runs emit Telegram-ready HTML only for new, high-signal items.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "ai_networking_optics_watch_state.json"
PENDING_PATH = ROOT / "out" / "ai_networking_optics_watch_pending_state.json"
ALERT_PATH = ROOT / "out" / "ai_networking_optics_watch_telegram.html"
STATUS_PATH = ROOT / "out" / "ai_networking_optics_watch_status.md"

KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime.now(dt.timezone.utc)

COMPANIES = {
    "NVIDIA": {
        "ticker": "NVDA",
        "aliases": ["NVIDIA", "Nvidia"],
        "query": 'NVIDIA (Spectrum-X OR NVLink OR BlueField OR networking OR Ethernet OR CPO OR "co-packaged optics" OR "silicon photonics" OR 1.6T OR 3.2T)',
    },
    "Broadcom": {
        "ticker": "AVGO",
        "aliases": ["Broadcom"],
        "query": 'Broadcom (AI Ethernet OR Tomahawk OR Thor OR networking OR optical OR CPO OR "co-packaged optics" OR 1.6T OR 3.2T)',
    },
    "Arista Networks": {
        "ticker": "ANET",
        "aliases": ["Arista Networks", "Arista"],
        "query": '"Arista Networks" (AI networking OR Ethernet OR 800G OR 1.6T OR 3.2T OR optics OR optical OR cluster OR hyperscaler)',
    },
    "Marvell": {
        "ticker": "MRVL",
        "aliases": ["Marvell"],
        "query": 'Marvell (optical DSP OR SerDes OR interconnect OR networking OR 800G OR 1.6T OR 3.2T OR CPO OR "co-packaged optics" OR "Celestial AI" OR "photonic fabric" OR "200G/lane" OR DAC OR ACC OR "active copper cable" OR "co-packaged copper")',
    },
    "Lumentum": {
        "ticker": "LITE",
        "aliases": ["Lumentum"],
        "query": 'Lumentum (AI datacenter OR data center OR optical OR laser OR CPO OR 800G OR 1.6T OR 3.2T OR transceiver OR ELS OR ELSFP OR "external laser source" OR "external light source" OR "CW laser" OR UHP OR 350mW OR 400mW)',
    },
    "Coherent": {
        "ticker": "COHR",
        "aliases": ["Coherent"],
        "query": 'Coherent (PhotonLink OR "integrated optics" OR "complete optical solution" OR "end-to-end" OR "vertical integration" OR CPO OR NPO OR "chip-to-chip" OR "silicon photonics" OR SiPh OR InP OR ELS OR ELSFP OR "external laser source" OR "external light source" OR "CW laser" OR 400mW OR "specialty fiber" OR "polarization-maintaining fiber" OR "mode-matching fiber" OR "multicore fiber" OR "customer engagement" OR "long-term agreement" OR "content opportunity" OR 800G OR 1.6T OR 3.2T)',
    },
    "US Optical Policy": {
        "ticker": "FCC/의회",
        "aliases": ["FCC", "Federal Communications Commission", "U.S. Senate", "Congress"],
        "queries": [
            '"optical transceiver" (FCC OR "Federal Communications Commission") (China OR Chinese OR restriction OR rule OR "Covered List" OR 3.2T OR "domestic content" OR 65% OR 75%)',
            '"optical transceiver" (Senate OR Congress OR "national security systems") (China OR Chinese OR Innolight OR Eoptolink)',
            '"optical transceiver" ("Buy American" OR "domestic end product" OR HBOM OR SBOM)',
            '("Morgan Stanley" OR "Marc Lehman") (FCC OR optical OR transceiver) (3.2T OR 65% OR 75% OR Lumentum OR Coherent OR AAOI)',
        ],
    },
    "AXT": {
        "ticker": "AXTI",
        "aliases": ["AXT", "AXT Inc.", "AXT-Tongmei", "Tongmei"],
        "queries": [
            'AXT (InP OR "indium phosphide") (substrate OR shortage OR "export license" OR capacity OR "data center" OR optical)',
            'AXT ("6-inch InP" OR "6 inch InP") (Coherent OR Lumentum OR Casela OR "capacity reservation" OR prepayment OR "long-term supply")',
            'AXT InP (capacity reservation OR deposit OR prepayment OR "crystal growth" OR pilot OR yield OR "mass production")',
        ],
    },
    "InP Supply Chain": {
        "ticker": "InP 공급망",
        "aliases": ["InP", "indium phosphide", "Sumitomo Electric", "IQE", "Casela"],
        "queries": [
            '"indium phosphide" substrate ("data center" OR optical OR transceiver OR CPO OR 1.6T OR 3.2T) (shortage OR "lead time" OR capacity OR price OR export)',
            '"InP substrate" (shortage OR capacity OR "export license" OR "lead time" OR "capacity reservation" OR prepayment) (laser OR transceiver OR AI OR CPO)',
            '("6-inch InP" OR "6 inch InP") (Coherent OR Lumentum OR Casela OR capacity OR agreement OR prepayment)',
        ],
    },
    "GaAs Optical Supply Chain": {
        "ticker": "GaAs 광통신",
        "aliases": ["GaAs", "gallium arsenide", "WIN Semiconductors", "WIN Semi", "VPEC", "Visual Photonics Epitaxy"],
        "queries": [
            '("GaAs" OR "gallium arsenide" OR "WIN Semiconductors" OR "WIN Semi" OR VPEC) ("1.6T" OR "3.2T" OR CPO OR optical OR transceiver OR photodiode OR laser) (capacity OR shipment OR demand OR order OR shortage OR pricing OR qualification)',
            '("砷化鎵" OR "穩懋" OR "全新") ("光通訊" OR "1.6T" OR CPO) (出貨 OR 產能 OR 訂單 OR 需求 OR 漲價 OR 驗證)',
        ],
        "locales": [
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
            {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
        ],
    },
    "Applied Optoelectronics": {
        "ticker": "AAOI",
        "aliases": ["Applied Optoelectronics", "AOI", "AAOI"],
        "query": '"Applied Optoelectronics" (800G OR 1.6T OR 3.2T OR transceiver OR optical OR hyperscaler OR customer OR capacity OR shipment OR FCC OR China OR ECOC)',
    },
    "AAOI Taiwan Power-to-Production": {
        "ticker": "AAOI/BE",
        "aliases": ["Applied Optoelectronics", "AAOI", "祥茂光電", "Bloom Energy", "賀喜能源"],
        "queries": [
            '("祥茂光電" OR "Applied Optoelectronics" OR "AAOI") ("Bloom Energy" OR "賀喜能源" OR "Leadray") (SOFC OR 燃料電池 OR 發電 OR 供電 OR power OR expansion)',
            '("祥茂光電" OR "AAOI Taiwan" OR "AOI Taiwan") (Bloom OR SOFC OR "fuel cell" OR "on-site power" OR power OR 供電 OR 電力 OR 擴廠) (installation OR construction OR permit OR supply OR operation OR 2027 OR MW)',
            '("祥茂光電" OR "賀喜能源") ("驗收" OR "補助" OR "供氣" OR "運轉" OR "併網" OR "發電" OR "量產" OR "出貨" OR "電力" OR Bloom)',
        ],
        "locales": [
            {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ],
    },
    "Fabrinet": {
        "ticker": "FN",
        "aliases": ["Fabrinet"],
        "query": '"Fabrinet" ("data center" OR datacom OR optical OR 800G OR 1.6T OR CPO OR "optical packaging") (customer OR agreement OR order OR capacity OR production OR shipment OR revenue OR guidance OR ramp)',
    },
    "CPO Packaging & Test": {
        "ticker": "CPO 패키징·검사",
        "aliases": ["TSMC", "COUPE", "CPO testing", "optical engine", "electro-optical testing"],
        "queries": [
            'CPO (COUPE OR "advanced packaging" OR "optical engine") (yield OR capacity OR ramp OR production OR bottleneck OR order OR qualification OR shipment)',
            'CPO (testing OR "electro-optical test" OR "electro optical test" OR burn-in OR "high-power module socket" OR "testing throughput") (production OR volume OR capacity OR bottleneck OR standard OR qualification)',
            '("silicon photonics" OR SiPh) (packaging OR "fiber attach" OR FAU OR coupling) (yield OR production OR capacity OR qualification OR reliability OR shipment)',
            '("CPO" OR "COUPE") ("FAU" OR "fiber array" OR "grating coupling" OR "edge coupling") ("test time" OR "insertion loss" OR "coupling loss" OR "alignment" OR "yield" OR "volume production")',
            '("CPO" OR "co-packaged optics" OR "silicon photonics" OR SiPh OR COUPE) ("package substrate" OR "packaging substrate" OR "packaged substrate" OR "substrate-level multi-chip" OR interposer OR "glass substrate" OR "glass interposer" OR "ABF substrate" OR "organic substrate") (customer OR "design win" OR qualification OR production OR shipment OR order OR capacity OR yield OR warpage OR thermal OR "insertion loss" OR "low loss" OR CTE OR bottleneck)',
        ],
    },
    "Opticore": {
        "ticker": "380540.KQ",
        "aliases": ["옵티코어", "Opticore"],
        "queries": [
            '"옵티코어" ("광트랜시버" OR "400G" OR "800G" OR "1.6T") (수주 OR 공급계약 OR 발주 OR 검수 OR 납품 OR 계약기간 OR 정정 OR "AI 데이터센터")',
            '"Opticore" ("optical transceiver" OR 400G OR 800G OR 1.6T) (order OR contract OR shipment OR qualification OR "data center")',
        ],
        "locales": [
            {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ],
    },
    "OE Solutions": {
        "ticker": "138080.KQ",
        "aliases": ["오이솔루션", "OE Solutions"],
        "queries": [
            '"오이솔루션" (800G OR 1.6T OR ELSFP OR EML OR 광트랜시버) (샘플 OR 검증 OR 인증 OR 양산 OR 수주 OR 공급 OR 출하 OR 고객)',
            '"OE Solutions" (800G OR 1.6T OR ELSFP OR EML OR transceiver) (sample OR qualification OR certification OR shipment OR production OR customer OR order)',
        ],
        "locales": [
            {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ],
    },
    "Sungho Electronics / ADST": {
        "ticker": "043260.KQ",
        "aliases": ["성호전자", "Sungho Electronics", "ADST", "에이디에스테크"],
        "queries": [
            '("성호전자" OR "에이디에스테크" OR ADST) (CPO OR 광트랜시버 OR 광정렬 OR "렌즈 얼라인먼트" OR "Fiber Array Alignment" OR 검사장비 OR 외부광원) (수주 OR 발주 OR PO OR 공급 OR 납품 OR 검수 OR 양산 OR 증설 OR 고객)',
            '("Sungho Electronics" OR ADST) (CPO OR "co-packaged optics" OR "active alignment" OR "lens alignment" OR "fiber array alignment" OR inspection OR ELS) (order OR PO OR contract OR shipment OR qualification OR production OR customer)',
        ],
        "locales": [
            {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ],
    },
    "POET Technologies": {
        "ticker": "POET",
        "aliases": ["POET Technologies", "POET", "Optical Interposer", "Sivers Semiconductors"],
        "query": '"POET Technologies" (CPO OR "co-packaged optics" OR ELS OR "external light source" OR "external laser source" OR "Optical Interposer" OR Sivers) (customer OR sampling OR qualification OR production OR shipment OR order OR contract OR design win OR manufacturing)',
    },
    "TFLN Supply Chain": {
        "ticker": "TFLN 공급망",
        "aliases": ["TFLN", "thin-film lithium niobate", "thin film lithium niobate", "HyperLight", "AFR Milan", "Advanced Fiber Resources"],
        "queries": [
            '("thin-film lithium niobate" OR "thin film lithium niobate" OR TFLN) (CPO OR NPO OR LPO OR "200G/lane" OR "400G/lane") (customer OR sampling OR qualification OR production OR shipment OR foundry OR capacity OR order OR "design win")',
            '(HyperLight OR "AFR Milan" OR "Advanced Fiber Resources") (TFLN OR modulator) ("AI infrastructure" OR datacenter OR "data center" OR CPO OR NPO) (production OR customer OR shipment OR qualification OR sampling OR capacity OR order)',
        ],
    },
    "ELS Connector Supply Chain": {
        "ticker": "ELSFP 연결부품",
        "aliases": ["ELSFP", "SENKO", "TE Connectivity", "Molex", "Furukawa Electric", "blind-mate"],
        "queries": [
            '(ELSFP OR "external laser source") ("blind-mate" OR "blind mate" OR connector OR ferrule OR "insertion loss") (CPO OR NPO) (qualification OR production OR shipment OR customer OR order OR standard OR reliability)',
            '("SENKO" OR "TE Connectivity" OR Molex OR "Furukawa Electric") ELSFP (CPO OR "external laser") (production OR shipment OR qualification OR customer OR order OR "OIF-ELSFP")',
        ],
    },
    "Volantis": {
        "ticker": "비상장",
        "aliases": ["Volantis", "Volantis Semiconductor"],
        "queries": [
            'Volantis',
            '"Volantis" ("Series A" OR funding OR financing OR raises OR A-1 OR photonic OR VCSEL)',
            '"Volantis" (A-1 OR "photonic memory" OR "optical memory" OR "memory wall" OR "optical fabric" OR VCSEL OR inference) (customer OR sampling OR silicon OR tapeout OR benchmark OR commercialization OR delivery OR production OR partnership OR funding OR raises)',
            '"Volantis" ("10,000 tokens" OR "20 trillion" OR "240 TB/s" OR "10 TB" OR "1 pJ/bit" OR "220 memory chips")',
        ],
    },
    "Lightmatter": {
        "ticker": "비상장",
        "aliases": ["Lightmatter", "Passage"],
        "query": 'Lightmatter (Passage OR Guide OR photonic OR optical OR CPO OR NPO OR CPX OR "NVLink Fusion") (sampling OR customer OR deployment OR production OR shipment OR validation OR benchmark OR partnership OR funding OR financing OR manufacturing)',
    },
    "Ayar Labs": {
        "ticker": "비상장",
        "aliases": ["Ayar Labs", "TeraPHY", "SuperNova"],
        "query": '"Ayar Labs" (TeraPHY OR SuperNova OR optical OR CPO OR "NVLink Fusion" OR "extended memory") (customer OR deployment OR production OR shipment OR validation OR qualification OR sampling OR partnership OR funding OR financing OR "high-volume manufacturing" OR Wiwynn)',
    },
    "Xscape Photonics": {
        "ticker": "비상장",
        "aliases": ["Xscape Photonics", "FalconX", "ChromX", "CombX"],
        "query": '"Xscape Photonics" (FalconX OR ChromX OR CombX OR photonic OR optical OR laser) (production OR shipment OR customer OR sampling OR qualification OR partnership OR capacity OR funding)',
    },
    "Astera Labs": {
        "ticker": "ALAB",
        "aliases": ["Astera Labs", "Astera"],
        "query": '"Astera Labs" (PCIe OR CXL OR Scorpio OR fabric OR interconnect OR retimer OR AI rack OR networking)',
    },
    "Corning": {
        "ticker": "GLW",
        "aliases": ["Corning"],
        "query": 'Corning (AI data center OR datacenter OR optical communications OR fiber OR fibre OR cable OR connector OR CPO OR "co-packaged optics" OR photonics OR "glass substrate" OR advanced packaging)',
    },
    "Samsung Electronics": {
        "ticker": "005930.KS",
        "aliases": ["Samsung Electronics", "Samsung Foundry"],
        "query": '"Samsung Foundry" ("silicon photonics" OR SiPh OR PIC OR "optical module" OR "optical engine" OR CPO OR NPO OR "photonics foundry" OR "design win" OR "mass production")',
    },
    "OCS Optical Circuit Switching": {
        "ticker": "OCS 광회로",
        "aliases": ["Optical Circuit Switching", "OCS", "Lumentum", "iPronics", "Lumotive", "nEye", "POLATIS", "HUBER+SUHNER"],
        "queries": [
            '("optical circuit switch" OR "optical circuit switching") (NVIDIA OR GPU OR hyperscaler) (deployed OR deployment OR purchase OR order OR contract OR customer OR shipment OR "production")',
            '("optical circuit switching" OR "OCS switch") (Lumentum OR "iPronics" OR "Lumotive" OR "nEye" OR "Polatis" OR "Google") (order OR qualification OR shipped OR deployment OR interop OR standard OR production)',
            '("OCP" OR "Open Compute Project") ("optical circuit switching" OR "OCS") ("specification" OR "interoperability" OR "standard" OR "approved" OR "adopted" OR "NVIDIA")',
        ],
    },
    "Huawei OPEN NPO": {
        "ticker": "NPO 표준",
        "aliases": ["Huawei", "OPEN NPO", "华为", "近封装光学"],
        "queries": [
            '("Huawei" OR "OPEN NPO") ("near-packaged optics" OR "NPO") (MSA OR standard OR interop OR specification OR customer OR order OR production OR shipment OR adoption)',
            '("华为" OR "OPEN NPO") ("近封装光学" OR "NPO") ("协议" OR "标准" OR "互操作" OR "认证" OR "量产" OR "订单" OR "交付" OR "客户")',
        ],
        "locales": [
            {"hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"},
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ],
    },
    "CPO Equipment Supply Chain": {
        "ticker": "장비 공급망",
        "aliases": [
            "Chieftek", "Chieftek Precision", "直得",
            "GMT Global", "GMT GLOBAL", "高明鐵",
            "TOYO Automation", "TOYO", "東佑達",
            "ficonTEC", "Suruga Seiki", "Allring Tech", "FitTech", "萬潤",
        ],
        "queries": [
            'CPO 設備 直得 高明鐵 東佑達',
            'CPO 設備 出貨 擴產',
            'CPO 光耦合 對位 設備 訂單 能見度',
            '矽光子 設備 直得 高明鐵 東佑達',
            '高明鐵 CPO 訂單 產能',
            '東佑達 CPO 訂單 驗證',
            '直得 CPO 對位 線性馬達',
            '萬潤 CPO 光耦合 設備',
            '"Chieftek" CPO alignment equipment',
            '"GMT Global" CPO optical coupling',
            '"TOYO Automation" CPO optical coupling',
            'ficonTEC CPO optical coupling alignment',
            '"Suruga Seiki" CPO optical coupling',
            '("FAU" OR "fiber array unit") ("ficonTEC" OR "Suruga" OR "TOYO" OR "GMT Global" OR "Allring" OR "FitTech") (order OR shipment OR production OR equipment OR "test time" OR throughput)',
        ],
        "locales": [
            {"hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
            {"hl": "en-US", "gl": "US", "ceid": "US:en"},
        ],
    },
}

DISPLAY_NAMES_KO = {
    "NVIDIA": "엔비디아",
    "Broadcom": "브로드컴",
    "Arista Networks": "아리스타 네트웍스",
    "Marvell": "마벨",
    "Lumentum": "루멘텀",
    "Coherent": "코히런트",
    "US Optical Policy": "미국 광트랜시버 정책",
    "AXT": "AXT",
    "InP Supply Chain": "InP 기판 공급망",
    "GaAs Optical Supply Chain": "GaAs 광통신 기판 공급망",
    "Applied Optoelectronics": "어플라이드 옵토일렉트로닉스",
    "AAOI Taiwan Power-to-Production": "AAOI 대만 전력·증설",
    "Fabrinet": "파브리넷",
    "CPO Packaging & Test": "CPO 패키징·검사",
    "Opticore": "옵티코어",
    "OE Solutions": "오이솔루션",
    "Sungho Electronics / ADST": "성호전자·ADST",
    "POET Technologies": "POET Technologies",
    "TFLN Supply Chain": "TFLN 광변조기 공급망",
    "ELS Connector Supply Chain": "ELSFP 블라인드메이트 연결부품",
    "Volantis": "볼란티스",
    "Lightmatter": "라이트매터",
    "Ayar Labs": "아야르 랩스",
    "Xscape Photonics": "엑스케이프 포토닉스",
    "Astera Labs": "아스테라 랩스",
    "Corning": "코닝",
    "Samsung Electronics": "삼성전자",
    "CPO Equipment Supply Chain": "CPO 장비 공급망",
    "OCS Optical Circuit Switching": "광회로 스위칭(OCS)",
    "Huawei OPEN NPO": "화웨이 OPEN NPO",
}

TRUSTED_SOURCES = {
    "Reuters", "Bloomberg", "Financial Times", "The Wall Street Journal", "CNBC",
    "DigiTimes", "DIGITIMES", "Investing.com", "Barron's", "MarketWatch",
    "NVIDIA Blog", "NVIDIA Newsroom", "Broadcom", "Arista Networks", "Marvell",
    "Lumentum", "Coherent", "AXT", "WIN Semiconductors", "VPEC", "Applied Optoelectronics",
    "Fabrinet", "TSMC", "TrendForce",
    "Opticore", "옵티코어", "OE Solutions", "오이솔루션",
    "Sungho Electronics", "성호전자", "ADST", "에이디에스테크",
    "POET Technologies", "POET", "Sivers Semiconductors",
    "HyperLight", "AFR Milan", "Advanced Fiber Resources",
    "SENKO", "TE Connectivity", "Molex", "Furukawa Electric",
    "Volantis", "Lightmatter", "Ayar Labs", "Xscape Photonics",
    "KIND", "KRX", "한국거래소",
    "연합뉴스", "전자신문", "ETNews", "Federal Communications Commission", "FCC",
    "U.S. Senate", "Congress.gov", "Astera Labs", "Corning",
    "TrendForce", "MoneyDJ", "Economic Daily News", "UDN", "經濟日報",
    "GMT GLOBAL INC.", "TOYO Automation", "Chieftek Precision",
    "Open Compute Project", "OCP", "iPronics", "Lumotive", "nEye",
    "HUBER+SUHNER", "POLATIS", "Huawei", "华为", "Huawei Cloud", "华为云",
    "Open AI Infra", "Open AI Infra Community",
    "Leadray Energy", "賀喜能源", "Bloom Energy", "TechNews", "科技新報",
    "時報資訊", "時報", "工商時報", "Reccessary", "富聯網",
}

HIGH_SIGNAL_PATTERNS = [
    r"\b3\.2\s*[Tt]\b", r"\b1\.6\s*[Tt]\b", r"\b800\s*[Gg]\b",
    r"co[- ]?packaged optics?", r"\bCPO\b", r"silicon photonics?",
    r"mass production", r"volume production", r"volume shipment", r"shipments?",
    r"customer qualification", r"customer certification", r"qualified", r"certified",
    r"adopt(?:ed|ion)?", r"deploy(?:ed|ment)?", r"production ramp", r"ramp(?:ing)?",
    r"backlog", r"bookings?", r"orders?", r"guidance", r"revenue",
    r"capacity expansion", r"expand(?:ing|s|ed)? capacity", r"new factory", r"new plant",
    r"shortage", r"constraint", r"bottleneck", r"supply tight", r"pricing", r"price increase",
    r"copper", r"optical", r"fiber", r"fibre", r"transceiver", r"laser",
    r"\bELS\b", r"\bELSFP\b", r"external laser source", r"external light source",
    r"high[- ]power CW", r"ultra[- ]high[- ]power", r"\bUHP\b",
    r"TFLN", r"thin[- ]film lithium niobate", r"thin film lithium niobate",
    r"blind[- ]mate", r"insertion loss", r"hot[- ]swap", r"field[- ]replaceable",
    r"200G/lane", r"400G/lane", r"direct attach copper", r"\bDAC\b", r"\bACC\b", r"co[- ]packaged copper",
    r"reliability", r"lifetime", r"thermal", r"laser failure",
    r"data movement", r"interconnect", r"fabric", r"retimer", r"PCIe", r"CXL",
    r"photonic memory", r"optical memory", r"memory wall", r"memory pooling",
    r"photonic AI", r"photonic inference", r"AI inference system",
    r"compute[- ]to[- ]memory", r"optical fabric", r"micro[- ]?VCSEL", r"VCSEL",
    r"tokens? per second", r"tok/s", r"20\s*trillion", r"10\s*trillion",
    r"240\s*TB/s", r"10\s*TB", r"1\s*pJ/bit", r"220\s*memory chips",
    r"integrated inference engines?", r"customer sampling", r"silicon validation", r"tape[- ]?out", r"benchmark",
    r"PhotonLink", r"integrated optics?", r"complete optical solutions?", r"end[- ]to[- ]end",
    r"vertical integration", r"one[- ]stop", r"\bNPO\b", r"chip[- ]to[- ]chip",
    r"customer engagements?", r"long[- ]term agreements?", r"anchor customers?",
    r"content opportunity", r"content per", r"100\s*Tbps", r"specialty fibers?",
    r"polarization[- ]maintaining", r"mode[- ]matching", r"multicore fibers?",
    r"\bInP\b", r"indium phosphide", r"InP substrate", r"export licen[cs]e",
    r"\bGaAs\b", r"gallium arsenide", r"砷化鎵",
    r"6[- ]inch InP", r"capacity reservation", r"prepayment", r"deposit",
    r"long[- ]term supply", r"crystal growth", r"pilot production",
    r"yield", r"test throughput", r"burn[- ]?in", r"standardization", r"reliability framework", r"wafer substrate",
    r"\bSiPh\b", r"photonics foundry", r"design win",
    r"\bFCC\b", r"Federal Communications Commission", r"Covered List",
    r"equipment authorization", r"Chinese[- ]made", r"China[- ]based",
    r"domestic content", r"domestic end product", r"Buy American",
    r"\b65\s*%\b", r"\b75\s*%\b", r"exempt(?:ion|ions)?", r"restrictions?",
    r"national security systems?", r"Inn[o]?light", r"Eoptolink",
    r"광트랜시버", r"광통신", r"AI 데이터센터", r"ELSFP", r"EML",
    r"공급계약", r"수주", r"검수", r"납품", r"계약기간", r"샘플", r"samples?", r"sampling", r"양산", r"출하",
    r"optical coupling", r"active alignment", r"alignment modules?", r"aligners?",
    r"COUPE", r"advanced packaging", r"optical engine yield", r"electro[- ]optical test",
    r"testing throughput", r"burn[- ]?in", r"high[- ]power module sockets?", r"fiber attach",
    r"package substrate", r"packaging substrate", r"packaged substrate", r"substrate[- ]level multi[- ]chip",
    r"glass substrate", r"glass interposer", r"ABF substrate", r"organic substrate", r"interposer",
    r"warpage", r"coefficient of thermal expansion", r"\bCTE\b", r"low[- ]loss", r"low\s*D[fk]",
    r"motion platforms?", r"linear motors?", r"6[- ]axis", r"nanometer", r"50\s*nm",
    r"\bFAU\b", r"\bOSAT\b", r"order visibility", r"delivery visibility",
    r"production capacity", r"\bCAPA\b", r"new lines?", r"assembly lines?",
    r"factory expansion", r"capacity doubles?", r"utilization", r"qualification",
    r"optical circuit switch(?:ing)?", r"\bOCS\b",
    r"\bOPEN NPO\b", r"near[- ]packaged optics", r"近封装光学", r"光电路交换",
    r"validation", r"verification", r"ahead[- ]of[- ]time orders?",
]

ACTION_PATTERNS = [
    r"mass production", r"volume production", r"shipment", r"customer", r"qualified",
    r"certified", r"adopt", r"deploy", r"ramp", r"backlog", r"booking", r"order",
    r"guidance", r"revenue", r"capacity", r"factory", r"plant", r"shortage",
    r"constraint", r"bottleneck", r"price", r"pricing", r"launch", r"introduc",
    r"engagement", r"agreement", r"anchor customer", r"content opportunity",
    r"integrated optics", r"vertical integration", r"one[- ]stop", r"chip[- ]to[- ]chip",
    r"specialty fiber", r"silicon photonics", r"photonics foundry", r"design win",
    r"optical coupling", r"alignment", r"aligner", r"motion platform", r"linear motor",
    r"FAU", r"OSAT", r"order visibility", r"delivery visibility", r"new line",
    r"assembly line", r"factory expansion", r"capacity", r"CAPA", r"utilization",
    r"qualification", r"validation", r"verification", r"sampling", r"sample",
    r"silicon", r"tape[- ]?out", r"benchmark", r"commercialization", r"delivery",
    r"funding", r"financing", r"raises?", r"series\s+[abc]",
    r"reliability", r"lifetime", r"MTBF", r"failure rate", r"thermal",
    r"blind[- ]mate", r"insertion loss", r"hot[- ]swap", r"field[- ]replaceable",
    r"OIF[- ]ELSFP", r"reach", r"meter", r"metre",
    r"final rule", r"proposed rule", r"rulemaking", r"adopt(?:s|ed)?", r"effective",
    r"restrict(?:s|ed|ion|ions)?", r"ban(?:s|ned)?", r"prohibit(?:s|ed|ion)?",
    r"introduc(?:es|ed)? bill", r"legislation", r"covered list", r"equipment authorization",
    r"domestic content", r"domestic end product", r"buy american", r"exempt(?:ion|ions)?",
    r"export licen[cs]e", r"capacity reservation", r"prepayment", r"deposit",
    r"long[- ]term supply", r"crystal growth", r"pilot production",
    r"공급계약", r"단일판매", r"수주", r"발주서", r"검수", r"납품", r"계약기간",
    r"정정", r"샘플", r"samples?", r"sampling", r"고객.{0,12}(검증|평가|인증)", r"양산", r"출하", r"생산능력", r"증설",
    r"訂單", r"能見度", r"出貨", r"量產", r"擴產", r"產能", r"產能利用率",
    r"驗證", r"認證", r"導入", r"光耦合", r"對位", r"線性馬達", r"六軸",
    r"interoperability", r"ratif(?:ied|ication)", r"specification",
    r"互操作", r"协议", r"标准", r"量产", r"交付", r"客户",
]

NOISE_PATTERNS = [
    r"stock price", r"price target", r"analyst rating", r"upgrade[s]? .* stock",
    r"downgrade[s]? .* stock", r"options activity", r"insider sells?", r"dividend",
    r"investment story", r"investment case", r"why .* stock", r"simply wall st",
    r"futu niu niu", r"stockstory", r"seeking alpha quant",
    # Market-price/reaction stories are not structural AI-optics events.
    r"\bshares?\b", r"\bstock\b.{0,40}\b(rise|rises|jump|jumps|gain|gains|surge|surges|rally|rallies)",
    r"\b(boost|boosts|lift|lifts|send|sends|drive|drives)\b.{0,60}\bshares?\b",
    r"kucoin", r"marsbit", r"huoxing", r"hyperliquid", r"altcoins?",
    r"관련주", r"테마주", r"주가.{0,30}(급등|상승|강세)", r"(급등|상한가).{0,30}주가",
]

SOURCE_PRIORITY = {
    "Coherent": 100, "NVIDIA Blog": 100, "NVIDIA Newsroom": 100,
    "Broadcom": 100, "Arista Networks": 100, "Marvell": 100,
    "Lumentum": 100, "AXT": 100, "Applied Optoelectronics": 100,
    "Fabrinet": 100, "TSMC": 100,
    "Volantis": 100, "Lightmatter": 100, "Ayar Labs": 100, "Xscape Photonics": 100,
    "Sungho Electronics": 100, "성호전자": 100, "ADST": 100, "에이디에스테크": 100,
    "POET Technologies": 100, "POET": 100, "Sivers Semiconductors": 100,
    "HyperLight": 100, "AFR Milan": 100, "Advanced Fiber Resources": 100,
    "SENKO": 100, "TE Connectivity": 100, "Molex": 100, "Furukawa Electric": 100,
    "Opticore": 100, "옵티코어": 100, "OE Solutions": 100, "오이솔루션": 100,
    "KIND": 100, "KRX": 100, "한국거래소": 100, "연합뉴스": 90, "전자신문": 85, "ETNews": 85,
    "Federal Communications Commission": 100, "FCC": 100,
    "U.S. Senate": 100, "Congress.gov": 100, "Astera Labs": 100, "Corning": 100,
    "Samsung Electronics": 100, "Samsung Global Newsroom": 100,
    "Reuters": 95, "Bloomberg": 94, "Financial Times": 93,
    "The Wall Street Journal": 93, "CNBC": 88, "DigiTimes": 85, "DIGITIMES": 85,
    "GlobeNewswire": 84, "PR Newswire": 82,
    "TrendForce": 92, "GMT GLOBAL INC.": 100, "TOYO Automation": 100,
    "Open Compute Project": 100, "OCP": 100, "iPronics": 100,
    "Lumotive": 100, "nEye": 100, "POLATIS": 100, "HUBER+SUHNER": 100,
    "Huawei": 100, "华为": 100, "Huawei Cloud": 100, "华为云": 100,
    "Huawei Computing": 100, "Open AI Infra": 100,
    "Bloom Energy": 100, "Applied Optoelectronics": 100,
    "Leadray Energy": 100, "賀喜能源": 100, "TechNews": 82,
    "科技新報": 82, "時報資訊": 80, "時報": 80,
    "工商時報": 80, "富聯網": 78, "Reccessary": 74,
    "Chieftek Precision": 100, "Economic Daily News": 82, "UDN": 82,
    "經濟日報": 82, "MoneyDJ": 78,
    "HPCwire": 70, "Compound Semiconductor": 70, "Investing.com": 65,
}

STORY_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "how", "in", "into", "is", "it", "its", "of", "on", "or", "the", "to",
    "with", "will", "new", "next", "generation", "corp", "corporation",
    "launch", "launches", "launched", "unveil", "unveils", "unveiled",
    "platform", "supports", "support", "enable", "enables", "enabling",
}


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 khs-watch/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))
    assert last_error is not None
    raise last_error


def parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def event_key(company: str, title: str, source: str) -> str:
    normalized = f"{company}|{title.lower()}|{source.lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def story_tokens(title: str) -> set[str]:
    value = html.unescape(title or "").lower()
    value = re.sub(r"\s+-\s+[^-]{2,80}$", " ", value)
    value = re.sub(r"[^a-z0-9.\uac00-\ud7a3\u4e00-\u9fff]+", " ", value)
    tokens = {
        token for token in value.split()
        if len(token) >= 3 and token not in STORY_STOPWORDS
    }
    return tokens


def _money_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for amount, unit in re.findall(
        r"\$?\s*(\d+(?:\.\d+)?)\s*(million|billion|mn|bn|m|b)\b",
        text or "",
        flags=re.I,
    ):
        normalized = amount.rstrip("0").rstrip(".") if "." in amount else amount
        suffix = "b" if unit.lower() in {"billion", "bn", "b"} else "m"
        token = f"{normalized}{suffix}"
        if token not in tokens:
            tokens.append(token)
    return tokens


VOLANTIS_VERIFIED_BASELINE = {
    "as_of": "2026-10-04",
    "series_a_usd_m": 88.0,
    "total_raised_usd_m": 97.0,
    "first_customer_delivery_year": 2027,
    "optical_reach_mm_min": 200.0,
    "memory_chiplets_min": 220,
    "bandwidth_tb_s_company": 240.0,
    "memory_tb_company": 10.0,
    "energy_pj_per_bit_lt": 1.0,
    "latency_ns_lt": 5.0,
    "ber_lt": 1e-12,
    "external_laser_required": False,
    "laser_architecture": "integrated micro-VCSEL",
    "silicon_photonics_current_architecture_confirmed": False,
    "company_site_model_target_gt_trillion": 10.0,
    "press_release_model_target_gt_trillion": 20.0,
    "model_target_public_material_discrepancy": True,
    "sources": [
        "https://volantissemi.ai/news-insights/our-88m-series-a-demolishing-the-memory-wall-with-photonics-post",
        "https://volantissemi.ai/technology",
        "https://volantissemi.ai/",
        "https://www.prnewswire.com/news-releases/volantis-raises-88m-series-a-to-demolish-the-ai-memory-wall-with-photonics-302895940.html",
    ],
}

KNOWN_PHOTONIC_BASELINE_KEYS = {
    "volantis|funding|series-a",
    "lightmatter|passage|sampling|1.6tbps-per-fiber",
    "lightmatter|nvlink-fusion|ecosystem",
    "ayar|funding|2026-primary-650m",
    "ayar|wiwynn|strategic-investment",
    "ayar|nvlink-fusion|ecosystem",
    "marvell|celestial|acquisition-complete",
    "marvell|celestial|revenue-guidance|v1",
}


def preserve_delivery_metadata(previous: dict, pending: dict) -> dict:
    # Silent checks must not erase proof of the most recent confirmed Telegram send.
    for key in ("last_successful_delivery_kst", "telegram_message_ids", "bot_username"):
        if previous.get(key) is not None:
            pending[key] = previous[key]
    return pending


def canonical_story_key(company: str, title: str) -> str | None:
    text = html.unescape(title or "").lower()
    money = _money_tokens(text)

    if company == POWER_COMPANY:
        result = power_milestone(title)
        return result[2] if result else None

    if company == "Volantis":
        # Preserve the already-seen $88M Series A key, but do not collapse every
        # future financing round into that old event.
        if re.search(r"series\s*a", text, re.I) or re.search(r"\b88\s*(?:m|million)\b", text, re.I):
            return "volantis|funding|series-a"
        series = re.search(r"series\s*([b-z])", text, re.I)
        if series and re.search(r"funding|financing|raises?|capital", text, re.I):
            suffix = "-" + "-".join(money) if money else ""
            return f"volantis|funding|series-{series.group(1).lower()}{suffix}"
        if re.search(r"funding|financing|raises?|capital", text, re.I):
            suffix = "-".join(money) if money else "generic"
            return f"volantis|funding|other|{suffix}"
        if re.search(r"customer sampling|customer delivery|customer deployment|integrated inference engines?", text, re.I):
            return "volantis|a1|customer"
        if re.search(
            r"silicon|tape[- ]?out|benchmark|measured|prototype|240\s*tb/s|>200\s*tb/s|10\s*tb|"
            r"1\s*pj/bit|sub[- ]?5\s*ns|ber\s*<?\s*1e-12|200\s*mm|220\s*memory\s*chiplets?|"
            r"tokens? per second|tok/s",
            text,
            re.I,
        ):
            return "volantis|a1|silicon-performance"
        if re.search(r"vcsel|micro[- ]?vcsel|foundry|wafer|laser|supply chain", text, re.I):
            return "volantis|a1|vcsel-supply"
        if re.search(r"a-1|photonic memory|optical memory|memory wall|optical fabric|memory pooling", text, re.I):
            return "volantis|a1|architecture"

    if company == "Lightmatter":
        if re.search(r"nvlink fusion", text, re.I):
            return "lightmatter|nvlink-fusion|ecosystem"
        if re.search(r"passage", text, re.I) and re.search(r"sampl|customer qualification|customer validation", text, re.I):
            if re.search(r"1\.?6\s*tbps|1\.?6\s*t", text, re.I):
                return "lightmatter|passage|sampling|1.6tbps-per-fiber"
            return "lightmatter|passage|customer-sampling"
        if re.search(r"passage", text, re.I) and re.search(r"production|shipment|deployment|mass production|volume production", text, re.I):
            return "lightmatter|passage|production-deployment"
        if re.search(r"funding|financing|raises?|strategic investment", text, re.I):
            suffix = "-".join(money) if money else "generic"
            return f"lightmatter|funding|{suffix}"

    if company == "Ayar Labs":
        if re.search(r"funding|financing|raises?|capital", text, re.I):
            # Sep-2026 additional $150M brought 2026 primary capital to $650M.
            # Reprints that quote either number are one event, not new alerts.
            if re.search(r"2026", text) and (
                re.search(r"\b150\s*(?:m|million)\b", text, re.I)
                or re.search(r"\b650\s*(?:m|million)\b", text, re.I)
            ):
                return "ayar|funding|2026-primary-650m"
            suffix = "-".join(money) if money else "generic"
            return f"ayar|funding|{suffix}"
        if re.search(r"wiwynn", text, re.I) and re.search(r"invest|strategic", text, re.I):
            return "ayar|wiwynn|strategic-investment"
        if re.search(r"nvlink fusion", text, re.I):
            return "ayar|nvlink-fusion|ecosystem"
        if re.search(r"high[- ]volume manufacturing|volume production|mass production|customer deployment|shipments?", text, re.I):
            return "ayar|hvm|production-deployment"
        if re.search(r"customer sampling|qualification|validation", text, re.I):
            return "ayar|customer-validation"

    if company == "Marvell" and re.search(r"celestial ai|photonic fabric", text, re.I):
        if re.search(r"completed? (?:the )?acquisition|acquisition (?:is )?complete|closes? (?:the )?acquisition|acquires? celestial", text, re.I):
            return "marvell|celestial|acquisition-complete"
        if re.search(r"revenue|run[- ]?rate|guidance|fiscal 2028|fy28|fiscal 2029|fy29", text, re.I):
            # Marvell's original acquisition guidance: H2 FY28 revenue start,
            # $500M annualized run-rate in Q4 FY28 and $1B in Q4 FY29.
            old_v1 = (
                (re.search(r"(?:fiscal\s*)?2028|fy28", text, re.I) and re.search(r"\b500\s*(?:m|million)\b", text, re.I))
                or (re.search(r"(?:fiscal\s*)?2029|fy29", text, re.I) and re.search(r"\b1\s*(?:b|billion)\b", text, re.I))
            )
            if old_v1:
                return "marvell|celestial|revenue-guidance|v1"
            suffix = "-".join(money) if money else re.sub(r"[^a-z0-9]+", "-", text)[:80].strip("-")
            return f"marvell|celestial|revenue-guidance|{suffix or 'generic'}"
        if re.search(r"production|shipment|mass production|volume production", text, re.I):
            return "marvell|celestial|production-shipment"
        if re.search(r"customer|design win|qualification|validation|milestone", text, re.I):
            return "marvell|celestial|customer-validation"

    structure_key = structural_story_key(company, title)
    if structure_key:
        return structure_key

    if company == "US Optical Policy":
        if re.search(r"senate|congress|bill|legislation|national security systems?", text, re.I):
            if re.search(r"signed|enacted|becomes? law", text, re.I):
                return "us-optical-policy|congress|enacted"
            if re.search(r"pass(?:es|ed)?", text, re.I):
                return "us-optical-policy|congress|passed"
            return "us-optical-policy|congress|bill"
        if re.search(r"effective|takes? effect|implementation date", text, re.I):
            return "us-optical-policy|fcc|effective"
        if re.search(r"final rule|finaliz(?:e|es|ed|ing)|adopt(?:s|ed)?", text, re.I):
            return "us-optical-policy|fcc|final"
        if re.search(r"proposed rule|rulemaking|notice|comment|draft|consider", text, re.I):
            return "us-optical-policy|fcc|proposal"
        if re.search(r"3\.2\s*t|65\s*%|75\s*%|domestic content|buy american|exempt", text, re.I):
            parts = []
            if re.search(r"3\.2\s*t", text, re.I):
                parts.append("3.2t")
            if re.search(r"65\s*%", text, re.I):
                parts.append("65")
            if re.search(r"75\s*%", text, re.I):
                parts.append("75")
            if re.search(r"domestic content|domestic end product|buy american", text, re.I):
                parts.append("domestic")
            if re.search(r"exempt", text, re.I):
                parts.append("exemption")
            return "us-optical-policy|fcc|content-scenario|" + "-".join(parts or ["generic"])
        return None

    if company in {"AXT", "InP Supply Chain"} and re.search(r"\binp\b|indium phosphide", text, re.I):
        if re.search(r"export licen[cs]e|restriction|china", text, re.I):
            return "axt|inp|export-policy"
        if re.search(r"shortage|tight|capacity|expand|substrate", text, re.I):
            return "axt|inp|capacity-shortage"

    if company == "Coherent" and "photonlink" in text:
        if re.search(r"customer engagements?|long[- ]term(?:\s+\w+){0,6}\s+agreements?|anchor customers?|design win|secures?.{0,60}agreements?", text, re.I):
            return "coherent|photonlink|customer-contract"
        if re.search(r"content opportunity|content per|100\s*tbps|15,?000", text, re.I):
            return "coherent|photonlink|content-value"
        if re.search(r"chip[- ]to[- ]chip", text, re.I):
            return "coherent|photonlink|chip-to-chip"
        if re.search(r"specialty fibers?|polarization[- ]maintaining|mode[- ]matching|multicore fibers?", text, re.I):
            return "coherent|photonlink|specialty-fiber"
        if re.search(r"\binp\b.*(?:capacity|expand)|(?:capacity|expand).*\binp\b", text, re.I):
            return "coherent|photonlink|inp-capacity"
        if re.search(r"revenue|guidance|mass production|volume production|shipments?|production ramp|ramp(?:ing)?", text, re.I):
            return "coherent|photonlink|commercial-ramp"
        return "coherent|photonlink|launch"
    return None


# CPO packaging / OCS switching / NPO connector placement are three different
# architectures. A common optical keyword is not proof of the same customer or PO.
NEW_STRUCTURE_AXES = {"OCS Optical Circuit Switching", "Huawei OPEN NPO"}
OCS_PRIMARY_SOURCES = {
    "Open Compute Project", "OCP", "NVIDIA Newsroom", "NVIDIA Blog",
    "NVIDIA", "Lumentum", "iPronics", "Lumotive", "nEye", "HUBER+SUHNER",
    "POLATIS", "Google", "Google Cloud", "Microsoft",
    "OCP Foundation", "Open Compute Project Foundation",
}
NPO_PRIMARY_SOURCES = {
    "Huawei", "华为", "Huawei Cloud", "华为云", "Huawei Computing",
    "Open AI Infra", "Open AI Infra Community", "Global Computing Consortium",
}
STRUCTURAL_PRIMARY_DOMAINS = {
    "opencompute.org", "nvidia.com", "lumentum.com", "ipronics.com",
    "lumotive.com", "neye.com", "huber-suhner.com", "google.com",
    "microsoft.com", "huawei.com", "huaweicloud.com",
    "openaiinfra.org",
}
STRUCTURAL_OPTICS_VERSION = 2

# Only true new milestones may alert. Historical 2025 OCS OCP membership and
# July-2026 NPO MSA launch become baseline. Roadmap numbers are not shipments.
KNOWN_NEW_STRUCTURE_KEYS = {
    "ocs|ocp|founding-2025",
    "huawei|open-npo|msa-initial-2026-07",
}


def meaningful_fau_milestone(title: str) -> bool:
    text = html.unescape(title or "")
    if not re.search(r"\bFAU\b|fiber[- ]array|光纖陣列|光纤阵列", text, re.I):
        return True
    # A repeated general note about coupling being a "bottleneck" is not a
    # new production event. Measured yield/accuracy, real order and acceptance are.
    return bool(re.search(
        r"orders?|bookings?|contract|purchase|shipments?|deliver(?:y|ies)|"
        r"mass production|volume production|yield (?:rises?|improves?|reaches?|hits?|falls?)|"
        r"(?:coupling|insertion) loss.{0,20}\d+(?:\.\d+)?\s*dB|"
        r"test(?:ing)? time.{0,20}\d+(?:\.\d+)?\s*(?:s|seconds?|ms)|"
        r"\d+(?:\.\d+)?\s*%\s*(?:yield|pass)|\d+\s*nm|"
        r"(?:passes?|completes?|wins?) (?:customer )?(?:qualification|validation)|qualified|"
        r"產能|量產|出貨|訂單|驗證完成|认证完成|订单|量产|出货",
        text, re.I
    ))


def _explicit_completion_verb(text: str) -> bool:
    return bool(re.search(
        r"sign(?:s|ed)?|secur(?:es|ed)|awarded|receiv(?:es|ed)|beg(?:ins|an)|"
        r"start(?:s|ed)?|complet(?:es|ed)|shipp(?:ed|ing)|deliver(?:s|ed)|"
        r"deploy(?:s|ed)|installs?|validated|qualif(?:ied|ies)|"
        r"发布|签署|获批|量产开始|正式交付|订单落地|完成",
        text, re.I,
    ))


def _headline_plan_only(text: str) -> bool:
    planned = bool(re.search(
        r"plans? to|expected to|expects? to|aims? to|could|may |will deploy|to deploy|"
        r"targets? |eyes? |prepar(?:es?|ing) to|wants? to|"
        r"seeks? to|mulls?|reportedly|considers?|"
        r"拟|计划|预计|有望|考虑|目标是",
        text, re.I,
    ))
    return planned and not _explicit_completion_verb(text)


def classify_structural_axis(company: str, title: str) -> str | None:
    text = html.unescape(title or "").strip()
    if company in NEW_STRUCTURE_AXES and _headline_plan_only(text):
        return None
    if company == "OCS Optical Circuit Switching":
        # "NVIDIA's CPO Ethernet Photonics" is NOT an optical circuit switch.
        if not re.search(
            r"optical circuit switch(?:ing)?|\bOCS\b.{0,30}\bswitch|\bOCS\b.{0,30}光",
            text, re.I
        ):
            return None
        commercial = bool(re.search(
            r"purchase(?:d|s)?|procure(?:d|ment)?|contracts?|orders?|"
            r"ship(?:ped|ment|ments)|deploy(?:ed|ment|s)?|"
            r"pilot(?:s)?|trial(?:s)?|qualif(?:ied|ication)|"
            r"first customer|customer win|design win|installed|production|"
            r"采购|订单|部署|交付|量产|客户",
            text, re.I,
        ))
        standard = bool(re.search(
            r"ratif(?:y|ied)|published? spec(?:ification)?|"
            r"interoperab|standards? release|approved? spec|"
            r"protocol revision|specification v\d|"
            r"互操作|标准发布|规格发布",
            text, re.I,
        ))
        if commercial:
            return "OCS 고객·주문·배치"
        if standard:
            return "OCS 표준·상호운용성"
        return None

    if company == "Huawei OPEN NPO":
        if not re.search(r"\bNPO\b|near[- ]packag(?:e|ed) optics|近封装光学", text, re.I):
            return None
        if not re.search(r"Huawei|华为|OPEN NPO", text, re.I):
            return None
        if re.search(
            r"customer (?:order|contract|acceptance)|"
            r"purchase order|commercial deploy|mass production|volume production|"
            r"production shipments?|manufacturing ramp|"
            r"订单|采购合同|客户导入|客户验证|规模部署|量产|出货|交付",
            text, re.I
        ):
            return "NPO 고객·양산·계약"
        if re.search(
            r"(?:final|updated?|revis(?:ed|ion)|approved?|ratif(?:ied|y)|published?|released?)"
            r".{0,60}(?:MSA|spec(?:ification)?|standard|interop)|"
            r"(?:MSA|spec(?:ification)?|standard|interop).{0,60}"
            r"(?:final|updated?|revis(?:ed|ion)|approved?|ratif(?:ied|y)|published?|released?)|"
            r"标准发布|标准修订|互操作测试|多源协议升级|标准升级|"
            r"(?:MSA|多源协议).{0,30}(?:2\.0|v2|第二版|修订版).{0,20}(?:发布|获批|发布通过)|"
            r"(?:发布|批准).{0,20}(?:MSA|多源协议).{0,20}(?:2\.0|v2|第二版)",
            text, re.I
        ):
            return "NPO 표준 제·개정"
        if re.search(r"new (?:member|partner|signator)|新增成员|新成员加入", text, re.I):
            return "NPO 공급사·생태계 확대"
        return None
    return None


def structural_stage(company: str, category: str, title: str) -> str:
    if category in {"OCS 고객·주문·배치", "NPO 고객·양산·계약"}:
        if re.search(r"mass production|volume production|shipments?|deployed|deployment|量产|出货|部署", title, re.I):
            return "상용 공급·배치 주장"
        return "고객검증·수주 주장"
    if category in {"OCS 표준·상호운용성", "NPO 표준 제·개정"}:
        return "표준화·상호운용성"
    if category == "NPO 공급사·생태계 확대":
        return "표준 생태계 참여"
    return stage_for(title)


def _is_official_structural_source(item: dict) -> bool:
    company = item.get("company") or ""
    name = normalize_text(item.get("source") or "").lower()
    primary = OCS_PRIMARY_SOURCES if company == "OCS Optical Circuit Switching" else NPO_PRIMARY_SOURCES
    if not any(name == a.lower() for a in primary):
        return False
    address = normalize_text(item.get("source_url") or "")
    host = urllib.parse.urlparse(address).hostname or ""
    # A claimed source name alone is not sufficient for a confirmed official
    # story; validate the publisher's actual source domain.
    return any(host == domain or host.endswith("." + domain) for domain in STRUCTURAL_PRIMARY_DOMAINS)


def credible_structural_source(item: dict, all_items: list[dict]) -> bool:
    company = item.get("company") or ""
    if company not in NEW_STRUCTURE_AXES:
        return True
    name = normalize_text(item.get("source") or "").lower()
    if _is_official_structural_source(item):
        return True
    # A third-party headline about NVIDIA OCS deployment / Huawei mass
    # production is not automatically a verified shipment. Require a second
    # independent recognized source describing the *same* event.
    return any(
        other is not item
        and other.get("company") == company
        and normalize_text(other.get("source") or "").lower() != name
        and source_priority(other.get("source") or "") >= 65
        and (
            same_underlying_story(other, item)
            and not same_article_identity(other, item)
        )
        for other in all_items
    )


def evidence_label(item: dict) -> str:
    company = item.get("company")
    if company not in NEW_STRUCTURE_AXES:
        return "공식 확인 수준은 원문별 재검증 필요"
    if _is_official_structural_source(item):
        return "당사자·표준단체 발표 — 계약·양산은 문구별 구분"
    return "독립된 신뢰매체 교차확인 — 공식 계약·양산 여부 별도 확인"


def structural_story_key(company: str, title: str) -> str | None:
    text = html.unescape(title or "").lower()
    if company == "OCS Optical Circuit Switching":
        if re.search(r"ocp|open compute project", text, re.I) and re.search(r"launch|establish|form", text, re.I) and re.search(r"2025|initial|founding", text, re.I):
            return "ocs|ocp|founding-2025"
    if company == "Huawei OPEN NPO":
        if re.search(r"msa|multi[- ]source agreement|多源协议", text, re.I) and not re.search(
            r"2\.0|revision|升级|修订|update|revised|ratif(?:ied|y)|新版|new version",
            text, re.I
        ) and re.search(r"launch|first|inaugural|发起|启动|首个|initial|initially|publish|releas", text, re.I):
            return "huawei|open-npo|msa-initial-2026-07"
    return None


def source_priority(source: str) -> int:
    source = normalize_text(source)
    source_lower = source.lower()
    for name, priority in SOURCE_PRIORITY.items():
        name_lower = name.lower()
        if source_lower == name_lower or name_lower in source_lower:
            return priority
    if re.search(r"simply wall|futu|stockstory|kucoin|marsbit|huoxing|tradingbeats", source, re.I):
        return 5
    return 50



POWER_COMPANY = "AAOI Taiwan Power-to-Production"
POWER_MONITOR_VERSION = 1
POWER_INITIAL_KEY = "aaoi-taiwan|bloom-leadray|epc-announcement-2026-10-07"
POWER_BASELINE_KEYS = {POWER_INITIAL_KEY}
POWER_SOURCES_OFFICIAL = ("bloomenergy.com", "ao-inc.com", "gcs-web.com")
POWER_TRUSTED_MEDIA = (
    "digitimes.com", "technews.tw", "money-link.com.tw",
    "reccessary.com", "udn.com", "ctee.com.tw",
)


def is_aaoi_power_topic(title: str) -> bool:
    text = html.unescape(title or "")
    aaoi = bool(re.search(
        r"Applied Optoelectronics|\bAAOI\b|\bAOI\b|祥茂光[電电]", text, re.I
    ))
    taiwan = bool(re.search(r"Taiwan|台灣|台湾|祥茂光[電电]", text, re.I))
    power = bool(re.search(
        r"Bloom Energy|賀喜能源|贺喜能源|Leadray|\bSOFC\b|"
        r"fuel cell|燃料[電电]池|on[- ]site power|現地發電|现场发电|"
        r"electricity supply|power supply|power outage|grid connection|"
        r"(?:電力|电力|供電|供电|發電|发电).{0,25}"
        r"(?:擴廠|扩厂|工廠|工厂|產能|产能)", text, re.I
    ))
    return aaoi and taiwan and power


def power_is_plan(title: str) -> bool:
    text = html.unescape(title or "")
    planned = bool(re.search(
        r"expects? to|expected to|plans? to|scheduled to|aims? to|"
        r"set to|on track to|to be (?:installed|completed|commissioned|energized|operational)|"
        r"will (?:install|deploy|start|complete|begin|commission)|"
        r"anticipated|target(?:s|ing)?|預計|预计|計畫|计划|將於|"
        r"将于|擬|拟|規劃|规划|가동 예정|설치 예정|시운전 예정", text, re.I
    ))
    achieved = bool(re.search(
        r"(?:has |have )?(?:completed|commissioned|energized|"
        r"installed and operating|started commercial operation)|"
        r"正式運轉|正式运行|已完成|已投運|"
        r"已投入運轉|驗收完成|验收完成", text, re.I
    ))
    # Do not elevate a future-dated 2027 commissioning headline written in
    # October 2026 to completed generation, even when phrased ambiguously.
    future_year = re.search(r"\b(20\d{2})\b", text)
    future_target = bool(
        future_year and int(future_year.group(1)) > NOW.astimezone(KST).year
        and re.search(r"2027|2028|2029", text)
        and not re.search(r"has commissioned|has entered operation|已投入運轉|正式運轉", text, re.I)
    )
    return (planned or future_target) and not achieved


def power_amount_fingerprint(title: str) -> str:
    text = html.unescape(title or "")
    power = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*(MW|kW|兆瓦|千瓦)\b", text, re.I)
    money = re.search(
        r"(?:US\$|NT\$|\$)\s*(\d+(?:[.,]\d+)?)\s*(million|billion|m|bn)?|"
        r"\d+(?:\.\d+)?\s*(?:億元|亿元|萬元|万元)", text, re.I
    )
    suffix = []
    if power:
        suffix.append((power.group(1) + power.group(2)).lower())
    if money:
        suffix.append(re.sub(r"\s+", "", money.group(0)).lower())
    return "-".join(suffix)


def power_milestone(title: str) -> tuple[str, str, str] | None:
    if not is_aaoi_power_topic(title):
        return None
    text = html.unescape(title or "")
    future = power_is_plan(text)
    fingerprint = power_amount_fingerprint(text)
    if re.search(r"delay|postpon|suspend|cancel|延期|延後|推遲|推迟|停電|停电|燃氣不足|天然氣短缺", text, re.I):
        return ("AAOI 현장발전 일정·공급 위험", "지연·취소·연료 공급 역풍", "aaoi-taiwan|power|delay|" + (fingerprint or "event"))
    if re.search(r"subsidy|grant|補助|补助", text, re.I) and re.search(
        r"approved|granted|awarded|核准|核定|獲准|批准", text, re.I
    ) and not re.search(r"applied|application|申請|申请|待審|待审", text, re.I):
        return ("AAOI 현장발전 보조금", "보조금 실제 승인", "aaoi-taiwan|power|grant|" + (fingerprint or "approved"))
    if not future and re.search(
        r"commissioned|commercial operation|energized|power[- ]on|"
        r"正式運轉|正式运行|投入運轉|投入运行|正式發電|正式发电", text, re.I
    ):
        return ("AAOI 현장발전 전원 인가", "실제 전원 인가·가동", "aaoi-taiwan|power|operating|" + (fingerprint or "start"))
    if not future and re.search(
        r"installed|site acceptance|construction completed|"
        r"安裝完成|安装完成|完工驗收|完工验收|驗收完成|验收完成", text, re.I
    ):
        return ("AAOI SOFC 설치·검수", "실제 설치·검수", "aaoi-taiwan|power|inspection|" + (fingerprint or "completed"))
    if not future and re.search(
        r"construction begins|construction starts|breaks ground|"
        r"delivery of fuel cell|設備到貨|设备到货|正式開工|正式开工", text, re.I
    ):
        return ("AAOI SOFC 착공·장비반입", "실제 착공·반입", "aaoi-taiwan|power|construction|" + (fingerprint or "start"))
    if not future and re.search(
        r"gas supply secured|gas connection completed|grid permit granted|"
        r"gas contract signed|供氣完成|供气完成|併網核准|并网核准", text, re.I
    ):
        return ("AAOI 연료·전력 접속", "가스 공급·접속·허가", "aaoi-taiwan|power|gas-grid|" + (fingerprint or "secured"))
    if not future and re.search(
        r"maintenance agreement|service contract|long[- ]term service|"
        r"remote monitoring contract|O&M agreement|stack replacement|"
        r"維運合約|维运合同|長期維護|长期维护|維修合約|维修合同",
        text, re.I
    ):
        return ("AAOI SOFC 유지보수 계약", "장기 유지보수·교체부품·원격관제 계약", "aaoi-taiwan|power|service|" + (fingerprint or "agreement"))
    if future and fingerprint and re.search(
        r"Bloom Energy|賀喜能源|Leadray|\bSOFC\b|fuel cell|燃料[電电]池", text, re.I
    ):
        return ("AAOI SOFC 계획 용량·금액", "계획 수치 공개·실제 계약 검증 전", "aaoi-taiwan|power|planned-terms|" + fingerprint)
    if not future and fingerprint and re.search(
        r"Bloom Energy|賀喜能源|Leadray|\bSOFC\b|fuel cell|燃料[電电]池", text, re.I
    ):
        return ("AAOI 현장발전 용량·계약금액", "실제 규모 또는 금액 공개", "aaoi-taiwan|power|terms|" + fingerprint)
    if not future and re.search(
        r"800G|1\.6T", text, re.I
    ) and re.search(
        r"customer (?:qualification|approved|certification)|"
        r"volume shipments?|production ramp|volume production|"
        r"客戶認證|客户认证|量產|量产|出貨|出货", text, re.I
    ):
        return ("AAOI 전력 확보→출하 검증", "고객 승인·양산·출하", "aaoi-taiwan|power|optics|" + (fingerprint or "production"))
    if re.search(r"Bloom Energy|Leadray|賀喜能源|贺喜能源|SOFC|fuel cell|燃料[電电]池", text, re.I):
        # The October 2026 EPC announcement is planned for Q1 2027, not energized.
        return ("AAOI 현장발전 EPC 추진", "사업 발표·가동 전", POWER_INITIAL_KEY)
    return None


def retain_historical_optics_record(record: dict) -> bool:
    # A short-lived intermediate deploy incorrectly labeled an unrelated
    # Chunghwa Telecom article as AAOI Taiwan power news. Purge it from both
    # seen hashes and story records; never treat it as verified AAOI evidence.
    return not (
        record.get("company") == POWER_COMPANY
        and power_milestone(str(record.get("title") or "")) is None
    )


def same_power_event(a: dict, b: dict) -> bool:
    if a.get("company") != POWER_COMPANY or b.get("company") != POWER_COMPANY:
        return False
    left = power_milestone(a.get("title") or "")
    right = power_milestone(b.get("title") or "")
    return bool(left and right and left[2] == right[2])


def official_power_source(item: dict) -> bool:
    name = normalize_text(item.get("source") or "").lower()
    addr = normalize_text(item.get("source_url") or "")
    host = urllib.parse.urlparse(addr).hostname or ""
    return bool(
        any(n in name for n in ("bloom energy", "applied optoelectronics", "leadray", "賀喜能源"))
        and any(host == d or host.endswith("." + d) for d in POWER_SOURCES_OFFICIAL)
    )


def verified_power_event(item: dict, all_items: list[dict]) -> bool:
    if item.get("company") != POWER_COMPANY:
        return True
    if official_power_source(item):
        return True
    matching = set()
    for row in all_items:
        if not same_power_event(item, row):
            continue
        if source_priority(row.get("source") or "") < 70:
            continue
        host = urllib.parse.urlparse(row.get("source_url") or "").hostname or ""
        if any(host == d or host.endswith("." + d) for d in POWER_TRUSTED_MEDIA):
            matching.add(host.removeprefix("www."))
    return len(matching) >= 2

def _article_title_identity(title: str) -> str:
    value = html.unescape(title or "").lower()
    # Google News commonly appends " - Source" to the headline.
    value = re.sub(r"\s+-\s+[^-]{2,100}$", " ", value)
    value = re.sub(r"[^a-z0-9.\uac00-\ud7a3\u4e00-\u9fff]+", " ", value)
    return " ".join(value.split())


def same_article_identity(a: dict, b: dict) -> bool:
    # One underlying article can be returned by several thematic queries
    # (e.g. FAU coupling under both packaging/test and equipment). It is one
    # new event, not two. Collapse across synthetic company buckets.
    a_link = normalize_text(a.get("link") or "")
    b_link = normalize_text(b.get("link") or "")
    if a_link and b_link and a_link == b_link:
        return True
    a_title = _article_title_identity(a.get("title") or "")
    b_title = _article_title_identity(b.get("title") or "")
    if not a_title or a_title != b_title:
        return False
    a_source = normalize_text(a.get("source") or "").lower()
    b_source = normalize_text(b.get("source") or "").lower()
    return bool(a_source and a_source == b_source)


def _scope_descriptor(item: dict) -> dict:
    return {
        "company": item.get("company"),
        "ticker": item.get("ticker"),
        "category": item.get("category"),
    }


def merge_article_scopes(current: dict, candidate: dict) -> dict:
    # Keep one alert item while preserving every legitimate interpretation axis.
    chosen = dict(candidate if prefer_story_item(candidate, current) else current)
    scopes: list[dict] = []
    seen_scopes: set[tuple[str, str]] = set()
    for source_item in (current, candidate):
        rows = list(source_item.get("related_scopes") or []) + [_scope_descriptor(source_item)]
        for row in rows:
            company = str(row.get("company") or "")
            category = str(row.get("category") or "")
            key = (company, category)
            if not company or not category or key in seen_scopes:
                continue
            seen_scopes.add(key)
            scopes.append({
                "company": company,
                "ticker": row.get("ticker"),
                "category": category,
            })
    chosen["related_scopes"] = scopes
    return chosen


def same_underlying_story(a: dict, b: dict) -> bool:
    if a.get("company") != b.get("company"):
        return False
    if a.get("company") == POWER_COMPANY:
        return same_power_event(a, b)

    if a.get("company") == "CPO Equipment Supply Chain":
        # Sector articles are often rewritten with different supplier names/headlines.
        # Treat near-same-date stories with the same commercial stage as one event,
        # while keeping orders, capacity, qualification and shipment as separate events.
        if a.get("category") != b.get("category"):
            return False
        try:
            ap = dt.datetime.fromisoformat(a.get("published") or "")
            bp = dt.datetime.fromisoformat(b.get("published") or "")
            if abs((ap - bp).total_seconds()) > 72 * 3600:
                return False
        except Exception:
            pass
        ta = story_tokens(a.get("title", ""))
        tb = story_tokens(b.get("title", ""))
        overlap = len(ta & tb)
        union = len(ta | tb)
        smaller = min(len(ta), len(tb)) if ta and tb else 0
        jaccard = overlap / union if union else 0.0
        containment = overlap / smaller if smaller else 0.0
        shared_anchor = bool(re.search(
            r"chieftek|gmt|toyo|suruga|ficontec|allring|fittech|2027|q2|1\.6t|800g",
            " ".join(sorted(ta & tb)),
            re.I,
        ))
        return (shared_anchor and (jaccard >= 0.20 or containment >= 0.38)) or jaccard >= 0.42

    a_key = canonical_story_key(a.get("company", ""), a.get("title", ""))
    b_key = canonical_story_key(b.get("company", ""), b.get("title", ""))
    if a_key and b_key:
        return a_key == b_key
    if a.get("category") != b.get("category"):
        return False
    ta = story_tokens(a.get("title", ""))
    tb = story_tokens(b.get("title", ""))
    if not ta or not tb:
        return False
    overlap = len(ta & tb)
    union = len(ta | tb)
    smaller = min(len(ta), len(tb))
    jaccard = overlap / union if union else 0.0
    containment = overlap / smaller if smaller else 0.0
    return jaccard >= 0.48 or containment >= 0.72


def prefer_story_item(candidate: dict, current: dict) -> bool:
    c_rank = source_priority(candidate.get("source") or "")
    o_rank = source_priority(current.get("source") or "")
    if c_rank != o_rank:
        return c_rank > o_rank
    if candidate.get("score", 0) != current.get("score", 0):
        return candidate.get("score", 0) > current.get("score", 0)
    return (candidate.get("published") or "") > (current.get("published") or "")


def query_google_news(
    query: str,
    hl: str = "en-US",
    gl: str = "US",
    ceid: str = "US:en",
) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": query,
        "hl": hl,
        "gl": gl,
        "ceid": ceid,
    })
    url = f"https://news.google.com/rss/search?{params}"
    root = ET.fromstring(fetch(url))
    items: list[dict] = []
    for item in root.findall("./channel/item")[:20]:
        title = normalize_text(item.findtext("title") or "")
        link = normalize_text(item.findtext("link") or "")
        pub = parse_date(item.findtext("pubDate"))
        source_node = item.find("source")
        source = normalize_text(source_node.text if source_node is not None and source_node.text else "")
        source_url = normalize_text(source_node.attrib.get("url", "") if source_node is not None else "")
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "published": pub.isoformat() if pub else None,
                "source": source,
                "source_url": source_url,
            })
    return items


def is_noise(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in NOISE_PATTERNS)


def signal_score(title: str, source: str) -> int:
    text = f"{title} {source}"
    if is_noise(text):
        return -10
    score = 0
    if re.search(r"\b3\.2\s*[Tt]\b", text, re.I):
        score += 6
    if re.search(r"\b1\.6\s*[Tt]\b", text, re.I):
        score += 5
    if re.search(r"co[- ]?packaged optics?|\bCPO\b|silicon photonics?", text, re.I):
        score += 5
    if re.search(r"PhotonLink|integrated optics?|complete optical solutions?|end[- ]to[- ]end|vertical integration|one[- ]stop", text, re.I):
        score += 7
    if re.search(r"\bNPO\b|chip[- ]to[- ]chip", text, re.I):
        score += 5
    if re.search(r"optical circuit switch(?:ing)?|\bOCS\b|近封装光学|光电路交换|\bOPEN NPO\b", text, re.I):
        score += 7
    if re.search(r"customer engagements?|long[- ]term agreements?|anchor customers?", text, re.I):
        score += 5
    if re.search(r"content opportunity|content per|100\s*Tbps", text, re.I):
        score += 5
    if re.search(r"specialty fibers?|polarization[- ]maintaining|mode[- ]matching|multicore fibers?", text, re.I):
        score += 4
    if re.search(r"\bInP\b|indium phosphide|InP substrate|\bGaAs\b|gallium arsenide|砷化鎵|\bSiPh\b|photonics foundry|design win", text, re.I):
        score += 4
    if re.search(r"photonic memory|optical memory|memory wall|memory pooling|compute[- ]to[- ]memory|optical fabric|micro[- ]?VCSEL|VCSEL|photonic AI|photonic inference|AI inference system", text, re.I):
        score += 6
    if re.search(r"\bELS\b|\bELSFP\b|external laser source|external light source|high[- ]power CW|ultra[- ]high[- ]power|\bUHP\b", text, re.I):
        score += 5
    if re.search(r"TFLN|thin[- ]film lithium niobate|thin film lithium niobate", text, re.I):
        score += 5
    if re.search(r"blind[- ]mate|insertion loss|hot[- ]swap|field[- ]replaceable", text, re.I):
        score += 4
    if re.search(r"200G/lane|400G/lane|direct attach copper|\bDAC\b|\bACC\b|co[- ]packaged copper", text, re.I):
        score += 4
    if re.search(r"reliability|lifetime|MTBF|failure rate|thermal|laser failure", text, re.I):
        score += 3
    if re.search(r"funding|financing|raises?|series\s+[abc]", text, re.I):
        score += 3
    if re.search(
        r"tokens? per second|tok/s|20\s*trillion|10\s*trillion|240\s*TB/s|>200\s*TB/s|10\s*TB|"
        r"1\s*pJ/bit|sub[- ]?5\s*ns|BER\s*<?\s*1e-12|200\s*mm|220\s*memory\s*(?:chips|chiplets)",
        text,
        re.I,
    ):
        score += 4
    if re.search(r"customer sampling|integrated inference engines?|silicon validation|tape[- ]?out|benchmark|commercialization", text, re.I):
        score += 5
    if re.search(r"6[- ]inch InP|capacity reservation|prepayment|deposit|long[- ]term supply|crystal growth|pilot production|wafer substrate", text, re.I):
        score += 5
    if re.search(r"\bFCC\b|Federal Communications Commission|Covered List|equipment authorization", text, re.I):
        score += 7
    if re.search(r"Chinese[- ]made|China[- ]based|domestic content|domestic end product|Buy American|\b65\s*%\b|\b75\s*%\b|Inn[o]?light|Eoptolink", text, re.I):
        score += 4
    if re.search(r"final rule|proposed rule|rulemaking|restrict(?:ion|ions)?|ban|prohibit|legislation|national security systems?", text, re.I):
        score += 5
    if re.search(r"export licen[cs]e", text, re.I):
        score += 5
    if re.search(r"optical coupling|active alignment|alignment modules?|aligners?|motion platforms?|linear motors?|6[- ]axis|nanometer|50\s*nm|\bFAU\b", text, re.I):
        score += 5
    if re.search(r"\bOSAT\b|qualification|validation|verification", text, re.I):
        score += 4
    if re.search(r"order visibility|delivery visibility|backlog|ahead[- ]of[- ]time orders?", text, re.I):
        score += 5
    if re.search(r"production capacity|\bCAPA\b|new lines?|assembly lines?|factory expansion|capacity doubles?|utilization", text, re.I):
        score += 4
    if re.search(r"訂單|能見度|出貨|量產|擴產|產能|產能利用率", text):
        score += 5
    if re.search(r"光耦合|對位|線性馬達|六軸|驗證|認證|導入", text):
        score += 4
    if re.search(r"mass production|volume production|customer qualification|customer certification|qualified|certified", text, re.I):
        score += 5
    if re.search(r"adopt|deploy|ramp|shipment", text, re.I):
        score += 4
    if re.search(r"backlog|bookings?|orders?|guidance|revenue", text, re.I):
        score += 4
    if re.search(r"shortage|constraint|bottleneck|supply tight|price increase|pricing", text, re.I):
        score += 4
    if re.search(r"capacity expansion|factory|plant|capex", text, re.I):
        score += 3
    if re.search(r"copper|optical|fiber|fibre|transceiver|laser|data movement|interconnect|fabric|retimer|PCIe|CXL", text, re.I):
        score += 2
    if re.search(r"광트랜시버|광통신|AI 데이터센터", text, re.I):
        score += 3
    if re.search(r"공급계약|단일판매|수주|발주서|\bPO\b", text, re.I):
        score += 5
    if re.search(r"검수|납품|계약기간|정정", text, re.I):
        score += 4
    if re.search(r"샘플|samples?|sampling|고객.{0,20}(검증|평가|인증)|검증|인증|양산|출하|증설|생산능력", text, re.I):
        score += 4
    if re.search(r"AI|data ?center|datacenter|hyperscaler|GPU|XPU", text, re.I):
        score += 2
    if any(source.lower() == trusted.lower() for trusted in TRUSTED_SOURCES):
        score += 2
    return score


def stage_for(title: str) -> str:
    if re.search(r"reliability|lifetime|MTBF|failure rate|thermal|laser failure", title, re.I):
        return "신뢰성·열검증"
    if re.search(r"blind[- ]mate|insertion loss|hot[- ]swap|field[- ]replaceable|OIF[- ]ELSFP", title, re.I):
        return "광결합·커넥터 검증"
    if re.search(r"funding|financing|raises?|series\s+[abc]|strategic investment", title, re.I):
        return "투자·개발자금"
    if re.search(r"customer delivery|customer deployment|integrated inference engines?", title, re.I):
        return "고객 샘플·배치"
    if re.search(r"silicon validation|silicon demonstrates?|tape[- ]?out|benchmark|measured|prototype", title, re.I):
        return "실리콘·성능 검증"
    if re.search(r"commercialization|mass production|volume production|production ramp", title, re.I):
        return "상용화·양산"
    if re.search(r"final rule|finaliz(?:e|es|ed|ing)|adopt(?:s|ed)?|effective|takes? effect|signed|enacted", title, re.I):
        return "최종 규칙·시행"
    if re.search(r"proposed rule|rulemaking|notice|comment period|draft rule|considering", title, re.I):
        return "규칙 제안·검토"
    if re.search(r"senate|congress|introduc(?:es|ed)? bill|legislation", title, re.I):
        return "법안 발의·입법"
    if re.search(r"export licen[cs]e|export restriction", title, re.I):
        return "수출허가·공급망 규제"
    if re.search(r"계약기간.{0,20}(변경|연장)|검수.{0,20}(지연|조정|변경)|납품.{0,20}(지연|조정|변경)|정정", title, re.I):
        return "납기·검수 변경"
    if re.search(r"공급계약|단일판매|수주|발주서|\bPO\b", title, re.I):
        return "수주·가시성"
    if re.search(r"샘플|samples?|sampling|고객.{0,20}(검증|평가|인증)|검증|인증", title, re.I):
        return "고객 검증·양산 도입"
    if re.search(r"양산|출하", title, re.I):
        return "양산·출하"
    if re.search(r"증설|생산능력", title, re.I):
        return "설비투자"
    if re.search(r"驗證|認證|導入|\bOSAT\b|qualification|validation|verification|passes?.{0,40}certification", title, re.I):
        return "고객 검증·양산 도입"
    if re.search(r"訂單|能見度|order visibility|delivery visibility|backlog|orders?|bookings?", title, re.I):
        return "수주·가시성"
    if re.search(r"擴產|產能|產能利用率|new line|factory|capacity|CAPA|utilization", title, re.I):
        return "설비투자"
    if re.search(r"出貨|量產|mass production|volume production|shipment|ramp", title, re.I):
        return "양산·출하"
    if re.search(r"\bOSAT\b|qualification|validation|verification|passes?.{0,40}certification", title, re.I):
        return "고객 검증·양산 도입"
    if re.search(r"order visibility|delivery visibility|backlog|orders?|bookings?", title, re.I):
        return "수주·가시성"
    if re.search(r"long[- ]term(?:\s+\w+){0,6}\s+agreement|anchor customer|secures?.{0,60}agreement", title, re.I):
        return "장기계약·고객 확정"
    if re.search(r"customer engagements?|design win|qualified|certified|adopt|deploy", title, re.I):
        return "고객 검증·채택"
    if re.search(r"revenue|guidance|backlog|bookings?|orders?", title, re.I):
        return "실적·수주 확인"
    if re.search(r"mass production|volume production|shipment|ramp", title, re.I):
        return "양산·출하"
    if re.search(r"qualified|certified|customer qualification|customer certification|adopt|deploy", title, re.I):
        return "고객 검증·채택"
    if re.search(r"shortage|constraint|bottleneck|supply tight|pricing|price increase", title, re.I):
        return "공급 병목·가격"
    if re.search(r"capacity expansion|factory|plant|capex", title, re.I):
        return "설비투자"
    return "기술·제품 준비"


def category_for(title: str, company: str) -> str:
    if company == POWER_COMPANY:
        milestone = power_milestone(title)
        return milestone[0] if milestone else "AAOI 현장발전 EPC 추진"
    structural = classify_structural_axis(company, title)
    if structural is not None:
        return structural
    if company == "Volantis":
        if re.search(r"funding|financing|raises?|series\s+[abc]", title, re.I):
            return "광메모리 투자·개발자금"
        if re.search(r"customer sampling|customer delivery|customer deployment|integrated inference engines?", title, re.I):
            return "광메모리 고객검증·상용화"
        if re.search(
            r"silicon|tape[- ]?out|benchmark|measured|prototype|240\s*TB/s|>200\s*TB/s|10\s*TB|"
            r"1\s*pJ/bit|sub[- ]?5\s*ns|BER\s*<?\s*1e-12|200\s*mm|220\s*memory\s*chiplets?|"
            r"tokens? per second|tok/s",
            title,
            re.I,
        ):
            return "광메모리 성능·검증"
        if re.search(r"VCSEL|micro[- ]?VCSEL|supply chain|foundry|wafer|laser", title, re.I):
            return "VCSEL 광메모리 공급망"
        return "광메모리·추론 아키텍처"
    if company in {"Lightmatter", "Ayar Labs", "Xscape Photonics"}:
        if re.search(r"funding|financing|raises?|series\s+[abc]|strategic investment", title, re.I) and re.search(r"production|manufacturing|capacity|deployment|commercial", title, re.I):
            return "광컴퓨팅 투자·양산확대"
        if re.search(r"customer|deployment|production|shipment|sampling|qualification|validation", title, re.I):
            return "광컴퓨팅 상용화·고객검증"
        return "광컴퓨팅·스케일업 인터커넥트"
    if company == "Marvell" and re.search(r"Celestial AI|Photonic Fabric", title, re.I):
        if re.search(r"completed? (?:the )?acquisition|acquisition (?:is )?complete|closes? (?:the )?acquisition|acquires? Celestial", title, re.I):
            return "Photonic Fabric 인수·통합"
        if re.search(r"revenue|run[- ]rate|guidance|fiscal 2028|FY28|fiscal 2029|FY29", title, re.I):
            return "Photonic Fabric 매출 램프"
        if re.search(r"production|shipment|mass production|volume production", title, re.I):
            return "Photonic Fabric 양산·출하"
        if re.search(r"customer|design win|qualification|validation|milestone", title, re.I):
            return "Photonic Fabric 고객검증·수주"
        return "Photonic Fabric 광스케일업"
    if company == "US Optical Policy":
        if re.search(r"senate|congress|bill|legislation|national security systems?", title, re.I):
            return "미국 광트랜시버 규제·법안"
        return "FCC 광트랜시버 규제"
    if company in {"AXT", "InP Supply Chain"} and re.search(r"capacity reservation|prepayment|deposit|long[- ]term supply|agreement", title, re.I):
        return "InP 기판 장기계약·생산능력"
    if company in {"AXT", "InP Supply Chain"} and re.search(r"export licen[cs]e|export restriction", title, re.I):
        return "InP 수출허가·공급망"
    if company in {"AXT", "InP Supply Chain"} and re.search(r"\bInP\b|indium phosphide|substrate|6[- ]inch", title, re.I):
        return "InP 기판 병목"
    if company == "GaAs Optical Supply Chain":
        return "GaAs 광통신 기판·파운드리"
    if company == "Fabrinet":
        if re.search(r"1\.6\s*T|1\.6T", title, re.I) and re.search(r"production|shipment|ramp|customer|order|revenue|guidance", title, re.I):
            return "1.6T 광모듈 제조·패키징 램프"
        if re.search(r"optical packaging|advanced optical|packaging|data center|datacom", title, re.I):
            return "광모듈 제조·패키징"
        return "광통신 제조"
    if company == "CPO Packaging & Test":
        package_substrate = bool(re.search(
            r"package substrate|packaging substrate|packaged substrate|substrate[- ]level multi[- ]chip|"
            r"glass substrate|glass interposer|ABF substrate|organic substrate|interposer",
            title,
            re.I,
        ))
        if package_substrate and re.search(
            r"customer|design win|qualification|qualified|production|mass production|volume production|"
            r"shipment|order|capacity|ramp|commercial",
            title,
            re.I,
        ):
            return "CPO 광패키징 기판·양산"
        if package_substrate and re.search(
            r"yield|warpage|thermal|heat|insertion loss|low[- ]loss|low\s*D[fk]|"
            r"coefficient of thermal expansion|\bCTE\b|reliability|bottleneck|constraint",
            title,
            re.I,
        ):
            return "CPO 광패키징 기판·수율·열검증"
        if package_substrate:
            return "CPO 광패키징 기판·인터포저"
        if re.search(r"COUPE|advanced packaging|2\.5D|3D packaging", title, re.I):
            return "CPO 첨단패키징·COUPE"
        if re.search(r"testing throughput|electro[- ]optical test|burn[- ]?in|high[- ]power module socket|test standard|testing standard", title, re.I):
            return "CPO 검사·신뢰성 병목"
        if re.search(r"optical engine|fiber attach|\bFAU\b|coupling|yield", title, re.I):
            return "CPO 광엔진 수율·광결합"
        return "CPO 패키징·검사"
    if company == "Opticore":
        if re.search(r"계약기간|검수|납품.{0,20}(지연|조정)|정정", title, re.I):
            return "국내 AI 광트랜시버 납기·검수"
        if re.search(r"공급계약|단일판매|수주|발주서|\bPO\b|400G|800G", title, re.I):
            return "국내 AI 광트랜시버 수주"
        return "국내 AI 광트랜시버"
    if company == "OE Solutions":
        if re.search(r"1\.6\s*T|ELSFP|EML", title, re.I) and re.search(r"샘플|samples?|sampling|검증|qualification|certification|고객", title, re.I):
            return "국내 1.6T 고객검증·샘플"
        if re.search(r"수주|공급|order|shipment|양산|출하", title, re.I):
            return "국내 광통신 수주·양산"
        return "국내 광통신"
    if company == "Sungho Electronics / ADST":
        if re.search(r"수주|발주|\bPO\b|공급계약|order|contract", title, re.I):
            return "ADST CPO 정렬·검사 수주"
        if re.search(r"검수|납품|shipment|양산|production|ramp", title, re.I):
            return "ADST CPO 정렬·검사 양산"
        if re.search(r"active alignment|lens alignment|fiber array alignment|광정렬|얼라인먼트|검사", title, re.I):
            return "ADST CPO 정밀정렬·검사"
        return "ADST CPO 장비"
    if company == "POET Technologies":
        if re.search(r"ELS|external (?:laser|light) source|Sivers", title, re.I):
            if re.search(r"customer|sampling|qualification|production|shipment|order|contract|design win", title, re.I):
                return "POET ELS 상용화·고객검증"
            return "POET ELS·하이브리드집적"
        if re.search(r"production|shipment|order|customer|qualification|sampling", title, re.I):
            return "POET 광엔진 상용화"
        return "POET 광엔진·하이브리드집적"
    if company == "TFLN Supply Chain":
        if re.search(r"400G/lane|400G per lane", title, re.I):
            return "TFLN 400G/lane"
        if re.search(r"customer|sampling|qualification|production|shipment|foundry|order|design win", title, re.I):
            return "TFLN 고객검증·양산"
        return "TFLN 광변조기"
    if company == "ELS Connector Supply Chain":
        if re.search(r"blind[- ]mate|blind mate|connector|ferrule|insertion loss", title, re.I):
            return "ELSFP 블라인드메이트·광결합"
        if re.search(r"reliability|lifetime|thermal|failure|hot[- ]swap|field[- ]replaceable", title, re.I):
            return "ELSFP 신뢰성·서비스성"
        return "ELSFP 연결부품"
    if company in {"Lumentum", "Coherent"} and re.search(r"\bELS\b|\bELSFP\b|external (?:laser|light) source|high[- ]power CW|ultra[- ]high[- ]power|\bUHP\b|350mW|400mW", title, re.I):
        if re.search(r"customer|sampling|qualification|production|shipment|order|agreement|anchor", title, re.I):
            return "ELS 외장광원·양산"
        if re.search(r"reliability|lifetime|thermal|failure|hot[- ]swap|field[- ]replaceable", title, re.I):
            return "ELS 외장광원 신뢰성"
        return "ELS 외장광원"
    if company == "Marvell" and re.search(r"200G/lane|200G per lane|direct attach copper|\bDAC\b|\bACC\b|active copper cable|co[- ]packaged copper", title, re.I):
        if re.search(r"2(?:\.0|\.5)?[- ]?meter|2(?:\.0|\.5)?[- ]?metre|reach|extend|redriver|co[- ]packaged copper|\bACC\b", title, re.I):
            return "200G/lane 구리 연장기술"
        return "200G/lane 구리 도달거리"
    if company == "Marvell" and re.search(r"400G/lane|400G per lane", title, re.I) and re.search(r"copper|DAC|ACC|optical|CPO|NPO", title, re.I):
        return "400G/lane 구리 한계"
    if company == "CPO Equipment Supply Chain":
        if re.search(r"驗證|認證|導入|\bOSAT\b|qualification|validation|verification|certif", title, re.I):
            return "CPO 장비 고객검증·도입"
        if re.search(r"擴產|產能|產能利用率|production capacity|\bCAPA\b|factory|new lines?|assembly lines?|expand|acquisition|utilization|capacity doubles?", title, re.I):
            return "CPO 장비 증설·가동률"
        if re.search(r"出貨|量產|shipments?|mass production|volume production|ramp", title, re.I):
            return "CPO 장비 출하·양산"
        if re.search(r"訂單|能見度|order visibility|delivery visibility|backlog|orders?|bookings?|ahead[- ]of[- ]time orders?", title, re.I):
            return "CPO 장비 수주·가시성"
        return "CPO 정밀정렬·광결합 장비"
    if company == "Coherent" and re.search(r"PhotonLink|integrated optics?|complete optical solutions?|end[- ]to[- ]end|vertical integration|one[- ]stop", title, re.I):
        return "광 링크 통합·수직계열화"
    if re.search(r"customer engagements?|long[- ]term(?:\s+\w+){0,6}\s+agreements?|anchor customers?|secures?.{0,60}agreements?", title, re.I):
        return "고객·장기계약"
    if re.search(r"content opportunity|content per|100\s*Tbps", title, re.I):
        return "광학 콘텐츠 가치"
    if re.search(r"chip[- ]to[- ]chip", title, re.I):
        return "칩 간 광연결"
    if re.search(r"specialty fibers?|polarization[- ]maintaining|mode[- ]matching|multicore fibers?", title, re.I):
        return "특수광섬유"
    if company == "Samsung Electronics" and re.search(r"silicon photonics|\bSiPh\b|PIC|photonics foundry|optical module|optical engine|design win", title, re.I):
        return "SiPh 파운드리"
    if re.search(r"\b3\.2\s*[Tt]\b", title, re.I):
        return "3.2T 전환"
    if re.search(r"co[- ]?packaged optics?|\bCPO\b|silicon photonics?", title, re.I):
        return "CPO·실리콘 포토닉스"
    if re.search(r"\b1\.6\s*[Tt]\b", title, re.I):
        return "1.6T 전환"
    if re.search(r"shortage|constraint|bottleneck|supply tight|pricing|price increase", title, re.I):
        return "공급 병목·가격"
    if re.search(r"backlog|bookings?|orders?|guidance|revenue", title, re.I):
        return "수주·실적"
    if company == "Corning" and re.search(r"glass substrate|advanced packaging", title, re.I):
        return "유리기판·첨단 패키징"
    if re.search(r"fiber|fibre|optical|transceiver|laser", title, re.I):
        return "광통신"
    if re.search(r"PCIe|CXL|retimer|fabric|interconnect", title, re.I):
        return "랙 내부 인터커넥트"
    return "AI 네트워킹"


def meaning_for(category: str) -> str:
    mapping = {
        "AAOI 현장발전 EPC 추진": "Leadray Energy가 설계·조달·시공을 맡고 Bloom Energy의 SOFC로 대만 광통신 공장 전력을 보강할 예정입니다. 2027년 1분기는 운전 목표이며 현재 전원 인가·발전용량·계약금액은 공개되지 않았습니다.",
        "AAOI 현장발전 용량·계약금액": "실제 발전용량(MW)과 공급계약 금액이 공개되면 설치비·단위 출력 및 증설 대응 정도를 검산할 수 있습니다. 미공개 수치를 다른 프로젝트에서 차용하지 않습니다.",
        "AAOI SOFC 계획 용량·금액": "새로 공개된 용량·금액 목표는 확정 납품·설비투자가 아닙니다. 공급계약·허가·실제 설치규모와 분리해 추적합니다.",
        "AAOI SOFC 착공·장비반입": "연료전지 설비반입과 실제 착공은 발표 단계보다 진전됐지만 시운전·계통접속·안전 승인·전원 인가가 남아 있습니다.",
        "AAOI SOFC 설치·검수": "설비 설치·검수는 전원 인가 전 마지막 주요 관문입니다. 검사와 안전 승인이 끝났는지 별도로 확인합니다.",
        "AAOI 현장발전 전원 인가": "실제 상업운전이 확인되면 전력 공급 위험은 줄지만 AAOI 대만 공장의 고객인증·수율·800G/1.6T 출하는 별도 확인해야 합니다.",
        "AAOI 연료·전력 접속": "대만 현장 가스 공급·전력 접속과 현지 허가가 확보되면 발전설비 가동 지연 위험이 낮아집니다.",
        "AAOI 현장발전 보조금": "보조금 신청과 실제 승인·금액 지급은 구분해야 합니다. 확정 금액과 수혜 당사자만 사업비 계산에 반영합니다.",
        "AAOI SOFC 유지보수 계약": "전력설비 인도 이후 장기 유지보수 계약·스택 교체·원격관제는 Bloom 및 서비스 당사자의 반복매출 경로입니다. 최초 장비 공급계약과 분리합니다.",
        "AAOI 전력 확보→출하 검증": "전력 설비 가동 이후 고객별 800G·1.6T 생산 인증, 양품 수율, 실제 출하량과 매출 증가가 연결돼야 설비투자 효과가 입증됩니다.",
        "AAOI 현장발전 일정·공급 위험": "가스 계약·허가·설치·검수·2027년 1분기 전원 인가 일정의 지연은 대만 광통신 생산능력 증설의 선행 위험입니다.",
        "OCS 고객·주문·배치": "OCS는 광경로 자체를 바꾸는 별도 스위치입니다. NVIDIA의 OCP 참여·CPO 제품 판매를 OCS 구매로 오인하지 않고 실제 OCS 장비 계약·고객·배치 대수를 확인합니다.",
        "OCS 표준·상호운용성": "OCP의 광회로 스위칭 개방형 제어 인터페이스·상호운용성이 개선되면 신규 고객군의 장비 검증 비용을 낮출 수 있습니다. 표준 참여는 양산수주와 다릅니다.",
        "NPO 표준 제·개정": "화웨이 OPEN NPO의 다중공급자 규격 개정·호환성 인증은 NPO 공급망 진입조건을 바꿀 수 있습니다. MSA 발표만으로 고객 양산 물량이 생기지는 않습니다.",
        "NPO 공급사·생태계 확대": "OPEN NPO에 새 실공급사가 공식 편입되면 NPO 광엔진·모듈·연결부품의 후보군이 확대되지만 직접 납품은 별도 검증해야 합니다.",
        "NPO 고객·양산·계약": "화웨이 NPO 광연결이 확정 고객 주문·출하·양산으로 전환되는 경우에만 실제 장비·부품 매출 실현 신호입니다.",
        "광메모리 투자·개발자금": "대규모 자금조달은 광메모리 아키텍처의 개발·인력·테이프아웃·고객 샘플 비용을 감당할 수 있게 하지만, 그 자체가 성능 검증이나 양산 수주를 의미하지는 않습니다.",
        "광메모리·추론 아키텍처": "광학을 랙 간 네트워크가 아니라 가속기와 메모리 사이까지 끌어오면 HBM 용량·대역폭의 물리적 한계를 우회할 수 있어 추론 시스템 구조 자체를 바꾸는 신호입니다.",
        "광메모리 고객검증·상용화": "설계 목표를 넘어 실제 고객 샘플·통합 추론엔진·배치 일정이 확인되면 광메모리 아키텍처가 연구단계에서 매출 가능 단계로 넘어가는 핵심 검증 신호입니다.",
        "광메모리 성능·검증": "토큰 처리량·메모리 대역폭·용량·비트당 에너지가 실제 실리콘 또는 독립 벤치마크로 확인되면 광메모리의 경제성이 검증되는 신호입니다.",
        "VCSEL 광메모리 공급망": "볼란티스처럼 InP 외부레이저 대신 GaAs 기반 micro-VCSEL을 쓰는 구조가 양산되면 VCSEL 에피·레이저·패키징 공급망에 새로운 AI 매출 경로가 열릴 수 있습니다.",
        "광컴퓨팅 투자·양산확대": "자금조달이 고용 확대가 아니라 실제 고용량 생산·테스트·패키징·고객 배치 능력 확장에 쓰이면 광인터커넥트가 연구개발에서 양산 인프라 단계로 이동하는 신호입니다.",
        "광컴퓨팅 상용화·고객검증": "라이트매터·아야르 랩스·엑스케이프 등에서 샘플링·고객검증·생산·배치가 확인되면 광인터커넥트가 기술 시연에서 실제 AI 시스템 매출로 이동하는 신호입니다.",
        "Photonic Fabric 매출 램프": "마벨이 Celestial AI의 Photonic Fabric에서 실제 매출 개시·연환산 매출 가이던스를 확인하거나 상향하면 비상장 광인터커넥트 기술이 상장사 데이터센터 매출로 전환되는 직접 검증 신호입니다.",
        "Photonic Fabric 고객검증·수주": "고객 실명·설계 채택·검증 통과가 확인되면 기존 인수 발표와 매출 가이던스 사이의 실질적인 고객 관문을 통과했다는 신호입니다.",
        "Photonic Fabric 양산·출하": "Photonic Fabric의 생산·출하가 실제로 시작되면 인수 당시의 기술·매출 목표가 물량으로 전환되는 단계 변화입니다.",
        "Photonic Fabric 인수·통합": "Celestial AI 인수 완료 자체는 매출 발생이 아니라 Marvell 데이터센터 사업 안으로 기술·인력·개발비가 편입된 사건으로 분리해 봅니다.",
        "Photonic Fabric 광스케일업": "Celestial AI의 광 I/O를 패키지·시스템·랙까지 확장하는 구조는 전기식 스케일업 인터커넥트의 전력·거리 한계를 낮추는 마벨의 중장기 광연결 축입니다.",
        "광컴퓨팅·스케일업 인터커넥트": "GPU·XPU·메모리 사이 데이터 이동 병목을 광링크로 줄이는 구조가 확산되면 AI 인프라 가치가 연산칩에서 광엔진·레이저·패키징까지 넓어지는 신호입니다.",
        "FCC 광트랜시버 규제": "완제품 국적보다 부품 원산지·가치비중까지 규제가 내려오면 3.2T 세대의 공급사 선정과 레이저·InP·DSP 가치배분이 직접 바뀌는 정책 신호입니다.",
        "미국 광트랜시버 규제·법안": "FCC 상업시장 규제와 연방 국가안보시스템 조달 제한은 범위가 다르므로, 법안 통과·적용대상 확대 여부가 중국 광모듈의 실제 미국 매출 접근성을 바꾸는 신호입니다.",
        "InP 기판 병목": "InP 기판 수급·수출허가·증설은 EML·CW 레이저와 1.6T·3.2T 광모듈 출하량의 상류 한계를 결정해 LITE·COHR·AXTI의 물량·가격·가동률에 직접 연결됩니다.",
        "InP 기판 장기계약·생산능력": "Coherent·Lumentum 같은 광부품사가 6인치 InP 생산능력을 선지급·예약하면 1.6T·3.2T·CPO용 레이저 기판 수요가 단순 전망에서 실제 장기 발주로 넘어갔다는 강한 검증 신호입니다.",
        "InP 수출허가·공급망": "InP 수출허가·원산지·납기 변화는 광레이저와 1.6T·3.2T 광모듈의 실제 출하량을 좌우하는 상류 공급망 신호입니다.",
        "GaAs 광통신 기판·파운드리": "1.6T·CPO 전환으로 GaAs 기반 광소자·포토다이오드·레이저·파운드리 수요가 늘면 InP 병목을 보완하는 단거리 광링크와 광통신 소재 공급망의 별도 매출축이 커지는 신호입니다.",
        "1.6T 광모듈 제조·패키징 램프": "1.6T 광모듈의 고객 주문·출하·생산 램프가 파브리넷 같은 고정밀 광학 제조·패키징 업체의 데이터센터 매출로 실제 전환되는 신호입니다.",
        "광모듈 제조·패키징": "고속 광모듈 수요가 부품 단계에서 조립·정렬·검사·패키징 물량으로 내려오는지를 확인하는 제조 실행 신호입니다.",
        "광통신 제조": "광통신 수요가 실제 제조 물량·가동률·매출로 이어지는지를 확인합니다.",
        "CPO 광패키징 기판·양산": "CPO·SiPh의 광엔진과 전기 칩이 동일 패키지 안에서 양산 단계로 내려오면 패키지 기판·인터포저·광결합 구조가 실제 생산물량과 매출로 연결되는 직접 신호입니다.",
        "CPO 광패키징 기판·수율·열검증": "고집적 CPO 패키지의 휨·열팽창계수·삽입손실·저손실 특성·수율 검증은 광엔진과 ASIC을 같은 패키지에서 대량생산할 수 있는지를 좌우하는 핵심 병목입니다.",
        "CPO 광패키징 기판·인터포저": "CPO는 광학과 실리콘을 하나의 패키지 기판·인터포저 계층에서 통합하므로, 고밀도 배선·저손실·열안정성이 확보될수록 광연결의 전력·거리 병목을 줄일 수 있습니다.",
        "CPO 첨단패키징·COUPE": "CPO는 광엔진과 SiPh 칩을 정밀 패키징해야 하며, COUPE 같은 첨단패키징 생산능력·수율이 CPO 양산 속도를 직접 제한할 수 있습니다.",
        "CPO 검사·신뢰성 병목": "CPO 양산에서는 단순 광정렬보다 검사 처리량·번인·고출력 모듈 소켓·신뢰성 표준이 원가와 출하 속도를 좌우하는 병목으로 이동하고 있습니다.",
        "CPO 광엔진 수율·광결합": "광엔진 수율과 FAU·광섬유 결합 손실은 양품률과 테스트 시간을 동시에 좌우하므로 고객 양산 물량의 핵심 선행지표입니다.",
        "CPO 패키징·검사": "CPO가 시제품에서 양산으로 넘어갈수록 패키징·검사·광결합의 처리량과 수율이 실제 출하량을 결정합니다.",
        "국내 AI 광트랜시버 수주": "옵티코어의 400G·800G AI 데이터센터 광트랜시버가 실제 PO·공급계약으로 확인되면 국내 광통신 테마가 아니라 현재 매출로 연결되는 직접 신호입니다.",
        "국내 AI 광트랜시버 납기·검수": "납품·검수 일정 변경은 수주금액 자체보다 매출 인식 시점을 바꾸므로 계약기간 연장·검수 완료 여부를 별도 추적해야 합니다.",
        "국내 AI 광트랜시버": "국내 AI 데이터센터용 400G·800G 광트랜시버의 고객·수주·양산 연결을 확인하는 신호입니다.",
        "국내 1.6T 고객검증·샘플": "오이솔루션의 ELSFP·EML 샘플이 고객 검증을 거쳐 양산 채택되면 1.6T AI 네트워킹 매출이 개발 단계에서 실제 주문 단계로 넘어가는 신호입니다.",
        "국내 광통신 수주·양산": "국내 광통신 신제품이 실제 수주·출하·양산으로 전환되는지 확인하는 매출 검증 신호입니다.",
        "국내 광통신": "국내 광통신 업체의 800G·1.6T 제품 개발이 고객 검증·주문으로 연결되는지 확인하는 신호입니다.",
        "ADST CPO 정렬·검사 수주": "성호전자의 CPO 연결은 필름 기판이 아니라 자회사 ADST의 광섬유·렌즈 정렬, 검사·조립 장비 수주입니다. 신규 PO·계약금액·고객·납기가 실제 매출로 연결되는지를 확인하는 직접 신호입니다.",
        "ADST CPO 정렬·검사 양산": "ADST 장비가 검수·납품을 넘어 고객 양산라인에서 반복 투입되면 CPO 기대가 실제 장비 매출과 서비스 수요로 전환되는 신호입니다.",
        "ADST CPO 정밀정렬·검사": "CPO는 광엔진·FAU·렌즈·광섬유의 결합 손실과 정렬 오차가 수율을 좌우하므로 나노미터급 정렬·검사 장비의 채택이 핵심 양산 관문입니다.",
        "ADST CPO 장비": "성호전자 자회사 ADST의 CPO 장비 사업이 신규 고객·수주·검수·양산으로 확장되는지를 추적합니다.",
        "POET ELS 상용화·고객검증": "POET Optical Interposer와 외장광원 조합이 샘플·검증·주문·양산으로 넘어가면 하이브리드 집적 기술이 실제 CPO 매출로 전환되는 신호입니다.",
        "POET ELS·하이브리드집적": "POET의 Optical Interposer와 외장광원 결합은 레이저·광소자·전자소자를 칩 스케일에서 통합하는 CPO 경로이지만 고객·양산 확인 전에는 기술·협력 단계입니다.",
        "POET 광엔진 상용화": "POET 광엔진의 고객 샘플·주문·출하가 확인되면 하이브리드 집적 플랫폼이 개발 단계에서 반복 가능한 제품 매출로 이동하는 신호입니다.",
        "POET 광엔진·하이브리드집적": "POET의 수동 정렬 기반 Optical Interposer는 CPO·플러거블 광엔진의 조립 복잡도와 비용을 낮출 수 있는 제조 경로입니다.",
        "TFLN 400G/lane": "400G/lane TFLN 변조기가 실험실 성능을 넘어 고객 검증·생산으로 이동하면 3.2T 이상 광링크의 전력·대역폭 병목을 완화하는 차세대 경로가 됩니다.",
        "TFLN 고객검증·양산": "TFLN은 CPO의 필수 단일 해법이 아니라 SiPh·InP와 경쟁·보완하는 변조기 경로입니다. 고객 검증·파운드리·대량생산이 확인돼야 실제 매출 단계로 봅니다.",
        "TFLN 광변조기": "박막 리튬니오베이트는 높은 변조 대역폭과 낮은 구동전압을 노리는 차세대 광변조기 경로지만 현재 CPO 전체를 대체하는 확정 표준은 아닙니다.",
        "ELSFP 블라인드메이트·광결합": "ELSFP의 블라인드메이트 커넥터는 외장 레이저를 현장 교체 가능하게 하면서 낮은 삽입손실과 정밀 정렬을 확보해야 하므로 CPO 서비스성·광결합 수율의 핵심 연결부품입니다.",
        "ELSFP 신뢰성·서비스성": "외장 레이저를 고열 ASIC 패키지 밖으로 이동하고 현장 교체 가능하게 만드는 것이 ELSFP의 핵심 목적이므로 수명·열·교체성 검증은 CPO 가동률과 유지보수 비용을 좌우합니다.",
        "ELSFP 연결부품": "ELSFP 표준 연결부품의 고객 채택·양산은 외장광원이 개별 데모에서 멀티벤더 생태계로 넘어가는 신호입니다.",
        "ELS 외장광원·양산": "Coherent·Lumentum 등의 고출력 InP CW 외장광원이 고객 샘플·장기계약·양산으로 넘어가면 CPO의 열·서비스성 병목을 해결하는 직접 매출 신호입니다.",
        "ELS 외장광원 신뢰성": "외장광원의 핵심은 레이저를 고열 패키지에서 분리해 열부하와 고장 교체 위험을 낮추는 것입니다. 수명·온도별 출력·현장교체 검증이 실제 채택을 좌우합니다.",
        "ELS 외장광원": "CPO 외장광원은 SiPh 광엔진에 고출력 CW 빛을 공급하며 레이저를 ASIC 패키지 밖으로 분리해 열관리와 서비스성을 개선하는 구조입니다.",
        "200G/lane 구리 연장기술": "200G/lane에서 수동 DAC 도달거리가 약 1m 수준으로 짧아지는 반면 ACC·리드라이버·co-packaged copper가 2m 이상 구간을 연장하면 CPO 전환 시점을 일부 늦출 수 있습니다.",
        "200G/lane 구리 도달거리": "200G/lane 수동 구리는 약 1m 수준의 도달거리 제약이 생겨 단일 랙을 넘는 scale-up에서 광연결 필요성이 커지는 구조적 병목입니다.",
        "400G/lane 구리 한계": "400G/lane으로 올라가면 구리 도달거리·손실·전력 한계가 더 악화돼 NPO/CPO 같은 광연결 전환 압력이 커지는 장기 촉발 요인입니다.",
        "3.2T 전환": "차세대 광링크가 시제품에서 고객 검증·양산으로 넘어가면 광 DSP·레이저·모듈의 다음 매출 사이클 선행신호입니다.",
        "CPO·실리콘 포토닉스": "스위치와 광학을 더 가깝게 결합해 전력·대역폭 병목을 줄이는 구조 변화로, 기존 플러거블 광모듈의 가치 배분까지 바꿀 수 있습니다.",
        "1.6T 전환": "800G에서 1.6T로 실제 출하가 이동하는 신호로, 광 DSP·레이저·고밀도 연결부품의 현재 매출 증가와 직접 연결됩니다.",
        "공급 병목·가격": "수요가 공급능력을 앞서는지 확인하는 신호입니다. 평균판매단가에는 긍정적일 수 있지만 고객 데이터센터 가동 지연은 역풍입니다.",
        "수주·실적": "기술 기대가 실제 고객 주문·백로그·매출로 전환되는지 확인하는 가장 강한 검증 신호입니다.",
        "유리기판·첨단 패키징": "고밀도 AI 패키징의 휨·배선·열 문제를 줄이는 방향으로 채택이 늘면 Corning의 신규 AI 매출 경로가 열릴 수 있습니다.",
        "광통신": "GPU 수 증가로 랙·데이터센터 사이 데이터 이동량이 커지면서 구리 대신 광 연결 비중이 상승하는 구조적 수혜 신호입니다.",
        "랙 내부 인터커넥트": "GPU·CPU·메모리 사이 데이터 이동 지연을 줄여 비싼 가속기의 실제 이용률을 높이는 부품 수요와 연결됩니다.",
        "AI 네트워킹": "AI 성능 병목이 단일 GPU 연산력에서 데이터 이동·네트워크 전체로 넓어지는 흐름을 확인하는 신호입니다.",
        "광 링크 통합·수직계열화": "레이저·정밀광학·실리콘포토닉스·특수광섬유·수신부를 한 회사가 통합 공급하면 AI 광학의 가치가 개별 부품에서 전체 링크 설계·조립·테스트로 이동하는 신호입니다.",
        "고객·장기계약": "고객 협업이 장기계약과 앵커 고객으로 전환되면 기술 기대가 반복 가능한 양산 매출로 넘어가는 강한 검증 신호입니다.",
        "광학 콘텐츠 가치": "스위치·xPU당 광학 콘텐츠 금액이 높아지면 같은 AI 설비투자 안에서도 광학 부품·어셈블리의 매출 몫이 커지는 신호입니다.",
        "칩 간 광연결": "광 연결이 랙·패키지 경계를 넘어 칩 간 연결로 들어가면 2029~2030년 이후 메모리·가속기 패키징 구조까지 바꿀 수 있는 장기 재평가 신호입니다.",
        "특수광섬유": "범용 광섬유가 아니라 편광유지·모드매칭·멀티코어 같은 고부가 특수광섬유의 증설·양산이 확인되면 CPO·NPO 내부 콘텐츠 확대와 직접 연결됩니다.",
        "SiPh 파운드리": "대형 광모듈사의 실리콘포토닉스 설계가 외부 파운드리 양산으로 연결되면 삼성전자 등 파운드리의 신규 AI 매출 경로가 열리는 신호입니다.",
        "CPO 장비 수주·가시성": "CPO·SiPh 양산 전에 정밀 정렬·광 결합 장비 주문이 먼저 차는 선행신호입니다. 주문 가시성이 늘면 고객이 실제 양산 설비투자 예산을 집행하고 있다는 뜻에 가깝습니다.",
        "CPO 장비 증설·가동률": "장비업체가 신규 라인·공장·조립능력을 늘리는 것은 수주가 단기 샘플을 넘어 반복 양산 수요로 전환될 가능성을 보여주는 설비투자 신호입니다.",
        "CPO 장비 출하·양산": "정밀 모션·광 결합 장비가 실제 출하·양산으로 넘어가면 CPO 기술 발표가 제조현장 CAPEX와 매출로 연결됐다는 직접 증거입니다.",
        "CPO 장비 고객검증·도입": "글로벌 광통신 고객이나 OSAT 인증·검증 통과는 장비가 시험평가를 넘어 실제 생산라인에 채택될 가능성을 높이는 핵심 관문입니다.",
        "CPO 정밀정렬·광결합 장비": "CPO 제조의 나노미터급 정렬·광 결합·FAU 공정 장비 수요가 늘면 광학 부품뿐 아니라 생산장비까지 AI 인프라 설비투자 수혜가 확산되는 신호입니다.",
    }
    return mapping[category]


def risk_for(category: str) -> str:
    mapping = {
        "AAOI 현장발전 EPC 추진": "전력망·가스 공급·허가·부지 설치·보험과 SOFC 초기 고장으로 2027년 1분기 가동 목표가 지연될 수 있습니다.",
        "AAOI 현장발전 용량·계약금액": "정격출력과 실제 연속 가동률이 다르며 보조금·설치비·천연가스 가격·정비비를 반영해야 실질 단위 원가를 판단할 수 있습니다.",
        "AAOI SOFC 계획 용량·금액": "계획 용량과 계약 물량·실제 설치 용량이 다를 수 있으며, 가스·인허가·설치비·후속 유지보수 비용이 달라집니다.",
        "AAOI SOFC 착공·장비반입": "현장 배관·방재·계통 보호·고온 설비 인허가와 시운전의 지연 위험이 남습니다.",
        "AAOI SOFC 설치·검수": "설비 설치를 마쳐도 신뢰성 검사·안전 인수·가스 연결과 전력 계통 검증 실패 시 전원 인가가 지연될 수 있습니다.",
        "AAOI 현장발전 전원 인가": "연료전지 가동률·정비 정지·가스 공급·백업전원이 부족하면 실제 광모듈 라인 가동률 증가는 제한됩니다.",
        "AAOI 연료·전력 접속": "현지 연료 공급·계통 보호설비·가스 안전 승인·보험 조건에 문제가 있으면 전원 공급이 늦어집니다.",
        "AAOI 현장발전 보조금": "정부 심사·지급 지연이나 승인액 축소가 프로젝트 순설비투자와 투자회수기간을 바꿀 수 있습니다.",
        "AAOI SOFC 유지보수 계약": "SOFC 연료비·유지보수·스택 교체 주기와 가동률·보증충당금이 실제 반복매출 마진을 바꿀 수 있습니다.",
        "AAOI 전력 확보→출하 검증": "전력을 확보해도 고객별 제품 인증·광엔진 수율·1.6T 검사 시간·핵심 광부품 병목으로 출하가 자동 증가하지 않을 수 있습니다.",
        "AAOI 현장발전 일정·공급 위험": "2027년 1분기를 넘겨 전원 인가가 밀리면 신규 공장 고정비 부담과 광트랜시버 납기 위험이 먼저 나타납니다.",
        "OCS 고객·주문·배치": "OCS 제어 소프트웨어와 스위치 재구성 지연·광경로 차단·고장복구가 GPU 가동률을 떨어뜨리면 채택과 재주문이 지연될 수 있습니다.",
        "OCS 표준·상호운용성": "규격 합의 뒤에도 실제 다중업체 상호운용성·제어 인터페이스·운영 자동화 검증에 실패하면 설치가 지연됩니다.",
        "NPO 표준 제·개정": "CPO와 경쟁하는 NPO의 광결합·삽입손실·외장광원·서비스성·온도별 신뢰성 조건이 규격을 충족하지 못하면 인증이 지연됩니다.",
        "NPO 공급사·생태계 확대": "협약 참여와 실제 품질인증·PO가 다르며 공급사 추가가 가격 하락 또는 초기 품질관리 부담을 키울 수 있습니다.",
        "NPO 고객·양산·계약": "고객 인증·초기 수율·광결합 정렬·패키징 검사에서 병목이 생기면 계약 물량의 출하·검수·매출 인식이 지연됩니다.",
        "광메모리 투자·개발자금": "투자금 유치는 기술 검증이 아닙니다. 목표 토큰속도·메모리 용량·비트당 에너지가 실제 실리콘·독립 벤치마크·고객 샘플로 확인되지 않으면 밸류체인 기대만 앞설 수 있습니다.",
        "광메모리·추론 아키텍처": "현재 공개 수치는 대부분 회사의 설계목표이므로 실리콘 존재 여부·메모리 종류·패키징 수율·실제 토큰당 비용이 검증되지 않으면 기대가 매출로 이어지지 않을 수 있습니다.",
        "광메모리 고객검증·상용화": "2027 고객 인도 일정이 지연되거나 고객 실명이 공개되지 않은 채 샘플 단계에 머물면 상용화 시점이 뒤로 밀릴 수 있습니다.",
        "광메모리 성능·검증": "시뮬레이션·설계목표와 실측치를 혼동하면 안 되며, 대형 모델에서의 지연시간·전력·오류율·메모리 일관성 검증이 실패할 수 있습니다.",
        "VCSEL 광메모리 공급망": "micro-VCSEL 수율·열안정성·수명·웨이퍼 공급과 고밀도 패키징 정렬 난도가 병목이 되면 InP 회피 효과가 줄어들 수 있습니다.",
        "광컴퓨팅 투자·양산확대": "대규모 자금이 있어도 고용량 생산수율·패키징·레이저 수명·테스트 시간이 해결되지 않으면 설비 확장이 매출보다 먼저 비용 부담으로 나타날 수 있습니다.",
        "광컴퓨팅 상용화·고객검증": "고객검증·패키징 수율·레이저 신뢰성·표준화 일정이 늦어지면 대량배치가 지연될 수 있습니다.",
        "Photonic Fabric 매출 램프": "인수 당시 제시된 매출 시점·연환산 매출 목표가 고객 일정 또는 양산수율 때문에 늦어지면 마벨의 광스케일업 재평가 시점도 함께 밀릴 수 있습니다.",
        "Photonic Fabric 고객검증·수주": "고객 발표가 설계 검토나 평가 단계에 머물고 실제 주문·검증 통과로 이어지지 않으면 매출 시점이 늦어질 수 있습니다.",
        "Photonic Fabric 양산·출하": "초기 출하가 고객 인증·수율·패키징 문제로 반복 양산에 이어지지 않으면 출하 뉴스가 일회성 검증에 그칠 수 있습니다.",
        "Photonic Fabric 인수·통합": "인수 완료 이후 통합 비용은 발생하지만 고객·제품 통합과 매출 개시가 늦어지면 단기 비용이 먼저 나타날 수 있습니다.",
        "Photonic Fabric 광스케일업": "스케일업 표준 경쟁, 패키징 수율, 외부 레이저·광엔진 비용이 기대보다 높으면 대량 채택 속도가 늦어질 수 있습니다.",
        "광컴퓨팅·스케일업 인터커넥트": "광링크가 구리 대비 비용·전력·유지보수 우위를 충분히 입증하지 못하거나 표준 경쟁이 길어지면 채택 속도가 늦어질 수 있습니다.",
        "FCC 광트랜시버 규제": "3.2T·65% 같은 시장 시나리오가 최종 규정에서 바뀌거나, 미국 제조요건이 더 엄격해지면 예상 수혜기업과 공급망 구조가 달라질 수 있습니다.",
        "미국 광트랜시버 규제·법안": "연방 국가안보시스템 조달 제한을 전체 상업용 데이터센터 금지로 확대해석하면 실적 민감도를 과대평가할 수 있습니다.",
        "InP 기판 병목": "중국 수출허가·원산지 규제가 강화되면 InP 가격 상승의 수혜보다 공급중단·고객 이원화가 먼저 나타날 수 있습니다.",
        "InP 기판 장기계약·생산능력": "선지급·예약 계약이 있어도 6인치 결정성장 수율·파일럿→양산 전환·수출허가가 지연되면 고객의 예약 물량을 실제 출하하지 못할 수 있습니다.",
        "InP 수출허가·공급망": "허가 완화가 공급 정상화로 이어지면 가격·리드타임 프리미엄이 빠르게 축소될 수 있고, 반대로 규제 강화 시 출하 자체가 막힐 수 있습니다.",
        "GaAs 광통신 기판·파운드리": "GaAs 수요가 1.6T 광통신이 아니라 스마트폰·위성 등 다른 응용에 더 크게 좌우되면 AI 데이터센터 수혜 민감도를 과대평가할 수 있습니다.",
        "1.6T 광모듈 제조·패키징 램프": "고객 집중도와 모듈 세대 전환 속도가 높아 1.6T 주문이 특정 고객의 일정 변경에 민감할 수 있고, 수율이 낮으면 외형 성장보다 원가 부담이 먼저 나타날 수 있습니다.",
        "광모듈 제조·패키징": "광통신 수요 증가가 곧바로 파브리넷의 고마진 매출 증가를 뜻하지 않으며 제품 혼합·고객 집중·가동률을 함께 봐야 합니다.",
        "광통신 제조": "수요 기대만 있고 실제 고객 주문·생산·출하가 없으면 제조 매출로 연결되지 않습니다.",
        "CPO 광패키징 기판·양산": "양산 발표 뒤에도 고객 인증·가동률·반복 주문이 따라오지 않으면 초기 출하가 일회성에 그칠 수 있고, 패키지 기판 수율 저하는 매출총이익률을 먼저 압박할 수 있습니다.",
        "CPO 광패키징 기판·수율·열검증": "대형 패키지의 휨·열팽창 불일치·광결합 오차·삽입손실이 높으면 재작업과 검사시간이 늘고 양품률이 떨어져 고객 승인과 양산 일정이 지연될 수 있습니다.",
        "CPO 광패키징 기판·인터포저": "유리기판·유리인터포저는 TGV 성숙도와 대량생산 수율이 아직 핵심 변수이고, 기존 ABF·실리콘 인터포저가 예상보다 오래 유지되면 신소재 기판 전환 시점이 늦어질 수 있습니다.",
        "CPO 첨단패키징·COUPE": "CPO가 AI 칩과 동일한 2.5D·3D 패키징 자원을 놓고 경쟁하면 생산능력 확보가 늦어지고, 패키징 수율 저하는 광엔진보다 더 큰 출하 병목이 될 수 있습니다.",
        "CPO 검사·신뢰성 병목": "검사 표준이 통일되지 않고 검사시간이 길면 장비 증설만으로 처리량을 늘리기 어렵고 고객 인증·매출 인식이 지연될 수 있습니다.",
        "CPO 광엔진 수율·광결합": "광결합 오차·열·패키징 불량이 누적되면 광엔진 양품률이 떨어지고 검사·재작업 비용이 급증할 수 있습니다.",
        "CPO 패키징·검사": "기술 시연이 성공해도 패키징 수율·검사 처리량·고객 신뢰성 인증이 확보되지 않으면 대량생산은 지연될 수 있습니다.",
        "국내 AI 광트랜시버 수주": "반복 PO가 이어지지 않거나 고객 집중도가 높으면 단일 계약의 매출 기여가 일회성에 그칠 수 있습니다.",
        "국내 AI 광트랜시버 납기·검수": "검수 지연이 반복되면 매출 인식이 뒤로 밀리고 재고·운전자본 부담이 먼저 커질 수 있습니다.",
        "국내 AI 광트랜시버": "고객 실명·반복수주·검수 완료가 확인되지 않으면 실제 AI 데이터센터 매출 민감도를 과대평가할 수 있습니다.",
        "국내 1.6T 고객검증·샘플": "샘플 출하가 고객 인증·양산 PO로 이어지지 않거나 ELSFP 열·신뢰성 검증이 늦어지면 매출 시점이 지연될 수 있습니다.",
        "국내 광통신 수주·양산": "초기 수주가 반복계약으로 이어지지 않거나 가격 하락이 빠르면 외형 증가 대비 마진 개선이 제한될 수 있습니다.",
        "국내 광통신": "제품 발표만 있고 고객 검증·수주가 없으면 투자 기대가 실제 매출보다 앞설 수 있습니다.",
        "ADST CPO 정렬·검사 수주": "PO가 반복 발주로 이어지지 않거나 고객이 CPO 양산 일정을 늦추면 장비 매출이 일회성에 그칠 수 있습니다. 검수·수주잔고·고객 다변화를 함께 봐야 합니다.",
        "ADST CPO 정렬·검사 양산": "고객 라인 수율이 낮거나 CPO 일정이 연기되면 장비 설치와 매출 인식도 함께 밀리고 재고·운전자본 부담이 먼저 나타날 수 있습니다.",
        "ADST CPO 정밀정렬·검사": "정렬 정밀도·UPH·검사시간이 고객 요구를 못 맞추거나 경쟁 장비가 인증되면 독점 기대가 약해질 수 있습니다.",
        "ADST CPO 장비": "성호전자 본업 필름콘덴서와 ADST CPO 장비를 혼동하면 실적 민감도를 과대평가할 수 있습니다.",
        "POET ELS 상용화·고객검증": "협력 발표가 고객 인증·양산 주문으로 이어지지 않거나 외장광원 수율·열·패키징 비용이 높으면 매출 시점이 지연될 수 있습니다.",
        "POET ELS·하이브리드집적": "기술 집적 성공만으로 양산 경제성이 보장되지 않으며 레이저 공급, 패키징 수율, 고객 인증이 별도 병목입니다.",
        "POET 광엔진 상용화": "초기 샘플이 반복 주문으로 이어지지 않거나 고객 집중도가 높으면 매출 가시성이 낮을 수 있습니다.",
        "POET 광엔진·하이브리드집적": "플랫폼 장점이 있어도 대량생산 수율과 원가가 기존 SiPh·EML 방식보다 불리하면 채택이 제한될 수 있습니다.",
        "TFLN 400G/lane": "400G/lane 실험 성능이 실제 패키징·온도·수명·대량생산 수율에서 재현되지 않으면 상용화가 늦어질 수 있습니다.",
        "TFLN 고객검증·양산": "TFLN은 아직 멀티벤더 대량생산·패키징 표준과 비용곡선이 확정되지 않았고 SiPh·InP 대안이 있어 채택이 분산될 수 있습니다.",
        "TFLN 광변조기": "연구 성능과 고객 양산은 별개입니다. 파운드리 수율·결합손실·패키징·드라이버 통합 비용이 먼저 확인돼야 합니다.",
        "ELSFP 블라인드메이트·광결합": "삽입손실·편광 정렬·반복 착탈 신뢰성이 나쁘면 외장광원 출력 여유를 잡아먹고 현장 교체성 이점이 줄어듭니다.",
        "ELSFP 신뢰성·서비스성": "레이저를 외부로 빼도 커넥터·PMF·TEC·전원·오염 문제가 새로운 고장점이 될 수 있어 전체 링크 신뢰성을 확인해야 합니다.",
        "ELSFP 연결부품": "OIF 규격 준수 자체가 고객 채택을 보장하지 않으며 실제 스위치·가속기 설계 채택과 양산 수량이 필요합니다.",
        "ELS 외장광원·양산": "Coherent와 Lumentum 등 복수 공급자가 있어 특정 업체 독점 가정은 위험합니다. 출력·효율·수명·가격·고객 이원화가 마진을 좌우합니다.",
        "ELS 외장광원 신뢰성": "고온 출력과 수명 검증이 충분하지 않거나 레이저 고장률이 예상보다 높으면 CPO 시스템 가동률과 유지보수 비용이 악화될 수 있습니다.",
        "ELS 외장광원": "외장화가 열 문제를 완화해도 광결합 손실·PMF 정렬·커넥터 비용이 커지면 시스템 총비용 우위가 줄어들 수 있습니다.",
        "200G/lane 구리 연장기술": "ACC·co-packaged copper가 2~4m 구간을 낮은 전력·지연으로 커버하면 일부 scale-up 구간의 광 전환이 뒤로 밀릴 수 있습니다.",
        "200G/lane 구리 도달거리": "1m는 대표적인 수동 DAC 한계이지 모든 구리 링크의 절대 한계가 아닙니다. ACC·AEC·co-packaged copper를 섞으면 더 긴 거리가 가능하므로 CPO 수요를 과대추정하면 안 됩니다.",
        "400G/lane 구리 한계": "400G/lane 상용화 시점이 늦거나 랙 구조가 더 짧은 구리 배선을 허용하면 광 전환 시점도 늦어질 수 있습니다.",
        "3.2T 전환": "고객 인증·대량생산 수율이 지연되면 매출 시점이 뒤로 밀릴 수 있습니다.",
        "CPO·실리콘 포토닉스": "레이저 신뢰성·수율·현장 교체 난도와 플러거블 대비 경제성이 핵심 실패 경로입니다.",
        "1.6T 전환": "물량 증가보다 평균판매단가 하락이 빠르면 매출 성장 폭이 제한될 수 있습니다.",
        "공급 병목·가격": "가격 상승이 고객의 AI 랙 배치를 늦추면 단기 출하량에는 오히려 역풍이 될 수 있습니다.",
        "수주·실적": "한두 고객 집중이나 선주문이 실제 반복매출로 이어지지 않는지 확인해야 합니다.",
        "유리기판·첨단 패키징": "고객 인증·수율·기존 유기기판 대비 원가 우위가 확보되지 않으면 채택이 늦어질 수 있습니다.",
        "광통신": "전력·열·레이저 공급 및 고객 설계 전환 일정이 광부품 출하 시점을 늦출 수 있습니다.",
        "랙 내부 인터커넥트": "PCIe/CXL 세대 전환 지연이나 고객 자체 설계가 범용 부품 시장을 축소할 수 있습니다.",
        "AI 네트워킹": "GPU 설비투자가 둔화하거나 하이퍼스케일러가 네트워크 투자를 뒤로 미루면 수혜 시점이 지연될 수 있습니다.",
        "광 링크 통합·수직계열화": "통합 공급사가 부품을 내재화할수록 독립 레이저·렌즈·아이솔레이터·특수광섬유 업체의 외부 공급 기회가 줄어들 수 있습니다.",
        "고객·장기계약": "협업 고객 수가 늘어도 실제 양산 발주와 반복매출로 전환되지 않으면 매출 가시성이 과대평가될 수 있습니다.",
        "광학 콘텐츠 가치": "최대 콘텐츠 기회와 실제 평균판매단가는 다르므로 고객 믹스·수율·가격 인하로 실현 금액이 낮아질 수 있습니다.",
        "칩 간 광연결": "패키지 내 광연결은 수율·열·정렬 정밀도·신뢰성 검증이 어려워 2029~2030년 일정이 지연될 수 있습니다.",
        "특수광섬유": "특수광섬유 증설이 실제 CPO·NPO 채택보다 빠르면 가동률과 가격이 먼저 압박받을 수 있습니다.",
        "SiPh 파운드리": "고객 실명이 공개되지 않거나 시험생산 물량에 그치면 대형 양산 수주로 보기 어렵고 기존 선발 파운드리와의 경쟁도 남습니다.",
        "CPO 장비 수주·가시성": "6~12개월 선발주나 중복 발주가 실제 최종 CPO 수요보다 앞서면 수주잔고가 향후 취소·납기 연기로 바뀔 수 있습니다.",
        "CPO 장비 증설·가동률": "증설 속도가 실제 CPO 양산보다 빠르면 신규 공장 가동률과 고정비 부담이 먼저 악화될 수 있습니다.",
        "CPO 장비 출하·양산": "장비 출하 후 고객 검수·설치·수율 확보가 늦어지면 매출 인식과 후속 주문이 지연될 수 있습니다.",
        "CPO 장비 고객검증·도입": "OSAT·광모듈 고객의 검증을 통과해도 양산 라인 적용이나 반복 발주까지 이어지지 않으면 매출 규모는 제한될 수 있습니다.",
        "CPO 정밀정렬·광결합 장비": "정렬 정밀도·검사시간·수율이 목표에 못 미치거나 CPO 채택 일정이 늦어지면 장비 투자가 뒤로 밀릴 수 있습니다.",
    }
    return mapping[category]


def _self_test_korean_optics_alerts() -> None:
    opticore_order = "옵티코어 AI 데이터센터용 400G 800G 광트랜시버 공급계약 체결"
    assert signal_score(opticore_order, "전자신문") >= 7
    assert category_for(opticore_order, "Opticore") == "국내 AI 광트랜시버 수주"
    assert stage_for(opticore_order) == "수주·가시성"

    opticore_delay = "옵티코어 400G 800G 광트랜시버 고객사 검수 일정 조정으로 계약기간 변경"
    assert signal_score(opticore_delay, "한국거래소") >= 7
    assert category_for(opticore_delay, "Opticore") == "국내 AI 광트랜시버 납기·검수"
    assert stage_for(opticore_delay) == "납기·검수 변경"

    oe_sample = "OE Solutions begins Q3 2026 customer sampling of ELSFP for 1.6T AI networking"
    assert signal_score(oe_sample, "OE Solutions") >= 7
    assert category_for(oe_sample, "OE Solutions") == "국내 1.6T 고객검증·샘플"
    assert stage_for(oe_sample) == "고객 검증·양산 도입"

    assert len(story_tokens("옵티코어 AI 데이터센터 광트랜시버 공급계약")) >= 3
    assert source_priority("전자신문") >= 65
    assert source_priority("OE Solutions") >= 65

    cpo_pkg_prod = (
        "Broadcom CPO volume production uses advanced substrate-level multi-chip packaging "
        "for silicon photonics optical engines"
    )
    assert signal_score(cpo_pkg_prod, "Broadcom") >= 7
    assert category_for(cpo_pkg_prod, "CPO Packaging & Test") == "CPO 광패키징 기판·양산"

    cpo_pkg_yield = (
        "CPO glass interposer warpage and thermal CTE mismatch constrain silicon photonics "
        "package substrate yield"
    )
    assert signal_score(cpo_pkg_yield, "TrendForce") >= 7
    assert category_for(cpo_pkg_yield, "CPO Packaging & Test") == "CPO 광패키징 기판·수율·열검증"

    # One TrendForce FAU article may match both packaging/test and equipment queries.
    # It must be one Telegram event with two interpretation axes, never two "new changes".
    same_article_a = {
        "company": "CPO Packaging & Test",
        "ticker": "CPO 패키징·검사",
        "category": "CPO 광엔진 수율·광결합",
        "title": "Passive Part, Active Battle: Inside CPO's FAU Coupling Bottleneck - TrendForce",
        "source": "TrendForce",
        "link": "https://news.google.com/rss/articles/example?oc=5",
        "published": "2026-10-07T05:31:28+00:00",
        "score": 10,
    }
    same_article_b = {
        "company": "CPO Equipment Supply Chain",
        "ticker": "장비 공급망",
        "category": "CPO 정밀정렬·광결합 장비",
        "title": "Passive Part, Active Battle: Inside CPO's FAU Coupling Bottleneck - TrendForce",
        "source": "TrendForce",
        "link": "https://news.google.com/rss/articles/example?oc=5",
        "published": "2026-10-07T05:31:28+00:00",
        "score": 10,
    }
    assert same_article_identity(same_article_a, same_article_b)
    merged = merge_article_scopes(same_article_a, same_article_b)
    assert len(merged.get("related_scopes") or []) == 2

    # Harden three separate optical architectures against headline confusion.
    ocs_member = "NVIDIA joins OCP optical circuit switching project"
    ocs_contract = "NVIDIA signs contract to purchase optical circuit switching OCS switches for GPU clusters"
    cpo_not_ocs = "NVIDIA Spectrum-X Ethernet Photonics CPO volume production shipments"
    npo_old = "Huawei launches China's first OPEN NPO MSA with industry partners"
    npo_real = "Huawei OPEN NPO begins mass production and customer delivery of near-packaged optics"
    fau_old = "Passive Part, Active Battle: Inside CPO's FAU Coupling Bottleneck - TrendForce"
    fau_new = "ficonTEC receives new order for FAU optical coupling production equipment for CPO"
    assert classify_structural_axis("OCS Optical Circuit Switching", ocs_member) is None
    assert classify_structural_axis("OCS Optical Circuit Switching", ocs_contract) == "OCS 고객·주문·배치"
    assert classify_structural_axis("OCS Optical Circuit Switching", cpo_not_ocs) is None
    assert classify_structural_axis("Huawei OPEN NPO", npo_old) is None
    assert classify_structural_axis("Huawei OPEN NPO", npo_real) == "NPO 고객·양산·계약"
    assert meaningful_fau_milestone(fau_old) is False
    assert meaningful_fau_milestone(fau_new) is True
    assert canonical_story_key("Huawei OPEN NPO", npo_old) == "huawei|open-npo|msa-initial-2026-07"
    assert "OCS" not in category_for(cpo_not_ocs, "NVIDIA")
    assert source_priority("Open Compute Project") == 100
    assert evidence_label({"company": "Huawei OPEN NPO", "source": "TrendForce"}).startswith("독립된")
    assert classify_structural_axis("Huawei OPEN NPO", "Huawei plans to begin OPEN NPO mass production in 2027") is None
    assert classify_structural_axis("OCS Optical Circuit Switching", "NVIDIA reportedly considers deploying OCS optical circuit switches") is None
    assert classify_structural_axis("OCS Optical Circuit Switching", "NVIDIA to deploy optical circuit switching OCS switches in 2027") is None
    assert classify_structural_axis("Huawei OPEN NPO", "华为OPEN NPO MSA 2.0发布") == "NPO 표준 제·개정"
    assert _is_official_structural_source({
        "company": "Huawei OPEN NPO", "source": "Huawei Cloud", "source_url": "https://www.huaweicloud.com"
    })
    assert not _is_official_structural_source({
        "company": "Huawei OPEN NPO", "source": "Huawei", "source_url": "https://example.com"
    })

    # Regression: the 2026-10-08 Bloom/Leadray story was missing because
    # the old query required optical/800G/CPO terms in the news headline.
    initial = "Bloom Energy SOFC system to support AOI's Taiwan expansion"
    taiwan_press = "賀喜能源擔任祥茂光電EPC 導入Bloom Energy現地發電系統"
    forecast = "AOI Taiwan Bloom Energy SOFC to begin operation in first quarter 2027"
    realized = "AAOI Taiwan Bloom Energy SOFC plant commissioned and entered commercial operation"
    another_site = "Bloom Energy installs 3MW at Unimicron Taiwan facility"
    old_customer = "AAOI Taiwan facility was qualified to produce some 800G products during 2025"
    award_application = "祥茂光電Bloom Energy SOFC台灣已申請補助 awaiting government approval"
    award_granted = "祥茂光電Bloom Energy SOFC台灣燃料電池補助核准"
    assert power_milestone(initial)[2] == POWER_INITIAL_KEY
    assert power_milestone(taiwan_press)[2] == POWER_INITIAL_KEY
    assert power_milestone(forecast)[2] == POWER_INITIAL_KEY
    assert power_milestone(realized)[2] != POWER_INITIAL_KEY
    assert power_milestone(another_site) is None
    assert power_milestone(old_customer) is None
    assert power_milestone(award_application)[2] == POWER_INITIAL_KEY
    assert power_milestone(award_granted)[0] == "AAOI 현장발전 보조금"
    assert power_milestone("AAOI Taiwan Bloom Energy SOFC plant 5MW officially confirmed")[2] != power_milestone(
        "AAOI Taiwan Bloom Energy SOFC plant 8MW officially confirmed"
    )[2]
    assert power_milestone(
        "AAOI Taiwan Bloom Energy 5MW SOFC to be commissioned in 2027"
    )[0] == "AAOI SOFC 계획 용량·금액"
    assert power_milestone(
        "AAOI Taiwan Bloom Energy SOFC to be commissioned in Q1 2027"
    )[2] == POWER_INITIAL_KEY
    p1 = {"company": POWER_COMPANY, "title": initial}
    p2 = {"company": POWER_COMPANY, "title": taiwan_press}
    assert same_power_event(p1, p2)
    assert official_power_source({
        "source": "Bloom Energy", "source_url": "https://www.bloomenergy.com/news/test"
    })
    assert not official_power_source({
        "source": "Bloom Energy", "source_url": "https://example.org/blog"
    })
    assert not retain_historical_optics_record({
        "company": POWER_COMPANY,
        "title": "Chunghwa Telecom's Simplified Modular Data Center delivers turnkey deployment",
    })
    assert retain_historical_optics_record({
        "company": POWER_COMPANY,
        "title": initial,
    })
    assert power_milestone("AAOI Taiwan Bloom Energy SOFC long-term service contract signed")[0] == "AAOI SOFC 유지보수 계약"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen_keys": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"initialized": False, "seen_keys": []}


def main() -> None:
    _self_test_korean_optics_alerts()
    (ROOT / "out").mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)

    state = load_state()

    # workflow_run is only a redundant backup trigger. If a successful check was
    # already performed recently, skip the duplicate query burst to avoid
    # throttling Google News and other sources.
    if os.getenv("GITHUB_EVENT_NAME", "").strip() == "workflow_run":
        last_checked = state.get("last_checked_kst")
        if last_checked:
            try:
                last_dt = dt.datetime.fromisoformat(last_checked).astimezone(KST)
                age = dt.datetime.now(KST) - last_dt
                if age < dt.timedelta(minutes=15):
                    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
                    STATUS_PATH.write_text(
                        "# AI 네트워킹·광통신 감시 상태\n\n"
                        f"- 조회 생략: 최근 정상 조회 후 {int(age.total_seconds() // 60)}분 경과\n"
                        "- 사유: workflow_run 백업 트리거 중복 방지\n",
                        encoding="utf-8",
                    )
                    print("backup_trigger_skipped_recent_check=true")
                    return
            except Exception:
                pass

    seen = set(state.get("seen_keys") or [])
    for invalid in state.get("seen_story_records") or []:
        if not retain_historical_optics_record(invalid):
            seen.discard(event_key(
                str(invalid.get("company") or ""),
                str(invalid.get("title") or ""),
                str(invalid.get("source") or ""),
            ))
    all_relevant: list[dict] = []
    errors: list[str] = []
    successful_company_queries = 0
    attempted_company_queries = 0
    consecutive_service_failures = 0
    power_source_healthy = False
    power_source_errors: list[str] = []

    cutoff = NOW - dt.timedelta(days=7)
    for company, meta in COMPANIES.items():
        attempted_company_queries += 1
        try:
            feed_items = []
            locales = meta.get("locales") or [{"hl": "en-US", "gl": "US", "ceid": "US:en"}]
            queries = meta.get("queries") or [meta.get("query")]
            power_locales_ok: set[str] = set()
            power_query_failed = False
            for query in [q for q in queries if q]:
                for locale in locales:
                    try:
                        rows = query_google_news(
                            query,
                            hl=locale.get("hl", "en-US"),
                            gl=locale.get("gl", "US"),
                            ceid=locale.get("ceid", "US:en"),
                        )
                        feed_items.extend(rows)
                        if company == POWER_COMPANY:
                            power_locales_ok.add(locale.get("gl", "US"))
                    except Exception as exc:
                        if company != POWER_COMPANY:
                            raise
                        power_query_failed = True
                        power_source_errors.append(
                            f"{locale.get('gl', 'US')} query: {type(exc).__name__}: {exc}"
                        )
            if company == POWER_COMPANY:
                # Unlike a generic news category, the power-to-production gate
                # must not advance when one language lane is unavailable.
                power_source_healthy = (
                    not power_query_failed
                    and {"TW", "US"}.issubset(power_locales_ok)
                )
                if not power_source_healthy:
                    errors.append(
                        "AAOI Taiwan power source degraded: hold only power lane; "
                        + " | ".join(power_source_errors[:4])
                    )
                    continue
        except Exception as exc:
            errors.append(f"{company}: {type(exc).__name__}: {exc}")
            is_service_failure = isinstance(exc, urllib.error.HTTPError) and getattr(exc, "code", None) in {429, 500, 502, 503, 504}
            consecutive_service_failures = consecutive_service_failures + 1 if is_service_failure else 0
            if consecutive_service_failures >= 3:
                errors.append("Google News circuit breaker: repeated service failures; remaining queries aborted")
                break
            continue
        successful_company_queries += 1
        consecutive_service_failures = 0
        for item in feed_items:
            published = dt.datetime.fromisoformat(item["published"]) if item.get("published") else None
            if published and published < cutoff:
                continue
            title = item["title"]
            source = item.get("source") or ""
            # A power/fuel-cell article is not a generic 800G customer award.
            # Route it exclusively through the AAOI factory-power evidence gate.
            if company == "Applied Optoelectronics" and is_aaoi_power_topic(title):
                continue
            power_event = power_milestone(title) if company == POWER_COMPANY else None
            if company == POWER_COMPANY and power_event is None:
                continue

            # Keep 800V-DC / SiC / GaN power architecture separate from optics.
            # Higher rack density can drive both power and optical changes, but one does
            # not prove the other. Power-only stories stay in the existing data-center
            # power watcher unless the headline contains a direct optical/CPO link.
            power_only = bool(re.search(
                r"\bSiC\b|silicon carbide|\bGaN\b|gallium nitride|800\s*V(?:DC)?|HVDC|power semiconductor",
                title,
                re.I,
            ))
            optical_link = bool(re.search(
                r"\bInP\b|indium phosphide|\bGaAs\b|gallium arsenide|砷化鎵|optical|transceiver|"
                r"\bCPO\b|\bNPO\b|1\.6T|3\.2T|laser|photodiode|silicon photonics|\bSiPh\b|COUPE|optical engine",
                title,
                re.I,
            ))
            if power_only and not optical_link:
                continue

            # Conference demonstrations are discovery signals, not commercial milestones.
            # ECOC/OFC showcase-only headlines are baselined unless they also include
            # customer/order/production/capacity/revenue/qualification evidence.
            conference_only = bool(re.search(r"\b(?:ECOC|OFC)\b|demonstrat(?:e|es|ed|ing|ion)|showcase|exhibit|booth", title, re.I))
            commercial_proof = bool(re.search(
                r"customer|order|bookings?|backlog|shipment|production|capacity|revenue|guidance|"
                r"qualification|qualified|certif|agreement|contract|supply|design win|ramp|mass production",
                title,
                re.I,
            ))
            if conference_only and not commercial_proof:
                continue

            structural_category = classify_structural_axis(company, title)
            if company in NEW_STRUCTURE_AXES and structural_category is None:
                continue
            if company in {"CPO Packaging & Test", "CPO Equipment Supply Chain"}:
                if not meaningful_fau_milestone(title):
                    continue

            score = signal_score(title, source)
            if power_event:
                # Factory fuel cell / grid news often lacks 800G or "optical"
                # in the title, so the original optics score must not drop it.
                score = max(score, 10)
            # Require both a technology/data-movement term and a concrete commercial/action term.
            # CPO mentions alone are not enough: this prevents stock-reaction/commentary articles
            # from becoming alerts. Only a 3.2T milestone may bypass the action requirement.
            has_high = any(re.search(p, title, re.I) for p in HIGH_SIGNAL_PATTERNS)
            has_action = any(re.search(p, title, re.I) for p in ACTION_PATTERNS)
            very_strong = bool(re.search(r"\b3\.2\s*[Tt]\b", title, re.I))
            if not power_event and (score < 7 or not has_high or (not has_action and not very_strong)):
                continue
            key = event_key(company, title, source)
            item.update({
                "company": company,
                "ticker": meta["ticker"],
                "score": score,
                "key": key,
                "stage": power_event[1] if power_event else structural_stage(company, structural_category, title) if structural_category else stage_for(title),
                "category": power_event[0] if power_event else category_for(title, company),
            })
            all_relevant.append(item)

    # Fail closed when the discovery layer is unhealthy. Never advance baselines
    # or silently report "no change" after a broad upstream outage.
    required_successes = max(3, (len(COMPANIES) + 1) // 2)
    if successful_company_queries < required_successes:
        if PENDING_PATH.exists():
            PENDING_PATH.unlink()
        if ALERT_PATH.exists():
            ALERT_PATH.unlink()
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        status_lines = [
            "# AI 네트워킹·광통신 감시 상태",
            "",
            f"- 소스 상태: 실패 — 정상 조회 {successful_company_queries}/{attempted_company_queries}",
            f"- 최소 정상 소스 기준: {required_successes}",
            "- 상태 기준선: 갱신하지 않음",
            "- Telegram: 송출하지 않음",
        ]
        if errors:
            status_lines.extend(["", "## 소스 오류"] + [f"- {e}" for e in errors])
        STATUS_PATH.write_text("\n".join(status_lines).strip() + "\n", encoding="utf-8")
        print(f"source_health_failed=true successful={successful_company_queries} attempted={attempted_company_queries} errors={len(errors)}")
        raise RuntimeError("Discovery sources unhealthy; state intentionally not advanced")

    # Source-quality gate: unknown/low-quality sources cannot trigger by themselves.
    # They are admitted only when a higher-quality source independently reports the same event.
    def source_is_corroborated(item: dict) -> bool:
        if source_priority(item.get("source") or "") >= 65:
            return True

        # Private photonics startups are often first covered by specialist media.
        # Allow a low-priority source only when a second independent outlet reports
        # the same underlying event. One low-quality article can never trigger alone.
        if item.get("company") in {"Volantis", "Lightmatter", "Ayar Labs", "Xscape Photonics"}:
            corroborating_sources = {
                normalize_text(other.get("source") or "").lower()
                for other in all_relevant
                if other is not item
                and normalize_text(other.get("source") or "").lower() != normalize_text(item.get("source") or "").lower()
                and same_underlying_story(item, other)
            }
            if corroborating_sources:
                return True

        return any(
            other is not item
            and source_priority(other.get("source") or "") >= 65
            and same_underlying_story(item, other)
            for other in all_relevant
        )

    quality_candidates = list(all_relevant)
    all_relevant = [
        item for item in quality_candidates
        if (
            source_is_corroborated(item)
            and credible_structural_source(item, quality_candidates)
            and verified_power_event(item, quality_candidates)
        )
    ]

    # Stable order: newest first, then score.
    def sort_key(item: dict):
        published = item.get("published") or "1970-01-01T00:00:00+00:00"
        return (published, item.get("score", 0))

    all_relevant.sort(key=sort_key, reverse=True)

    # Collapse syndicated/mirrored articles about the same underlying event.
    # Prefer the company release or higher-quality reporting instead of counting
    # each headline/source as a separate "new change".
    deduped: list[dict] = []
    for item in all_relevant:
        exact_index = next(
            (idx for idx, existing in enumerate(deduped) if same_article_identity(item, existing)),
            None,
        )
        if exact_index is not None:
            deduped[exact_index] = merge_article_scopes(deduped[exact_index], item)
            continue

        matched_index = next(
            (idx for idx, existing in enumerate(deduped) if same_underlying_story(item, existing)),
            None,
        )
        if matched_index is None:
            deduped.append(item)
            continue
        if prefer_story_item(item, deduped[matched_index]):
            replacement = dict(item)
            if deduped[matched_index].get("related_scopes"):
                replacement["related_scopes"] = list(deduped[matched_index]["related_scopes"])
            deduped[matched_index] = replacement

    initialized = bool(state.get("initialized"))
    dedupe_version = int(state.get("dedupe_version") or 0)
    seen_story_keys = (
        set(state.get("seen_story_keys") or [])
        | set(KNOWN_PHOTONIC_BASELINE_KEYS)
        | set(KNOWN_NEW_STRUCTURE_KEYS)
        | set(POWER_BASELINE_KEYS)
    )
    seen_story_records = [
        record for record in (state.get("seen_story_records") or [])
        if retain_historical_optics_record(record)
    ]

    for item in deduped:
        item["story_key"] = canonical_story_key(item["company"], item["title"])

    def already_seen(item: dict) -> bool:
        if item["key"] in seen:
            return True
        story_key = item.get("story_key")
        if story_key and story_key in seen_story_keys:
            return True
        for previous in seen_story_records:
            if same_article_identity(item, previous):
                return True
            if previous.get("company") != item.get("company"):
                continue
            # Never let a previously-sent low-quality/market-reaction source suppress
            # a later official or high-quality structural event.
            if source_priority(previous.get("source") or "") < 65:
                continue
            try:
                prev_dt = dt.datetime.fromisoformat(previous.get("published") or "")
                item_dt = dt.datetime.fromisoformat(item.get("published") or "")
                if abs((item_dt - prev_dt).total_seconds()) > 7 * 24 * 3600:
                    continue
            except Exception:
                pass
            if same_underlying_story(item, previous):
                return True
        return False

    new_items = [item for item in deduped if not already_seen(item)]

    updated_seen = list(dict.fromkeys([item["key"] for item in deduped] + list(seen)))[:1500]
    updated_story_keys = list(dict.fromkeys(
        [item["story_key"] for item in deduped if item.get("story_key")] + list(seen_story_keys)
    ))[:500]
    new_story_records = [{
        "company": item.get("company"),
        "category": item.get("category"),
        "title": item.get("title"),
        "source": item.get("source"),
        "published": item.get("published"),
        "link": item.get("link"),
    } for item in deduped if source_priority(item.get("source") or "") >= 65]

    # Clean legacy state: remove low-quality reaction sources and collapse
    # syndicated/mirrored records by underlying event, not just exact text.
    merged_story_records = []
    for record in new_story_records + seen_story_records:
        if source_priority(record.get("source") or "") < 65:
            continue
        if any(
            same_article_identity(record, existing) or same_underlying_story(record, existing)
            for existing in merged_story_records
        ):
            continue
        merged_story_records.append(record)
        if len(merged_story_records) >= 500:
            break

    pending = {
        "initialized": True,
        "dedupe_version": 3,
        "quality_version": 3,
        "photonic_compute_version": 6,
        "optical_material_version": 1,
        "cpo_equipment_version": 2,
        "optical_policy_version": 2,
        "korea_optics_version": 1,
        "optical_bottleneck_version": 1,
        "optical_packaging_version": 2,
        "structural_optics_version": STRUCTURAL_OPTICS_VERSION,
        "aaoi_taiwan_power_watch_version": POWER_MONITOR_VERSION,
        "aaoi_taiwan_power_source_ok": power_source_healthy,
        "aaoi_taiwan_power_last_healthy_kst": (
            dt.datetime.now(KST).isoformat(timespec="seconds")
            if power_source_healthy else state.get("aaoi_taiwan_power_last_healthy_kst")
        ),
        "aaoi_taiwan_power_errors": power_source_errors,
        "volantis_verified_baseline": VOLANTIS_VERIFIED_BASELINE,
        "last_checked_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "seen_keys": updated_seen,
        "seen_story_keys": updated_story_keys,
        "seen_story_records": merged_story_records,
        "relevant_item_count": len(deduped),
        "source_errors": errors,
        # The one-time correction is committed only after a Telegram API
        # delivery confirmation (push validation never persists any state).
        "aaoi_power_prior_alert_correction_done": True,
    }
    pending = preserve_delivery_metadata(state, pending)
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # One-time migration: establish the semantic/event baseline silently so the
    # dedupe upgrade itself cannot resend already reported stories.
    if dedupe_version < 2:
        alert_items = []
    else:
        equipment_version = int(state.get("cpo_equipment_version") or 0)
        if equipment_version < 2:
            new_items = [item for item in new_items if item.get("company") != "CPO Equipment Supply Chain"]
        optical_policy_version = int(state.get("optical_policy_version") or 0)
        if optical_policy_version < 1:
            new_items = [item for item in new_items if item.get("company") not in {"US Optical Policy", "AXT"}]
        if optical_policy_version < 2:
            new_items = [item for item in new_items if item.get("company") != "InP Supply Chain"]
        korea_optics_version = int(state.get("korea_optics_version") or 0)
        if korea_optics_version < 1:
            new_items = [item for item in new_items if item.get("company") not in {"Opticore", "OE Solutions"}]
        optical_bottleneck_version = int(state.get("optical_bottleneck_version") or 0)
        if optical_bottleneck_version < 1:
            # Establish the newly added bottleneck branches silently. Only future
            # customer, order, reliability, production, reach or standard changes alert.
            new_items = [
                item for item in new_items
                if item.get("company") not in {
                    "Sungho Electronics / ADST",
                    "POET Technologies",
                    "TFLN Supply Chain",
                    "ELS Connector Supply Chain",
                }
            ]
        optical_packaging_version = int(state.get("optical_packaging_version") or 0)
        if optical_packaging_version < 1:
            # ECOC-era known packaging/test headlines become the baseline silently.
            # Future customer, capacity, yield, shipment, testing-throughput or guidance changes alert.
            new_items = [
                item for item in new_items
                if item.get("company") not in {"Fabrinet", "CPO Packaging & Test"}
            ]
        elif optical_packaging_version < 2:
            # Establish the new package-substrate/interposer branch silently.
            # Future customer, capacity, yield, shipment, thermal/warpage or qualification changes alert.
            new_items = [
                item for item in new_items
                if item.get("category") not in {
                    "CPO 광패키징 기판·양산",
                    "CPO 광패키징 기판·수율·열검증",
                    "CPO 광패키징 기판·인터포저",
                }
            ]
        power_version = int(state.get("aaoi_taiwan_power_watch_version") or 0)
        if power_version < POWER_MONITOR_VERSION or not power_source_healthy:
            # Seed October-2026 EPC press as history; suppress power events
            # during a partial source outage without affecting other watchers.
            new_items = [item for item in new_items if item.get("company") != POWER_COMPANY]
        structural_version = int(state.get("structural_optics_version") or 0)
        if structural_version < STRUCTURAL_OPTICS_VERSION:
            # First upgrade run baselines historical OCP and OPEN NPO coverage.
            # Never send 2025/July-2026 membership or a 2026 COUPE roadmap as
            # a newly-confirmed customer purchase or initial NPO shipment.
            new_items = [
                item for item in new_items
                if item.get("company") not in NEW_STRUCTURE_AXES
            ]
        photonic_compute_version = int(state.get("photonic_compute_version") or 0)
        if photonic_compute_version < 5:
            new_items = [item for item in new_items if item.get("company") not in {"Volantis", "Lightmatter", "Ayar Labs", "Xscape Photonics"}]
        if photonic_compute_version < 6:
            # Baseline currently-known funding/architecture announcements silently.
            # Future customer, silicon, production, or revenue-ramp events remain eligible.
            new_items = [
                item for item in new_items
                if item.get("category") not in {
                    "광메모리 투자·개발자금",
                    "광컴퓨팅 투자·양산확대",
                    "Photonic Fabric 광스케일업",
                }
            ]
        alert_items = new_items[:8] if initialized else []
    if ALERT_PATH.exists():
        ALERT_PATH.unlink()

    for i, first in enumerate(alert_items):
        for second in alert_items[i + 1:]:
            if same_article_identity(first, second):
                raise RuntimeError(
                    "Duplicate article identity reached Telegram alert stage; refusing to send"
                )

    if alert_items:
        policy_only = all(item.get("company") == "US Optical Policy" for item in alert_items)
        korea_optics_only = all(item.get("company") in {"Opticore", "OE Solutions"} for item in alert_items)
        photonic_compute_only = all(item.get("company") in {"Volantis", "Lightmatter", "Ayar Labs", "Xscape Photonics"} for item in alert_items)
        if policy_only:
            alert_header = "🚨 <b>미국 광트랜시버 규제 변화 감지</b>"
        elif korea_optics_only:
            alert_header = "🚨 <b>국내 AI 광통신 수주·검증 변화 감지</b>"
        elif photonic_compute_only:
            alert_header = "🚨 <b>AI 광컴퓨팅·광메모리 구조 변화 감지</b>"
        elif all(item.get("company") == POWER_COMPANY for item in alert_items):
            alert_header = "🚨 <b>AAOI 대만 전력확보·광모듈 증설 변화 감지</b>"
        else:
            alert_header = "🚨 <b>AI 네트워킹·광통신 구조 변화 감지</b>"
        lines = [
            alert_header,
            f"조회시각(KST): {html.escape(dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S'))}",
            f"신규 변화: <b>{len(alert_items)}건</b>",
            "",
        ]
        for idx, item in enumerate(alert_items, 1):
            pub = ""
            if item.get("published"):
                try:
                    pub_dt = dt.datetime.fromisoformat(item["published"]).astimezone(KST)
                    pub = pub_dt.strftime("%Y-%m-%d %H:%M KST")
                except Exception:
                    pub = item["published"]
            category = item["category"]
            lines.extend([
                f"<b>{idx}) {html.escape(DISPLAY_NAMES_KO.get(item['company'], item['company']))} ({html.escape(item['ticker'])}) — {html.escape(category)}</b>",
                f"• 단계: {html.escape(item['stage'])}",
                f"• 확인 수준: {html.escape(evidence_label(item))}" if item['company'] in NEW_STRUCTURE_AXES else (
                    "• 확인 수준: 공급사 공식발표" if official_power_source(item) else
                    "• 확인 수준: 독립 신뢰매체 교차확인·실제 계약조건 재검증 필요"
                ) if item['company'] == POWER_COMPANY else "",
                f"• 원문 제목: {html.escape(item['title'])}",
                f"• 출처·시각: {html.escape(item.get('source') or '미표기')} / {html.escape(pub or '시각 미표기')}",
            ])
            related_categories = []
            for scope in item.get("related_scopes") or []:
                related = str(scope.get("category") or "")
                if related and related != category and related not in related_categories:
                    related_categories.append(related)
            if related_categories:
                lines.append(f"• 연관 감시축: {html.escape(' + '.join(related_categories))}")
            lines.extend([
                f"• 투자 의미: {html.escape(meaning_for(category))}",
                f"• 역풍 확인: {html.escape(risk_for(category))}",
                f"• <a href=\"{html.escape(item['link'], quote=True)}\">원문 링크</a>",
                "",
            ])
        lines.extend([
            "<b>감시 기준</b>",
            "• 고객·수주·양산: 1.6T·3.2T·CPO·광컴퓨팅의 고객인증, PO, 출하, 생산능력, 매출 가이던스 변화",
            "• 병목·정책: FAU·InP·ELS·OCS/NPO 검증, AAOI 대만 전력·SOFC 시운전·검수·출하·허가",
            "• 제외: 전시·데모·단순 주가반응·기존 기사 재탕은 알림하지 않음",
        ])
        ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    # Repair two real misfires from code-push runs during the watcher upgrade:
    # 267 was not an AAOI event; 268 was a baseline EPC announcement, not a
    # verified energized plant or incremental optical production.
    # A correction is operational hygiene, not a newly detected market event.
    correction_due = not bool(state.get("aaoi_power_prior_alert_correction_done"))
    if correction_due:
        correction_lines = [
            "<b>[정정] AI 광통신·AAOI 대만 전력 알림</b>",
            "",
            "• 이전 메시지 267: 중화전신(Chunghwa Telecom) 데이터센터 기사가 AAOI 감시로 잘못 분류됐습니다. AAOI 신규 사업사건으로 취급하지 마십시오.",
            "• 이전 메시지 268: AAOI 대만 사업장·블룸에너지 SOFC의 EPC 추진 보도는 관련 사실이지만, 신규 전원 인가·발전 가동·1.6T 출하가 확인된 사건은 아닙니다.",
            "• 확인된 사실: Leadray Energy가 설계·조달·시공을 맡아 SOFC를 도입하는 사업이며, 2027년 1분기 운전 개시는 목표 일정입니다.",
            "• 아직 미공개: 이 사업장의 정격출력(MW), 계약금액, 보조금 승인액, 가스계통·전원 인가일, 추가 광트랜시버 생산량.",
            "• 개선: 이후 전력 계약→착공→검수→가동→고객별 인증·출하를 분리 검증하고, 코드 변경(push)은 전송 및 감시 기준선 갱신을 하지 않습니다.",
            "• <a href=\"https://technews.tw/2026/10/08/bloom-energy-ai-optical-supply-chain-sofc-gigalight-expands-production/\">대만 현지 보도</a>"
            " / <a href=\"https://appliedoptoelectronics.gcs-web.com/node/17511/html\">AAOI 2026년 2분기 공식 자료</a>",
        ]
        correction_html = "\n".join(correction_lines).strip() + "\n"
        if ALERT_PATH.exists():
            with ALERT_PATH.open("a", encoding="utf-8") as handle:
                handle.write("\n" + correction_html)
        else:
            ALERT_PATH.write_text(correction_html, encoding="utf-8")

    status_lines = [
        "# AI 네트워킹·광통신 감시 상태",
        "",
        f"- 조회시각(KST): {dt.datetime.now(KST).isoformat(timespec='seconds')}",
        f"- 기준선 초기화 여부: {'예' if initialized else '아니오 — 이번 실행은 기준선만 저장'}",
        f"- 관련 신규 사건 후보: {len(new_items)}건",
        f"- Telegram 발송 사건: {len(alert_items)}건",
        f"- 중복 기사 통합 후 사건 기준선: {len(deduped)}건",
        f"- 중복 제거 방식: 동일 원문 URL·제목/출처 통합 + 동일 사건 의미 클러스터 + 사건키 v3",
        f"- FAU·OCS·OPEN NPO 감시 버전: {STRUCTURAL_OPTICS_VERSION} (2025 OCP·2026년 7월 OPEN NPO 기존사건 기준선)",
        f"- AAOI 대만 전력 감시: {'정상' if power_source_healthy else '보류·해당 감시축 기준선 미갱신'}",
        f"- 이전 오탐 정정: {'전송 대기' if correction_due else '기존 송출 확인·중복 발송 금지'}",
        f"- AAOI 대만 전력 최근 정상조회: {pending.get('aaoi_taiwan_power_last_healthy_kst') or '확인되지 않음'}",
        f"- 소스 오류: {len(errors)}건",
    ]
    if errors:
        status_lines.extend(["", "## 소스 오류"] + [f"- {e}" for e in errors])
    STATUS_PATH.write_text("\n".join(status_lines).strip() + "\n", encoding="utf-8")

    print(f"initialized_before={initialized}")
    print(f"relevant={len(deduped)} new={len(new_items)} alert={len(alert_items)} errors={len(errors)}")


if __name__ == "__main__":
    main()
