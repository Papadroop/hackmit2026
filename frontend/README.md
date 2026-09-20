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
emulates `prefers-reduced-motion` for the menu screen's reduced-motion pass.

## Where things are

| Path | What |
|---|---|
| `src/lib/router.ts` | The URL is the screen: `/` is the menu, `/a/<id>` an analysis. A reload keeps the analysis (the server holds its log). |
| `src/screens/menu.tsx` | Choose a document, and the screen that carries the name: a title card that rinses as you scroll, the forest behind the list, then the documents, the own-text form and recent analyses. Documents and recordings come from `GET /api/documents`; pace is a per-viewer preference. |
| `src/components/title-card.tsx` | The first viewport: the Water shader over the generated pigment, the word "rinse", and the mask that drains the pigment from the top down as the reader scrolls. |
| `src/components/forest.tsx` | The fixed SVG layer behind the content. Places each tree and writes one CSS variable per tree per frame; CSS derives every dash offset and leaf scale from it. |
| `src/lib/pigment.ts` | The wet-pigment image the shader refracts, drawn on a canvas from a fixed seed so it is reproducible, plus the luminance maths the contrast checks use. |
| `src/lib/forest.ts` | The tree generator: limbs as Bézier curves in a unit space, leaves as smoothed blots, and the growth window each carries. Where the five trees stand, and which of them a viewport shows. |
| `src/lib/menu-scroll.ts` | The menu's scroll choreography as pure functions: the rinse's mask edge, the title's colour and exit, the cue and tagline fades, and each tree's own progress. |
| `src/lib/random.ts` | mulberry32, the seeded PRNG behind the pigment and the forest, so a demo looks the same on every load. |
| `src/screens/analysis.tsx` | One analysis: header, workspace (document pane and claim panel, or a bottom sheet below 56rem), and the events panel. Selection lives here. |
| `src/components/document-pane.tsx` | The sheet: text from the layout, claim highlights cut by claims then by language marks, margin ids, the honest version's redlines and inserted omissions, and whatever sits on the desk above it. |
| `src/components/omission-cards.tsx` | The Omissions layer: what the document does not say, as slips on the desk above the sheet. |
| `src/components/signal-row.tsx` | One language signal in the panel (kind in the layer's mark style, polarity, strength, its words as buttons, the note). |
| `src/components/summary-band.tsx` | The summary header: headline likelihood with confidence, the five-dimension profile, verdict counts, top issues and credit linking to their claims; collapses below 56rem. |
| `src/components/score-bar.tsx` | A short problem-score bar (length = score, alpha = confidence) shared by the band and the claim detail. |
| `src/components/claim-panel.tsx` | Progress, verdict counts and the claims in document order; hands a selected claim to the detail. |
| `src/components/claim-detail.tsx` | One claim read like a ruling: quote, verdict with the judge's reasoning, dimension bars, evidence, the debate collapsed, fix, honest rewrite, fields. |
| `src/components/evidence-list.tsx` | Evidence rows (relation, tier, source, verified quote, provenance, link, computation) and the clickable evidence ids. |
| `src/components/verdict-mark.tsx` | A verdict word in the document's own encoding, for the legend, the list and the detail. |
| `src/lib/diff.ts` | The honest version's redline: word-level diff when most words survive, whole-span replacement otherwise. |
| `src/lib/language.ts` | Words for the Language layer: signal kinds, polarities and their order of notice. |
| `src/lib/evidence.ts` | Words for dimensions, tiers, kinds, verification, relations and roles; how a claim's evidence list is assembled (links plus citations, ordered by relation then tier). |
| `src/lib/encoding.ts` | The verdict scale's numbers: confidence to fill and underline alpha, labels, counts. Hues and underline styles are in `index.css`. |
| `src/lib/anchor.ts` | Span anchoring: code-point offsets to UTF-16, verified against the span's text, re-anchored by context or occurrence when stale (`../contract/CONTRACT.md` §3). |
| `src/lib/document-layout.ts` | Canonical text to blocks and lines; regions classify them. Cuts lines into segments at mark boundaries, so overlapping marks stay flat. |
| `src/lib/document-dom.ts` | Margin label placement and scroll-to-span. |
| `src/state/annotations.ts` | Anchors claim and signal spans and builds the marks of each layer that is on; `Layers` and the defaults live here. |
| `src/state/fold.ts` | Events to contract entities (document, claims, signals, evidence, scores, arguments, verdicts, omissions, summary). Malformed payloads are skipped; an unverified quote is dropped here so no view can show it. |
| `src/lib/events.ts` | The event envelope and lifecycle type names (`../fixtures/README.md`). |
| `src/lib/api.ts` | Calls to the backend. |
| `src/lib/stream.ts` | The EventSource subscription: one handler for every event type, resume on reconnect. |
| `src/state/analysis.ts` | The reducer: state is a fold over the events received. Selectors for views live here. |
| `src/state/analysis-provider.tsx` | Fetches one analysis and tails its stream; mounted with `key={id}`. Exposes `useAnalysis()`. |
| `src/components/debug-drawer.tsx` | The raw event log in the bottom panel of the analysis screen. Stays in the app throughout. |
| `src/App.tsx` | The route switch. |
| `src/index.css` | Design tokens and the document pane's type and highlight styles, then the menu screen's own palette and rules (every class prefixed `rinse-`). Light is the designed palette; dark is provisional. |
| `@contract` | Path alias for `../contract/types.ts`, the generated contract types. Type-only imports, so it never reaches a bundle. |

Add shadcn components with `npx shadcn@latest add <name>`. If you re-add `sonner`, keep the
patch that points it at the local theme provider instead of next-themes.
