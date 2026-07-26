#!/usr/bin/env python3
"""Repair the three templates that fail `model-v2.py --check`.

All three carry the same copy-pasted logic block and therefore the same three
faults:

  1. a step of kind "analyzer" whose srcNode points at an app or a channel.
     None of these three models contains an analyzer node at all — they read as
     system models, where no analyzer applies — so the step kind was wrong by
     construction, not merely mis-wired. It becomes "transform".
  2. the first step consumes an input no step produces. A pipeline's first step
     consumes nothing; that is what makes it first.
  3. the last step produces an output nothing consumes. A terminal human step
     produces nothing inside the graph.

Nothing about the domain graphs is touched. Only the logic block is edited, and
only where it is provably wrong.
"""

import json
import sys

FILES = [
    "templates/ba-flow.json",
    "templates/corpo-ideas-implementation.json",
    "templates/shippingmogul.json",
]


def fix(path):
    with open(path, encoding="utf-8") as fh:
        pack = json.load(fh)
    model = pack["model"]
    logic = model.get("logic") or {}
    steps = logic.get("steps", [])
    node_kind = {n["id"]: n["kind"] for n in model.get("nodes", [])}
    notes = []

    # 1. A step claiming to be an analyzer, in a model with no analyzer node.
    has_analyzer_node = any(k == "analyzer" for k in node_kind.values())
    for s in steps:
        src = s.get("srcNode") or ""
        if src and node_kind.get(src) != "analyzer":
            notes.append(f"{s['id']}: dropped srcNode '{src}' ({node_kind.get(src)}, not an analyzer)")
            s["srcNode"] = ""
        if s.get("kind") == "analyzer" and not s.get("srcNode") and not has_analyzer_node:
            notes.append(f"{s['id']}: kind analyzer -> transform (no analyzer node in this model)")
            s["kind"] = "transform"

    # 2/3. Producer-consumer closure at the two ends of the graph.
    preds = {s["id"]: set() for s in steps}
    for e in logic.get("edges", []):
        if e.get("to") in preds and e.get("from") in preds:
            preds[e["to"]].add(e["from"])
    by_id = {s["id"]: s for s in steps}

    def upstream(sid, seen=None):
        seen = seen if seen is not None else set()
        for p in preds.get(sid, ()):
            if p not in seen:
                seen.add(p)
                upstream(p, seen)
        return seen

    for s in steps:
        available = set()
        for p in upstream(s["id"]):
            available.update(by_id[p].get("produces") or [])
        unreachable = [c for c in (s.get("consumes") or []) if c not in available]
        if unreachable:
            notes.append(f"{s['id']}: dropped unproduced input(s) {unreachable}")
            s["consumes"] = [c for c in s["consumes"] if c in available]

    consumed = set()
    for s in steps:
        consumed.update(s.get("consumes") or [])
    for s in steps:
        dangling = [p for p in (s.get("produces") or []) if p not in consumed]
        if dangling:
            notes.append(f"{s['id']}: dropped unconsumed output(s) {dangling}")
            s["produces"] = [p for p in s["produces"] if p in consumed]

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(pack, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return notes


if __name__ == "__main__":
    for f in FILES:
        print(f)
        for n in fix(f):
            print("   " + n)
    sys.exit(0)
