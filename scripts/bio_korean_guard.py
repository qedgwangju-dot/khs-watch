from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request

UA = 'Mozilla/5.0 (compatible; BioKoreanGuard/1.0)'

# 제품명·회사명·임상명·규제 약어처럼 번역하면 식별성이 깨지는 항목만 보존한다.
ALLOWED_IDENTIFIERS = (
    'Enhertu', 'Jemperli', 'dostarlimab', 'trastuzumab deruxtecan', 'pertuzumab',
    'Intismeran', 'Intismeran autogene', 'pembrolizumab', 'berahyaluronidase alfa',
    'KEYTRUDA', 'QLEX', 'ALT-B4', 'Hybrozyme', 'GSK', 'Merck', 'Moderna',
    'AstraZeneca', 'Daiichi Sankyo', 'Tesaro', 'FDA', 'EMA', 'EU', 'EC', 'PDUFA',
    'CHMP', 'Project Orbis', 'ClinicalTrials.gov', 'DESTINY-Breast09', 'DESTINY-Breast05',
    'AZUR-1', 'AZUR-2', 'AZUR-4', 'DOMENICA', 'JADE', 'INTerpath-001', 'INTerpath-014',
    'KEYNOTE-942', 'HER2', 'dMMR', 'MSI-H', 'sBLA', 'RFS', 'DMFS', 'OS', 'HR', 'PFS',
    'ORR', 'cCR12', 'mRNA', 'SC', 'IV', 'THP', 'WAC', 'QoQ', 'YoY', 'USD', 'KRW',
)

COMMON_REPLACEMENTS = (
    (r'\bNational Priority Voucher program\b', '국가 우선 바우처 프로그램'),
    (r'\bNational Priority Voucher\b', '국가 우선 바우처'),
    (r'\bCommissioner[’\']s National Priority Voucher\b', '미국 FDA 국가 우선 바우처'),
    (r'\brecurrence[- ]free survival\b', '재발 없는 생존기간'),
    (r'\bdistant metastasis[- ]free survival\b', '원격전이 없는 생존기간'),
    (r'\bprogression[- ]free survival\b', '무진행 생존기간'),
    (r'\boverall survival\b', '전체생존기간'),
    (r'\bobjective response rate\b', '객관적 반응률'),
    (r'\bhazard ratio\b', '위험비'),
    (r'\bclinical complete response\b', '임상적 완전반응'),
    (r'\bpriority review\b', '우선 검토'),
    (r'\bprimary endpoint(?:s)?\b', '1차 평가변수'),
    (r'\bmet endpoints?\b', '평가변수 달성'),
    (r'\bphase\s*iii\b', '3상'),
    (r'\bphase\s*3\b', '3상'),
    (r'\bphase\s*ii\b', '2상'),
    (r'\bphase\s*2\b', '2상'),
    (r'\bfirst[- ]line\b', '1차 치료'),
    (r'\bsecond[- ]line\b', '2차 치료'),
    (r'\bsubcutaneous\b', '피하주사'),
    (r'\bintravenous\b', '정맥주사'),
    (r'\bgross sales\b', '총판매액'),
    (r'\bconversion rate\b', '전환율'),
    (r'\badoption rate\b', '채택률'),
    (r'\badoption\b', '채택'),
    (r'\buptake\b', '채택 확대'),
    (r'\bsafety profile\b', '안전성 프로파일'),
    (r'\bregulatory submission(?:s)?\b', '허가 신청'),
    (r'\bapproval\b', '승인'),
    (r'\bapproved\b', '승인'),
    (r'\btrial\b', '임상'),
    (r'\bstudy\b', '임상'),
    (r'\bresults?\b', '결과'),
    (r'\bendpoints?\b', '평가변수'),
    (r'\bpatients?\b', '환자'),
    (r'\bsales\b', '판매'),
    (r'\brevenue\b', '매출'),
    (r'\bmonths?\b', '개월'),
    (r'\bcompared to\b', '대비'),
    (r'\bversus\b', '대비'),
)


def apply_common_replacements(text: str) -> str:
    out = text
    for pattern, replacement in COMMON_REPLACEMENTS:
        out = re.sub(pattern, replacement, out, flags=re.I)
    return out


def protect_identifiers(text: str) -> tuple[str, dict[str, str]]:
    protected = text
    mapping: dict[str, str] = {}
    for index, identifier in enumerate(sorted(ALLOWED_IDENTIFIERS, key=len, reverse=True)):
        pattern = re.compile(re.escape(identifier), re.I)
        if not pattern.search(protected):
            continue
        marker = f'【고유명{index}】'
        match = pattern.search(protected)
        if not match:
            continue
        mapping[marker] = match.group(0)
        protected = pattern.sub(marker, protected)
    return protected, mapping


def restore_identifiers(text: str, mapping: dict[str, str]) -> str:
    out = text
    for marker, value in mapping.items():
        out = out.replace(marker, value)
    return out


def translate_to_korean(text: str) -> str:
    if not text.strip():
        return text
    pair = 'ja|ko' if re.search(r'[ぁ-んァ-ン]', text) else 'en|ko'
    protected, mapping = protect_identifiers(text)
    query = urllib.parse.urlencode({'q': protected[:480], 'langpair': pair, 'mt': '1'})
    req = urllib.request.Request(
        f'https://api.mymemory.translated.net/get?{query}',
        headers={'User-Agent': UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode('utf-8', errors='replace'))
        candidate = html.unescape(str((payload.get('responseData') or {}).get('translatedText') or '')).strip()
    except Exception as exc:
        raise RuntimeError(f'한국어 자동번역 실패: {type(exc).__name__}') from exc
    if not candidate or len(re.findall(r'[가-힣]', candidate)) < 2:
        raise RuntimeError('한국어 자동번역 결과가 비어 있거나 불완전함')
    return restore_identifiers(candidate, mapping)


def scrub_identifiers(text: str) -> str:
    out = text
    for identifier in sorted(ALLOWED_IDENTIFIERS, key=len, reverse=True):
        out = re.sub(re.escape(identifier), '', out, flags=re.I)
    out = re.sub(r'https?://\S+', '', out)
    out = re.sub(r'\bNCT\d+\b', '', out, flags=re.I)
    return out


def general_english_words(text: str) -> list[str]:
    scrub = scrub_identifiers(text)
    return re.findall(r'\b[A-Za-z]{3,}\b', scrub)


def has_japanese(text: str) -> bool:
    return bool(re.search(r'[ぁ-んァ-ン一-龯]', text))


def translate_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return line
    # URL 자체와 클릭 링크 목적지는 번역하지 않는다.
    if stripped.startswith('- 원문:') or '원문 뉴스보기' in stripped or re.fullmatch(r'https?://\S+', stripped):
        return line

    converted = apply_common_replacements(line)
    if has_japanese(converted) or len(general_english_words(converted)) >= 2:
        converted = translate_to_korean(converted)
        converted = apply_common_replacements(converted)

    leftover = general_english_words(converted)
    if has_japanese(converted) or len(leftover) >= 2:
        raise RuntimeError(
            '한국어 송출 검증 실패 — 일반 영어/일본어 설명어가 남아 있음: '
            + ', '.join(leftover[:8])
        )
    return converted


def ensure_korean_text(text: str) -> str:
    return '\n'.join(translate_line(line) for line in text.splitlines())


def main() -> int:
    import pathlib
    import sys

    if len(sys.argv) != 2:
        print('usage: bio_korean_guard.py FILE', file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    original = path.read_text(encoding='utf-8')
    converted = ensure_korean_text(original)
    path.write_text(converted, encoding='utf-8')
    print('bio_korean_guard=ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
