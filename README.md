# Greenwashing Auditor

HackMIT 2026. Reads a public corporate text, highlights each environmental claim, and shows
the verdict, the evidence and the confidence behind it. Design in `design-doc.md`, plan in
`roadmap.md`, visual direction in `design-plan.md`, hand analysis of the demo document in
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
the demo documents with their recorded analyses; press Analyse on one and watch events arrive
in the panel at the bottom. Each analysis has its own address (`/a/<id>`), so reloading or
sharing the link keeps it. The backtick key toggles the events panel; `d` toggles dark mode.

## Layout

| Path | What |
|---|---|
| `backend/` | API, event store, replay, and where the pipeline plugs in. `backend/README.md`. |
| `frontend/` | The interface. `frontend/README.md`. |
| `contract/` | The data contract: `schema.json` and the tooling that builds, validates and folds event logs. |
| `fixtures/` | Event logs the app can replay, and the envelope rules (`fixtures/README.md`). |
| `demo-documents/` | The demo texts, verbatim, with retrieval notes. |

## Checks

```sh
cd backend && .venv/bin/python -m pytest
cd frontend && npm run typecheck && npm run lint && npm run build && npm test
backend/.venv/bin/python contract/tools/contract.py validate fixtures/shell-climate.jsonl --analysis fixtures/shell-climate.analysis.json
```
