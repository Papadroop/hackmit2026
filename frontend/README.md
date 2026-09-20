# Frontend

Vite, React 19, TypeScript, Tailwind v4, shadcn/ui (radix-nova), Motion, Lucide. Fonts are
Public Sans for the interface and Literata for the document pane and the wordmark, per
`../design-plan.md`. The menu screen also uses `@paper-design/shaders-react` for the pigment
wash and `lenis` for smooth scrolling, per `../menu-design.md`; neither reaches the analysis
screen.

```sh
npm install
npm run dev          # http://localhost:5174, proxies /api to the backend on 8400
npm run typecheck && npm run lint && npm run build
npm test             # vitest: router, reducer, fold, span anchoring, document layout, encoding
node scripts/snap.mjs http://localhost:5174/a/<id> shot.png 1440 900   # headless Chrome screenshot
```

The screenshot script drives Google Chrome over the DevTools protocol (set `CHROME` to
another binary). Extra arguments are JavaScript expressions run in the page before the
shot, so a state can be set up: `'document.querySelector("[data-claim=\"C9\"]").click()'`.
`VISION=achromatopsia` (or `deuteranopia`, `protanopia`, `tritanopia`) renders the page as
that viewer sees it, for checking the verdict encoding without colour. `MOTION=reduce`
emulates `prefers-reduced-motion` for the menu screen's reduced-motion pass. `CLIP=x,y,w,h`
shoots one CSS-pixel rectangle of the page instead of the whole viewport, for looking closely
at a detail such as the menu's waterline.

## The two screens

The menu (`/`) is the one described in `../menu-design.md`. The analysis screen (`/a/<id>`) is
a case file with four dividers — Claims, Omissions, Corrected version, Verdict — and each is
part of the address (`/a/<id>/verdict`), so a section can be linked to and a reload keeps it.
Keys 1 to 4 open them; Escape clears the selected claim. There is no events panel: the
pipeline's progress is nine ticks in the header, and the raw log is still served at
`GET /api/analyses/<id>/log` for anyone debugging the backend.

## Where things are

| Path | What |
|---|---|
| `src/lib/router.ts` | The URL is the screen: `/` is the menu, `/a/<id>` an analysis, `/a/<id>/<section>` one of its four sections. A reload keeps both (the server holds the log). |
| `src/lib/sections.ts` | The four dividers of the case file — claims, omissions, corrected, verdict — and their labels. There is no events section. |
| `src/screens/menu.tsx` | Choose a document, and the screen that carries the name: a title card that rinses as you scroll, the forest behind the list, then the documents, the own-text form and recent analyses. Each document is a sheet with a stripe of pigment down its edge that drains on hover and again when its analysis starts. Documents and recordings come from `GET /api/documents`; pace is a per-viewer preference. |
| `src/components/title-card.tsx` | The first viewport: the Water shader over the generated pigment, the word "rinse" in ink above the waterline and the tagline in white below it, and the rAF loop that writes the waterline's paths as the reader scrolls. The block is drawn twice, and the line clips the ink copy to the part of the sheet that has come clean. |
| `src/components/forest.tsx` | The fixed SVG layer behind the content. Places each tree and writes one CSS variable per tree per frame; CSS derives every dash offset and leaf scale from it. |
| `src/lib/pigment.ts` | The wet-pigment image, drawn on a canvas from a fixed seed so it is reproducible, plus the luminance maths the contrast checks use. It is the dye suspended in the water, and the whole card where there is no WebGL2; what the water refracts is the canopy photograph. |
| `src/lib/forest.ts` | The tree generator: limbs as Bézier curves in a unit space, leaves as smoothed blots, and the growth window each carries. Where the five trees stand, and which of them a viewport shows. |
| `src/lib/menu-scroll.ts` | The menu's scroll choreography as pure functions: how far the rinse has run, the cue's fade, the block's exit, the forest's arrival and each tree's own progress. |
| `src/components/ground.tsx` | The three fixed layers under everything on the menu: the canopy photograph, the veil of paper over it, and the paper's own fibre, which also goes out as `--paper-grain` for the sheets. |
| `src/lib/paper.ts` | The fibre tile, generated from a fixed seed, and the small tilt each sheet keeps from its own document id. |
| `public/canopy.jpg` | The ground. "Aerial view of the Amazon Rainforest" by lubasi, [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0), from [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Aerial_view_of_the_Amazon_Rainforest.jpg). Credited at the foot of the menu, which is what the licence asks; keep that line if you keep the image. |
| `src/lib/waterline.ts` | The edge the rinse leaves: drifting waves and rivulets sampled across the card and smoothed into one path, which clips the wash on one side and the ink wordmark on the other. Pure, so it is tested and scrubs both ways. |
| `src/lib/random.ts` | mulberry32, the seeded PRNG behind the pigment and the forest, so a demo looks the same on every load. |
| `src/screens/analysis.tsx` | One analysis as a case file: the header with the pipeline's own progress, the four dividers, and one section at a time. Selection, the annotation pass and the cross-references between sections live here. |
| `src/components/section-tabs.tsx` | The dividers. Links, not tab widgets, because each section is an address; the open one takes the desk's colour and covers the strip's rule, and a Marker cap slides between them. |
| `src/components/pipeline.tsx` | The nine stages as nine ticks in the header, filling as they complete, with the running one named. What the events panel used to be for. |
| `src/components/claims-view.tsx` | The Claims section: the sheet and the claim column, or a bottom sheet below 56rem. The control for what the sheet is marked with sits at the head of the column. |
| `src/components/omissions-view.tsx` | The Omissions section: what the page does not say, worst first, one paper card each with its materiality, its reference and its evidence. |
| `src/components/corrected-view.tsx` | The Corrected version: side by side by default, or the redline in one column, which is also what a screen under 68rem gets. |
| `src/components/corrected-split.tsx` | The split: one grid with a row per block, the page as published on the left and as the evidence allows on the right, the ids of what changed between them, and what the page omits at the end. |
| `src/components/verdict-view.tsx` | The Verdict: the finding in words, the distribution in the document's own hues, the five dimensions, and the claims to go and look at. |
| `src/components/document-pane.tsx` | The sheet: the blocks with their margin ids, the click and key delegation, and the corrected version's inserted omissions. |
| `src/components/document-blocks.tsx` | One block of the document — heading, list or paragraph — cut by claim marks then by language marks, with the rewrites drawn as a redline or as the corrected text. Shared by the sheet and the split. |
| `src/components/signal-row.tsx` | One language signal in the panel (kind in the layer's mark style, polarity, strength, its words as buttons, the note). |
| `src/components/score-bar.tsx` | A short problem-score bar (length = score, alpha = confidence) shared by the band and the claim detail. |
| `src/components/claim-panel.tsx` | The claims in document order and the document-level wording, under the control for what the sheet is marked with; hands a selected claim to the detail. |
| `src/components/claim-detail.tsx` | One claim read like a ruling: quote, verdict with the judge's reasoning, dimension bars, evidence, the debate collapsed, fix, honest rewrite, fields. |
| `src/components/evidence-list.tsx` | Evidence rows (relation, tier, source, verified quote, provenance, link, computation) and the clickable evidence ids. |
| `src/components/verdict-mark.tsx` | A verdict word in the document's own encoding, for the legend, the list and the detail. |
| `src/lib/diff.ts` | The honest version's redline: word-level diff when most words survive, whole-span replacement otherwise. |
| `src/lib/language.ts` | Words for the Language layer: signal kinds, polarities and their order of notice. |
| `src/lib/evidence.ts` | Words for dimensions, tiers, kinds, verification, relations and roles; how a claim's evidence list is assembled (links plus citations, ordered by relation then tier). |
| `src/lib/encoding.ts` | The verdict scale's numbers: confidence to fill and underline alpha, labels, counts. Hues and underline styles are in `index.css`. |
| `src/lib/anchor.ts` | Span anchoring: code-point offsets to UTF-16, verified against the span's text, re-anchored by context or occurrence when stale (`../contract/CONTRACT.md` §3). |
| `src/lib/document-layout.ts` | Canonical text to blocks and lines; regions classify them. Cuts lines into segments at mark boundaries, so overlapping marks stay flat, and says where a block sits in the text. |
| `src/lib/document-dom.ts` | Margin label placement, scroll-to-span, and what one section asks another to point at. |
| `src/lib/keep-scroll.ts` | Where each section was left, so moving between them and back does not cost the reader their place. |
| `src/state/annotations.ts` | Anchors claim and signal spans and builds both lists of marks; which of them a section draws is the section's own business. |
| `src/state/fold.ts` | Events to contract entities (document, claims, signals, evidence, scores, arguments, verdicts, omissions, summary). Malformed payloads are skipped; an unverified quote is dropped here so no view can show it. |
| `src/lib/events.ts` | The event envelope and lifecycle type names (`../fixtures/README.md`). |
| `src/lib/api.ts` | Calls to the backend. |
| `src/lib/stream.ts` | The EventSource subscription: one handler for every event type, resume on reconnect. |
| `src/state/analysis.ts` | The reducer: state is a fold over the events received. Selectors for views live here. |
| `src/state/analysis-provider.tsx` | Fetches one analysis and tails its stream; mounted with `key={id}`. Exposes `useAnalysis()`. |
| `src/screens/metrics.tsx` | `/calibration`: how far the audit's likelihood matches what regulators decided. Reads `GET /api/calibration`, the artifact `python -m auditor.calibration run` wrote. |
| `src/components/calibration-plot.tsx` | Every precedent on one axis at the score the audit gave it, above the line where it was upheld and below where the advertiser was cleared, with the threshold as a line the reader moves; and the calibration curve beside it. |
| `src/lib/calibration.ts` | The report's shape and the metrics redone in the browser, so moving the threshold is free. A test checks it reproduces the backend's published numbers exactly. |
| `src/screens/company.tsx` | `/c/<company>`: one company across its documents, with the trend. Reads `GET /api/company/{name}`. Read-only: a document's `url` is where it was read from, not what is there now, so nothing is analysed from here. |
| `src/components/trend-line.tsx` | The company's documents in time at their own headline scores. Problem scores, so a rising line is the company getting worse; nothing is drawn below two dated documents. |
| `src/lib/company.ts` | The company view's words and its slug, which mirrors `company_slug` in `backend/auditor/company.py` so a link finds its own company. Shapes come from `@contract`. |
| `src/App.tsx` | The route switch. |
| `src/index.css` | Design tokens and the document pane's type and highlight styles, then the menu screen's own palette and rules (every class prefixed `rinse-`). Light is the designed palette; dark is provisional. |
| `@contract` | Path alias for `../contract/types.ts`, the generated contract types. Type-only imports, so it never reaches a bundle. |

Add shadcn components with `npx shadcn@latest add <name>`. If you re-add `sonner`, keep the
patch that points it at the local theme provider instead of next-themes.
