# Fixtures and the event envelope

An analysis is an ordered stream of events (design-doc D8). A fixture, a live run and a
replay all use the same file format, so the frontend cannot tell them apart and replay
comes free. This file defines the **envelope**: the wrapper around every event and the
lifecycle events the transport needs. The **payloads** of domain events (claims, language
signals, evidence, dimension scores, verdicts, omissions, summary) and the closed lists of
event types and stage names are defined by the data contract in `contract/schema.json`
(roadmap step 2). The contract's `Event` definition and this envelope are the same thing;
if they ever disagree, the contract wins and this file is wrong.

## File format

One JSON object per line (JSONL), UTF-8, blank lines ignored. A fixture is
`fixtures/<name>.events.jsonl`, usually built by `contract/tools/contract.py build` from
`fixtures/<name>.analysis.json`; a plain `fixtures/<name>.jsonl` also works. Either is
replayed by `POST /api/analyses {"kind": "replay", "fixture": "<name>"}`.

```json
{"seq": 3, "t_ms": 1200, "type": "stage.started", "payload": {"stage": "extract"}}
```

| Field | Type | Rule |
|---|---|---|
| `seq` | int | Position in the log, 1-based and contiguous. Optional in files: assigned from line order when absent, checked against it when present. |
| `t_ms` | int ≥ 0 | Milliseconds since the analysis started. Non-decreasing. Replay emits each event at `t_ms / speed`; a live run stamps it from the clock. Author it for demo pace, not pipeline latency. |
| `type` | string | `namespace.verb`, lowercase, at least one dot, e.g. `claim.found`, `verdict.set`. |
| `payload` | object | Opaque to the transport. Shape per `type` is the data contract's. May be `{}`. |

No other top-level keys are allowed. Domain events do not carry a stage field; the stage
lifecycle events below bracket them.

## Lifecycle events (owned by the transport)

| Type | Payload | Rule |
|---|---|---|
| `analysis.started` | `{}` plus any descriptive keys (e.g. `source`) | Must be the first event. |
| `stage.started` | `{"stage": "<name>", "label"?: "<human text>"}` | Brackets the events a pipeline stage produces. |
| `stage.completed` | `{"stage": "<name>"}` | |
| `analysis.completed` | `{}` | Must be the last event. |
| `analysis.failed` | `{"error": "<message>"}` | Alternative last event. `error: "cancelled"` when the user stopped it. |

A log is valid when it starts with `analysis.started`, ends with exactly one terminal event
(`analysis.completed` or `analysis.failed`), and has neither of those anywhere else.
`analysis.started` also carries `contract_version` (required by the contract) and, for the
frontend's fixture list, `document_ref.title`. Stage names are the contract's `Stage` list:
`ingest`, `extract`, `language`, `substantiate`, `verify`, `consistency`, `omissions`,
`verdict`, `summary`. The transport checks the envelope and the lifecycle rules above; it
does not check payloads or the closed lists, which is the contract validator's job.

## Check a fixture

```sh
# envelope and lifecycle (what the API checks before replaying)
cd backend && .venv/bin/python -m auditor.validate ../fixtures/<name>.events.jsonl
# full contract: schema, spans, references, derivation rules
.venv/bin/python ../contract/tools/contract.py validate ../fixtures/<name>.events.jsonl
```

The first prints the event count, duration and a count per type, or the first violation
with its line number. The API's `GET /api/fixtures` reports the same, so a broken fixture
shows up in the app's fixture list instead of failing silently.

## Files

- `shell-climate.jsonl`: the step 2 fixture. The hand analysis of Shell's "Climate" page
  (`golden-reference.md`) as 239 events over about 24 seconds: document, 25 claims, 24 language
  signals, 31 evidence items, 100 dimension scores, 8 arguments, 25 verdicts, 4 omissions, summary.
  `shell-climate.analysis.json` is the same analysis folded into one object.
- `shell-our-climate-target.jsonl`: **the only end-to-end live run in the repo.** The pipeline
  over the Wayback capture of Shell's predecessor climate page of 14 March 2024, recorded
  2026-09-20 in 577 seconds: 27 claims, 27 verdicts, 11 omissions, every one of the nine stages
  run rather than replayed, and it validates clean. This is what the demo opens, because it is
  the recording of which "everything you see is the tool reading the page" is true. Its top
  finding is that the page never mentions Shell has since retired the 2035 intensity target it
  states, and its sharpest claim-level one is C4, where "supports the more ambitious goal of
  the UN Paris Agreement" is contradicted by the Transition Pathway Initiative's finding that
  Shell's intensity targets imply over 2°C.

  Every other recording of a Shell page in `backend/data/runs/` has between five and seven of
  its nine stages **replayed from `shell-climate.jsonl`** rather than run — they were made
  before step 18 removed the replay machinery, and their `stage.started` events say so in a
  `note`. None of them is a live run, so none is committed here. Three more, all exactly 24.0
  seconds long and byte-identical, are test artifacts built with faked model output.
- `smoke.jsonl`: transport smoke test. Lifecycle events only, about six seconds. Used for
  the roadmap step 3 visual check and as the quickest way to prove the stream works.
- `shell-climate.analysis.json` and `shell-climate.events.jsonl`: the hand analysis of the
  Shell "Climate" page (`golden-reference.md`) as an Analysis object and as the event log
  built from it. The primary demo document.

## Payloads

Payload shapes, the closed set of event types, the ordering rules between domain events and the
rules that derive a verdict are the data contract's: `contract/CONTRACT.md`, with
`contract/schema.json` as the machine form and `contract/types.ts` for the frontend. The contract
uses the stage names listed above. Check a real fixture against both layers:

```sh
cd backend && .venv/bin/python -m auditor.validate ../fixtures/shell-climate.jsonl        # envelope
.venv/bin/python contract/tools/contract.py validate fixtures/shell-climate.jsonl --analysis fixtures/shell-climate.analysis.json   # payloads, ordering, round trip
```
