# rinse

HackMIT 2026. Reads a public corporate text, highlights each environmental claim, and shows
the verdict, the evidence and the confidence behind it. The name is what it does: the green
comes off, and what is left is the evidence. Design in `design-doc.md`, plan in
`roadmap.md`, visual direction in `design-plan.md` and `menu-design.md`, hand analysis of the demo document in
`golden-reference.md`.

## Run the skeleton

Two processes. Ports 8000 and 5173 are taken by another project on the dev machine.

```sh
# API (FastAPI), port 8400
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m uvicorn auditor.main:app --port 8400 --reload

# Frontend (Vite), port 5174, proxies /api to the API
cd frontend
npm install
npm run dev
```

Open http://localhost:5174 (not 127.0.0.1: Vite binds to the IPv6 localhost). The menu lists
the demo documents with their recorded analyses; press Analyse on one and watch the claims
light up as the verdicts land. An analysis is a case file with four sections — the claims in
the document, what it leaves out, the corrected version and the verdict — and each has its own
address (`/a/<id>/verdict`), so reloading or sharing a link keeps the place. Keys 1 to 4 open
the sections; `d` toggles dark mode. The raw event log is at `GET /api/analyses/<id>/log`.

## Layout

| Path | What |
|---|---|
| `backend/` | API, event store, replay, and where the pipeline plugs in. `backend/README.md`. |
| `frontend/` | The interface. `frontend/README.md`. |
| `contract/` | The data contract: `schema.json` and the tooling that builds, validates and folds event logs. |
| `fixtures/` | Event logs the app can replay, and the envelope rules (`fixtures/README.md`). |
| `demo-documents/` | The demo texts, verbatim, with retrieval notes. |
| `demo.md` | The run of show: what to say, in what order, and what to do when something breaks. |

## Credits

The menu's background is "Aerial view of the Amazon Rainforest" by lubasi, [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0), from [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Aerial_view_of_the_Amazon_Rainforest.jpg), stored at `frontend/public/canopy.jpg`. The attribution is on the page, at the foot of the document list. Everything else in the interface is drawn in code.

## Checks

```sh
cd backend && .venv/bin/python -m pytest
cd frontend && npm run typecheck && npm run lint && npm run build && npm test
backend/.venv/bin/python contract/tools/contract.py validate fixtures/shell-climate.jsonl --analysis fixtures/shell-climate.analysis.json
```
