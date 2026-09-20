"""Check event logs against the envelope rules.

    python -m auditor.validate ../fixtures/smoke.jsonl [more files]
"""

from __future__ import annotations

import sys
from pathlib import Path

from .envelope import LogError, log_summary, read_log


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip())
        return 2
    failed = 0
    for arg in argv:
        path = Path(arg)
        try:
            events = read_log(path)
        except FileNotFoundError:
            print(f"{path}: not found")
            failed += 1
            continue
        except LogError as exc:
            print(f"INVALID  {exc}")
            failed += 1
            continue
        summary = log_summary(events)
        types = ", ".join(f"{name} x{count}" for name, count in summary["types"].items())
        print(f"OK       {path.name}: {summary['events']} events, {summary['duration_ms']} ms; {types}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
