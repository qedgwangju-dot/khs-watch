#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import html
import os
from typing import Any

import ebest

import kospi_derivatives_flow_ls_realtime as base
from kospi_flow_attribution_ls import attribution_html_lines, fetch_attribution


class AttributionRealtimeWatch(base.RealtimeWatch):
    """실시간 가격·파생 경보에 같은 시점의 현물/선물/프로그램 주체 수급을 결합한다."""

    def alert_text(self, level: int, m: dict[str, Any]) -> str:
        original = super().alert_text(level, m)
        try:
            flow = fetch_attribution(token=self.ls_token, window_minutes=15)
            flow_lines = attribution_html_lines(flow)
            pgm = flow.get("program") or {}
            pgm_delta = pgm.get("delta") or {}
            cls = flow.get("classification") or {}

            extra = [
                "",
                "<b>현물·선물·프로그램 교차판정</b>",
                *flow_lines,
            ]
            if not pgm.get("stale") and pgm.get("base_time"):
                def raw(v: Any) -> str:
                    try:
                        n = float(v)
                        return f"{n:+,.0f}"
                    except Exception:
                        return "확인 불가"
                extra += [
                    "",
                    "<b>프로그램매매 15분 변화 · LS 보고값</b>",
                    f"• 전체 <b>{raw(pgm_delta.get('전체'))}</b> · 차익 <b>{raw(pgm_delta.get('차익'))}</b> · 비차익 <b>{raw(pgm_delta.get('비차익'))}</b>",
                    "• LS 공개 문서가 해당 변화값의 환산 단위를 명시하지 않아 임의로 억원 표기하지 않음",
                ]
            else:
                extra += [
                    "",
                    "<b>프로그램매매 15분 변화</b>",
                    "• 해당 구간 표본 부족 — 프로그램을 원인으로 단정하지 않음",
                ]

            verdict = str(cls.get("verdict") or "판정 불가")
            confidence = str(cls.get("confidence") or "낮음")
            extra += [
                "",
                "<b>최종 매도주체 판정</b>",
                f"• <b>{html.escape(verdict)}</b> · 확신도 {html.escape(confidence)}",
                "• 하루 누적 현물 수급이 아니라 급락 직전 15분의 현물·KOSPI200·선물 변화와 프로그램 동조를 우선함",
            ]
            return original + "\n" + "\n".join(extra)
        except Exception as exc:
            return original + "\n\n" + "\n".join([
                "<b>현물·선물·프로그램 교차판정</b>",
                f"• LS 주체별 수급 조회 실패 — 매도주체 확정 보류 ({html.escape(type(exc).__name__)})",
                "• 가격 경보는 유지하되 현물 누적값만으로 원인을 단정하지 않음",
            ])


async def async_main(test: bool, test_seconds: int) -> int:
    now = dt.datetime.now(base.KST)
    if not test:
        if now.weekday() >= 5:
            base.STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
            base.STATUS_PATH.write_text(
                f"# 코스피 LS 실시간 파생·수급 감시 v2\n\n- 상태: 주말\n- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n",
                encoding="utf-8",
            )
            return 0
        if now.time() < base.START_TIME:
            target = dt.datetime.combine(now.date(), base.START_TIME, tzinfo=base.KST)
            await asyncio.sleep(max(0.0, (target - now).total_seconds()))
        if dt.datetime.now(base.KST).time() >= base.END_TIME:
            return 0

    appkey = (os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    appsecret = (os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not appkey or not appsecret:
        raise RuntimeError("LS OpenAPI secrets missing")

    ls_token = await asyncio.to_thread(base.get_ls_token)
    current200 = await asyncio.to_thread(base.fetch_kpi200)
    weekly_puts = await asyncio.to_thread(base.get_weekly_puts, ls_token, current200)

    api = ebest.OpenApi()
    if not await api.login(appkey, appsecret):
        raise RuntimeError(f"LS login failed: {api.last_message}")

    watch = AttributionRealtimeWatch(api, ls_token, weekly_puts, test=test)
    started = dt.datetime.now(base.KST)
    try:
        await watch.run(seconds=test_seconds if test else None)
        base.write_status(watch, started, "정상 종료 · 현물/선물/프로그램 교차판정 v2")
        return 0
    except Exception as exc:
        base.write_status(watch, started, f"오류: {type(exc).__name__}: {exc}")
        raise
    finally:
        try:
            await api.close()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--test-seconds", type=int, default=8)
    args = ap.parse_args()
    return asyncio.run(async_main(args.test, args.test_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
