from __future__ import annotations

import csv
from pathlib import Path
from database import Database
from models import utc_now


HEADINGS = ("예산", "수익구조", "현재 숫자", "미래 재평가", "역풍·실패모드", "결론", "핵심 한 줄 요약")


def write_report(db: Database, output_dir: str, new_finding_ids: list[int]) -> Path | None:
    if not new_finding_ids:
        return None
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = db.rows(
        f"SELECT * FROM findings WHERE finding_id IN ({','.join('?' for _ in new_finding_ids)}) ORDER BY finding_id",
        new_finding_ids,
    )
    stamp = utc_now().replace(":", "").replace("+", "_")
    path = out / f"svic_alert_{stamp}.md"
    lines = ["# 삼성전자 SVIC 82호·83호 신규 공식자료", ""]
    for heading in HEADINGS:
        lines += [f"## {heading}", ""]
        if heading == "예산":
            lines += ["- SVIC 82호 총 출자 예정액: 5,000억원", "- SVIC 83호 총 출자 예정액: 3,000억원"]
        elif heading == "현재 숫자":
            lines += ["| 기업 | 투자 조합 | 상태 | 신규 사실 | 근거 |", "|---|---|---|---|---|"]
            lines += [f"| {r['company_name']} | {r['related_fund'] or '확인 필요'} | {r['fund_confirmation_status']} | {r['summary']} | {'<br>'.join(__import__('json').loads(r['source_urls']))} |" for r in rows]
        elif heading == "역풍·실패모드":
            lines += ["- 조합번호가 명시되지 않은 Samsung Ventures 투자는 82호·83호로 확정할 수 없음.", "- PoC와 고객 인증은 양산 또는 매출 발생을 의미하지 않음.", "- 공식 원문 접근 실패 시 기존 사실을 신규 사실로 재사용하지 않음."]
        elif heading == "핵심 한 줄 요약":
            lines += [f"- 신규 공식 문서 {len(rows)}건을 탐지했으며, 확정 조합·투자금액·양산·반복 매출은 각 원문에서 확인된 범위만 반영했다."]
        else:
            lines += ["- 신규 공식자료에 명시된 범위만 분석하며, 확인되지 않은 값은 확인 불가."]
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_csv(db: Database, output_dir: str) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "companies.csv"
    rows = db.rows("SELECT * FROM companies ORDER BY record_id")
    names = [d[1] for d in db.conn.execute("PRAGMA table_info(companies)")]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(names)
        writer.writerows([[row[name] for name in names] for row in rows])
    return path

