# rinse — Visual design plan

*Companion to `design-doc.md` (D7) and `roadmap.md` (Phase 1). First pass, for team review before any interface code is written. Edit the tokens here rather than in code until the plan is agreed.*

Last updated: 2026-09-19

## Brief

| | |
|---|---|
| Subject | A corporate climate page (Shell's first) read under audit. The document is the product, annotated in place as evidence arrives. |
| Audience | The analyst who has to defend a finding: regulator, journalist, investor analyst. Judges stand in for that reader. Resolves design-doc open question 1. |
| Primary job | Show each claim's verdict and confidence where the claim sits in the text, and make the pipeline's stages visible as they land. |

## Tokens

### Base palette (light)

| Token | Hex | Role |
|---|---|---|
| Desk | `#E9ECEE` | App chrome. A cool reading-room grey; the only non-paper surface. |
| Paper | `#FFFFFF` | The document pane only. Nothing else on screen is white. |
| Ink | `#1C2733` | Text. Blue-black, like fountain-pen ink; not a tinted `#111`. |
| Graphite | `#5B6572` | Secondary text, rules, pending highlights. |
| Marker | `#2A4D9B` | The single interactive accent: selected claim, focus rings, links. |

Dark mode: derive after the light palette is agreed. Paper becomes a dark slate, Desk darker still; verdict hues are lightened for contrast. Not designed yet.

### Verdict scale

Hue encodes the verdict category. Highlight alpha encodes confidence (low confidence looks tentative). Underline style is the second channel so meaning survives greyscale and colour-blindness (D7).

| Verdict | Hex | Underline | Highlight alpha |
|---|---|---|---|
| Contradicted | `#B3261E` | solid | 0.30 × confidence + 0.04 |
| Misleading by framing | `#B8700A` | wavy | same |
| Unsubstantiated | `#6E6A85` | dashed | same |
| Supported | `#1E7566` | dotted | same |
| Pending (claim found, no verdict yet) | Graphite at 15% | none | fixed |

Built 2026-09-19 (roadmap step 5). The alpha slope was widened from the first draft
(0.18 × confidence + 0.10) so that a 0.5-confidence verdict (alpha 0.19) sits just above the
pending grey and a 0.9 verdict (0.31) is unmistakable; the underline's own alpha also follows
confidence (0.7 × confidence + 0.3) so the category stays legible when the fill is faint.
Underlines are 1.5px, offset 0.16em, and do not skip descenders, so dashes and dots read as
continuous patterns. The margin id takes the verdict hue. Hover is a 1px ring in the mark's
own hue; selection is a 1.5px Marker ring. The numbers live in `frontend/src/lib/encoding.ts`,
the hues and line styles under `[data-verdict]` in `index.css`. Checked with Chrome's
achromatopsia and deuteranopia emulation: the four categories stay distinct by line style.

Language layer marks (hedges, vague terms, scope mismatches) use Graphite text-decoration only, never fill, so they read as a lighter layer beneath verdicts.

### Type

| Face | Role | Notes |
|---|---|---|
| Literata (variable, optical sizes) | Document pane | 17px / 1.6, measure 68ch, ragged right. Reads as the exhibit, distinct from the tool. |
| Public Sans (variable) | Everything the tool says: header, panel, evidence, buttons | Tabular figures (`font-variant-numeric: tabular-nums`) for scores. Chosen for its regulator vernacular (US Web Design System). |

Scale: 13 / 15 / 17 / 22 / 28 px. Weights 400, 500, 600 only. No monospace anywhere, including data labels. No uppercase labels; "Tier 2", not "T2".

Fontsource packages when the time comes: `@fontsource-variable/literata`, `@fontsource-variable/public-sans`. Geist can then be removed.

## Layout

Three regions per D7, all left-aligned. Summary header is one dense band, not stat tiles. The claim panel uses spacing, indentation and rules, not cards. Omissions are margin notes in the document gutter.

```
┌────────────────────────────────────────────────────────────────────┐
│ rinse   Shell plc, Climate page   Layers ▣ ▢ ▢   Honest version ○ │
├────────────────────────────────────────────────────────────────────┤
│ Likelihood 0.78 (confidence 0.71)  Clarity ▮▮▮▯ Support ▮▮▮▯ …    │
│ 4 contradicted  5 unsubstantiated  6 misleading  3 supported       │
│ Top issues: net-zero target outside plan …  NCI is not Shell's …   │
├───────────────────────────────────────────┬────────────────────────┤
│ gutter │ Document, Literata, 68ch          │ Claim C1               │
│  ◐ C1  │ Our target is to become a         │ Contradicted, 0.82     │
│        │ ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾   │ Clarity   ▮▮▯▯  c .80  │
│  ▢ Not │ net-zero emissions energy …       │ Support   ▮▮▮▮  c .90  │
│  mentioned:                                │ Evidence               │
│  absolute Scope 3 …                        │  Tier 2  Annual report │
│        │                                   │ Prosecutor ▸ Defence ▸ │
│        │                                   │ Fix      Honest rewrite│
└───────────────────────────────────────────┴────────────────────────┘
```

- Header band: headline likelihood and confidence first, then the dimension profile, then verdict counts, then top issues. Each item links to its claim.
- Document pane: the paper sheet sits on the desk with a hairline edge, no shadow. Gutter to the left holds claim marks and omission notes.
- Claim panel: dimensions as short bars with confidence beside each; evidence as rows with the tier mark at the left, verified quote, link, and supports/contradicts; prosecutor and defence collapsed; fix and honest rewrite last.
- Below ~900px the panel becomes a bottom sheet (vaul is already installed); the header band collapses to likelihood, confidence and counts.

### The menu (built 2026-09-19)

The first screen lists the documents, not features. Each row is a document: company in
Graphite, title in Literata (the source text's voice), then type, retrieval date, length and a
link to the source. Rows sit on Paper with hairline separators because they are separate
documents; no cards, no numbering. One primary action per row, "Analyse", with the recording's
length beneath it in small text, so replay is disclosed without being loud. The pace control
sits with the list, not in the app chrome. The interface never shows the team's expected
verdict for a demo text. Every analysis has its own address (`/a/<id>`) so a reload during
the demo keeps it.

### The document pane (built 2026-09-19, roadmap step 4)

The sheet is Paper on the Desk with a hairline edge, 68ch of Literata at 17px/1.6. The source
page's hierarchy is kept, because it is evidence: the hero paragraph is set a size larger, the
footnote and the cautionary note are small print in Graphite, the promo card is an indented
aside. A claim is a Graphite highlight at 15% with no underline (the pending state of the
verdict scale) and its id sits in the left margin beside its first line, in Public Sans with
tabular figures; ids that would collide stack downward. Selecting a claim, from the text, the
margin or the panel, rings it in Marker and opens its fields on the right; on a narrow screen
the fields open in a bottom sheet. Highlights fade in as claims arrive (400 ms, none under
reduced motion). Structure is computed from the canonical text and only classified by regions,
so a document with no regions still reads as paragraphs; highlights are flat segments cut at
every mark boundary, so the word-level Language layer can later straddle a claim boundary
without nesting.

### The claim panel (built 2026-09-19, roadmap step 6)

A selected claim reads like a ruling, top to bottom: the statement at issue (its quotes, each
a button that shows it in the text), the verdict word in the document's encoding with
likelihood and confidence, the pattern tags, the judge's reasoning and the evidence it
cites; then the four dimensions as short bars, where bar length is the problem score and the
bar's alpha is the evaluator's confidence, each with its one-sentence basis and the evidence
it rests on; then the evidence as rows separated by hairlines, not cards: the relation to the
claim leads ("Contradicts", "Contradicts the framing, supports"), the tier sits at the right
as "Tier 2" with the scale in its tooltip, then the source, the quote in Literata when it is
verified, one sentence each for kind, verification method and retrieval, the source's host
as the link text, and any note; computations show their formula and inputs. Rows are ordered
by relation (most consequential first), then tier, then arrival; items that a score, an
argument or the verdict cites without a direct link are appended as "Cited". Evidence ids
anywhere in the panel are buttons that scroll to their row and flash it. The prosecutor and
defence sit under a collapsed "Debate" heading, then the fix, the honest rewrite in
Literata, and the claim's extracted fields last under "Details". Nothing here uses hue
except the verdict word; the dimension bars are Ink so a problem score is not mistaken for
a category. Citation integrity is enforced in the fold, not the view: a quote that is not
verified never reaches the screen.

### The summary header (built 2026-09-19, roadmap step 7)

*Superseded 2026-09-20: the band is now the Verdict section. See "The analysis screen, as a case file".*

One band under the app header, on the chrome's grey, spanning the document and the panel.
Line one: "Likelihood" and the headline score at 22px with its confidence beside it, then the
five-dimension profile (the four claim dimensions plus Completeness) as the same short Ink
bars the claim panel uses, each with its score and confidence. Line two: the verdict
distribution, count first and the category word in the document's encoding, then the claim
and omission counts. Then the top issues, numbered by rank in two columns, and the credit,
each a dotted-underlined button that selects its claim and scrolls the document to it; the
selected one is set in medium weight. A target the interface cannot show yet (an omission,
until step 8) is plain text. Before the summary stage the band already stands: "Likelihood
follows the verdicts", empty profile tracks, and the live verdict counts, so the final
summary fills a space rather than pushing the document down. Below 56rem the band keeps only
the headline and the counts, as planned. The summary's narrative is prose, so it goes in the
panel's overview under "Summary", not in the band; a summary that is not yet final says
"provisional" in both places. No hue is used except the verdict words.

### The layers (built 2026-09-19, roadmap step 8)

*Superseded 2026-09-20: Omissions is a section, and the remaining two marks are a control at the head of the claim column. See "The analysis screen, as a case file".*

Three toggles in the app header, each with its count: Claims, Language, Omissions. Claims
and Language are on from the start because they are the live progression; Omissions is off,
because its cards would push the sheet down while the reader is in the text. The Language
layer is word-level text-decoration only, as planned: a 1px dotted Graphite line tight under
the words (0.04em), so a verdict underline can sit below it at 0.16em; a benign note is the
same line at 40%, a credit is a thin solid line in the Supported hue, so the three read apart
in greyscale. Hovering a mark names the signal; a word carrying several signals is styled as
the most notable and described by all. The text is cut by claims first and by language marks
inside each piece, so a claim highlight stays one element and a signal that straddles a claim
boundary is drawn in two pieces, which an underline does not show. Signals with no place in
the text (document-level) appear in the panel's overview under "Wording, document-level";
a claim's own signals appear in its detail under "Wording", each word a button that scrolls
the sheet to it. Omissions have no place in the text either, so they are slips of Paper on
the Desk above the sheet, two abreast when the pane is wide: "Not mentioned", the topic, why
it is material, what the page would say in Literata, the materiality score with its
confidence, the reference and the evidence ids. A top issue or a count that names an
omission switches the layer on and scrolls to the card. The toggles are hidden below the
small breakpoint; a phone gets the default layers.

### The honest version (built 2026-09-19, roadmap step 9)

*Superseded 2026-09-20: the toggle is the Corrected version section, which also offers a clean copy. See "The analysis screen, as a case file".*

A toggle beside the layers, with the count of rewrites. On, the sheet becomes a redline in
the regulator's own idiom: each claim's primary span shows what the evidence does not allow
struck through in Graphite, and the honest rewrite after it in italic Literata, the voice of
a rewrite, with no colour of its own. The claim's highlight stays around both, so the diff
lines up with its claim and its margin id by construction; the fill stays on the struck
words and the honest words sit on Paper, with only the category underline continuing. When
at least half the original words survive in at most four change runs the redline is
word-level (two claims in the fixture); otherwise the whole span is replaced, which is what
a rewrite from scratch is. Repeated spans of a claim are left as they are. A rewrite's full
stop is dropped when the document's own follows the span. What the document omits is
inserted at the end as italic paragraphs with O-ids in the margin; clicking one, or its id,
opens its card. Off, every redline and insertion disappears and the margin ids return to
the claims alone.

## Principles

1. The document is the hero. The only white on screen is paper; the chrome stays quiet grey.
2. One motion moment: highlights settle from Graphite to verdict colour as evidence arrives (D7 live progression). Nothing else moves unprompted. Respect `prefers-reduced-motion` by cutting straight to the settled state.
3. Structure encodes meaning: underline style is category, alpha is confidence, the tier mark is reliability. No decorative eyebrows, numbering, or dividers.
4. A number never appears without its confidence.
5. Copy is in the tool's voice, sentence case, plain verbs. "Not mentioned: absolute Scope 3 emissions" rather than "Omission detected".

## Review against generic defaults

Checked against the common AI-generated looks; what was changed and why.

- Rejected cream paper with a serif and a clay accent. Paper is white on a grey desk; the accent is ultramarine.
- Rejected green as the brand colour, including the leaf icon in the current smoke test. Green appears only as the Supported verdict, and a cool verdigris rather than eco-green.
  The menu screen is the one exception, made deliberately when the product was named **rinse** on 2026-09-20: the name is about washing green off, so that screen has to show green to take it away. It is still not the brand colour. Green there is a material — wet pigment on paper, in the Supported hue — that the reader rinses off the card, and afterwards it survives only in the leaves of the trees, which is the auditor's argument in one image. The analysis screen is untouched. See `menu-design.md`.
- Swapped Geist (the installed shadcn default) for Public Sans, chosen for the subject rather than habit.
- Dropped uppercase tier labels and any middle-dot meta strings.
- Watch items while building: broadsheet hairlines everywhere (rules only where they separate evidence items) and the SaaS card kit (evidence is rows, the summary is one band, no uniform shadows).

## Open for the team

- Agree or edit the verdict hues; check all four against each other in greyscale before step 5.
- The document pane keeps the source page's headings and hierarchy as-is (built that way in step 4); confirm or change.
- Dark mode palette, after light is agreed.

## The menu, rinse (built 2026-09-20)

The first screen was rebuilt to the specification in `menu-design.md`, which owns the detail. What the rest of this plan needs to know:

- **The name.** The product is **rinse**, lowercase everywhere. The wordmark is italic Literata, the voice of the honest rewrite in the application, so the name reads as the honest version. It is the one place the interface borrows the document's typeface. "Greenwashing Auditor" is retired from the interface.
- **The green, and where it stops.** Menu-only tokens live beside the base palette in `index.css`: Rinsed paper `#E6EEE9`, Viridian (the Supported hue), Pine `#0F3B2E`, Sap `#6F9B3A`, Wet paper `#D5E3DA`. Nothing on the analysis screen changed, and Marker is still the interactive accent — no button turned green.
- **One orchestrated moment, spread across the scroll.** The first viewport opens with the word "rinse" in ink on clean paper and the bottom half of the card under green water — the same aerial canopy the page stands on, refracted and moving, seen through a depth of pigment that is nearly clear at the surface and dense below it. Scrolling takes the rest of the pigment down behind a waterline that runs in waves and cuts channels through it; the tagline under the line comes up in ink as the water passes it. Below the card, ink trees draw themselves in growth order and leaf last. Nothing below the card fades or slides in — the forest is the motion there.
- **Why white type that becomes ink.** Ink on dense pigment is 2.8:1. Type on the wash is white and becomes ink as the water clears, which turns the constraint into the moment. Each piece is drawn twice, white and ink, and the waterline clips the ink copy to the part of the sheet that has come clean, so the water uncovers the letters rather than a colour ramp taking them through grey. Measured on the built screen: type on the wash is 6.1:1 on average and 3.8:1 at its worst pixel; the tagline 4.6:1 at worst; the cue 4.7:1.
- **The water is the ground, seen through water.** The shader refracts the canopy photograph rather than a flat wash, so the forest continues under the surface. It was an opaque green field before, which read as murk: water needs something to be water *over*. The green is now a depth rather than a fill.
- **The ground is a real canopy.** Under everything, fixed, is an aerial photograph of dense Amazon forest, veiled back with the page's own paper until it is a ground rather than a picture, with the paper's fibre tiled over it. The drawn trees are ink over it, and the column of documents sits on a frosted panel of paper. It is on from the first frame, so the rinse takes the pigment off the card and what is under the sheet is the forest itself. Credit and licence (CC BY-SA 2.0) are on the page.
- **Below the card, sheets on the ground.** Each document is its own sheet of paper, square, hairlined, with a 4 px stripe of pigment down its left edge — the green that document still has on it. The stripe drains when the sheet is under the pointer or the keyboard, and again for good when its analysis starts: the title card's gesture at the size of a row, and the only decoration on the sheet. Section headings are the serif, so the list speaks in the document's voice and the controls beside it read as interface.
- **Reach.** Green is a material, never a light: no neon, no glow, no gradient text, no leaf icon. Paper stays white, never cream.

Changes against `menu-design.md`, each recorded there with the reason. From building it: the Water shader needed a crop and an offset to stop it seaming and to keep the title's contrast; the forest's limbs cannot use `vector-effect: non-scaling-stroke` because it breaks the draw-on; and leaves are smoothed blots at a lower opacity, because hard hexagons at 0.72 multiply to black wherever the canopy is dense. From reviewing it on screen (§6.1, §6.4): the card opens with the water already halfway up it and the wordmark centred in the clean half above the line, the wordmark is at the top and a third smaller, the sheet edge across the bottom of the card is gone, and the straight mask edge that drained the pigment is now the waterline — it read as a band sliding down a green rectangle rather than as water leaving a sheet. The list below it was rebuilt as sheets (§8), and the page lost a third of its length: the card's wrapper is 150svh instead of 200, the list sizes to what it carries instead of a 170svh floor, and the forest grows over the list's approach to the top of the viewport rather than over the whole page, so the stand is full while the reader is arriving at the list.

## The analysis screen, as a case file (rebuilt 2026-09-20)

The screen showed everything at once, in strips: an app header, a summary band, the document,
the claim panel, and the raw event log across the bottom. The document — the thing the plan
calls the hero — had about half the height and a third of the width, and the three things that
were not the document each had too little room to be read. Asked for "a bar up top with
different selections", and for the events log to go, it was rebuilt as a case file with four
dividers, each carrying one whole argument.

**The dividers.** Claims, Omissions, Corrected version, Verdict, in that order: the document
and what is wrong with it, what is not in it at all, what it should have said, and the finding.
Each is an address (`/a/<id>/verdict`), so a section can be linked to, the back button walks
them and a reload during the demo keeps the one that was open; keys 1 to 4 open them. The open
divider is the one pulled forward — it takes the colour of the desk below it and its bottom
edge is the desk's own, so it covers the strip's rule and reads as one piece of paper with the
section under it. A 2 px Marker cap sits on its top edge, because Marker is what "selected"
means everywhere else on this screen, and it slides from divider to divider on a spring: the
only motion added, and it answers the reader's own click. Each divider carries its count, and
the Verdict carries the headline score, so the number is visible before the section is opened.

**No events section.** The raw log was a developer's tool, not one of the file's dividers, and
`GET /api/analyses/<id>/log` still serves it. What it was doing on screen — showing that the
pipeline is working — is now nine ticks in the header, one per contract stage, filling as they
complete with the running one named beside them. It is the only thing that moves on its own,
and it stops when the analysis does (roadmap's "every stage is inspectable" is now the log
endpoint plus the ticks).

**Claims** keeps the arrangement that worked: the sheet on the desk, every claim highlighted
where it sits with its id in the margin, and the claims in a column beside it, a selected one
read like a ruling. What was three layer toggles in the app header is now two at the head of
that column, where the lists they affect are — Claims and Wording, both on, so the reader can
take the marks off and read the page as published.

**Omissions** was a layer that pushed slips of paper above the sheet, which is why it was off
by default. It has the desk to itself now: one card per topic, worst first, each saying why the
absence is material, what the page would say if it were complete, how near the page came to
saying it, its materiality with confidence, the standard that makes it material, and its
evidence behind a fold.

**Corrected version** was the "honest version" toggle. As a section it is a split: the page as
published on the left, the same page as the evidence allows it on the right, block beside block.
A redline reads well when a rewrite is a few words, but the worst claims here are rewritten
wholesale, and a struck paragraph followed by its replacement is two paragraphs of prose
interleaved — neither can be read. The two columns are one grid with a row per block rather
than two scrolling panes, so a paragraph and its rewrite always start on the same line however
much longer the rewrite is; a list is split further, a row per item, because items are what the
corrections land on. Between the columns are the ids of the claims that changed in that row —
the sheet's margin ids, in the one place a split leaves for them — and each opens its claim.
What the page omits comes last, with "Not on the page" where the original would be.

The redline is kept as the second view, because it is the only one that shows a change of two
words as two words, and it is what a screen under 68 rem gets, since two columns of prose need
the width for two measures. The tool's wording is italic in both and keeps the claim's own
highlight, so it is never mistaken for the page's.

**Verdict** was the band. The summary's narrative had nowhere to go in a band, so it was in the
panel in 13 px; here it is the finding, in Literata at 19 px, under the headline score and its
confidence. Then the verdicts as a distribution bar in the document's own hues with the counts
beneath it, the five dimensions with the question each answers, and the top issues and the
credit, each a button that opens the section which can show its target.

Reading between sections is kept: what one names, another opens and puts in view, and where a
section was scrolled to is remembered while the file is open.

**Copy.** "Honest version" is the design-doc's name (D6) and stays there; the interface calls
the section Corrected version, which is what it is for the reader, and the claim detail's
heading follows it.
