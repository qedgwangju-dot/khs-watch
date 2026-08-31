from pathlib import Path
from datetime import datetime
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path = [str(SCRIPT_DIR)] + [
    path
    for path in sys.path
    if Path(path or ".").resolve() not in {SCRIPT_DIR, ROOT}
]
import gamejoa_preopen_news_radar_full_compact_runner as radar

WORKFLOW = ROOT / ".github/workflows/gamejoa-preopen-news-radar.yml"
REQUIRED = (
    'cron: "7,27,47 * * * *"',
    "RADAR_RUN_MODE: ${{ github.event_name == 'schedule' && 'live' || github.event.inputs.radar_run_mode || 'preopen' }}",
)

def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    missing = [snippet for snippet in REQUIRED if snippet not in text]
    if missing:
        for snippet in missing:
            print(f"GAMEJOA native schedule contract error: missing {snippet}")
        return 1
    rendered = radar.compact_alert(
        {
            "importance": "\uc0c1",
            "status": "\uacf5\uc2dd \ud655\uc778 \uc804",
            "memory_antitrust_lawsuit": True,
            "news": "\uba54\ubaa8\ub9ac \ubc18\ub3c5\uc810 \uc18c\uc1a1",
            "source_title": "\uba54\ubaa8\ub9ac \ubc18\ub3c5\uc810 \uc18c\uc1a1",
            "policy_plain_summary": "\uad00\ub828 DRAM \uac00\uaca9\ub2f4\ud569 \uc9d1\ub2e8\uc18c\uc1a1 \ubcf4\ub3c4\ub294 \ub2f9\uc7a5 \uc2e4\uc801\ubcf4\ub2e4",
            "link": "https://www.reuters.com/legal/example",
            "impacts": ["\ub9e4\ucd9c\u00b7\ub9c8\uc9c4\u00b7\ud604\uae08\ud750\ub984"],
        },
        1,
        datetime.now().astimezone(),
        {},
        {},
    )
    expected = "- \ud575\uc2ec: \uc0bc\uc131\uc804\uc790\u00b7SK\ud558\uc774\ub2c9\uc2a4\u00b7Micron\uc5d0 DRAM \uac00\uaca9\ub2f4\ud569 \uc9d1\ub2e8\uc18c\uc1a1\uc774 \uc81c\uae30\ub410\uc2b5\ub2c8\ub2e4."
    if expected not in rendered:
        print("GAMEJOA native schedule contract error: antitrust summary is incomplete")
        return 1
    radar.guard_preopen_report(
        "\n".join(
            [
                "\U0001f4f0 \uc2e4\uc2dc\uac04 \ud575\uc2ec \ub274\uc2a4 \ub808\uc774\ub354 \u00b7 2026\ub144 07\uc6d4 30\uc77c \u00b7 11:30",
                "\uc120\ubcc4: \ud575\uc2ec 1\uac74",
                "",
                rendered,
                "\ud22c\uc790 \uc870\uc5b8\uc774 \uc544\ub2cc \ucc38\uace0\uc6a9 \ub274\uc2a4 \ube0c\ub9ac\ud551\uc785\ub2c8\ub2e4.",
            ]
        )
    )
    print("GAMEJOA native schedule contract OK: live fallback and complete summaries enabled.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

