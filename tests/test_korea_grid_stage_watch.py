import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.korea_grid_stage_watch import (
    compare_state,
    discover_stage_pages,
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


def test_discover_stage_pages_includes_completion_tab():
    html = """
    <a href="plantoapprove/boardList.do">계획확정 - 사업승인전</a>
    <a href="approvetostart/boardList.do">사업승인 - 공사착수전</a>
    <a href="starttocomplete/boardList.do">공사착수 - 사업완료전</a>
    <a href="completetoyear/boardList.do">사업완료 - 준공후 1년</a>
    """
    pages = discover_stage_pages(html, "https://www.kepco.co.kr/home/disclosure/transdisclosure/transstatus/")
    assert set(pages) == {"계획확정", "사업승인", "공사착수", "사업완료"}
    assert pages["사업완료"][0] == 4
    assert pages["사업완료"][1].endswith("completetoyear/boardList.do")


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
    report = render_report(
        events,
        new_counts,
        {
            "사업승인": {"expected": 190, "parsed": 190, "complete": True},
            "공사착수": {"expected": 203, "parsed": 203, "complete": True},
        },
    )
    assert "어떤 사업이 바뀌었나" in report
    assert "154kV 테스트변전소 건설사업" in report
    assert "사업승인 → 공사착수" in report
    assert "공사착수 (+1)" in report
    assert "시간표·돈 버는 능력" in report
    assert "변압기·GIS·차단기" in report
    assert "특정 기사 추적이 아니라 한국전력 송변전 사업현황의 실제 단계·물량 변화 감지" in report
    assert "<i>" not in report


def test_render_report_calls_out_unreconciled_count_change():
    counts = {"계획확정": 396, "사업승인": 195, "공사착수": 131, "사업완료": 2}
    events = [
        {"type": "count_change", "changes": [("계획확정", 393, 396)]},
    ]
    report = render_report(
        events,
        counts,
        {"계획확정": {"expected": 396, "parsed": 10, "complete": False}},
    )
    assert "계획확정 (+3)" in report
    assert "대응 사업명을 아직 확정하지 못함" in report
    assert "전수 확인 아님" in report
    assert "목록 갱신 시차 확인 필요" in report
