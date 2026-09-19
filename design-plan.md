# Greenwashing Auditor — Visual design plan

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
| Contradicted | `#B3261E` | solid | 0.18 × confidence + 0.10 |
| Misleading by framing | `#B8700A` | wavy | same |
| Unsubstantiated | `#6E6A85` | dashed | same |
| Supported | `#1E7566` | dotted | same |
| Pending (claim found, no verdict yet) | Graphite at 15% | none | fixed |

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
│ Greenwashing Auditor   Shell plc, Climate page   Layers ▣ ▢ ▢   Honest version ○ │
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
- Swapped Geist (the installed shadcn default) for Public Sans, chosen for the subject rather than habit.
- Dropped uppercase tier labels and any middle-dot meta strings.
- Watch items while building: broadsheet hairlines everywhere (rules only where they separate evidence items) and the SaaS card kit (evidence is rows, the summary is one band, no uniform shadows).

## Open for the team

- Agree or edit the verdict hues; check all four against each other in greyscale before step 5.
- Decide whether the document pane keeps the source page's headings as-is or normalises them.
- Dark mode palette, after light is agreed.
