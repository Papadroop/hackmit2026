# Knowledge stores

The two curated stores the substantiation evaluator (roadmap step 13, design-doc D5) reads:

- `criteria.json`: substantiation criteria. For each claim term or claim type, what must be
  true for the claim to be legitimate, drawn from regulator guidance and law (CMA Green Claims
  Code, EU Directive 2024/825, FTC Green Guides, CAP Code and guidance, ACM, Competition
  Bureau Canada, UN HLEG, SBTi, GHG Protocol, ISO).
- `precedents.json`: past rulings on environmental claims (regulators, self-regulatory bodies,
  courts), each with the wording ruled on, the outcome and the reasoning.

Neither store maps a claim to a verdict. The evaluator matches each claim to the rules it is
measured against and the rulings on similar wording, shows them in the claim panel as evidence
with relation `criteria` or `precedent`, and scores Support from them. The precedent set is
also the ground truth for calibration (step 19).

And one the omissions stage (step 16, design-doc D4 Q3 and open question 2) reads:

- `materiality.json`: the materiality reference. One entry per industry, naming the disclosure
  topics that industry's documents are read against, taken from an external standard (the SASB
  Standard for the industry, GRI 11 for oil and gas, ESRS E1 for the cross-industry entry).
  It is the list "not mentioned" is measured against; without it an omission is only an
  opinion. `python -m auditor.materiality check` prints it, `match` shows which entry a
  document lands on.

## An entry

Every entry is a contract EvidenceItem (`contract/CONTRACT.md` §4) without `links`, plus an
`index` block that only the matcher reads:

```json
{
  "id": "cap-guidance-carbon-neutral-net-zero",
  "kind": "standard",                 "tier": 1,
  "source": {"name": "...", "publisher": "...", "date": "2023-02-10", "locator": "..."},
  "url": "https://...",               "text_url": "https://... (optional: where a script can read the text)",
  "quote": "verbatim words from the page",
  "verified": true,                   "verification": "fetched_exact",
  "retrieved": "2026-09-20",
  "note": "one or two sentences shown under the item in the panel",
  "index": { ... }
}
```

`index` for a criterion: `jurisdiction`, `terms` (claim words the rule governs), `applies_to`
(claim types, empty for any), `rule` (what must be true, one or two sentences). For a
precedent: `jurisdiction`, `body`, `company`, `industry`, `claim_text` (the wording ruled
on), `outcome` (`upheld`, `upheld_in_part`, `not_upheld`, `dismissed`, `settled`, `pending`),
`reasoning`, `terms`, `applies_to`, and `adjudicated_urls` (the texts ruled on, when they are
web pages; such a precedent is held out when that very page is analysed, the leakage rule in
`demo-documents.md` §6).

Rules the loader enforces, the same ones the contract validator applies to evidence:

- `verified: true` needs a `quote` and a verification method (`fetched_exact` when a script
  found the words on the page, `fetched_by_eye` when a person read them there,
  `second_party_fetch` when a separate fetch confirmed them). An unverified entry has
  `verification: unverified` and its quote is never displayed; it is listed by name and note.
- Tiers: 1 regulator ruling, court judgment or law; 2 assured filing or government data; 3
  independent standard or dataset; 4 news; 5 the company's own material.
- `retrieved` is an ISO date. Ids are stable slugs; the log carries short ids (`K1`, `P3`)
  with the slug in `ext.store_id`.

## Adding entries

1. Find the ruling or guidance page and read it. Copy the sentence that carries the finding or
   the rule, character for character.
2. Add the entry at the end of the file. Write the `rule` or `reasoning` in your own words:
   that text is what the matcher reads, so say which claim wording it bears on.
3. Check it: `cd backend && .venv/bin/python -m auditor.knowledge check --fetch`. The command
   validates both files, fetches every URL and reports whether each verified quote is on its
   page. A page that refuses scripts (HTTP 403, a timeout) is a warning, a dead link or a
   missing quote is a failure.
4. Run the tests: `.venv/bin/python -m pytest tests/test_knowledge.py tests/test_substantiate.py`.

## Adding an industry to `materiality.json`

An entry has the same evidence fields, and an `index` of `industry`, `sasb_code` (`*` for the
cross-industry entry), `also_codes` (neighbouring codes it answers for), `aliases` and
`keywords` (how a document is placed in it), and `topics`. A topic is `code`, `name`,
`why_material`, `expects` (what a document that addressed it would say) and `terms`.

`terms` is the part to get right: the words a page uses when it really does address the topic,
not every word related to it. They are what turns "not mentioned" into something a reader can
check, and a term that is too broad quietly disarms the check. Write them, then run

    .venv/bin/python -m auditor.materiality check
    .venv/bin/python -m auditor.materiality coverage ../demo-documents/<a document>.md

The second prints, topic by topic, which terms are in that document and which are not, with no
model involved. A topic that shows as mentioned everywhere has terms that are too broad; one
that shows as absent on a page that plainly discusses it is missing a term. Then run
`.venv/bin/python -m pytest tests/test_omissions.py`.

Where the industry's own standard is behind a download form (the SASB Standards) the entry is
listed by name and its topics are attributed in `note`, as the ISO entries in `criteria.json`
are; where a free standard names the same impacts (GRI 11 for oil and gas, ESRS E1
cross-industry) the entry carries a quote a script found on the page.

Company-authored material (annual reports, strategy PDFs, FAQ pages) is evidence for the
other evaluators, never a precedent, and cannot substantiate the same company's claim (D5).

## Provenance

Curated 2026-09-20 from pages fetched that day. `demo-documents.md` §7 records the earlier
verification of the Shell, TotalEnergies and Apple rulings. The ISO standards are behind a
purchase wall, so their entries are unverified and summarise the requirements from the
standards' public abstracts; the Ryanair 2020 ruling is no longer on asa.org.uk and is listed
from the Sabin Center's copy without a quote.
