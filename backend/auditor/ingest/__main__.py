"""Ingest something and look at the result.

    python -m auditor.ingest <url | file> [--json | --curated | --text] [--demo-dir DIR]

Default output is the curated markdown form (front matter, `#` headings, `- ` bullets), which
is also what demo-documents/ files look like. `--json` prints the contract Document; `--text`
the canonical text alone. Notes about the fetch and the extraction go to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import IngestError, ingest_file, ingest_url
from .text import to_curated


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m auditor.ingest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="a URL or a path (.md, .txt, .html, .json content model, .pdf)")
    form = parser.add_mutually_exclusive_group()
    form.add_argument("--json", action="store_true", help="print the Document as JSON")
    form.add_argument("--text", action="store_true", help="print the canonical text only")
    form.add_argument("--curated", action="store_true", help="print the curated markdown (default)")
    parser.add_argument("--demo-dir", type=Path, default=Path(__file__).resolve().parents[3] / "demo-documents", help="where the curated copies are")
    args = parser.parse_args(argv)
    try:
        if args.source.startswith(("http://", "https://")):
            ingested = ingest_url(args.source, demo_dir=args.demo_dir)
        else:
            ingested = ingest_file(Path(args.source))
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for note in ingested.notes:
        print(f"note: {note}", file=sys.stderr)
    if args.json:
        print(json.dumps(ingested.document, ensure_ascii=False, indent=2))
    elif args.text:
        print(ingested.document["text"])
    else:
        sys.stdout.write(to_curated(ingested.document))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
