"""Offline checks; never send or edit Telegram while testing."""
import hashlib
import io
import json
import zipfile
import unittest
from unittest.mock import patch

import robot_watch_single_message_correction_404 as fix
import robot_watch_delivery as d

class ScopedCorrectionCheck(unittest.TestCase):
    def test_pinned_run_message_and_actual_prior_key(self):
        self.assertEqual(fix.RUN_ID,45103989370)
        self.assertEqual(fix.MESSAGE_ID,404)
        self.assertEqual(fix.EXISTING_KEY,"44e38c418d8b624501e53e833075280cbb24234df30454c4e1425da953799ffb")
        self.assertNotEqual(fix.EXISTING_KEY,fix.DUPLICATE_KEY)

    def test_exactly_fifth_article_removed_and_header_corrected(self):
        blocks="\n\n".join(f'<b>{i}. 기사{i}</b>\n<a href="https://example.org/{i}">원문</a>'
                          for i in range(1,6))
        text="<b>신규 고신호 5건</b>\n\n"+blocks+"\n<b>판정 기준</b> 검사"
        expected="<b>신규 고신호 4건</b>\n\n"+"\n\n".join(
            f'<b>{i}. 기사{i}</b>\n<a href="https://example.org/{i}">원문</a>'
            for i in range(1,5))+"\n<b>판정 기준</b> 검사"
        expected_sha=d._digest(expected)
        with patch.object(fix,"CORRECTED_SHA",expected_sha):
            result=fix.corrected_text(text)
        self.assertEqual(result,expected)
        self.assertNotIn("기사5",result)
        self.assertEqual(result.count("<b>판정 기준</b>"),1)

    def test_other_structure_or_checksum_fails_closed(self):
        text="<b>신규 고신호 5건</b>\n"+''.join(f'<b>{i}. 기사</b>\n' for i in range(1,5))+"<b>판정 기준</b>"
        with self.assertRaises(d.DeliveryError):
            fix.corrected_text(text)

    def test_zip_digest_and_member_scope(self):
        files={d.ALERT_PATH.name:"fixture"}
        def encode(rows):
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w") as z:
                for name,body in rows.items(): z.writestr(name,body)
            return buf.getvalue()
        raw=encode(files)
        digest="sha256:"+hashlib.sha256(raw).hexdigest()
        metadata={"name":f"robotis-physical-ai-{fix.RUN_ID}","expired":False,"digest":digest}
        with patch.object(fix,"ARTIFACT_SHA",digest):
            self.assertEqual(fix.parse_artifact(raw,metadata),files)
            with self.assertRaises(d.DeliveryError):
                fix.parse_artifact(encode({"some-other-message.txt":"bad"}),metadata)
            with self.assertRaises(d.DeliveryError):
                fix.parse_artifact(raw,dict(metadata,digest="sha256:"+"0"*64))

if __name__=="__main__":unittest.main()
