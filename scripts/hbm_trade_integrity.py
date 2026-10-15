"""Strict, network-free trade row selection and an HTTP evidence ledger.

``choose_exact_row`` accepts already decoded response rows.  The caller must
choose the amount field and its documented unit for that endpoint; neither the
field name nor the size of a number establishes its unit here.  Use
``unit='unverified'`` while a source contract is unresolved: the raw amount and
identity proof remain available, but ``amount_usd`` is None.

Success is ``(normalized_row, '')``.  Only an empty response is ``missing:``.
Nonempty incompatible, ambiguous, duplicate or malformed responses are
``invalid:`` and must not be treated as an unpublished month.  A province may
omit its response echo, which is explicitly weaker than an echoed identity.
A requested country must have an independently matching response echo.

``TradeEvidence`` performs no HTTP requests.  Record *each* HTTP attempt from the
caller's retry loop, then attach its selection result.  It saves exact response
bytes only when they contain none of the credentials privately loaded from the
named environment variables.  A response containing a credential is withheld,
not redacted and relabelled as raw evidence.  The ledger never sends messages or
updates operating state.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import html
import json
import math
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, quote_plus, unquote, urlencode, urlsplit, urlunsplit


MONTH_FIELDS = ("year", "priodTitle", "month", "yyyymm", "ym")
HS_FIELDS = ("hsSgn", "hsCd", "hsCode", "hs")
REGION_CODE_FIELDS = ("sidoCd", "sidoCode", "regionCode")
REGION_NAME_FIELDS = ("sidoNm", "sidoName", "sidoCdNm", "sidoCdCntnKor1", "regionNm", "regionName")
COUNTRY_CODE_FIELDS = ("statCd", "cntyCd", "countryCode", "natCd", "country_code")
COUNTRY_NAME_FIELDS = ("statCdCntnKor1", "cntyNm", "cntyCdNm", "countryNm", "countryName", "country_name")
_NUMBER = re.compile(r"[+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
_MONTH_COMPACT = re.compile(r"([0-9]{4})([0-9]{2})\Z")
_MONTH_SEPARATED = re.compile(r"([0-9]{4})\s*[-./]\s*([0-9]{1,2})\Z")
_MONTH_KOREAN = re.compile(r"([0-9]{4})\s*년\s*([0-9]{1,2})\s*월\Z")
_HS = re.compile(r"[0-9]+(?:[.\- ][0-9]+)*\Z")
_REGIONS = {
    "44": ("충남", "충청남도", "chungnam", "chungcheongnamdo", "chungcheongnam-do"),
    "43": ("충북", "충청북도", "chungbuk", "chungcheongbukdo", "chungcheongbuk-do"),
    "41": ("경기", "경기도", "gyeonggi", "gyeonggido", "gyeonggi-do"),
}
_COUNTRIES = {"MY": ("MY", "MYS", "말레이시아", "Malaysia")}
_REDACTED = "[REDACTED]"


def normalize_month(value: Any) -> str | None:
    """Return one exact calendar month; totals, dates and ranges are invalid.

    Supported source spellings are YYYYMM, YYYY-MM, YYYY.MM, YYYY/MM and
    YYYY년 M월.  Whitespace around a value/separator is harmless.  Dropping all
    nondigits is deliberately forbidden because it accepts cumulative periods.
    """
    if isinstance(value, bool) or value is None or not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    match = _MONTH_COMPACT.fullmatch(text) or _MONTH_SEPARATED.fullmatch(text) or _MONTH_KOREAN.fullmatch(text)
    if not match:
        return None
    year, month = (int(part) for part in match.groups())
    try:
        date(year, month, 1)
    except (ValueError, OverflowError):
        return None
    return f"{year:04d}{month:02d}"


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float, Decimal)):
        text = str(value).strip()
    else:
        return None
    if not _NUMBER.fullmatch(text):
        return None
    try:
        result = Decimal(text.replace(",", ""))
        if not result.is_finite() or result < 0:
            return None
        numeric = float(result)
        if not math.isfinite(numeric) or (result != 0 and numeric == 0):
            return None
        return abs(result) if result == 0 else result
    except (InvalidOperation, OverflowError, ValueError):
        return None


def finite_number(value: Any) -> float | None:
    """Parse a finite nonnegative export value, including a reported zero."""
    parsed = _decimal(value)
    return float(parsed) if parsed is not None else None


def _hs_code(value: Any) -> str | None:
    if isinstance(value, bool) or value is None or not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return re.sub(r"[.\- ]", "", text) if _HS.fullmatch(text) else None


def _fields(row: Mapping[str, Any], names: Iterable[str]) -> dict[str, Any]:
    return {name: row[name] for name in names if name in row and row[name] is not None and str(row[name]).strip() != ""}


def _one_identity(values: Mapping[str, Any], normalizer, missing_reason: str, invalid_reason: str):
    if not values:
        return None, missing_reason
    normalized = [normalizer(value) for value in values.values()]
    if any(value is None for value in normalized):
        return None, invalid_reason
    if len(set(normalized)) != 1:
        return None, "conflicting_identity"
    return normalized[0], ""


def _plain_identity(value: Any) -> str | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = re.sub(r"\s+", "", str(value)).casefold()
    return text or None


def _region_request(region: Any) -> tuple[str | None, str | None]:
    if isinstance(region, Mapping):
        code = region.get("sido") or region.get("code") or region.get("sidoCd")
        name = region.get("name") or region.get("region") or region.get("sidoNm")
    elif str(region).strip().isdigit():
        code, name = region, None
    else:
        code, name = None, region
    code, name = _plain_identity(code), _plain_identity(name)
    if code and not code.isdigit():
        return None, None
    named_code = next((key for key, aliases in _REGIONS.items() if name in {_plain_identity(item) for item in aliases}), None) if name else None
    if code and named_code and code != named_code:
        return None, None
    if not code and name:
        code = named_code
    return code, name


def _check_region(row: Mapping[str, Any], requested: Any) -> tuple[dict[str, Any] | None, str]:
    code, name = _region_request(requested)
    if not code and not name:
        return None, "invalid_requested_region"
    codes, names = _fields(row, REGION_CODE_FIELDS), _fields(row, REGION_NAME_FIELDS)
    if not codes and not names:
        return {"status": "request_scoped_no_response_echo", "requested_code": code, "requested_name": name, "response_fields": {}}, ""
    aliases = {_plain_identity(item) for item in _REGIONS.get(code or "", ())}
    if name:
        aliases.add(name)
    for value in codes.values():
        if code is None or _plain_identity(value) != code:
            return None, "region_mismatch"
    for value in names.values():
        if not aliases or _plain_identity(value) not in aliases:
            return None, "region_mismatch"
    return {"status": "response_echo_matched", "requested_code": code, "requested_name": name, "response_fields": {**codes, **names}}, ""


def _check_country(row: Mapping[str, Any], requested: Any) -> tuple[dict[str, Any] | None, str]:
    country = str(requested).strip().upper()
    if not re.fullmatch(r"[A-Z]{2,3}", country):
        return None, "invalid_requested_country"
    values = {**_fields(row, COUNTRY_CODE_FIELDS), **_fields(row, COUNTRY_NAME_FIELDS)}
    if not values:
        return None, "response_country_missing"
    aliases = {_plain_identity(item) for item in _COUNTRIES.get(country, (country,))}
    if any(_plain_identity(value) not in aliases for value in values.values()):
        return None, "country_mismatch"
    return {"status": "response_echo_matched", "requested_code": country, "response_fields": values}, ""


def choose_exact_row(
    rows: Iterable[Mapping[str, Any]],
    month: str,
    hs: str,
    region: Any = None,
    country: str | None = None,
    value_fields: tuple[str, ...] = ("expDlr",),
    unit: str = "usd",
    *,
    unit_proof: Any = None,
    factor: Any = None,
    weight_fields: tuple[str, ...] = ("expWgt", "expTtwg"),
    month_fields: tuple[str, ...] = MONTH_FIELDS,
    hs_fields: tuple[str, ...] = HS_FIELDS,
) -> tuple[dict[str, Any] | None, str]:
    """Select exactly one response-identified monthly row, without inference.

    ``region`` may be a code/name or ``{'sido': '44', 'name': '충남'}``.
    Missing province echoes are retained as request-scoped evidence; present
    codes/names must match.  Country echoes are mandatory.  Duplicate matching
    rows are rejected even if their values agree.  Multiple amount aliases are
    also ambiguous and rejected: choose the endpoint's one documented field.

    ``unit`` is the caller's explicit contract: usd -> factor 1,
    thousand_usd -> 1000, unverified -> no conversion.  ``factor``, if provided,
    must agree with that contract.  ``unit_proof`` is carried unchanged into the
    proof; this function does not promote a caller declaration into a verified
    provider contract.  ``selected_row`` retains original scalar operands for
    attachment to a credential-safe ledger.
    """
    requested_month, requested_hs = normalize_month(month), _hs_code(hs)
    if requested_month is None or requested_hs is None or not value_fields:
        return None, "invalid:request_identity"
    unit = str(unit).strip().lower()
    conversions = {"usd": Decimal(1), "thousand_usd": Decimal(1000), "unverified": None}
    if unit not in conversions:
        return None, "invalid:unit_contract"
    multiplier = conversions[unit]
    if factor is not None:
        specified = _decimal(factor)
        if multiplier is None or specified is None or specified != multiplier:
            return None, "invalid:unit_factor_conflict"
    try:
        source_rows = list(rows)
    except (TypeError, ValueError):
        return None, "invalid:rows_container"
    if not source_rows:
        return None, "missing:no_rows"

    candidates: list[tuple[int, Mapping[str, Any], dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    ambiguous = False
    for index, row in enumerate(source_rows):
        if not isinstance(row, Mapping):
            rejected.append({"row_index": index, "reason": "malformed_row"})
            ambiguous = True
            continue
        months, hs_values = _fields(row, month_fields), _fields(row, hs_fields)
        row_month, month_error = _one_identity(months, normalize_month, "response_month_missing", "non_monthly_period")
        row_hs, hs_error = _one_identity(hs_values, _hs_code, "response_hs_missing", "invalid_hs")
        mismatched = (row_month is not None and row_month != requested_month) or (row_hs is not None and row_hs != requested_hs)
        if mismatched:
            rejected.append({"row_index": index, "reason": "different_month_or_hs"})
            continue
        if month_error or hs_error:
            reason = month_error or hs_error
            rejected.append({"row_index": index, "reason": reason})
            # An explicit range/total is not a duplicate monthly observation.
            # Missing/conflicting identities could conceal a second target row.
            if reason != "non_monthly_period":
                ambiguous = True
            continue
        region_proof, country_proof = None, None
        if region is not None:
            region_proof, reason = _check_region(row, region)
            if reason:
                rejected.append({"row_index": index, "reason": reason})
                continue
        if country is not None:
            country_proof, reason = _check_country(row, country)
            if reason:
                rejected.append({"row_index": index, "reason": reason})
                if reason == "response_country_missing":
                    ambiguous = True
                continue
        proof = {"month": {"status": "response_echo_matched", "response_fields": months}, "hs": {"status": "response_echo_matched", "response_fields": hs_values}}
        if region_proof is not None:
            proof["region"] = region_proof
        if country_proof is not None:
            proof["country"] = country_proof
        candidates.append((index, row, proof))

    if len(candidates) > 1:
        return None, "invalid:duplicate_target_rows"
    if not candidates:
        reason = rejected[0]["reason"] if rejected else "no_exact_target"
        return None, f"invalid:{reason}"
    if ambiguous:
        return None, "invalid:ambiguous_target_identity"
    index, selected, proof = candidates[0]
    amounts = _fields(selected, value_fields)
    if len(amounts) != 1:
        return None, "invalid:amount_missing" if not amounts else "invalid:ambiguous_amount_fields"
    amount_field, amount_input = next(iter(amounts.items()))
    raw_amount = _decimal(amount_input)
    if raw_amount is None:
        return None, "invalid:amount_not_finite_nonnegative"
    converted = raw_amount * multiplier if multiplier is not None else None
    if converted is not None and finite_number(converted) is None:
        return None, "invalid:converted_amount_not_finite"
    weights = _fields(selected, weight_fields)
    parsed_weights = [_decimal(value) for value in weights.values()]
    if any(value is None for value in parsed_weights):
        return None, "invalid:weight_not_finite_nonnegative"
    if len(set(parsed_weights)) > 1:
        return None, "invalid:conflicting_weight_fields"
    weight = parsed_weights[0] if parsed_weights else None
    proof["selection"] = {"row_index": index, "matching_rows": 1, "rejected_rows": rejected}
    result = {
        "month": requested_month,
        "hs": requested_hs,
        "raw_amount": float(raw_amount),
        "raw_amount_text": str(amount_input),
        "raw_amount_decimal": str(raw_amount),
        "raw_amount_field": amount_field,
        "raw_amount_unit": unit,
        "amount_usd": float(converted) if converted is not None else None,
        "weight_kg": float(weight) if weight is not None else None,
        "weight_status": "response_value" if weight is not None else "not_returned",
        "unit_proof": {"status": "unverified" if multiplier is None else "caller_declared_contract", "unit": unit, "factor_to_usd": str(multiplier) if multiplier is not None else None, "contract": copy.deepcopy(unit_proof)},
        "identity_proof": proof,
        "selected_row": copy.deepcopy(dict(selected)),
    }
    if country is not None:
        result["country_code"] = str(country).strip().upper()
    if region is not None:
        code, name = _region_request(region)
        result["region_code"], result["region"] = code, name
    return result, ""


def _sensitive_name(value: Any) -> bool:
    key = re.sub(r"[^a-z0-9]", "", str(value).casefold())
    return key in {"servicekey", "apikey", "authorization", "proxyauthorization", "password", "passwd", "secret", "clientsecret", "token", "accesstoken", "refreshtoken", "cookie", "setcookie"} or key.endswith(("servicekey", "apikey", "accesstoken", "clientsecret"))


class TradeEvidence:
    """Write exact response evidence with a strict credential boundary.

    Credentials are accepted only as environment *names*, loaded privately,
    and never returned or written. ``record_attempt`` returns a string id and
    durably writes the updated ledger after each call. ``mark_selection`` also
    writes immediately. ``as_dict`` returns a sanitized detached copy.

    Example::

        evidence = TradeEvidence(path)
        attempt = evidence.record_attempt(
            'GET', endpoint, params=params, status=response.status_code,
            raw_bytes=response.content, started_at=start, completed_at=end)
        selected, error = choose_exact_row(rows, month, hs, unit='unverified')
        evidence.mark_selection(attempt, selected, error)

    Caller retries must invoke record_attempt for every failed/successful
    attempt. ``error_type`` accepts an exception or an exception class/name,
    never an exception message containing a potentially credentialled URL.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        credential_env_names: Iterable[str] = ("KCS_DATA_GO_SERVICE_KEY",),
        code_sha: str | None = None,
        run_id: str | None = None,
    ):
        self.path = Path(path)
        self.__credentials: set[str] = set()
        for name in credential_env_names:
            value = os.environ.get(str(name), "").strip()
            if not value:
                continue
            for _ in range(3):
                self.__credentials.update((value, quote(value, safe=""), quote_plus(value)))
                decoded = unquote(value)
                if decoded == value:
                    break
                value = decoded
        self.__document = {
            "schema_version": 1,
            "source": "Korea Customs trade HTTP evidence",
            "code_sha": code_sha if code_sha is not None else os.environ.get("HBM_CODE_SHA", os.environ.get("GITHUB_SHA", "")),
            "github_sha": os.environ.get("GITHUB_SHA", ""),
            "run_id": run_id if run_id is not None else os.environ.get("GITHUB_RUN_ID", ""),
            "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
            "attempts": [],
        }
        self.__document = self._sanitize(self.__document)

    def _contains_credential(self, value: bytes | str) -> bool:
        if isinstance(value, bytes):
            # UTF-16/32 responses are uncommon but must not bypass the boundary.
            texts = [value.decode(encoding, errors="ignore") for encoding in ("utf-8", "utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be")]
        else:
            texts = [value]
        for text in texts:
            variants = {text, html.unescape(text), text.replace("\\/", "/")}
            variants.update(unquote(item) for item in tuple(variants))
            variants.update(re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), item) for item in tuple(variants))
            if any(secret.casefold() in item.casefold() for item in variants for secret in self.__credentials):
                return True
            if any(re.search(r'(?i)(?:service[_-]?key|api[_-]?key|access[_-]?token|authorization|password|client[_-]?secret)[\"\'\s]*(?:=|:)\s*[\"\']?[^\s\"\'&<>]{1,}', item) for item in variants):
                return True
            if any(re.search(r'(?i)<(?:service[_-]?key|api[_-]?key|access[_-]?token|authorization|password|client[_-]?secret)\b[^>]*>\s*[^\s<]+', item) for item in variants):
                return True
        return False

    def _safe_text(self, value: Any) -> str:
        text = str(value)
        for secret in sorted(self.__credentials, key=len, reverse=True):
            text = re.sub(re.escape(secret), _REDACTED, text, flags=re.IGNORECASE)
        # Also remove unnamed credentials in common URL/query error messages.
        text = re.sub(r"(?i)((?:service[_-]?key|api[_-]?key|access[_-]?token|password|client[_-]?secret)\s*(?:=|%3d)\s*)[^\s&\"'<>]+", lambda match: match.group(1) + _REDACTED, text)
        text = re.sub(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", text)
        return text

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {self._safe_text(key): _REDACTED if _sensitive_name(key) else self._sanitize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._sanitize(item) for item in value]
        if isinstance(value, bytes):
            return "[BINARY_METADATA_OMITTED]"
        if isinstance(value, str):
            return self._safe_text(value)
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        return self._safe_text(value)

    def _safe_url(self, url: Any) -> str:
        try:
            parts = urlsplit(str(url))
            host = parts.netloc.rsplit("@", 1)[-1]
            query = [(key, _REDACTED if _sensitive_name(key) else self._safe_text(value)) for key, value in parse_qsl(parts.query, keep_blank_values=True)]
            return self._safe_text(urlunsplit((parts.scheme, host, parts.path, urlencode(query), "")))
        except ValueError:
            return "[INVALID_URL_OMITTED]"

    def record_attempt(
        self,
        method: str,
        url: str,
        *,
        params: Any = None,
        data: Any = None,
        status: int | None = None,
        raw_bytes: bytes | None = None,
        error_type: Any = None,
        started_at: Any = None,
        completed_at: Any = None,
        response_headers: Any = None,
    ) -> str:
        """Save one actual request/response attempt; timestamps default to UTC now."""
        timestamp = datetime.now(timezone.utc).isoformat()
        if isinstance(error_type, BaseException):
            error_name = type(error_type).__name__
        elif isinstance(error_type, type) and issubclass(error_type, BaseException):
            error_name = error_type.__name__
        else:
            error_name = str(error_type or "")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,100}", error_name):
                error_name = "request_error" if error_type else ""
        response: dict[str, Any] = {"http_status": status if isinstance(status, int) and not isinstance(status, bool) else None, "headers": self._sanitize(response_headers or {}), "raw_preserved": False, "raw_bytes_length": len(raw_bytes) if isinstance(raw_bytes, bytes) else None, "raw_sha256": None, "raw_base64": None}
        if raw_bytes is None:
            response["raw_not_preserved_reason"] = "no_response_bytes"
        elif not isinstance(raw_bytes, bytes):
            response["raw_not_preserved_reason"] = "invalid_response_bytes_type"
        elif self._contains_credential(raw_bytes):
            response["raw_not_preserved_reason"] = "credential_detected_in_response"
        else:
            response.update(raw_preserved=True, raw_sha256=hashlib.sha256(raw_bytes).hexdigest(), raw_base64=base64.b64encode(raw_bytes).decode("ascii"))
        attempt_id = str(len(self.__document["attempts"]) + 1)
        entry = {
            "attempt_id": attempt_id,
            "request": {"method": self._safe_text(str(method).upper()), "url": self._safe_url(url), "params": self._sanitize(params or {}), "data": self._sanitize(data or {})},
            "started_at": self._safe_text(started_at if started_at is not None else timestamp),
            "completed_at": self._safe_text(completed_at if completed_at is not None else timestamp),
            "timestamp_basis": "caller_supplied" if started_at is not None and completed_at is not None else "ledger_recording_time_for_unsupplied_boundaries",
            "error_type": self._safe_text(error_name),
            "response": response,
            "selection": {"status": "not_evaluated"},
        }
        self.__document["attempts"].append(entry)
        self.write()
        return attempt_id

    def mark_selection(self, attempt_id: str, selected: Mapping[str, Any] | None = None, error: str = "", *, validation_status: str | None = None) -> None:
        """Attach exact row operands/identity proof, or an explicit held result."""
        entry = next((item for item in self.__document["attempts"] if item["attempt_id"] == str(attempt_id)), None)
        if entry is None:
            raise ValueError("unknown trade evidence attempt id")
        if validation_status is None:
            if selected is None:
                validation_status = "missing" if str(error).startswith("missing:") else "invalid"
            else:
                validation_status = "identity_matched_unit_unverified" if selected.get("amount_usd") is None else "selected_under_caller_unit_contract"
        selection = {"status": validation_status, "error": error, "normalized": selected}
        entry["selection"] = self._sanitize(selection)
        entry["selection"]["metadata_redacted"] = self._contains_credential(json.dumps(selection, ensure_ascii=False, default=str))
        self.write()

    def as_dict(self) -> dict[str, Any]:
        """Return a detached sanitized document, without private credentials."""
        # Metadata is sanitized on ingress. Rewriting base64/hash strings here
        # could destroy exact response evidence if a short secret coincidentally
        # occurred in its encoded representation.
        return copy.deepcopy(self.__document)

    to_dict = as_dict

    def write(self) -> Path:
        """Atomically persist the sanitized ledger; never modify monitor state."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.as_dict(), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink()
        return self.path

    flush = write
