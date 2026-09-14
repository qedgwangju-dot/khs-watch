import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.korea_grid_stage_watch import (
    compare_state,
    parse_overview_counts,
    parse_stage_rows,
    render_report,
)


def test_parse_overview_counts():
    html = """
    <div>443 건 계획확정 - 사업승인전 이동 버튼</div>
    <div>191 건 사업승인 - 공사착수전 이동 버튼</div>
    <div>203 건 공사착수 - 사업완료전 이동 버튼</div>
    <div>14 건 사업완료 - 준공후 1년 이동 버튼</div>
    """
    assert parse_overview_counts(html) == {
        "계획확정": 443,
        "사업승인": 191,
        "공사착수": 203,
        "사업완료": 14,
    }


def test_parse_stage_rows():
    html = """
    <table>
      <tr><th>번호</th><th>사업명</th><th>설비종류</th><th>담당본부</th><th>담당사업소</th></tr>
      <tr><td>202</td><td><a href="boardView.do?id=1">345kV 남양주변전소 건설사업</a></td><td>변전</td><td>경인건설본부</td><td>직할</td></tr>
    </table>
    """
    rows = parse_stage_rows(html, "공사착수", 3, "https://www.kepco.co.kr/base/")
    assert len(rows) == 1
    assert rows[0]["name"] == "345kV 남양주변전소 건설사업"
    assert rows[0]["equipment"] == "변전"
    assert rows[0]["stage"] == "공사착수"


def test_compare_state_detects_stage_change_and_count_change():
    old_counts = {"계획확정": 443, "사업승인": 191, "공사착수": 202, "사업완료": 14}
    new_counts = {"계획확정": 443, "사업승인": 190, "공사착수": 203, "사업완료": 14}
    old_projects = {
        "154kv테스트변전소건설사업": {
            "name": "154kV 테스트변전소 건설사업",
            "stage": "사업승인",
            "stage_order": 2,
            "equipment": "변전",
            "hq": "중부건설본부",
            "office": "직할",
            "url": "https://example.com/old",
        }
    }
    new_projects = {
        "154kv테스트변전소건설사업": {
            "name": "154kV 테스트변전소 건설사업",
            "stage": "공사착수",
            "stage_order": 3,
            "equipment": "변전",
            "hq": "중부건설본부",
            "office": "직할",
            "url": "https://example.com/new",
        }
    }
    events = compare_state(old_counts, old_projects, new_counts, new_projects)
    assert any(e["type"] == "count_change" for e in events)
    assert any(e["type"] == "stage_change" for e in events)
    report = render_report(events, new_counts)
    assert "사업승인 → 공사착수" in report
    assert "시간표·돈 버는 능력" in report
    assert "변압기·GIS·차단기" in report
    assert "특정 기사 추적이 아니라 한국전력 송변전 사업현황의 실제 단계·물량 변화 감지" in report
    assert "<i>" not in report
