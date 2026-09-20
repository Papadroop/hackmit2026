# Greenwashing Auditor — Roadmap

Companion to `design-doc.md`; D-numbers refer to its decisions.

## How the plan works

- **Frontend first, against a fixture.** One real document is analysed by hand and written down in the agreed data format. The whole interface is built on that file before any pipeline exists.
- **One mechanism for fixture, live and replay.** An analysis is an ordered stream of events. Replay reads them from a file; live receives them from the pipeline. The frontend cannot tell the difference, so replay (D7) comes free, and each backend stage can be switched from fixture to real one at a time.
- **Every step ends in a visual check in the app.** Do not start the next step until it passes.
- **Every stage stays inspectable.** A debug drawer listing raw events did this until
  2026-09-20, when the analysis screen was rebuilt around four sections and the drawer was
  dropped as one of them; the raw log is served at `GET /api/analyses/<id>/log`, and the
  header shows a tick per stage as it completes.

## Phase 0 — Foundations

| # | Build | Visual check |
|---|---|---|
| 1 | Choose 2–3 demo documents: one likely greenwashing, one likely clean, one mixed. Analyse one by hand: claims, types, language signals, some evidence, an omission, verdicts. | The team reads the annotated document and agrees with it. It becomes the golden reference for later steps. |
| 2 | Data contract: schemas for claim, language signal, evidence item, dimension score, verdict, omission and summary, plus the event types that carry them. Write the hand analysis as an event log. | The fixture validates against the schema. |
| 3 | Skeleton: frontend, API, and a replay endpoint that streams the fixture with timing. Debug drawer. | Open the app, press Analyse, watch events arrive in the drawer. |

## Phase 1 — Interface on the fixture (D7)

| # | Build | Visual check |
|---|---|---|
| 4 | Document pane: render the text, highlight claim spans in neutral. | Every highlight covers exactly the right words. Span anchoring is the likeliest source of bugs; settle it here. |
| 5 | Live progression and encoding: highlights move from neutral to verdict colour; intensity for confidence; second channel. | A replay settles convincingly; a low-confidence claim looks tentative; still readable in greyscale. |
| 6 | Claim panel: dimensions with confidence, verdict, pattern tags, evidence cards, debate (collapsed), fix, honest rewrite. | Click every claim. Every field in the contract is visible somewhere. |
| 7 | Summary header: headline likelihood and confidence, dimension profile, verdict distribution, top issues. | Click a top issue; the document scrolls to its claim. |
| 8 | Layers toggle: Claims, Language (word-level marks), Omissions (margin cards). | Each layer switches on and off cleanly. |
| 9 | Honest version toggle: document-wide diff. | Diffs line up with their claims. |

**Milestone A:** a complete demo on fixture data. From here on there is always something to show.

## Phase 2 — Pipeline, one stage at a time

Each stage replaces its part of the fixture with real output. Everything downstream stays fixture until its turn.

| # | Build | Visual check |
|---|---|---|
| 10 | Ingestion: text, URL and PDF to clean text with stable character offsets. | All demo documents load; text is clean, with no menus or footers. |
| 11 | Claim extraction (D4 Q1): atomic claims with span, scope and type. | Highlights on the hand-analysed document match the golden reference. Then try a document never seen before. |
| 12 | Linguistic evaluator (D4 Q2): language signals and the Clarity score. | The Language layer marks hedges and vague terms sensibly on a real document. |
| 13 | Knowledge stores and substantiation evaluator: criteria and precedents; match claims to both. | A "carbon neutral" claim shows its criteria and a similar precedent with a working link. |
| 14 | Live retrieval, external verification, citation integrity: tiered evidence per claim; numbers and proportionality checked; quotes verified. | Open three evidence links by hand; each quote is on the page. Feed in a fake quote; it is rejected. |
| 15 | Self-consistency evaluator: the company's filings and archived page versions. | One claim shows a contradiction in the company's own words, with source. |
| 16 | Omissions (D4 Q3): materiality reference per industry, compared with topics covered. | Margin cards name a material topic that is truly absent from the document. |
| 17 | Verdict layer (D5, D6): debate, weakest-link combination, confidence, derived labels, fix, rewrite. | No fixture data left in the claim panel. A specific-but-false claim gets high likelihood. A claim with no evidence gets low confidence, not high likelihood. |

**Milestone B:** end to end on real documents.

## Phase 3 — Zoom out, prove it, harden

| # | Build | Visual check |
|---|---|---|
| 18 | Aggregation (D6): document summary from real results; company view across documents, with trend. | Summary numbers can be explained from the claims beneath them. The company page shows at least two documents. |
| 19 | Calibration: run held-out precedents; metrics page with precision, recall and calibration curve. | The chart is in the app. If calibration is poor, adjust the combination and re-run. |
| 20 | Demo hardening: record replays of the demo documents; rehearse the narrative (D2). | The full demo runs with the network off. |

## Parallel work

The steps are ordered, but the team is four. Once the contract (step 2) exists:

- **Curating criteria and precedents (step 13) is the long pole.** It is human reading, not code. Start it immediately.
- Ingestion and extraction (10, 11) can be built against the contract while the interface is under way.
- Integration still happens in order. A stage is not done until its visual check passes in the app.

## Pace

- Milestone A at about one quarter of the time.
- Milestone B at about three quarters.
- Feature freeze with a few hours left for step 20.

## If behind, cut in this order

1. Honest version toggle (9); keep the per-claim rewrite.
2. Company view (part of 18).
3. Archived versions in 15; keep filings.
4. Debate in 17; fall back to a single judge.

Never cut: citation integrity (14), calibration (19; shrink the set instead), replay (20).
