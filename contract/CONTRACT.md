# Data contract

*Phase 0, step 2 of `roadmap.md`. Version 1.0.0. The machine-readable form is `contract/schema.json` (JSON Schema draft-07); this file explains it. D-numbers refer to `design-doc.md`.*

Last updated: 2026-09-19

## 1. What it is, and the files

An analysis is an ordered stream of events (D8). The **transport** owns the envelope around each event and the lifecycle events it needs to run a stream; that is written down in `fixtures/README.md` and implemented in `backend/auditor/envelope.py`. The **contract** owns everything inside `payload`: the entities (document, claim, language signal, evidence item, dimension score, argument, verdict, omission, summary), the domain event types that carry them, the ordering rules between them, and the rules that derive a verdict from its scores.

| File | Role |
|---|---|
| `contract/schema.json` | Source of truth. Root validates one event; `definitions` hold the entities, enums, payloads and the folded `Analysis` object. Draft-07 so it works unchanged with `jsonschema` (Python), `ajv` (already in `frontend/node_modules`), VS Code and type generators. |
| `contract/types.ts` | TypeScript types generated from the schema. Regenerate, never edit. |
| `contract/tools/contract.py` | `resolve` spans, `build` an event log from an analysis file, `validate` a log or an analysis, `fold` a log back into an analysis. |
| `contract/tools/gen_types.sh` | Regenerates `types.ts`. |
| `contract/requirements.txt` | `jsonschema` for the tool. |
| `fixtures/shell-climate.analysis.json` | The golden reference (`golden-reference.md`) as data: the folded `Analysis` object. |
| `fixtures/shell-climate.jsonl` | The same analysis as an event log with demo pacing. This is what the app replays. |
| `fixtures/smoke.jsonl` | Transport-only smoke test (lifecycle events, no payloads). Valid for the transport, not for the contract; that is intended. |

Validate everything:

```sh
python3 -m venv .venv && .venv/bin/pip install -r contract/requirements.txt
.venv/bin/python contract/tools/contract.py validate-analysis fixtures/shell-climate.analysis.json
.venv/bin/python contract/tools/contract.py validate fixtures/shell-climate.jsonl --analysis fixtures/shell-climate.analysis.json
cd backend && .venv/bin/python -m auditor.validate ../fixtures/shell-climate.jsonl      # transport rules only
```

Regenerate the types after any schema change:

```sh
contract/tools/gen_types.sh
```

(The generator only emits definitions reachable from the root, so the script wraps `Event` and `Analysis` in one root first; the `Contract` type it emits is that wrapper and can be ignored.)

## 2. The envelope and the event types

Envelope (transport-owned, restated here): `{"seq": 3, "t_ms": 1200, "type": "claim.extracted", "payload": {...}}`. Only those four keys. `seq` is 1-based and contiguous and may be omitted in files (assigned from line order). `t_ms` is milliseconds since `analysis.started`, non-decreasing; replay honours it, a live run stamps it. `type` is lowercase `namespace.verb`.

The contract closes the set of types. Anything else is rejected by `schema.json`; the transport alone would let it through.

| Type | Payload | Emitted by | Meaning |
|---|---|---|---|
| `analysis.started` | `{contract_version, analysis_id?, mode?, document_ref?, source?, ...}` | transport / pipeline | First event. `contract_version` is required so a consumer can refuse a log it does not understand. Extra descriptive keys allowed. |
| `stage.started` | `{stage, label?, note?}` | pipeline | Opens a stage. `label` is the human text for the progress display. |
| `stage.completed` | `{stage, note?}` | pipeline | Closes it. |
| `document.ingested` | `{document}` | ingest | The canonical text, regions and metadata. Before any claim. |
| `claim.extracted` | `{claim}` | extract | One atomic claim (D4 Q1). Appears in neutral until scored. |
| `language.signal` | `{signal}` | language | A word-level mark or a document-level observation (D4 Q2). |
| `evidence.added` | `{evidence}` | any evaluator, omissions | One evidence item with its links to claims or omissions (D5). |
| `dimension.scored` | `{score}` | the evaluator that owns the dimension | One dimension of one claim (D6). |
| `omission.found` | `{omission}` | omissions | A margin card: a material topic the text does not address (D4 Q3). |
| `argument.made` | `{argument}` | verdict | A prosecutor, defence or judge turn for one claim (D5). |
| `verdict.issued` | `{verdict}` | verdict | The claim's likelihood, confidence, category, tags, fix and rewrite. |
| `summary.updated` | `{summary, final}` | summary | The header. May be emitted more than once; exactly one has `final: true` before `analysis.completed`. |
| `analysis.completed` | `{duration_ms?, counts?}` | transport / pipeline | Last event. |
| `analysis.failed` | `{error, stage?}` | transport / pipeline | Alternative last event. `error` is `"cancelled"` when the user stopped it. |
| `debug.note` | `{text, ...}` | anyone | Free-form line for the debug drawer. |

Stages, in canonical order, named as the transport already uses them: `ingest`, `extract`, `language` (Linguistic evaluator), `substantiate` (Substantiation), `verify` (External verification), `consistency` (Self-consistency), `omissions`, `verdict`, `summary`.

### Ordering rules (checked by `contract.py validate`)

1. `extract` starts after `ingest` completes. The four evaluators and `omissions` start after `extract` completes and **may overlap**; `verdict` starts after all five complete; `summary` after `verdict`. Each stage starts and completes at most once.
2. Each domain event is emitted while its owning stage is open: `document.ingested` in `ingest`; `claim.extracted` in `extract`; `language.signal` and clarity scores in `language`; support scores in `substantiate` or `verify`; materiality scores in `verify`; consistency scores in `consistency`; `evidence.added` in any evaluator or `omissions`; `omission.found` in `omissions`; `argument.made` and `verdict.issued` in `verdict`; `summary.updated` in `summary`.
3. **Nothing is referenced before it exists.** A claim before any signal, score, argument or verdict that names it; an evidence item before any score, omission, argument, verdict or computation that cites it; every one of a claim's four dimensions before its verdict; every target of the summary before the summary.
4. Exactly one score per claim per dimension and exactly one verdict per claim. (Live mode may later allow re-scoring; that would be a minor version with a "last wins" rule. Until then, duplicates are errors.)
5. `analysis.completed.counts`, when present, equals what the log contains.

### Fixture pacing

`contract.py build` lays the fixture out for the live progression in D7: claims arrive one by one in neutral, then the language marks, then the evidence, then the scores, then the arguments and verdicts, then the summary. The evaluators are opened together and closed together, as they will run live. Total about 24 seconds; the replay endpoint takes a `speed` factor.

## 3. Document text, spans and regions

`Document.text` is **canonical plain text**: NFC-normalised; every Unicode space (including U+00A0, which the Shell page contained ten times) becomes an ASCII space; no tabs, carriage returns, runs of spaces, or spaces at line boundaries; `\n` line breaks; blocks separated by exactly one blank line; no markdown markers. The ingestion step (roadmap 10) must produce this form; the validator refuses anything else, because every offset depends on it.

A **Span** is `{text, start, end, context?, occurrence?}`. `text` is authoritative and must equal `Document.text[start:end]` (Unicode code points, which is what Python gives; in JavaScript, index by code point or use `text` to re-anchor, since UTF-16 offsets differ once a non-BMP character appears). `context` (a unique substring containing `text`) or `occurrence` (1-based) disambiguate repeated phrases, and let `contract.py resolve` recompute offsets if the text changes.

**Regions** label ranges of the text: `title`, `heading` (with `level`), `paragraph` (with a `label` such as `P4` and a `prominence`), `list_item`, `footnote`, `cautionary_note`, `promo`, `quote`, `caption`, `other`. Regions of the same kind never overlap; different kinds nest. `prominence` is 1.0 for the hero, about 0.6 for body, 0.3 for footnotes and cautionary notes; step 18 uses it to weight claims in the document summary.

## 4. Entities

**Claim** (D4 Q1): `id`, `spans` (first is the primary highlight; more for repeats), `type` ∈ {factual, commitment, comparative, vague_attribute, certification}, `scope` ∈ {product, packaging, operations, supply_chain, company, other} with a free `scope_note`, `attribute`, optional `quantity`, `baseline`, `timeframe`, `paragraph` label, `prominence`, `note`.

**LanguageSignal** (D4 Q2): `id`, `level` ∈ {claim, document}, `kind` (hedge, vague_term, undefined_term, comparative_without_baseline, weak_verb, qualifier_present, qualifier_absent, scope_mismatch, responsibility_diffusion, framing, ratio_language, intensifier, approximation, buried_admission, prominence, share_of_attention, emotive, register), `polarity` ∈ {flag, benign, credit}, `spans` (word-level; required for claim level), `note`, `claim_ids`, `strength`. `benign` exists so the Language layer visibly does not flag everything; `credit` marks a qualifier or precision that counts in the text's favour.

**EvidenceItem** (D5): `id`, `kind` (ruling, law, filing, report, dataset, standard, company_page, press_release, news, archive, computation, other), `tier` 1–5 (1 regulator ruling, court judgment, law; 2 audited or assured filing, government or intergovernmental data; 3 independent dataset or standard; 4 news; 5 the company's own material), `source {name, publisher?, date?, locator?}`, `url?`, `quote?`, `verified`, `verification` ∈ {fetched_exact, fetched_by_eye, second_party_fetch, computed, unverified}, `retrieved`, `stage`, `links` (one or more `{target, relation}` where target is a claim or omission id), `computation {formula, inputs, result}` and `derived_from` for computations, `note`.

- `relation` is from the target's point of view: `supports` and `contradicts` concern the literal content; `contradicts_framing` means the literal content stands but the impression does not; `context` is background or materiality; `precedent` is a ruling on similar wording; `criteria` is a rule the claim is measured against. For an omission, `supports` means the evidence establishes the omitted fact.
- `verified: true` requires a `quote` and a verification method other than `unverified`. **Unverified quotes are never displayed** (D5 citation integrity); an unverified item may still be listed by name.
- Tier-5 material can `contradict` its author and can be `context`; the validator warns if it is listed as `supports` for a claim, because a company cannot substantiate its own claim (D5).
- Computations are evidence too, so "numbers recomputed" is visible in the panel: `kind: computation`, `verification: computed`, the `quote` is the result sentence, and `derived_from` names the inputs. A computation's tier may not be better than its worst input.

**DimensionScore** (D6): `claim_id`, `dimension` ∈ {clarity, support, materiality, consistency}, `score` (a *problem* score: 0 no signal, 1 maximal), `confidence`, `basis` (one sentence), `evidence_ids`, `stage`.

**Argument**: `claim_id`, `role` ∈ {prosecutor, defence, judge}, `text`, `evidence_ids`.

**Verdict** (D6): `claim_id`, `likelihood`, `confidence`, `category` ∈ {supported, unsubstantiated, misleading_by_framing, contradicted}, `tags` (the seven sins: hidden_trade_off, no_proof, vagueness, irrelevance, lesser_of_two_evils, fibbing, false_labels; plus greenrinsing, a target changed before it is met), `rationale` (the judge), `fix`, `rewrite`, `evidence_ids`.

**Omission** (D4 Q3): `id`, `topic` (the margin card title), `why_material`, `materiality_reference` (e.g. a SASB topic), `complete_text` (what the document would say), `score`, `confidence`, `evidence_ids`.

**Summary** (D6, D7): `headline {score, confidence}`, `dimensions {clarity, support, materiality, consistency, completeness}` each `{score, confidence}`, `verdict_distribution`, `top_issues [{rank, target, title}]` (targets are claim or omission ids, so the header can link to them), `credit [{target, title}]`, `claim_count`, `omission_count`, `narrative`.

**Analysis**: the folded object, `{analysis_id, contract_version, mode, document, claims, signals, evidence, scores, arguments, verdicts, omissions, summary}`. The frontend's reducer is a fold over the events; `contract.py fold` is the reference implementation and the round-trip check proves the fixture's log folds back to its analysis file exactly.

Every entity has an optional `ext` object for anything not in the contract, so `additionalProperties: false` can stay on everywhere else and typos fail loudly.

## 5. Ids

Strings matching `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$`, unique across all entity types within an analysis (a link target can then be a claim or an omission without a type field). Fixture ids are short and stable (`C1`, `L11`, `E8b`, `X3`, `O2`); live ids may be generated.

## 6. Derivation rules (checked by the validator)

These are the rules the golden reference was scored under. They are deliberately simple; step 17 may refine them, and any refinement is a contract change.

- **Likelihood** of a claim = the maximum of its four dimension scores (weakest link, D6). Exact.
- **Category**, in order:
  1. `contradicted` if some evidence item links to the claim with relation `contradicts` and (Support ≥ 0.7 with confidence ≥ 0.6, or Consistency ≥ 0.7 with confidence ≥ 0.6).
  2. `unsubstantiated` if Clarity ≥ 0.7 (too vague to verify), or if Support is between 0.4 and 0.6 with confidence below 0.6 (nothing found either way).
  3. `misleading_by_framing` if the likelihood is above 0.5.
  4. `supported` otherwise.

  Consequences worth knowing: a claim whose only weakness is materiality at 0.5 is `supported` and carries that 0.5 as a visible caveat (Shell's operational-emissions claims); an item that contradicts only the *framing* does not make a claim `contradicted` (Shell's LNG claim is `misleading_by_framing` even though its own report contradicts the impression). These were the two open points in `golden-reference.md` §9; the rules above settle them.
- **Confidence** of a verdict is bounded by its dimensions: not above the highest dimension confidence, not more than 0.1 below the lowest. In the fixture it is a judgment. Step 17 defines the formula, implemented once in `backend/auditor/verdict.py` (`verdict_confidence`):

      confidence = min(base, evidence cap) - 0.05 - conflict - dissent - instability

  *base* is the confidence of the **deciding dimension**, the weakest link whose score is the likelihood; ties go to the least confident of the tied dimensions, then to the order above. *evidence cap* is what the evidence is worth: **0.55 when no evidence is linked to the claim at all** ("no evidence found" lowers confidence, D6), and otherwise, **only when the deciding dimension is Support, Materiality or Consistency**, the best tier reached among the items that bear on whether the claim holds (relation `supports`, `contradicts` or `contradicts_framing`; `criteria`, `precedent` and `context` count only when there are none) — tier 1 → 1.00, 2 → 0.95, 3 → 0.85, 4 → 0.75, 5 → 0.65. Clarity is read from the text, so no tier makes a vagueness reading surer. Then a flat **0.05** for humility, because no single evaluator decides a verdict; **0.10 conflict** when evidence both supports and contradicts the same claim (evaluator disagreement); **up to 0.10 dissent** when the judge did not reach the derived category itself, and **up to 0.10 instability** when repeated judges disagree with each other (judge consistency). Finally the bounds above, which win: a dimension nobody scored counts as confidence 0 there, so a missing evaluator cannot hold a verdict's confidence up.

  The validator still checks only the bounds, because two of the inputs (the judge's own read, the number of samples) live in `Verdict.ext.judge` rather than in the contract. Measured against the golden reference's 25 hand-assigned confidences the formula's mean absolute error is 0.04, 23 of 25 inside 0.10: `python -m auditor.verdict --calibrate fixtures/shell-climate.analysis.json` prints the table and calls no model.
- **Pattern tags** are computed, not judged separately (D6): rules over the dimension scores, the language signal kinds and the evidence relations propose candidates, and the judge keeps the ones the evidence bears out, drops the rest and may add from the closed taxonomy. On the golden reference the rules alone recover 17 of its 19 tags before any judge runs.
- Step 17 **did not refine the likelihood and category rules**: weakest-link and the four-branch category rule are D6's design, not placeholders, so they stand as written and the contract is unchanged. What step 17 added is above, plus `Verdict.ext.confidence_basis` (one sentence naming what set the confidence) and `Verdict.ext.judge` (`own_category`, `own_likelihood`, `agreement`, and `dissent`, `samples`, `stability` where they apply) — all inside `ext`, so no schema change.
- **Document summary** numbers are not derived by the validator beyond consistency checks (distribution equals the verdict counts, counts equal the lists, ranks are 1..n, targets exist). Step 18 owns the aggregation, implemented in `backend/auditor/summary.py` (`aggregate`):

  Every header number is a **weighted Lehmer mean** over the claims beneath it — each claim's say is `prominence x confidence x score^2`, so the number sits near the worst of what the page says without ever leaving the range of the scores or resting on one sentence. A plain weighted mean was tried and rejected: it lets twenty true footnotes bury one false headline, which is the document-level form of the failure weakest-link prevents at claim level (D6). Each of the four dimensions is aggregated over its own scores, the **headline** over the verdict likelihoods, and **Completeness** over the omissions (which are not said anywhere, so confidence alone weights them). A profile entry's confidence is the same mean over the confidences of the claims that set its score, so it says how sure we are of *that* number rather than of the page.

  **Top issues** are claims and omissions together, ordered by the same weighted severity the mean uses; **credit** is the lowest-likelihood `supported` claims, most prominent first. Every number records the claims it came from in `summary.ext.drivers`, and `summary.ext.power` the exponent used — the step's visual check is that the header can be explained from the claims beneath it. The titles and the narrative are the one thing asked of a model, after the numbers are fixed.

  Against the golden reference's hand-written header the profile's mean absolute error is about 0.08, and the ranking picks 3 of its 5 top issues and 3 of its 4 credits. The reference was a judgment and this is arithmetic; they are closest on Completeness and Consistency and differ most on the headline (0.70 against 0.80), which is the price of the dilution resistance above.

## 7. Fixture authoring

1. Save the document text under `demo-documents/` in canonical form (§3).
2. Write `fixtures/<name>.analysis.json` with spans as `text` (plus `context` or `occurrence` where a phrase repeats) and offsets left at 0.
3. `contract.py resolve <file> --write` fills the offsets and refuses ambiguous or missing spans. For the Shell page all 63 spans from the golden reference anchored on the first run, once whitespace was normalised.
4. `contract.py validate-analysis`, then `contract.py build <file> fixtures/<name>.jsonl`, then `contract.py validate fixtures/<name>.jsonl --analysis <file>`.
5. Every `fixtures/*.jsonl` is listed by `GET /api/fixtures` and replayable with `POST /api/analyses {"kind": "replay", "fixture": "<name>"}`.

The golden reference's precedent items (ASA on Shell, the Paris court on TotalEnergies) are evidence in this fixture; the hold-out rule for the precedent store is in `demo-documents.md` §6.

## 8. Rendering rules the contract implies (for steps 4–9)

- Colour encodes `verdict.category`; intensity encodes `verdict.confidence`; a second channel (icon or underline style) repeats the category so meaning never rests on colour alone (D7). Until a verdict arrives a claim is neutral.
- A claim's panel shows the four `DimensionScore`s with their `basis`, the verdict's `rationale`, `tags`, `fix` and `rewrite`, the linked evidence items with tier and relation, and the arguments collapsed.
- An evidence card shows `quote` only when `verified` is true; otherwise the source name, url and note.
- `LanguageSignal.polarity` picks the mark style; `benign` and `credit` are visibly different from `flag`.
- Omissions have no span; they render as margin cards with `topic`, `why_material` and `complete_text`.
- The debug drawer lists raw envelopes; `debug.note` lines appear there and nowhere else.

## 9. Versioning and extension

`contract_version` is semantic. Adding an optional field or an enum value is a minor version; renaming, removing or tightening is a major version. Consumers refuse a log whose major version they do not know. Put experiments in `ext` first; promote them when they stick.

## 10. Decisions taken here, and what was deferred

- One schema file, draft-07, `definitions` with `$ref`, `additionalProperties: false` plus `ext`: works with every tool the repo already has, and typos fail at validation time rather than at demo time.
- Spans store text and offsets, with text authoritative: offsets make the frontend fast, text makes the fixture survive re-extraction, and the validator proves they agree.
- Evidence links carry the relation, not the item: one filing can support one claim and contradict the framing of another.
- The four evaluators are overlapping stages: the fixture streams them that way because scores legitimately cite evidence another evaluator found, and the validator's reference-before-use rule caught exactly that when they were sequential.
- The confidence formula (§6) starts from the deciding dimension rather than averaging the four, because the verdict's likelihood *is* that dimension's score: averaging would let three confident readings of things that are not the problem drown the one that is. It subtracts rather than multiplies so each term is readable in the one-sentence `ext.confidence_basis` the panel can show.
- Deferred: re-scoring semantics for live runs, and the company view's cross-document objects (the rest of step 18) — a company page is several analyses side by side with a trend, which needs objects this contract does not yet have.
