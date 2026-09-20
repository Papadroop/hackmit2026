# rinse — the demo

*Roadmap step 20. The run of show, what to say, and what to do when something breaks. The
narrative is design-doc D2's three zoom levels: **open a document, click into one claim, zoom
out to the company.** Two minutes if you are cut short, five if you are not.*

Last updated: 2026-09-20

## The one-sentence claim

Greenwashing is the gap between the impression a page gives and what its evidence supports
(D3), and this tool measures that gap claim by claim, shows its working, and has been scored
against 24 real regulatory rulings so you can say how often it is right.

## Before you present

Run these in order. The whole point of the rehearsal is that none of them touch the network.

```sh
cd backend && .venv/bin/python -m pytest -q          # 333 passing
cd ../frontend && npm run build                       # writes frontend/dist
cd ../backend && .venv/bin/python -m uvicorn auditor.main:app --port 8400
```

The backend serves `frontend/dist` when it exists, so the demo is one process on
**http://localhost:8400**. Ports 8000 and 5173 belong to another project on the dev machine;
8400 and 5174 are ours.

Then, with the wifi **off**, check all four:

| Check | What you should see |
|---|---|
| `http://localhost:8400/` | Four documents; **the two Shell ones have "Replay"** |
| Replay **Our climate target** | Highlights settle from grey to colour; the header fills |
| `http://localhost:8400/c/shell-plc` | Two Shell documents and a trend |
| `http://localhost:8400/calibration` | The precedent plot, precision and recall |

If any of those needs the network, you have a live analysis selected somewhere instead of a
replay. **Replay is the demo. A live run is the encore, and only with wifi.**

**Apple and Ørsted have no recording.** Their rows offer "Analyse", which is a live run and
needs the network and API credit. With the wifi off they will fail, so do not click them. The
narrative only needs Shell; the other two are there to show the tool is not hard-wired to one
page, and you can say that without opening them.

## The run of show

### 1. Open a document (60 s)

Start on the menu. The first screen is documents, not features — the product is called *rinse*
because the name is about washing green off, and the title card does exactly that as you
scroll. Do not narrate the animation; scroll past it.

Pick **Shell, "Our climate target" (14 March 2024)** and press Replay.

> "This is Shell's climate page as it stood in March 2024, pulled from the Wayback Machine.
> What you are about to watch is a recording of the tool reading it — every stage really ran,
> nothing here is hand-written."

That sentence is true of **this** document and you should only say it here. The other Shell
recording, the 2026 "Climate" page, is our hand-written reference analysis: it is what we
measure the tool against, and it is labelled as such in `fixtures/README.md`. If you open that
one, say so.

Let it run and say what is landing while it lands:

- claims light up in the text as they are found — 27 of them;
- thin grey underlines appear under hedges and vague words: that is the language layer;
- each highlight **settles from grey into a verdict colour** as the evidence arrives.

The colour is the category, the strength of the colour is the confidence, and the underline
style repeats the category so it survives colour-blindness. Say that once, then stop.

### 2. Click into one claim (90 s)

Click **C4**:

> **"This supports the more ambitious goal of the UN Paris Agreement: to limit the rise in
> average global temperature to 1.5°C."**

Verdict: **contradicted**. This is the demo's best moment, so slow down. The panel reads like a
ruling, top to bottom: the statement at issue, the verdict and confidence, the reasoning, then
the evidence, then the fix and an honest rewrite.

The thing to point at is the evidence:

> "The sentence is not false. Shell can say it supports 1.5°C. What the tool found is that the
> Transition Pathway Initiative scores Shell's own intensity targets as implying more than 2°C.
> The claim and the evidence point in opposite directions, and the tool went and got the
> evidence."

Every quote on screen was checked against the page it came from before it was allowed to
render — if it does not verify, it never appears. Say that once.

Two more beats, if there is time:

- **Tiers.** Evidence carries a reliability tier: an assured annual report outranks a press
  release. The tier is derived from what the source *is*, never chosen by the model.
- **Derived, not judged.** The likelihood is the worst of the four dimensions, not an average,
  so three confident readings of things that are not the problem cannot drown the one that is.
  A prosecutor and a defence argue each claim and a judge decides, but the judge does not set
  the number.

### 3. Turn on Omissions (45 s)

The top finding on this page is not something it says, it is something it does not:

> **"Not mentioned: Shell has since retired its 2035 intensity target and weakened its 2030
> goal."**

Toggle **Omissions**. Eleven cards appear on the desk above the sheet: no absolute Scope 3
tonnage, no production trajectory, no capital-expenditure split.

> "Each card names the disclosure topic, why it is material for this industry, and the nearest
> thing the page does say. 'Not mentioned' is a claim about the text, so it has to be
> answerable — and it is, because we quote what the page has instead."

### 4. Zoom out to the company (45 s)

Click **Shell plc** in the header. This is D2's third level, and it is a by-product: verifying
a claim already means gathering company-level evidence.

> "Two documents: the March 2024 page we just read, and the version that replaced it."

Point at the trend line and at the sentence under it:

> "It says +0.10, getting worse — and then it says *two documents 919 days apart is a step, not
> a trend*. Confidence 0.35. That sentence is the product."

### 5. "Is this just a language model with opinions?" (60 s)

Go to **Calibration** (from the menu, or `/calibration`).

> "Every precedent we curated is also a test. We take the ruling out of the knowledge store,
> score the wording the regulator actually ruled on, and compare. Twenty-four cases, none
> allowed to see its own answer."

> "Precision 84%, recall 94%. And then the caveat the report writes itself: only three of the
> twenty adjudicated cases went the advertiser's way, so precision rests on too few negatives
> to mean much, and the calibration curve is the number to read."

Drag the threshold line. The four regions are the confusion matrix, and the marks that change
colour are the cases where the tool and the regulator disagree.

> "The scale runs 0 to 1 but nothing scored below 0.50, so the bottom half is empty. On this
> set we separate claims by how strongly we doubt them, not by whether we doubt them at all.
> That is a real weakness and it is on the page rather than in a footnote."

## Questions you should expect

**"Did you tune it to get those numbers?"** No. Three negatives cannot support tuning — that
would be fitting noise. The three misses are written up instead: the ASA cleared Shell's
investment-split ad *because* the 68/23/9 split was on screen, and the audit, with that ruling
held out, did not get there from the criteria alone. That one is a genuine weakness. The Apple
case was dismissed on a US pleading standard, so it is arguably mislabelled ground truth.

**"What stops it hallucinating evidence?"** Citation integrity, and it is enforced in the fold
rather than the view: a quote that does not verify against its source never reaches any screen.

**"Why does the company number not go down when a company improves?"** Because the headline
says what the worst of the record is and the trend says which way it is moving; one number
cannot do both. An older bad page ages out of the weighting over about two years.

**"Can it run on something we give you?"** Yes — paste text or a URL on the menu. **Only do
this with wifi on, and only if you have three minutes to spare.** It is a genuinely live run:
web search, archive lookups, a prosecutor and a defence per claim.

## If something breaks

- **A replay stalls.** Reload the page; the address is the analysis, so it resumes from the
  server's log.
- **A document will not open.** Use another. Shell is the only one the narrative needs.
- **The company page shows one document.** A Shell recording is missing from `fixtures/`.
  Carry on — the trend sentence degrades honestly to "not enough to say", which is itself a
  fair thing to show.
- **Everything is on fire.** `fixtures/shell-climate.jsonl` is the hand-authored reference and
  replays without any of the rest. Show that and talk over it — but say it is the reference,
  not a run.

## What not to do

- Do not start a live run to fill time. It takes minutes and needs the network.
- Do not open the events panel unless asked. It is there for the "show me it is real" question,
  not for the tour.
- Do not claim the tool is a regulator. It is an instrument an analyst uses to defend a
  finding, which is exactly who it was designed for.
