from pathlib import Path

path = Path('scripts/honam_semiconductor_watch.py')
text = path.read_text(encoding='utf-8')

needle = "    '\"호남권 반도체 국가산업단지\" 전력 용수 변전소 송전',\n"
insert = (
    "    '\"호남권 반도체 국가산업단지\" 전력 용수 변전소 송전',\n"
    "    '국회입법조사처 호남 반도체 클러스터 용수 공급 타당성',\n"
    "    'site:nars.go.kr 호남 반도체 클러스터 용수',\n"
    "    '호남 반도체 댐 용수 하수재이용수 하천수 가뭄',\n"
    "    '호남 반도체 동복댐 주암댐 장흥댐 보성강댐 나주댐',\n"
)
if needle in text and "site:nars.go.kr 호남 반도체 클러스터 용수" not in text:
    text = text.replace(needle, insert, 1)

old = '"5_기반시설_생활SOC": ["전력", "용수", "변전소", "송전", "배전", "전원 인가", "도로", "철도", "교통", "교육", "학교", "의료", "병원", "문화", "생활 soc", "기반시설", "산업용수", "하수", "물류", "공항", "항공화물", "에너지", "분산에너지"],'
new = '"5_기반시설_생활SOC": ["전력", "용수", "변전소", "송전", "배전", "전원 인가", "도로", "철도", "교통", "교육", "학교", "의료", "병원", "문화", "생활 soc", "기반시설", "산업용수", "하수", "물류", "공항", "항공화물", "에너지", "분산에너지", "댐", "동복댐", "주암댐", "장흥댐", "보성강댐", "나주댐", "하수재이용수", "재이용수", "하천수", "이수 안전도", "유입량", "유출량", "가뭄", "물 부족", "용수 배분", "목적 외 사용", "사용료", "수자원", "용수 공급"],'
if old in text:
    text = text.replace(old, new, 1)

old_mat = '"전력", "용수"]'
new_mat = '"전력", "용수", "댐", "하수재이용수", "하천수", "가뭄", "물 부족", "유입량", "유출량", "이수 안전도", "수자원"]'
if old_mat in text:
    text = text.replace(old_mat, new_mat, 1)

path.write_text(text, encoding='utf-8')
print('patched=true')
