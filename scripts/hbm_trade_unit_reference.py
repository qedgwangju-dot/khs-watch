"""Public K-stat province rows selected by an exact monthly HSK10 request.

K-stat's sheet response does not echo the requested month or HSK, so its
request-scoped identity limit is retained explicitly. No source amount is
reused as another month's value. All HTTP goes through the injected request
function.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup


FORM_URL = "https://stat.kita.net/stat/kts/prod/ProdWholeList.screen"
SHEET_URL = "https://stat.kita.net/stat/kts/prod/ProdWholeListWorker.screen"
CUSTOMS_DOC_URL = "https://www.data.go.kr/data/15101641/openapi.do"
HS = "8542323000"
REGIONS = {"44": ("31", "충남"), "43": ("36", "충북")}
COLUMNS = (
    "RN", "ORDER_NM", "ROW_CODE", "KOR_NAME", "LAST_EXP_AMT", "LAST_EXP_RATE",
    "LAST_IMP_AMT", "LAST_IMP_RATE", "PROFIT", "THIS_EXP_AMT", "THIS_EXP_RATE",
    "THIS_IMP_AMT", "THIS_IMP_RATE", "THIS_PROFIT",
)
_NUMBER = re.compile(r"[+]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?\Z")
_HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": FORM_URL}


class _ReferenceError(ValueError):
    pass


def _positive(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not _NUMBER.fullmatch(text):
        return None
    try:
        number = Decimal(text.replace(",", ""))
        return number if number.is_finite() and number > 0 else None
    except InvalidOperation:
        return None


def _month(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{6}", value):
        return None
    try:
        date(int(value[:4]), int(value[4:]), 1)
        return value
    except ValueError:
        return None


def _response_bytes(response, limit):
    if getattr(response, "status_code", None) != 200:
        raise _ReferenceError("http_status")
    content = response.content
    if not isinstance(content, bytes) or not content or len(content) > limit:
        raise _ReferenceError("response_bytes")
    return content


def _form_contract(content, target_month=None):
    html = content.decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")
    forms = soup.select('form[name="form1"]')
    if len(forms) != 1 or forms[0].get("method", "").lower() != "post":
        raise _ReferenceError("form_contract")
    form = forms[0]

    def options(name):
        matches = form.select(f'select[name="{name}"]')
        if len(matches) != 1:
            raise _ReferenceError("selection_contract")
        pairs = [(o.get("value", ""), o.get_text(" ", strip=True)) for o in matches[0].select("option")]
        if not pairs or len({v for v, _ in pairs}) != len(pairs):
            raise _ReferenceError("selection_options")
        return dict(pairs)

    # Each chosen value must still have its documented, visible meaning.
    contracts = {
        "p_cond_in_gb": ("2", "광역자치별"),
        "s_item_type": ("HS", "HSK"),
        "s_field": ("AMT", "금액"),
        "s_monthsum_gb": ("1", "당월"),
        "s_measure": ("1", "US$,%"),
    }
    for name, (value, label) in contracts.items():
        actual = options(name).get(value, "")
        if re.sub(r"\s+", "", actual) != label:
            raise _ReferenceError("selection_meaning_changed")
    item_inputs = form.select('input[name="s_item_value"]')
    if len(item_inputs) != 1 or (
        item_inputs[0].get("maxlength") is not None
        and (not item_inputs[0]["maxlength"].isdigit() or int(item_inputs[0]["maxlength"]) < 10)
    ):
        raise _ReferenceError("hsk10_input_contract")

    years, months = options("s_year"), options("s_month")
    if any(not re.fullmatch(r"[0-9]{4}", y) for y in years):
        raise _ReferenceError("year_options")
    if any(not re.fullmatch(r"(?:0[1-9]|1[0-2])", m) for m in months):
        raise _ReferenceError("month_options")
    latest_year, latest_month = max(years), max(months)
    if set(months) != {f"{m:02d}" for m in range(1, int(latest_month) + 1)}:
        raise _ReferenceError("month_options_incomplete")
    # These server-rendered defaults bind the month options to the latest year.
    for field, expected in (("year", latest_year), ("month", latest_month)):
        defaults = re.findall(r"setSelect\(f\.s_" + field + r"\s*,\s*['\"]([0-9]+)['\"]\s*\)", html)
        if defaults != [expected]:
            raise _ReferenceError("latest_month_default_contract")
    latest_available_month = _month(latest_year + latest_month)
    if latest_available_month is None:
        raise _ReferenceError("calendar_month")
    if target_month is None:
        month = latest_available_month
    else:
        month = _month(target_month)
        if month is None:
            raise _ReferenceError("calendar_month")
        if month[:4] not in years or month[4:] not in months:
            raise _ReferenceError("requested_month_unavailable")
    columns = re.search(r"initdata\.Cols\s*=\s*\[(.*?)\];", html, re.S)
    if columns is None or tuple(re.findall(r"SaveName\s*:\s*['\"]([^'\"]+)", columns[1])) != COLUMNS:
        raise _ReferenceError("sheet_columns_changed")
    if not re.search(r"mySheet1\.DoSearch\(\s*['\"]/stat/kts/prod/ProdWholeListWorker\.screen['\"]\s*,\s*FormQueryStringEnc\(f\)\s*\)", html):
        raise _ReferenceError("sheet_endpoint_changed")

    params = {}
    for node in form.select('input[name]'):
        if node.get("type", "").lower() not in ("radio", "checkbox") or node.has_attr("checked"):
            params[node["name"]] = node.get("value", "")
    for node in form.select('select[name]'):
        selected = node.select("option[selected]") or node.select("option")[:1]
        params[node["name"]] = selected[0].get("value", "") if selected else ""
    # No authentication override, private geography, cumulative figure or
    # unpublished month is requested.
    params.update({name: value for name, (value, _) in contracts.items()})
    params.update(
        event_udap="Search", searchType="SHEET", pageNum="1",
        s_item_value=HS, s_year=month[:4], s_month=month[4:],
        s_sort="THIS_EXP_AMT", s_sort_val="DESC", p_measure="1", p_field="금액",
    )
    if params.get("auth_info", "") != "":
        raise _ReferenceError("public_authentication_contract")
    return month, params


def _sheet_rows(content):
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise _ReferenceError("xml_declaration")
    root = ET.fromstring(content.lstrip())
    if root.tag != "SHEET" or len(root.findall("DATA")) != 1 or root.find("ERROR") is not None:
        raise _ReferenceError("sheet_response")
    selected = {}
    expected = {code: (customs, name) for customs, (code, name) in REGIONS.items()}
    for tr in root.findall("./DATA/TR"):
        cells = [(td.text or "").strip() for td in tr.findall("TD")]
        # IBSheet adds one empty link cell to its 14 published data columns.
        if len(cells) == len(COLUMNS) + 1 and cells[-1] == "":
            cells.pop()
        if len(cells) != len(COLUMNS):
            raise _ReferenceError("sheet_row_columns")
        row = dict(zip(COLUMNS, cells))
        code, name = row["ROW_CODE"], row["KOR_NAME"]
        name_targets = [k for k, (_, n) in expected.items() if name == n]
        if code not in expected and not name_targets:
            continue
        if code not in expected or name != expected[code][1] or code in selected:
            raise _ReferenceError("province_identity_or_duplicate")
        amount = _positive(row["THIS_EXP_AMT"])
        if amount is None:
            raise _ReferenceError("province_amount_not_positive")
        selected[code] = {"amount_usd": str(amount), "selected_row": row}
    if set(selected) != set(expected):
        raise _ReferenceError("province_rows_missing")
    return selected


def fetch_reference(request_fn, target_month=None):
    """Return publicly selectable monthly USD province rows for one month.

    ``request_fn`` must have the existing retry helper's method/url/data/headers
    signature. ``target_month`` is an exact YYYYMM target; when omitted, the
    latest month selected by K-stat's server-rendered form is used. The caller
    records every response in its own HTTP ledger.
    """
    try:
        form_response = request_fn("GET", FORM_URL, headers=dict(_HEADERS))
        form_bytes = _response_bytes(form_response, 2_000_000)
        month, params = _form_contract(form_bytes, target_month=target_month)
        sheet_response = request_fn("POST", SHEET_URL, data=params, headers=dict(_HEADERS))
        sheet_bytes = _response_bytes(sheet_response, 1_000_000)
        selected = _sheet_rows(sheet_bytes)
    except _ReferenceError as exc:
        return None, "invalid:kstat_reference_" + str(exc)
    except (ValueError, UnicodeError, ET.ParseError, KeyError, TypeError, AttributeError) as exc:
        return None, "invalid:kstat_reference_" + type(exc).__name__
    except Exception as exc:
        # Request exception messages can contain URLs or credentials.
        return None, "error:kstat_reference_" + type(exc).__name__
    return {
        "provider": "K-stat 한국무역협회", "month": month, "hs": HS,
        "unit": "usd", "monthly_not_cumulative": True,
        "amounts_usd": {customs: selected[code]["amount_usd"] for customs, (code, _) in REGIONS.items()},
        "source_region_codes": {customs: code for customs, (code, _) in REGIONS.items()},
        "selected_rows": {customs: selected[code]["selected_row"] for customs, (code, _) in REGIONS.items()},
        "request_scope_no_response_echo": True,
        "identity_limit": "XML has no month/HS echo; month and HSK are the validated public request scope.",
        "evidence_attempt_ids": {
            "form": getattr(form_response, "_hbm_trade_attempt_id", None),
            "sheet": getattr(sheet_response, "_hbm_trade_attempt_id", None),
        },
        "provider_request": {"form_url": FORM_URL, "sheet_url": SHEET_URL, "method": "POST", "data": params, "headers": dict(_HEADERS)},
        "source_sha256": {"form": hashlib.sha256(form_bytes).hexdigest(), "sheet": hashlib.sha256(sheet_bytes).hexdigest()},
    }, ""


def reconcile_unit(api_rows, reference):
    """Choose only a unique factor 1/1000 matching both same-month provinces.

    Input rows are the strict Customs selector's normalized rows, either a list
    or a mapping keyed by Customs province code.  This proves a field contract;
    it never copies the reference month's amount into a newer observation.
    """
    if not isinstance(reference, Mapping) or (
        reference.get("hs") != HS or reference.get("unit") != "usd"
        or reference.get("monthly_not_cumulative") is not True
        or reference.get("request_scope_no_response_echo") is not True
        or _month(reference.get("month")) is None
        or reference.get("source_region_codes") != {k: v[0] for k, v in REGIONS.items()}
    ):
        return None, "invalid:unit_reference_scope"
    if not isinstance(reference.get("amounts_usd"), Mapping) or set(reference["amounts_usd"]) != set(REGIONS):
        return None, "invalid:unit_reference_regions"
    if isinstance(api_rows, Mapping):
        if set(api_rows) != set(REGIONS):
            return None, "invalid:unit_api_regions"
        rows = []
        for code, row in api_rows.items():
            if not isinstance(row, Mapping) or row.get("region_code") != code:
                return None, "invalid:unit_api_region_identity"
            rows.append(row)
    elif isinstance(api_rows, (list, tuple)):
        rows = list(api_rows)
    else:
        return None, "invalid:unit_api_rows"
    if len(rows) != 2 or any(not isinstance(row, Mapping) for row in rows):
        return None, "invalid:unit_api_row_count"
    operands = {}
    for row in rows:
        code = row.get("region_code")
        if not isinstance(code, str) or code not in REGIONS or code in operands:
            return None, "invalid:unit_api_duplicate_or_unknown_region"
        if row.get("month") != reference["month"] or row.get("hs") != HS or row.get("raw_amount_field") != "expUsdAmt":
            return None, "invalid:unit_api_scope"
        raw = _positive(row.get("raw_amount_decimal", row.get("raw_amount")))
        amount = _positive(reference["amounts_usd"].get(code))
        if raw is None or amount is None:
            return None, "invalid:unit_operands_not_positive"
        operands[code] = (raw, amount)
    matches = []
    for factor in (Decimal(1), Decimal(1000)):
        differences = {code: abs(raw * factor - amount) for code, (raw, amount) in operands.items()}
        if all(delta <= Decimal(1000) for delta in differences.values()):
            matches.append((factor, differences))
    if len(matches) != 1:
        return None, "invalid:unit_factor_not_unique" if matches else "invalid:unit_cross_provider_mismatch"
    factor, differences = matches[0]
    return {
        "status": "verified_same_month_cross_provider", "month": reference["month"], "hs": HS,
        "unit": "usd" if factor == 1 else "thousand_usd", "factor_to_usd": str(factor),
        "amount_field": "expUsdAmt", "customs_document_url": CUSTOMS_DOC_URL,
        "reference_url": SHEET_URL, "reference_source_sha256": dict(reference.get("source_sha256", {})),
        "request_scope_no_response_echo": True, "tolerance_usd": "1000",
        "comparisons": {code: {"api_raw_amount": str(raw), "reference_amount_usd": str(amount),
                               "converted_api_amount_usd": str(raw * factor), "absolute_difference_usd": str(differences[code])}
                        for code, (raw, amount) in operands.items()},
        "limit": "Same-month numerical unit evidence; neither company attribution nor HBM-only coverage is established.",
    }, ""
