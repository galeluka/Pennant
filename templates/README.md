# Community templates

A template is an ordinary model file. Nothing in Pennant distinguishes one from a
model you made yesterday, which is the point: if it opens, it is a template.

## The shape

A template is a **pack**, not a bare model. The studio's file picker checks three
things before it looks at your graph at all:

```json
{ "kind": "doccritique.knowledge-model", "schemaVersion": "1.1", "model": { ... } }
```

Two fields called `schemaVersion` are in play and they are not the same field. The
outer one is the pack format, the string `"1.1"`. The one inside `model` is the
graph schema, the number `2`. `tools/test_import.js` checks both against the
constants in the running build, so a version bump here breaks the test rather than
shipping templates nobody can import.

(`samples/*.json`, which the server embeds, are bare models instead. That
inconsistency is in the code, not in this file.)

## Using one

Download a `.json` from this directory, then **Knowledge models → Import JSON** —
not *Import markdown*. It lands in your own workspace; editing it changes nothing
here.

## Contributing one

Four requirements, in the order they will bounce you:

1. **It must be anonymised.** Use the Anonymise page. It reports what it changed —
   read that report before you commit, because it will have missed something. No
   customer, employee, supplier, system hostname, ticket reference or internal
   project codename. If you have to think about whether a name is safe, it is not.

2. **It must validate.**

   ```bash
   python3 tools/model-v2.py --check templates/your-template.json
   node tools/test_import.js
   ```

   Zero errors from the first, and the second must pass — it confirms the studio
   will actually accept the file, and that every node kind and relationship name in
   it exists in this build. Warnings from the first are allowed and often correct:
   an unevidenced claim in a template is frequently the lesson it is teaching.

3. **It must carry a `summary` a stranger can act on.** What kind of document or
   domain this is for, what question it answers, and what it deliberately leaves
   out. Three to five sentences. A template nobody can place is a template nobody
   uses.

4. **Add one line to the table below.** Alphabetical by file.

| File | Review domain | What it is for |
|---|---|---|
| `ba-flow.json` | System | An approval workflow: actors, controls, a threshold rule, and the systems that route it. Ships one unenforced rule. |
| `change-proposal-review.json` | Document review | A change proposal as a graph: five sections, four claims, three obligations, four pieces of evidence, four analyzers wired with `CHECKS`. Ships with one deliberately unevidenced claim — the load-bearing one — because that is the finding it exists to teach. |
| `change-window-source-review.json` | Source review | A change-governance rulebook held as knowledge, so a proposed change is checked against it rather than against somebody's memory. A month-end freeze and an emergency bypass are wired with `CONTRADICTS`, and the bypass turns on a term nothing defines. |
| `corpo-ideas-implementation.json` | System | An idea intake and portfolio funnel: capability, controls, a budget variable, and the portal behind it. |
| `data-capture-pipeline-system.json` | System | A change data capture pipeline. Here partly to show what a system model *is*: no analyzer applies to it, so all ten show greyed with a reason. One component is deliberately left with no owner. |
| `incident-postmortem-review.json` | Document review | A postmortem as a document graph. Carries the two findings postmortems reliably produce: the claim that it cannot recur has no evidence, and the action item to review the process names nobody. One chapter is left unchecked so it passes by default. |
| `insuranceClaim.json` | Document review | A claim package: coverage, amount and timeliness as claims, with an adjuster obligation and the evidence that would settle each. |
| `live-event-production-review.json` | Document review | A production plan built around the failure that reads as competence: the schedule claims rigging and sound check run in parallel to save four hours, while a `DEPENDS_ON` edge says sound check cannot start until the rig is up. Both sentences survive a read-through; only the graph puts them side by side. |
| `personal-data-flow-source-review.json` | Source review | A record of processing checked against held retention rules. Two retention windows are wired with `CONTRADICTS` over rows that are in both sets, and the export interface has no edge from the lawful-basis register — the absence *is* the finding. |
| `pricing-rulebook-source-review.json` | Source review | Two failures that read as reasonable in prose: one capability with two `OWNED_BY` edges and no handoff, and a rule turning on the word *material* with no number behind it. A third rule is left neither implemented nor checked. |
| `shippingmogul.json` | System | Tender selection: rules, defined terms, a vessel-age rule and derived ceilings. Ships one unlinked term and one unenforced rule. |
| `student-absent.json` | Document review | An absence verification package: guardian explanation, policy guidelines and prior history as chapters, with the evidence behind each claim. |
| `vendor-security-questionnaire-review.json` | Document review | A vendor questionnaire response. Its point is the distinction prose flattens: one claim evidenced by an independent audit, one only by the vendor's own questionnaire, one by nothing. All three read identically in the document; only the graph separates them. |

### Domain coverage

There are three review domains and they are not equally served. Before adding
another document-review template, check whether the gap you are filling is
actually a gap:

| Review domain | Templates | Analyzers that apply |
|---|---|---|
| `document-review` | 6 | 9–10 of 10 |
| `source-review` | 3 | 5 of 10 |
| `system` | 4 | 0 of 10 — by design |

A `system` model makes no checkable assertion, so no analyzer applies to it. That
is the correct answer and not a missing feature. If your system template wants
analyzers, it probably wants `rule` and `control` nodes and a `reviewDomain` of
`source-review` instead.

### Findings are a budget, not a score

Every finding a template produces has to be one the summary claims. A template
whose gap audit reports five unchecked chapters is not teaching five lessons; it
is teaching the reader to skim the audit. Run:

```bash
node tools/test_templates.js
```

which prints every finding the app's own `auditModel` computes per template.
Aim for one, occasionally two. Zero means it is documentation — say so in the
summary.

### Generated templates

`tools/build-templates.py` declares seven of the templates above and writes them
out. Hand-writing a 200-line graph is how the three files that used to fail
`--check` got that way, so if you are adding something structurally similar,
add a declaration there rather than a new JSON file. It asserts two things the
validator does not: that every consecutive layer pair has an edge crossing it,
and that no node is left with no relationships.

## What makes a good one

The best templates are not the biggest. They are the ones where the graph says
something the prose could not: a `CONTRADICTS` edge between two rules nobody had
put side by side, a claim with no evidence behind it, an obligation whose owner was
never named.

If your template has no findings in it, it is documentation. That is fine, but say
so in the summary so nobody goes looking for the sharp edge.

## Licence

By opening a pull request you agree your template is contributed under the MIT
licence in [`LICENSE`](../LICENSE), and that you have the right to publish it.
That second part is the one to think about if the model started life inside an
employer's document.
