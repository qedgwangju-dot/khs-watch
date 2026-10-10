#!/usr/bin/env python3
"""공유 저장소에서 최신 Warsh 금리경로 상태를 안전하게 동기화한다.

GitHub Actions의 이전 실행이 상태를 push한 직후라도 이전 checkout 상태를
다시 읽어 중복 텔레그램 경고를 보내지 않도록 하는 직렬화 안전장치.
실제 리포트 수치·가공 없이 상태만 확인한다.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess

STATE=Path("data/warsh_policy_path_watch_state.json")
REF="origin/main:"+STATE.as_posix()


def checked_json(text, name):
    try:
        result=json.loads(text)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{name} Warsh 상태 JSON 손상") from exc
    if not isinstance(result,dict):
        raise RuntimeError(f"{name} Warsh 상태 최상위 객체 오류")
    return result


def iso(value):
    try:
        timestamp=datetime.fromisoformat(str(value or "").replace("Z","+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("timezone missing")
        return timestamp.astimezone(timezone.utc)
    except (TypeError,ValueError) as exc:
        raise RuntimeError("Warsh 상태 갱신 시각 확인 실패") from exc


def reconcile(local, remote):
    if not isinstance(local,dict) or not isinstance(remote,dict):
        raise RuntimeError("Warsh 상태 형식 불일치")
    if not local or not local.get("updated_at_utc"):
        return dict(remote), "remote_initial"
    if not remote or not remote.get("updated_at_utc"):
        raise RuntimeError("원격 Warsh 상태 갱신시각 없음")
    lt=iso(local["updated_at_utc"])
    rt=iso(remote["updated_at_utc"])
    if rt>lt:
        return dict(remote), "remote_newer"
    if lt>rt:
        return dict(local), "local_newer"
    # 동일 시각이지만 메시지 전송 영수증이 한쪽에만 있으면 영수증이 있는
    # 쪽을 우선해 불필요한 중복 발송 위험을 낮춘다.
    rmid=remote.get("last_health_message_id")
    lmid=local.get("last_health_message_id")
    if isinstance(rmid,int) and rmid>0 and not lmid:
        return dict(remote), "remote_receipt"
    if isinstance(lmid,int) and lmid>0 and not rmid:
        return dict(local), "local_receipt"
    if local!=remote:
        raise RuntimeError("동일 갱신시각의 Warsh 상태가 서로 다름 — 중복 발송 방지 중단")
    return dict(local), "equal"


def main():
    # GitHub Actions 단계에서 직전에 git fetch origin main을 마친다.
    result=subprocess.run(["git","show",REF],capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError("GitHub 최신 Warsh 상태 조회 실패 — 기존 상태로 감시 재개 금지")
    remote=checked_json(result.stdout,"원격")
    local=checked_json(STATE.read_text(encoding="utf-8"),"로컬") if STATE.exists() else {}
    chosen, why=reconcile(local,remote)
    if chosen != local:
        STATE.parent.mkdir(parents=True,exist_ok=True)
        temp=STATE.with_suffix(".sync.tmp")
        temp.write_text(json.dumps(chosen,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        os.replace(temp,STATE)
    print(json.dumps({
        "warsh_policy_state_sync":why,
        "status":chosen.get("source_status"),
        "health_alerted":bool(chosen.get("source_health_alerted")),
        "last_health_message_id":chosen.get("last_health_message_id"),
    },ensure_ascii=False))


if __name__=="__main__":
    main()
