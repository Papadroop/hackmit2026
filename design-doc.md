# Greenwashing Auditor — Design Doc

*Working title. Living document, updated after each design discussion.*
Last updated: 2026-09-19

## Context

- **Category:** Best Textual Analysis Hack. From a public corporate text (label, policy, claim), classify the likelihood that its statements are greenwashing.
- **Judged on:** (1) evidence quality, with sources cited; (2) creativity and sophistication of textual analysis; (3) conclusion confidence; (4) presentation.
- **Team:** 4 experienced engineers, 1.5 days. Build cost is not the binding constraint; choice quality is.

## Guiding principle

Three of the four criteria reward the analysis pipeline, not the interface. Every decision should move effort toward analysis depth and toward making evidence and confidence visible.

## Decisions

### D1. Form factor: web app

Thin frontend over a backend pipeline exposed as an API.

- **Why:** evidence and citations need screen space; inputs arrive as text, URLs and PDFs, which only a web app handles uniformly; reliable in a live demo.
- **Rejected:**
  - Browser extension: no room for evidence, web pages only, fragile live, and a second surface dilutes the demo.
  - Mobile label scanner: OCR failure point, and labels carry too little text to analyse.
  - Notebook/CLI: weak presentation.

### D2. Scope: one pipeline, three zoom levels

Not three products. One claim-level engine, viewed at three scales:

| Level | Input | Output |
|---|---|---|
| Claim | One statement | Verdict, confidence, evidence with sources |
| Document | Report, product page or policy (text, URL, PDF) | The same document annotated: each environmental claim highlighted, scored, and clickable to its evidence |
| Company | Derived from the documents analysed | Rollup of claim scores plus company-level evidence |

- **Entry point is always a corporate text,** as the brief requires. The company is identified from the text. A company-name search, if added, only fetches texts and runs the same flow.
- **The company view is a by-product, not an extra feature.** Verifying claims already requires gathering company-level evidence; the company view is that evidence store made visible.
- **Build order:** claim engine, then document view, then company rollup. Everything depends on the claim engine, so its depth takes priority over breadth of views.
- **Demo narrative:** open a document, click into one claim, zoom out to the company.

### D3. Working definition: the impression–reality gap

Greenwashing is the gap between the impression a reasonable reader takes from a text and what the evidence supports.

- Impression = what is claimed × how it is portrayed × what is left out.
- This mirrors the "net impression on a reasonable consumer" standard regulators apply to deceptive marketing, so the definition is defensible to judges.
- **Implication:** the analysis must capture the impression, not just the literal propositions. A literally true sentence can still greenwash.

### D4. Pre-evaluation analysis: three questions

Nothing is scored until these are answered for the text.

**Q1. What is claimed?** Decompose the text into atomic claims, each with:
- Source span (drives the highlighting in the document view)
- Subject and scope: product, packaging, operations, supply chain or whole company
- Attribute asserted (e.g. carbon neutral, recyclable)
- Quantity, baseline and timeframe, where stated
- Type: factual, commitment, comparative, vague attribute, or certification/label

**Q2. How is it portrayed?**
- Claim level: specificity, hedging ("aim to", "up to"), qualifiers present or absent, implied scope versus stated scope
- Document level: prominence (headline versus footnote), emotive or nature-evoking language, share of attention given to each topic

**Q3. What is omitted?** Impacts that are material for the company's industry but unaddressed in the text (the "hidden trade-off": an airline talking about recycled cups). Requires an external reference for what is material per industry.

Consequences:
- **Claim type routes evaluation.** Factual claims are verified; commitments are tested for credibility; comparatives need their baseline; certifications are checked for existence and coverage; vague attributes cannot be verified, and that unverifiability is itself the signal.
- **Portrayal is evidence, not pre-processing.** Some greenwashing is detectable from the text alone; the rest needs external evidence. Both feed the score.

### D5. Evaluation: independent signals, adversarial verdict, measured confidence

What the verdict looks like is defined in D6.

**Prebuilt knowledge** (curated, static, demo-safe). Not a claim-to-verdict lookup, which is brittle and looks like one. Two stores instead:
- *Substantiation criteria:* for each claim term, what must be true for it to be legitimate, drawn from regulator guidance.
- *Precedents:* past enforcement rulings on environmental claims, with claim text, reasoning and outcome (upheld or not). Used for case-based reasoning and as ground truth for calibration.

**Live retrieval** supplies company-specific evidence per claim, showing the system generalises beyond the curated stores.

**Four evaluators,** each an independent signal:

| Evaluator | Question | Evidence |
|---|---|---|
| Linguistic | Does the wording itself mislead? | Text only (D4 Q2). LLM plus small fine-tuned climate-text classifiers as a cross-check |
| Substantiation | Does the claim meet the criteria for its term? Has similar wording been ruled on? | Criteria and precedent stores |
| External verification | Do independent data agree? | Government and third-party data. Numbers recomputed; absolute versus intensity; proportionality (share of the footprint the claim covers) |
| Self-consistency | Does the company say the same elsewhere and over time? | Its own filings and risk disclosures; archived page versions (targets weakened, delayed or dropped) |

**Verdict layer:**
- *Adversarial:* a prosecutor agent and a defence agent argue each claim from the retrieved evidence; a judge decides. Counters a detector's built-in bias toward accusation.
- *Evidence weighting* by reliability and independence: regulator ruling > audited filing or government data > third-party dataset > news > company marketing. A company's own marketing cannot substantiate its own claim.
- *Confidence inputs:* agreement between evaluators, judge consistency across repeated runs, evidence tier.

**Rigour guarantees:**
- *Citation integrity:* every evidence item stores URL, quoted span and retrieval date. Quotes are checked programmatically against the source; unverified quotes are never displayed.
- *Calibration:* run the pipeline on the precedent set and report precision, recall and a calibration curve in the demo. Test cases are held out of the retrieval store (leave-one-out) to avoid leakage.

**Demo headliners:** self-consistency (the company contradicted by its own words), precedent matching, and the adversarial verdict with measured confidence.

### D6. Output: a profile, not a single score

A single score conflates different failures (vague, false, true-but-trivial) that have different remedies, and conflates severity with certainty. The headline likelihood stays, because the brief asks for one, but it is derived from a breakdown and always shown with it.

**Claim-level dimensions,** each with its own score and confidence:

| Dimension | Question | Fed by |
|---|---|---|
| Clarity | Is the claim specific and checkable, or vague and hedged? | Linguistic evaluator |
| Support | Does evidence contradict it, fail to back it, or support it? | Substantiation and external verification |
| Materiality | How much of the real environmental impact does it address? | External verification (proportionality) |
| Consistency | Does it match the company's other statements and its past ones? | Self-consistency evaluator |
| Completeness | Are material impacts addressed at all? (document level only) | D4 Q3 |

- **Combination is weakest-link, not average.** A claim that fails badly on any one dimension is greenwashing regardless of the others: a specific, consistent, material claim that is false should not score 75%.
- **Confidence is separate from likelihood,** per dimension and overall. "No evidence found" lowers confidence; it is not proof of greenwashing.

**Derived labels** (computed from the dimensions, not judged separately):
- *Verdict category:* Supported, Unsubstantiated, Misleading by framing, Contradicted.
- *Pattern tags* from an established taxonomy (the "seven sins of greenwashing": hidden trade-off, no proof, vagueness, irrelevance, lesser of two evils, fibbing, false labels), so the finding is named in terms people recognise.

**Constructive outputs:**
- *Credit where due:* well-substantiated claims are shown as such. A tool that only accuses is less credible.
- *Fix:* what evidence or rewording would make the claim legitimate, taken from the substantiation criteria.
- *Honest rewrite:* the claim as the evidence would allow it to be stated. Original versus rewrite makes the impression–reality gap concrete.

**Aggregation:**
- *Document:* claim results weighted by prominence, plus Completeness. Shown as a dimension profile, the distribution of verdict categories, and the top issues; never only a mean.
- *Company:* the same across documents, plus the trend over time.

### D7. Interface: the annotated document, analysed live

Extends the document view in D2. Judges can only reward analysis they can see, so the interface's job is to make the pipeline visible.

- **Layout:** document on the left with claims highlighted in place; detail panel on the right; summary header on top (headline likelihood and confidence, dimension profile, verdict distribution, top issues, each linking to its claim).
- **Highlight encoding:** colour for verdict category, intensity for confidence. A second channel (icon or underline style) so meaning never rests on colour alone.
- **Live progression:** results stream in as stages complete. Claims first appear in neutral, then language signals are marked, then evidence arrives and the colour settles. Shows the pipeline at work and turns latency into part of the demo.
- **Layers toggle:** Claims; Language (hedges, vague terms and scope mismatches marked at word level); Omissions.
- **Omissions** have no text to highlight, so they appear as margin cards ("Not mentioned: ...") with why the topic is material.
- **Claim panel:** dimensions with confidence, verdict and pattern tags, evidence cards (source, reliability tier, verified quote, link, supports or contradicts), prosecutor and defence arguments collapsed by default, fix and honest rewrite.
- **Honest version toggle:** the whole document with rewrites shown as a diff.
- **Replay:** any analysis can be saved and replayed with the same progression, so the demo does not depend on network or model latency.

## Open questions (design)

1. Primary audience (consumer, investor, regulator, or the company's own compliance team); shapes how the output is presented. **Resolved 2026-09-19:** the analyst who has to defend a finding (regulator, journalist, investor analyst); see `design-plan.md`.
2. Materiality reference for D4 Q3 (what counts as material per industry).
3. Demo narrative: which companies and documents. **Resolved 2026-09-19:** Shell (likely greenwashing), Apple (mixed), Ørsted (likely clean); see `demo-documents.md` for the selection and `golden-reference.md` for the hand analysis of the Shell page.

## Build plan

See `roadmap.md`: frontend first on a hand-made fixture, then one pipeline stage at a time, each step ending in a visual check.

- **D8. An analysis is an event stream.** Fixture, live run and replay share one format, so the interface is built before the pipeline and replay comes free. Envelope: `fixtures/README.md`; payloads, ordering and derivation rules: `contract/CONTRACT.md`; first fixture: `fixtures/shell-climate.jsonl`.

## Deferred (implementation)

- Concrete evidence sources for each store and evaluator; verify each is live and accessible.
- Models and tooling for each evaluator.
- Work split across the four team members.
