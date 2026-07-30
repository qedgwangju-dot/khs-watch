from pathlib import Path


WORKFLOW = Path(".github/workflows/gamejoa-preopen-news-radar.yml")
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
    print("GAMEJOA native schedule contract OK: 20-minute live fallback enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
