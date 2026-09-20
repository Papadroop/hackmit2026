# Backend

FastAPI service: creates analyses, streams their events over Server-Sent Events, and replays
saved event logs with their original timing. The pipeline stages (roadmap steps 10–17) plug
into `auditor/pipeline.py`. Ingestion (step 10) is built: a live request reads its text, URL
or PDF into a contract Document and emits it; the stages after it replay from a recording of
the same document when there is one, and otherwise the run stops at `extract` with a clear
message, the document still shown.

## Run

```sh
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m uvicorn auditor.main:app --port 8400 --reload
```

Port 8400 is what `frontend/vite.config.ts` proxies `/api` to. Ports 8000 and 5173 are taken
by another project on the dev machine. If `frontend/dist` exists (after `npm run build`), the
same process serves it: assets as files, and `index.html` for every other non-API path so the
client-side routes (`/a/<analysis id>`) survive a reload. One server then runs the whole demo.

Tests: `.venv/bin/python -m pytest`. Check a fixture: `.venv/bin/python -m auditor.validate ../fixtures/smoke.jsonl`.

## Claude

The pipeline stages call Claude through `auditor/llm.py`: one client, one set of defaults, two
call shapes (`complete` for text, `extract` for a typed pydantic result via structured outputs).
Every request streams with adaptive thinking, and returns its token usage.

```sh
cp .env.example .env            # then put your key in ANTHROPIC_API_KEY
.venv/bin/python -m auditor.llm check     # one small call each way; prints model, effort, tokens
```

Defaults, overridable in `.env` or the environment: `AUDITOR_MODEL=claude-sonnet-5` (the team's
choice for now; `claude-opus-5` is the step up) and `AUDITOR_EFFORT=high` (`low` to `max`).
`python -m auditor.llm check --model claude-opus-5 --effort xhigh` tries another setting without
changing the file. Put the document text in `system` and pass `cache=True` so the stages that
read the same document share a prompt cache.

## Endpoints

| Method, path | Purpose |
|---|---|
| `GET /api/health` | Liveness, plus the fixtures and runs directories in use. |
| `GET /api/fixtures` | Fixtures in `fixtures/`, each with event count, duration and a count per type, or the validation error if the file is invalid. |
| `GET /api/documents` | What the menu shows: the demo texts in `demo-documents/` joined with their recordings in `fixtures/` by source URL, plus `live_analysis` (whether text and URL input work yet) and any invalid recordings. The demo text's `role` is never exposed. |
| `POST /api/analyses` | Start an analysis. Body is one of `{"kind": "replay", "fixture": "<name>", "speed": 1}`, `{"kind": "replay", "run": "<saved run>"}`, `{"kind": "text", "text": "...", "title": "..."}`, `{"kind": "url", "url": "..."}`, `{"kind": "pdf", "filename": "...", "data_base64": "..."}`. Live kinds take an optional `speed` for any stages replayed from a recording. Returns 201 with `analysis_id` and `events_url`. The pasted text and the PDF bytes are never written to the log's `source`. |
| `GET /api/analyses` | Analyses in this process, newest first. |
| `GET /api/analyses/{id}` | Status (`running`, `completed`, `failed`), event count, last seq. |
| `GET /api/analyses/{id}/events` | SSE stream. `?after=<seq>` or a `Last-Event-ID` header resumes. Ends after the terminal event. |
| `GET /api/analyses/{id}/log` | The full log as JSONL (what `fixtures/` files look like). |
| `DELETE /api/analyses/{id}` | Cancel. The log ends with `analysis.failed`, error `cancelled`. |

Every analysis is also appended, event by event, to `backend/data/runs/<timestamp>-<id>.jsonl`
(gitignored), so any run can be replayed with `{"kind": "replay", "run": "<file stem>"}`.

## How it fits together

- `envelope.py`: the event wrapper and log validation. Rules in `fixtures/README.md`.
- `documents.py`: the menu's document list. Joins demo texts and recordings by URL; also
  `recording_for_url`, which the pipeline uses to find the recording to continue from.
- `store.py`: analyses in memory. A producer appends through `Analysis.emit`; the SSE
  endpoint tails through `Analysis.wait_changed`. A replay and a live run are the same kind of
  producer, which is what keeps them indistinguishable to the frontend (design-doc D8).
- `replay.py`: emits a log's events at `t_ms / speed`, keeping the log's own `t_ms`.
- `pipeline.py`: the live pipeline. `run_live` emits `analysis.started`, runs ingestion in a
  worker thread inside the `ingest` stage (with `debug.note` lines about the fetch and the
  extraction), then either replays the recording that matches the document's URL, spans
  re-anchored to the live text, or fails at `extract` because step 11 is not built.
- `ingest/`: roadmap step 10. `canonical.py` is the contract's text form, `blocks.py` the one
  intermediate form and the assembly that computes regions while writing the text (so offsets
  are exact by construction), and one adapter per input: `html.py` (main content, chrome pruned,
  captions, footnotes, quotes, link cards), `aem.py` (Adobe Experience Manager `.model.json`, which
  is where shell.com keeps its text), `pdf.py` (PyMuPDF; running headers, footers and page numbers
  dropped, hyphenation repaired, columns in order, headings by font size), `text.py` (pasted or
  curated text with `#` and `-` markers, and the writer that produces the curated form).
  `fetch.py` fetches with a browser user agent and falls back to the Wayback Machine; a demo
  document's curated copy is used when its site refuses. `anchor.py` places spans written
  against another copy of the text by the contract's rules. Try it:
  `.venv/bin/python -m auditor.ingest <url or file> [--json | --text]`.
- `main.py`: routes and settings. `AUDITOR_FIXTURES_DIR` and `AUDITOR_RUNS_DIR` override the
  defaults.

SSE puts the whole envelope in `data:` rather than using the `event:` field, so a single
`EventSource.onmessage` handler in the frontend receives every event type, including ones the
contract adds later.
