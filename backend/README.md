# Backend

FastAPI service: creates analyses, streams their events over Server-Sent Events, and replays
saved event logs with their original timing. The pipeline stages (roadmap steps 10–18) plug
into `auditor/pipeline.py`, and all of them are built, so any document runs all the way
through: a request reads its text, URL or PDF into a contract Document, Claude finds the
claims, marks how they are worded and scores each claim's Clarity, matches every claim to the
criteria it is measured against and the precedents on similar wording from the curated stores
in `knowledge/`, searches the web for the facts and checks every quote it brings back against
the page it came from, recomputes the numbers and scores Support and Materiality, reads the
company against itself — its own filings and pages, and the Wayback Machine's captures of this
very page — and scores Consistency, measures the page against the material topics its
industry's reference names and writes a margin card for each one it leaves out, argues every
claim between a prosecutor and a defence and has a judge decide it, and finally aggregates the
lot into the summary header. Every entity is streamed as it is written.

Nothing is replayed. A recording of the same page, where one exists, is a reference to measure
against: each stage emits a `debug.note` comparing what it found with the golden reference, and
those notes are each step's visual check. A page nobody has recorded runs the same way.

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

The pipeline stages call Claude through `auditor/llm.py`: one client, one set of defaults, three
call shapes (`complete` for text, `extract` for a typed pydantic result via structured outputs,
and `extract_streaming`, which is `extract` plus a callback that receives each item of the
result's lists the moment it is complete in the stream, so a stage can emit as Claude writes).
Every request streams with adaptive thinking, and returns its token usage.

```sh
cp .env.example .env            # then put your key in ANTHROPIC_API_KEY
.venv/bin/python -m auditor.llm check     # one small call each way; prints model, effort, tokens
```

Defaults, overridable in `.env` or the environment: `AUDITOR_MODEL=claude-sonnet-5` (the team's
choice for now; `claude-opus-5` is the step up) and `AUDITOR_EFFORT=high` (`low` to `max`). The
built stages override the effort: claim extraction reads at `medium` (`AUDITOR_EXTRACT_EFFORT`),
because on the Shell page it found the same 24 of 25 golden claims as `high` in a third of the
time; the linguistic evaluator judges at `medium` too (`AUDITOR_LANGUAGE_EFFORT`), where it found
the same 17 of 24 golden signals as `high` with the first mark after 12 s instead of 24 s; the
substantiation evaluator matches at `low` (`AUDITOR_SUBSTANTIATE_MATCH_EFFORT`, a lookup with
judgment that should answer first) and scores at `medium` (`AUDITOR_SUBSTANTIATE_EFFORT`).
External verification retrieves at `medium` (`AUDITOR_VERIFY_RETRIEVE_EFFORT`) in parallel calls of
`AUDITOR_VERIFY_BATCH` claims (default 6), recomputes at `medium` (`AUDITOR_VERIFY_COMPUTE_EFFORT`) and
scores at `medium` (`AUDITOR_VERIFY_EFFORT`) in calls of `AUDITOR_VERIFY_SCORE_BATCH` (default 9).
Self-consistency searches the company's own material at `medium`
(`AUDITOR_CONSISTENCY_ELSEWHERE_EFFORT`) in parallel calls of `AUDITOR_CONSISTENCY_BATCH` claims
(default 8), compares each archived capture at `medium` (`AUDITOR_CONSISTENCY_ARCHIVE_EFFORT`)
and scores at `medium` (`AUDITOR_CONSISTENCY_EFFORT`) in calls of
`AUDITOR_CONSISTENCY_SCORE_BATCH` (default 9); `AUDITOR_CONSISTENCY_SNAPSHOTS` (default 3) is how
many captures of the page it reads, and 0 turns the archive axis off when a demo cannot wait for
the Internet Archive.
`python -m auditor.llm check --model claude-opus-5 --effort xhigh` tries another setting without
changing the file. Put the document text in `system` and pass `cache=True`: the cache breakpoint
goes on the system block, so every stage that sends the same document reads it from the cache
whatever its own task says.

Retrieval is the one stage that gives Claude tools: `web_tools()` in `llm.py` builds the search and
fetch server tools, which run on Anthropic's servers. It builds the **direct** pair
(`web_search_20250305`, `web_fetch_20250910`), not the newer dynamic-filtering pair, which runs the
search inside a code-execution sandbox: on the Ørsted page the filtering pair spent 228 s writing
plumbing and returned nothing quotable, the direct pair returned five verbatim quotes in 30 s. A
stage whose product is a quote wants the page in the context. `AUDITOR_WEB_TOOLS=filtering` switches
back, and `max_content_tokens` caps what one fetch may pour into the turn — without it a batch of SEC
filings puts a retrieval call over the 1M context window. A turn that runs server tools can stop with
`pause_turn`; `Llm._stream` sends it back to continue, up to `MAX_PAUSES` times, so a stage never
sees a half-finished answer.

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
  worker thread inside the `ingest` stage, then claim extraction inside `extract` (with
  `debug.note` lines about the fetch, the extraction and, when a recording exists, the match
  against the golden reference). When a recording matches the document's URL, live claims that
  overlap recorded ones take the recorded ids, the later stages replay from the recording with
  spans re-anchored and events about unmatched recorded claims dropped, and the summary's
  counts are recomputed. The language, substantiate and verify stages all run live in between,
  emitting straight into the log: `live_stages` names them, so their stage events, the evidence
  they emit and the dimensions they score (clarity from `language`, support and materiality
  from `verify`) are left out of the replay and references to the replaced evidence are
  stripped from the recorded scores and verdicts. The verdict stage runs live too, inside the
  replay: `live_verdict` is called where the recording's own verdict stage would have started,
  so the debate reads every score and evidence item that exists by then, the recorded ones
  included. A claim without all four dimensions (no recording ever had it, so nothing scored
  its Consistency) is left without a verdict, which is what the contract allows and the panel
  shows as neutral. Any verdict the replay does still emit has its likelihood and category
  re-derived by the contract's rules (§6) from the live scores, the recorded rationale kept.
  Without a recording the run stops at `verdict`, because the verdict layer runs inside the
  replay and the summary (step 18) is not built.
- `omissions.py`: roadmap step 16, D4 Q3 — the margin cards. The materiality reference for the
  company's industry (`materiality.py`) is the list "not mentioned" is measured against; Claude
  says for each of its topics whether the page addresses it and writes a card where it does
  not, with the nearest passage the page does contain. That passage is placed in the text
  (`extract.locate`) and dropped if it is not there, and each topic's own words are looked for
  in the document (`materiality.mentions`): a card whose words are present with no passage to
  explain them loses confidence, one whose words are all absent carries that in `ext.absence`.
  Every card cites the reference that makes its topic material and whatever evidence the
  earlier stages retrieved that establishes the omitted fact. The document-level Completeness
  score is returned rather than emitted; step 18 folds it into the summary.
  `.venv/bin/python -m auditor.omissions ../demo-documents/shell-climate-2026-09-19.md --golden ../fixtures/shell-climate.analysis.json`
  runs the stage on the reference's own claims and evidence and compares the cards it writes.
- `materiality.py`: the third knowledge store, `knowledge/materiality.json` — one entry per
  industry, an external standard (SASB, GRI 11, ESRS E1) with the disclosure topics that
  industry's documents are read against, and per topic the words that appear when a page does
  address it. A document is placed by its `Document.industry` codes, then by its label; one
  the store cannot place is placed by Claude, and every document is also measured against the
  cross-industry entry. `check [--fetch]` validates the store and looks for every quote on its
  page; `coverage <file or url>` prints which of the reference's words are in a document and
  which are not, with no model in the loop.
- `calibration.py`: roadmap step 19, D5 "Rigour guarantees" — the audit scored on the only
  ground truth this project has. Each of the 24 precedents is a labelled case: its wording is
  analysed with **its own ruling taken out of the store** (`Knowledge.without`, the leave-one-out
  rule in demo-documents.md §6), and what a regulator decided is the label. A precedent gives a
  wording and nothing else, so only Clarity and Support run — the two this set is ground truth
  for; Materiality and Consistency need a document and a company's record, and external
  verification would find the very ruling held out. The debate is not run either: likelihood is
  derived, not judged, so it cannot move the number being measured.
  `.venv/bin/python -m auditor.calibration run --out data/calibration.json` scores the set
  (about two calls a case) and `report data/calibration.json` recomputes the metrics, moves the
  threshold and redraws the curve without paying again. `GET /api/calibration` serves the saved
  report to the metrics page. The committed run: precision 84%, recall 94%, Brier 0.14, and a
  curve that is honest at the top (predicted 0.83, observed 0.83) — but **0 of 3 negatives were
  cleared**, and the report says in as many words that 3 negatives cannot support a precision
  figure. The threshold sweep is in the report: at 0.8 all three are cleared at 100% precision
  and recall falls to 41%.
- `summary.py`: roadmap step 18, D6 "Aggregation" — the header, from the results beneath it.
  Nothing here is a model's opinion: the profile, the headline and the ranking are arithmetic,
  and each number records in `ext.drivers` the claims it came from, which is the step's visual
  check. The mean leans to the worst of the page — each claim's say is its prominence, its
  confidence and the square of how bad it is — because a plain mean would let twenty true
  footnotes bury one false headline, the document-level form of the failure weakest-link
  prevents at claim level. Completeness comes from the omissions, which have no prominence.
  Claude is asked for one thing, at the end: a title for each issue and each credit, and the
  narrative. Measure it without calling a model:
  `.venv/bin/python -m auditor.summary ../fixtures/shell-climate.analysis.json --explain`
  prints the arithmetic and compares the header with the reference's hand-written one.
- `verdict.py`: roadmap step 17. A prosecutor and a defence argue each claim in two calls that
  cannot see each other, from one dossier: the claim, its four dimension scores with their
  bases, its language marks and every evidence item linked to it. A judge then reads both and
  writes the rationale, the pattern tags, the fix and the honest rewrite. The numbers are not
  the model's: likelihood is the largest of the four scores (weakest link, contract §6) and
  the category follows the contract's rule. Confidence is the formula §6 left to this step —
  the deciding dimension's confidence, capped by what the evidence is worth, less a flat
  humility and penalties for evaluator conflict and for a judge that did not reach the same
  category (`AUDITOR_VERDICT_SAMPLES` above 1 adds repeated judges and measures whether they
  agree with each other). Tags are proposed by rule from the scores, marks and evidence
  relations, then kept or dropped by the judge. Measure it against the golden reference:
  `.venv/bin/python -m auditor.verdict --calibrate ../fixtures/shell-climate.analysis.json`
  prints the confidence formula's error over the 25 hand-scored claims and calls no model;
  `.venv/bin/python -m auditor.verdict ../demo-documents/shell-climate-2026-09-19.md --golden ../fixtures/shell-climate.analysis.json`
  runs the debate on the reference's own scores and compares the verdicts it reaches.
- `consistency.py`: roadmap step 15, the demo headliner (D2) — the company against itself, on
  two axes that run in parallel. **Elsewhere**: parallel calls at medium effort, each with the
  search and fetch tools, look through the company's *own* publications only — the annual
  report and the 20-F and above all their risk factors and cautionary statements, the assured
  GHG statement, the transition strategy report where targets are set and retired, the FAQ and
  methodology pages — for the same target with a different number, a condition the filings
  disclose and the page omits, or small print the page's impression cannot survive. Independent
  evidence is step 14's job; keeping the two apart is what makes this stage's finding hard to
  argue with. **Over time**: `ingest.fetch.wayback_history` lists every distinct capture of the
  page under analysis, `spread` picks a few *evenly over the time the archive covers* (the
  archive captures in bursts, so spreading over the list would read one week and miss a year),
  and each is read with the same ingestion the live page went through. What the archive holds
  for a modern corporate page is the JavaScript shell, so a thin capture is re-read from the
  content model captured nearest it — and the timestamp is read back from the archive's own
  redirect, so a 2025 shell is never labelled with content the archive only holds from 2026.
  Citation integrity is step 14's bar: a quote from the company's other material is fetched and
  looked for in the page, and a quote from a capture is looked for in the capture this module
  already holds, so that half needs no network at all. An unverified quote is never displayed.
  The relation an archived version bears to a claim is derived from what changed, not asked for
  (as `tier` is derived from `independence` in step 14): a target weakened, dropped, delayed,
  narrowed, restated or softened `contradicts_framing`, because "15-20% by 2030" is still
  literally true today; only the impression of steady progress is not. A target changed before
  it was met is marked `ext.greenrinsing`, which is the evidence for the contract tag step 17
  assigns. Then Consistency is scored from both axes, and one band inverts the other
  evaluators: **finding no contradiction is mildly good news, not a problem**, so it scores
  0.3–0.4 at middling confidence and an unassessed claim gets a 0.3/0.2 placeholder rather than
  the 0.5 the other stages use — a stage that found nothing must never be what pushes a claim's
  likelihood (the weakest link, contract §6) above neutral. `compare_consistency` measures a
  result against the golden reference, by host and by which claims the company contradicts
  itself on. Try it:
  `.venv/bin/python -m auditor.consistency ../demo-documents/shell-climate-2026-09-19.md --golden ../fixtures/shell-climate.analysis.json`,
  and the archive on its own, which is how to tell before a demo whether a page has any history
  worth reading: `.venv/bin/python -m auditor.consistency --history "<url>"`.
- `knowledge.py`: the curated stores in `knowledge/` (criteria and precedents; see the README
  there). Loads and validates both files by the contract's evidence rules, turns an entry into
  the evidence item the log carries (`K1..` for criteria, `P1..` for precedents, the store key
  in `ext.store_id`), holds out a precedent that adjudicated the very page under analysis, and
  checks the store: `.venv/bin/python -m auditor.knowledge check --fetch` fetches every URL and
  looks for each verified quote on its page. `AUDITOR_KNOWLEDGE_DIR` overrides the directory.
- `verify.py`: roadmap step 14, and the three things in it. **Live retrieval**: parallel calls at
  medium effort, each with the search and fetch tools, return sources with a URL and a verbatim
  quote for the claims in their batch; the tier is derived here from who stands behind the source
  (regulator 1, assured filing or government 2, independent 3, news 4, the company itself 5), not
  chosen by the model, and a tier-5 `supports` link is turned into `context`, because a company
  cannot substantiate its own claim (D5). **Citation integrity**: every URL is fetched from here
  (`knowledge.page_text`) and the quote looked for in the page (`knowledge.quote_in`, the store
  check's own bar). Found: `verified`, `fetched_exact`. Otherwise the item is listed by name, its
  quote dropped and the reason in its `note` — and the run keeps the two reasons apart, because
  they are not the same thing: a quote the page does not contain is a citation rejected, while a
  page that will not open (sec.gov refuses this network outright and its filings have no Wayback
  snapshot) is a gap the machine could not close. **Numbers recomputed**: a call with no tools
  turns the retrieved figures into arithmetic; `evaluate` runs the expression here (plain
  arithmetic over the named inputs, nothing else), and a computation is dropped unless it
  reproduces the number the model claimed and its sentence states that number. A computation's
  tier is its worst input's, or 5 when its figures come off the document itself. Then Support and
  Materiality are scored in parallel batches from the criteria and precedents and the facts
  together — Support belongs to this stage because that is the dimension's definition (D6), and
  the contract allows one score per claim per dimension. `compare_scores` and `compare_sources`
  measure a result against the golden reference. Try it:
  `.venv/bin/python -m auditor.verify ../demo-documents/shell-climate-2026-09-19.md --golden ../fixtures/shell-climate.analysis.json`,
  and the citation check on its own:
  `.venv/bin/python -m auditor.verify --check-quote "<url>" "<quote>"` (exit 1 when the quote is not there).
- `substantiate.py`: roadmap step 13. One call at low effort matches every claim to the
  criteria it is measured against and the rulings on similar wording, each match emitted as
  `evidence.added` (relation `criteria` or `precedent`) the moment it closes in the stream;
  it can also score Support from the criteria and precedents alone (parallel batches at medium
  effort), which is what `--no-score` turns off and what the pipeline no longer asks for: step
  14 scores Support once, from the rules and the facts together.
  `compare_links` and `compare_support` measure a result against the golden reference:
  `.venv/bin/python -m auditor.substantiate ../demo-documents/shell-climate-2026-09-19.md --golden ../fixtures/shell-climate.analysis.json`.
- `language.py`: roadmap step 12. Claude returns word-level language signals (the contract's 18
  kinds, three polarities) and a Clarity score per claim as structured output. The claims go
  out in parallel batches of `AUDITOR_LANGUAGE_BATCH` (default 9) plus one call for the page as
  a whole, because one call over every claim thinks for minutes before writing a word; each
  signal is placed the moment it closes in the stream (inside the claim's own spans first, then
  its paragraph, then anywhere; exact, then normalised, then case-insensitive) and emitted, so
  the Language layer fills in while the model works. A claim the model skips gets a neutral
  placeholder score at low confidence, so every claim has its Clarity dimension. `compare_signals`
  and `compare_clarity` measure a result against the golden reference. Try it (the reference's
  own claims are the input, so the evaluator is measured on the hand-analysed claims):
  `.venv/bin/python -m auditor.language ../demo-documents/shell-climate-2026-09-19.md --golden ../fixtures/shell-climate.analysis.json`.
- `extract.py`: roadmap step 11. Claude returns claims as structured output; every quote is
  placed in the canonical text (exact, then quotation marks and dashes normalised, then
  case-insensitive), numbered in document order and labelled with its paragraph. `compare`
  scores a result against a reference by span overlap. Try it:
  `.venv/bin/python -m auditor.extract ../demo-documents/shell-climate-2026-09-19.md --golden ../fixtures/shell-climate.analysis.json`.
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
