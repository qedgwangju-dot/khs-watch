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
        changes.append(f"2030 계획 IT 전력 {old_plan:,.0f}MW → {new_plan:,.0f}MW")
    if abs(new_ratio - old_ratio) >= 2.0:
        changes.append(f"계획 대비 가동률 {old_ratio:.1f}% → {new_ratio:.1f}%")
    if abs(new_sites - old_sites) >= 2:
        changes.append(f"미국 추적 사이트 {old_sites}곳 → {new_sites}곳")
    return changes


def build_alert(new: dict, changes: list[str], first: bool) -> str:
    title = "✅ 미국 AI 데이터센터 실제 가동률 감시 연결 완료" if first else "⚡ 미국 AI 데이터센터 실제 가동률 변화"
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
        f"• 실제 가동률: {ratio:.1f}%",
        f"• 아직 미가동: {remaining:,.0f}MW ({100-ratio:.1f}%)",
        f"• 추적 미국 AI 데이터센터: {int(new['site_count'])}곳",
        "",
        "■ 이번 변화",
    ]
    for ch in changes[:6]:
        lines.append(f"• {ch}")

    lines += [
        "",
        "■ 해석",
        "• 계획 GW가 아니라 실제 IT 전력이 켜진 비율을 추적합니다.",
        "• 이 비율이 올라가면 전력망·변전소·냉각·서버 반입이 실제 운영 단계로 넘어간 것으로 봅니다.",
        "• 계획 전력만 커지고 가동률이 정체되면 전원 인가·건설·냉각 병목이 더 커진 것으로 봅니다.",
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

    old = load_state()
    new = build_snapshot()
    changes = material_changes(old, new)
    first = not bool(old)
    should_alert = bool(changes)

    PENDING.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if should_alert:
        ALERT.write_text(build_alert(new, changes, first), encoding="utf-8")

    STATUS.write_text(
        "# 미국 AI 데이터센터 실제 가동률 감시\n\n"
        f"- 추적 사이트: **{new['site_count']}곳**\n"
        f"- 현재 IT 전력: **{new['current_it_mw']:,.1f}MW**\n"
        f"- 2030 계획 IT 전력: **{new['planned_it_mw_2030']:,.1f}MW**\n"
        f"- 실행률: **{new['execution_ratio_pct']:.2f}%**\n"
        f"- 잔여: **{new['remaining_it_mw']:,.1f}MW**\n"
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
