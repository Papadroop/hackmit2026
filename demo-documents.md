# Demo documents — selection

*Phase 0, step 1 of `roadmap.md`: choose 2–3 demo documents (one likely greenwashing, one likely clean, one mixed). This file records the criteria, the candidate pool, the scores, the picks, and what was verified. D-numbers refer to `design-doc.md`.*

Last updated: 2026-09-19

## Picks

| Role | Company, document | URL | Fixture | Backup |
|---|---|---|---|---|
| Likely greenwashing (primary) | Shell, "Climate" | https://www.shell.com/sustainability/climate.html | `demo-documents/shell-climate-2026-09-19.md` | TotalEnergies, "Energy transition" (https://totalenergies.com/energy-transition) |
| Mixed | Apple, "Apple unveils its first carbon neutral products" (press release, 12 Sep 2023) | https://www.apple.com/newsroom/2023/09/apple-unveils-its-first-carbon-neutral-products/ | `demo-documents/apple-carbon-neutral-2023-09-12.md` | Oatly, "Climate footprint product label" (https://www.oatly.com/oatly-who/sustainability-plan/climate-footprint-product-label) |
| Likely clean | Ørsted, "Towards net zero" (decarbonisation) | https://orsted.com/en/about-us/sustainability/decarbonisation | `demo-documents/orsted-decarbonisation-2026-09-19.md` | Interface Inc., "Carbon negative" (https://www.interface.com/US/en-US/sustainability/carbon-negative.html) |

The Shell page is hand-analysed in `golden-reference.md`. Design open question 3 (demo narrative: which companies and documents) is closed by this file.

## 1. What a demo document has to do

Derived from the brief and the design doc, before any candidate was looked at.

1. **Be a public corporate text** of one of the brief's kinds: label, policy or claim. Written by the company, not about it (D2: the entry point is always a corporate text).
2. **Carry enough claims to fill the document view**: at least eight atomic claims and at least three of the five claim types in D4 Q1, so extraction, routing by type and the Language layer all have something to show.
3. **Have ground truth a judge can check** (judging criterion 3, conclusion confidence). For the greenwashing and mixed roles: an adjudication by a regulator, court or self-regulatory body on the same claim family. For the clean role: independent validation of the claims and no adverse finding.
4. **Leave an evidence trail for all four evaluators** (D5): public data to recompute the numbers and their proportionality; filings or assured reports for self-consistency; archived versions or a documented target history; an industry with a materiality reference (SASB) for omissions.
5. **Be fetchable and stable**: live today, 400–2,500 words, retrievable by the ingestion step (step 10) without heroics, and archived so replay does not depend on the page surviving.
6. **Carry the demo narrative** (D2, D7): a name the judges recognise and a story that survives "open a document, click a claim, zoom out to the company".
7. **As a set, be diverse**: different industries (so Omissions is not one lookup), different text types, different jurisdictions of precedent, all five claim types somewhere.

## 2. Rubric

| | Criterion | Weight | 0 | 3 |
|---|---|---|---|---|
| R1 | Claim density and variety (req. 2) | 3 | fewer than 5 claims or one type | ≥ 8 claims, ≥ 3 types, quantified and vague claims both present |
| R2 | Ground truth (req. 3) | 3 | none, or only pending litigation | upheld ruling on this claim family (or, for clean: validated targets, assured data, no adverse finding) |
| R3 | Evidence trail (req. 4) | 3 | company material only | public data, assured filing, documented target history, SASB industry |
| R4 | Fit and stability (req. 1, 5) | 2 | page dead or unreachable | live, right length, plain fetch, archived |
| R5 | Demo value (req. 6) | 2 | unknown name, no story | household name, story writes itself |

Maximum 42. Scores are judgments made after the verification in §7; where the verification failed the score reflects that, not the candidate's reputation.

## 3. Candidate pool and scores

### Role A — likely greenwashing

| Candidate, document | R1 | R2 | R3 | R4 | R5 | Total | Notes |
|---|---|---|---|---|---|---|---|
| **Shell — "Climate" page** | 3 | 3 | 3 | 2 | 3 | **37** | 25 claims, all five types. ASA upheld (7 Jun 2023, omission of the fossil share); three Dutch RCC rulings on offset claims (2021, 2022, 2023); Paris court ruling on TotalEnergies is a same-family precedent. 20-F filer; annual report with EY limited assurance; 2024 strategy documents the 2030 target cut (20% → 15–20%) and the retired 2035 target; the page's own cautionary note says the plan "cannot reflect" the 2050 target. JS-rendered site, but the AEM `.model.json` gives clean text. Wayback monthly at this URL from 2025-03; earlier at the previous URL. |
| TotalEnergies — "Energy transition" (~3,200 words) or "Climate and sustainable energy" (~700) | 3 | 3 | 2 | 2 | 2 | 32 | Only court judgment directly on "carbon neutrality by 2050" wording (23 Oct 2025, not appealed), but the adjudicated paragraphs were removed from the French site, so the live text is a sibling. 20-F filer. No documented target rollback; no Wayback before mid-2025. Same industry as Shell, so it is the backup rather than a second pick. |
| Ryanair — "Sustainability" and "Pathway to net zero" | 2 | 2 | 3 | 2 | 2 | 29 | Best external-verification story in the pool (EU ETS aircraft-operator data allow absolute vs intensity to be recomputed) and a documented shift of target metric (g/pax-km 2018–2019 → per-RTK on a 2023 base, 2024). Only ruling is ASA 5 Feb 2020 on ads. Pages are short and already hedged. Keep as the airline alternative. |
| BP — "Net zero" page | 2 | 1 | 3 | 1 | 3 | 26 | Two documented rollbacks (Feb 2023, Feb 2025) but no ruling on the merits (the 2019 OECD complaint ended when BP withdrew the ads). bp.com returns 403 to fetch tools; no Wayback snapshots for the page. |
| KLM — "Sustainability" | 2 | 3 | 2 | 0 | 2 | 25 | The strongest single precedent in the pool (Amsterdam District Court, 20 Mar 2024, 15 of 19 statements misleading, no appeal) but the live page could not be fetched from here, is JS-rendered, and the adjudicated statements were already withdrawn. Not an SEC filer. |

### Role B — mixed

| Candidate, document | R1 | R2 | R3 | R4 | R5 | Total | Notes |
|---|---|---|---|---|---|---|---|
| **Apple — "Apple unveils its first carbon neutral products" (12 Sep 2023)** | 3 | 3 | 3 | 1 | 3 | **35** | Product-label announcement: the "carbon neutral" Apple Watch claim was ruled misleading by the Frankfurt Regional Court on 26 Aug 2025 (Az. 3-06 O 8/24, Deutsche Umwelthilfe v Apple; offsets from the Paraguay eucalyptus project secured only to 2029). Not final: appeal to the OLG possible and no appellate decision published as of 3 Sep 2026; a parallel US consumer claim was dismissed (N.D. Cal., 20 Feb 2026, secondary source). Apple's Sept 2025 and Sept 2026 Watch releases make no product-level carbon-neutral claim. Alongside: emissions −45% since 2015 in the release (over 60% by 2025, Apex-assured), SBTi-validated 61.7% cut by FY2030, Fraunhofer-checked product LCAs. 10-K filer. Long (4093 words with footnotes). Static page, archived. |
| Oatly — "Climate footprint product label" page | 3 | 2 | 2 | 1 | 2 | 27 | ASA upheld four claims on 26 Jan 2022 (G21-1096286), including "73% less CO2e vs. milk"; the live page now carries the narrower "44% to 76% lower climate impact than comparable cow's milk", a retraction in practice. CarbonCloud-verified product labels; 20-F filer; GHG assurer unverified; poor Wayback coverage; ~2,500–4,000-word pages with 404s. Backup. |
| Coca-Cola — "Packaging" and "Emissions" pages | 2 | 1 | 3 | 2 | 3 | 28 | Strong evidence trail (10-K, EY review-level assurance, the 2 Dec 2024 goal replacement that dropped the 25% reusable-packaging target, Break Free From Plastic brand audits) but no adjudication: the D.C. Court of Appeals only reversed a dismissal (29 Aug 2024) and the case's later status is unverified. |
| Microsoft — "Carbon negative by 2030" (2020) | 3 | 0 | 3 | 1 | 3 | 26 | Total emissions up 23.4% (2025 report) and 25% year-on-year (2026 report) against the 2020 baseline; SBTi net-zero commitment removed; Deloitte limited assurance. No adjudication and no retraction, so it fails the role's core criterion. 4,500–5,000 words. |
| JBS — "Net Zero by 2040" | 2 | 3 | 1 | 0 | 1 | 20 | Richest adjudication trail (NAD/NARB 2023; NY Attorney General assurance of discontinuance, 3 Nov 2025, $1.1m; goal dropped in the July 2026 report) but the adjudicated pages are gone (archive only), the assurer is unnamed and SBTi removed the commitment. Reads as "mostly bad", not mixed. |

### Role C — likely clean

| Candidate, document | R1 | R2 | R3 | R4 | R5 | Total | Notes |
|---|---|---|---|---|---|---|---|
| **Ørsted — "Towards net zero" (decarbonisation)** | 2 | 3 | 3 | 2 | 2 | **32** | ~700 words, ~10 claims (factual, certification/validation, commitment, superlatives). SBTi-validated net-zero 2040 (first energy company); CDP A seven years; WBA #1; Annual Report 2025 with PwC limited assurance confirms 4 g CO2e/kWh (target ≤ 10 g), 99% renewable share. No adverse ruling; one open complaint to the Danish Consumer Ombudsman on biomass marketing (Mar 2023, no decision found). Honest flags for the tool to find: biomass zero-rating underpins the intensity figure; Scope 3 rose 19% in 2025; superlatives. orsted.com blocks plain curl but the fetch tool works. |
| Interface Inc. — "Carbon negative" | 2 | 2 | 2 | 2 | 1 | 24 | SBTi-validated 2030 targets; third-party-verified EPDs; ended offset-based "Carbon Neutral Floors" on 30 Apr 2024 (own release). "Carbon negative" tile rests on biogenic-carbon convention; "more than halfway there" unquantified. 10-K filer, no ESG assurance. Little name recognition. Backup. |
| Beyond Meat — "Mission" | 1 | 1 | 1 | 2 | 2 | 17 | Live page is unquantified; the 90% / 97% figures live in press releases and shift across LCA versions (2018 → 2023 → 2025); all LCAs commissioned by the company; no ESG assurance; 10-K delayed in 2026. No adverse environmental ruling. |
| Patagonia — "Our footprint", "Climate goals" | 2 | 0 | 1 | 0 | 3 | 15 | Site serving a holding page today; French JDP upheld a complaint against a Patagonia email (1 Jul 2022); footprint rose 2% in FY2025; private company. The premise that a 2024 California greenwashing class action exists could not be verified. |
| Allbirds — "Sustainability" | 1 | 2 | 0 | 0 | 2 | 13 | Dwyer v. Allbirds (S.D.N.Y., 18 Apr 2022) dismissed in Allbirds' favour, which is a rare "adjudicated clean" asset, but the sustainability pages now 404, the brand was sold in March 2026, the company reports going-concern doubt, and the 2025 halving target uses a counterfactual baseline and was never reported. |

## 4. The picks

### A. Shell — "Climate" (likely greenwashing, primary)

Why this one: it is the only candidate that scores full marks on claims, ground truth and evidence trail at once, and it carries the three demo headliners from D5 in a single page.

- **Self-consistency**: the page's own cautionary note, and the FY2025 annual report (p. 367), say Shell's business plans "cannot reflect our 2050 net-zero emissions target". The 2024 strategy admits the 2030 intensity target was lowered and the 2035 target retired.
- **Precedent matching**: the ASA's 2023 ruling on Shell's ads (omitting the fossil share of the business) and the Paris court's 2025 ruling on TotalEnergies' "carbon neutrality by 2050" messaging are the same claim family as this page's hero sentence. The ASA's 2025 ruling that *cleared* a Shell ad which stated the 68% / 23% investment split on screen is the precedent for the tool's "Fix" output.
- **Adversarial verdict with measured confidence**: the page is numerate and literally accurate almost everywhere, so a naive detector finds little; the greenwashing is in scope, ratios and omission. That is the case a prosecutor–defence–judge structure is built for, and where the tool's distinction between "Contradicted" and "Misleading by framing" earns its keep.
- **Credit where due**: operational emissions −36% with EY limited assurance, methane intensity, routine flaring ended. The tool should show these green.

Expected result (from `golden-reference.md`): headline likelihood 0.8, confidence 0.85; 10 Supported, 7 Unsubstantiated, 7 Misleading by framing, 1 Contradicted; four omissions (absolute footprint, capital allocation, volume plans, target history).

Risks and mitigations: the site is JavaScript-rendered, so step 10 must fetch the `.model.json` (documented in the fixture header) or use the Wayback copy; the fixture is already saved. The page has no Wayback history at this URL before March 2025, so step 15's archived-version diff should use the previous URL (`/sustainability/our-climate-target.html`, snapshots from 2024-03-01) and the 2024 strategy PDF.

### B. Apple — "Apple unveils its first carbon neutral products" (mixed)

Why this one: it is a label in the brief's sense (the announcement of a "carbon neutral" product mark), and it puts well-substantiated claims and an adjudicated one in the same text.

- **Supported, with assurance**: "Apple has so far reduced total emissions by over 45 percent since 2015" (Apex-assured reporting; over 60% by 2025); corporate operations on renewable electricity since 2018; supplier clean energy (15 GW then, 17.8 GW in 2025); SBTi-validated target of 61.7% by FY2030; product LCAs checked by the Fraunhofer Institute. These should render green.
- **Adjudicated**: "carbon neutral Apple Watch" rests on a 75% cut plus carbon credits. The Frankfurt Regional Court found the claim misleading (26 Aug 2025) because the offset project's leases secure the carbon only to 2029; the court rejected the separate complaint about the "Carbon Neutral" logo. The judgment is not final, and a US court dismissed a parallel consumer claim in Feb 2026, so the verdict is jurisdiction-dependent. That is exactly the situation in which the tool should show a **confidence** lower than its likelihood.
- **Self-consistency**: Apple's Watch releases of 9 Sep 2025 and 9 Sep 2026 carry no product-level carbon-neutral claim; only the company-wide 2030 goal remains. The claim was withdrawn, not defended.
- **Criteria**: EU Directive 2024/825 blacklists offset-based product neutrality claims from 27 Sep 2026. The substantiation criteria store can show the claim failing a rule that did not exist when it was made.
- **Portrayal**: the release has numbered footnotes defining the baseline for the "over 75 percent" reduction, the shipping condition and the mass-balance basis for cobalt. Prominence versus footnote is measurable here.

Expected result: headline likelihood about 0.55 with confidence about 0.7; a majority of Supported claims; the "carbon neutral" family Misleading by framing (or Contradicted in the German jurisdiction); Unsubstantiated for "clean energy", "high-quality carbon credits" and "industry-leading"; omissions on the share of the product footprint covered by credits (about a quarter), absolute units sold, and device lifetime and repairability (SASB Hardware: product lifecycle management).

Risks: the release is long (4093 words as first counted; 2,318 once step 10's ingester dropped the page's hidden duplicate of the article text), around the 2,500-word guideline; the document view has to scroll, which real documents demand anyway. The April 2025 release "Apple surpasses 60 percent reduction" (about 2,900 words) is the shorter substitute if the interface struggles; it still contains the carbon-neutral Watch and Mac mini claims.

### C. Ørsted — "Towards net zero" (likely clean)

Why this one: it is the only candidate whose headline numbers are third-party validated (SBTi), assured (PwC, limited), consistent with its 2025 annual report, and free of any adverse ruling. It also sits in the same broad sector as Shell, so the demo can show the tool separating two "energy companies with net-zero targets" on evidence rather than on vocabulary.

Expected result, written down now so the "likely clean" label is honest and checkable later:

- **Supported**: "98 % reduction in scope 1 and 2 emissions intensity by the end of 2025" (annual report: 4 g CO2e/kWh in 2025 vs 16 g in 2024, target ≤ 10 g); "renewable energy share of 99 %" (annual report); "2040 net-zero target … validated by the Science Based Targets initiative" (SBTi validation 2021, strengthened pathway approved Jan 2025); "'A' CDP climate score for seven consecutive years" (check on cdp.net in step 14).
- **Flags the tool should raise, and that a fair reviewer would agree with**: (1) the headline is an *intensity* figure while absolute Scope 3 rose 19% in 2025 (Tyra gas offtake, sale of stored coal) and the page gives no Scope 3 number; (2) biomass is 97% of Ørsted's renewable-source energy consumption and its biogenic CO2 is reported outside Scopes 1–3, so the 4 g figure depends on a zero-rating convention that is the subject of an open complaint to the Danish Consumer Ombudsman; (3) "world's first energy company", "#1 leader", "undisputed leader" are certification-type superlatives to check against the WBA and SBTi sources; (4) "share of capital expenditures classified as sustainable stands at 99 %" is an EU-taxonomy label claim. Expected: one or two "Misleading by framing" at most, one omission card (biomass accounting), headline likelihood about 0.25 with confidence about 0.75.
- **Self-consistency check to run in step 15**: Ørsted's 2020 framing was "carbon neutral by 2025"; the 2025 framing is "98 % intensity reduction" and "≤ 10 g". If the ≤ 10 g metric was the original definition, this is a reframing, not a weakening; the tool should say which.

Risks: orsted.com returns 403 to plain curl (the fetch tool works); the fixture was captured through the fetch tool and must be re-extracted from rendered HTML in step 10 before spans are anchored. Wayback coverage of the sustainability section is sparse (closest snapshot to 2024 and 2025 is 2023-03-25).

## 5. Set-level checks

| Check | Shell | Apple | Ørsted |
|---|---|---|---|
| Industry (SASB) | Oil & Gas – E&P / Refining & Marketing | Technology Hardware | Electric Utilities & Power Generators |
| Text type (brief) | Policy page | Label (product-claim press release) | Corporate sustainability page |
| Precedent jurisdictions | UK ASA, Dutch RCC, French court (TotalEnergies) | German court, US court (dismissed), EU law | Danish Consumer Ombudsman (open complaint) |
| Claim types present | all five | all five (incl. certification: the "carbon neutral" mark) | factual, commitment, certification (SBTi, CDP, WBA), vague superlatives |
| Expected headline | ~0.8 (conf. 0.85) | ~0.55 (conf. 0.7) | ~0.25 (conf. 0.75) |
| Headliner (D5) | self-consistency: contradicted by its own filing | precedent + measured confidence: courts disagree | credit where due, with honest flags |

The three expected headlines spread across the scale, so the demo shows a scale rather than one colour. All three companies publish assured GHG data and file or publish annual reports, so the self-consistency evaluator has a filing to read in every case.

**Demo order** (D2): Shell first and deepest; Apple second for the label, the court split and the EU deadline; Ørsted third as the contrast; then the company view for whichever company the judges ask about.

**Timeliness hook.** EU Directive 2024/825 applies from 27 September 2026, days after the hackathon: it bans generic environmental claims without recognised excellent performance and bans product claims of neutral, reduced or positive climate impact based on offsetting. "Cleaner", "low-carbon" and offset-based "carbon neutral" all appear in the demo set. The tool's criteria store (step 13) should carry the directive's list.

## 6. Leakage and hold-out rules

- A ruling that adjudicates the **exact text** under analysis is held out of the precedent store when that text is analysed. None of the three primary documents is itself an adjudicated text: the Shell and TotalEnergies rulings concern ads and the French consumer site, not the pages picked here. Rulings on the same company's *other* texts stay in the store; that is what a human analyst would find, and precedent matching on a sibling text is the generalisation the demo should show.
- The demo documents are excluded from the calibration set (step 19). Calibration uses leave-one-out over the precedent set only.
- Company-authored material (annual reports, strategy PDFs, FAQ pages) is evidence, never precedent, and cannot substantiate the same company's claim (D5). It can contradict it.

## 7. Verification log (2026-09-19)

Everything below was fetched today unless marked. "Fetch tool" is the web-fetch tool; "curl" is a plain HTTP client with a browser user agent.

| Item | Status | Note |
|---|---|---|
| shell.com/sustainability/climate.html | live | JS shell; content in `climate.model.json` (35 KB). 840 words of claims + 1,320-word cautionary note. |
| shell.com/sustainability/climate/our-climate-target-faqs.html | live | `.model.json` works. |
| shell.com/what-we-do/powering-progress.html | 404 | |
| shell.com …/shell-energy-transition-strategy-2024.pdf | live | 33 pp; target change on p. 26. |
| Shell Annual Report and Accounts 2025 (PDF, 462 pp; also SEC 6-K and 20-F FY2025) | live | Quotes and page numbers in `golden-reference.md` §4. |
| ASA G22-1170842 (7 Jun 2023), G24-1248246 (9 Apr 2025), A25-1288971 (1 Oct 2025) | live | Upheld; not upheld; not upheld. |
| RCC 2021/00190, CvB 2022/00100, RCC 2023/00091 | live | All upheld against Shell (verification run). |
| Paris court communiqué, 23 Oct 2025, RG 22/02955 | live (PDF) | Text extracted and quoted in `golden-reference.md`. TotalEnergies statement of 24 Oct 2025: no appeal. |
| Wayback, shell.com/sustainability/climate.html | 19 monthly snapshots 2025-03-28 → 2026-09-04 | CDX API; `archive.org/wayback/available` rate-limited (429) during the run. |
| Wayback, shell.com/sustainability/our-climate-target.html | 13 snapshots 2024-03-01 → 2025-03-02 | Earliest at this URL is 2024-03-01, two weeks before the strategy change. |
| totalenergies.com/energy-transition ; /sustainability/climate-and-sustainable-energy | live | /company/energy-transition and /sustainability/climate are 404. |
| bp.com/en/global/corporate/sustainability/net-zero.html | live via curl only | 403 to the fetch tool; no Wayback snapshots. |
| corporate.ryanair.com/sustainability/ ; /pathway-to-net-zero/ | live | /environment/ is 404. |
| klm.com/information/sustainability | unreachable | Timed out (fetch tool and curl); Wayback copy is JS-rendered. |
| orsted.com/en/about-us/sustainability/decarbonisation ; /en/sustainability | live via fetch tool | curl gets 403. /en/sustainability/our-approach and /climate-action-plan soft-redirect to /en/sustainability. |
| Ørsted Annual Report 2025 (PDF, 218 pp, 6 Feb 2026) | live | 4 g CO2e/kWh; 99% renewable share; Scope 3 +19%; PwC limited assurance (pp. 214–215). |
| interface.com …/carbon-negative.html ; /sustainability-overview.html ; /epds | live | /climate-take-back is 404. Wayback 2024-01-26 and 2025-01-22. |
| beyondmeat.com/en-US/mission | live | /sustainability and /impact are 404. |
| patagonia.com/our-footprint/ , /climate-goals/ | holding page | HTTP 200 but "temporarily unavailable"; Wayback copies exist (2024-01-05, 2025-01-04). |
| allbirds.com/pages/sustainability | redirects to materials page | /carbon-footprint and /flight-plan are 404; brand sold 29 Mar 2026 (8-K). |
| apple.com/newsroom/2023/09/apple-unveils-its-first-carbon-neutral-products/ | live | Static HTML; 4093 words after removing duplicated footnote and contact blocks. Wayback 2024-01-06, 2024-12-26. |
| Frankfurt Regional Court press release (ordentliche-gerichtsbarkeit.hessen.de/presse/co2-neutrales-produkt) ; DUH release | live | Ruling 26 Aug 2025, Az. 3-06 O 8/24; not final (tww.law, 3 Sep 2026: no OLG decision published). |
| apple.com Watch Series 11 (9 Sep 2025) and Series 12 (9 Sep 2026) releases | live | No product-level "carbon neutral" claim; only the Apple 2030 goal. |
| Apple Environmental Progress Report 2026 (PDF) ; 10-K FY2025 | live | Apex assurance statement; Fraunhofer LCA checks; SBTi 61.7% by FY2030. |
| oatly.com …/climate-footprint-product-label ; ASA G21-1096286 | live | /oatly-who/sustainability and /en-us/climate-footprint are 404. |
| coca-colacompany.com/about-us/environment/packaging , /emissions | live | Both candidate URLs from the brief's first guess are 404; 2 Dec 2024 goal-revision release live. |
| blogs.microsoft.com 2020 carbon-negative post ; 2025 and 2026 ESR posts | live | |
| jbs.com.br/en/sustainability/net-zero/ and jbsfoodsgroup.com/our-purpose/net-zero | 404 | Archived copy 2025-01-19; NY AG assurance of discontinuance PDF live. |

## 8. Fixture files

- `demo-documents/shell-climate-2026-09-19.md` — verbatim text, with a front-matter header recording URL, retrieval method, archive status and word counts. Spans in `golden-reference.md` are substrings of this file.
- `demo-documents/orsted-decarbonisation-2026-09-19.md` — same format; re-extracted from the rendered HTML by the step 10 ingester on 2026-09-19 and diffed against the fetch-tool copy: the same text with the page's curly quotes restored, plus the link cards' section heading and link sentences. 720 words.
- `demo-documents/apple-carbon-neutral-2023-09-12.md` — same format; re-extracted from the static HTML by the step 10 ingester on 2026-09-19. 2,318 words: the earlier 4,093 count included the page's hidden copy-text duplicate of the article, which the ingester drops.
- `fixtures/shell-climate.analysis.json` and `fixtures/shell-climate.jsonl` — the Shell hand analysis as contract data and as the replayable event log (step 2); see `contract/CONTRACT.md`.
