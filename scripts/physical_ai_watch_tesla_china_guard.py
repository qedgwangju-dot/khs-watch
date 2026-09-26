#!/usr/bin/env python3
"""Tesla Optimus China-supply-chain discovery layer for the existing Physical-AI watcher.

This does not create a new alert system. It extends the currently active watcher so
Chinese first/industry supply-chain reports can surface material Optimus state
changes before Korean/English rewrites appear. The alert unit is the underlying
production/procurement milestone, not a specific article or URL.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html as html_lib
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

import physical_ai_watch_figure_guard as current

base = current.base

_orig_query_news = base.query_news
_orig_topic_group = base.topic_group
_orig_load_state = base.load_state
_orig_score = base.score
_orig_category = base.category
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_key = base.key
_orig_clean_title = base.clean_title

TESLA_CN_SENTINEL = 'DIRECT_TESLA_OPTIMUS_CN_SUPPLY_CHAIN'
JOE_X_SENTINEL = 'DIRECT_JOE_TEGTMEYER_OPTIMUS_SITE_X'
JOE_X_TIMELINE = 'https://syndication.twitter.com/srv/timeline-profile/screen-name/JoeTegtmeyer'
JOE_X_SOURCE = 'Joe Tegtmeyer (X)'
TESLA_APP_X_SENTINEL = 'DIRECT_TESLA_APP_IOS_OPTIMUS_X'
TESLA_APP_X_TIMELINE = 'https://syndication.twitter.com/srv/timeline-profile/screen-name/tesla_app_ios'
TESLA_APP_X_SOURCE = 'Tesla App Updates (X)'
TESLA_GEN3_APK_SENTINEL = 'DIRECT_TESLA_OPTIMUS_GEN3_APK_ASSET_20260923'
TESLA_GEN3_APK_SOURCE = 'Tesla APK 역공학 관측'
TESLA_RAMP_BOTTLENECK_SENTINEL = 'DIRECT_TESLA_OPTIMUS_RAMP_BOTTLENECK_20260925'
TESLA_RAMP_BOTTLENECK_SOURCE = 'The Information'
TESLA_KOREA_SUPPLIER_SENTINEL = 'DIRECT_TESLA_KOREA_SUPPLIER_SCOUTING_20260924'
TESLA_KOREA_SUPPLIER_SOURCE = '한국경제'
MUSK_X_SENTINEL = 'DIRECT_ELON_MUSK_OPTIMUS_X'
MUSK_X_TIMELINE = 'https://syndication.twitter.com/srv/timeline-profile/screen-name/elonmusk'
MUSK_X_SOURCE = 'Elon Musk (X)'

TESLA_OPT = re.compile(r'Tesla|特斯拉|테슬라', re.I)
OPTIMUS = re.compile(r'Optimus|擎天柱|옵티머스', re.I)
TESLA_HUMANOID = re.compile(r'Optimus|擎天柱|옵티머스|人形机器人|humanoid|휴머노이드', re.I)
SCALE_ORDER = re.compile(
    r'(?:约|約|약\s*)?(?:5,?000|5000)\s*(?:台|대)?|数千\s*台|數千\s*台|수천\s*대|千台级|千台級|천\s*단위',
    re.I,
)
ORDER = re.compile(
    r'订单|訂單|下发|下發|采购|採購|批量订单|批量訂單|量产订单|量產訂單|'
    r'order|purchase\s*order|batch\s*order|발주|주문|양산\s*주문',
    re.I,
)
TRIAL = re.compile(r'数百\s*台|數百\s*台|수백\s*대|试产|試產|trial\s*production|pilot\s*order|시험\s*생산', re.I)
AUDIT = re.compile(
    r'审厂|審廠|供应商审核|供應商審核|现场审核|現場審核|走访.{0,16}供应商|走訪.{0,16}供應商|'
    r'supplier\s*audit|factory\s*audit|site\s*audit|공급업체\s*심사|현장\s*심사|공급사\s*실사|'
    r'생산\s*감사|생산\s*심사|양산\s*감사|生产审核|生產審核',
    re.I,
)
AUDIT_STARTED = re.compile(
    r'启动(?:新一轮|新一輪)?.{0,18}(?:审厂|審廠)|开启(?:新一轮|新一輪)?.{0,18}(?:审厂|審廠)|'
    r'开始(?:新一轮|新一輪)?.{0,18}(?:审厂|審廠)|已于.{0,24}(?:开启|啟動|启动).{0,18}(?:审厂|審廠)|'
    r'(?:supplier|factory)\s*audit\s*(?:started|began|launched)|'
    r'공급업체\s*심사\s*(?:시작|개시)|양산\s*심사\s*(?:시작|개시)|'
    r'(?:생산|양산)\s*(?:감사|심사)\s*(?:착수|시작|개시)|(?:生产|生產)(?:审核|審核).{0,8}(?:启动|啟動|开始|開始)',
    re.I,
)
ACTUAL_WEEKLY = re.compile(
    r'(?:实际|實際|当前|當前|目前).{0,18}(?:周产|週產|每周生产|每週生產).{0,14}(?:\d{2,5})\s*台|'
    r'(?:周产|週產|每周生产|每週生產).{0,14}(?:达到|達到|已达|已達|稳定|穩定).{0,10}(?:\d{2,5})\s*台|'
    r'actual\s+weekly\s+production.{0,20}\d{2,5}|producing.{0,20}\d{2,5}.{0,12}(?:per\s+week|weekly)|'
    r'실제\s*주간\s*생산.{0,16}\d{2,5}\s*대|주당\s*실제\s*생산.{0,16}\d{2,5}\s*대',
    re.I,
)
WEEKLY_TARGET = re.compile(
    r'(?:目标|目標|要求|供应能力|供應能力|产能目标|產能目標).{0,28}(?:周产|週產|每周|每週).{0,18}\d{2,5}\s*台|'
    r'weekly\s+(?:target|capacity|run[-\s]*rate\s*target).{0,18}\d{2,5}|'
    r'주당\s*\d{2,5}\s*대분?\s*(?:공급능력|목표)|주간\s*생산\s*목표.{0,16}\d{2,5}\s*대',
    re.I,
)
RAMP = re.compile(
    r'量产|量產|良率|产线|產線|周产|週產|产能|產能|批量供应|批量供應|'
    r'production|yield|production\s*line|weekly\s*production|capacity|mass\s*production|'
    r'양산|수율|생산라인|주간\s*생산|생산능력|대량\s*공급',
    re.I,
)
PRODUCTION_STARTED = re.compile(
    r'正式(?:量产|量產)|开始(?:量产|量產)|開始(?:量产|量產)|启动(?:量产|量產)|啟動(?:量产|量產)|'
    r'started\s+(?:mass\s+)?production|production\s+(?:has\s+)?started|SOP\s+(?:started|began)|'
    r'양산\s*(?:시작|개시|착수)|생산\s*(?:시작|개시)|실제\s*양산\s*(?:시작|개시)',
    re.I,
)
RAMP_TENFOLD = re.compile(r'10\s*배|약\s*10\s*배|ten[- ]?fold|10x|production.{0,30}(?:10x|ten[- ]?fold)|생산.{0,30}10\s*배', re.I)
WEEKLY_HUNDREDS = re.compile(r'주당\s*수백\s*대|주당\s*몇백\s*대|hundreds?\s*(?:of\s*)?(?:robots?|units?)?\s*(?:per|a)\s*week|hundreds?\s*per\s*week', re.I)
YEAR_END_1000 = re.compile(r'(?:연말|year[- ]?end).{0,50}(?:주당\s*)?1,?000\s*대|1,?000\s*(?:robots?|units?)\s*(?:per|a)\s*week.{0,50}(?:year[- ]?end|연말)|주당\s*1,?000\s*대.{0,50}(?:연말|목표)', re.I)
LONG_TERM_20000 = re.compile(r'주당\s*(?:약\s*)?2\s*만\s*대|20,?000\s*(?:robots?|units?)\s*(?:per|a)\s*week|20,?000\s*per\s*week', re.I)
CONTINUOUS_AUTO_LINE = re.compile(r'연속\s*자동화\s*라인|continuous\s*automated\s*line|continuous\s*automation\s*line|fully\s*automated\s*line', re.I)
HAND_ASSEMBLY_BOTTLENECK = re.compile(r'(?:hand|hands|손|forearm|팔뚝|전완).{0,120}(?:100\s*(?:개|plus|more)|100\+|screws?|나사|small\s*parts?|소형\s*부품|manual\s*assembly|수작업)|(?:100\s*(?:개|plus|more)|100\+|screws?|나사|small\s*parts?|소형\s*부품|manual\s*assembly|수작업).{0,120}(?:hand|hands|손|forearm|팔뚝|전완)', re.I)
TACTILE_DURABILITY = re.compile(r'(?:촉각\s*센서|tactile\s*sensor|touch\s*sensor).{0,80}(?:내구성|durability|reliability|문제|issue|failure)|(?:내구성|durability|reliability).{0,80}(?:촉각\s*센서|tactile\s*sensor|touch\s*sensor)', re.I)
SUPPLIER_CONSISTENCY = re.compile(r'(?:중국|China|Chinese).{0,80}(?:supplier|업체|공급사).{0,120}(?:품질|quality|일관성|consistency|수율|yield|규모|volume)|(?:품질|quality|일관성|consistency|수율|yield).{0,120}(?:중국|China|Chinese).{0,80}(?:supplier|업체|공급사)', re.I)
CORE_PARTS = re.compile(r'모터|motor|정밀\s*기어|precision\s*gear|gearbox|감속기|actuator|액추에이터', re.I)
TRAINING_500K = re.compile(r'50\s*만\s*시간|500,?000\s*hours?|500k\s*hours?', re.I)
TRAINING_DOUBLE = re.compile(r'(?:연말|year[- ]?end).{0,50}(?:두\s*배|2\s*배|double)|(?:double|두\s*배|2\s*배).{0,50}(?:연말|year[- ]?end)', re.I)
FIXTURE_REWORK = re.compile(
    r'(?:fixture|jig|지그|보조기구).{0,140}(?:align|alignment|정렬).{0,120}(?:rework|재작업|line|라인)|'
    r'(?:rework|재작업).{0,140}(?:fixture|jig|지그|alignment|정렬)|'
    r'(?:tooling|automated\s+equipment|자동화\s*설비).{0,120}(?:fail|failure|malfunction|오작동|고장).{0,120}(?:rework|재작업|line|라인)',
    re.I,
)
SENSING_GLOVE = re.compile(r'sensing\s*glove|센싱\s*글러브|센싱\s*장갑|감지\s*장갑', re.I)
AI_GENERALIZATION = re.compile(
    r'generaliz|general-purpose|범용화|범용\s*로봇|untrained|unseen\s+(?:task|situation|scenario)|'
    r'미훈련\s*(?:상황|작업|태스크)|예측\s*불가|unpredictable',
    re.I,
)
BASIC_TASK_DAYS = re.compile(
    r'(?:basic|simple)\s+(?:new\s+)?task.{0,60}(?:several|multiple|few)\s+days|'
    r'(?:several|multiple|few)\s+days.{0,60}(?:basic|simple)\s+(?:new\s+)?task|'
    r'(?:기본|단순)\s*(?:작업|태스크).{0,50}(?:수일|며칠)|(?:수일|며칠).{0,50}(?:기본|단순)\s*(?:작업|태스크)',
    re.I,
)
TRAINING_HUBS = re.compile(
    r'(?:training\s+(?:hub|center)|훈련\s*(?:허브|센터)).{0,160}(?:Colorado|Arizona|Florida|콜로라도|애리조나|플로리다)|'
    r'(?:Colorado|Arizona|Florida|콜로라도|애리조나|플로리다).{0,160}(?:training\s+(?:hub|center)|훈련\s*(?:허브|센터))',
    re.I,
)
LEASE_COMMERCIAL = re.compile(
    r'(?:lease|leasing|rent|리스|임대).{0,180}(?:commercial\s+customer|outside\s+customer|warehouse|factory|고객|창고|공장)|'
    r'(?:commercial\s+customer|outside\s+customer|warehouse|factory|고객|창고|공장).{0,180}(?:lease|leasing|rent|리스|임대)',
    re.I,
)
RETRIEVE_UPGRADE_DATA = re.compile(
    r'(?:retrieve|recover|회수).{0,120}(?:upgrade|refurbish|업그레이드|개조|정비)|'
    r'(?:customer|factory|warehouse|고객|공장|창고).{0,160}(?:data\s+collection|collect\s+data|데이터\s*수집).{0,120}(?:AI|improve|개선)',
    re.I,
)
INTERNAL_TEST_USE = re.compile(
    r'(?:internal|inside\s+Tesla|자사|내부).{0,120}(?:test|testing|training|data\s+collection|테스트|훈련|데이터\s*수집)',
    re.I,
)
FACTORY_SITE = re.compile(r'Giga(?:factory)?\\s*Texas|Giga\\s*Texas|기가\\s*텍사스|텍사스.{0,50}Optimus|Optimus.{0,50}(?:Texas|텍사스)|Optimus.{0,40}(?:dedicated\\s*factory|factory)|옵티머스.{0,40}(?:전용\\s*공장|공장)|로봇\\s*기가팩토리', re.I)
FACTORY_STRUCTURE = re.compile(r'steel\\s*(?:assembly|frame|framing)|column\\s*grids?|concrete|rebar|footing|grade[-\\s]*beam|roof\\s*truss|철골|골조|콘크리트|철근|기초|기초보|지붕|상부\\s*\\d+개?\\s*층', re.I)
FACTORY_TOOLING = re.compile(r'tooling|equipment\\s*(?:install|installation|move[-\\s]*in)|production\\s*equipment|장비\\s*(?:반입|설치)|생산\\s*설비\\s*(?:반입|설치)|생산라인\\s*설치', re.I)
APP_CODE_OPTIMUS = re.compile(r'optimus_charger_id|createBaseChargerId_OptimusChargerId|Optimus.{0,20}(?:charger|충전기)|(?:charger|충전기).{0,20}Optimus|옵티머스.{0,20}(?:충전기|charger)|(?:충전기|charger).{0,20}옵티머스|robot_phone_key|robot_home_data_collection', re.I)
APP_HOME_STACK = re.compile(r'Tesla\\s*app|테슬라\\s*앱|app\\s*code|앱\\s*코드|decompil|reverse\\s*engineer|Powerwall|파워월|solar|태양광|home|가정|charger|충전|registration|등록|manage|관리', re.I)
APP_GEN_ASSET = re.compile(r'Optimus\\s*(?:Gen(?:eration)?\\s*)?3|Optimus\\s*Gen\\s*2\\.5|Gen\\s*2\\.5.{0,40}Gen\\s*3|Gen\\s*3.{0,40}Gen\\s*2\\.5|옵티머스\\s*(?:Gen\\s*)?3|Gen\\s*3\\s*(?:이미지|자산|render|asset)|第三代.{0,20}Optimus|Optimus.{0,20}第三代|2\\.5代.{0,30}第三代|第三代.{0,30}2\\.5代', re.I)
APP_APK_CONTEXT = re.compile(r'APK|Android\\s*app|안드로이드\\s*앱|app\\s*asset|image\\s*asset|render|resource|asset\\s*package|4\\.60\\.5[- ]4573|v4\\.60\\.5[- ]4573|安卓.{0,12}(?:App|应用)|应用程序包|数字资产|素材|渲染图|设计.{0,12}(?:泄露|曝光)|泄露.{0,12}设计', re.I)
MUSK_EXEC_ACTOR = re.compile(r'Elon\\s*Musk|일론\\s*머스크|머스크', re.I)
OPTIMUS_V3 = re.compile(r'Optimus\\s*3|옵티머스\\s*3|V3\\s*Optimus|Optimus\\s*V3', re.I)
OPTIMUS_V4 = re.compile(r'Optimus\\s*4|옵티머스\\s*4|V4\\s*Optimus|Optimus\\s*V4', re.I)
EXEC_FINAL_STAGE = re.compile(r'final\\s+stages?|almost\\s+ready|completion|완성\\s*마지막\\s*단계|마지막\\s*단계|거의\\s*완성', re.I)
EXEC_PROD_START = re.compile(r'start\\s+(?:production|manufacturing)|production\\s+(?:will\\s+)?start|begin\\s+(?:production|manufacturing)|생산\\s*(?:시작|개시)|양산\\s*(?:시작|개시)|생산을\\s*시작', re.I)
EXEC_HIGH_VOLUME = re.compile(r'high[-\\s]*volume\\s+production|mass\\s+production|volume\\s+production|대량\\s*생산|대량생산|본격\\s*양산', re.I)
EXEC_DESIGN_CADENCE = re.compile(r'new\\s+robot\\s+design\\s+every\\s+year|improved\\s+robot\\s+design\\s+every\\s+year|매년.{0,20}(?:새로운|개선된).{0,20}로봇.{0,12}(?:디자인|설계)|매년.{0,20}로봇.{0,12}(?:디자인|설계)', re.I)
EXEC_SCALE = re.compile(r'(?:1|one)\\s*million\\s+(?:units|robots).{0,20}(?:a|per)\\s+year|10\\s*million\\s+(?:units|robots).{0,20}(?:a|per)\\s+year|연간\\s*100만\\s*대|연간\\s*1,?000만\\s*대', re.I)
NAMED_OPTIMUS_SUPPLIERS = re.compile(r'拓普集团|Tuopu|三花智控|Sanhua|均胜电子|Joyson', re.I)
NAMED_SUPPLIER_ORDER = re.compile(
    r'已获.{0,16}订单|已经.{0,16}拿到.{0,16}订单|都已经拿到了.{0,20}订单|订单已.{0,12}(?:下发|下達|下达)|'
    r'got.{0,20}(?:Optimus|humanoid).{0,20}order|received.{0,20}(?:Optimus|humanoid).{0,20}order|'
    r'휴머노이드.{0,20}(?:수주|주문).{0,20}(?:확보|받)|수주.{0,20}(?:확보|완료)',
    re.I,
)

KOREA_LOCATIONS = re.compile(r'한국|韓|Korea|South\s*Korea|국내', re.I)
KOREA_SUPPLIER_SCOUT = re.compile(r'공장\s*(?:방문|실사|점검)|생산시설.{0,20}(?:방문|실사|점검)|기술력.{0,20}(?:점검|검토)|공급망.{0,20}(?:점검|검토|다변화)|협의.{0,16}(?:진행|이어)|factory\s*(?:visit|inspection)|production\s*facility.{0,20}(?:visit|review|assessment)|supplier\s*(?:scouting|review|assessment)|supply\s*chain\s*diversif', re.I)
KOREA_COMPONENT_SCOPE = re.compile(r'감속기|모터|센서|액추에이터|정밀\s*가공|reducer|motor|sensor|actuator|precision\s*machining', re.I)
CN_LOCATIONS = re.compile(r'上海|杭州|宁波|寧波|厦门|廈門|상하이|항저우|닝보|샤먼', re.I)
OFFICIAL_CONFIRM = re.compile(r'Tesla\s+(?:said|confirmed|announced)|特斯拉(?:官方|确认|確認|宣布)|테슬라(?:가|는)?\s*(?:공식|확인|발표)', re.I)
LOW_TRUST_COMMUNITY = re.compile(
    r'雪球|xueqiu|CSDN|blog\\.csdn\\.net|财富号|財富號|caifuhao|东方财富号|東方財富號',
    re.I,
)
TESLA_MARKET_REACTION = re.compile(r'A股异动|概念股|集体(?:走强|拉升)|股价|涨停|涨超|上涨|下跌|shares?\\s*(?:jump|rise|surge|fall)|stock\\s*price|market\\s*reaction|板块.{0,12}(?:走强|拉升)', re.I)
TESLA_TITLE_DIRECT_EVENT = re.compile(r'Gen\\s*3|第三代|APK|安卓|设计.{0,10}(?:泄露|曝光)|供应商.{0,10}(?:审核|审厂)|审厂|订单|量产|production|factory|工厂|产线|生产线|韩国|日本|Korea|Japan', re.I)


SOURCE_KO = {
    '新浪财经': '시나재경', '新浪財經': '시나재경', 'finance.sina.com.cn': '시나재경',
    '界面新闻': '제몐뉴스', '界面新聞': '제몐뉴스',
    '21财经': '21세기경제보도', '21財經': '21세기경제보도',
    '21世纪经济报道': '21세기경제보도', '21世紀經濟報道': '21세기경제보도', 'm.21jingji.com': '21세기경제보도',
    '格隆汇': '거룽후이', '格隆匯': '거룽후이',
    '财联社': '차이롄서', '財聯社': '차이롄서', 'www.cls.cn': '차이롄서',
    '证券时报': '증권시보', '證券時報': '증권시보',
    '中国证券报': '중국증권보', '中國證券報': '중국증권보',
    '上海证券报': '상하이증권보', '上海證券報': '상하이증권보', 'paper.cnstock.com': '상하이증권보',
    '观点网': '관점망', '觀點網': '관점망', 'www.guandian.cn': '관점망',
}

if TESLA_CN_SENTINEL not in base.QUERIES:
    base.QUERIES.append(TESLA_CN_SENTINEL)
if JOE_X_SENTINEL not in base.QUERIES:
    base.QUERIES.append(JOE_X_SENTINEL)
if TESLA_APP_X_SENTINEL not in base.QUERIES:
    base.QUERIES.append(TESLA_APP_X_SENTINEL)
if MUSK_X_SENTINEL not in base.QUERIES:
    base.QUERIES.append(MUSK_X_SENTINEL)
_TEXAS_FACTORY_QUERY = '(Tesla OR 테슬라) (Optimus OR 옵티머스) ("Giga Texas" OR "Gigafactory Texas" OR 텍사스) (construction OR factory OR steel OR concrete OR rebar OR 철골 OR 콘크리트 OR 철근 OR 장비설치 OR tooling)'
if _TEXAS_FACTORY_QUERY not in base.QUERIES:
    base.QUERIES.append(_TEXAS_FACTORY_QUERY)
_TESLA_APP_QUERY = '(Tesla OR 테슬라) (Optimus OR 옵티머스) ("app code" OR "앱 코드" OR charger OR 충전기 OR Powerwall OR 파워월 OR "phone key" OR "home integration" OR 가정용)'
if _TESLA_APP_QUERY not in base.QUERIES:
    base.QUERIES.append(_TESLA_APP_QUERY)
if TESLA_GEN3_APK_SENTINEL not in base.QUERIES:
    base.QUERIES.append(TESLA_GEN3_APK_SENTINEL)
_TESLA_GEN3_APK_QUERY = '(Tesla OR 테슬라) (Optimus OR 옵티머스) ("Gen 3" OR "Gen 2.5") (APK OR "Android app" OR asset OR render OR image)'
if _TESLA_GEN3_APK_QUERY not in base.QUERIES:
    base.QUERIES.append(_TESLA_GEN3_APK_QUERY)
for _q in ['"Optimus chargers" Tesla app', '"optimus_charger_id" Tesla', '"createBaseChargerId_OptimusChargerId"']:
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)
_NAMED_SUPPLIER_ORDER_QUERY = '(Tesla OR 特斯拉 OR 테슬라) (Optimus OR 擎天柱 OR 휴머노이드) (拓普集团 OR Tuopu OR 三花智控 OR Sanhua OR 均胜电子 OR Joyson) (订单 OR order OR 审厂 OR supplier audit OR 量产 OR mass production)'
if _NAMED_SUPPLIER_ORDER_QUERY not in base.QUERIES:
    base.QUERIES.append(_NAMED_SUPPLIER_ORDER_QUERY)
if TESLA_KOREA_SUPPLIER_SENTINEL not in base.QUERIES:
    base.QUERIES.append(TESLA_KOREA_SUPPLIER_SENTINEL)
_TESLA_KOREA_SUPPLIER_QUERY = '(Tesla OR 테슬라) (Optimus OR 옵티머스 OR humanoid OR 휴머노이드) (한국 OR 국내 OR Korea) (공장 방문 OR 생산시설 점검 OR 공급망 OR supplier OR factory visit OR actuator OR 감속기 OR 센서)'
if _TESLA_KOREA_SUPPLIER_QUERY not in base.QUERIES:
    base.QUERIES.append(_TESLA_KOREA_SUPPLIER_QUERY)
_TESLA_RAMP_BOTTLENECK_QUERY = '(Tesla OR 테슬라) (Optimus OR 옵티머스) ("hundreds per week" OR "주당 수백 대" OR "10x" OR "10배" OR "1,000 per week" OR "20,000 per week" OR hand OR 손 OR forearm OR 전완 OR tactile OR 촉각 OR "sensing glove" OR fixture OR jig OR rework OR 재작업 OR generalization OR "several days" OR lease OR 리스 OR "training hub" OR 훈련허브) ("The Information" OR Electrek OR production OR 생산 OR supply chain OR 공급망)'
if _TESLA_RAMP_BOTTLENECK_QUERY not in base.QUERIES:
    base.QUERIES.append(_TESLA_RAMP_BOTTLENECK_QUERY)
if TESLA_RAMP_BOTTLENECK_SENTINEL not in base.QUERIES:
    base.QUERIES.append(TESLA_RAMP_BOTTLENECK_SENTINEL)
_TESLA_TRAINING_DATA_QUERY = '(Tesla OR 테슬라) (Optimus OR 옵티머스) ("500,000 hours" OR "500k hours" OR "50만 시간" OR training data OR 학습 데이터) (year-end OR 연말 OR double OR 두배)'
if _TESLA_TRAINING_DATA_QUERY not in base.QUERIES:
    base.QUERIES.append(_TESLA_TRAINING_DATA_QUERY)
_FACTORY_MILESTONE_QUERY = '(Tesla OR 테슬라) (Optimus OR 옵티머스) ("dedicated factory" OR "Optimus factory" OR "옵티머스 전용 공장" OR "로봇 기가팩토리") (steel OR concrete OR rebar OR 철골 OR 콘크리트 OR 철근 OR construction OR 공사)'
if _FACTORY_MILESTONE_QUERY not in base.QUERIES:
    base.QUERIES.append(_FACTORY_MILESTONE_QUERY)
for _q in [
    '("Elon Musk" OR "일론 머스크") ("Optimus 3" OR "Optimus 4" OR 옵티머스) (production OR manufacturing OR "high volume" OR "mass production" OR design OR 생산 OR 양산 OR 대량생산 OR 디자인)',
    '("Elon Musk" OR "일론 머스크") Optimus (podcast OR interview OR summit OR webcast OR earnings OR 팟캐스트 OR 인터뷰 OR 서밋 OR 실적발표)',
    '(Tesla OR 테슬라) ("Optimus 3" OR "Optimus 4") (summer OR 2026 OR 2027 OR 2028 OR million OR "대량 생산" OR "생산 시작")',
]:
    if _q not in base.QUERIES:
        base.QUERIES.append(_q)
base.TRUSTED.update({
    '시나재경', '제몐뉴스', '21세기경제보도', '거룽후이', '차이롄서',
    '증권시보', '중국증권보', '상하이증권보', 'Tesla Telemetry', '第一财经', '펑파이신문', '澎湃新闻', 'The Paper',
    'Moonshots with Peter Diamandis', 'Peter H. Diamandis', 'Dwarkesh Podcast', 'All-In Podcast',
    '한국경제', 'Hankyung', 'The Information', 'Electrek', 'Investing.com',
})
base.OFFICIAL_OR_PRIMARY.add(MUSK_X_SOURCE)



def _is_exec_guidance(text: str) -> bool:
    if not (MUSK_EXEC_ACTOR.search(text) and OPTIMUS.search(text)):
        return False
    return bool(
        EXEC_FINAL_STAGE.search(text)
        or EXEC_PROD_START.search(text)
        or EXEC_HIGH_VOLUME.search(text)
        or (OPTIMUS_V4.search(text) and re.search(r'design|디자인|설계|release|출시', text, re.I))
        or EXEC_DESIGN_CADENCE.search(text)
        or EXEC_SCALE.search(text)
    )


def _exec_signature(text: str) -> str:
    tags = []
    tests = [
        ('v3-final', OPTIMUS_V3.search(text) and EXEC_FINAL_STAGE.search(text)),
        ('v3-production-start', OPTIMUS_V3.search(text) and EXEC_PROD_START.search(text)),
        ('v3-high-volume', OPTIMUS_V3.search(text) and EXEC_HIGH_VOLUME.search(text)),
        ('v4-design', OPTIMUS_V4.search(text) and re.search(r'design|디자인|설계|release|출시', text, re.I)),
        ('annual-design-cadence', EXEC_DESIGN_CADENCE.search(text)),
        ('scale-million', EXEC_SCALE.search(text)),
    ]
    for name, matched in tests:
        if matched:
            tags.append(name)

    temporal_patterns = [
        ('this-summer', r'this\s+summer|올\s*여름|이번\s*여름'),
        ('next-summer', r'next\s+summer|내년\s*여름'),
        ('next-year', r'next\s+year|내년'),
        ('mid-year', r'mid(?:dle)?\s+of\s+(?:this|next)\s+year|연중|중반'),
        ('year-2026', r'\b2026\b|2026년'),
        ('year-2027', r'\b2027\b|2027년'),
        ('year-2028', r'\b2028\b|2028년'),
    ]
    for name, pat in temporal_patterns:
        if re.search(pat, text, re.I):
            tags.append(name)

    months = re.findall(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b|\b\d{1,2}월\b', text, re.I)
    tags.extend(f'month-{m.lower()}' for m in months[:2])
    return '|'.join(sorted(set(tags))) or 'generic-exec-guidance'


def _exec_key(text: str) -> str:
    return hashlib.sha256(f'tesla-optimus|musk-exec-guidance|{_exec_signature(text)}'.encode()).hexdigest()


_MARCH_18_2026_MUSK_OPTIMUS_TEXT = (
    'Elon Musk Optimus 3 final stages start production this summer very slow at first '
    'high-volume production around summer next year Optimus 4 design next year '
    'new improved robot design every year'
)
_MARCH_18_2026_MUSK_OPTIMUS_KEY = '571c83f2d14deb01adca23481291d4fb41d2c61abca1463e75e6da6edb73b330'


def load_state() -> dict:
    state = _orig_load_state()
    seen = list(state.get('seen', []))
    # Historical baseline: this guidance was given at the Mar. 18, 2026 Abundance Summit.
    # Seed it so a September rewrite of the same old quote is not mislabeled as a new event.
    if _MARCH_18_2026_MUSK_OPTIMUS_KEY not in seen:
        seen.append(_MARCH_18_2026_MUSK_OPTIMUS_KEY)
    state['seen'] = seen[-3500:]
    return state


def topic_group(text: str) -> str | None:
    if _is_exec_guidance(text):
        return 'tesla'
    if TESLA_OPT.search(text) and KOREA_LOCATIONS.search(text) and KOREA_SUPPLIER_SCOUT.search(text) and KOREA_COMPONENT_SCOPE.search(text):
        return 'tesla'
    if TESLA_OPT.search(text) and TESLA_HUMANOID.search(text) and NAMED_OPTIMUS_SUPPLIERS.search(text) and NAMED_SUPPLIER_ORDER.search(text) and AUDIT.search(text):
        return 'tesla'
    return _orig_topic_group(text)


def _query_cn_once(query: str) -> list[dict]:
    params = urllib.parse.urlencode({'q': query, 'hl': 'zh-CN', 'gl': 'CN', 'ceid': 'CN:zh-Hans'})
    root = ET.fromstring(base.fetch(f'https://news.google.com/rss/search?{params}'))
    out: list[dict] = []
    for node in root.findall('./channel/item')[:60]:
        title = base.norm(node.findtext('title'))
        link = base.norm(node.findtext('link'))
        desc = base.norm(node.findtext('description'))
        pub = base.parse_date(node.findtext('pubDate'))
        src_node = node.find('source')
        src = base.norm(src_node.text if src_node is not None else '')
        src = SOURCE_KO.get(src, src)
        if title and link:
            out.append({
                'title': title,
                'link': link,
                'description': desc,
                'published': pub.isoformat() if pub else None,
                'source': src,
                'cn_supply_chain': True,
            })
    return out


def _query_tesla_cn_supply_chain() -> list[dict]:
    queries = [
        '特斯拉 Optimus (5000台 OR 数千台 OR 千台级 OR 批量订单 OR 量产订单 OR 供应商订单)',
        '特斯拉 Optimus (审厂 OR 供应商审核 OR 现场审核 OR 走访供应商 OR 启动审厂 OR 开启审厂 OR 量产审厂 OR 上海 OR 杭州 OR 宁波 OR 厦门)',
        '特斯拉 Optimus (实际周产 OR 周产量达到 OR 当前周产 OR 良率 OR 周产 OR 产线 OR 量产 OR 产能) (供应商 OR 订单 OR 审厂 OR 产量)',
        '特斯拉 Optimus ("实际周产" OR "周产达到" OR "每周生产" OR "供应能力" OR "产能目标")',
    ]
    merged: dict[str, dict] = {}
    for q in queries:
        for item in _query_cn_once(q):
            signature = f"{item.get('title','')}|{item.get('source','')}"
            merged[signature] = item
    return list(merged.values())


def _query_korea_supplier_recovery() -> list[dict]:
    published = dt.datetime(2026, 9, 24, 0, 30, tzinfo=dt.timezone.utc)
    if base.NOW - published > dt.timedelta(hours=120):
        return []
    return [{
        'title': '테슬라, 한국 로봇 부품 공급망 생산시설·기술력 점검 보도',
        'link': 'https://www.hankyung.com/article/202609233829i',
        'description': (
            'Tesla reportedly visited several South Korean robot-component companies in the first half of 2026 to review production facilities and technical capabilities. '
            'The search covers reducers, motors, sensors, actuators and precision-machined parts as Tesla prepares Optimus Gen 3 mass production and seeks to diversify beyond China. '
            'No Korean company has yet been officially named as an Optimus supplier; discussions are ongoing.'
        ),
        'published': published.isoformat(),
        'source': TESLA_KOREA_SUPPLIER_SOURCE,
        'korea_supplier_scouting': True,
    }]


_TESLA_NAMED_SUPPLIER_RECOVERY = 'DIRECT_TESLA_NAMED_SUPPLIER_ORDER_20260921'
if _TESLA_NAMED_SUPPLIER_RECOVERY not in base.QUERIES:
    base.QUERIES.append(_TESLA_NAMED_SUPPLIER_RECOVERY)

def _query_named_supplier_recovery() -> list[dict]:
    published = dt.datetime(2026, 9, 21, 1, 58, tzinfo=dt.timezone.utc)
    if base.NOW - published > dt.timedelta(hours=120):
        return []
    text = (
        '特斯拉机器人团队上周已在拓普集团、三花智控、均胜电子等长三角供应链企业开启审厂。'
        '产业链人士称，这些企业在本次审厂前都已经拿到特斯拉Optimus人形机器人订单，只是供应规模不同；'
        '审厂将评估相关产线质量与合规，通过后将很快开始生产。'
    )
    return [{
        'title': '特斯拉机器人团队在长三角审厂，多家企业已获订单',
        'link': 'https://www.yicai.com/news/103371779.html',
        'description': text,
        'published': published.isoformat(),
        'source': '第一财经',
        'named_supplier_order_recovery': True,
    }]

_JOE_FACTORY_RECOVERY_POSTS = {
    '2100597451396719051': (
        'Tesla Optimus dedicated factory at Giga Texas construction update: steel framing is advancing, '
        'upper floors show concrete placement and rebar work, with additional high-bay production space under construction.'
    ),
}


def _make_joe_factory_item(status_id: str, text: str, published: dt.datetime | None) -> dict | None:
    text = base.norm(text)
    if published is None:
        try:
            ms = (int(status_id) >> 22) + 1288834974657
            published = dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
        except Exception:
            return None
    cutoff = base.NOW - dt.timedelta(hours=120)
    if not status_id or not text or published < cutoff or published > base.NOW + dt.timedelta(minutes=10):
        return None
    if not (OPTIMUS.search(text) and FACTORY_SITE.search(text) and (FACTORY_STRUCTURE.search(text) or FACTORY_TOOLING.search(text))):
        return None
    return {
        'title': '테슬라 옵티머스 Giga Texas 전용공장 현장 공정 신규 진척',
        'link': f'https://x.com/JoeTegtmeyer/status/{status_id}',
        'description': text,
        'published': published.isoformat(),
        'source': JOE_X_SOURCE,
        'x_status_id': status_id,
        'direct_site_observation': True,
    }


def _query_joe_x() -> list[dict]:
    gathered: dict[str, dict] = {}
    try:
        raw = base.fetch(JOE_X_TIMELINE).decode('utf-8', errors='ignore')
        m = re.search(r"<script[^>]+id=['\"]__NEXT_DATA__['\"][^>]*>(.*?)</script>", raw, re.I | re.S)
        if m:
            payload = json.loads(html_lib.unescape(m.group(1)))
            entries = payload.get('props', {}).get('pageProps', {}).get('timeline', {}).get('entries', [])
            for entry in entries:
                tweet = (entry.get('content') or {}).get('tweet') or {}
                user = tweet.get('user') or {}
                if str(user.get('screen_name') or '').lower() != 'joetegtmeyer':
                    continue
                status_id = str(tweet.get('id_str') or tweet.get('id') or '').strip()
                text = str(tweet.get('full_text') or tweet.get('text') or '')
                item = _make_joe_factory_item(status_id, text, base.parse_date(tweet.get('created_at')))
                if item:
                    gathered[status_id] = item
    except Exception:
        pass

    for status_id, text in _JOE_FACTORY_RECOVERY_POSTS.items():
        item = _make_joe_factory_item(status_id, text, None)
        if item:
            gathered.setdefault(status_id, item)
    return list(gathered.values())


_TESLA_GEN3_APK_RECOVERY_POSTS = {
    '2102661891957162092': (
        'Tesla Android app APK v4.60.5-4573 contains Optimus Gen 2.5 and Gen 3 image assets according to third-party reverse engineering. '
        'The assets use Gen 3 naming and show a different silhouette/proportion, but this is not a Tesla public product announcement and does not prove the final production design.'
    ),
}


def _make_gen3_apk_item(status_id: str, text: str, published: dt.datetime | None) -> dict | None:
    text = base.norm(text)
    if published is None:
        published = _x_time_from_id(status_id)
    cutoff = base.NOW - dt.timedelta(hours=120)
    if not status_id or not text or published is None or published < cutoff or published > base.NOW + dt.timedelta(minutes=10):
        return None
    if not (TESLA_OPT.search(text) and OPTIMUS.search(text) and APP_GEN_ASSET.search(text) and APP_APK_CONTEXT.search(text)):
        return None
    return {
        'title': '테슬라 앱 APK서 Optimus Gen 3 디자인 자산 발견',
        'link': f'https://x.com/tslaming/status/{status_id}',
        'description': text,
        'published': published.isoformat(),
        'source': TESLA_GEN3_APK_SOURCE,
        'x_status_id': status_id,
        'apk_asset_observation': True,
    }


def _query_gen3_apk_recovery() -> list[dict]:
    out = []
    for status_id, text in _TESLA_GEN3_APK_RECOVERY_POSTS.items():
        item = _make_gen3_apk_item(status_id, text, None)
        if item:
            out.append(item)
    return out


_TESLA_APP_RECOVERY_POSTS = {
    '2101086846159618326': (
        'Tesla app code shows optimus_charger_id and createBaseChargerId_OptimusChargerId. '
        'Optimus charger registration/management appears alongside home energy products such as Powerwall and solar.'
    ),
}


def _x_time_from_id(status_id: str) -> dt.datetime | None:
    try:
        ms = (int(status_id) >> 22) + 1288834974657
        return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
    except Exception:
        return None


def _make_tesla_app_item(status_id: str, text: str, published: dt.datetime | None) -> dict | None:
    text = base.norm(text)
    if not status_id or not text or not APP_CODE_OPTIMUS.search(text):
        return None
    if published is None:
        published = _x_time_from_id(status_id)
    cutoff = base.NOW - dt.timedelta(hours=120)
    if published is None or published < cutoff or published > base.NOW + dt.timedelta(minutes=10):
        return None
    return {
        'title': '테슬라 앱 코드, Optimus 충전기·가정용 기기 통합 준비 정황 포착',
        'link': f'https://x.com/tesla_app_ios/status/{status_id}',
        'description': text,
        'published': published.isoformat(),
        'source': TESLA_APP_X_SOURCE,
        'x_status_id': status_id,
        'app_code_observation': True,
    }


def _query_tesla_app_x() -> list[dict]:
    """Directly watch @tesla_app_ios; keep a short-lived recovery for a missed fresh post."""
    gathered: dict[str, dict] = {}
    try:
        raw = base.fetch(TESLA_APP_X_TIMELINE).decode('utf-8', errors='ignore')
        m = re.search(r"<script[^>]+id=['\"]__NEXT_DATA__['\"][^>]*>(.*?)</script>", raw, re.I | re.S)
        if m:
            payload = json.loads(html_lib.unescape(m.group(1)))
            entries = payload.get('props', {}).get('pageProps', {}).get('timeline', {}).get('entries', [])
            for entry in entries:
                tweet = (entry.get('content') or {}).get('tweet') or {}
                user = tweet.get('user') or {}
                if str(user.get('screen_name') or '').lower() != 'tesla_app_ios':
                    continue
                status_id = str(tweet.get('id_str') or tweet.get('id') or '').strip()
                text = str(tweet.get('full_text') or tweet.get('text') or '')
                item = _make_tesla_app_item(status_id, text, base.parse_date(tweet.get('created_at')))
                if item:
                    gathered[status_id] = item
    except Exception:
        pass

    # Short-lived recovery for the specific fresh post that exposed this source gap.
    # Snowflake time automatically expires it after 120h; it is not a permanent backfill rule.
    for status_id, text in _TESLA_APP_RECOVERY_POSTS.items():
        item = _make_tesla_app_item(status_id, text, _x_time_from_id(status_id))
        if item:
            gathered.setdefault(status_id, item)
    return list(gathered.values())



def _query_elon_x() -> list[dict]:
    try:
        raw = base.fetch(MUSK_X_TIMELINE).decode('utf-8', errors='ignore')
        m = re.search(r"<script[^>]+id=['\"]__NEXT_DATA__['\"][^>]*>(.*?)</script>", raw, re.I | re.S)
        if not m:
            return []
        payload = json.loads(html_lib.unescape(m.group(1)))
        entries = payload.get('props', {}).get('pageProps', {}).get('timeline', {}).get('entries', [])
        out = []
        cutoff = base.NOW - dt.timedelta(hours=120)
        for entry in entries:
            tweet = (entry.get('content') or {}).get('tweet') or {}
            user = tweet.get('user') or {}
            if str(user.get('screen_name') or '').lower() != 'elonmusk':
                continue
            status_id = str(tweet.get('id_str') or tweet.get('id') or '').strip()
            text = base.norm(str(tweet.get('full_text') or tweet.get('text') or ''))
            published = base.parse_date(tweet.get('created_at'))
            if not status_id or not text or not published or published < cutoff:
                continue
            if not (OPTIMUS.search(text) and (EXEC_PROD_START.search(text) or EXEC_HIGH_VOLUME.search(text) or EXEC_DESIGN_CADENCE.search(text) or EXEC_SCALE.search(text) or EXEC_FINAL_STAGE.search(text))):
                continue
            out.append({
                'title': '일론 머스크, Optimus 생산·세대 전환 시간표 신규 언급',
                'link': f'https://x.com/elonmusk/status/{status_id}',
                'description': f'Elon Musk {text}',
                'published': published.isoformat(),
                'source': MUSK_X_SOURCE,
                'x_status_id': status_id,
                'direct_exec_statement': True,
            })
        return out
    except Exception:
        return []


def _query_ramp_bottleneck_recovery() -> list[dict]:
    # Short-lived recovery for the fresh The Information report surfaced by the user.
    # Exact weekly-output/training-data figures are source-reported and remain Tesla-unconfirmed.
    published = dt.datetime(2026, 9, 25, 10, 0, tzinfo=dt.timezone.utc)
    if base.NOW - published > dt.timedelta(hours=120):
        return []
    return [{
        'title': '테슬라 Optimus 생산 확대…손 조립·촉각센서·공급망 병목 보도',
        'link': 'https://www.theinformation.com/articles/elon-musk-preps-teslas-optimus-prime-time-big-hurdles-remain',
        'description': (
            'The Information sources report Tesla increased Optimus production about 10x in recent months to hundreds of units per week. '
            'Tesla is targeting a continuous automated line above 1,000 units per week by year-end and has discussed a long-term target near 20,000 per week. '
            'Hands and forearms remain a bottleneck: more than 100 screws and small parts keep assembly labor-intensive. '
            'Fixtures at hand, joint and electronics-test stations can misalign tighter-tolerance parts, causing line-off rework, while some automated equipment fails at higher speed. '
            'Touch-sensor reliability remains a concern; Tesla reportedly plans a replaceable sensing glove next year so sensors can be serviced without replacing the whole hand. '
            'Motors and precision gears sourced largely from external Chinese suppliers show quality and consistency problems as volumes rise from prototype to mass production. '
            'The report also says Tesla has accumulated more than 500,000 hours of Optimus training data and aims to roughly double it by year-end, with training hubs in Colorado, Arizona and Florida. '
            'Optimus still takes several days to learn some basic tasks and can behave unpredictably in untrained situations, so most current V3 units remain inside Tesla for testing, training and data collection. '
            'Initial external commercialization is reportedly planned as leasing to a small set of factory or warehouse customers similar to Tesla, allowing hardware retrieval, upgrades or refurbishment and continued AI data collection.'
        ),
        'published': published.isoformat(),
        'source': TESLA_RAMP_BOTTLENECK_SOURCE,
        'source_reported_unconfirmed': True,
    }]


def query_news(q: str) -> list[dict]:
    if q == TESLA_RAMP_BOTTLENECK_SENTINEL:
        return _query_ramp_bottleneck_recovery()
    if q == TESLA_KOREA_SUPPLIER_SENTINEL:
        return _query_korea_supplier_recovery()
    if q == TESLA_GEN3_APK_SENTINEL:
        return _query_gen3_apk_recovery()
    if q == TESLA_CN_SENTINEL:
        return _query_tesla_cn_supply_chain()
    if q == _TESLA_NAMED_SUPPLIER_RECOVERY:
        return _query_named_supplier_recovery()
    if q == JOE_X_SENTINEL:
        return _query_joe_x()
    if q == TESLA_APP_X_SENTINEL:
        return _query_tesla_app_x()
    if q == MUSK_X_SENTINEL:
        return _query_elon_x()
    return _orig_query_news(q)


def _is_tesla_supply_text(text: str) -> bool:
    factory = FACTORY_SITE.search(text) and (FACTORY_STRUCTURE.search(text) or FACTORY_TOOLING.search(text))
    app_productization = APP_CODE_OPTIMUS.search(text) and APP_HOME_STACK.search(text)
    gen3_asset = APP_GEN_ASSET.search(text) and APP_APK_CONTEXT.search(text)
    korea_scout = KOREA_LOCATIONS.search(text) and KOREA_SUPPLIER_SCOUT.search(text) and KOREA_COMPONENT_SCOPE.search(text)
    ramp_bottleneck = _is_ramp_bottleneck_event(text)
    exec_guidance = _is_exec_guidance(text)
    actor = TESLA_OPT.search(text) or MUSK_EXEC_ACTOR.search(text)
    robot_term = OPTIMUS.search(text) or (TESLA_OPT.search(text) and TESLA_HUMANOID.search(text))
    return bool(
        actor
        and (
            korea_scout
            or (
                robot_term
                and (
                    ORDER.search(text)
                    or AUDIT.search(text)
                    or RAMP.search(text)
                    or factory
                    or app_productization
                    or gen3_asset
                    or ramp_bottleneck
                    or exec_guidance
                )
            )
        )
    )


def _is_ramp_bottleneck_event(text: str) -> bool:
    ramp = bool(RAMP_TENFOLD.search(text) or WEEKLY_HUNDREDS.search(text) or YEAR_END_1000.search(text) or LONG_TERM_20000.search(text))
    hand = bool(HAND_ASSEMBLY_BOTTLENECK.search(text) or TACTILE_DURABILITY.search(text) or SENSING_GLOVE.search(text))
    process = bool(FIXTURE_REWORK.search(text))
    supply = bool(SUPPLIER_CONSISTENCY.search(text) and CORE_PARTS.search(text))
    data = bool(TRAINING_500K.search(text) and TRAINING_DOUBLE.search(text))
    ai = bool(AI_GENERALIZATION.search(text) or BASIC_TASK_DAYS.search(text) or TRAINING_HUBS.search(text))
    commercial = bool(LEASE_COMMERCIAL.search(text) or RETRIEVE_UPGRADE_DATA.search(text) or INTERNAL_TEST_USE.search(text))
    return bool(ramp and (hand or process or supply or CONTINUOUS_AUTO_LINE.search(text) or data or ai or commercial))


def _stage(text: str) -> str:
    scaled = bool(SCALE_ORDER.search(text) and ORDER.search(text))
    actual_weekly = bool(ACTUAL_WEEKLY.search(text))
    weekly_target = bool(WEEKLY_TARGET.search(text))
    audit_started = bool(AUDIT_STARTED.search(text))
    if actual_weekly:
        return 'actual_weekly_production'
    if _is_exec_guidance(text):
        return 'executive_production_timeline'
    if weekly_target:
        return 'weekly_capacity_target'
    if _is_ramp_bottleneck_event(text):
        return 'production_ramp_bottleneck'
    if PRODUCTION_STARTED.search(text):
        return 'production_started'
    if APP_GEN_ASSET.search(text) and APP_APK_CONTEXT.search(text):
        return 'app_generation_asset'
    if APP_CODE_OPTIMUS.search(text) and APP_HOME_STACK.search(text):
        return 'home_app_integration'
    if KOREA_LOCATIONS.search(text) and KOREA_SUPPLIER_SCOUT.search(text) and KOREA_COMPONENT_SCOPE.search(text):
        return 'korea_supplier_scouting'
    if NAMED_OPTIMUS_SUPPLIERS.search(text) and NAMED_SUPPLIER_ORDER.search(text) and AUDIT.search(text):
        return 'named_supplier_orders_audit'
    if FACTORY_SITE.search(text) and FACTORY_TOOLING.search(text):
        return 'factory_tooling'
    if FACTORY_SITE.search(text) and FACTORY_STRUCTURE.search(text):
        return 'factory_structure'
    audit = bool(AUDIT.search(text))
    if audit_started:
        return 'supplier_audit_started'
    if scaled and audit:
        return 'scale_order_audit'
    if scaled:
        return 'scale_order'
    if audit:
        return 'supplier_audit'
    if RAMP.search(text):
        return 'production_ramp'
    return ''


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    title = item.get('title','')
    # Price/sector reaction articles are never the alert unit. Even when they
    # restate a real audit/order milestone, the underlying operating source must
    # surface separately; otherwise one old event can re-alert whenever stocks move.
    if TESLA_MARKET_REACTION.search(title):
        return 0
    s = _orig_score(item)
    if not _is_tesla_supply_text(text):
        # Generic Tesla/Optimus rewrites must not alert just because they contain
        # high-signal words. If none of the explicit state classifiers match,
        # keep the story as discovery-only and wait for a real state transition.
        if _orig_topic_group(text) == 'tesla':
            return 0
        return s
    source = item.get('source') or ''
    # Investor-community/aggregator posts are useful discovery leads but are not
    # promoted to high-signal on their own. Wait for a trusted/official corroboration.
    if LOW_TRUST_COMMUNITY.search(source):
        return 0
    s = max(s, 18)
    stage = _stage(text)
    if not stage:
        return 0
    if stage == 'executive_production_timeline':
        s += 16
    if stage in {'scale_order', 'scale_order_audit'}:
        s += 10
    if stage in {'supplier_audit', 'scale_order_audit'}:
        s += 8
    if stage == 'supplier_audit_started':
        s += 12
    if stage == 'actual_weekly_production':
        s += 15
    if stage == 'weekly_capacity_target':
        s += 6
    if stage == 'production_ramp_bottleneck':
        s += 18
    if stage == 'production_started':
        s += 12
    if stage == 'app_generation_asset':
        s += 14
    if stage == 'home_app_integration':
        s += 12
    if stage == 'korea_supplier_scouting':
        s += 14
    if stage == 'named_supplier_orders_audit':
        s += 16
    if stage == 'factory_structure':
        s += 12
    if stage == 'factory_tooling':
        s += 14
    if stage == 'production_ramp':
        # "almost mass production / ramping soon" without a hard new milestone
        # is background commentary, not a new state change.
        return 0
    if TRIAL.search(text):
        s += 4
    if CN_LOCATIONS.search(text):
        s += 3
    if RAMP.search(text):
        s += 5
    if item.get('source') in base.TRUSTED:
        s += 3
    return s


def category(text: str, group: str) -> str:
    if group == 'tesla' and _is_tesla_supply_text(text):
        stage = _stage(text)
        if stage == 'actual_weekly_production':
            return 'Optimus 실제 주간 완제품 생산량'
        if stage == 'executive_production_timeline':
            return 'Optimus 경영진 양산 시간표·세대 전환'
        if stage == 'weekly_capacity_target':
            return 'Optimus 주간 공급능력·생산 목표'
        if stage == 'production_ramp_bottleneck':
            return 'Optimus 주간 생산 램프·손·공급망 병목'
        if stage == 'production_started':
            return 'Optimus 실제 양산 개시'
        if stage == 'app_generation_asset':
            return 'Optimus Gen 3 앱 자산·세대 디자인 준비'
        if stage == 'home_app_integration':
            return 'Optimus 가정용 앱·충전 인프라 준비'
        if stage == 'korea_supplier_scouting':
            return 'Optimus 한국 공급망 생산시설·기술 점검'
        if stage == 'named_supplier_orders_audit':
            return 'Optimus 실명 공급사 주문·양산심사'
        if stage == 'factory_structure':
            return 'Optimus Giga Texas 전용공장 구조공사 진척'
        if stage == 'factory_tooling':
            return 'Optimus Giga Texas 생산설비 반입·설치'
        if stage == 'scale_order_audit':
            return 'Optimus 천 단위 발주·공급업체 심사'
        if stage == 'scale_order':
            return 'Optimus 천 단위 양산 발주'
        if stage == 'supplier_audit_started':
            return 'Optimus 공급업체 양산 심사 실제 개시'
        if stage == 'supplier_audit':
            return 'Optimus 공급업체 심사·양산 준비'
        if stage == 'production_ramp':
            return 'Optimus 생산라인·수율 램프업'
    return _orig_category(text, group)


def meaning(cat: str) -> str:
    if cat == 'Optimus 실제 주간 완제품 생산량':
        return ('옵티머스가 공급망 목표나 부품 발주가 아니라 실제 완제품 주간 생산량으로 넘어갔는지를 보는 최상위 양산 신호입니다. '
                '주당 생산량·수율·완성품 출하·내부 배치 대수를 분리해 확인하고, 이전 목표 대비 실제 달성률을 계산합니다.')
    if cat == 'Optimus 경영진 양산 시간표·세대 전환':
        return ('일론 머스크가 Optimus 세대별 설계 완료·생산 시작·대량생산 시점을 직접 제시하면 양산 시간표를 바꾸는 1차 경영진 신호로 봅니다. '
                '발언 시간표를 실제 생산라인 설치→첫 생산→주간 생산량→수율→대량생산 도달과 연결해 추적합니다.')
    if cat == 'Optimus 주간 공급능력·생산 목표':
        return ('주당 몇 대분을 공급할 수 있어야 하는지 또는 생산 목표가 얼마인지 보여주는 선행 시간표 신호입니다. '
                '실제 완제품 생산량과 혼동하지 않고 목표→실생산 전환 시점을 별도 추적합니다.')
    if cat == 'Optimus 주간 생산 램프·손·공급망 병목':
        return ('단순 양산 예정이 아니라 실제 생산량이 주당 수백 대 수준으로 올라갔다는 보도와 동시에 손·전완 수작업, 지그 정렬 불량에 따른 재작업, 촉각센서 신뢰성, 중국 핵심부품 공급사 품질 일관성, AI 범용화가 함께 병목으로 드러나는 신호입니다. '
                '현재 생산량→연말 주당 1,000대 자동화라인 목표→장기 주당 2만대 계획을 분리해 추적하고, 손 조립 자동화율·직행수율/재작업률·센싱 글로브 적용·촉각센서 불량률·공급사 수율·기본 작업 학습시간·학습데이터/훈련허브 확대가 실제 안정 양산으로 이어지는지 확인합니다. '
                '초기 외부 상용화는 판매보다 선별 고객 대상 리스·회수·업그레이드·데이터 피드백 구조인지도 별도로 추적합니다.')
    if cat == 'Optimus 실제 양산 개시':
        return ('양산 예정·심사·공급망 준비가 아니라 실제 생산 개시가 확인된 단계 변화입니다. '
                '첫 주간 생산량·수율·완성품 출하·내부 배치로 실제 램프업 속도를 확인합니다.')
    if cat == 'Optimus Gen 3 앱 자산·세대 디자인 준비':
        return ('Tesla 서명 안드로이드 앱 패키지에서 Gen 2.5·Gen 3로 구분되는 이미지 자산이 관측됐다는 것은 공개 발표 전 소프트웨어 자산이 차세대 하드웨어 세대를 준비하는 제품화 신호입니다. '
                '다음 단계는 최신 앱 버전에서 자산이 유지되는지→Tesla 공식 Gen 3 공개→최종 기구 설계·액추에이터 구성→생산라인 적용 순으로 추적합니다.')
    if cat == 'Optimus 가정용 앱·충전 인프라 준비':
        return ('앱 내부 코드에 Optimus 전용 충전·등록·가정용 기기 관리 경로가 생긴 것은 단순 로봇 데모보다 제품화에 가까운 소프트웨어 인프라 신호입니다. '
                '실제 메뉴 활성화→충전 거치대 공개→가정용 시험사용자→소비자 판매 순으로 다음 상태 변화를 추적합니다.')
    if cat == 'Optimus 한국 공급망 생산시설·기술 점검':
        return ('테슬라가 중국 중심 Optimus 부품 조달을 보완하기 위해 한국 업체들의 생산시설·기술력을 직접 점검했다는 공급망 다변화 신호입니다. '
                '현재는 후보 발굴·기술 검토 단계이며, 다음 단계는 방문 업체 실명→샘플·공동개발→공급업체 승인→양산 발주→첫 출하 순으로 추적합니다.')
    if cat == 'Optimus 실명 공급사 주문·양산심사':
        return ('기존 익명 공급망의 심사 개시 보도에서 한 단계 나아가 Tuopu·Sanhua·Joyson 등 실명 업체와 주문 보유 주장이 함께 나온 후속 신호입니다. '
                '실명 업체별 심사 통과→생산 개시→실제 출하→수주 물량 공개 순으로 매출 연결을 추적합니다.')
    if cat == 'Optimus Giga Texas 전용공장 구조공사 진척':
        return ('계획 발표가 아니라 전용공장의 철골·콘크리트·철근 등 물리 공정이 실제 진행되는 단계 변화입니다. '
                '구조공사 완료→외장·유틸리티→생산설비 반입→시운전→양산 순으로 시간표를 추적합니다.')
    if cat == 'Optimus Giga Texas 생산설비 반입·설치':
        return ('건물 공사에서 실제 생산설비 설치로 넘어가는 더 강한 양산 준비 신호입니다. '
                '장비 설치 완료·전원 인가·시운전·초기 수율과 첫 완제품 생산을 다음 단계로 확인합니다.')
    if cat == 'Optimus 천 단위 발주·공급업체 심사':
        return ('수백 대 시험 생산 물량에서 약 5,000대 규모로 알려진 첫 천 단위 공급망 주문과 중국 공급업체 심사가 동시에 포착된 단계 변화입니다. '
                '양산 가능성을 공급망에서 검증하는 신호로 보고 실제 공급업체별 배정 수량·납기·출하·생산 수율을 이어서 추적합니다.')
    if cat == 'Optimus 천 단위 양산 발주':
        return ('수백 대 시험 물량에서 천 단위 부품 발주로 주문 규모가 한 단계 올라간 공급망 신호입니다. '
                '실제 부품사별 발주 수량·납기·반복 주문이 확인되면 양산 매출 가시성이 높아집니다.')
    if cat == 'Optimus 공급업체 양산 심사 실제 개시':
        return ('기존 약 5,000대 규모 공급망 주문의 후속으로, 공급업체 심사가 예정·방문 단계에서 실제 양산 심사 개시로 넘어간 신호입니다. '
                '심사 통과·정식 공급업체 선정·최종 발주 배정·실제 출하 순으로 다음 상태 변화를 추적합니다.')
    if cat == 'Optimus 공급업체 심사·양산 준비':
        return ('테슬라가 중국 공급업체의 현장 생산능력·품질·공정 준비를 직접 확인하는 단계로 해석되는 공급망 신호입니다. '
                '심사 통과, 최종 공급업체 선정, 양산 발주와 실제 출하를 분리해 추적합니다.')
    if cat == 'Optimus 생산라인·수율 램프업':
        return ('옵티머스가 설계 검증에서 반복 가능한 제조로 넘어가는지를 보는 신호입니다. '
                '주간 생산량·수율·라인 가동률·부품 병목과 실제 내부 배치를 확인합니다.')
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    if cat == 'Optimus 실제 주간 완제품 생산량':
        return ('공급망 기사에서 주당 수량이 언급돼도 실제 완제품 생산실적과 부품 공급능력 목표는 다를 수 있습니다. '
                '테슬라 공식자료 또는 복수의 독립 공급망 자료에서 실제 생산·출하가 확인되지 않으면 공식 실적처럼 표기하지 않습니다.')
    if cat == 'Optimus 경영진 양산 시간표·세대 전환':
        return ('경영진 목표는 실제 생산실적이 아닙니다. 일정이 바뀌면 새 시간표로 다시 알리되, 기존 발언의 재인용은 같은 사건으로 묶고 생산라인·장비 반입·수율·주간 생산량으로 이행 여부를 검증합니다.')
    if cat == 'Optimus 주간 공급능력·생산 목표':
        return ('공급능력 목표는 실제 생산량이 아닙니다. 수율·부품 병목·라인 안정화가 늦으면 목표치와 실제 주간 완제품 생산량의 격차가 커질 수 있습니다.')
    if cat == 'Optimus 주간 생산 램프·손·공급망 병목':
        return ('The Information 소식통 보도 성격의 생산량·목표 수치는 Tesla 공식 생산실적과 다를 수 있습니다. 주당 수백 대가 실제 완제품 기준인지, 연말 주당 1,000대가 라인 설계능력인지 실생산 목표인지 구분해야 합니다. '
                '가장 현실적인 실패 경로는 손·전완 조립 복잡도와 지그 정렬 불량 재작업, 촉각센서 신뢰성, 외부 모터·정밀기어 공급사의 대량생산 품질 편차, 미훈련 상황에서의 AI 불안정성이 동시에 남아 자동화라인 램프와 고객 배치가 늦어지는 경우입니다. '
                '먼저 볼 지표는 직행수율·재작업률, 센싱 글로브 실제 적용 시점, 기본 작업 학습시간, 50만시간→약 100만시간 데이터 확대 달성, 외부 리스 고객 실명과 실제 배치입니다.')
    if cat == 'Optimus 실제 양산 개시':
        return ('생산 개시와 안정 양산은 다릅니다. 초기 직행수율·재작업률·주간 생산량이 따라오지 않으면 양산 개시 후에도 병목이 지속될 수 있습니다.')
    if cat == 'Optimus Gen 3 앱 자산·세대 디자인 준비':
        return ('APK 자산명과 렌더는 Tesla의 공개 제품 발표나 최종 양산 설계가 아닙니다. 사용되지 않는 UI 자산·중간 디자인일 수 있고, 외형만으로 액추에이터·배선·내부 기구 변경을 확정할 수 없습니다. '
                '현재 최신 공개 APK는 4.61.0-4607이므로 같은 자산의 지속 여부와 Tesla 공식 공개를 후속 확인합니다.')
    if cat == 'Optimus 가정용 앱·충전 인프라 준비':
        return ('앱 코드 존재는 소비자 출시 확정이나 실제 충전기 양산을 뜻하지 않습니다. 실험용·비활성 코드일 수 있으므로 Tesla 공식 기능 공개, 실제 앱 화면, 충전 하드웨어 인증·출시가 뒤따르는지 확인합니다.')
    if cat == 'Optimus 한국 공급망 생산시설·기술 점검':
        return ('한국경제의 업계 취재 단계로, Tesla가 방문한 국내 업체 실명과 공식 공급업체 선정은 확인되지 않았습니다. '
                'HL만도·에스비비테크·로보티즈·삼현·하이젠알앤엠 등 기술 연관 기업을 방문사로 임의 치환하지 않고, Tesla/해당 기업 공식자료나 공급계약이 나올 때만 직접 공급사로 승격합니다.')
    if cat == 'Optimus 실명 공급사 주문·양산심사':
        return ('주문 보유와 심사 진행은 현재 익명 밸류체인 관계자 보도이며 Tesla와 각 상장사의 공식 수주 공시는 아닙니다. 9월 18일 각사 답변도 심사 여부를 확인하지 않았거나 답변을 유보했으므로 공식 확인 전까지 공급규모·독점 여부를 확정하지 않습니다.')
    if cat == 'Optimus Giga Texas 전용공장 구조공사 진척':
        return ('드론 현장 관측은 공정 진척을 보여주지만 최종 내부 배치·생산라인 구성과 가동일을 확정하지는 않습니다. 구조공사 후 장비 반입·유틸리티·시운전이 지연될 수 있습니다.')
    if cat == 'Optimus Giga Texas 생산설비 반입·설치':
        return ('설비 반입은 안정 양산과 다릅니다. 설치·캘리브레이션·공정 수율·부품 공급이 뒤따르지 않으면 가동 일정이 늦어질 수 있습니다.')
    if cat in {'Optimus 천 단위 발주·공급업체 심사', 'Optimus 천 단위 양산 발주'}:
        return ('약 5,000대 발주는 현재 중국 공급망 보도이며 테슬라 공식 공시로 확인된 수량은 아닙니다. '
                '공급업체 심사와 주문 보도가 실제 완제품 5,000대 생산·출하를 뜻하지 않으므로 공급업체 실명·발주서·납기·출하와 테슬라 공식 생산량을 별도로 확인합니다.')
    if cat == 'Optimus 공급업체 양산 심사 실제 개시':
        return ('심사 실제 개시는 최종 공급업체 선정·양산 수주 확정과 다릅니다. '
                '품질·원가·수율·납기 기준에서 탈락하거나 재심사가 발생하면 실제 출하 일정이 다시 늦어질 수 있습니다.')
    if cat == 'Optimus 공급업체 심사·양산 준비':
        return ('공급업체 심사 시작은 최종 선정이나 양산 수주 확정과 다릅니다. '
                '품질·원가·수율·납기 기준 미달 시 공급업체 변경 또는 양산 일정 지연이 먼저 나타날 수 있습니다.')
    if cat == 'Optimus 생산라인·수율 램프업':
        return ('생산라인 설치와 실제 안정 양산은 다릅니다. 수율과 주간 생산량이 목표에 못 미치면 부품 발주와 공급업체 증설이 다시 지연될 수 있습니다.')
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group == 'tesla' and _is_tesla_supply_text(text):
        if OFFICIAL_CONFIRM.search(text) or item.get('source') == 'Tesla':
            return '테슬라 공식·1차 자료'
        if _stage(text) == 'actual_weekly_production':
            return '실제 주간 생산량 보도 · 테슬라 공식자료 또는 복수 공급망 자료로 교차확인 필요'
        if _stage(text) == 'executive_production_timeline':
            source = item.get('source') or ''
            if source == MUSK_X_SOURCE or source == 'Tesla':
                return '일론 머스크·Tesla 1차 자료'
            if re.search(r'Diamandis|Moonshots|Dwarkesh|All-In', source, re.I):
                return '일론 머스크 공개 인터뷰·팟캐스트 1차 발언'
            return '머스크 발언 보도 · 원문 인터뷰/공식자료 교차확인'
        if _stage(text) == 'weekly_capacity_target':
            return '공급망 생산능력·목표 보도 · 실제 완제품 생산량과 분리'
        if _stage(text) == 'production_ramp_bottleneck':
            return 'The Information 원문 공개 범위와 Electrek·Investing.com 후속 보도 교차확인 · 주당 수백 대·연말 1,000대·손/지그 재작업·센싱 글로브·AI 일반화·리스 전략은 보도 단계이며 Tesla 공식 생산실적·상용화 확정 전'
        if _stage(text) == 'production_started':
            return '양산 실제 개시 보도 · 테슬라 공식 생산상태와 후속 교차확인'
        if _stage(text) == 'app_generation_asset':
            return '제3자 APK 역공학 관측 · Tesla 서명 4.60.5-4573 패키지 존재 확인 · Tesla 공식 Gen 3 디자인 공개 전'
        if _stage(text) == 'home_app_integration':
            return '테슬라 앱 코드 관측·역공학 단계 · Tesla 공식 소비자 기능/출시 발표 전'
        if _stage(text) == 'korea_supplier_scouting':
            return '한국경제 로봇업계 취재 보도 · 방문업체 실명·Tesla 공식 공급망 편입은 미확인'
        if _stage(text) == 'named_supplier_orders_audit':
            return '펑파이신문 취재·第一财经 재전재의 익명 밸류체인 관계자 발언 · Tesla/각사 공식 수주 확인 전'
        if _stage(text) == 'factory_structure':
            return '현장 드론 관측·신뢰매체 보도 · Tesla 공식 Q2 자료의 Giga Texas 건설 진행 상태와 교차확인'
        if _stage(text) == 'factory_tooling':
            return '현장·보도 단계 · Tesla 공식 자료에서 설비 설치·가동 상태 후속 확인'
        if _stage(text) in {'scale_order', 'scale_order_audit'}:
            return '중국 공급망 복수 보도 · 테슬라 공식 양산계획과 교차확인 · 약 5,000대 발주 수량은 테슬라 공식 확인 전'
        if _stage(text) == 'supplier_audit_started':
            return '중국 공급망 후속 보도 · 9월 17일 새 양산 심사 개시 보도 · 테슬라 공식 공급업체 선정 결과는 미확인'
        if _stage(text) == 'supplier_audit':
            return '중국 공급망 보도 · 공급업체 심사 진행 여부를 당사자·공식자료로 후속 확인'
    return _orig_verification(item, group, text)


def clean_title(title: str, source: str) -> str:
    # User-facing alert titles are Korean. Preserve company/product identifiers,
    # but do not expose untranslated Chinese headline prose.
    if re.search(r'特斯拉机器人团队在长三角审厂.{0,30}多家企业已获订单', title):
        return '테슬라 로봇팀, 창삼각 공급망 공장 실사…다수 기업 주문 확보 보도'
    if re.search(r'特斯拉被曝启动新一轮机器人业务量产审厂.{0,40}多家供应链企业回应', title):
        return '테슬라, 로봇 사업 신규 양산 공장 실사 착수 보도…다수 공급망 기업 반응'
    if re.search(r'特斯拉.{0,30}(?:审厂|審廠).{0,40}(?:订单|訂單)', title):
        return '테슬라 Optimus 공급망, 공장 실사·주문 관련 신규 보도'

    text = f'{title} {source}'
    if _is_tesla_supply_text(text):
        stage = _stage(text)
        if stage == 'actual_weekly_production':
            return '테슬라 옵티머스, 실제 주간 완제품 생산량 신규 확인'
        if stage == 'executive_production_timeline':
            return '일론 머스크, Optimus 생산·대량생산·세대 전환 시간표 신규 언급'
        if stage == 'weekly_capacity_target':
            return '테슬라 옵티머스, 주간 공급능력·생산 목표 신규 변화'
        if stage == 'production_ramp_bottleneck':
            return '테슬라 Optimus, 주당 수백 대 생산 램프…손·재작업·센서·AI·공급망 병목'
        if stage == 'production_started':
            return '테슬라 옵티머스, 실제 양산 개시 신규 확인'
        if stage == 'app_generation_asset':
            return '테슬라 앱 APK서 Optimus Gen 3 디자인 자산 발견'
        if stage == 'home_app_integration':
            return '테슬라 앱 코드, Optimus 충전기·가정용 기기 통합 준비 정황 포착'
        if stage == 'korea_supplier_scouting':
            return '테슬라, Optimus Gen 3 앞두고 한국 로봇부품 공급망 생산시설·기술력 점검 보도'
        if stage == 'named_supplier_orders_audit':
            return '테슬라 Optimus, Tuopu·Sanhua·Joyson 실명 공급사 주문 보유·양산심사 보도'
        if stage == 'factory_structure':
            return '테슬라 옵티머스, Giga Texas 전용공장 철골·콘크리트 공정 신규 진척'
        if stage == 'factory_tooling':
            return '테슬라 옵티머스, Giga Texas 생산설비 반입·설치 단계 진입'
        if stage == 'scale_order_audit':
            return '테슬라 옵티머스, 약 5,000대 공급망 주문·중국 공급업체 심사 진행 보도'
        if stage == 'scale_order':
            return '테슬라 옵티머스, 약 5,000대 천 단위 공급망 주문 보도'
        if stage == 'supplier_audit_started':
            return '테슬라 옵티머스, 기존 약 5,000대 주문 후속…중국 공급업체 양산 심사 실제 개시 보도'
        if stage == 'supplier_audit':
            return '테슬라 옵티머스, 중국 공급업체 심사·현장 방문 진행 보도'
        if stage == 'production_ramp':
            return '테슬라 옵티머스, 생산라인·수율 램프업 신규 변화'
    return _orig_clean_title(title, source)


def key(item: dict) -> str:
    text = f"{item.get('title','')} {item.get('description','')}"
    if _is_tesla_supply_text(text):
        stage = _stage(text)
        if stage == 'actual_weekly_production':
            m = re.search(r'(?<!\d)(\d{2,5})(?:\s*台|\s*대|\s*(?:per\s+week|weekly))', text, re.I)
            qty = m.group(1) if m else 'unknown'
            return hashlib.sha256(f'tesla-optimus|actual-weekly-production|{qty}'.encode()).hexdigest()
        if stage == 'executive_production_timeline':
            try:
                pub_year = dt.datetime.fromisoformat(item.get('published') or '').year
            except Exception:
                pub_year = base.NOW.year
            if pub_year == 2026 and OPTIMUS_V3.search(text) and (
                (EXEC_PROD_START.search(text) and re.search(r'this\s+summer|올\s*여름|이번\s*여름', text, re.I))
                or (EXEC_HIGH_VOLUME.search(text) and re.search(r'next\s+summer|내년\s*여름', text, re.I))
                or (OPTIMUS_V4.search(text) and re.search(r'next\s+year|내년', text, re.I))
            ):
                return _MARCH_18_2026_MUSK_OPTIMUS_KEY
            return _exec_key(text)
        if stage == 'production_ramp_bottleneck':
            return hashlib.sha256(b'tesla-optimus|2026-09|production-ramp-bottleneck|hands-supply-data').hexdigest()
        if stage == 'weekly_capacity_target':
            m = re.search(r'(?<!\d)(\d{2,5})(?:\s*台|\s*대|\s*(?:per\s+week|weekly))', text, re.I)
            qty = m.group(1) if m else 'unknown'
            return hashlib.sha256(f'tesla-optimus|weekly-capacity-target|{qty}'.encode()).hexdigest()
        if stage == 'app_generation_asset':
            return hashlib.sha256(b'tesla-optimus|gen3-apk-assets|4.60.5-4573').hexdigest()
        if stage == 'home_app_integration':
            return hashlib.sha256(b'tesla-optimus|home-app|charger-integration').hexdigest()
        if stage == 'factory_structure':
            return hashlib.sha256(b'tesla-optimus|giga-texas|factory-structure').hexdigest()
        if stage == 'factory_tooling':
            return hashlib.sha256(b'tesla-optimus|giga-texas|factory-tooling').hexdigest()
        if stage == 'korea_supplier_scouting':
            return hashlib.sha256(b'tesla-optimus|2026-h1|korea-supplier-scouting').hexdigest()
        if stage == 'named_supplier_orders_audit':
            return hashlib.sha256(b'tesla-optimus|2026-09-21|named-suppliers-orders-audit|tuopu-sanhua-joyson').hexdigest()
        if stage == 'supplier_audit_started':
            return hashlib.sha256(b'tesla-optimus|2026-09-17|supplier-production-audit-started').hexdigest()
        if stage == 'scale_order_audit':
            return hashlib.sha256(b'tesla-optimus|scale-order-5000|supplier-audit').hexdigest()
        if stage == 'scale_order':
            return hashlib.sha256(b'tesla-optimus|scale-order-5000').hexdigest()
        if stage == 'supplier_audit':
            return hashlib.sha256(b'tesla-optimus|supplier-audit').hexdigest()
    return _orig_key(item)


base.query_news = query_news
base.topic_group = topic_group
base.load_state = load_state
base.score = score
base.category = category
base.meaning = meaning
base.risk = risk
base.verification = verification
base.clean_title = clean_title
base.key = key


def _finalize_alert_text() -> None:
    if not base.ALERT_PATH.exists():
        return
    text = base.ALERT_PATH.read_text(encoding='utf-8')
    upgraded = '공식 사전예고·신규 AI 모델/성능 공개·천 단위 공급망 발주·공급업체 심사·수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·기술 재평가·수급·시간표를 바꾸는 내용만 알림.'
    for old in [
        '신규 수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·수급·시간표를 바꾸는 내용만 알림.',
        '공식 사전예고·신규 AI 모델/성능 공개·수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·기술 재평가·수급·시간표를 바꾸는 내용만 알림.',
    ]:
        text = text.replace(old, upgraded)
    base.ALERT_PATH.write_text(current.fig.legacy.display._inline_original_link(text), encoding='utf-8')


if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    current.fig.legacy.repair_pending_seen(pre_state)
    _finalize_alert_text()
