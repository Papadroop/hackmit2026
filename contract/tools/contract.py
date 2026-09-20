#!/usr/bin/env python3
"""Contract tool: resolve spans, build an event log, validate, fold.

Usage:
  contract.py resolve  <analysis.json> [--write]        fill start/end on every span from text/context/occurrence
  contract.py build    <analysis.json> <events.jsonl>   analysis -> event log with fixture timing
  contract.py validate <events.jsonl> [--analysis analysis.json]
                                                        envelope + payload schema + ordering invariants;
                                                        with --analysis, fold and compare (round trip)
  contract.py validate-analysis <analysis.json>         schema + spans + references + derivation rules
  contract.py fold     <events.jsonl> <out.json>        events -> Analysis object

Exit code 1 on any error; warnings do not fail. Requires jsonschema>=4 (contract/requirements.txt).
The envelope rules mirror backend/auditor/envelope.py and fixtures/README.md; keep them in step.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

try:
    from jsonschema import Draft7Validator, FormatChecker
except ImportError:  # pragma: no cover
    print("missing dependency: pip install -r contract/requirements.txt", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE.parent / "schema.json"
CONTRACT_VERSION = "1.0.0"

STAGES = ["ingest", "extract", "language", "substantiate", "verify", "consistency", "omissions", "verdict", "summary"]
STAGE_LABELS = {
    "ingest": "Reading the document",
    "extract": "Finding claims",
    "language": "Reading how claims are worded",
    "substantiate": "Checking criteria and precedents",
    "verify": "Gathering evidence and recomputing numbers",
    "consistency": "Comparing with the company's own statements",
    "omissions": "Looking for what is missing",
    "verdict": "Arguing and deciding",
    "summary": "Summarising",
}
EVALUATOR_STAGES = {"language", "substantiate", "verify", "consistency"}
DIMENSIONS = ["clarity", "support", "materiality", "consistency"]
DIM_STAGE = {"clarity": {"language"},
             "support": {"substantiate", "verify"},
             "materiality": {"verify"},
             "consistency": {"consistency"}}
TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


# ----------------------------------------------------------------------------- helpers

class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def finish(self, label: str) -> int:
        for w in self.warnings:
            print(f"WARN  {w}")
        for e in self.errors:
            print(f"ERROR {e}")
        print(f"{label}: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return 1 if self.errors else 0


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validator_for(defn: str) -> Draft7Validator:
    schema = load_schema()
    sub = {"$schema": schema["$schema"], "$ref": f"#/definitions/{defn}", "definitions": schema["definitions"]}
    return Draft7Validator(sub, format_checker=FormatChecker())


def schema_errors(v: Draft7Validator, obj: object) -> list[str]:
    out = []
    for err in sorted(v.iter_errors(obj), key=lambda e: list(e.path)):
        path = "/".join(str(p) for p in err.absolute_path) or "<root>"
        msg = err.message
        if len(msg) > 300:
            msg = msg[:300] + "..."
        out.append(f"{path}: {msg}")
    return out


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(obj: object, path: str) -> None:
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_all(hay: str, needle: str) -> list[int]:
    out, i = [], 0
    while True:
        j = hay.find(needle, i)
        if j < 0:
            return out
        out.append(j)
        i = j + 1


# ----------------------------------------------------------------------------- resolve

def resolve_span(text: str, span: dict, where: str, rep: Report) -> None:
    needle = span["text"]
    if "context" in span:
        ctx_hits = find_all(text, span["context"])
        if len(ctx_hits) != 1:
            rep.error(f"{where}: context must occur exactly once, found {len(ctx_hits)}: {span['context'][:60]!r}")
            return
        rel = span["context"].find(needle)
        if rel < 0:
            rep.error(f"{where}: text not inside its context: {needle[:60]!r}")
            return
        start = ctx_hits[0] + rel
    else:
        hits = find_all(text, needle)
        occ = span.get("occurrence")
        if occ is not None:
            if occ > len(hits):
                rep.error(f"{where}: occurrence {occ} requested but only {len(hits)} found: {needle[:60]!r}")
                return
            start = hits[occ - 1]
        else:
            if len(hits) == 0:
                rep.error(f"{where}: text not found in document: {needle[:60]!r}")
                return
            if len(hits) > 1:
                rep.error(f"{where}: text occurs {len(hits)} times; add `context` or `occurrence`: {needle[:60]!r}")
                return
            start = hits[0]
    span["start"], span["end"] = start, start + len(needle)


def all_spans(analysis: dict):
    for c in analysis["claims"]:
        for i, s in enumerate(c["spans"]):
            yield f"claim {c['id']} span[{i}]", s
    for sg in analysis["signals"]:
        for i, s in enumerate(sg["spans"]):
            yield f"signal {sg['id']} span[{i}]", s


def cmd_resolve(path: str, write: bool) -> int:
    rep = Report()
    a = load_json(path)
    text = a["document"]["text"]
    check_text(text, rep)
    for where, s in all_spans(a):
        resolve_span(text, s, where, rep)
    if not rep.errors and write:
        dump_json(a, path)
        print(f"wrote {path}")
    return rep.finish("resolve")


# ----------------------------------------------------------------------------- derivation rules (CONTRACT.md §6)

def derive_likelihood(scores: dict[str, dict]) -> float:
    return max(scores[d]["score"] for d in DIMENSIONS)


def derive_category(scores: dict[str, dict], has_contradicting_evidence: bool) -> str:
    S, C, K = scores["support"], scores["clarity"], scores["consistency"]
    if has_contradicting_evidence and ((S["score"] >= 0.7 and S["confidence"] >= 0.6) or
                                       (K["score"] >= 0.7 and K["confidence"] >= 0.6)):
        return "contradicted"
    if C["score"] >= 0.7:
        return "unsubstantiated"
    if 0.4 <= S["score"] <= 0.6 and S["confidence"] < 0.6:
        return "unsubstantiated"
    if derive_likelihood(scores) > 0.5:
        return "misleading_by_framing"
    return "supported"


# ----------------------------------------------------------------------------- analysis-level checks

def check_text(text: str, rep: Report) -> None:
    if unicodedata.normalize("NFC", text) != text:
        rep.error("document.text is not NFC-normalised")
    if "\r" in text:
        rep.error("document.text contains carriage returns")
    bad_ws = sorted({ch for ch in text if ch.isspace() and ch not in (" ", "\n")})
    if bad_ws:
        rep.error(f"document.text contains non-canonical whitespace {[hex(ord(c)) for c in bad_ws]}; normalise to ASCII space or \\n")
    if "  " in text:
        rep.error("document.text contains runs of spaces")
    if re.search(r" \n|\n ", text):
        rep.error("document.text has spaces at a line boundary")
    if "\n\n\n" in text or text != text.strip():
        rep.error("document.text has blank-line runs or leading/trailing whitespace")


def check_analysis(a: dict, rep: Report, strict_summary: bool = True) -> None:
    v = validator_for("Analysis")
    for e in schema_errors(v, a):
        rep.error(f"schema: {e}")
    if rep.errors:
        return  # structure is broken; the rest would be noise

    doc = a["document"]
    text = doc["text"]
    n = len(text)
    check_text(text, rep)
    if doc.get("word_count") is not None and doc["word_count"] != len(text.split()):
        rep.warn(f"document.word_count {doc['word_count']} != {len(text.split())} (len(text.split()))")

    # ids unique across every entity type
    ids: Counter[str] = Counter()
    for coll in ("claims", "signals", "evidence", "omissions"):
        for x in a[coll]:
            ids[x["id"]] += 1
    for i, c in ids.items():
        if c > 1:
            rep.error(f"id {i!r} used {c} times")
    claim_ids = {c["id"] for c in a["claims"]}
    omission_ids = {o["id"] for o in a["omissions"]}
    evidence_ids = {e["id"] for e in a["evidence"]}
    targets = claim_ids | omission_ids

    # spans
    for where, s in all_spans(a):
        if not (0 <= s["start"] < s["end"] <= n):
            rep.error(f"{where}: offsets out of range ({s['start']},{s['end']}) for text length {n}")
            continue
        if text[s["start"]:s["end"]] != s["text"]:
            rep.error(f"{where}: text != document.text[start:end]: {s['text'][:50]!r} vs {text[s['start']:s['end']][:50]!r}")
    for sg in a["signals"]:
        if sg["level"] == "claim" and not sg["spans"]:
            rep.error(f"signal {sg['id']}: claim-level signal without spans")
        for cid in sg["claim_ids"]:
            if cid not in claim_ids:
                rep.error(f"signal {sg['id']}: unknown claim {cid}")

    # regions
    by_kind: dict[str, list[dict]] = defaultdict(list)
    labels: Counter[str] = Counter()
    for r in doc["regions"]:
        if not (0 <= r["start"] < r["end"] <= n):
            rep.error(f"region {r.get('label') or r['kind']}: offsets out of range")
        by_kind[r["kind"]].append(r)
        if r.get("label"):
            labels[r["label"]] += 1
    for lab, c in labels.items():
        if c > 1:
            rep.error(f"region label {lab!r} used {c} times")
    for kind, rs in by_kind.items():
        rs = sorted(rs, key=lambda r: r["start"])
        for p, q in zip(rs, rs[1:]):
            if q["start"] < p["end"]:
                rep.error(f"regions of kind {kind} overlap: {p.get('label', p['start'])} and {q.get('label', q['start'])}")
    paras = {r["label"]: r for r in doc["regions"] if r["kind"] == "paragraph" and r.get("label")}
    for c in a["claims"]:
        lab = c.get("paragraph")
        if lab:
            if lab not in paras:
                rep.error(f"claim {c['id']}: paragraph {lab!r} is not a labelled paragraph region")
            else:
                reg, s0 = paras[lab], c["spans"][0]
                if not (reg["start"] <= s0["start"] and s0["end"] <= reg["end"]):
                    rep.error(f"claim {c['id']}: primary span is not inside paragraph {lab}")

    # evidence
    tiers = {e["id"]: e["tier"] for e in a["evidence"]}
    for e in a["evidence"]:
        seen = set()
        for l in e["links"]:
            if l["target"] not in targets:
                rep.error(f"evidence {e['id']}: link target {l['target']} is not a claim or omission")
            key = (l["target"], l["relation"])
            if key in seen:
                rep.error(f"evidence {e['id']}: duplicate link {key}")
            seen.add(key)
            if e["tier"] == 5 and l["relation"] == "supports" and l["target"] in claim_ids:
                rep.warn(f"evidence {e['id']}: tier-5 (company) material listed as supporting claim {l['target']}; company material cannot substantiate its own claim (D5)")
        for d in e.get("derived_from", []):
            if d not in evidence_ids:
                rep.error(f"evidence {e['id']}: derived_from unknown evidence {d}")
            if d == e["id"]:
                rep.error(f"evidence {e['id']}: derived from itself")
        if e["verified"] and not e.get("quote"):
            rep.error(f"evidence {e['id']}: verified but no quote")
        if e["kind"] == "computation":
            worst = max((tiers.get(d, 5) for d in e.get("derived_from", [])), default=5)
            if e["tier"] < worst:
                rep.warn(f"evidence {e['id']}: computation tier {e['tier']} is better than its worst input tier {worst}")
        if e.get("stage") and e["stage"] not in EVALUATOR_STAGES | {"omissions"}:
            rep.error(f"evidence {e['id']}: stage {e['stage']} does not produce evidence")

    # scores: exactly one per claim per dimension
    per_claim: dict[str, dict[str, dict]] = defaultdict(dict)
    for s in a["scores"]:
        if s["claim_id"] not in claim_ids:
            rep.error(f"score for unknown claim {s['claim_id']}")
            continue
        if s["dimension"] in per_claim[s["claim_id"]]:
            rep.error(f"claim {s['claim_id']}: dimension {s['dimension']} scored twice")
        per_claim[s["claim_id"]][s["dimension"]] = s
        for eid in s.get("evidence_ids", []):
            if eid not in evidence_ids:
                rep.error(f"score {s['claim_id']}/{s['dimension']}: unknown evidence {eid}")
        if s.get("stage") and s["stage"] not in DIM_STAGE[s["dimension"]]:
            rep.error(f"score {s['claim_id']}/{s['dimension']}: stage {s['stage']} cannot produce this dimension")
    for cid in claim_ids:
        missing = [d for d in DIMENSIONS if d not in per_claim[cid]]
        if missing:
            rep.error(f"claim {cid}: missing dimension scores {missing}")

    # arguments
    for g in a["arguments"]:
        if g["claim_id"] not in claim_ids:
            rep.error(f"argument for unknown claim {g['claim_id']}")
        for eid in g.get("evidence_ids", []):
            if eid not in evidence_ids:
                rep.error(f"argument {g['claim_id']}/{g['role']}: unknown evidence {eid}")

    # verdicts: exactly one per claim; derivation rules
    contradicting: dict[str, bool] = defaultdict(bool)
    for e in a["evidence"]:
        for l in e["links"]:
            if l["relation"] == "contradicts":
                contradicting[l["target"]] = True
    vcount: Counter[str] = Counter()
    for vd in a["verdicts"]:
        cid = vd["claim_id"]
        vcount[cid] += 1
        if cid not in claim_ids:
            rep.error(f"verdict for unknown claim {cid}")
            continue
        for eid in vd.get("evidence_ids", []):
            if eid not in evidence_ids:
                rep.error(f"verdict {cid}: unknown evidence {eid}")
        sc = per_claim.get(cid, {})
        if len(sc) == 4:
            L = derive_likelihood(sc)
            if abs(vd["likelihood"] - L) > 1e-9:
                rep.error(f"verdict {cid}: likelihood {vd['likelihood']} != max dimension score {L}")
            cat = derive_category(sc, contradicting[cid])
            if vd["category"] != cat:
                rep.error(f"verdict {cid}: category {vd['category']} but the rules derive {cat}")
            confs = [sc[d]["confidence"] for d in DIMENSIONS]
            if vd["confidence"] > max(confs) + 1e-9 or vd["confidence"] < min(confs) - 0.1:
                rep.warn(f"verdict {cid}: confidence {vd['confidence']} is outside the range of its dimension confidences [{min(confs)}, {max(confs)}]")
    for cid in claim_ids:
        if vcount[cid] != 1:
            rep.error(f"claim {cid}: {vcount[cid]} verdicts (expected 1)")

    # omissions
    for o in a["omissions"]:
        for eid in o.get("evidence_ids", []):
            if eid not in evidence_ids:
                rep.error(f"omission {o['id']}: unknown evidence {eid}")

    # summary
    sm = a.get("summary")
    if sm is None:
        if strict_summary:
            rep.error("analysis has no summary")
        return
    dist = Counter(vd["category"] for vd in a["verdicts"])
    for k in ("supported", "unsubstantiated", "misleading_by_framing", "contradicted"):
        if sm["verdict_distribution"][k] != dist.get(k, 0):
            rep.error(f"summary.verdict_distribution.{k} = {sm['verdict_distribution'][k]} but verdicts give {dist.get(k, 0)}")
    if sm["claim_count"] != len(a["claims"]):
        rep.error(f"summary.claim_count {sm['claim_count']} != {len(a['claims'])}")
    if sm["omission_count"] != len(a["omissions"]):
        rep.error(f"summary.omission_count {sm['omission_count']} != {len(a['omissions'])}")
    ranks = [t["rank"] for t in sm["top_issues"]]
    if ranks != list(range(1, len(ranks) + 1)):
        rep.error(f"summary.top_issues ranks must be 1..n, got {ranks}")
    for t in sm["top_issues"]:
        if t["target"] not in targets:
            rep.error(f"summary.top_issues target {t['target']} unknown")
    for t in sm["credit"]:
        if t["target"] not in claim_ids:
            rep.error(f"summary.credit target {t['target']} is not a claim")
        vd = next((x for x in a["verdicts"] if x["claim_id"] == t["target"]), None)
        if vd and vd["category"] != "supported":
            rep.warn(f"summary.credit lists {t['target']} whose verdict is {vd['category']}")


def cmd_validate_analysis(path: str) -> int:
    rep = Report()
    a = load_json(path)
    check_analysis(a, rep)
    return rep.finish("validate-analysis")


# ----------------------------------------------------------------------------- build (analysis -> events)

class Timeline:
    def __init__(self) -> None:
        self.seq = 0
        self.t = 0
        self.events: list[dict] = []

    def emit(self, typ: str, payload: dict, dt: int = 0) -> None:
        self.seq += 1
        self.t += dt
        self.events.append({"seq": self.seq, "t_ms": self.t, "type": typ, "payload": payload})

    def start(self, stage: str, dt: int = 100) -> None:
        self.emit("stage.started", {"stage": stage, "label": STAGE_LABELS[stage]}, dt)

    def done(self, stage: str, dt: int = 100) -> None:
        self.emit("stage.completed", {"stage": stage}, dt)


def build_events(a: dict) -> list[dict]:
    """Fixture pacing (D7): claims first, in neutral; then language marks; then evidence; then the
    colour settles as dimensions are scored and verdicts issued. The four evaluators run as
    overlapping stages, as they will live (D5). Every evidence item is emitted before anything
    that cites it."""
    tl = Timeline()
    doc = a["document"]
    started = {"contract_version": a["contract_version"], "analysis_id": a["analysis_id"], "mode": a["mode"],
               "source": {"kind": a["mode"], "name": a["analysis_id"]}}
    ref = {k: v for k, v in (("url", doc["source"].get("url")), ("title", doc.get("title"))) if v}
    if ref:
        started["document_ref"] = ref
    tl.emit("analysis.started", started)

    tl.start("ingest", 50)
    tl.emit("document.ingested", {"document": doc}, 300)
    tl.done("ingest", 50)

    tl.start("extract")
    for c in a["claims"]:
        tl.emit("claim.extracted", {"claim": c}, 90)
    tl.done("extract", 200)

    ev_by_stage: dict[str, list[dict]] = defaultdict(list)
    for e in a["evidence"]:
        ev_by_stage[e.get("stage") or "verify"].append(e)
    scores_by_dim: dict[str, list[dict]] = defaultdict(list)
    for s in a["scores"]:
        scores_by_dim[s["dimension"]].append(s)

    for st in ("language", "consistency", "substantiate", "verify"):
        tl.start(st)
    for sg in a["signals"]:
        tl.emit("language.signal", {"signal": sg}, 60)
    # company material first: computations in `verify` derive from it
    for st in ("language", "consistency", "substantiate", "verify"):
        for e in ev_by_stage[st]:
            tl.emit("evidence.added", {"evidence": e}, 250 if e["kind"] != "computation" else 150)
    for dim in DIMENSIONS:
        for s in scores_by_dim[dim]:
            tl.emit("dimension.scored", {"score": s}, 25)
    for st in ("language", "substantiate", "verify", "consistency"):
        tl.done(st)

    tl.start("omissions")
    for e in ev_by_stage["omissions"]:
        tl.emit("evidence.added", {"evidence": e}, 250)
    for o in a["omissions"]:
        tl.emit("omission.found", {"omission": o}, 400)
    tl.done("omissions", 150)

    tl.start("verdict")
    args_by_claim: dict[str, list[dict]] = defaultdict(list)
    for g in a["arguments"]:
        args_by_claim[g["claim_id"]].append(g)
    for vd in a["verdicts"]:
        for g in args_by_claim.get(vd["claim_id"], []):
            tl.emit("argument.made", {"argument": g}, 400)
        tl.emit("verdict.issued", {"verdict": vd}, 200 if args_by_claim.get(vd["claim_id"]) else 120)
    tl.done("verdict", 150)

    tl.start("summary")
    if a.get("summary"):
        tl.emit("summary.updated", {"summary": a["summary"], "final": True}, 500)
    tl.done("summary", 50)
    tl.emit("analysis.completed", {"duration_ms": tl.t + 50,
                                   "counts": {"claims": len(a["claims"]), "signals": len(a["signals"]),
                                              "evidence": len(a["evidence"]), "omissions": len(a["omissions"])}}, 50)
    return tl.events


def cmd_build(src: str, out: str) -> int:
    rep = Report()
    a = load_json(src)
    check_analysis(a, rep)
    if rep.errors:
        return rep.finish("build (analysis invalid, nothing written)")
    events = build_events(a)
    with open(out, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"wrote {out}: {len(events)} events, {events[-1]['t_ms']} ms")
    return rep.finish("build")


# ----------------------------------------------------------------------------- fold + validate events

def read_events(path: str, rep: Report) -> list[dict]:
    """Parse JSONL; assign seq from line order when absent (transport rule)."""
    events = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as ex:
                rep.error(f"line {ln}: not JSON ({ex})")
                continue
            if not isinstance(obj, dict):
                rep.error(f"line {ln}: not a JSON object")
                continue
            obj.setdefault("seq", len(events) + 1)
            events.append(obj)
    return events


def fold_events(events: list[dict]) -> dict:
    a: dict = {"analysis_id": "unknown", "contract_version": CONTRACT_VERSION, "mode": "live",
               "claims": [], "signals": [], "evidence": [], "scores": [], "arguments": [], "verdicts": [], "omissions": []}
    for e in events:
        t, p = e["type"], e["payload"]
        if t == "analysis.started":
            a["contract_version"] = p["contract_version"]
            a["analysis_id"] = p.get("analysis_id", a["analysis_id"])
            a["mode"] = p.get("mode", a["mode"])
        elif t == "document.ingested":
            a["document"] = p["document"]
        elif t == "claim.extracted":
            a["claims"].append(p["claim"])
        elif t == "language.signal":
            a["signals"].append(p["signal"])
        elif t == "evidence.added":
            a["evidence"].append(p["evidence"])
        elif t == "dimension.scored":
            a["scores"].append(p["score"])
        elif t == "argument.made":
            a["arguments"].append(p["argument"])
        elif t == "verdict.issued":
            a["verdicts"].append(p["verdict"])
        elif t == "omission.found":
            a["omissions"].append(p["omission"])
        elif t == "summary.updated":
            a["summary"] = p["summary"]
    return a


def check_events(events: list[dict], rep: Report) -> dict:
    v = validator_for("Event")
    for i, e in enumerate(events, 1):
        for err in schema_errors(v, e):
            rep.error(f"event {i}: schema: {err}")
        if isinstance(e.get("type"), str) and not TYPE_PATTERN.match(e["type"]):
            rep.error(f"event {i}: type {e['type']!r} is not lowercase namespace.verb")
    if rep.errors:
        return {}
    # envelope order (transport rules)
    for i, e in enumerate(events, 1):
        if e["seq"] != i:
            rep.error(f"event {i}: seq {e['seq']} (expected {i})")
    for p, q in zip(events, events[1:]):
        if q["t_ms"] < p["t_ms"]:
            rep.error(f"event {q['seq']}: t_ms decreases")
    if events[0]["type"] != "analysis.started":
        rep.error("first event must be analysis.started")
    if events[-1]["type"] not in ("analysis.completed", "analysis.failed"):
        rep.error("last event must be analysis.completed or analysis.failed")
    for e in events[1:]:
        if e["type"] == "analysis.started":
            rep.error(f"event {e['seq']}: analysis.started may only appear first")
    for e in events[:-1]:
        if e["type"] in ("analysis.completed", "analysis.failed"):
            rep.error(f"event {e['seq']}: terminal event before the end of the log")

    # stage lifecycle, dependencies, reference-before-use (contract rules)
    started: dict[str, int] = {}
    completed: dict[str, int] = {}
    open_stages: set[str] = set()
    seen_claims: set[str] = set()
    seen_evidence: set[str] = set()
    seen_omissions: set[str] = set()
    seen_scores: dict[str, set[str]] = defaultdict(set)
    finals = 0
    n_signals = 0

    def need_open(stage_set: set[str], seq: int, what: str) -> None:
        if not (open_stages & stage_set):
            rep.error(f"event {seq}: {what} emitted outside stage(s) {sorted(stage_set)} (open: {sorted(open_stages)})")

    def need_done(stages: list[str], seq: int, what: str) -> None:
        for s in stages:
            if s not in completed:
                rep.error(f"event {seq}: {what} started before stage {s} completed")

    for e in events:
        t, p, seq = e["type"], e["payload"], e["seq"]
        if t == "stage.started":
            s = p["stage"]
            if s in started:
                rep.error(f"event {seq}: stage {s} started twice")
            started[s] = seq
            open_stages.add(s)
            if s == "extract":
                need_done(["ingest"], seq, "extract")
            elif s in EVALUATOR_STAGES or s == "omissions":
                need_done(["extract"], seq, s)
            elif s == "verdict":
                need_done(sorted(EVALUATOR_STAGES) + ["omissions"], seq, "verdict")
            elif s == "summary":
                need_done(["verdict"], seq, "summary")
        elif t == "stage.completed":
            s = p["stage"]
            if s not in open_stages:
                rep.error(f"event {seq}: stage {s} completed but not open")
            open_stages.discard(s)
            completed[s] = seq
        elif t == "document.ingested":
            need_open({"ingest"}, seq, "document.ingested")
        elif t == "claim.extracted":
            need_open({"extract"}, seq, "claim.extracted")
            seen_claims.add(p["claim"]["id"])
        elif t == "language.signal":
            need_open({"language"}, seq, "language.signal")
            n_signals += 1
            for cid in p["signal"]["claim_ids"]:
                if cid not in seen_claims:
                    rep.error(f"event {seq}: signal references claim {cid} before it was extracted")
        elif t == "evidence.added":
            need_open(EVALUATOR_STAGES | {"omissions"}, seq, "evidence.added")
            ev = p["evidence"]
            seen_evidence.add(ev["id"])
            for d in ev.get("derived_from", []):
                if d not in seen_evidence:
                    rep.error(f"event {seq}: evidence {ev['id']} derived from {d} before it was added")
            for l in ev["links"]:
                if l["target"] not in seen_claims and l["target"] not in seen_omissions and l["target"].startswith("C"):
                    rep.error(f"event {seq}: evidence {ev['id']} links to claim {l['target']} before it was extracted")
        elif t == "dimension.scored":
            s = p["score"]
            need_open(DIM_STAGE[s["dimension"]], seq, f"dimension.scored/{s['dimension']}")
            if s["claim_id"] not in seen_claims:
                rep.error(f"event {seq}: score for claim {s['claim_id']} before extraction")
            for eid in s.get("evidence_ids", []):
                if eid not in seen_evidence:
                    rep.error(f"event {seq}: score cites evidence {eid} before it was added")
            seen_scores[s["claim_id"]].add(s["dimension"])
        elif t == "omission.found":
            need_open({"omissions"}, seq, "omission.found")
            o = p["omission"]
            seen_omissions.add(o["id"])
            for eid in o.get("evidence_ids", []):
                if eid not in seen_evidence:
                    rep.error(f"event {seq}: omission cites evidence {eid} before it was added")
        elif t == "argument.made":
            need_open({"verdict"}, seq, "argument.made")
            if p["argument"]["claim_id"] not in seen_claims:
                rep.error(f"event {seq}: argument for unknown claim")
            for eid in p["argument"].get("evidence_ids", []):
                if eid not in seen_evidence:
                    rep.error(f"event {seq}: argument cites evidence {eid} before it was added")
        elif t == "verdict.issued":
            need_open({"verdict"}, seq, "verdict.issued")
            vd = p["verdict"]
            missing = [d for d in DIMENSIONS if d not in seen_scores[vd["claim_id"]]]
            if missing:
                rep.error(f"event {seq}: verdict for {vd['claim_id']} before dimensions {missing} were scored")
            for eid in vd.get("evidence_ids", []):
                if eid not in seen_evidence:
                    rep.error(f"event {seq}: verdict cites evidence {eid} before it was added")
        elif t == "summary.updated":
            need_open({"summary"}, seq, "summary.updated")
            if p["final"]:
                finals += 1
            for tgt in [x["target"] for x in p["summary"]["top_issues"]] + [x["target"] for x in p["summary"]["credit"]]:
                if tgt not in seen_claims and tgt not in seen_omissions:
                    rep.error(f"event {seq}: summary references {tgt} before it exists")
        elif t == "analysis.completed":
            c = p.get("counts")
            if c and (c["claims"], c["signals"], c["evidence"], c["omissions"]) != (len(seen_claims), n_signals, len(seen_evidence), len(seen_omissions)):
                rep.error("analysis.completed counts do not match the events")
    if events[-1]["type"] == "analysis.completed":
        if finals != 1:
            rep.error(f"expected exactly one final summary.updated, found {finals}")
        for s in STAGES:
            if s not in completed:
                rep.error(f"stage {s} never completed")
        if open_stages:
            rep.error(f"stages still open at completion: {sorted(open_stages)}")
    return fold_events(events)


def canon(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def cmd_validate(path: str, analysis_path: str | None) -> int:
    rep = Report()
    events = read_events(path, rep)
    if rep.errors or not events:
        if not events:
            rep.error("log is empty")
        return rep.finish("validate")
    folded = check_events(events, rep)
    if folded:
        check_analysis(folded, rep, strict_summary=(events[-1]["type"] == "analysis.completed"))
    if analysis_path and folded and not rep.errors:
        a = load_json(analysis_path)
        for key in ("analysis_id", "contract_version", "mode", "document", "summary"):
            if canon(a.get(key)) != canon(folded.get(key)):
                rep.error(f"round trip: {key} differs between events and {analysis_path}")
        for coll in ("claims", "signals", "evidence", "omissions"):
            left = {x["id"]: x for x in a[coll]}
            right = {x["id"]: x for x in folded[coll]}
            if set(left) != set(right):
                rep.error(f"round trip: {coll} ids differ: {sorted(set(left) ^ set(right))}")
            for k in set(left) & set(right):
                if canon(left[k]) != canon(right[k]):
                    rep.error(f"round trip: {coll}/{k} differs")
        for coll, keyf in (("scores", lambda s: (s["claim_id"], s["dimension"])),
                           ("verdicts", lambda s: s["claim_id"]),
                           ("arguments", lambda s: (s["claim_id"], s["role"], s["text"][:40]))):
            left = {keyf(x): x for x in a[coll]}
            right = {keyf(x): x for x in folded[coll]}
            if set(left) != set(right):
                rep.error(f"round trip: {coll} keys differ")
            for k in set(left) & set(right):
                if canon(left[k]) != canon(right[k]):
                    rep.error(f"round trip: {coll}/{k} differs")
        if not rep.errors:
            print(f"round trip: events fold back to {analysis_path} exactly")
    counts = ", ".join(f"{k} x{n}" for k, n in sorted(Counter(e["type"] for e in events).items()))
    print(f"{len(events)} events, {events[-1]['t_ms']} ms; {counts}")
    return rep.finish("validate")


def cmd_fold(path: str, out: str) -> int:
    rep = Report()
    events = read_events(path, rep)
    folded = check_events(events, rep) if events else {}
    if folded and not rep.errors:
        dump_json(folded, out)
        print(f"wrote {out}")
    return rep.finish("fold")


# ----------------------------------------------------------------------------- main

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, rest = argv[1], argv[2:]
    try:
        if cmd == "resolve":
            return cmd_resolve(rest[0], "--write" in rest)
        if cmd == "build":
            return cmd_build(rest[0], rest[1])
        if cmd == "validate":
            ap = rest[rest.index("--analysis") + 1] if "--analysis" in rest else None
            return cmd_validate(rest[0], ap)
        if cmd == "validate-analysis":
            return cmd_validate_analysis(rest[0])
        if cmd == "fold":
            return cmd_fold(rest[0], rest[1])
    except IndexError:
        pass
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
