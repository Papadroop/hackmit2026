# rinse: the menu screen

*Design and build specification for the first screen of the HackMIT 2026 greenwashing auditor, now named "rinse". Written 2026-09-20 for the agent that builds it. It sits beside `design-plan.md` (the interface's tokens and principles) and `roadmap.md`. Read `design-plan.md` and `frontend/README.md` first; this document overrides `design-plan.md` only where it says so.*

## 0. How to use this document

- Build exactly what is specified. Where a value is given, use it. Where a value is marked *tune*, start from the given value and adjust by screenshot until the stated target is met, then record the final value in this document.
- The product name is now **rinse**, lowercase everywhere, including sentence starts in copy that names it. "Greenwashing Auditor" is retired.
- Decisions Chris has not yet confirmed are listed in §1 and are taken as decided. Do not reopen them; do not ask about them. If one turns out to be impossible, build the stated fallback and say so in your report.
- Nothing here changes the analysis screen except the wordmark (§4.2). Do not touch `contract/`, `backend/`, `fixtures/`, `demo-documents/`.
- Do not commit. Another agent works in the same tree on the backend; its dev server on port 8400 reloads on file changes. Ports 8000 and 5173 belong to an unrelated project on this Mac; never kill them. The frontend dev server is on 5174.
- Gates before you report done: `npm run format`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, all clean. Then the visual checks in §14.
- Screenshots: `frontend/scripts/snap.mjs <url> <out.png> [width] [height] [js steps...]` drives headless Chrome over the DevTools protocol. It has a real GPU (WebGL2, about 60 fps), so shader scenes screenshot fine. Each JS step is an async IIFE string whose resolved value is printed. Write shots to your scratchpad directory, never into the repo.

## 1. Decisions taken

Chris approved the concept in conversation. These specific choices were recommended and not yet confirmed; treat them as decided:

| Decision | Taken | Fallback if impossible |
|---|---|---|
| Title-card background | Paper Design's `Water` shader over a generated pigment image (§6.2). **Built with `Water`**; the fallback was not needed once caustic and highlights came down (§6.3, §20) | Paper Design's `Warp` with the same four pigment colours; everything else unchanged |
| Trees | Ink-drawn SVG forest generated in code, grown by scroll (§7) | None. Do not use three.js, React Three Fiber, Rive or Lottie. |
| Reach of the green | The menu screen only. The analysis screen stays the ink, paper and desk reading room in `design-plan.md`. | n/a |
| Wordmark | "rinse" in Literata italic, lowercase, at every size | n/a |
| Smooth scrolling | Lenis on the menu screen only, off under reduced motion | Native scrolling |

## 2. The idea

The name says what the product does: the green comes off. So the menu screen shows that, once, in order:

1. **The wash.** The first viewport is wet green pigment on white paper, moving as if under running water. The word "rinse" is the only other thing on it.
2. **The rinse.** As the reader scrolls, the pigment drains from the top of the card downward until the paper is clean. The word turns from white to ink as the water passes over it. Under the card is the list of documents.
3. **What actually grew.** Behind the list, trees are drawn in ink as the reader keeps scrolling: trunk, limbs, twigs, in growth order. Leaves come last, as green watercolour blots. Green appears only where something real grew, which is the auditor's argument.

Everything else on the screen is still. There is one orchestrated moment, spread across the scroll, and no decoration that does not belong to it.

## 3. Scope

Changes:

- `frontend/src/screens/menu.tsx`: restructured around a title card, a forest layer and the existing content sections.
- New: `frontend/src/components/title-card.tsx`, `frontend/src/components/forest.tsx`, `frontend/src/lib/pigment.ts`, `frontend/src/lib/forest.ts`, `frontend/src/lib/menu-scroll.ts`.
- `frontend/src/components/chrome.tsx`: the wordmark.
- `frontend/index.html`: `<title>rinse</title>`.
- `frontend/src/index.css`: Literata display and italic imports, menu tokens, title and forest rules.
- Dependencies: `@paper-design/shaders-react` (verified 0.0.81, Apache-2.0, about 14 kB gzipped for one shader after tree-shaking, no three.js dependency, peer React ^19; install with `npm i -E` because the 0.0.x line ships breaking renames) and `lenis` (verified 1.3.26, MIT, 5 kB). Nothing else. In particular no GSAP, no three.js, no React Three Fiber (its current release pins React below 19.3; this project is on React 19.3.0 and the install fails).
- Docs: append a section "The menu, rinse (built <date>)" to `design-plan.md` (do not delete the earlier "Rejected green as the brand colour" line; add a sentence under it saying the menu screen is the exception and why). Add the new files to the "Where things are" table in `frontend/README.md`.

Unchanged: the API calls and data handling in `menu.tsx` (documents list, `live_analysis`, pace preference, recent analyses, the own-text form, error and empty states). The interface still never shows a demo document's expected verdict (`role`).

## 4. Tokens

### 4.1 Colour

Menu-only tokens, defined as CSS variables in `index.css` next to the existing palette, with a `.dark` override. Add them to `@theme inline` so Tailwind utilities exist (`bg-rinsed-paper`, `text-pine`, ...).

| Token | Light | Dark | Role |
|---|---|---|---|
| Paper | `#FFFFFF` (existing `--paper`) | `#1E242B` (existing) | The list sheet, form fields. |
| Ink | `#1C2733` (existing `--ink`) | `#E6E9EC` (existing) | All type; tree branches. |
| Rinsed paper | `#E6EEE9` | `#161D1A` | The page background under the list: a cool, faintly green off-white. Replaces Desk on this screen only. |
| Viridian | `#1E7566` (alias of `--verdict-supported`) | `#1E7566` | The pigment's mid-tone. Same green as the Supported verdict, so the two screens share one green. |
| Pine | `#0F3B2E` | `#175C50` | Where pigment pools. In dark mode it is lifted so the wash shows against the dark page. |
| Sap | `#6F9B3A` | `#7FA845` | Leaves, and thin veins in the wash. A warm watercolour green. |
| Wet paper | `#D5E3DA` | `#35524A` | The thinnest wash; the shader's highlight colour. |

Rules:

- Green is a material, never a light. No neon, no acid green, no Tailwind `green-500`, no glow, no gradient text.
- Ink text never sits on dense pigment: contrast of Ink on Viridian is 2.8:1. On the wash, type is Paper (white). White on Viridian is 5.5:1, on Pine 12:1, on Sap 3.3:1, so the tagline must be at least 24 px (large text) wherever Sap veins can lie under it.
- Marker (`#2A4D9B`) remains the interactive accent for buttons, links and focus rings. Do not recolour buttons green.

### 4.2 Type

- Import Literata's display and italic files. `index.css` currently imports `@fontsource-variable/literata` (weight axis, upright only). Replace with `@fontsource-variable/literata/opsz.css` and add `@fontsource-variable/literata/opsz-italic.css` (both are already in `node_modules`). Literata's axes: weight 200–900, optical size 7–72.
- **The wordmark**, at every size: `font-family: var(--font-serif); font-style: italic; font-variation-settings: "opsz" 72, "wght" 420;` lowercase "rinse". In the analysis header and the not-found page: 18 px, `"opsz" 18`, foreground colour, no underline, existing focus ring. It links to the menu there. The menu screen itself shows no small wordmark (§6.5).
- **The title** on the card: the wordmark at `font-size: clamp(96px, 22vw, 360px); line-height: 0.9; letter-spacing: -0.015em;`. Rendered as an `h1` whose text content is exactly "rinse" (letters wrapped in spans for the reveal; the accessible name stays "rinse").
- **The tagline**: Public Sans 400, 24 px / 1.35, maximum width 30ch. Do not go below 24 px at any breakpoint (§4.1).
- Everything below the card uses the existing scale: 13 / 15 / 17 / 22 / 28 px, weights 400, 500, 600 only. Headings "Documents", "Your own text", "Recent" stay 22 px / 500. No uppercase labels, no monospace.

Why Literata italic for the name: in the application, italic Literata is the voice of the honest rewrite (design-plan.md, "The honest version"). The wordmark in that voice says the product is the honest version. It is the one place the tool borrows the document's typeface.

### 4.3 Surfaces and layers

Stacking order, back to front:

| z | What | Position |
|---|---|---|
| 0 | Page background, Rinsed paper | `body` / screen root |
| 1 | Forest SVG layer | `position: fixed; inset: 0; pointer-events: none;` `aria-hidden` |
| 2 | Content sections (list on Paper, headings and forms on Rinsed paper) | normal flow |
| 3 | Title card wrapper (200svh) with the sticky card (100svh) inside | normal flow, first child |
| 4 | Fixed header with the theme toggle | `position: fixed; top: 0; right: 0` |

The card is above the content in stacking so that as the wrapper scrolls away the list simply emerges from under the card's bottom edge. The forest sits under everything and is only visible where the content has no Paper surface (margins, section gaps, behind headings and labels).

## 5. Page structure

Desktop (1440 wide):

```
┌──────────────────────────────────────────────────────────────┐ ─┐
│                                                     [◐ theme]│  │
│                                                              │  │
│   ▒▒▒▒▒▒▒▒▒ green pigment, moving under water ▒▒▒▒▒▒▒▒▒▒▒▒▒  │  │ card, sticky,
│                                                              │  │ 100svh, inside
│         rinse                     ← Literata italic, white   │  │ a 200svh wrapper
│         Every environmental claim in a corporate             │  │
│         text, rinsed down to its evidence.                   │  │
│                                                              │  │
│         Choose a document                                    │  │
│ ═══════════════════ hairline: top edge of the sheet below ═══│ ─┘
│ ╲│╱      Documents                          Pace 1× 4× 10× ∞ │
│  │╲      ┌────────────────────────────────────────┐      ╲│╱ │
│  │       │ Shell plc                     Analyse  │       │  │  trees grow in the
│ ╱│       │ Climate | Shell Global                 │      ╱│╲ │  margins and behind
│  │       │ Apple Inc.                Analyse live │       │  │  the sheet as you
│  │       └────────────────────────────────────────┘       │  │  scroll
│          Your own text                                       │
│          [ textarea ]                                        │
│          [ url ]                                             │
│ ✿✿✿      Recent                                        ✿✿✿  │  leaves last
└──────────────────────────────────────────────────────────────┘
```

Phone (390 wide): the same order. The title is 96 px, the tagline wraps to three lines, the cue sits above the sheet edge. One tree, rooted at the bottom right, behind the content.

Alignment: everything is left-aligned on one axis. The card's inner container and the content sections both use `mx-auto w-full max-w-3xl px-6`, so the title's left edge, the tagline, the cue and the "Documents" heading share the same x. Nothing is centred.

Heights:

- Card wrapper: `height: 200svh`. Card: `position: sticky; top: 0; height: 100svh`.
- Content section: `padding-top: 4rem; padding-bottom: 8rem; min-height: 170svh` so the forest's scroll range exists even with three documents.

## 6. The title card

### 6.1 Composition

Inside the sticky card, back to front: the shader mount (full bleed), the mask that rinses it (§6.4), the inner container with the title block, the cue, the sheet edge.

- Title block top edge at 40svh. Title, then the tagline 24 px below the title's baseline box.
- Cue: "Choose a document", Public Sans 15 px, white, at `bottom: 56px` on the content axis.
- Sheet edge: a full-width strip at the card's bottom, 12 px tall, Paper, with a 1 px top border `#CBD1D6` (dark: `#2B333B`). It reads as the top of the sheet underneath.

**As built (2026-09-20, second pass).** Back to front: the wash (full bleed, clipped by the waterline), the waterline's own SVG, the block in white, the same block in ink clipped to the clean sheet. Four changes, all from looking at the built screen:

- **The card opens with the water already halfway up it**, not under a full sheet of pigment (§6.4). That sets the rest of the composition: the wordmark sits in the clean half above the opening waterline in ink, and the tagline below it in white on the wash.
- **The wordmark is centred in that clean half, not at 40svh:** `margin-top: calc(24svh - 0.45em)` puts the middle of its line box a little above the middle of the half, and `em` there resolves against the title's own size, so it holds at every viewport. `font-size: clamp(72px, min(14vw, 36svh), 210px)`, down from `clamp(96px, 22vw, 360px)`. Two caps, because two things bound it: at 22vw the word ran edge to edge and read as an overflow rather than a size, and 36svh is what keeps the box clear of the opening waterline's highest crest on a short window.
- **The tagline is positioned from the top of the card, at 60svh,** not from the wordmark's baseline. It has to start below the opening waterline's lowest trough (56.2svh), and both copies of the block have to lay out identically, which they cannot do if one of them measures from a word whose size is clamped against the viewport.
- **The sheet edge is gone.** A 12 px Paper strip with a hairline across the bottom of a full-bleed card read as a divider laid over the image, not as the sheet underneath. The cue already says there is more, and the waterline gives the card an edge of its own.

### 6.2 The pigment image (`lib/pigment.ts`)

The shader refracts an image. Generate it in code so it is reproducible and matches the palette. Pure function `pigmentWash(seed: number, size = 768): string` returning a PNG data URL from an offscreen canvas, memoised per theme.

1. Fill the square with Viridian.
2. Seeded PRNG (mulberry32, seed 7). Draw 18 radial-gradient blobs at seeded positions: 10 Pine (centre alpha 0.55 to 0 at the edge, radius 18–45 % of the canvas, composite `multiply`), 5 Sap (alpha 0.35, radius 12–28 %, `multiply`), 3 Wet paper (alpha 0.5, radius 10–20 %, `screen`). These are the thin spots where the water runs.
3. A vertical gradient of Pine at alpha 0.35 from the top to 40 % down: pigment pools where the water enters.
4. Grain: 24 000 one-pixel rectangles at seeded positions, alternating white and black at alpha 0.05.
5. Target: mean relative luminance between 0.08 and 0.14 (measure it in a test by sampling the canvas; white text then contrasts at 5:1 or better on average). Fewer than 15 % of pixels lighter than Sap.

Dark mode uses the dark pigment set from §4.1 with the same procedure.

### 6.3 The shader

`import { Water } from "@paper-design/shaders-react"`. Before using it, read `node_modules/@paper-design/shaders-react/dist/index.d.ts` for the exact prop names, types and ranges; do not guess ranges. Verified prop names: `image, colorBack, colorHighlight, highlights, layering, edges, caustic, waves, size`, plus the mount props `speed, frame, minPixelRatio, maxPixelCount`.

Verified ranges: `highlights`, `layering`, `edges`, `waves` and `caustic` are 0–1; `size` is 0.01–7; `fit` is `contain` or `cover`; `image` accepts a URL string or an `HTMLImageElement`; `speed` 0 stops the render loop entirely; `frame` fixes the phase. The mount defaults `minPixelRatio` to 2, so set it explicitly. The loop already pauses when the tab is hidden or the element leaves the viewport.

Starting values (*tune*): `image` = the pigment data URL; `fit="cover"`; `colorBack` = Pine; `colorHighlight` = Wet paper; `highlights` 0.3; `caustic` 0.4; `waves` 0.2; `layering` 0.5; `edges` 0.2; `size` such that one ripple spans 12–20 % of the viewport width; `speed` 0.6; `minPixelRatio` 1; `maxPixelCount` 1 200 000.

**As built (2026-09-20), tuned by screenshot at 1440×900:** `highlights` 0.04, `caustic` 0.1, `waves` 0.4, `layering` 0.05, `edges` 0.1, `size` 0.35, `speed` 0.6, `minPixelRatio` 1, `maxPixelCount` 1 200 000, plus two sizing props this document did not anticipate: `scale` 1.6 and `offsetX` 0.08 / `offsetY` −0.2.

At the starting values the card read as the floor of a swimming pool, which is target 1's stated failure; three rounds of lowering `caustic`, `highlights` and `layering` cleared it. The two new props are what targets 1–4 and §12 actually needed:

- **The seam (target 4)** is not tiling. The fragment shader offsets the image's own UV by up to `0.1 × waves` and fills anything past the image edge with `colorBack`, which showed as two vertical bands down the card. `scale` crops in so the distortion never reaches the edge; 1.6 is seam-free at 1440×900, 1920×1080, 1024×768, 1440×700 and 390×844.
- **The title's contrast (§12)** was 2.9:1 at its worst pixel with the image centred, because the brightest Wet-paper thin spot sat under the word at every crop. The offsets move that spot out from under the title. Measured on the built screen with the type hidden: title 6.1:1 mean and 3.8:1 worst, tagline 5.8:1 / 4.6:1, cue 5.9:1 / 4.7:1.

The shader needs WebGL2. If `canvas.getContext("webgl2")` is null, render the pigment image as a static CSS background of the card instead and skip the shader; everything else (title, rinse mask, forest) works unchanged.

Tuning targets, judged from screenshots at 1440×900:

1. It reads as pigment on wet paper, not as the floor of a swimming pool. If a caustic net pattern dominates after tuning `caustic` and `highlights` down, take the fallback (§1): `Warp` with colours Pine, Viridian, Sap, Wet paper.
2. Movement is slow: two screenshots 2 s apart differ visibly but not dramatically.
3. Mean luminance is dark enough that the white title contrasts at 4.5:1 or better on the average pixel under it (measure with a canvas readback of a screenshot, or trust the pigment test in §6.2).
4. No visible tiling seam.

The shader mount is `aria-hidden`. Unmount it, or set `speed` to 0 and `visibility: hidden`, once the card has rinsed (p ≥ 0.85, §6.4) so that scrolling the list costs no GPU. Remount when the reader scrolls back above.

### 6.4 The rinse (scroll choreography)

`p` is the card wrapper's scroll progress from Motion: `useScroll({ target: wrapperRef, offset: ["start start", "end end"] })`, 0 with the wrapper's top at the viewport top, 1 with its bottom at the viewport bottom. All values below are driven from `p` with `useTransform`; they scrub in both directions. Keep the wrapper and every ancestor of the sticky card free of CSS transforms: Motion issue 3658 (open) breaks string offsets for a sticky element inside a transformed parent. If it bites anyway, use numeric offsets (`[0, 1]`) for this one call.

The rinse is a mask on the shader mount's wrapper that clears from the top down, with a soft edge. With edge position `e = clamp((p - 0.10) / 0.70, 0, 1)`:

```
mask-image: linear-gradient(to bottom,
  transparent calc(e * 124svh - 24svh),
  black       calc(e * 124svh))
```

(the 24svh feather starts above the card at e = 0 so nothing pops; at e = 1 the transparent stop is past the bottom). Compose the string with `useMotionTemplate`.

| p | What happens |
|---|---|
| 0.00–0.08 | Cue fades out (opacity 1 to 0). |
| 0.10–0.80 | The mask edge travels from the top of the card to the bottom. |
| 0.11–0.16 | Theme toggle icon colour: Paper to foreground (the edge passes the header first). |
| 0.40–0.52 | Tagline fades out, before the edge reaches it. |
| 0.46–0.54 | Title colour: Paper to foreground. The edge crosses the title's centre at p ≈ 0.49 (the title's centre sits at about 56 % of the card height: 0.10 + 0.70 × 0.56). Adjust these two numbers if the title block moves. In dark mode the title is foreground throughout; skip this crossfade. |
| 0.70–0.90 | Forest layer opacity 0 to 1. |
| 0.82–0.96 | Title translates up 4svh and fades to 0, so the clean card does not carry a stranded word into the list. |
| 0.85 | Shader paused (§6.3). |

Under reduced motion (§9): the mask edge still follows scroll (it is the reader's own action), but with the feather widened to 60svh so it reads as a crossfade; the title does not translate; the forest layer is simply visible.

**As built (2026-09-20, second pass): the edge is a waterline, it starts halfway up the card, and it uncovers the type rather than crossfading it.** The mask above is a horizontal line with a 24svh feather starting off the top of a fully wet card, which on the built screen read as a grey band sliding down a green rectangle. It is replaced by `lib/waterline.ts`, a pure curve sampled 73 times across the card and emitted as one path:

- **Shape.** Four drifting sine waves (amplitudes 0.032, 0.018, 0.0085, 0.0035 of the card's height; wavelengths 1.37, 0.53, 0.21, 0.083 of its width; none a multiple of another) plus five rivulets — narrow Gaussian channels, 0.09 to 0.21 of the card deep and 0.015 to 0.03 wide, steep on the leading side and trailing a tail — that run ahead of the front and cut down through the pigment. Rivulets fade in and out with `sin(π·e)`, so the opening line is waves only. Every vertical amplitude is scaled by `clamp(aspect / 1.6, 0.5, 1)`: heights are fractions of the card's height and widths fractions of its width, so on a phone the same numbers would draw icicles. The floor is not the aspect maths — below it a phone's line goes flat, which is the thing the curve exists to avoid.
- **Where it starts.** `front = 0.5 + 0.78 e`, so the card arrives with its top half already drained and the last of the pigment leaves a quarter-card below the bottom. The wordmark is therefore in ink from the first frame and never has the water over it, and the tagline is in white from the first frame and never has clean paper under it: the opening line runs between 43.8svh and 56.2svh, `.rinse-title` is capped so its box cannot pass 40.2svh, and `.rinse-tagline` starts at 60svh.
- **Where it goes.** One `<path>` closed downward is a `clipPath` over the wash; the same path closed upward is a `clipPath` over the ink copy of the block; the open curve is stroked twice, once at `min(w, h)/600` px for the meniscus and once at `min(w, h) × 0.05` px blurred for the diluted band under it, both in a new `--waterline` token (white; `#CFE8DE` in dark, at a lower opacity because a halo on a near-black sheet reads as a smudge).
- **Motion.** The four paths are written straight to the DOM from one rAF loop while the card is on screen, not through React. The loop stops with the shader at p ≥ 0.85 and never runs under reduced motion, where the line is still and the reader's own scrolling is the only thing that moves it. Measured 60.3 fps on the scroll probe, against 59.3 for the straight mask.

**The crossfades are gone with it.** The block is drawn twice in the same place, white underneath and `--foreground` on top, and the waterline clips the ink copy to the part of the sheet it has already cleaned. The water uncovers the tagline line by line instead of a colour ramp taking it through mid-grey, so the two numbers §6.4 invited an adjustment to no longer exist, and neither does the 2.0–2.5:1 moment they produced. Ink is on top rather than white so that the antialiased edge that shows through is white on pale paper, not dark on green.

The table above reduces to three rows: the cue clears over p 0–0.08, the forest arrives over 0.70–0.90, and the block leaves over 0.82–0.96. The tagline's fade is gone — the water takes it, around p 0.19 to 0.30 — and so is the toggle's crossfade: the top of the card is clean from the first frame, so the toggle is `--foreground` throughout and its focus ring no longer needs the white outline that made it legible on the pigment.

### 6.5 The header

The menu screen's header is only the theme toggle, `position: fixed`, 16 px from the top and right, ghost icon button as now. Its icon colour follows the crossfade in the table. There is no small wordmark on the menu: the title is the wordmark, and a link to the menu from the menu is pointless. The analysis screen's header keeps its wordmark (§4.2).

### 6.6 Load choreography

Runs once, after `document.fonts.ready` resolves for the italic Literata face (until then the title is invisible and the shader is already moving). Times from that moment.

| t | Element | Animation |
|---|---|---|
| 0 ms + 70 ms × i | Letter i of "rinse" (i = 0…4), each an `inline-block` span, `aria-hidden` inside an `h1` whose accessible name is set once with `aria-label="rinse"` | opacity 0 to 1; `translateY` 0.4em to 0; `filter: blur(10px)` to `blur(0)`; 900 ms; `cubic-bezier(0.2, 0.7, 0.2, 1)` |
| 0–1400 ms | Title (should, not must) | An SVG `feTurbulence` + `feDisplacementMap` filter on the `h1`, displacement scale 28 to 0, ease-out. The letters ripple as if seen through water, then settle crisp. Drop it if it stutters below 50 fps in the headless probe or renders wrongly. |
| 700 ms | Tagline | opacity 0 to 1; `translateY` 0.3em to 0; 600 ms; same easing |
| 1400 ms | Cue | opacity 0 to 1; 400 ms |

Total under 2 s. Nothing loops. Under reduced motion every element is at its final state on first paint and the shader runs at `speed` 0 with a fixed `frame` so the wash is still visible.

### 6.7 Copy

- Title: `rinse`
- Tagline: `Every environmental claim in a corporate text, rinsed down to its evidence.`
- Cue: `Choose a document`
- The current intro sentence at the top of the menu is removed; the tagline replaces it.

## 7. The forest

### 7.1 Layer and placement

A single fixed SVG covering the viewport (`viewBox` = `0 0 W H` in CSS pixels, updated on resize), behind the content (§4.3), `aria-hidden`, `pointer-events: none`. Trees are generated once in a unit space (root at the origin, height 1, y up) from fixed seeds, so the forest is identical on every load and screenshots are reproducible. Each tree is placed with `transform="translate(rootX, H) scale(S, -S)"` where `S` = its height in pixels; strokes use `vector-effect: non-scaling-stroke` so widths stay in pixels. **As built: not `vector-effect`** — in Chromium it makes dashes screen-measured, `pathLength` stops normalising them, and every limb renders fully drawn whatever the offset (verified: forcing `stroke-dashoffset: 1` inline changes nothing with it on, and hides the limb with it off). `forest.tsx` divides each width by the tree's own scale instead, which is uniform in magnitude, so a limb is still exactly that many CSS pixels wide. The JS fallback §7.3 offers would not have helped: the cause is the unit the dash is measured in, not where the number comes from.

| Tree | Seed | Root x (% of viewport width) | Height (% of viewport height) | Max depth | Lean | Shown at |
|---|---|---|---|---|---|---|
| T1 | 11 | 9 | 92 | 6 | +4° toward centre | ≥ 1024 px |
| T2 | 23 | 91 | 85 | 6 | −3° toward centre | ≥ 640 px (at < 1024: root x 92, height 80); the only tree below 640 (root x 88, height 70) |
| T3 | 37 | 22 | 60 | 5 | 0° | ≥ 1024 px |
| T4 | 41 | 78 | 68 | 5 | 0° | ≥ 1024 px |
| T5 | 59 | 50 | 46 | 4 | 0° | ≥ 640 px (a sapling behind the sheet, seen above and between sections) |

### 7.2 Generator (`lib/forest.ts`, pure, tested)

`generateTree(seed, { maxDepth, lean }): Tree` with a mulberry32 PRNG. Unit space, height 1.

- Trunk: length 0.30, angle 90° + lean, width 9 px.
- A branch is a quadratic Bézier from its origin along its angle for its length, with the control point at the midpoint pushed perpendicular by 6–14 % of the length; the sign alternates with depth and is jittered.
- Children per branch: 2 with probability 0.65, else 3. Child angle = parent angle ± spread, spread 24° ± 9°, the third child near 0° offset; every child is nudged 2° toward vertical (phototropism). Child length = parent × (0.68 ± 0.07). Child width = parent × 0.62. Children attach at the parent's end, except at depths 0 and 1 where one child attaches at 60–85 % along the parent (a side limb).
- Stop at `maxDepth` or when length < 0.012. From depth 3 on, a branch ends early with probability 0.12.
- Leaves: on branches at depth ≥ `maxDepth − 1`, one to three leaves at the end and along the last 40 %. **As built: on the tips** — a branch at that depth that has stopped forking. Leaving them on every branch at that depth puts 310 leaves on T2, over this section's own 300-leaf assertion and twice its budget of roughly 150; on the tips the five trees carry 81–193 each. A leaf is also emitted as a closed path whose six jittered points are smoothed through their edge midpoints: as a raw polygon it reads as a crystal, not a blot. A leaf is a six-point blob polygon, radius 0.012–0.020 jittered ± 25 %, random rotation. Colour Sap (70 %) or Viridian (30 %).
- Expected size: a depth-6 tree has roughly 250 branches and 150 leaves. Assert in tests that no tree exceeds 400 branches or 300 leaves and that all coordinates fall inside x ∈ [−0.7, 0.7], y ∈ [0, 1.05].

Growth windows, in tree-progress units `g ∈ [0, 1]`:

- `spanByDepth = [0.16, 0.12, 0.09, 0.07, 0.06, 0.05, 0.05]`.
- Trunk `birth = 0`. A child's `birth = parent.birth + parent.span × attachT − 0.15 × parent.span`, clamped to ≥ `parent.birth`, where `attachT` is 1 for end-attached children. The overlap keeps growth continuous.
- A leaf's `birth = branch.birth + 0.9 × branch.span`, `span = 0.06`.
- Normalise every `birth` and `span` by the largest `birth + span` so the last leaf ends at exactly 1. Test: windows are monotone in depth along any path from the trunk, and the maximum end is 1.

### 7.3 Driving growth from scroll

`f` is the content section's scroll progress: `useScroll({ target: contentRef, offset: ["start end", "end end"] })`, 0 when the section's top enters at the bottom of the viewport, 1 at the end of the page.

Per-tree windows on `f`: start `[0.00, 0.06, 0.12, 0.04, 0.10]`, end `[0.82, 0.90, 0.96, 0.86, 0.92]` for T1–T5; `g_i = clamp((f − start_i) / (end_i − start_i), 0, 1)`.

Do not create a motion value per path. Set one CSS custom property per tree, `--g`, on the tree's group each frame (`useMotionValueEvent(f, "change", …)`), and let CSS derive every element:

```css
.branch {
  fill: none;
  stroke: var(--ink);
  stroke-opacity: 0.55;
  stroke-linecap: round;
  vector-effect: non-scaling-stroke;
  stroke-dasharray: 1;                       /* paths carry pathLength="1" */
  stroke-dashoffset: clamp(0, 1 - (var(--g) - var(--b)) / var(--s), 1);
}
.leaf {
  fill: var(--sap);
  fill-opacity: 0.72;
  mix-blend-mode: multiply;                  /* overlapping leaves darken like wet pigment */
  transform-box: fill-box;
  transform-origin: center;
  transform: scale(clamp(0, (var(--g) - var(--b)) / var(--s), 1));
  transition: transform 220ms cubic-bezier(0.34, 1.56, 0.64, 1);   /* a small pop */
}
```

Each element carries its own `--b` (birth) and `--s` (span) as inline style. Verify in Chromium that number-valued `clamp()` works on `stroke-dashoffset`; if not, fall back to setting `stroke-dashoffset` from JavaScript in one batched loop per frame.

Branch width per depth as a `stroke-width` attribute in pixels (9 × 0.62^depth, minimum 0.8). The 0.55 stroke opacity keeps headings and labels legible over branches; leaves at 0.72 with multiply. In dark mode: stroke `--ink` at 0.45, leaves `--sap` (dark value) at 0.8 with `mix-blend-mode: normal` (multiply vanishes on a dark page).

### 7.4 Sway

When a tree's `g` reaches 1, start a Motion `animate` on its inner group: `rotate` between −0.5° and +0.5° around the root, `duration` 7 s ± 1.5 s (seeded per tree), `repeat: Infinity`, `repeatType: "mirror"`, `ease: "easeInOut"`. Stop and reset it when `g` drops below 1. The structure is an outer `<g>` for placement and an inner `<g class="sway">` with `transform-origin: 0 0`, so the rotation composes with the placement transform. No sway under reduced motion.

## 8. The list, the form, recent

- Page background under the content: Rinsed paper. The documents `ul` stays a Paper sheet with the hairline border. Rows, copy, meta line, "Analyse" and "Analyse live" buttons, the recording length line, the pace control, the invalid-recordings note: unchanged.
- "Your own text": unchanged, fields on Paper. "Recent": unchanged.
- No entrance animations on any of these. They do not fade or slide in. The forest is the motion here.
- Headings keep 22 px / 500 Public Sans. No eyebrows, no numbering, no dividers beyond the existing hairlines.

## 9. Motion inventory and reduced motion

| Motion | Trigger | Reduced motion |
|---|---|---|
| Shader movement | always, on the card | `speed` 0, fixed `frame` |
| Title letters rise and unblur; ripple; tagline; cue | fonts ready, once | all at final state |
| The rinse (mask edge, title colour, tagline and cue fades, title exit) | scroll, scrubbed | mask becomes a wide crossfade; no translate |
| Forest growth, leaf pop | scroll, scrubbed | trees fully grown from first paint; no transition |
| Sway | tree fully grown | none |
| Lenis smoothing | wheel/touch | disabled |
| Existing button and focus transitions | interaction | as now |

Detect with Motion's `useReducedMotion()` and the CSS media query; both paths must render the same content.

## 10. Dark mode

Mechanical, using the dark column of §4.1. The card's "paper" that the wash rinses down to is the theme background (`var(--background)`), so in dark mode the pigment rinses to dark slate, the title stays foreground colour throughout, and the sheet edge uses the dark border. The pigment set is lifted (Pine `#175C50`, Wet paper `#35524A`) so the wash is visible against the dark page. Take dark screenshots at the same scroll positions as light (§14).

## 11. Responsive

- ≥ 1024: five trees; title 22vw capped at 360 px.
- 640–1023: T2 and T5; title 22vw.
- < 640: T2 only; title 96 px; tagline 24 px wrapping to three lines; the pace control wraps under the heading as now; the fixed header keeps 16 px insets.
- Use `svh` units throughout the card so the mobile URL bar does not resize the sticky card. No horizontal scroll at 390 px.

## 12. Accessibility

- The `h1` is "rinse"; the tagline is a `p`. The shader mount, the mask wrapper and the forest SVG are `aria-hidden="true"`.
- Contrast: white title on the wash ≥ 3:1 everywhere (large text) and ≥ 4.5:1 on average (§6.3); tagline ≥ 3:1 (24 px counts as large); after the rinse, foreground on background as before. Ink on Rinsed paper is 12:1.
- Keyboard: the theme toggle is the first tab stop, then the pace control and the row buttons as now. Focus rings stay Marker and remain visible over the wash (the toggle sits on pigment; a 3 px Marker ring on Pine is visible; check it in a screenshot).
- Reduced motion per §9.

## 13. Performance budget

- Added JavaScript ≤ 100 kB gzipped (paper shaders 81, lenis 5, the rest is code).
- The shader: one fullscreen fragment pass at `maxPixelCount` 1 200 000, `minPixelRatio` 1; paused after the rinse.
- The forest: one CSS variable write per tree per frame; about 900 branch paths and 600 leaves on desktop, all styled by CSS. If the headless probe shows under 50 fps while scrolling, cut T3 and T4 to depth 4 before anything else.
- Target: 60 fps on this Mac; 45 fps or better on an integrated-GPU laptop at DPR 1.
- Measure with a snap.mjs step that scrolls the page in 20 steps over 2 s while counting `requestAnimationFrame` callbacks, and report the number.

## 14. Implementation plan and checks

Work in this order. After each step take the listed screenshots, look at them, and fix what is wrong before moving on. Report to Chris with the final screenshots.

1. **Rename.** Wordmark text and styling (§4.2), `index.html` title, README and design-plan references. Screenshot: analysis header at 1440 wide.
2. **Fonts and tokens.** Literata display and italic imports; menu tokens light and dark in `index.css` and `@theme inline`.
3. **Pigment image** (`lib/pigment.ts`) with a vitest that checks determinism by seed, mean luminance in [0.08, 0.14], and the light-pixel share (run under jsdom with a canvas fallback: if no canvas is available in the test runner, test the pure blob-placement and gradient maths and check the image once by screenshot).
4. **Title card, static.** Card wrapper and sticky card, shader mount with the pigment, title, tagline, cue, sheet edge, fixed header. Screenshots at 1440×900 light and dark, and 390×844. Check contrast of the title and tagline over the wash by sampling pixels under them from the screenshot; check §6.3's tuning targets; decide Water versus the Warp fallback here and record it.
5. **Load choreography** (§6.6). Screenshots at 200 ms, 800 ms and 2 s after load. Reduced-motion screenshot (add a `MOTION=reduce` environment switch to snap.mjs that emulates the media feature over the DevTools protocol; keep the change small and documented in the script's header).
6. **The rinse** (§6.4). Screenshots at p = 0.30, 0.50, 0.75, 0.95 by scrolling the window to `p × (wrapperHeight − viewportHeight)`. The title must be white above the edge and ink below it, with no state where it is unreadable for more than a few percent of p.
7. **Forest generator** (`lib/forest.ts`) with vitests for determinism, counts, bounds and window monotonicity.
8. **Forest layer** (§7.1, §7.3). Screenshots at f = 0.25, 0.60, 1.00 at 1440×900 light and dark, 1024×768, and 390×844. Check: growth order reads trunk to twig to leaf; leaves are green blots, not dots; text over branches is legible; the sheet hides nothing important.
9. **Sway** and the shader pause; Lenis on the menu only: wrap the menu screen in `ReactLenis` from `lenis/react` with `root` and `options={{ anchors: true }}`, import `lenis/dist/lenis.css`, and do not mount it under reduced motion (Lenis 1.3.26 also forces its interpolation to 1 under the media query on its own). It scrolls the native document, so `position: sticky` and Motion's `useScroll` keep working. Never on the analysis screen, which has its own scroll containers.
10. **Performance probe** (§13) and the phone pass (§11).
11. **Gates** (§0), then docs (§3).

Tests are for the pure modules (`pigment.ts`, `forest.ts`, `menu-scroll.ts` mapping functions from p and f to the values in §6.4 and §7.3). Do not test visuals in vitest; the screenshots are the visual check.

## 15. Acceptance checklist

- [ ] The name is "rinse" everywhere in the interface, README and design plan; "Greenwashing Auditor" appears nowhere in the UI.
- [ ] First paint: a moving green pigment wash with a white italic "rinse" that surfaces letter by letter; tagline and cue follow; done under 2 s; nothing loops except the wash and, later, the sway.
- [ ] Scrolling rinses the pigment from the top down; the word turns to ink as the edge passes; the list emerges from under the card; no dead viewport of blank paper longer than about 15 % of the wrapper.
- [ ] Trees draw in growth order as the reader scrolls, leaves bloom last in Sap and Viridian; scrolling back ungrows them; grown trees sway gently.
- [ ] The document list, pace control, own-text form and recent list work exactly as before, and the demo document's expected verdict is never shown.
- [ ] Dark mode, 390 px width, reduced motion, and keyboard focus all checked by screenshot.
- [ ] Bundle within budget; scroll probe ≥ 50 fps in headless on this Mac.
- [ ] Prettier, typecheck, lint, tests and build clean; nothing committed; backend, contract and fixtures untouched.

## 16. Do not

These are the tells that would turn this screen into the generic version of itself. None of them is allowed, even if it seems like an improvement:

- A leaf, sprout, globe or recycling icon anywhere. No icon next to the title.
- Neon or acid green; green on near-black; gradient text; glows; glassmorphism panels; a mesh-gradient or aurora preset used as shipped.
- A bouncing chevron, an arrow, or "Scroll" as the cue. The cue is the words "Choose a document" and the sheet edge.
- Centred hero layout. Everything sits on the left content axis.
- Entrance animations on the list, the form or the headings; hover lifts on rows; cards with drop shadows.
- Uppercase eyebrow labels, numbered section markers, middle-dot meta strings, monospace labels, a typewriter effect, a cursor-follow effect, particles or sparkles.
- Changing the interactive accent (Marker) to green, or recolouring the analysis screen.
- Adding GSAP, three.js, React Three Fiber, Rive, Lottie, tsParticles, Vanta, Spline or Unicorn Studio.
- Copy that sells ("AI-powered", "next-generation", "trusted by"). The tagline is the only sentence on the card.
- Drifting into the "cream, serif and sage" look, which a 2026 survey of design forums names as the new tasteful default. Paper stays pure white, never cream; the greens stay saturated pigment (Viridian, Pine, Sap), never sage or mint; the serif appears only in the wordmark and, as now, in document titles. Every other word on the screen is Public Sans.

## 17. Why these choices

- **Green as pigment, not light.** The name is about washing green off. Pigment on paper is a material with a reason to move (water) and to disappear (rinsing). Light-green gradients and glows are the default eco look and carry no meaning here.
- **White title that turns to ink.** Ink on dense pigment fails contrast (2.8:1). Making the word white on the wash and letting it become ink as the water passes turns a constraint into the moment: the word is revealed in its true colour when the green is gone.
- **Scroll-driven rinse, not a timed one.** The reader owns it, can scrub it back, and a presenter can hold any state on stage. It also means the page never plays a movie at someone who has already seen it.
- **Left-aligned on the content axis.** The title, tagline, cue and "Documents" heading share one x. The card and the list are one page, not a hero bolted onto a form. Centred heroes are the default.
- **Literata italic wordmark.** It is the voice of the honest rewrite in the application, so the name reads as "the honest version". One typeface borrowed once, on purpose.
- **Ink-drawn trees with green only in the leaves.** Structure before colour is the auditor's order of work: draw what is there, then colour only what the evidence supports. Line drawing sits naturally with the Literata document pane and the ink and paper palette; a textured 3D tree next to a typeset list would read as two products.
- **Seeded, deterministic forest.** A demo has to look the same on every load and in every screenshot; the visual check depends on it.
- **CSS variables drive 1 500 elements.** One write per tree per frame instead of a motion value per path keeps scrolling smooth without a WebGL renderer for the trees.
- **No entrance animation below the card.** The card and the forest are one continuous moment. A second set of fades would compete with it and is the most recognisable generated-page habit.
- **A 200svh wrapper.** Long enough to make the rinse feel like a gesture, short enough that the clean card does not become a blank scroll before the list arrives.

## 18. Library facts behind the plan (verified 2026-09-20)

- `@react-three/fiber` 9.7.0 pins `react >=19 <19.3`; the frontend has React 19.3.0; `npm install` fails with ERESOLVE and forcing it hits an open crash (issue 3915). Plain `three` 0.186 works, and the installed `motion` 13.4 ships `motion/three` (`threeEffect`) to bind motion values to uniforms. Not used here because no library grows a tree from a progress value: `@dgreenheck/ez-tree` 1.1.0 (MIT) is the best generator but static, with about 3 MB of embedded textures; growth would be custom vertex work.
- `@paper-design/shaders-react` 0.0.81: Apache-2.0, 81 kB gzipped, no three.js or ogl dependency, peer React ^18 || ^19; 30 effects, of which `Water`, `FlutedGlass`, `LensDistortion`, `LiquidMetal`, `PaperTexture` and others accept an `image`.
- `gsap` 3.15.0 ships every plugin (SplitText, ScrollTrigger, DrawSVG, …) free under a proprietary no-charge licence. Not needed: Motion's free tier has `useScroll`, `useTransform`, `useSpring`, `useMotionValueEvent`, `useInView`, `useReducedMotion`, `animate`, `stagger`; it lacks `splitText`, which five letters do not need.
- `lenis` 1.3.26 (MIT, 5 kB) scrolls the native document, so Motion's `useScroll` and `position: sticky` keep working. Its React binding is `lenis/react` (`ReactLenis`, `useLenis`); anchors are blocked unless `anchors: true`; nested scrollables need `data-lenis-prevent`.
- Motion 13.4's `useScroll` runs on the browser's ScrollTimeline where the output feeds `opacity` or `transform` directly; a `mask-image` string built with `useMotionTemplate` goes through JavaScript, which is fine at one element. Open issue 3658: sticky element inside a transformed ancestor breaks string offsets.
- The 2026 sources on generated-looking pages agree on the tells: Tailwind and shadcn defaults left as shipped, blue-to-purple gradients, Inter, three feature cards, rounded-2xl on everything, glass cards, fade-in-from-below on scroll, and the newer "cream, serif and sage" palette. Mesh, blob and aurora backgrounds were not found to be a measured tell, but a library preset shipped unchanged is.
- Fluid simulations (`webgl-fluid` 0.4.0, MIT, updated 2026-05) exist and would give a literal dye-in-water rinse; not chosen because the fluid-cursor look is a recognised portfolio cliché and the mask-based rinse is cheaper and reads more clearly.
- Rive's community "Tree Demo" (CC BY 4.0) grows a tree from a number input; not chosen because it needs restyling by hand in the Rive editor and would be someone else's drawing.
- The headless screenshot tool renders with the Mac's GPU (WebGL2 via Metal, WebGPU present, about 60 fps), so every check in §14 is possible.

## 19. References: what premium green and water look like (2025–2026 award sites)

Verified 2026-09-20 by reading each site's bundles. None of these is to be copied; they show that deep green, water and foliage can read as premium when the saturation is low and there is one light source. Frames of each are in the research session's scratchpad under `shots/` and `aw/` if that directory still exists; otherwise open the sites.

| Site | What the hero does | Technique | Take from it |
|---|---|---|---|
| Springs, springs.estate (Awwwards site of the day and developer award, 2026) | Dark green field with a lime-to-teal haze; forest and rapids photos drift in perspective; water ripples on hover | three.js, shader materials, video textures, Rive for UI | A low-saturation deep green base with one lime light leak reads premium, not corny. Ripple on hover as the only interaction. |
| Craft, itscraft.com (honourable mention, 2026) | Near-black green; a translucent green membrane folds slowly under light | React Three Fiber with a transmission material | Proof that a single green hue under light reads as chlorophyll, not aurora. |
| Nature Beyond Technology, nature-beyond.tech (honourable mention, 2025) | Monochrome particle tree over a wireframe terrain; rain through foliage later | three.js, instanced leaves with wind noise, GSAP, Lenis | Restraint: one hue, data set like instruments. Suits an audit tool. |
| Explore Primland, explore.ownprimland.com (site of the day, 2026) | Aerial forest with rivers; cloud sprites drift over the canopy | three.js terrain, billboard clouds, video textures | The mist-over-green layer, if the wash ever needs more depth. |
| Farm Minerals, farmminerals.com/promo (site of the day and developer award, 2026) | Defocused foliage shadows in olive behind the product; plant growth on scroll | Webflow, GSAP, Lenis, Lottie, scroll-scrubbed video; no WebGL despite the tag | A well-graded blurred leaf-shadow layer beats a mediocre shader. |

The research also proposed, independently of this document, a hero in which an over-saturated "marketing green" grade rinses off a leaf photo in water to reveal the true colour underneath, built with the same Water shader and a scroll-driven mask. That is the same idea as §6, which is reassuring; this document keeps the generated pigment instead of a photograph so that the card owes nothing to stock imagery and stays reproducible.

What the research found generic in the same category: an orange droplet hero with AI-generated section videos (Greenlyte), cyan globes, and any site whose hero is a preset shader in the vendor's default colours.

## 20. As built (2026-09-20)

Built to this document with the changes recorded in §6.1, §6.3, §6.4, §7.1, §7.2 and below. Everything else is as specified. Nothing was committed; `contract/`, `backend/`, `fixtures/` and `demo-documents/` were not touched.

**Changed against the specification, with the reason:**

| Where | Specified | Built | Why |
|---|---|---|---|
| §6.3 | `Water` with the starting values | `scale` 1.6, `offsetX` 0.08, `offsetY` −0.2 added | Target 4 (no seam) and §12's 3:1 floor under the title, both measured |
| §7.1 | `vector-effect: non-scaling-stroke` | width ÷ the tree's scale | `vector-effect` breaks `pathLength`-normalised dashes in Chromium, so nothing draws on |
| §7.2, §7.3 | leaves on every branch at depth ≥ maxDepth−1; `fill-opacity` 0.72 | leaves on tips only, smoothed outline, `fill-opacity` 0.42 | 310 leaves broke this document's own 300 cap; hard hexagons at 0.72 multiply to black wherever the canopy is dense, which stops reading as green |
| §4.1 | type on the wash is Paper | type on the wash is `#ffffff` | Paper is dark slate in dark mode, which put dark type on dark green; the contrast maths in §4.1 is white |
| §6.1 | title block at 40svh, left in a centred column; `clamp(96px, 22vw, 360px)`; a 12 px sheet edge | wordmark centred in the clean half, `clamp(72px, min(14vw, 36svh), 210px)`; tagline at 60svh; no sheet edge | Reviewed on the built screen: the word ran edge to edge and the block read as off-centre, and the strip read as a divider over the image |
| §6.4 | a linear-gradient mask with a 24svh feather, from a fully wet card | a sampled waterline with waves and rivulets, starting halfway up the card | The straight edge read as a band sliding down a green rectangle, not as water leaving a sheet; opening with the wordmark already clear of the water was the client's call |
| §6.4 | title colour crossfades Paper to foreground over p 0.46–0.54; toggle over 0.11–0.16 | the block drawn twice and the waterline clipping the ink copy; the toggle is foreground throughout | The crossfade took the whole word through mid-grey; the water now uncovers it, and the top of the card is clean from the first frame |
| §6.4 | tagline fades out over p 0.40–0.52 | the water takes it, around p 0.19–0.30 | It sits under the opening waterline now, so it is white on the wash and then ink on paper, like the wordmark |

**Added, not specified:** `src/lib/waterline.ts`, the curve above, pure and tested; and `src/lib/random.ts`, seven lines holding the mulberry32 the pigment and the forest share, so the two do not each carry a copy of an algorithm that has to match. And a white outline outside the toggle's focus ring on this screen only: Marker against the wash is 1.29:1 by luminance — visible by hue, not by contrast — and the white reads at 10.3:1. The ring keeps its Marker colour, per §4.1.

**Measured on the built screen:**

| Check | Target | Measured |
|---|---|---|
| Pigment mean luminance (§6.2) | 0.08–0.14 | 0.0822 |
| Pigment pixels lighter than Sap (§6.2) | < 15 % | 0.18 % |
| White title on the wash (§12) | ≥ 3:1 everywhere, ≥ 4.5:1 mean | 3.8:1 worst pixel, 6.1:1 mean |
| Tagline, cue on the wash | ≥ 3:1 | 4.6:1, 4.7:1 worst |
| Wash movement over 2 s (§6.3) | visible, not dramatic | 22 % of pixels changed, mean ΔL 0.015 |
| Scroll probe, 20 steps over 2 s (§13) | ≥ 50 fps | 59.3 fps; 60.3 fps with the waterline |
| Added JavaScript (§13) | ≤ 100 kB gzipped | 63.0 kB gzipped (CSS +1.2 kB) |
| Forest elements (§13) | ~900 branches, ~600 leaves | 623 branches, 678 leaves |
| Phone at 390 px (§11) | no horizontal scroll | 0 px |
| Shader pause (§6.3) | stops at p ≥ 0.85 | visible at 0.84, hidden at 0.86, resumes on the way back |
| Tab order (§12) | toggle, pace, rows | toggle, pace 1×/4×/10×/Instant, rows |

**One thing worth a second opinion, as specified:**

- Dark mode leaves are Sap `#7FA845` at 0.8 on a `#161D1A` page, straight from §4.1 and §7.3. That is bright green on near-black, which §16 lists as a tell. The dark column is explicit and §10 says dark is mechanical, so it was built as written.

**Not done, out of scope:** `design-doc.md` and `roadmap.md` still carry the old name in their titles. §15 names the interface, the README and the design plan, all of which are renamed.

