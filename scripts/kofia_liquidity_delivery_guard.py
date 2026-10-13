"""Verify Telegram's returned recipient and rendered text before saving a receipt."""
import datetime as dt
import hashlib
from html.parser import HTMLParser
import re


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def validate_acknowledgement(response, html, expected_bot, expected_chat):
    result = response.get('result') or {}
    mid = result.get('message_id')
    if response.get('ok') is not True or type(mid) is not int or mid <= 0:
        raise RuntimeError('Telegram response lacks confirmed positive integer message_id')
    sender = result.get('from') or {}
    if sender.get('is_bot') is not True or str(sender.get('username') or '').lower() != expected_bot.lower().lstrip('@'):
        raise RuntimeError('Telegram returned message sender differs from verified bot')
    chat = result.get('chat') or {}
    expected = str(expected_chat).strip()
    if re.fullmatch(r'-?\d+', expected):
        if type(chat.get('id')) is not int or chat['id'] != int(expected):
            raise RuntimeError('Telegram returned recipient differs from configured chat')
    elif expected.startswith('@'):
        if str(chat.get('username') or '').lower() != expected[1:].lower():
            raise RuntimeError('Telegram returned recipient differs from configured channel')
    else:
        raise RuntimeError('Unsupported Telegram recipient format; refuse unverified receipt')
    parsed = PlainText()
    parsed.feed(html)
    parsed.close()
    plain = ''.join(parsed.parts)
    if result.get('text') != plain:
        raise RuntimeError('Telegram returned rendered text differs from validated message')
    date = result.get('date')
    if type(date) is not int or date <= 0:
        raise RuntimeError('Telegram confirmation lacks server message time')
    return {
        'message_id': mid,
        'telegram_date_utc': dt.datetime.fromtimestamp(date, dt.timezone.utc).isoformat(),
        'telegram_chat_id_sha256': hashlib.sha256(str(chat['id']).encode()).hexdigest(),
        'telegram_rendered_text': plain,
        'telegram_rendered_text_sha256': hashlib.sha256(plain.encode()).hexdigest(),
    }
