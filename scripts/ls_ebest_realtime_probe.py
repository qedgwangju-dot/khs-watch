#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import ebest

OUT = Path('out/ls_ebest_realtime_probe.json')


async def main() -> int:
    appkey = (os.getenv('LS_OPENAPI_APP_KEY') or '').strip()
    appsecret = (os.getenv('LS_OPENAPI_APP_SECRET') or '').strip()
    if not appkey or not appsecret:
        raise RuntimeError('LS OpenAPI secrets missing')

    api = ebest.OpenApi()
    if not await api.login(appkey, appsecret):
        raise RuntimeError(f'LS login failed: {api.last_message}')

    received: list[dict] = []

    def on_message(api_obj, msg):
        received.append({'type': 'message', 'msg': str(msg)[:300]})

    def on_realtime(api_obj, trcode, key, realtimedata):
        received.append({
            'type': 'realtime',
            'trcode': str(trcode),
            'key': str(key),
            'data_keys': sorted(list(realtimedata.keys()))[:50] if isinstance(realtimedata, dict) else [],
        })

    api.on_message.connect(on_message)
    api.on_realtime.connect(on_realtime)

    # Current index-futures master.
    rsp = await api.request('t8467', {'t8467InBlock': {'gubun': '1'}})
    if not rsp:
        raise RuntimeError(f't8467 failed: {api.last_message}')
    futures = rsp.body.get('t8467OutBlock') or []
    futcode = str((futures[0] if futures else {}).get('shcode') or '').strip()

    # Current weekly option master. WK worked in the REST credential probe.
    wrsp = await api.request('t8435', {'t8435InBlock': {'gubun': 'WK'}})
    weekly = (wrsp.body.get('t8435OutBlock') or []) if wrsp else []
    optcode = str((weekly[0] if weekly else {}).get('shcode') or '').strip()

    registrations = []
    checks = [
        ('IJ_', '001'),
        ('PM_', '001'),
    ]
    if futcode:
        checks.append(('FC0', futcode))
    if optcode:
        checks.append(('OC0', optcode))

    for tr_cd, key in checks:
        ok = await api.add_realtime(tr_cd, key)
        registrations.append({'tr_cd': tr_cd, 'key': key, 'ok': bool(ok), 'last_message': str(api.last_message)[:300]})

    await asyncio.sleep(3)

    for tr_cd, key in checks:
        try:
            await api.remove_realtime(tr_cd, key)
        except Exception:
            pass

    api.on_message.disconnect(on_message)
    api.on_realtime.disconnect(on_realtime)
    await api.close()

    result = {
        'login': True,
        'front_future': futcode,
        'weekly_option_sample': optcode,
        'registrations': registrations,
        'received': received[:30],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'login': True,
        'front_future': futcode,
        'weekly_option_sample': optcode,
        'registration_ok': {x['tr_cd']: x['ok'] for x in registrations},
        'received_count': len(received),
    }, ensure_ascii=False))

    if not all(x['ok'] for x in registrations):
        raise RuntimeError('One or more LS realtime registrations failed')
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
