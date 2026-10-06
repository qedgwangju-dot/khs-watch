#!/usr/bin/env python3
from __future__ import annotations

import asyncio, json, os
from pathlib import Path
import ebest

OUT=Path("out/ls_unified_flow_probe.json")

async def main():
    appkey=(os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    appsecret=(os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not appkey or not appsecret:
        raise RuntimeError("LS secrets missing")
    api=ebest.OpenApi()
    received=[]
    try:
        if not await api.login(appkey,appsecret):
            raise RuntimeError(f"login failed: {api.last_message}")
        def on_message(api_obj,msg):
            received.append({"type":"message","msg":str(msg)[:500]})
        def on_realtime(api_obj,trcode,key,realtimedata):
            received.append({
                "type":"realtime","trcode":str(trcode),"key":str(key),
                "data":realtimedata if isinstance(realtimedata,dict) else str(realtimedata)[:1000],
            })
        api.on_message.connect(on_message)
        api.on_realtime.connect(on_realtime)

        # 통합 시장/업종/프로그램/종목 프로그램 후보 등록.
        regs=[("UBT","U001"),("UBM","U001"),("UPM","01"),("UPH","U005930   ")]
        results=[]
        for tr,key in regs:
            try:
                ok=await api.add_realtime(tr,key)
                results.append({"tr":tr,"key":key,"ok":bool(ok),"last_message":str(api.last_message)[:500]})
            except Exception as exc:
                results.append({"tr":tr,"key":key,"ok":False,"error":f"{type(exc).__name__}: {exc}"})
        await asyncio.sleep(90)
        for tr,key in regs:
            try: await api.remove_realtime(tr,key)
            except Exception: pass
        out={"registrations":results,"received":received[:100]}
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({
            "registrations":results,
            "received_count":len(received),
            "trcodes":sorted({str(x.get("trcode")) for x in received if x.get("type")=="realtime"}),
            "data_keys":{str(x.get("trcode")):sorted((x.get("data") or {}).keys()) for x in received if x.get("type")=="realtime" and isinstance(x.get("data"),dict)}
        },ensure_ascii=False))
        realtime_trs={
            str(x.get("trcode")) for x in received
            if x.get("type")=="realtime"
        }
        realtime_seen=bool(realtime_trs)
        registration_ok=all(bool(x.get("ok")) for x in results)
        if not registration_ok:
            raise RuntimeError(f"one or more unified realtime registrations failed: {results}")
        import datetime as dt
        from zoneinfo import ZoneInfo
        now=dt.datetime.now(ZoneInfo("Asia/Seoul"))
        market_hours=(now.weekday()<5 and dt.time(9,0)<=now.time()<=dt.time(15,20))
        if market_hours and "UBM" not in realtime_trs:
            raise RuntimeError(
                f"unified industry realtime payload missing during 90s market-hours probe: {sorted(realtime_trs)}"
            )
        print(
            "unified_realtime_registration_valid=true "
            f"realtime_payload_seen={str(realtime_seen).lower()} "
            f"realtime_trcodes={sorted(realtime_trs)} market_hours={str(market_hours).lower()}"
        )
        return 0
    finally:
        try: await api.close()
        except Exception: pass

if __name__=="__main__":
    raise SystemExit(asyncio.run(main()))
