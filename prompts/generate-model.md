# Generate a Pennant model

Paste everything below into a capable model — the one you already trust with the
document — then paste your source material after it. It returns a single JSON file
you import on the **Knowledge models** page.

This exists because the useful division of labour is the opposite of the usual
one. Let the big model do the reading; let Pennant hold the structure, run the
checks, and be the thing you edit and version. What comes back here is a first
draft of a graph, not an answer.

Two warnings before you use it.

**It will get things wrong.** Everything it produces is a proposal. A node you did
not verify is a node that will be exported as fact later, so the import is the
start of the work, not the end of it. `tools/model-v2.py --check` catches structural
mistakes; only you can catch the wrong ones.

**Check what you paste.** If the source is confidential, the model you paste it
into is a third party. Pennant's Anonymise page exists for the return trip; it
cannot help with the outbound one.

---

## The prompt

````text
You convert source material into a Pennant knowledge model: a single JSON file
describing a domain as layers of typed nodes joined by typed edges.

Return ONLY the JSON. No prose before or after, no markdown fence, no commentary.

## The shape

The studio's file picker refuses anything that is not wrapped in this envelope. It
checks three things before it looks at your model at all: `kind`, `schemaVersion`,
and that `model.layers` is an array. Get the envelope wrong and the import is
rejected with no partial credit.

Note the two different `schemaVersion` fields. The outer one is the **pack format**
and is the string `"1.1"`. The inner one is the **model** schema and is the number
`2`. They are not the same field and neither substitutes for the other.

{
  "kind": "doccritique.knowledge-model",
  "schemaVersion": "1.1",
  "model": {

  "schemaVersion": 2,
  "id": "m_<short_slug>",
  "name": "<short human name>",
  "domain": "<the subject in three or four words>",
  "domainId": "<document-review | source-review | system>",
  "reviewDomain": "<same value as domainId, or omit>",
  "question": "<the one question this model exists to answer>",
  "summary": "<3-5 sentences: what is modelled, and what a reader can settle with it>",
  "anonymised": false,
  "layers": [ { "id": "l1", "name": "<layer name>", "role": "<what belongs in this layer and what does not>" } ],
  "nodes":  [ { "id": "<slug>", "layer": "l1", "kind": "<node kind>", "label": "<short label>",
                "props": {}, "note": "<one or two sentences, or empty>" } ],
  "edges":  [ { "id": "e_0001", "from": "<node id>", "to": "<node id>", "rel": "<REL>", "note": "" } ],
  "createdAt": 0,
  "logic": {
    "goal": "<what running this pipeline decides>",
    "steps": [ { "id": "st_<slug>", "name": "<step name>", "kind": "<step kind>",
                 "intent": "<what this step is for>", "prompt": "",
                 "consumes": ["<named input>"], "produces": ["<named output>"],
                 "srcNode": "<analyzer node id, only for kind analyzer>" } ],
    "edges": [ { "id": "le_0001", "from": "st_a", "to": "st_b", "rel": "needs" } ]
  }

  }
}

(The indentation above is only there to show which fields sit inside `model`.
Return ordinary JSON.)

## Layers

Three to five. A layer is a level of description, not a folder: the same fact must
not appear in two layers. Name in `role` what does NOT belong in each one — that
sentence is what stops the model sprawling.

For a document: what the document must contain / what it commits to / what would
settle it. For a system: what customers meet / what the business owns / what runs.

## Node kinds — use these exact strings and no others

Document modelling:
  document    A whole document of a recurring type. The thing a template describes.
  chapter     A section a document of this type must contain.
  claim       An assertion the document makes that could be false. If it cannot be
              false it is not a claim; it is background.
  obligation  Something somebody must do because the document says so. It has an
              owner and a date, or it is not an obligation.
  evidence    What would settle a claim. A number, a system of record, an executed
              test, a signature. Never an opinion.
  analyzer    A checker responsible for verifying one thing. See below.

Domain and system modelling:
  product channel rule actor capability control process app integration
  datastore provider event term incident variable ceiling

  rule        A condition that decides an outcome: eligibility, pricing, policy.
  actor       A person, team or role that owns or approves something.
  control     A requirement, standard or governance artefact.
  term        A defined word. Once, then referenced everywhere it is used.
  incident    A recorded failure, with a window and a cause.
  variable    A measured fact about the organisation. Something you look up, not
              estimate.
  ceiling     A limit derived from variables. Not a target — the point past which
              nobody can operate the result.

## Relationship types — use these exact strings and no others

Document:  PART_OF ASSERTS IMPOSES EVIDENCED_BY CHECKS CONTRADICTS SUPERSEDES
System:    FLOWS_TO TRIGGERS CALLS READS_FROM WRITES_TO LISTENS_TO SENDS_VIA
           SOLD_VIA VALIDATES IMPLEMENTS GOVERNS OWNED_BY MONITORS DEPENDS_ON
           CAUSED_BY USED_IN

  ASSERTS       Section A makes claim B. If B is false, the section is wrong.
  IMPOSES       A creates obligation B on somebody.
  EVIDENCED_BY  Claim A is settled by evidence B. No evidence, no claim.
  CHECKS        Analyzer A is responsible for verifying B.
  CONTRADICTS   A and B cannot both be true. Use it. An unstated contradiction is
                the single most valuable thing a model can surface.

## The rules that matter

1. Every claim needs at least one EVIDENCED_BY edge, or it is a finding rather
   than a claim. If you cannot name the evidence, still create the claim and leave
   it unevidenced — that absence is a result, not a gap to paper over.
2. Every obligation carries props.owner and props.due. If the source does not say,
   write "unstated" and put the quote in `note`. Never invent an owner.
3. An analyzer CHECKS exactly one kind of thing, and its edges must land on that
   kind. Declare it:
      "appliesTo": { "domains": ["document-review"], "targetKinds": ["claim"], "requires": [] }
   An analyzer pointed at a whole document produces an impression. Pointed at one
   claim, it produces a finding. That distinction is the product.
4. Every node id is a short lowercase slug, unique, stable and meaningful:
   c_dates, s_scope, ev_capacity. Never a number on its own.
5. Both ends of every edge must be a node id that exists in `nodes`.
6. Quote the source in `note` when a node came from a specific sentence. A node
   whose provenance nobody can find is a node nobody can check.
7. Anything you inferred rather than read gets `"note": "inferred: <why>"`. Say so.
   A model that hides which parts were guessed is worse than a shorter model.
8. Do not invent numbers, dates, owners, systems or names. Absent is a legitimate
   answer and a useful one.

## The logic pipeline

Order the checks. Step kinds: extract, perspective, analyzer, transform,
proportions, human. Edge rel is "needs" for a data dependency and "after" for
ordering that is not one.

Every name in a step's `consumes` must appear in the `produces` of a step it
depends on, transitively. Start with one `extract` step; end with one `human`
step, because a person decides and the pipeline stops there.

## Size

20 to 60 nodes. Under 20 and the graph says less than the prose it came from; over
60 and nobody reviews it. If the source is larger, model the part that answers
`question` and say what you left out in `summary`.

Now read the source material that follows and return the JSON.
````

---

## After it answers

```bash
# structure, contracts and the checks that matter.
# Reads either the envelope or a bare model.
python3 tools/model-v2.py --check my-model.json
```

It will report unevidenced claims as warnings. Read them: that list is the first
useful output of the whole exercise, and it is usually the reason you built the
model.

Then import the file on the **Knowledge models** page — *Import JSON*, not *Import
markdown* — and start disagreeing with it. Fix the labels, delete what is wrong, add the CONTRADICTS edges it missed.

If the result is good enough to be worth someone else's time, see
[`templates/README.md`](../templates/README.md) — anonymise it first, and the
Anonymise page will tell you what it changed.
