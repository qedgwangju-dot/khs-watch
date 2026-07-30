from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from analysis.codex_analyzer import analyze_if_configured
from analysis.report import export_csv, write_report
from database import Database
from models import Document
from notifier import notify
from parsers.investment_parser import parse_document
from search.base import Fetcher
from search.collectors import collect_source

LOG = logging.getLogger("svic_tracker")


async def run(config_path: str, sample_path: str | None = None) -> int:
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    db = Database(os.getenv("SVIC_DB_PATH", "state/svic_tracker.sqlite3"))
    run_id = db.start_run()
    raw_dir = Path(os.getenv("SVIC_RAW_DIR", "state/raw"))
    raw_dir.mkdir(parents=True, exist_ok=True)
    new_docs: list[Document] = []
    failures: list[tuple[str, str, int]] = []
    try:
        if sample_path:
            payload = json.loads(Path(sample_path).read_text(encoding="utf-8"))
            candidates = [Document(**item) for item in payload]
            batches = [("sample", candidates, None)]
        else:
            request_cfg = cfg["request"]
            fetcher = Fetcher(request_cfg["timeout_seconds"], request_cfg["retries"], request_cfg["backoff_seconds"], request_cfg["requests_per_second"])
            since = db.last_success_at()
            tasks = {
                name: asyncio.create_task(collect_source(name, source, fetcher, None, since))
                for name, source in cfg["sources"].items() if source.get("enabled")
            }
            batches = []
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for (name, _), result in zip(tasks.items(), results):
                if isinstance(result, Exception):
                    count = db.source_failed(name, str(result))
                    failures.append((name, str(result), count))
                else:
                    db.source_succeeded(name)
                    batches.append((name, result, None))
        for _, documents, _ in batches:
            for doc in documents:
                raw_path = raw_dir / f"{doc.content_hash}.html"
                if db.add_document(doc, str(raw_path)):
                    raw_path.write_text(doc.body, encoding="utf-8")
                    new_docs.append(doc)
        new_ids: list[int] = []
        for doc in new_docs:
            for finding in parse_document(doc):
                finding_id = db.add_finding(finding)
                if finding_id and finding.event_type in cfg["alert_events"] and db.reserve_alert(finding_id, finding.alert_hash):
                    new_ids.append(finding_id)
                    try:
                        notify({"type": "svic_finding", "company": finding.company_name_original, "event": finding.event_type, "summary": finding.summary, "sources": finding.source_urls})
                        db.mark_alert(finding.alert_hash)
                    except Exception as exc:
                        db.mark_alert(finding.alert_hash, str(exc))
                        LOG.exception("alert delivery failed")
        if new_docs:
            # Costly model analysis is gated strictly behind new-document detection.
            analysis = analyze_if_configured(new_docs)
            (raw_dir / f"analysis_run_{run_id}.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        for source, error, count in failures:
            if count == 3:
                notify({"type": "collector_error", "source": source, "consecutive_failures": count, "error": error})
        report = write_report(db, os.getenv("SVIC_OUTPUT_DIR", "outputs"), new_ids)
        export_csv(db, os.getenv("SVIC_OUTPUT_DIR", "outputs"))
        # A partial source failure never promotes old rows as new facts.
        status = "success" if not failures else "partial"
        db.finish_run(run_id, status, len(new_docs), len(new_ids), "; ".join(f"{n}: {e}" for n, e, _ in failures) or None)
        print(json.dumps({"run_id": run_id, "status": status, "new_documents": len(new_docs), "new_alerts": len(new_ids), "report": str(report) if report else None}, ensure_ascii=False))
        # Individual collectors carry their own persistent failure counters.
        # A partial run stays operational and only the third consecutive source
        # failure emits an error alert.
        return 0
    except Exception as exc:
        db.finish_run(run_id, "failed", len(new_docs), 0, str(exc))
        LOG.exception("run failed")
        return 1
    finally:
        db.close()


def cli() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--sample", help="offline JSON document fixture")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return asyncio.run(run(args.config, args.sample))


if __name__ == "__main__":
    raise SystemExit(cli())
