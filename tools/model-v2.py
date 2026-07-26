#!/usr/bin/env python3
"""Pennant model migration and validator. Copyright (c) 2026 Luka Gale. MIT licence.

Two jobs:

  --check     report what is wrong with a model and change nothing
  --write     upgrade a v1 model to schemaVersion 2 in place (with a .bak)

The v2 addition is small and additive: analyzers gain an explicit contract, so
the editor can stop offering every analyzer in every template. Nothing is
removed, and a v1 file still loads in the current app.

    "appliesTo": {
      "domains":     ["document-review"],   # which templates offer it
      "targetKinds": ["claim"],             # what a CHECKS edge may land on
      "requires":    []                     # graph preconditions, hand-tightened
    },
    "consumes": [...],                      # lifted from the matching logic step
    "produces": [...]

Nothing here is guessed from a hardcoded table. The contract is *inferred from
what the model already says*:

  targetKinds  <- the kinds of nodes this analyzer already has CHECKS edges to
  domains      <- the model's own domain, slugified
  consumes /
  produces     <- the logic step whose srcNode is this analyzer

So the migration is a lossless restatement of intent that was already in the
file but only implicitly. Tighten `requires` and widen `domains` by hand
afterwards; the inference cannot know what you meant to allow, only what you
already did.

Usage:
    python3 tools/model-v2.py --check  models/*.json
    python3 tools/model-v2.py --write  models/document-model.json
"""

import argparse
import json
import re
import shutil
import sys
from collections import defaultdict

SCHEMA_VERSION = 2


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")


PACK_KIND = "doccritique.knowledge-model"
PACK_VERSION = "1.1"


def load(path):
    """Return (model, envelope_or_None).

    Two shapes are in circulation and both are legitimate:

      * the export/import pack - {"kind", "schemaVersion": "1.1", "model": {...}} -
        which is what the studio's file picker reads and writes, and therefore what
        a template in templates/ should be;
      * a bare model, which is what samples/*.json are, because the server reads
        those directly.

    Note that the pack's "schemaVersion" is the string "1.1" and describes the
    envelope, while the model's own "schemaVersion" is the number 2 and describes
    the graph. Same name, different things, different levels.
    """
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if isinstance(doc, dict) and isinstance(doc.get("model"), dict):
        return doc["model"], doc
    return doc, None


def index_nodes(model):
    return {n["id"]: n for n in model.get("nodes", [])}


def validate(model, path):
    """Return a list of (severity, message). Severity is 'error' or 'warn'."""
    out = []
    nodes = index_nodes(model)
    edges = model.get("edges", [])

    # 1. Dangling edge endpoints.
    for e in edges:
        for end in ("from", "to"):
            if e.get(end) not in nodes:
                out.append(("error", f"edge {e.get('id')}: {end} '{e.get(end)}' is not a node"))

    # 2. Layer references.
    layers = {l["id"] for l in model.get("layers", [])}
    for n in model.get("nodes", []):
        if n.get("layer") not in layers:
            out.append(("error", f"node {n['id']}: layer '{n.get('layer')}' is not declared"))

    # 3. CHECKS edges must land on a kind the analyzer declares it can check.
    #    This is the rule that turns "a finding, not an impression" from a
    #    sentence in the summary into something the editor enforces.
    for e in edges:
        if e.get("rel") != "CHECKS":
            continue
        src, dst = nodes.get(e.get("from")), nodes.get(e.get("to"))
        if not src or not dst:
            continue
        if src.get("kind") != "analyzer":
            out.append(("error", f"edge {e['id']}: CHECKS must originate from an analyzer, not '{src.get('kind')}'"))
            continue
        allowed = (src.get("appliesTo") or {}).get("targetKinds")
        if allowed and dst.get("kind") not in allowed:
            out.append(("error",
                        f"analyzer {src['id']} checks {dst['id']} ({dst.get('kind')}) "
                        f"but declares targetKinds {allowed}"))

    # 4. Claims with no evidence. The tool's own headline finding, applied to
    #    the model file itself.
    evidenced = {e["from"] for e in edges if e.get("rel") == "EVIDENCED_BY"}
    for n in model.get("nodes", []):
        if n.get("kind") == "claim" and n["id"] not in evidenced:
            out.append(("warn", f"claim {n['id']} ('{n.get('label')}') has no EVIDENCED_BY edge"))

    # 5. Logic graph.
    logic = model.get("logic") or {}
    steps = {s["id"]: s for s in logic.get("steps", [])}
    ledges = logic.get("edges", [])

    for e in ledges:
        for end in ("from", "to"):
            if e.get(end) not in steps:
                out.append(("error", f"logic edge {e.get('id')}: {end} '{e.get(end)}' is not a step"))
        if e.get("rel") not in ("needs", "after"):
            out.append(("warn", f"logic edge {e.get('id')}: unknown rel '{e.get('rel')}'"))

    for s in logic.get("steps", []):
        if s.get("srcNode") and s["srcNode"] not in nodes:
            out.append(("error", f"step {s['id']}: srcNode '{s['srcNode']}' is not a node"))
        elif s.get("srcNode") and nodes[s["srcNode"]].get("kind") != "analyzer":
            out.append(("error", f"step {s['id']}: srcNode '{s['srcNode']}' is not an analyzer"))
        if s.get("kind") == "analyzer" and not s.get("srcNode"):
            out.append(("warn", f"step {s['id']}: analyzer step has no srcNode, so it is not tied to a model node"))

    # Cycle detection over 'needs' + 'after' (both are ordering constraints).
    adj = defaultdict(list)
    for e in ledges:
        if e.get("from") in steps and e.get("to") in steps:
            adj[e["from"]].append(e["to"])
    state = {}

    def walk(node, trail):
        state[node] = 1
        for nxt in adj[node]:
            if state.get(nxt) == 1:
                out.append(("error", "logic cycle: " + " -> ".join(trail + [nxt])))
            elif state.get(nxt) is None:
                walk(nxt, trail + [nxt])
        state[node] = 2

    for sid in steps:
        if state.get(sid) is None:
            walk(sid, [sid])

    # Producer/consumer reachability: every input a step consumes must be
    # produced by a step it depends on, transitively.
    preds = defaultdict(set)
    for e in ledges:
        if e.get("from") in steps and e.get("to") in steps:
            preds[e["to"]].add(e["from"])

    def upstream(sid, seen=None):
        seen = seen or set()
        for p in preds[sid]:
            if p not in seen:
                seen.add(p)
                upstream(p, seen)
        return seen

    produced_anywhere = set()
    for s in logic.get("steps", []):
        produced_anywhere.update(s.get("produces") or [])

    for s in logic.get("steps", []):
        available = set()
        for p in upstream(s["id"]):
            available.update(steps[p].get("produces") or [])
        for want in s.get("consumes") or []:
            if want not in available:
                where = "produced by no step" if want not in produced_anywhere else "not reachable from this step"
                out.append(("error", f"step {s['id']} consumes '{want}': {where}"))

    consumed_anywhere = set()
    for s in logic.get("steps", []):
        consumed_anywhere.update(s.get("consumes") or [])
    for s in logic.get("steps", []):
        for made in s.get("produces") or []:
            if made not in consumed_anywhere:
                out.append(("warn", f"step {s['id']} produces '{made}' and nothing consumes it"))

    return out


def migrate(model):
    """Return (model, [notes]) with schemaVersion 2 fields filled in."""
    notes = []
    nodes = index_nodes(model)
    edges = model.get("edges", [])
    logic = model.get("logic") or {}

    if model.get("schemaVersion") == SCHEMA_VERSION:
        return model, ["already at schemaVersion 2, nothing to do"]

    domain_slug = slug(model.get("domain")) or "unspecified"
    model["schemaVersion"] = SCHEMA_VERSION
    model["domainId"] = domain_slug
    notes.append(f"domainId = '{domain_slug}' (from domain '{model.get('domain')}')")

    # Which kinds does each analyzer already check?
    checks = defaultdict(set)
    for e in edges:
        if e.get("rel") == "CHECKS" and e.get("from") in nodes and e.get("to") in nodes:
            checks[e["from"]].add(nodes[e["to"]].get("kind"))

    # Which logic step drives each analyzer?
    by_src = {s["srcNode"]: s for s in logic.get("steps", []) if s.get("srcNode")}

    for n in model.get("nodes", []):
        if n.get("kind") != "analyzer":
            continue
        target_kinds = sorted(k for k in checks.get(n["id"], set()) if k)
        if not target_kinds:
            target_kinds = ["claim"]
            notes.append(f"{n['id']}: no CHECKS edge found, defaulted targetKinds to ['claim'] - review this")
        n.setdefault("appliesTo", {})
        n["appliesTo"].setdefault("domains", [domain_slug])
        n["appliesTo"].setdefault("targetKinds", target_kinds)
        n["appliesTo"].setdefault("requires", [])
        step = by_src.get(n["id"])
        if step:
            n.setdefault("consumes", list(step.get("consumes") or []))
            n.setdefault("produces", list(step.get("produces") or []))
        else:
            n.setdefault("consumes", [])
            n.setdefault("produces", [])
            notes.append(f"{n['id']}: no logic step references it, consumes/produces left empty")
        notes.append(f"{n['id']}: targetKinds {n['appliesTo']['targetKinds']}")

    if "createdAt" in model and not model["createdAt"]:
        notes.append("createdAt is 0 - set it on write, or drop the field")

    return model, notes


def main():
    ap = argparse.ArgumentParser(description="Pennant model migration and validator")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report problems, change nothing")
    mode.add_argument("--write", action="store_true", help="upgrade to schemaVersion 2 in place")
    ap.add_argument("--fail-on", choices=["error", "warn"], default="error",
                    help="exit non-zero at this severity or above (default: error)")
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args()

    worst = 0
    for path in args.paths:
        try:
            model, envelope = load(path)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"{path}: cannot read: {exc}")
            worst = max(worst, 2)
            continue

        if envelope is not None:
            if envelope.get("kind") != PACK_KIND:
                print(f"{path}: E pack kind is {envelope.get('kind')!r}, the studio reads {PACK_KIND!r} "
                      f"and will refuse this file")
                worst = max(worst, 2)
            if envelope.get("schemaVersion") != PACK_VERSION:
                print(f"{path}: E pack schemaVersion is {envelope.get('schemaVersion')!r}, "
                      f"the studio reads {PACK_VERSION!r} and will refuse this file")
                worst = max(worst, 2)

        if args.write:
            model, notes = migrate(model)
            shutil.copyfile(path, path + ".bak")
            out = model if envelope is None else dict(envelope, model=model)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(out, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            print(f"{path}: written (backup at {path}.bak)")
            for note in notes:
                print(f"  . {note}")

        findings = validate(model, path)
        errors = [m for s, m in findings if s == "error"]
        warns = [m for s, m in findings if s == "warn"]
        print(f"{path}: {len(errors)} error(s), {len(warns)} warning(s)")
        for m in errors:
            print(f"  E {m}")
        for m in warns:
            print(f"  W {m}")
        if errors:
            worst = max(worst, 2)
        elif warns:
            worst = max(worst, 1)

    threshold = 2 if args.fail_on == "error" else 1
    sys.exit(1 if worst >= threshold else 0)


if __name__ == "__main__":
    main()
