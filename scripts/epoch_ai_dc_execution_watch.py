#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

DATA_URL = "https://epoch.ai/data/data_centers/data_centers.csv"
TIMELINE_URL = "https://epoch.ai/data/data_centers/data_center_timelines.csv"
SOURCE_URL = "https://epoch.ai/data/ai-data-centers"

STATE = Path("data/epoch_ai_dc_execution_state.json")
OUT = Path("out")
ALERT = OUT / "epoch_ai_dc_execution_alert.txt"
PENDING = OUT / "epoch_ai_dc_execution_pending_state.json"
STATUS = OUT / "epoch_ai_dc_execution_status.md"

KST = ZoneInfo("Asia/Seoul")
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
FORMAT_VERSION = 4
CENSUS_STATE = Path("data/data_center_growth_state.json")


def fetch_text(url: str, timeout: int = 40) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def rows_from_csv(url: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(fetch_text(url))))


def key(row: dict, *names: str) -> str:
    for name in names:
        if name in row and str(row.get(name) or "").strip():
            return str(row.get(name) or "").strip()
    return ""


def number(value) -> float | None:
    try:
        s = str(value or "").strip().replace(",", "")
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def parse_date(value: str):
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except Exception:
            continue
    return None


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def pct_change(new: float, old: float) -> float:
    return (new / old - 1) * 100 if old else 0.0



def census_context() -> dict | None:
    """Read the existing Census state, not an estimated monthly cash outlay."""
    try:
        d = json.loads(CENSUS_STATE.read_text(encoding="utf-8"))
        year, month = map(int, str(d["last_period"]).split("-"))
        now = datetime.now(KST)
        months_old = (now.year - year) * 12 + now.month - month
        yoy, mom = float(d["last_yoy_pct"]), float(d["last_mom_pct"])
        if not (0 <= months_old <= 3 and -100 <= yoy <= 2000 and -100 <= mom <= 2000):
            return None
        return {"period": d["last_period"], "yoy": yoy, "mom": mom}
    except (OSError, ValueError, TypeError, KeyError):
        return None


def pipeline_flow(old: dict, new: dict) -> dict:
    """Never equate falling not-yet-online capacity with falling new project plans."""
    if not old:
        return {"kind": "기준선", "plan": 0.0, "live": 0.0, "gap": 0.0,
                "added": None, "removed": None, "matched": None}
    plan = float(new["planned_it_mw_2030"]) - float(old.get("planned_it_mw_2030") or 0)
    live = float(new["current_it_mw"]) - float(old.get("current_it_mw") or 0)
    gap = float(new["remaining_it_mw"]) - float(old.get("remaining_it_mw") or 0)
    past_sites = old.get("site_capacity_snapshot_mw") or {}
    next_sites = new.get("site_capacity_snapshot_mw") or {}
    added = removed = matched = None
    if past_sites and next_sites:
        new_names = next_sites.keys() - past_sites.keys()
        lost_names = past_sites.keys() - next_sites.keys()
        both_names = past_sites.keys() & next_sites.keys()
        added = sum(float(next_sites[k]["planned"]) for k in new_names)
        removed = sum(float(past_sites[k]["planned"]) for k in lost_names)
        matched = sum(float(next_sites[k]["planned"]) - float(past_sites[k]["planned"]) for k in both_names)
        if abs((added - removed + matched) - plan) > 2:
            raise ValueError("Epoch aggregate and site-level plan revision mismatch")
    if plan <= -1000:
        kind = "계획 축소·자료 재분류 가능성 추가 검증 필요"
    elif plan >= 1000:
        kind = "추정 계획 용량 확대"
    elif abs(plan) < 200 and live >= 500 and gap <= -500:
        kind = "기존 계획의 가동 전환(사업 취소 신호 아님)"
    elif live <= -500:
        kind = "가동 추정치 감소·자료 재확인 필요"
    else:
        kind = "새로운 대규모 변화 미확인"
    return {"kind": kind, "plan": round(plan, 1), "live": round(live, 1),
            "gap": round(gap, 1), "added": added, "removed": removed, "matched": matched}


def regression_checks() -> None:
    """Test unit- and cohort-safe pipeline classification on each run."""
    old = {"planned_it_mw_2030": 10000, "current_it_mw": 2000, "remaining_it_mw": 8000}
    online = {"planned_it_mw_2030": 10000, "current_it_mw": 3000, "remaining_it_mw": 7000}
    cut = {"planned_it_mw_2030": 8500, "current_it_mw": 2000, "remaining_it_mw": 6500}
    assert pipeline_flow(old, online)["kind"].startswith("기존 계획의 가동 전환")
    assert pipeline_flow(old, cut)["kind"].startswith("계획 축소")
    assert pipeline_flow(old, online)["plan"] == 0
    try:
        pipeline_flow(
            {**old, "site_capacity_snapshot_mw": {"A": {"planned": 10000}}},
            {**online, "site_capacity_snapshot_mw": {"A": {"planned": 8500}}})
    except ValueError:
        pass
    else:
        raise AssertionError("Unreconciled site/aggregate IT capacities slipped through")


def ko_visible(value: str) -> str:
    text = re.sub(r"#(?:confident|likely|speculative)\b", "", str(value or ""), flags=re.I).strip()
    if not text:
        return ""
    if not re.search(r"[A-Za-z]", text):
        return text

    known = {
        "Microsoft": "마이크로소프트", "Amazon": "아마존", "AWS": "아마존웹서비스",
        "Meta": "메타", "Google": "구글", "OpenAI": "오픈AI", "Oracle": "오라클",
        "Anthropic": "앤트로픽", "xAI": "엑스AI", "QTS": "큐티에스",
        "Vantage": "밴티지", "CoreWeave": "코어위브", "SoftBank": "소프트뱅크", "Softbank": "소프트뱅크", "Stargate": "스타게이트",
        "Data Center": "데이터센터", "Data center": "데이터센터",
        "Hyperscale": "하이퍼스케일", "Fairwater": "페어워터",
        "Hyperion": "하이페리온", "Prometheus": "프로메테우스", "Colossus": "콜로서스",
        "Wisconsin": "위스콘신", "Michigan": "미시간", "New Mexico": "뉴멕시코",
        "Texas": "텍사스", "Louisiana": "루이지애나", "Indiana": "인디애나",
        "Ohio": "오하이오", "Georgia": "조지아", "Atlanta": "애틀랜타", "Abilene": "애빌린",
    }
    translated = text
    for src, dst in sorted(known.items(), key=lambda kv: len(kv[0]), reverse=True):
        translated = translated.replace(src, dst)
    if not re.search(r"[A-Za-z]", translated):
        return translated

    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client":"gtx","sl":"auto","tl":"ko","dt":"t","q":text},
            headers=HEADERS,
            timeout=12,
        )
        r.raise_for_status()
        data = r.json()
        out = "".join(seg[0] for seg in (data[0] or []) if isinstance(seg,list) and seg and isinstance(seg[0],str)).strip()
        if out and re.search(r"[가-힣]", out):
            return out
    except Exception:
        pass

    cleaned = re.sub(r"\b[A-Za-z][A-Za-z0-9._&+\-/]*\b", "", translated)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ·-/")
    return cleaned or "해외 데이터센터 프로젝트"


def build_snapshot() -> dict:
    centers = rows_from_csv(DATA_URL)
    timelines = rows_from_csv(TIMELINE_URL)
    today = datetime.now(KST).date()
    cutoff = datetime(2030, 12, 31).date()

    us_names = set()
    owner = {}
    for row in centers:
        country = key(row, "Country", "country")
        if "united states" not in country.lower() and country.lower() not in {"usa", "us"}:
            continue
        name = key(row, "Name", "Data center", "Data Center", "name")
        if not name:
            continue
        us_names.add(name)
        owner[name] = key(row, "Owner", "owner")

    per_site = {}
    for row in timelines:
        name = key(row, "Data center", "Data Center", "Name", "name")
        if name not in us_names:
            continue
        d = parse_date(key(row, "Date", "date"))
        it = number(row.get("IT power (MW)") if "IT power (MW)" in row else row.get("IT Power (MW)"))
        if d is None or it is None or it < 0:
            continue
        item = per_site.setdefault(name, {"current": 0.0, "planned": 0.0, "current_date": None, "planned_date": None})
        if d <= today and (item["current_date"] is None or d >= item["current_date"]):
            item["current"] = it
            item["current_date"] = d
        if d <= cutoff and (it > item["planned"] or (it == item["planned"] and (item["planned_date"] is None or d > item["planned_date"]))):
            item["planned"] = it
            item["planned_date"] = d

    eligible = {name: v for name, v in per_site.items() if v["planned"] > 0}
    current_mw = sum(v["current"] for v in eligible.values())
    planned_mw = sum(v["planned"] for v in eligible.values())
    ratio = current_mw / planned_mw * 100 if planned_mw else 0.0
    gap_mw = max(planned_mw - current_mw, 0.0)

    top_gap = []
    for name, v in eligible.items():
        gap = max(v["planned"] - v["current"], 0.0)
        if gap <= 0:
            continue
        top_gap.append({
            "name": name,
            "owner": owner.get(name, ""),
            "current_mw": round(v["current"], 1),
            "planned_mw": round(v["planned"], 1),
            "gap_mw": round(gap, 1),
            "planned_date": v["planned_date"].isoformat() if v["planned_date"] else None,
        })
    top_gap.sort(key=lambda x: x["gap_mw"], reverse=True)

    return {
        "format_version": FORMAT_VERSION,
        "source": "Epoch AI",
        "source_url": SOURCE_URL,
        "data_url": DATA_URL,
        "timeline_url": TIMELINE_URL,
        "as_of_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "site_count": len(eligible),
        "current_it_mw": round(current_mw, 1),
        "planned_it_mw_2030": round(planned_mw, 1),
        "remaining_it_mw": round(gap_mw, 1),
        "execution_ratio_pct": round(ratio, 2),
        "top_remaining_sites": top_gap[:12],
        "site_capacity_snapshot_mw": {
            name: {"planned": round(v["planned"], 1), "current": round(v["current"], 1)}
            for name, v in sorted(eligible.items())
        },
    }


def material_changes(old: dict, new: dict) -> list[str]:
    if not old:
        return ["기준선 설정"]
    changes = []
    if int(old.get("format_version", 0) or 0) < FORMAT_VERSION:
        changes.append("한국어 표기·가독성 형식 업그레이드")
    old_current = float(old.get("current_it_mw") or 0)
    new_current = float(new.get("current_it_mw") or 0)
    old_plan = float(old.get("planned_it_mw_2030") or 0)
    new_plan = float(new.get("planned_it_mw_2030") or 0)
    old_ratio = float(old.get("execution_ratio_pct") or 0)
    new_ratio = float(new.get("execution_ratio_pct") or 0)
    old_sites = int(old.get("site_count") or 0)
    new_sites = int(new.get("site_count") or 0)

    if abs(new_current - old_current) >= 500 or (old_current and abs(pct_change(new_current, old_current)) >= 5):
        changes.append(f"현재 가동 IT 전력 {old_current:,.0f}MW → {new_current:,.0f}MW")
    if abs(new_plan - old_plan) >= 1000 or (old_plan and abs(pct_change(new_plan, old_plan)) >= 5):
        changes.append(f"2030 계획 IT전력 추정치 {old_plan:,.0f}→{new_plan:,.0f}MW (착공 전 물량과 구분)")
    if abs(new_ratio - old_ratio) >= 2.0:
        changes.append(f"계획 대비 가동률 {old_ratio:.1f}% → {new_ratio:.1f}%")
    if abs(new_sites - old_sites) >= 2:
        changes.append(f"미국 추적 사이트 {old_sites}곳 → {new_sites}곳")
    return changes


def build_alert(new: dict, changes: list[str], first: bool, flow: dict, census: dict | None) -> str:
    title = "미국 AI 데이터센터 추정 IT전력 기준선" if first else "미국 AI 데이터센터 계획·가동 추정치 변화"
    current = float(new["current_it_mw"])
    planned = float(new["planned_it_mw_2030"])
    remaining = float(new["remaining_it_mw"])
    ratio = float(new["execution_ratio_pct"])

    lines = [
        title,
        "",
        "▶ 한눈에 보기",
        f"• 현재 가동 IT 전력: {current:,.0f}MW",
        f"• 2030년까지 계획 IT 전력: {planned:,.0f}MW",
        f"• 추정 가동/2030 계획 IT전력 비율: {ratio:.1f}% (건설 공정률 아님)",
        f"• 미가동 계획량: {remaining:,.0f}MW ({100-ratio:.1f}%) · 착공 전/건설 중 미분리",
        f"• 추적 미국 AI 데이터센터: {int(new['site_count'])}곳",
        "",
        "■ 이번 변화",
    ]
    for ch in changes[:6]:
        lines.append(f"• {ch}")

    lines += [
        "",
        "■ 신규 투자와 기존 사업 가동 전환 구분",
        f"• Epoch 가동 IT전력 변화: {flow['live']:+,.0f}MW",
        f"• Epoch 2030 계획 IT전력 변화: {flow['plan']:+,.0f}MW",
        f"• 아직 미가동인 계획량 변화: {flow['gap']:+,.0f}MW",
        f"• 단계 판정: {flow['kind']}",
    ]
    if flow["matched"] is not None:
        lines.append(
            f"• 신규 포착 프로젝트 +{flow['added']:,.0f}MW"
            f" / 추적 제외 프로젝트 -{flow['removed']:,.0f}MW"
            f" / 기존 프로젝트 계획 수정 {flow['matched']:+,.0f}MW"
        )
    if census:
        lines.append(
            f"• Census 민간 데이터센터 건설지출({census['period']}, 계절조정 연율):"
            f" 전월 {census['mom']:+.1f}%, 전년 {census['yoy']:+.1f}%"
        )
    lines += [
        "• BNEF의 미국 전체 착공 전/건설 중/가동 GW와 Epoch의"
        " 일부 AI 프로젝트 IT전력 MW는 표본·범위가 달라 합산하지 않습니다.",
        "• 미가동 계획 감소만으로 착공 전 계획 감소·취소를 확정하지 않습니다.",
        "",
        "■ 해석",
        "• Epoch 추정 가동 IT전력 ÷ 2030 추정 계획 IT전력의 비율을 봅니다.",
        "• 비율 상승은 추정 가동 증가이나 공식 전원 인가·계통 접속·고객 검수의 증거는 아닙니다.",
        "• 계획만 커지고 추정 가동이 정체되면 전원 인가·건설·냉각 병목을 별도 확인합니다.",
        "",
        "■ 미가동 전력 상위 프로젝트",
    ]
    for row in new.get("top_remaining_sites", [])[:6]:
        project_name = ko_visible(row.get("name", ""))
        owner_name = ko_visible(row.get("owner", ""))
        own = f" · {owner_name}" if owner_name else ""
        lines.append(
            f"• {project_name}{own}: 현재 {row['current_mw']:,.0f}MW / 계획 {row['planned_mw']:,.0f}MW "
            f"→ 잔여 {row['gap_mw']:,.0f}MW"
        )

    lines += [
        "",
        "■ 주의",
        "• 에포크AI는 고해상도 위성영상·허가·공시·공개자료와 자체 모델을 결합한 독립 추정치입니다.",
        "• 전력회사 공식 전원 인가 MW나 기업 공시 확정치와 동일한 통계가 아니므로 방향·실행 속도 확인용으로 사용합니다.",
        f"원문: {SOURCE_URL}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (ALERT, PENDING, STATUS):
        p.unlink(missing_ok=True)

    regression_checks()
    old = load_state()
    try:
        new = build_snapshot()
        if old.get("site_count") and new["site_count"] < 0.7 * old["site_count"]:
            raise ValueError("Epoch 추적 사이트 수가 30% 넘게 급감: 원천 품질 저하 가능")
        flow = pipeline_flow(old, new)
    except Exception as exc:
        # Preserve the baseline and allow the other live monitors to run.
        if not old or not all(k in old for k in ("site_count", "current_it_mw", "planned_it_mw_2030")):
            raise
        PENDING.write_text(json.dumps(old, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        STATUS.write_text(
            "# Epoch AI 투자 사이클 감시\n\n"
            f"- 원천 오류: {type(exc).__name__}: {exc}\n"
            "- 기준선 유지·신규 알림 미발송·다른 감시는 계속 진행\n",
            encoding="utf-8",
        )
        print(f"epoch_ai_dc_execution source_error={type(exc).__name__} baseline_held=True alert=False")
        return 0
    census = census_context()
    changes = material_changes(old, new)
    first = not bool(old)
    should_alert = bool(changes)

    PENDING.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if should_alert:
        ALERT.write_text(build_alert(new, changes, first, flow, census), encoding="utf-8")

    STATUS.write_text(
        "# 미국 AI 데이터센터 실제 가동률 감시\n\n"
        f"- 추적 사이트: **{new['site_count']}곳**\n"
        f"- 현재 IT 전력: **{new['current_it_mw']:,.1f}MW**\n"
        f"- 2030 계획 IT 전력: **{new['planned_it_mw_2030']:,.1f}MW**\n"
        f"- 실행률: **{new['execution_ratio_pct']:.2f}%**\n"
        f"- 미가동 계획량(착공 전/건설 중 구분 불가): **{new['remaining_it_mw']:,.1f}MW**\n"
        f"- 계획 증감: **{flow['plan']:+,.1f}MW**, 가동 증감: **{flow['live']:+,.1f}MW**\n"
        f"- 투자 사이클 판정: **{flow['kind']}**\n"
        f"- 중요 변화: **{len(changes)}건**\n"
        f"- 알림: **{'예' if should_alert else '아니오'}**\n",
        encoding="utf-8",
    )
    print(
        f"epoch_ai_dc_execution sites={new['site_count']} current={new['current_it_mw']:.1f} "
        f"planned={new['planned_it_mw_2030']:.1f} ratio={new['execution_ratio_pct']:.2f} "
        f"changes={len(changes)} alert={should_alert}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
