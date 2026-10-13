"""Preserve a newer confirmed baseline when Git state advances during delivery."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

KEYS = ('deposit', 'mmf', 'cma', 'credit', 'receivable', 'forced')


def verified(data):
    payload = {key: data['values'][key] for key in KEYS}
    actual = hashlib.sha256(json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    if actual != data['fingerprint']:
        raise RuntimeError('KOFIA state fingerprint inconsistent; refusing overwrite')
    return data


def keep_incoming(current, incoming):
    verified(current)
    verified(incoming)
    receipt = incoming.get('delivery_receipt') or {}
    if type(receipt.get('message_id')) is not int or receipt['message_id'] <= 0:
        raise RuntimeError('KOFIA incoming state has no confirmed delivery')
    stamp = dt.datetime.fromisoformat(receipt['timestamp_utc'])
    if stamp.utcoffset() is None:
        raise RuntimeError('KOFIA delivery timestamp lacks timezone')
    if current['snapshot_date'] > incoming['snapshot_date']:
        return False
    if current['snapshot_date'] == incoming['snapshot_date']:
        current_receipt = current.get('delivery_receipt') or {}
        if current_receipt.get('timestamp_utc'):
            previous = dt.datetime.fromisoformat(current_receipt['timestamp_utc'])
            if previous.utcoffset() is None:
                raise RuntimeError('KOFIA current receipt timezone missing')
            if previous > stamp:
                return False
        if current['fingerprint'] not in (incoming['fingerprint'], incoming['prior_fingerprint']):
            raise RuntimeError('KOFIA confirmed state changed during delivery; preserve current state')
    return True


if __name__ == '__main__':
    destination = Path('data/kofia_liquidity_state.json')
    incoming = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    current = json.loads(destination.read_text(encoding='utf-8'))
    if keep_incoming(current, incoming):
        destination.write_text(json.dumps(incoming, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('kofia_state_apply_confirmed=true')
    else:
        print('kofia_state_keep_newer_confirmed=true')
