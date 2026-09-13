import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.korea_grid_stage_watch_v2 import parse_stage_rows


def test_parse_live_text_node_structure():
    html = """
    <div>번호</div><div>사업명</div><div>설비종류</div><div>담당본부</div><div>담당사업소</div>
    <div>202</div><div>345kV 남양주변전소 건설사업</div><div>변전</div><div>경인건설본부</div><div>직할</div>
    <div>201</div><div>154kV 에코-순아 지중송전선로 건설사업</div><div>지중송전선로</div><div>남부건설본부</div><div>직할</div>
    <div>이전</div>
    """
    rows = parse_stage_rows(html, "공사착수", 3, "https://www.kepco.co.kr/list")
    assert len(rows) == 2
    assert rows[0]["name"] == "345kV 남양주변전소 건설사업"
    assert rows[1]["equipment"] == "지중송전선로"
