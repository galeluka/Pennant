#!/usr/bin/env python3
"""What happens when somebody builds something big. Measures against a real
template rather than guessing at bytes-per-node, and prints the three ceilings
in the order a user actually hits them. Run from the repository root."""
import json, time, copy, os
T = json.load(open('templates/change-proposal-review.json'))['model']
per_node = len(json.dumps(T)) / len(T['nodes'])
print(f"reference: {len(T['nodes'])} nodes, {len(T['edges'])} edges = {len(json.dumps(T))} bytes"
      f"  ->  ~{per_node:.0f} bytes per node incl. its share of edges/logic\n")

def synth(n):
    layers=[{"id":f"l{i}","name":f"Layer {i}","role":"x"} for i in range(1,4)]
    nodes=[{"id":f"n{i}","layer":f"l{i%3+1}","kind":"claim",
            "label":f"Claim number {i} about something in the domain",
            "props":{},"note":"A note of roughly the length people actually write."} for i in range(n)]
    edges=[{"id":f"e{i}","from":f"n{i}","to":f"n{(i+1)%n}","rel":"DEPENDS_ON","note":""} for i in range(n)]
    return {"schemaVersion":2,"id":"m","name":"big","domain":"d","question":"q","summary":"s",
            "layers":layers,"nodes":nodes,"edges":edges,"logic":{"goal":"g","steps":[],"edges":[]}}

print(f"{'nodes':>8} {'one model':>12} {'models.json':>12} {'+30 undo':>12} {'clone ms':>9}  verdict")
for n in (500, 2_000, 10_000, 25_000, 50_000):
    m = synth(n)
    s = json.dumps(m); one = len(s)
    t0=time.perf_counter(); copy.deepcopy(m); ms=(time.perf_counter()-t0)*1000
    undo = one * 31
    cap = "server PUT refuses (>32 MB)" if one > 32*1024*1024 else \
          "browser RAM heavy" if undo > 500*1024*1024 else "fine"
    print(f"{n:>8} {one/1048576:>10.1f} MB {one/1048576:>10.1f} MB {undo/1048576:>10.0f} MB {ms:>8.0f}  {cap}")
print("\nmodels.json holds EVERY model, so the middle column is per-mutation write volume for the whole workspace.")
