"""CSV preview from run 38156218314; remaining cases are synthetic fixtures."""
import datetime as dt
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import lng_supply_crisis_alert_v34 as monitor
import lng_supply_crisis_alert_v22 as parser
import lng_supply_crisis_alert_v20 as bonds

PREVIEW=ROOT/'tests/fixtures/bundesbank_run38156218314_preview.csv'

def rows(delimiter=',',decimal='.',quoted=False):
    out=[]
    for day,value in [('2026-08-04','3.00'),('2026-10-07','4.70'),('2026-10-09','4.78')]:
        value=value.replace('.',decimal)
        if quoted:
            day='"'+day+'"';value='"'+value+'"'
        out.append(delimiter.join([day,value,'']))
    return ('\n'.join(out)+'\n').encode()

class BundesbankCsvTest(unittest.TestCase):
    def test_exact_failed_response_preview_parses_date_first_comma_columns(self):
        result=parser.parse_bundesbank_csv_v22(PREVIEW.read_bytes())
        self.assertEqual(result[0],(dt.date(2001,10,1),4.78))
        self.assertEqual(result[-1],(dt.date(2001,10,9),4.66))
        self.assertEqual(len(result),7)
        self.assertNotIn(dt.date(2026,10,9),dict(result)) # Metadata update is not an observation.
        self.assertNotIn(dt.date(2001,10,6),dict(result)) # Missing-value flag is not a yield.

    def test_delimiters_quoted_dates_and_decimal_variants(self):
        for delimiter,decimal,quoted in [(',', '.',False),(',', '.',True),(',', ',',True),(';','.',False),(';',',',False),(';',',',True),('\t','.',False)]:
            with self.subTest(delimiter=delimiter,decimal=decimal,quoted=quoted):
                result=parser.parse_bundesbank_csv_v22(rows(delimiter,decimal,quoted))
                self.assertEqual(result[-1],(dt.date(2026,10,9),4.78))
                self.assertEqual(len(result),3)

    def test_metadata_and_flag_numbers_are_not_observations(self):
        extra=b'last update,2026-10-11 12:07:51,4.78\n"note 2026-10-10",3.2,\n2026-10-10,.,5.5\n2026-10-11,N/A,4.7\n2026-10-12,NaN,\n2026-10-13,Infinity,\n2026-10-14,4.5junk,\n2026-02-30,4.5,\n'
        self.assertEqual(parser.parse_bundesbank_csv_v22(rows()+extra),parser.parse_bundesbank_csv_v22(rows()))

    def test_bom_crlf_and_quoted_flag_comma(self):
        raw=b'\xef\xbb\xbf'+rows().replace(b'\n',b'\r\n')+b'2026-10-10,4.72,"provisional, revised"\r\n'
        self.assertEqual(parser.parse_bundesbank_csv_v22(raw)[-1][1],4.72)

    def test_unquoted_decimal_comma_is_ambiguous_not_integer_yield(self):
        with self.assertRaisesRegex(RuntimeError,'ambiguous'):
            parser.parse_bundesbank_csv_v22(rows()+b'2026-10-10,4,78\n')

    def test_mixed_delimiters_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'delimiters disagree'):
            parser.parse_bundesbank_csv_v22(rows()+b'2026-10-10;4.78;\n')

    def test_implausible_values_still_fail_closed(self):
        for value in ('8.01','-1.01','1000'):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError,'implausible'):
                parser.parse_bundesbank_csv_v22(rows()+f'2026-10-10,{value},\n'.encode())

    def test_malformed_csv_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'malformed'):
            parser.parse_bundesbank_csv_v22(rows()+b'2026-10-10,"4.78\n')

    def test_too_few_valid_observations_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'data rows not found'):
            parser.parse_bundesbank_csv_v22(b'last update,2026-10-09 12:07:51,\n2026-10-09,4.78,\n')

    def test_active_v34_bond_parser_is_fixed_v22(self):
        self.assertIs(bonds.parse_bundesbank_csv,parser.parse_bundesbank_csv_v22)

    def test_historical_preview_remains_stale(self):
        with patch.object(monitor.core,'now_utc',return_value=dt.datetime(2026,10,11,tzinfo=dt.timezone.utc)), self.assertRaisesRegex(RuntimeError,'stale'):
            bonds._series_snapshot(parser.parse_bundesbank_csv_v22(PREVIEW.read_bytes()),'Bundesbank')

    def test_future_dates_remain_rejected(self):
        with patch.object(monitor.core,'now_utc',return_value=dt.datetime(2026,10,8,tzinfo=dt.timezone.utc)), self.assertRaisesRegex(RuntimeError,'stale'):
            bonds._series_snapshot(parser.parse_bundesbank_csv_v22(rows()),'Bundesbank')

    def test_missing_aug4_anchor_remains_rejected(self):
        raw=rows().replace(b'2026-08-04',b'2026-08-05')
        with patch.object(monitor.core,'now_utc',return_value=dt.datetime(2026,10,10,tzinfo=dt.timezone.utc)), self.assertRaisesRegex(RuntimeError,'missing Aug 4'):
            bonds._series_snapshot(parser.parse_bundesbank_csv_v22(raw),'Bundesbank')

    def test_official_bonds_keep_shared_date_and_basis_point_arithmetic(self):
        treasury=b'<feed>'+b''.join(f'<entry><NEW_DATE>{day}</NEW_DATE><BC_10YEAR>{value}</BC_10YEAR></entry>'.encode() for day,value in [('2026-08-04',4.00),('2026-10-07',4.50),('2026-10-08',4.55)])+b'</feed>'
        def fetch(url):
            if url==bonds.BUNDESBANK_10Y_CSV:return rows()
            if url==bonds.UST_XML_2026:return treasury
            raise AssertionError('unexpected official source')
        with patch.object(bonds,'_fetch_bytes',side_effect=fetch),patch.object(monitor.core,'now_utc',return_value=dt.datetime(2026,10,10,tzinfo=dt.timezone.utc)):
            bund,us=bonds.fetch_official_bond_snapshots()
        self.assertEqual(bund['latest_date'],dt.date(2026,10,9))
        self.assertEqual(us['latest_date'],dt.date(2026,10,8))
        self.assertEqual(bund['common_date'],dt.date(2026,10,7))
        self.assertEqual(us['common_date'],bund['common_date'])
        self.assertAlmostEqual(bund['common_since_aug4_bp'],170)
        self.assertAlmostEqual(us['common_since_aug4_bp'],50)
