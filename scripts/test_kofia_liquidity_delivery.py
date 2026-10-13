"""Offline acknowledgements only: never connect to or send Telegram."""
import copy
import unittest

from kofia_liquidity_delivery_guard import validate_acknowledgement

HTML = '<b>예탁금 +0.33조</b>\nMMF &amp; CMA'
ACK = {'ok': True, 'result': {'message_id': 1, 'date': 1791892800,
       'from': {'is_bot': True, 'username': 'fixture_bot'},
       'chat': {'id': -1001234567890}, 'text': '예탁금 +0.33조\nMMF & CMA'}}


class DeliveryTests(unittest.TestCase):
    def verify(self, value):
        return validate_acknowledgement(value, HTML, 'fixture_bot', '-1001234567890')

    def test_exact_recipient_and_rendered_content(self):
        self.assertEqual(self.verify(ACK)['message_id'], 1)

    def test_boolean_message_id_is_not_confirmation(self):
        value = copy.deepcopy(ACK); value['result']['message_id'] = True
        with self.assertRaisesRegex(RuntimeError, 'message_id'): self.verify(value)

    def test_wrong_recipient_cannot_advance_state(self):
        value = copy.deepcopy(ACK); value['result']['chat']['id'] += 1
        with self.assertRaisesRegex(RuntimeError, 'recipient'): self.verify(value)

    def test_wrong_rendered_amount_cannot_advance_state(self):
        value = copy.deepcopy(ACK); value['result']['text'] = value['result']['text'].replace('+0.33', '-0.33')
        with self.assertRaisesRegex(RuntimeError, 'rendered text'): self.verify(value)

    def test_wrong_sender_cannot_advance_state(self):
        value = copy.deepcopy(ACK); value['result']['from']['username'] = 'other_bot'
        with self.assertRaisesRegex(RuntimeError, 'sender'): self.verify(value)

    def test_missing_server_time_cannot_advance_state(self):
        value = copy.deepcopy(ACK); value['result'].pop('date')
        with self.assertRaisesRegex(RuntimeError, 'server message time'): self.verify(value)


if __name__ == '__main__':
    unittest.main()
