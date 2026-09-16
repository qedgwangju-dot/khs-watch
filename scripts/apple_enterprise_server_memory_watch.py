#!/usr/bin/env python3
"""Apple enterprise AI server / memory procurement watcher.

Purpose
- Track Apple's reported return to enterprise AI servers (M8 Ultra, 2/4-chip systems, 2029 target).
- Track NVIDIA NVLink Fusion discussions separately from any HBM purchase.
- Track named Apple server-DRAM/HBM/NVHBM procurement, LTAs, allocations and supplier design wins.
- Track commercial milestones, delays/cancellations, packaging/thermal/memory bottlenecks.

Guardrails
- NVLink Fusion adoption != HBM order.
- Mobile DRAM price pressure != confirmed Apple server-memory bulk purchase.
- HBM/server DRAM is promoted to "confirmed procurement" only on Apple/supplier official evidence
  or multiple high-quality reports with a named supplier/order/allocation.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "apple_enterprise_server_memory_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_PATH = OUT_DIR / "apple_enterprise_server_memory_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "apple_enterprise_server_memory_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "apple_enterprise_server_memory_watch_status.md"
KST = ZoneInfo("Asia/Seoul")

QUERIES = [
    ("ko", '애플 M8 Ultra 서버 NVLink Fusion'),
    ("ko", '애플 엔터프라이즈 AI 서버 M8 Ultra 2029'),
    ("ko", '애플 AI 서버 HBM 삼성전자 SK하이닉스 마이크론'),
    ("ko", '애플 서버 DRAM 장기계약 메모리 조달'),
    ("ko", '애플 NVHBM NVLink Fusion 메모리'),
    ("en", 'Apple M8 Ultra enterprise server NVLink Fusion'),
    ("en", 'Apple AI server HBM Samsung SK hynix Micron'),
    ("en", 'Apple server DRAM procurement LTA memory'),
    ("en", 'Apple NVHBM NVLink Fusion memory'),
    ("en", 'Apple AI server Broadcom M8 Ultra enterprise'),
]

HIGH_SOURCES = {
    "reuters", "the information", "bloomberg", "financial times", "wall street journal", "wsj",
    "apple", "nvidia", "broadcom", "trendforce", "semianalysis", "semi analysis",
    "samsung", "sk hynix", "micron", "tsmc",
}
MID_SOURCES = {
    "wallstreetcn", "华尔街见闻", "digitimes", "the elec", "tom's hardware", "toms hardware",
    "macrumors", "9to5mac", "zdnet", "전자신문", "etnews", "서울경제", "businesskorea",
}
LOW_SOURCES = {"wccftech", "technobezz", "biggo", "note.com", "ibtimes"}

APPLE = {"apple", "애플", "苹果"}
SERVER = {
    "m8 ultra", "m7 ultra", "enterprise server", "ai server", "server market", "server chip",
    "xserve", "private cloud compute", "pcc", "ai inference server", "엔터프라이즈 서버",
    "ai 서버", "서버 시장", "서버 칩", "추론 서버", "企业服务器", "服务器",
}
NVLINK = {"nvlink fusion", "nvlink", "nvhbm"}
MEMORY = {
    "hbm", "hbm4", "hbm4e", "nvhbm", "server dram", "rdimm", "socamm", "lpddr",
    "dram", "memory", "메모리", "서버 dram", "디램", "服务器dram", "内存",
}
SUPPLIERS = {
    "samsung", "samsung electronics", "삼성전자", "sk hynix", "sk하이닉스", "sk hynix",
    "micron", "마이크론", "broadcom", "브로드컴", "tsmc", "nvidia", "엔비디아",
}
PROCURE = {
    "order", "orders", "purchase", "procurement", "contract", "lta", "long-term agreement",
    "allocation", "reserve", "reservation", "supplier", "vendor", "supply deal", "design win",
    "buy", "bulk", "volume", "booking", "capacity reservation",
    "발주", "구매", "조달", "계약", "장기계약", "배정", "예약", "공급", "물량", "벌크",
    "采购", "订单", "供应", "长期协议", "产能预订",
}
MILESTONE = {
    "prototype", "tapeout", "tape-out", "validation", "sample", "sampling", "pilot",
    "mass production", "production", "launch", "ship", "shipment", "customer", "commercial",
    "adopt", "adoption", "partner", "partnership", "confirmed", "selected", "deploy",
    "시제품", "테이프아웃", "검증", "샘플", "시험생산", "양산", "출시", "출하", "고객",
    "채택", "협력", "확정", "선정", "배치", "原型", "流片", "验证", "量产", "发布",
}
FAIL = {
    "delay", "delayed", "cancel", "canceled", "cancelled", "pause", "paused", "suspend",
    "bottleneck", "shortage", "yield", "overheat", "thermal", "power", "abandon",
    "지연", "취소", "중단", "보류", "병목", "부족", "수율", "발열", "전력",
    "延期", "取消", "暂停", "瓶颈", "短缺", "良率",
}

BASELINE_TEXT = (
    "기준선: The Information/Reuters 보도상 Apple은 M8 Ultra 2개 또는 4개를 쓰는 기업용 AI 추론 서버를 "
    "검토 중이며 목표 시점은 이르면 2029년. NVIDIA NVLink Fusion은 '협의' 단계. "
    "Apple의 HBM·서버 DRAM 벌크 구매/LTA/공급사 배정은 미확인. NVLink Fusion 사용은 HBM 구매 확정이 아님."
)


def _rss_url(lang: str, q: str) -> str:
    params = {"q": q, "hl": "ko" if lang == "ko" else "en-US", "gl": "KR" if lang == "ko" else "US", "ceid": "KR:ko" if lang == "ko" else "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; khs-apple-server-watch/1.0)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def _clean(v: str | None) -> str:
    s = html.unescape(v or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm(v: str) -> str:
    s = _clean(v).lower()
    s = re.sub(r"[^0-9a-z가-힣一-龥%.$~+/-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_date(v: str | None) -> dt.datetime | None:
    if not v:
        return None
    try:
        x = parsedate_to_datetime(v)
        if x.tzinfo is None:
            x = x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(KST)
    except Exception:
        return None


def _source_rank(source: str) -> int:
    s = _norm(source)
    if any(x in s for x in HIGH_SOURCES):
        return 3
    if any(x in s for x in MID_SOURCES):
        return 2
    if any(x in s for x in LOW_SOURCES):
        return 0
    return 1


def _fp(item: dict) -> str:
    base = _norm(item["title"]) + "|" + _norm(item.get("source", ""))
    return hashlib.sha256(base.encode()).hexdigest()[:24]


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            d.setdefault("seen", [])
            d.setdefault("metrics", {})
            return d
        except Exception:
            pass
    return {
        "schema_version": 1,
        "baseline_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "seen": [],
        "metrics": {
            "target_year": 2029,
            "chip": "M8 Ultra",
            "processor_min": 2,
            "processor_max": 4,
            "nvlink_status": "talks",
            "hbm_procurement": "unconfirmed",
            "server_dram_procurement": "unconfirmed",
            "commercial_status": "reported_early_stage",
        },
        "last_alert": None,
    }


def _baseline_dt(state: dict) -> dt.datetime:
    try:
        x = dt.datetime.fromisoformat(str(state.get("baseline_at_utc")).replace("Z", "+00:00"))
        if x.tzinfo is None:
            x = x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(KST)
    except Exception:
        return dt.datetime.now(KST) - dt.timedelta(minutes=5)


def collect() -> tuple[list[dict], list[str]]:
    cutoff = dt.datetime.now(KST) - dt.timedelta(days=10)
    out, errors = [], []
    for lang, q in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, q)))
            for node in root.findall(".//item"):
                title = _clean(node.findtext("title"))
                link = _clean(node.findtext("link"))
                desc = _clean(node.findtext("description"))
                source_node = node.find("source")
                source = _clean(source_node.text if source_node is not None else "")
                published = _parse_date(node.findtext("pubDate"))
                if not title or not link or (published and published < cutoff):
                    continue
                out.append({"title": title, "link": link, "description": desc, "source": source, "published": published.isoformat(timespec="seconds") if published else None})
        except Exception as e:
            errors.append(f"{lang}:{q[:45]} -> {type(e).__name__}: {e}")
    dedup = {}
    for row in out:
        dedup.setdefault(_fp(row), row)
    return list(dedup.values()), errors


def _has(blob: str, words: set[str]) -> bool:
    b = blob.lower()
    return any(w in b for w in words)


def _years(blob: str) -> list[int]:
    return [int(x) for x in re.findall(r"\b(20\d{2})\b", blob) if 2026 <= int(x) <= 2035]


def _memory_sizes(blob: str) -> list[float]:
    vals = []
    for n, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(TB|terabytes?|GB|gigabytes?)", blob, flags=re.I):
        x = float(n)
        vals.append(x if unit.lower().startswith("t") else x / 1024.0)
    return vals


def _stage(blob: str) -> int:
    b = blob.lower()
    if any(x in b for x in ("mass production", "shipment", "shipments", "commercial launch", "양산", "출하", "正式出货")):
        return 4
    if _has(b, PROCURE) or any(x in b for x in ("customer trial", "customer validation", "pilot", "고객 검증", "시험생산")):
        return 3
    if _has(b, MILESTONE) or _has(b, NVLINK):
        return 2
    return 1


def _event_type(blob: str) -> str:
    b = blob.lower()
    if _has(b, FAIL):
        return "실패모드·일정 변화"
    if _has(b, MEMORY) and (_has(b, PROCURE) or _has(b, SUPPLIERS)):
        return "서버 메모리 조달"
    if _has(b, NVLINK):
        return "NVIDIA·NVLink Fusion"
    if _has(b, SERVER):
        return "Apple 기업용 AI 서버"
    return "Apple AI 인프라"


def _material(item: dict, state: dict, corroboration: dict[str, set[str]]) -> tuple[bool, str, int, str]:
    blob = _norm(f"{item['title']} {item.get('description','')} {item.get('source','')}")
    if not _has(blob, APPLE):
        return False, "", 0, ""
    if not (_has(blob, SERVER) or _has(blob, NVLINK) or (_has(blob, MEMORY) and _has(blob, PROCURE))):
        return False, "", 0, ""
    rank = _source_rank(item.get("source", ""))
    if rank == 0:
        return False, "", 0, ""

    et = _event_type(blob)
    stage = _stage(blob)
    reasons = []
    years = _years(blob)
    mem_tb = _memory_sizes(blob)
    metrics = state.get("metrics") or {}

    if years and any(y != int(metrics.get("target_year") or 2029) for y in years):
        reasons.append("기존 2029 목표와 다른 일정 숫자")
    if "m8 ultra" in blob and _has(blob, MILESTONE):
        reasons.append("M8 Ultra 개발 단계 변화")
    if _has(blob, NVLINK) and any(x in blob for x in ("adopt", "selected", "confirmed", "partnership", "deploy", "cancel", "채택", "확정", "선정", "협력", "취소")):
        reasons.append("NVLink Fusion 상태가 '협의'보다 진전/후퇴")
    if _has(blob, MEMORY) and _has(blob, PROCURE) and _has(blob, SUPPLIERS):
        reasons.append("Apple+메모리+공급사+조달 행위 동시 확인")
    if mem_tb:
        reasons.append("서버/칩 메모리 용량 수치 등장")
    if _has(blob, FAIL):
        reasons.append("지연·취소·수율·발열·메모리 부족 등 실패모드")
    if any(x in blob for x in ("enterprise customers", "business customers", "government", "commercial sale", "기업 고객", "정부", "판매")) and _has(blob, MILESTONE):
        reasons.append("기업 판매/고객 검증 단계 변화")

    # A high-quality source may trigger on a clear new milestone. Medium sources require
    # either a concrete numeric/party signal or same-event corroboration by 2+ sources.
    material = bool(reasons)
    corroborated = len(corroboration.get(et, set())) >= 2
    if rank == 1:
        return False, "", 0, ""
    if rank == 2 and not (corroborated or mem_tb or (_has(blob, SUPPLIERS) and _has(blob, PROCURE))):
        return False, "", 0, ""
    if not material:
        return False, "", 0, ""

    confidence = "높음" if rank >= 3 else "중간·복수 출처 확인"
    return True, et, stage, confidence + " | " + " / ".join(reasons[:3])


def _confirm_memory(blob: str, rank: int, corroborated: bool) -> str:
    b = blob.lower()
    if not (_has(b, MEMORY) and _has(b, PROCURE) and _has(b, SUPPLIERS)):
        return "미확정"
    if rank >= 3 or corroborated:
        if "hbm" in b or "nvhbm" in b:
            return "HBM 조달 신호 확인"
        if "server dram" in b or "rdimm" in b or "서버 dram" in b:
            return "서버 DRAM 조달 신호 확인"
    return "보도 단계"


def _escape(s: str) -> str:
    return html.escape(_clean(s), quote=False)


def _format(rows: list[dict], state: dict) -> str:
    lines = [
        "🚨 <b>[Apple 기업용 AI 서버·메모리 감시]</b>",
        f"<i>{dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}</i>",
        "",
    ]
    for i, r in enumerate(rows[:4], 1):
        blob = _norm(r["title"] + " " + r.get("description", ""))
        rank = _source_rank(r.get("source", ""))
        memory_status = _confirm_memory(blob, rank, r.get("corroborated", False))
        lines += [
            f"<b>{i}. 무엇이 달라졌나</b>",
            f"• {_escape(r['title'])}",
            f"• <b>현재 판정:</b> {_escape(r['event_type'])}",
            f"• <b>확인도:</b> {r['stage']}/4",
            f"• <b>메모리 판정:</b> {_escape(memory_status)}",
            f"• <b>신뢰도:</b> {_escape(r['reason'])}",
            f"• <b>출처:</b> {_escape(r.get('source') or '미상')}",
            f"• <a href=\"{html.escape(r['link'], quote=True)}\">원문 보기</a>",
            "",
        ]
    lines += [
        "<b>해석 잠금</b>",
        "• NVLink Fusion 채택/협의는 HBM 구매 확정이 아닙니다.",
        "• 모바일 DRAM 가격 압박만으로 Apple의 서버 DRAM·HBM 벌크구매를 추정해 알리지 않습니다.",
        "• HBM/서버 DRAM은 Apple 또는 공급사 실명 + 발주·계약·배정이 확인될 때 별도 상향 판정합니다.",
        "",
        "<b>현재 기준선</b>",
        "• " + _escape(BASELINE_TEXT),
        "",
        "<b>다음 확인</b>",
        "• M8 Ultra 테이프아웃/검증 → NVLink Fusion 공식 채택 → Samsung·SK hynix·Micron 메모리 계약 → 기업 고객 검증 → 양산·출하 순으로 확인합니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_PATH.unlink(missing_ok=True)
    state = _load_state()
    seen = set(state.get("seen") or [])
    baseline = _baseline_dt(state)
    items, errors = collect()

    # First pass: independent source count by event class.
    corroboration: dict[str, set[str]] = defaultdict(set)
    for it in items:
        blob = _norm(it["title"] + " " + it.get("description", "") + " " + it.get("source", ""))
        if _has(blob, APPLE) and (_has(blob, SERVER) or _has(blob, NVLINK) or (_has(blob, MEMORY) and _has(blob, PROCURE))):
            corroboration[_event_type(blob)].add(_norm(it.get("source", "")) or it["title"])

    candidates, new_seen = [], list(seen)
    for it in sorted(items, key=lambda x: x.get("published") or "", reverse=True):
        fp = _fp(it)
        if fp in seen:
            continue
        new_seen.append(fp)
        published = None
        if it.get("published"):
            try:
                published = dt.datetime.fromisoformat(it["published"]).astimezone(KST)
            except Exception:
                pass
        if published and published <= baseline:
            continue
        ok, et, stage, reason = _material(it, state, corroboration)
        if not ok:
            continue
        row = dict(it)
        row.update({
            "fingerprint": fp,
            "event_type": et,
            "stage": stage,
            "reason": reason,
            "corroborated": len(corroboration.get(et, set())) >= 2,
        })
        candidates.append(row)

    pending = json.loads(json.dumps(state, ensure_ascii=False))
    pending["seen"] = list(dict.fromkeys(new_seen))[-900:]
    pending["last_scan_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    pending["errors"] = errors[-20:]
    if candidates:
        pending["last_alert"] = {
            "at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            "fingerprints": [x["fingerprint"] for x in candidates[:4]],
            "event_types": [x["event_type"] for x in candidates[:4]],
        }
        ALERT_PATH.write_text(_format(candidates, state), encoding="utf-8")

    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS_PATH.write_text(
        "# Apple 기업용 AI 서버·메모리 감시\n\n"
        f"- 실행시각: {dt.datetime.now(KST).isoformat(timespec='seconds')}\n"
        f"- 수집항목: {len(items)}\n"
        f"- 신규 의미있는 변화: {len(candidates)}\n"
        f"- 오류: {len(errors)}\n"
        f"- 텔레그램 알림파일: {'생성' if ALERT_PATH.exists() else '없음'}\n\n"
        f"## 기준선\n- {BASELINE_TEXT}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
