from models import Finding


def classification(finding: Finding) -> str:
    if finding.fund_confirmation_status == "confirmed":
        return "직접 사업"
    if finding.event_type == "samsung_validation":
        return "고객 검증"
    if finding.official_source_exists:
        return "준비"
    return "검토"

