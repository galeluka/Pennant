# Where the graph data lives, and what happens when somebody builds a big one

Numbers below are from `tools/measure-scale.py`, measured against
`templates/change-proposal-review.json` (~371 bytes per node including its share
of edges and the logic block) rather than estimated.

## 1. It is not in the browser, but the browser holds all of it

`store` (`index.html:846`) is **not** localStorage. It is:

```
store.mem            plain JS object, the whole workspace, in RAM
store.set(k, v)      marks dirty, debounces 400 ms
store.flush()        PUT /api/workspace/<key> per dirty key
beforeunload         sendBeacon, fire-and-forget
```

`localStorage` holds exactly one thing — `ke.profile`, the chosen workspace name
(line 690). Everything else is memory during the session and JSON files on the
server after it. So: **authoritative copy on disk, working copy in RAM, nothing
durable in the browser.** That is the right design and it is already done.

Per workspace, on the server: `/data/profiles/<name>/<key>.json`, plus
`.history/` retaining **50 versions per key** by default (`KE_KEEP_VERSIONS`,
`main.go:85`).

## 2. Three ceilings, in the order they are actually hit

| nodes | one model | `models.json` | +30 undo copies | deep clone |
|---|---|---|---|---|
| 500 | 0.1 MB | 0.1 MB | 4 MB | 5 ms |
| 2,000 | 0.5 MB | 0.5 MB | 16 MB | 18 ms |
| 10,000 | 2.5 MB | 2.5 MB | 79 MB | 155 ms |
| 25,000 | 6.4 MB | 6.4 MB | 199 MB | 400 ms |
| 50,000 | 12.9 MB | 12.9 MB | 400 MB | 880 ms |

**Ceiling 1 — the canvas, around 1,000–2,000 nodes.** vis-network with physics
enabled stops being usable long before storage matters. This is the wall every
real user hits first, and it is a rendering problem, not a data problem. `FLAGS.graph`
already exists to turn the canvas off; a large model needs that plus a different
view (layer-at-a-time, or search-and-focus rather than draw-everything).

**Ceiling 2 — the undo clone, around 10,000–25,000 nodes.** This is the one worth
fixing. `snapshot()` (`index.html:2612`) does `clone(state.models)` — a full
serialise-and-reparse of **every model in the workspace** — and `markChange()`
calls it before every mutation. At 25,000 nodes that is ~400 ms of blocking work
per edit, so the editor visibly janks. `UNDO_MAX` is 30, so peak RAM is 31 copies
of everything.

**Ceiling 3 — the server PUT cap, around 85,000 nodes.** `handleWorkspaceKey`
limits a request body to 32 MB (`main.go:327`). Beyond that a save fails. Note
this is 32 MB for the **whole workspace**, because of the next point.

## 3. The structural problem: one key holds every model

```js
function saveModels(){ store.set('models', state.models); }     // index.html:3459
```

Editing one node in one model re-serialises and re-uploads **every model you
have**, and the server writes a new history version of the whole set. Three
consequences:

- write volume per keystroke-batch scales with the workspace, not the edit;
- the 32 MB cap is shared across all models rather than per model;
- history retention multiplies the whole workspace: at 10,000 nodes that is
  2.5 MB × 50 versions = **125 MB of disk per workspace**.

That last figure is the hosted cost driver. A thousand free users at that size is
125 GB of history for data nobody has paid for.

**The fix is small and worth doing before hosting anything:** key models
individually — `models:<id>` instead of `models` — so a mutation writes one
model, history retains per model, and the cap applies per model. `store` already
supports arbitrary keys and `store.keys()` already enumerates them, so this is a
change to `saveModels()` and the hydrate path, not to the storage layer.

Undo then becomes cheap too: snapshot the one model that changed rather than
`clone(state.models)`.

## 4. What this means for the free tier

You are right that a template-only free tier makes no sense. It is also
**unenforceable**: once a model is editable, "delete everything and rebuild" is
just editing, and a cleared-and-rebuilt template is indistinguishable from a
from-scratch model unless you track provenance nobody wants tracked. So the
templates are an on-ramp, not a restriction. If somebody wipes one and builds
their own domain in it, that is the tool working.

But the measurements say the cap I put in `PLANS` is the wrong cap.
`free.models = 3` is a proxy that does not track cost:

- three tiny models cost you almost nothing;
- **one** 20,000-node model costs 5 MB live and 250 MB of history.

A model count also breaks the on-ramp arithmetic: if the cap is 3 and the
templates are the way in, loading three templates spends the whole allowance and
leaves nothing to build in.

Cap the thing that costs money. **Nodes per workspace**, or bytes, with model
count left unlimited:

| plan | nodes / workspace | models |
|---|---|---|
| Hosted free | 2,000 | unlimited |
| Studio | 25,000 | unlimited |
| Team | 100,000 | unlimited |
| Self-hosted / Enterprise | unlimited | unlimited |

2,000 is not arbitrary: it is roughly where the canvas stops being usable
anyway, so the free tier ends at the point the tool stops being pleasant rather
than at an invented number. It is also ~0.5 MB live and ~25 MB of history, which
is a cost you can carry for a lot of free users.

And it is a limit you can explain in one sentence without sounding like you are
withholding anything: *the free tier holds a domain, not an enterprise.*

## 5. Fix order

1. **Per-model keys.** Unblocks everything else, small change, do it before any
   hosted deployment exists.
2. **Undo snapshots one model.** Removes ceiling 2 almost entirely.
3. **Cap nodes rather than models** in `PLANS`.
4. **History retention by total bytes, not version count** — 50 versions of a
   large workspace is unbounded disk; a byte budget is not.
5. **A view for large models.** The canvas is ceiling 1 and no storage change
   moves it.
