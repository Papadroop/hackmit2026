# Golden reference — Shell, "Climate" page

*Phase 0, step 1 of `roadmap.md`. Hand analysis of the primary demo document, written in the structure of D4–D6 of `design-doc.md`. The team reviews this file and either agrees with each verdict or edits it; once agreed it is the reference that step 11 (extraction) and step 17 (verdicts) are checked against, and the source for the fixture event log in step 2.*

Last updated: 2026-09-19

| | |
|---|---|
| Document | "Climate", shell.com/sustainability/climate.html |
| Text | `demo-documents/shell-climate-2026-09-19.md` (verbatim; spans below are quoted from it) |
| Company, industry | Shell plc; Oil & Gas – integrated (SASB EM-EP + EM-RM) |
| Text type | Corporate policy page (the brief's "policy") |
| Length | 840 words of claims, plus a 1,320-word cautionary note on the same page |
| Retrieved | 2026-09-19, from the page's AEM content model (`climate.model.json`) |
| Archive | Wayback snapshots monthly 2025-03-28 → 2026-09-04 at this URL; 2024-03-01 → 2025-03-02 at the previous URL `/sustainability/our-climate-target.html` |
| Role | Likely greenwashing (primary demo document) |

## 0. Conventions used in this file

**Scores.** Every dimension gets a *problem score* `s ∈ [0,1]` (0 = no greenwashing signal on that dimension, 1 = maximal) and a *confidence* `c ∈ [0,1]`. A claim's **likelihood** is the weakest link, `max(s)` over its applicable dimensions (D6). Its **confidence** is the confidence of the dimension that set the maximum, lowered when other well-evidenced dimensions disagree. Step 17 will formalise this; the numbers here are judgments, written down so the team can argue with them.

**Dimensions** (D6): Clarity (Linguistic evaluator), Support (Substantiation + External verification), Materiality (proportionality), Consistency (Self-consistency evaluator). Completeness is document-level only (§6).

**Verdict category**, derived from the dimensions, in this order:
1. **Contradicted** — an evidence item contradicts the literal content of the claim, or the company's own statements do (Support or Consistency ≥ 0.7 with `c` ≥ 0.6).
2. **Unsubstantiated** — the claim is too vague to verify (Clarity ≥ 0.7), or no evidence could be found either way (Support ≈ 0.5, low `c`).
3. **Misleading by framing** — the literal content is supported, but Clarity or Materiality (or a weakening of the target over time) is the weakest link at ≥ 0.5.
4. **Supported** — everything else, with `c` ≥ 0.6.

**Pattern tags** from the "seven sins" (hidden trade-off, no proof, vagueness, irrelevance, lesser of two evils, fibbing, false labels). One extra tag from Planet Tracker's taxonomy is used where the seven sins have no word for it: **greenrinsing** = changing a target before it is met.

**Evidence tiers** (D5): T1 regulator ruling / court judgment / law; T2 audited or assured filing, government or intergovernmental data; T3 independent third-party dataset or standard; T4 news; T5 company's own material. Company material can *contradict* the company (admission against interest) but cannot *substantiate* its own claim.

**Verified** column: "yes" means the quote was fetched from the URL on 2026-09-19 and matched programmatically or by eye in this session; "no" means it must be verified before it is displayed (D5 citation integrity).

## 1. The document, with paragraph markers

Markers `[P#]` are reading aids only; they are not in the fixture text. Headings are shown as in the page.

**[P1] Climate (hero)**
Our target is to become a net-zero emissions energy business by 2050. As we implement our strategy to deliver more value with less emissions, we are reducing emissions from our operations, and helping our customers transition to cleaner energy solutions. Find out more about how we are working to achieve this target and our progress so far.

**[P2] Climate (intro)**
We have a target to become a net-zero emissions energy business by 2050. As we work to deliver more value, we must also navigate the multi-decade energy transition. We are progressing with improving the energy efficiency of our operations and using more renewable electricity to power our activities. We are also helping to build the energy system of the future, with low-carbon energy products and solutions. Find out more about how we are working to achieve this target and our progress so far.

**Our targets and ambition**

**[P3]** We have set intensity targets and absolute targets and an ambition over the short, medium and long term to track our performance over time. We have a target to become a net-zero emissions energy business by 2050. We believe this target supports the more ambitious goal of the Paris Agreement, to limit the rise in the global average temperature this century to 1.5°C above pre-industrial levels.

**[P4]** Our net-zero target includes emissions from our operations, as well as from the end-use of all the energy products we sell. The metrics we use to track progress against our energy transition targets and ambition include:
- Halving Scope 1 and 2 emissions under our operational control by 2030, on a net basis, compared with 2016. Scope 1 emissions come directly from our operations, and Scope 2 from the energy we buy to run our operations.
- Maintaining methane emissions intensity for operated oil and gas assets below 0.2% and achieve near-zero methane emissions intensity by 2030.
- Reducing the net carbon intensity (NCI) of the products we sell by 15-20% by 2030. NCI measures emissions associated with each unit of energy we sell[A]. It reflects changes in sales of oil and gas products, and changes in sales of low-carbon products - such as biofuels and renewable electricity. Reducing the NCI of the products we sell requires action by both Shell and our customers, with the support of governments and policymakers to create the right conditions for change.
- Reducing customer emissions from the use of our oil products by 15-20% by 2030, Scope 3 Category 11 (2021 baseline).

**[P5]** We have set short-, medium- and long-term targets to reduce the net carbon intensity of the energy products we sell, compared with 2016:

**[P6]** (timeline graphic)
- 2-3% by 2021 - achieved
- 3-4% by 2022 - achieved
- 6-8% by 2023 - achieved
- 9-12% by 2024 - achieved
- 9-13% by 2025 - achieved
- 15-20% by 2030
- 100% by 2050

**Our progress**

**[P7] 2025 performance:**
- Scope 1 and 2 emissions were down by 36% by the end of 2025 compared with the 2016 baseline year. We have achieved around 70% of our target to halve our Scope 1 and 2 operational emissions by 2030, compared with 2016.
- Methane emissions intensity maintained well below our 0.2% target, at 0.04% for Shell-operated oil and gas assets with marketed gas and 0.002% for Shell-operated oil and gas assets without marketed gas.
- Net carbon intensity (NCI) decreased by 9.0% compared with the 2016 reference year and was within the 2025 target range.
- We eliminated routine flaring from our upstream operations with effect from January 2025.
- Customer emissions from the use of our oil products (Scope 3, Category 11) reduced by 18% by the end of 2025 compared with 2021.

**[P8] Shell Energy Transition Strategy 2024** (promo card)
See how we are providing energy today while helping to build the energy system of the future

**Our approach**

**[P9]** To decarbonise our operations, we are:
- using more renewable electricity to power our operations;
- developing CCS for some of our facilities;
- improving the energy efficiency of our operations; and
- making portfolio changes such as acquisitions and investments in low carbon intensity projects, decommissioning facilities, divesting assets while sustaining our liquids production.
If required, we may choose to use high-quality carbon credits to offset any remaining emissions from our operations, in line with the carbon mitigation hierarchy of avoid, reduce, and compensate or to meet local regulatory requirements.

**[P10]** To support our customers to decarbonise, we are:
- growing our power sales, including those of renewable power;
- increasing the proportion of gas and LNG in our hydrocarbon sales while reducing the proportion of sales of oil products;
- increasing sales of low-carbon fuels, such as biofuels, and developing hydrogen;
- developing abatement projects, including deploying more CCS; and
- using carbon credits to offset remaining carbon emissions.

**[P11] Footnotes**
[A] Shell's net carbon intensity is the average intensity, weighted by sales volume, of the energy products sold by Shell. It is tracked, measured and reported using our Net Carbon Footprint (NCF) methodology (PDF, 2 MB).

**[P12] Cautionary note** (1,320 words; three passages matter, quoted verbatim; the rest is forward-looking-statement boilerplate)
- "Shell only controls its own emissions. The use of the terms Shell's "net carbon intensity" or NCI is for convenience only and not intended to suggest these emissions are those of Shell plc or its subsidiaries."
- "However, Shell's operating plan and outlook cannot reflect our 2050 net-zero emissions target, as this target is outside our planning period."
- "However, if society is not net zero in 2050, as of today, there would be significant risk that Shell may not meet this target."

The cautionary note is a disclosure, not a set of claims. It is treated as **evidence** (E1, self-consistency) and as a **document-level portrayal signal** (L19, prominence), not as claims to score.

## 2. Q1 — What is claimed

Atomic claims, in document order. "Span" is verbatim and unique in the fixture text, so it can be anchored by string match in step 2.

| ID | Span | Where | Subject, scope | Attribute | Quantity / baseline / timeframe | Type |
|---|---|---|---|---|---|---|
| C1 | "Our target is to become a net-zero emissions energy business by 2050" | P1 (repeated P2, P3) | Whole company incl. use of sold products (per C8) | Net zero | — / — / 2050 | Commitment |
| C2 | "we are reducing emissions from our operations" | P1 | Operations (Scope 1+2) | Emissions falling | none stated | Factual |
| C3 | "helping our customers transition to cleaner energy solutions" | P1 | Customers / products | "cleaner" | none | Vague attribute |
| C4 | "deliver more value with less emissions" | P1 | Whole company | "less emissions" | no baseline | Vague attribute (comparative without baseline) |
| C5 | "We are progressing with improving the energy efficiency of our operations and using more renewable electricity to power our activities" | P2 | Operations | Efficiency; renewable power use | none | Factual (unquantified) |
| C6 | "helping to build the energy system of the future, with low-carbon energy products and solutions" | P2 | Products | "low-carbon" | none | Vague attribute |
| C7 | "We believe this target supports the more ambitious goal of the Paris Agreement, to limit the rise in the global average temperature this century to 1.5°C" | P3 | The 2050 target | Paris / 1.5°C alignment | — | Comparative (against an external benchmark), hedged |
| C8 | "Our net-zero target includes emissions from our operations, as well as from the end-use of all the energy products we sell" | P4 | Target scope | Scope 1, 2 and 3 covered | — | Factual (scope statement) |
| C9 | "Halving Scope 1 and 2 emissions under our operational control by 2030, on a net basis, compared with 2016" | P4 | Operations, operational control | −50% | 50% / 2016 / 2030; "net basis" | Commitment |
| C10 | "Maintaining methane emissions intensity for operated oil and gas assets below 0.2% and achieve near-zero methane emissions intensity by 2030" | P4 | Operated O&G assets | Methane intensity | <0.2%; near-zero / — / 2030 | Commitment |
| C11 | "Reducing the net carbon intensity (NCI) of the products we sell by 15-20% by 2030" | P4, P6 | Products sold (well-to-wheel, net of credits) | Intensity reduction | 15–20% / 2016 / 2030 | Commitment |
| C12 | "Reducing customer emissions from the use of our oil products by 15-20% by 2030, Scope 3 Category 11 (2021 baseline)" | P4 | Oil products only (gas, LNG excluded) | Absolute Scope 3 reduction | 15–20% / 2021 / 2030 | Commitment (called an "ambition" elsewhere, see L22) |
| C13 | "2-3% by 2021 - achieved" … "9-13% by 2025 - achieved" (five items) | P6 | NCI | Targets met | as listed / 2016 / 2021–2025 | Factual |
| C14 | "Scope 1 and 2 emissions were down by 36% by the end of 2025 compared with the 2016 baseline year" | P7 | Operations | −36% | 36% / 2016 / 2025 | Factual |
| C15 | "We have achieved around 70% of our target to halve our Scope 1 and 2 operational emissions by 2030" | P7 | Operations | Progress share | ~70% | Factual (derived) |
| C16 | "Methane emissions intensity maintained well below our 0.2% target, at 0.04% for Shell-operated oil and gas assets with marketed gas and 0.002% for Shell-operated oil and gas assets without marketed gas" | P7 | Operated O&G assets | Methane intensity | 0.04%, 0.002% / — / 2025 | Factual |
| C17 | "Net carbon intensity (NCI) decreased by 9.0% compared with the 2016 reference year and was within the 2025 target range" | P7 | Products sold | NCI −9.0%; target met | 9.0% / 2016 / 2025 | Factual |
| C18 | "We eliminated routine flaring from our upstream operations with effect from January 2025" | P7 | Upstream operations (operated assets, see L23) | Zero routine flaring | — / — / Jan 2025 | Factual |
| C19 | "Customer emissions from the use of our oil products (Scope 3, Category 11) reduced by 18% by the end of 2025 compared with 2021" | P7 | Oil products only | −18% | 18% / 2021 / 2025 | Factual |
| C20 | "making portfolio changes such as acquisitions and investments in low carbon intensity projects, decommissioning facilities, divesting assets while sustaining our liquids production" | P9 | Operations | Decarbonisation lever | — | Factual (action) |
| C21 | "we may choose to use high-quality carbon credits to offset any remaining emissions from our operations" | P9 | Operations | Offsetting with "high-quality" credits | — | Commitment (hedged); "high-quality" vague |
| C22 | "growing our power sales, including those of renewable power" | P10 | Power sales | Growth | none | Factual (unquantified) |
| C23 | "increasing the proportion of gas and LNG in our hydrocarbon sales while reducing the proportion of sales of oil products" | P10 (under "To support our customers to decarbonise") | Hydrocarbon sales mix | Presented as customer decarbonisation | proportion, no absolute | Factual, framed |
| C24 | "increasing sales of low-carbon fuels, such as biofuels, and developing hydrogen" | P10 | Low-carbon fuels | Growth | none | Factual (unquantified) |
| C25 | "using carbon credits to offset remaining carbon emissions" | P10 | Customer emissions / NCI | Offsetting | none | Factual (practice) |

Not scored as claims: P8 (promo card; its wording is covered by L5), P11 (definition), P12 (disclosure; used as evidence).

## 3. Q2 — How it is portrayed

### Claim-level language signals (word-level spans for the Language layer)

| ID | Span | Where | Kind | Note | Claims |
|---|---|---|---|---|---|
| L1 | "net-zero emissions energy business" | P1, P2, P3 | Term of art, undefined on page | Defined only on the FAQ page (E13). "Business" rather than "emissions" makes it an identity statement. | C1 |
| L2 | "cleaner" | P1 | Comparative without baseline | Cleaner than what? CMA principle 2 and its warning on general terms (E11). | C3 |
| L3 | "more value with less emissions" | P1 | Slogan; comparative without baseline | Pairs a financial and an environmental promise as if they moved together. | C4 |
| L4 | "helping" / "helping to build" | P1, P2, P8 | Agency hedge | Shell's own contribution is unspecified. | C3, C6 |
| L5 | "energy system of the future" | P2, P8 | Future-evoking, unfalsifiable | No content that could be checked. | C6 |
| L6 | "low-carbon energy products and solutions" | P2 | Vague attribute | "Low-carbon" undefined; on this page LNG is listed under customer decarbonisation (P10). | C6 |
| L7 | "We believe" | P3 | Hedge | Converts an alignment claim into an opinion. | C7 |
| L8 | "supports the more ambitious goal" | P3 | Weak verb | "Supports" rather than "is aligned with"; no third-party validation named. | C7 |
| L9 | "on a net basis" | P4 | Qualifier present but technical | Permits carbon credits; a lay reader will not parse it. Credit for stating it. | C9 |
| L10 | "requires action by both Shell and our customers, with the support of governments and policymakers" | P4 | Responsibility diffusion | Conditions the target on others. | C11 |
| L11 | "achieved" ×5 | P6 | Prominence / portrayal | Five ticks for short-horizon targets of 2–13%; the 2030 entry gives no hint that it was lowered from 20% in 2024, or that a 2035 target of 45% was removed (E7). | C11, C13 |
| L12 | "well below" | P7 | Intensifier | Accurate (0.04% vs 0.2%). Included so the Language layer shows that not every intensifier is flagged. | C16 |
| L13 | "around 70%" | P7 | Approximation | Arithmetic checks: 36/50 = 72%. | C15 |
| L14 | "To support our customers to decarbonise" | P10 heading | Framing / category | A heading about decarbonisation introduces a bullet about selling more gas. | C23 |
| L15 | "proportion" ×2 | P10 | Ratio language | Hides absolute volumes; LNG sales are planned to grow 4–5% a year (E3). | C23 |
| L16 | "high-quality" | P9 | Vague qualifier | No standard or registry named. | C21 |
| L17 | "If required, we may choose" | P9 | Double hedge | | C21 |
| L18 | "including those of renewable power" | P10 | Qualifier that reveals scope | Admits that power sales growth is not all renewable, under a decarbonisation heading. | C22 |
| L21 | "while sustaining our liquids production" | P9 | Buried admission | Oil output will not fall; placed inside a list of decarbonisation actions. | C20 |
| L22 | "targets and ambition" / fourth bullet presented as a target | P3, P4 | Hedge gradient, inconsistent across pages | The FAQ (E13) and the 2024 strategy (E7) call the oil-products reduction an "ambition"; this page lists it among target metrics without the label. | C12 |
| L23 | "upstream operations" | P7 | Implied scope wider than stated scope | Shell's own flaring page says "Upstream-operated assets" (E15): non-operated ventures are excluded. | C18 |

### Document-level signals

| ID | Signal | Observation |
|---|---|---|
| L19 | Prominence asymmetry | 840 words of claims above; the sentence that undercuts the headline ("cannot reflect our 2050 net-zero emissions target") is in a 1,320-word legal note at the bottom. |
| L20 | Share of attention | 0 words on the absolute size of Shell's footprint, on LNG growth plans, or on capital allocation; most of the text is about targets and intensity metrics. Feeds §6. |
| L24 | Register | Plain, numerate, corporate; little emotive or nature-evoking language. The greenwashing here is structural (scope, ratio, omission), not lyrical. Worth saying in the demo: the tool should not depend on spotting "green" adjectives. |

## 4. Evidence

| ID | Source | Tier | URL | Verified quote (or fact) | Verified | Bears on |
|---|---|---|---|---|---|---|
| E1 | Shell Annual Report and Accounts 2025, p. 367 (also Form 20-F / 6-K, FY2025) | T2 | https://www.sec.gov/Archives/edgar/data/1306965/000162828026017027/shellannualreportandacco.htm | "Shell's Operating Plan, outlook and business plans cover a 10-year forecast period and are updated every year. The business plan reflects our Scope 1, Scope 2 and NCI targets over the next 10 years. However, Shell's business plans cannot reflect our 2050 net-zero emissions target, as this target is currently outside our planning period." | yes | C1 (contradicts credibility) |
| E1b | Same, p. 459; also P12 of the page | T2 | as E1 | "However, if society is not net zero in 2050, as of today, there would be significant risk that Shell may not meet this target." | yes | C1 (conditionality) |
| E2 | Same, p. 24, cash capital expenditure by segment, 2025 ($ million) | T2 | as E1 | Integrated Gas 4,689; Upstream 9,316; Marketing 1,862; Chemicals and Products 3,063; Renewables and Energy Solutions 1,866; Corporate 119; Total 20,915 | yes | C1, C6, O2 |
| E3 | Same, p. 87; and Capital Markets Day release, 25 Mar 2025 | T2 / T5 | as E1; https://www.globenewswire.com/news-release/2025/03/25/3048433/0/en/Shell-accelerates-strategy-to-deliver-more-value-with-less-emissions.html | "We plan to grow LNG sales by 4-5% (CAGR) a year through to 2030." / "sustaining our 1.4 million barrels per day of liquids production to 2030 with increasingly lower carbon intensity." | yes | C1, C20, C23, O3 |
| E4 | Same, p. 93, "Drivers of absolute Scope 3 emissions change in 2025" | T2 | as E1 | "Scope 3 emissions associated with our energy product sales were 1,065 million tonnes CO2e, compared with 1,084 million tonnes CO2e in 2024. Higher emissions from the use of the liquefied natural gas (LNG) we sell were more than offset by lower emissions from the use of our oil products sold and lower emissions associated with our purchases of non-renewable power from third parties." | yes | C23 (contradicts framing), C4, O1 |
| E4b | Same, p. 93 and p. 15 | T2 | as E1 | "In 2025, Scope 3, Category 11 emissions from the use of our oil products were 467 million tonnes CO2e, a reduction of 4.9% compared with 2024. This reduction was driven by lower sales in our Products business following completion of the sale of the Shell Energy and Chemicals Park Singapore in April 2025 and by lower Mobility sales." / p. 15: 467 (2024: 491; 2021: 569) | yes | C12, C19 |
| E5 | Same, p. 7, headline KPIs | T2 | as E1 | "53 million tonnes — Scope 1 and 2 emissions CO2e (2024: 58)" / "71 gCO2e/MJ — Net carbon intensity (NCI) (2024: 71)" | yes | C2, C14, C17 |
| E6 | Same, p. 101, assurance | T2 | as E1 | "Ernst & Young LLP ('EY') was engaged by Shell plc … to perform a limited assurance engagement in accordance with … ISAE 3000 (Revised) … and … ISAE 3410 to report on the accompanying greenhouse gas (GHG) statement" | yes | C14, C16, C17, C19 (limited, not reasonable, assurance) |
| E7 | Shell Energy Transition Strategy 2024, p. 26 and p. 7 | T5 (admission against interest) | https://www.shell.com/sustainability/reporting-centre/_jcr_content/root/main/section_1888019429/promo_copy_1767682700/links/item0.stream/1726832326846/2c3f9065f2886e789ac196789f137dbca49473e8/shell-energy-transition-strategy-2024.pdf | p. 26: "Given this focus on value, we expect growth in total power sales to 2030 will be lower than previously planned. This has led to an update to our net carbon intensity target. We are now targeting a 15-20% reduction by 2030 in the net carbon intensity of the energy products we sell, compared with 2016, against our previous target of a 20% reduction. Acknowledging uncertainty in the pace of change in the energy transition, we have also chosen to retire our 2035 target of a 45% reduction in net carbon intensity." / p. 7: "We believe our total absolute emissions peaked in 2018 at 1.73 gigatonnes of carbon dioxide equivalent (GtCO2e)." | yes | C11, C13, C22, O4 |
| E8 | UK Advertising Standards Authority, ruling G22-1170842, Shell UK Ltd, 7 June 2023 | T1 | https://www.asa.org.uk/rulings/shell-uk-ltd-g22-1170842-shell-uk-ltd.html | Upheld (omission issue): "large-scale oil and gas investment and extraction comprised the vast majority of the company's business model in 2022" … "the ads omitted material information and were likely to mislead". Action: "ensure that their future ads featuring environmental claims did not mislead by exaggerating or omitting material information about the proportion of their business activities comprised of lower carbon activities." | yes | C1, C3, C6, O2 (precedent: omission of the fossil share) |
| E8b | ASA, ruling G24-1248246, Shell UK Ltd, 9 April 2025 | T1 | https://www.asa.org.uk/rulings/shell-uk-ltd-g24-1248246-shell-uk-ltd.html | Not upheld. The ad carried on-screen: "In 2023, 68% of Shell's global investments included oil & gas, 23% included low-carbon energy solutions and 9% non-energy products." ASA: "The ad had therefore not given a misleading overall impression of Shell's environmental impact". | yes | C1, O2 (precedent for the *fix*: disclosing the investment split made a comparable ad acceptable) |
| E8c | Dutch Reclame Code Commissie 2021/00190 (26 Aug 2021, "Rij CO2-neutraal", upheld); College van Beroep 2022/00100 (20 Oct 2022, upheld on appeal); RCC 2023/00091 (9 Oct 2023, Shell Energy "CO2-gecompenseerd gas", upheld) | T1 | https://www.reclamecode.nl/uitspraken/resultaten/vervoer-2021-00190/304997/ ; https://www.reclamecode.nl/uitspraak/?uitspraakId=365319 ; https://www.reclamecode.nl/uitspraken/uitspraak/vervoer-2023-00091/427115/ | Shell's offset-based "CO2-neutral" / "CO2-compensated" consumer claims found misleading three times; CvB: "Shell heeft zelf gekozen voor een claim met een absoluut karakter en dit impliceert dat zij nader bewijs dient te (kunnen) leveren" (Shell chose a claim of an absolute character and must therefore be able to prove it). | yes (verification run, 2026-09-19) | C21, C25 (precedent: offsetting claims) |
| E9 | Tribunal judiciaire de Paris, 34e chambre, judgment of 23 Oct 2025, RG n° 22/02955, Greenpeace France, Les Amis de la Terre, Notre Affaire à Tous v TotalEnergies; court communiqué | T1 | https://www.tribunal-de-paris.justice.fr/sites/default/files/2025-10/Communiqu%C3%A9%20Greenpeace%20Amis%20de%20la%20Terre%20et%20Notre%20Affaire%20%C3%A0%20Tous%20c.%20Totalenergies%2023102025.pdf | Misleading commercial practices found for consumer-facing statements referring to "leur ambition d'atteindre la neutralité carbone d'ici 2050 et d'être un acteur majeur dans la transition énergétique". Reasoning: "en ayant recours à cette terminologie, sans préciser aux consommateurs que le groupe avait son propre scénario pour atteindre la neutralité carbone, et qu'il continuait à augmenter sa production et ses investissements dans le pétrole et le gaz, à rebours des préconisations des experts scientifiques fondées sur l'Accord de Paris, le groupe avait fait état d'allégations environnementales de nature à induire en erreur le consommateur." Remedies: cease diffusion, damages, publication. Claims on fossil gas and agrofuels rejected as outside the action. TotalEnergies said on 24 Oct 2025 it would not appeal. | yes | C1, C7 (precedent: same claim family, different company; the court's reasoning maps onto O2/O3) |
| E10 | Transition Pathway Initiative, company assessment of Shell (retrieved 2026-09-19) | T3 | https://www.transitionpathwayinitiative.org/companies/shell | Management Quality: Level 5 "Transition Planning and Implementation". Carbon Performance: 2028 "Not Aligned"; 2035 "National Pledges"; 2050 "1.5 Degrees". | yes (assessment date not shown on page) | C1, C7 |
| E11 | UK CMA, Green Claims Code (20 Sep 2021) | T1 (criteria) | https://www.gov.uk/government/publications/green-claims-code-making-environmental-claims/environmental-claims-on-goods-and-services | Principles: "claims must be truthful and accurate"; "claims must be clear and unambiguous"; "claims must not omit or hide important information"; comparisons "fair and meaningful"; "consider the full life cycle"; "substantiated". Warns that "green", "sustainable", "eco-friendly" "especially if used without explanation" imply an overall benefit the business must be able to prove. | yes | C3, C4, C6, O1–O3 (criteria) |
| E12 | EU Directive 2024/825 (Empowering Consumers for the Green Transition), applies from 27 Sep 2026 | T1 (law) | https://eur-lex.europa.eu/eli/dir/2024/825/oj/eng | Bans generic environmental claims ("green", "climate friendly", …) without recognised excellent performance, and bans claims that a product has neutral, reduced or positive climate impact based on offsetting. Applies to B2C product claims; corporate targets are outside its direct scope. | date yes; recital text no | C3, C6, C21, C25 (criteria and timeliness) |
| E13 | Shell, "Our climate target – FAQs" | T5 | https://www.shell.com/sustainability/climate/our-climate-target-faqs.html | "The Scope 3 emissions we report account for over 90% of the total emissions we report." / "a target of 9-12% reduction by 2024 which we met, achieving a 9% reduction compared with 2016 and a target of 9-13% reduction by 2025 which we also met, reporting a continued 9% reduction compared with 2016." / "In March 2024, we also set an ambition to reduce customer emissions from the use of our oil products by 15-20% by 2030 compared with 2021 (Scope 3, Category 11)." | yes | C1, C12, C13, C17 |
| E14 | Shell, "Reducing methane emissions" | T5 | https://www.shell.com/what-we-do/oil-and-natural-gas/methane-emissions.html | "Total methane emissions from assets under Shell operational control were reduced by 78% between 2016 (138,000 tonnes) and 2025 (31,000 tonnes)." / "In January 2025, we eliminated routine gas flaring from our Upstream operated assets – five years ahead of the World Bank's Zero Routine Flaring by 2030 initiative, of which we are a signatory." | yes | C10, C16, C18 |
| E15 | Shell, "Flaring: Zero routine flaring by 2025" | T5 | https://www.shell.com/what-we-do/oil-and-natural-gas/flaring.html | "Shell reached our target of eliminating routine gas flaring from our Upstream-operated assets in 2025, moving faster than the World Bank's Zero Routine Flaring by 2030 initiative, to which we are a signatory." | yes | C18 (scope: operated assets) |
| E16 | SASB Standard, Oil & Gas – Exploration & Production (materiality reference) | T3 | https://sasb.ifrs.org/standards/ | Disclosure topics include Greenhouse Gas Emissions; Air Quality; Water Management; Biodiversity Impacts; Reserves Valuation & Capital Expenditures; Management of the Legal & Regulatory Environment; Business Ethics & Payments Transparency; Community Relations; Security, Human Rights & Rights of Indigenous Peoples; Health, Safety & Emergency Management; Critical Incident Risk Management. | topic list yes (from SASB brief) | §6 |
| E17 | OGMP 2.0 member list (29 Dec 2025) | T3 | https://www.ogmpartnership.org/sites/default/files/documents/2025-12/List_of_OGMP2.0_Member_Companies_29.12.pdf | Shell (Netherlands) listed as a member. Membership only; Gold Standard status not established in this session. | yes | C10, C16 (weak) |
| E18 | Shell Annual Report 2025, p. 22 | T2 | as E1 | "Oil and gas production available for sale in 2025 was 2,800 thousand boe/d, compared with 2,836 thousand boe/d in 2024. This decrease was mainly driven by divestments and field decline, partly offset by new production." | yes | C2, C14, C20 (divestment as driver) |
| E19 | Shell Annual Report 2025, strategy section | T2 | as E1 | "we have a target to cut the net carbon intensity (NCI) of the products we sell by 15--20% by 2030 compared with 2016. And, we are on track, delivering 9% by end-2025 compared with 2016." | yes | C11, C17 ("on track" vs pace, see §5) |

**Recomputed numbers** (External verification, D5):

| Check | Computation | Result |
|---|---|---|
| Share of footprint covered by the only absolute target (Scope 1+2) | 53 / (53 + 1,065) | 4.7% |
| Capex share, Renewables & Energy Solutions, 2025 | 1,866 / 20,915 | 8.9% |
| Capex share, Upstream + Integrated Gas, 2025 | (9,316 + 4,689) / 20,915 | 67.0% |
| "around 70%" of the 2030 Scope 1+2 target | 36 / 50 | 72% ✓ |
| Oil-products Scope 3 reduction vs 2021 | (569 − 467) / 569 | 17.9% ✓ (page says 18%) |
| Absolute Scope 3 change 2024 → 2025 | (1,084 − 1,065) / 1,084 | −1.8% |
| NCI pace achieved 2016 → 2025 | 9 points / 9 years | 1.0 pt/yr; 2024 → 2025: 0 (71 → 71 gCO2e/MJ) |
| NCI pace needed 2025 → 2030 for 15–20% | (15 − 9) … (20 − 9) over 5 years | 1.2 – 2.2 pt/yr |

## 5. Verdicts

### 5.1 All claims

Scores are (problem score / confidence). "—" means the dimension does not apply.

| Claim | Clarity | Support | Materiality | Consistency | Likelihood | Conf. | Verdict | Tags | Key evidence |
|---|---|---|---|---|---|---|---|---|---|
| C1 net zero by 2050 | 0.4/0.8 | 0.7/0.8 | 0.3/0.8 | 0.85/0.9 | **0.85** | 0.85 | **Contradicted** | hidden trade-off, no proof | E1, E1b, E2, E3, E7, E10, E8, E9 |
| C2 reducing operational emissions | 0.2/0.9 | 0.15/0.8 | 0.5/0.9 | 0.2/0.7 | 0.5 | 0.8 | Supported (materiality caveat) | — | E5, E6, E18 |
| C3 cleaner energy solutions | 0.85/0.9 | 0.5/0.4 | 0.6/0.7 | 0.3/0.5 | 0.85 | 0.9 | Unsubstantiated | vagueness | E11, E12, E8 |
| C4 more value with less emissions | 0.75/0.9 | 0.4/0.6 | 0.5/0.6 | 0.3/0.5 | 0.75 | 0.85 | Unsubstantiated | vagueness | E4, E11 |
| C5 efficiency, renewable electricity | 0.5/0.8 | 0.45/0.4 | 0.5/0.8 | 0.2/0.5 | 0.5 | 0.5 | Unsubstantiated | no proof | — |
| C6 energy system of the future, low-carbon products | 0.85/0.9 | 0.5/0.5 | 0.7/0.8 | 0.3/0.5 | 0.85 | 0.85 | Unsubstantiated | vagueness, hidden trade-off | E2, E8 |
| C7 supports Paris 1.5°C | 0.5/0.8 | 0.6/0.7 | 0.4/0.7 | 0.4/0.6 | 0.6 | 0.7 | Misleading by framing | hidden trade-off | E10, E3 |
| C8 target covers operations and use of sold products | 0.1/0.9 | 0.1/0.9 | 0.1/0.9 | 0.1/0.9 | 0.1 | 0.9 | Supported | — | E13, E1 |
| C9 halve Scope 1+2 by 2030 (net) | 0.35/0.8 | 0.3/0.7 | 0.5/0.9 | 0.2/0.8 | 0.5 | 0.7 | Supported (materiality caveat) | — | E5, E18 |
| C10 methane intensity target | 0.2/0.8 | 0.2/0.6 | 0.3/0.7 | 0.1/0.7 | 0.3 | 0.6 | Supported | — | E14, E17 |
| C11 NCI −15–20% by 2030 | 0.55/0.9 | 0.5/0.7 | 0.6/0.8 | 0.8/0.95 | 0.8 | 0.9 | Misleading by framing | greenrinsing, hidden trade-off | E7, E19, E5, E4 |
| C12 oil-product Scope 3 −15–20% by 2030 | 0.45/0.8 | 0.3/0.7 | 0.55/0.8 | 0.5/0.8 | 0.55 | 0.75 | Misleading by framing | hidden trade-off | E4, E4b, E13 |
| C13 five NCI targets "achieved" | 0.5/0.9 | 0.2/0.8 | 0.5/0.8 | 0.7/0.9 | 0.7 | 0.85 | Misleading by framing | greenrinsing | E7, E13, E5 |
| C14 Scope 1+2 −36% vs 2016 | 0.15/0.9 | 0.15/0.8 | 0.5/0.9 | 0.3/0.7 | 0.5 | 0.8 | Supported (materiality caveat) | — | E5, E6, E18 |
| C15 ~70% of 2030 target achieved | 0.15/0.9 | 0.1/0.9 | 0.5/0.9 | 0.1/0.9 | 0.5 | 0.9 | Supported | — | recomputation |
| C16 methane 0.04% / 0.002% | 0.2/0.8 | 0.25/0.6 | 0.3/0.7 | 0.1/0.8 | 0.3 | 0.6 | Supported | — | E14, E6, E17 |
| C17 NCI −9.0%, within 2025 range | 0.4/0.9 | 0.15/0.9 | 0.5/0.8 | 0.6/0.9 | 0.6 | 0.85 | Misleading by framing | greenrinsing | E5, E13, E19 |
| C18 routine flaring eliminated | 0.35/0.8 | 0.25/0.6 | 0.3/0.7 | 0.2/0.8 | 0.35 | 0.65 | Supported | — | E14, E15 |
| C19 oil-product Scope 3 −18% vs 2021 | 0.3/0.8 | 0.15/0.9 | 0.55/0.8 | 0.3/0.8 | 0.55 | 0.8 | Supported (driver caveat) | — | E4b |
| C20 portfolio changes, divesting assets | 0.5/0.8 | 0.3/0.7 | 0.65/0.85 | 0.4/0.7 | 0.65 | 0.8 | Misleading by framing | hidden trade-off | E18, E3, E4b |
| C21 high-quality carbon credits | 0.7/0.8 | 0.5/0.3 | 0.4/0.6 | 0.2/0.5 | 0.7 | 0.7 | Unsubstantiated | vagueness | E12 |
| C22 growing power sales, incl. renewable | 0.55/0.8 | 0.45/0.5 | 0.4/0.6 | 0.5/0.7 | 0.55 | 0.6 | Unsubstantiated | no proof | E7 |
| C23 more gas and LNG, framed as decarbonisation | 0.6/0.9 | 0.75/0.9 | 0.8/0.9 | 0.3/0.7 | 0.8 | 0.9 | Misleading by framing | hidden trade-off, lesser of two evils | E4, E3 |
| C24 low-carbon fuels, hydrogen | 0.55/0.8 | 0.5/0.3 | 0.5/0.6 | 0.3/0.4 | 0.55 | 0.5 | Unsubstantiated | no proof | — |
| C25 credits to offset remaining emissions | 0.4/0.8 | 0.2/0.7 | 0.4/0.6 | 0.1/0.8 | 0.4 | 0.6 | Supported (as a description of practice) | — | E13 |

Distribution: Supported 10, Unsubstantiated 7, Misleading by framing 7, Contradicted 1.

Note on C23: its weakest link is Materiality (0.8), and E4 contradicts the *framing* (LNG emissions rose) rather than the literal statement (proportions did shift), so by the rules in §0 it is Misleading by framing, not Contradicted. The team should decide whether that distinction is worth keeping; it is what makes the tool credible to a defence lawyer.

### 5.2 Featured claim: C1 — "Our target is to become a net-zero emissions energy business by 2050"

**Dimensions.**
- *Clarity 0.4.* The term is defined off-page (E13) but the scope is stated on-page (C8). Fine as a target statement.
- *Support 0.7.* The target exists. Its credibility as a commitment does not survive Shell's own plan: capex to Renewables & Energy Solutions was 8.9% of the 2025 total and Upstream plus Integrated Gas 67% (E2); LNG sales are planned to grow 4–5% a year and oil output to be held at 1.4 million b/d to 2030 (E3); the 2035 interim target was retired (E7); TPI rates 2028 performance "Not Aligned" (E10). Precedents: ASA 2023 on Shell's own ads (E8), and the Paris court on TotalEnergies' near-identical "carbon neutrality by 2050 / major player in the transition" messaging (E9), whose reasoning (no disclosure that production and investment in oil and gas keep growing) applies to this page word for word.
- *Materiality 0.3.* Credit: the target covers Scope 3, which is over 90% of the footprint (E13). This is the right scope.
- *Consistency 0.85.* The same page's cautionary note, and the annual report, say the business plan "cannot reflect" the target (E1) and that if society is not net zero, Shell likely will not be (E1b). The headline says "our target"; the footnote says the plan does not contain it.

**Prosecutor.** The hero sentence gives a reasonable reader the impression that Shell is on a path to net zero. Shell's own filing says its plans do not contain that path; the only interim milestone beyond 2030 was withdrawn in 2024; nine dollars in ten of capital go to oil, gas and products; and gas volumes are planned to grow through 2030. A regulator has already found Shell's transition advertising misleading for omitting the fossil share of its business, and a court has found the same claim family misleading at TotalEnergies.

**Defence.** A 2050 target necessarily sits beyond any 10-year plan; the plan does reflect the 2030 targets, and Scope 1+2 is 36% down with limited assurance. TPI gives Shell the top management-quality level and rates the 2050 target itself 1.5°C-aligned. The cautionary language is standard securities disclosure, and the conditionality on society reaching net zero is honest about a Scope 3 target the company cannot deliver alone.

**Judge.** The literal statement is true: the target exists. The impression is not supported: a "net-zero emissions energy business" is presented as a destination the company is travelling toward, while the company's own filing says its plans do not reflect it and its capital and volume plans point the other way. The defence's strongest point, that 2050 is outside any plan, would carry more weight if the 2035 milestone had not been retired. **Contradicted (credibility), likelihood 0.85, confidence 0.85.** The confidence is high because the decisive evidence is the company's own words in an assured filing.

**Fix.** Publish the pathway: a 2035 milestone for absolute Scope 3, the capex share needed to reach it, and how LNG growth to 2030 is reconciled with it; or state plainly that the plan does not yet contain the target. Precedent for the fix: the ASA accepted a 2025 Shell ad because it stated on screen that 68% of investments included oil and gas and 23% low-carbon (E8b).

**Honest rewrite.** "Shell has a target to reach net-zero emissions by 2050, including emissions from the use of the products we sell. Our business plans, which run ten years, do not yet reflect this target. In 2025 our total reported emissions were about 1.1 billion tonnes CO2e, 95% of them from customers using our products. To 2030 we plan to grow LNG sales by 4–5% a year and hold oil production at 1.4 million barrels a day; 9% of our 2025 capital spending went to renewables and energy solutions."

### 5.3 Featured claim: C23 — "increasing the proportion of gas and LNG in our hydrocarbon sales while reducing the proportion of sales of oil products", under "To support our customers to decarbonise"

- *Clarity 0.6.* Two proportions, no absolute numbers (L15); the heading supplies the environmental meaning (L14).
- *Support 0.75.* Shell's annual report says emissions from the LNG it sells went **up** in 2025 (E4); LNG sales are planned to grow 4–5% a year to 2030 (E3). The proportion claim is literally true; the decarbonisation framing is contradicted by Shell's own numbers.
- *Materiality 0.8.* Scope 3 is >90% of the footprint; the sales mix is the single most material lever the page mentions, and it is presented as a ratio.
- *Consistency 0.3.* Consistent with Shell's strategy documents, which are candid about LNG growth.

**Verdict: Misleading by framing, 0.8 / 0.9.** Tags: hidden trade-off (absolute LNG emissions rise), lesser of two evils (gas-versus-coal argument implied by the heading, not made on the page).

**Fix.** Give absolute emissions by product line and state the LNG growth plan alongside the proportion.

**Honest rewrite.** "We are selling more gas and LNG and less oil. In 2025 emissions from the LNG we sell rose; our total Scope 3 emissions fell 1.8% because oil-product sales fell, largely after we sold our Singapore refinery and chemicals park."

### 5.4 Featured cluster: C11, C13, C17 — the NCI timeline

- The timeline shows seven entries, five ticked "achieved" (L11). Shell's own 2024 strategy says the 2030 target was lowered from 20% to 15–20% and the 2035 target of 45% was retired (E7). The page does not say so; the timeline reads as unbroken delivery.
- "9-13% by 2025 - achieved" and "9-12% by 2024 - achieved" both rest on a 9% figure: NCI was 71 gCO2e/MJ in both 2024 and 2025 (E5), and the FAQ describes 2025 as "a continued 9% reduction" (E13). 2025 sits at the bottom edge of its range, with zero year-on-year progress.
- Pace: 9 points in nine years; 6–11 more points needed in five (§4 recomputation). The annual report nonetheless says "we are on track" (E19).
- NCI is an intensity net of carbon credits (P11, E13); it can fall while absolute emissions rise, and Shell's cautionary note says NCI is "not intended to suggest these emissions are those of Shell" (P12).

**Verdicts.** C11 Misleading by framing 0.8/0.9 (greenrinsing, hidden trade-off). C13 Misleading by framing 0.7/0.85 (greenrinsing). C17 Misleading by framing 0.6/0.85 (greenrinsing). All three literal statements are true, which is why Support scores are low and framing carries the verdict.

**Fix.** Show the target history on the timeline; report the absolute Scope 3 figure next to NCI; drop "achieved" for a year with no progress, or say "unchanged".

**Honest rewrite (for P5–P6).** "We aim to cut the net carbon intensity of the energy we sell by 15–20% by 2030 against 2016. In March 2024 we lowered this target from 20% and withdrew our 2035 target of 45%. Net carbon intensity was 9% below 2016 at the end of both 2024 and 2025."

### 5.5 Featured claim: C14 — "Scope 1 and 2 emissions were down by 36% by the end of 2025 compared with the 2016 baseline year" (credit where due)

- Matches the annual report (53 Mt vs 58 Mt in 2024, 36% below 2016; E5), which carries EY limited assurance (E6). Arithmetic for C15 checks (72%).
- Caveats that keep it from a perfect score: Materiality 0.5 because operations are 4.7% of the reported footprint; part of the fall comes from divestments (E18), which move emissions to another owner rather than removing them; assurance is limited, not reasonable.

**Verdict: Supported, likelihood 0.5 (materiality), confidence 0.8.** In the interface this should render as green with a visible materiality note, so a viewer sees that the tool credits real reductions and still says how much of the footprint they touch.

## 6. Q3 — What is omitted

Materiality reference: SASB Oil & Gas – E&P topics (E16), CMA principle 3 "must not omit or hide important information" (E11). Each omission is a margin card in the interface.

| ID | Not mentioned | Why it is material | What the page would say if complete | Evidence |
|---|---|---|---|---|
| O1 | The absolute size and trend of Shell's total emissions | The page gives one absolute target (Scope 1+2), which covers 4.7% of the reported footprint, and otherwise only intensities and percentages. SASB: GHG Emissions. | "Our total reported emissions in 2025 were about 1,118 million tonnes CO2e (Scope 1+2: 53; Scope 3: 1,065), down 1.8% on 2024; we believe they peaked at 1.73 billion tonnes in 2018." | E4, E5, E7, E13 |
| O2 | Capital allocation | Whether a "net-zero emissions energy business" is being built is decided by where the money goes. SASB: Reserves Valuation & Capital Expenditures. 2025: 8.9% to Renewables & Energy Solutions, 67% to Upstream and Integrated Gas. | "In 2025 we invested $1.9 billion of $20.9 billion in renewables and energy solutions." | E2 |
| O3 | Production and sales volume plans | LNG sales are planned to grow 4–5% a year to 2030 and oil output to be held at 1.4 million b/d. The only hint is "while sustaining our liquids production" inside a list of decarbonisation actions (L21). | "We plan to grow LNG sales by 4–5% a year and hold oil production at 1.4 million barrels a day to 2030." | E3 |
| O4 | The history of the targets | The 2030 NCI target was lowered from 20% to 15–20% and the 2035 target of 45% withdrawn in March 2024; the timeline shows neither. This is what archived page versions will surface in step 15. | "In 2024 we lowered our 2030 target and withdrew our 2035 target." | E7 |

Candidate not included: lobbying and policy positions (the page conditions the NCI target on "the support of governments", L10, without stating what Shell asks governments for; Shell publishes a separate lobbying report). Kept out because the materiality reference for it is weaker; revisit if the omissions evaluator has room.

**Completeness (document-level): 0.7 / 0.85.**

## 7. Document summary (what the header shows)

| | |
|---|---|
| Headline likelihood | **0.8** (prominence-weighted weakest link: the hero claims C1, C3, C4 and the most material claim C23 all score ≥ 0.75) |
| Headline confidence | **0.85** (decisive evidence is the company's own assured filing, backed by two T1 precedents on the same claim family) |
| Dimension profile | Clarity 0.55 · Support 0.45 · Materiality 0.65 · Consistency 0.7 · Completeness 0.7 |
| Verdict distribution | Supported 10 · Unsubstantiated 7 · Misleading by framing 7 · Contradicted 1 |
| Top issues | 1. C1 — the page's own cautionary note says the plan cannot reflect the headline target. 2. C23 — growing gas sales presented as customer decarbonisation while LNG emissions rose. 3. O2 — 9% of capital to renewables and energy solutions. 4. C11/C13 — weakened targets shown as unbroken achievement. 5. C3/C6 — "cleaner", "low-carbon", "energy system of the future". |
| Credit where due | C14/C15 operational emissions −36%, assured; C16 methane intensity; C18 routine flaring ended; C8 the target scope includes Scope 3. |

**Demo narrative for this document** (D2): open the page; watch the five "achieved" ticks settle to amber as the 2024 strategy PDF arrives; click C1 and scroll the panel to the cautionary-note quote; toggle Omissions to show the capex card; zoom out to the company view, where the same evidence store already holds the annual report, the 2024 strategy and the two rulings.

## 8. Notes for step 2 (data contract) that fell out of this analysis

1. **Spans are strings, offsets are derived.** Every claim and language span above is a verbatim substring of the fixture file; the contract should store the string and the offsets, and validate that they agree.
2. **A claim can have several spans** (C1 appears in P1, P2, P3). Store a primary span for the highlight and secondary spans for the Language layer.
3. **Evidence needs a `relation` field** with at least: supports, contradicts, contradicts-framing, criteria, precedent. C23 depends on "contradicts-framing".
4. **Evidence needs `verified: bool` plus `retrieved` date**; unverified items exist in the log but are never rendered as quotes (D5).
5. **Language signals need a `polarity`**: L12 is a signal the tool should show as benign.
6. **Document regions**: the contract should let the ingestion step mark regions (main, footnote, cautionary-note, promo) so prominence weighting (L19) has something to read.
7. **Tag vocabulary**: seven sins plus "greenrinsing"; keep the list closed, with a free-text `note`.
8. **Dimension scores carry a `basis` string** (one sentence) so the claim panel can show why, not just how much.
9. **Recomputations are evidence items too** (type `computation`, with the formula and inputs), so "numbers recomputed" is visible in the panel.

## 9. Open points for the team review

- Whether C23 is "Misleading by framing" or "Contradicted" (§5.1 note). This decides how the verdict rules in §0 are written.
- Whether C2, C9, C14 should show as Supported at likelihood 0.5, or whether a materiality-only weakness should cap likelihood lower (say 0.4) so "Supported" claims never sit at the midpoint of the scale.
- Whether "greenrinsing" stays as an eighth tag or is folded into the Consistency dimension only.
- E8b is the most useful precedent for the **Fix** field: the ASA accepted a 2025 Shell ad that stated the 68% / 23% investment split on screen. The fix for C1 and O2 should quote it.
