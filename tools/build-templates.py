#!/usr/bin/env python3
"""Build the community template set from declarations.

Hand-writing a 200-line JSON graph is how you get the three templates in this
repo that fail `model-v2.py --check`. Declaring the graph and generating the
file means the referential integrity is a property of the generator rather
than of somebody's attention at 2am.

Every template built here is asserted against the same rules the validator
applies, plus two the validator does not check:

  * every consecutive layer pair has an edge crossing it, so the model is one
    model rather than two sharing a file;
  * every deliberate finding is declared up front, so a finding that appears
    without being declared fails the build instead of shipping as a feature.

Usage:  python3 tools/build-templates.py [--out templates]
"""

import argparse
import json
import os
import sys

PACK_KIND = "doccritique.knowledge-model"
PACK_VERSION = "1.1"
GRAPH_SCHEMA = 2
CREATED = "2026-07-25T00:00:00.000Z"

# Node kinds and relationship names, mirrored from web/index.html. The build
# fails on anything not in these sets, which is cheaper than finding out at
# import time.
KINDS = {
    "product", "channel", "rule", "actor", "capability", "control", "process",
    "app", "integration", "datastore", "provider", "event", "term", "incident",
    "chapter", "analyzer", "variable", "ceiling", "document", "claim",
    "obligation", "evidence",
}
RELS = {
    "FLOWS_TO", "TRIGGERS", "CALLS", "READS_FROM", "WRITES_TO", "LISTENS_TO",
    "SENDS_VIA", "SOLD_VIA", "VALIDATES", "IMPLEMENTS", "GOVERNS", "OWNED_BY",
    "MONITORS", "DEPENDS_ON", "CAUSED_BY", "CONTRADICTS", "USED_IN", "CHECKS",
    "PART_OF", "ASSERTS", "IMPOSES", "EVIDENCED_BY", "SUPERSEDES",
}
STEP_KINDS = {"perspective", "analyzer", "proportions", "extract", "transform", "human"}
REVIEW_DOMAINS = {"document-review", "source-review", "system"}


# ─────────────────────────────────────────────────────────────────────────────
# T1 — Change window rules, checked against held platform knowledge.
# ─────────────────────────────────────────────────────────────────────────────
T1 = {
    "file": "change-window-source-review.json",
    "id": "m_change_window",
    "name": "Change window rules — source review",
    "domain": "platform change governance",
    "reviewDomain": "source-review",
    "question": "Can this change be executed inside the stated window without "
                "breaking a rule we already hold to be true?",
    "summary": "A set of standing change-governance rules held as a graph, so a "
               "proposed change can be checked against them rather than against "
               "somebody's memory of them. Two rules are wired with CONTRADICTS: "
               "a month-end freeze and an emergency bypass that does not name a "
               "testable definition of emergency. The model deliberately holds no "
               "release, no hostname and no ticket reference — it is the rulebook, "
               "not the change. What it leaves out is anything about a specific "
               "outage; an incident belongs in a postmortem model, not here.",
    "layers": [
        ("l1", "Standing rules",
         "Rules, controls and the roles accountable for them. Nothing naming a "
         "specific release or change record belongs here."),
        ("l2", "Definitions and measured limits",
         "Terms defined once, facts measured about this platform, and the ceilings "
         "derived from them. No rules belong here."),
        ("l3", "What a change touches",
         "Applications, interfaces and data stores in scope. No governance belongs here."),
    ],
    "nodes": [
        ("rule_freeze", "l1", "rule", "No production change during month-end billing",
         "Holds from the last working day of the month until billing confirms close."),
        ("rule_bypass", "l1", "rule", "An emergency change may proceed without board approval",
         "The exception everybody uses. It does not say who declares the emergency."),
        ("ctrl_board", "l1", "control", "Change advisory board mandate",
         "The standing authority both rules derive from."),
        ("act_chair", "l1", "actor", "Change advisory board chair", ""),
        ("act_oncall", "l1", "actor", "Platform on-call lead", ""),
        ("a_contra", "l1", "analyzer", "Conflicting change rules",
         "Two rules giving the platform different instructions for the same night.",
         {"domains": ["source-review", "document-review"], "targetKinds": ["rule"], "requires": []},
         ["rule statements"], ["rule conflicts"]),
        ("a_thresh", "l1", "analyzer", "Rule with no testable threshold",
         "A rule that cannot be evaluated without asking somebody what it meant.",
         {"domains": ["source-review"], "targetKinds": ["rule", "ceiling"], "requires": []},
         ["rule statements", "defined terms"], ["untestable thresholds"]),
        ("term_prod", "l2", "term", "Production",
         "Defined once so the freeze rule and the bypass rule cannot mean different things by it."),
        ("term_emergency", "l2", "term", "Emergency",
         "Used by the bypass rule and never given a threshold. This is the gap the model exists to show."),
        ("var_peak", "l2", "variable", "Peak concurrent sessions, trailing 90 days",
         "Measured, not estimated. Replace with your own figure."),
        ("ceil_restarts", "l2", "ceiling", "Maximum simultaneous rolling restarts",
         "Derived from peak sessions. Not a target — the point past which the platform sheds traffic."),
        ("app_selfcare", "l3", "app", "Customer self-care portal", ""),
        ("int_billing", "l3", "integration", "Billing event stream", ""),
        ("ds_subscriber", "l3", "datastore", "Subscriber profile store", ""),
    ],
    "edges": [
        ("ctrl_board", "GOVERNS", "rule_freeze", ""),
        ("ctrl_board", "GOVERNS", "rule_bypass", ""),
        ("rule_freeze", "CONTRADICTS", "rule_bypass",
         "The freeze admits no exception in its own text. The bypass admits any."),
        ("rule_freeze", "OWNED_BY", "act_chair", ""),
        ("ctrl_board", "OWNED_BY", "act_chair", ""),
        ("rule_bypass", "OWNED_BY", "act_oncall", ""),
        ("term_prod", "USED_IN", "rule_freeze", ""),
        ("term_emergency", "USED_IN", "rule_bypass", ""),
        ("ceil_restarts", "DEPENDS_ON", "var_peak", "The expression cannot be evaluated without the measurement."),
        ("a_contra", "CHECKS", "rule_freeze", ""),
        ("a_contra", "CHECKS", "rule_bypass", ""),
        ("a_thresh", "CHECKS", "ceil_restarts", ""),
        ("ceil_restarts", "GOVERNS", "app_selfcare", ""),
        ("app_selfcare", "READS_FROM", "ds_subscriber", ""),
        ("app_selfcare", "WRITES_TO", "int_billing", ""),
        ("app_selfcare", "OWNED_BY", "act_oncall", ""),
        ("int_billing", "OWNED_BY", "act_oncall", ""),
    ],
    "logic": {
        "goal": "Decide whether a proposed change may run in the requested window, "
                "and name the rule that stops it if it may not.",
        "steps": [
            ("st_read", "Read the rulebook", "extract",
             "Lift every rule statement and defined term out of the source.",
             [], ["rule statements", "defined terms"], None),
            ("st_contra", "Conflicting rules check", "analyzer",
             "Two rules that cannot both be obeyed on the same night.",
             ["rule statements"], ["rule conflicts"], "a_contra"),
            ("st_thresh", "Testable threshold check", "analyzer",
             "A rule whose trigger nobody can evaluate.",
             ["rule statements", "defined terms"], ["untestable thresholds"], "a_thresh"),
            ("st_gate", "Proportion gate", "proportions",
             "Is the restart plan inside the ceiling the measurements allow?",
             ["rule conflicts", "untestable thresholds"], ["change window verdict"], None),
            ("st_call", "Board decision", "human",
             "A person approves or refuses, holding the verdict and the named rule.",
             ["change window verdict"], [], None),
        ],
        "edges": [("st_read", "st_contra"), ("st_read", "st_thresh"),
                  ("st_contra", "st_gate"), ("st_thresh", "st_gate"),
                  ("st_gate", "st_call")],
    },
    "findings": [
        ("high", "CONTRADICTS between the freeze rule and the bypass rule."),
    ],
    "warnings": 0,
}

# ─────────────────────────────────────────────────────────────────────────────
# T2 — Personal data movement, checked against held retention rules.
# ─────────────────────────────────────────────────────────────────────────────
T2 = {
    "file": "personal-data-flow-source-review.json",
    "id": "m_personal_data_flow",
    "name": "Personal data flow — source review",
    "domain": "personal data processing",
    "reviewDomain": "source-review",
    "question": "Does every movement of personal data described here have a stated "
                "legal basis and a retention period that does not conflict with another?",
    "summary": "A record of processing held as a graph so an export can be checked "
               "against the retention rules the organisation already holds. Two "
               "retention rules are wired with CONTRADICTS because traffic data is "
               "also invoice-supporting data, and the two windows cannot both be "
               "obeyed for the same rows. The export interface is checked by an "
               "analyzer and has no edge from the lawful-basis register: that "
               "absence is the finding, and prose would have hidden it. No real "
               "controller, processor, dataset name or jurisdiction appears; "
               "retention figures are illustrative and must be replaced.",
    "layers": [
        ("l1", "Legal basis and retention rules",
         "The rules and the register they derive from, plus who is accountable. "
         "No systems belong here."),
        ("l2", "Definitions and measured volumes",
         "Terms defined once, and the measured facts a retention ceiling reads. "
         "No rules belong here."),
        ("l3", "Where personal data actually moves",
         "Interfaces, stores and third parties. No governance belongs here."),
    ],
    "nodes": [
        ("ctrl_basis", "l1", "control", "Lawful basis register",
         "The register every processing operation is supposed to appear in."),
        ("rule_traffic", "l1", "rule", "Traffic data is deleted after six months", ""),
        ("rule_invoice", "l1", "rule", "Records supporting an invoice are kept for five years", ""),
        ("act_dpo", "l1", "actor", "Data protection officer", ""),
        ("act_revenue", "l1", "actor", "Revenue assurance lead", ""),
        ("a_basis", "l1", "analyzer", "Data movement with no stated legal basis",
         "An interface that carries personal data and does not appear in the register.",
         {"domains": ["source-review", "document-review"],
          "targetKinds": ["integration", "datastore", "control"], "requires": []},
         ["data movements"], ["movements with no basis"]),
        ("a_retention", "l1", "analyzer", "Conflicting retention periods",
         "Two rules setting different windows over rows that are in both sets.",
         {"domains": ["source-review"], "targetKinds": ["rule"], "requires": []},
         ["rule statements"], ["retention conflicts"]),
        ("term_traffic", "l2", "term", "Traffic data",
         "The definition that decides whether the six-month rule reaches these rows."),
        ("term_subscriber", "l2", "term", "Subscriber identifier",
         "Pseudonymous is not anonymous. Defined here once."),
        ("var_held", "l2", "variable", "Days of traffic data currently held",
         "Measured from the oldest partition, not from policy."),
        ("ceil_retain", "l2", "ceiling", "Longest retention any dataset may carry",
         "Derived from the measured figure and the strictest applicable rule."),
        ("int_export", "l3", "integration", "Operational store to analytics export", ""),
        ("ds_crm", "l3", "datastore", "Operational subscriber store", ""),
        ("ds_warehouse", "l3", "datastore", "Analytics warehouse", ""),
        ("prov_analytics", "l3", "provider", "External analytics processor", ""),
    ],
    "edges": [
        ("ctrl_basis", "GOVERNS", "rule_traffic", ""),
        ("ctrl_basis", "GOVERNS", "rule_invoice", ""),
        ("rule_traffic", "CONTRADICTS", "rule_invoice",
         "Traffic data supporting an invoice is in both sets. Six months and five years cannot both hold."),
        ("ctrl_basis", "OWNED_BY", "act_dpo", ""),
        ("rule_traffic", "OWNED_BY", "act_dpo", ""),
        ("rule_invoice", "OWNED_BY", "act_revenue", ""),
        ("term_traffic", "USED_IN", "rule_traffic", ""),
        ("term_subscriber", "USED_IN", "int_export", ""),
        ("ceil_retain", "DEPENDS_ON", "var_held", ""),
        ("ceil_retain", "GOVERNS", "ds_warehouse", ""),
        ("a_retention", "CHECKS", "rule_traffic", ""),
        ("a_retention", "CHECKS", "rule_invoice", ""),
        ("a_basis", "CHECKS", "int_export", ""),
        ("int_export", "READS_FROM", "ds_crm", ""),
        ("int_export", "WRITES_TO", "ds_warehouse", ""),
        ("ds_warehouse", "OWNED_BY", "prov_analytics", ""),
        ("ds_crm", "OWNED_BY", "act_dpo", ""),
    ],
    "logic": {
        "goal": "Name every movement of personal data with no legal basis on record, "
                "and every pair of retention rules that cannot both be obeyed.",
        "steps": [
            ("st_read", "Read the record of processing", "extract",
             "Lift each data movement and each retention rule out of the source.",
             [], ["data movements", "rule statements"], None),
            ("st_basis", "Legal basis check", "analyzer",
             "Movements absent from the lawful basis register.",
             ["data movements"], ["movements with no basis"], "a_basis"),
            ("st_ret", "Retention conflict check", "analyzer",
             "Rules setting different windows over overlapping rows.",
             ["rule statements"], ["retention conflicts"], "a_retention"),
            ("st_gate", "Proportion gate", "proportions",
             "Is anything held longer than the ceiling the measurements allow?",
             ["movements with no basis", "retention conflicts"], ["processing verdict"], None),
            ("st_call", "Data protection sign-off", "human",
             "A named person accepts or refuses, holding the verdict.",
             ["processing verdict"], [], None),
        ],
        "edges": [("st_read", "st_basis"), ("st_read", "st_ret"),
                  ("st_basis", "st_gate"), ("st_ret", "st_gate"),
                  ("st_gate", "st_call")],
    },
    "findings": [
        ("high", "CONTRADICTS between the six-month and five-year retention rules."),
    ],
    "warnings": 0,
}

# ─────────────────────────────────────────────────────────────────────────────
# T3 — Pricing rulebook: duplicated authority and an untestable threshold.
# ─────────────────────────────────────────────────────────────────────────────
T3 = {
    "file": "pricing-rulebook-source-review.json",
    "id": "m_pricing_rulebook",
    "name": "Pricing rulebook — source review",
    "domain": "commercial pricing authority",
    "reviewDomain": "source-review",
    "question": "Who is actually allowed to approve a discount, and at what "
                "number does approval become mandatory?",
    "summary": "A pricing rulebook held as a graph, built around two failures that "
               "read as reasonable in prose. One capability carries two OWNED_BY "
               "edges and no handoff, which is duplicated authority rather than "
               "shared ownership. One rule turns on the word material with no "
               "threshold behind it, so nobody can evaluate it without asking. A "
               "third rule is deliberately left neither implemented nor checked, "
               "which the gap audit reports as nothing enforcing it. Prices, "
               "margins and product names are invented; replace every number "
               "before this is used for anything.",
    "layers": [
        ("l1", "Pricing authority",
         "Who may decide, the standard they decide against, and the capability "
         "itself. No rules and no channels belong here."),
        ("l2", "Rules and defined terms",
         "The written rules, the terms they turn on, and the measured margin a "
         "discount ceiling reads. No owners belong here."),
        ("l3", "Where a price is published",
         "Products and the channels that carry them. No governance belongs here."),
    ],
    "nodes": [
        ("cap_approve", "l1", "capability", "Price change approval",
         "Two teams claim this and the rulebook never says which one hands off to the other."),
        ("act_commercial", "l1", "actor", "Commercial pricing manager", ""),
        ("act_margin", "l1", "actor", "Margin control lead", ""),
        ("ctrl_margin", "l1", "control", "Minimum margin standard", ""),
        ("a_collide", "l1", "analyzer", "Two owners for one control",
         "A capability claimed twice with no handoff defined.",
         {"domains": ["source-review", "document-review"],
          "targetKinds": ["capability", "control", "actor", "rule"], "requires": []},
         ["ownership claims"], ["duplicated authority"]),
        ("a_vague", "l1", "analyzer", "Rule with no testable threshold",
         "A rule whose trigger is a word rather than a number.",
         {"domains": ["source-review"], "targetKinds": ["rule", "ceiling"], "requires": []},
         ["rule statements"], ["untestable thresholds"]),
        ("rule_discount", "l2", "rule", "A material discount requires margin approval",
         "Material is not defined anywhere in the source. This is the finding."),
        ("rule_promo", "l2", "rule", "Promotional pricing expires automatically",
         "Left neither implemented nor checked on purpose. Nothing enforces it."),
        ("term_material", "l2", "term", "Material discount",
         "Named but never given a number, so the rule that uses it cannot be evaluated."),
        ("var_margin", "l2", "variable", "Realised gross margin, last quarter",
         "Measured. Replace with your own figure."),
        ("ceil_discount", "l2", "ceiling", "Deepest discount that holds margin above the standard",
         "Derived from realised margin. Not a target."),
        ("prod_bundle", "l3", "product", "Converged bundle", ""),
        ("chan_web", "l3", "channel", "Web shop", ""),
        ("chan_retail", "l3", "channel", "Retail store", ""),
    ],
    "edges": [
        ("cap_approve", "OWNED_BY", "act_commercial", "First claim."),
        ("cap_approve", "OWNED_BY", "act_margin", "Second claim. No handoff is defined between the two."),
        ("ctrl_margin", "OWNED_BY", "act_margin", ""),
        ("ctrl_margin", "GOVERNS", "rule_discount", ""),
        ("ctrl_margin", "GOVERNS", "rule_promo", ""),
        ("rule_promo", "GOVERNS", "prod_bundle",
         "The rule reaches the product. Nothing implements it and no analyzer checks it."),
        ("a_collide", "CHECKS", "cap_approve", ""),
        ("a_vague", "CHECKS", "rule_discount", ""),
        ("a_vague", "CHECKS", "ceil_discount", ""),
        ("term_material", "USED_IN", "rule_discount", ""),
        ("ceil_discount", "DEPENDS_ON", "var_margin", ""),
        ("ceil_discount", "GOVERNS", "prod_bundle", ""),
        ("prod_bundle", "SOLD_VIA", "chan_web", ""),
        ("prod_bundle", "SOLD_VIA", "chan_retail", ""),
        ("prod_bundle", "OWNED_BY", "act_commercial", ""),
    ],
    "logic": {
        "goal": "Name who may approve a discount, and the number at which approval "
                "stops being optional.",
        "steps": [
            ("st_read", "Read the rulebook", "extract",
             "Lift every rule and every ownership claim out of the source.",
             [], ["rule statements", "ownership claims"], None),
            ("st_collide", "Duplicated authority check", "analyzer",
             "One capability, two claims, no handoff.",
             ["ownership claims"], ["duplicated authority"], "a_collide"),
            ("st_vague", "Testable threshold check", "analyzer",
             "A rule turning on a word with no number behind it.",
             ["rule statements"], ["untestable thresholds"], "a_vague"),
            ("st_gate", "Proportion gate", "proportions",
             "Is the proposed discount inside the ceiling realised margin allows?",
             ["duplicated authority", "untestable thresholds"], ["pricing verdict"], None),
            ("st_call", "Commercial sign-off", "human",
             "A named person approves, holding the verdict.",
             ["pricing verdict"], [], None),
        ],
        "edges": [("st_read", "st_collide"), ("st_read", "st_vague"),
                  ("st_collide", "st_gate"), ("st_vague", "st_gate"),
                  ("st_gate", "st_call")],
    },
    "findings": [
        ("high", "Rule 'Promotional pricing expires automatically' is neither "
                 "implemented nor checked."),
    ],
    "warnings": 0,
}

# ─────────────────────────────────────────────────────────────────────────────
# T4 — Incident postmortem as a reviewable document.
# ─────────────────────────────────────────────────────────────────────────────
T4 = {
    "file": "incident-postmortem-review.json",
    "id": "m_incident_postmortem",
    "name": "Incident postmortem — review template",
    "domain": "incident postmortem review",
    "reviewDomain": "document-review",
    "question": "Does this postmortem commit anybody to anything, and would any of "
                "its claims survive being asked for the number?",
    "summary": "A postmortem modelled as a document graph: four chapters, three "
               "claims, two obligations and the evidence that would settle them. "
               "It carries the finding postmortems reliably produce — the claim "
               "that the failure cannot recur has no evidence behind it, and the "
               "obligation to review the change process names nobody. One chapter "
               "is left with no analyzer pointed at it, so the gap audit reports "
               "that customer impact passes by default. Nothing here describes a "
               "real outage, customer, system or window; the incident node is a "
               "placeholder for yours.",
    "layers": [
        ("l1", "The postmortem as written",
         "The document, its chapters, the incident it is about and the process "
         "that caused it. No claims belong here."),
        ("l2", "What it claims and commits to",
         "Assertions that could be false, obligations they create, and the "
         "analyzers responsible for checking them. No evidence belongs here."),
        ("l3", "What would settle it",
         "Numbers and systems of record. No opinions and no narrative belong here."),
    ],
    "nodes": [
        ("doc", "l1", "document", "Production incident postmortem", ""),
        ("ch_timeline", "l1", "chapter", "Timeline", ""),
        ("ch_cause", "l1", "chapter", "Root cause", ""),
        ("ch_actions", "l1", "chapter", "Corrective actions", ""),
        ("ch_impact", "l1", "chapter", "Customer impact",
         "No analyzer is pointed at this chapter, so it passes by default. Deliberate."),
        ("inc", "l1", "incident", "Payment path outage",
         "Placeholder. Replace with your own incident, window and blast radius."),
        ("proc_change", "l1", "process", "Unreviewed configuration change", ""),
        ("act_reliability", "l1", "actor", "Reliability engineering lead", ""),
        ("c_cause", "l2", "claim", "A single configuration change caused the outage", ""),
        ("c_contained", "l2", "claim", "No customer records were lost", ""),
        ("c_norepeat", "l2", "claim", "The same failure cannot recur",
         "Deliberately unevidenced. This is the claim the template exists to teach."),
        ("o_alert", "l2", "obligation", "Add an alert on replication lag", ""),
        ("o_review", "l2", "obligation", "Review the change approval process",
         "No owner and no date. An obligation without both is a sentence, not an obligation."),
        ("a_unev", "l2", "analyzer", "Unevidenced claim",
         "A claim with nothing behind it that would settle it.",
         {"domains": ["document-review"], "targetKinds": ["claim"], "requires": []},
         ["claim list"], ["unevidenced claims"]),
        ("a_owner", "l2", "analyzer", "Obligation with no named owner",
         "An action item that will not happen because nobody owns it.",
         {"domains": ["document-review"], "targetKinds": ["obligation"], "requires": []},
         ["obligation list"], ["unowned obligations"]),
        ("a_placeholder", "l2", "analyzer", "Chapter promised and never written",
         "Content the document commits to and does not contain.",
         {"domains": ["document-review"], "targetKinds": ["document", "chapter"], "requires": []},
         ["chapter list"], ["missing content"]),
        ("ev_logs", "l3", "evidence", "Gateway error logs for the window", ""),
        ("ev_recon", "l3", "evidence", "Row count reconciliation report", ""),
        ("ev_change", "l3", "evidence", "Change record for the configuration edit", ""),
    ],
    "edges": [
        ("ch_timeline", "PART_OF", "doc", ""),
        ("ch_cause", "PART_OF", "doc", ""),
        ("ch_actions", "PART_OF", "doc", ""),
        ("ch_impact", "PART_OF", "doc", ""),
        ("inc", "CAUSED_BY", "proc_change", ""),
        ("proc_change", "OWNED_BY", "act_reliability", ""),
        ("ch_cause", "ASSERTS", "c_cause", ""),
        ("ch_impact", "ASSERTS", "c_contained", ""),
        ("ch_actions", "ASSERTS", "c_norepeat", ""),
        ("c_cause", "IMPOSES", "o_alert", ""),
        ("c_norepeat", "IMPOSES", "o_review", ""),
        ("c_cause", "EVIDENCED_BY", "ev_change", ""),
        ("c_cause", "EVIDENCED_BY", "ev_logs", ""),
        ("c_contained", "EVIDENCED_BY", "ev_recon", ""),
        ("a_unev", "CHECKS", "c_norepeat", ""),
        ("a_owner", "CHECKS", "o_review", ""),
        ("a_placeholder", "CHECKS", "ch_timeline", ""),
        ("a_placeholder", "CHECKS", "ch_cause", ""),
        ("a_placeholder", "CHECKS", "ch_actions", ""),
    ],
    "logic": {
        "goal": "Decide whether this postmortem can be signed off, and name what "
                "is missing if it cannot.",
        "steps": [
            ("st_ext", "Extract chapters, claims and obligations", "extract",
             "Lift the structure out of the document before checking anything.",
             [], ["chapter list", "claim list", "obligation list"], None),
            ("st_ph", "Missing content check", "analyzer",
             "Chapters the document promised and never wrote.",
             ["chapter list"], ["missing content"], "a_placeholder"),
            ("st_unev", "Unevidenced claim check", "analyzer",
             "Claims with nothing behind them.",
             ["claim list"], ["unevidenced claims"], "a_unev"),
            ("st_own", "Unowned obligation check", "analyzer",
             "Action items nobody owns.",
             ["obligation list"], ["unowned obligations"], "a_owner"),
            ("st_gate", "Proportion gate", "proportions",
             "Can the corrective actions actually be absorbed by the people named?",
             ["missing content", "unevidenced claims", "unowned obligations"],
             ["sign-off verdict"], None),
            ("st_call", "Sign-off", "human",
             "A named person closes the incident or sends it back.",
             ["sign-off verdict"], [], None),
        ],
        "edges": [("st_ext", "st_ph"), ("st_ext", "st_unev"), ("st_ext", "st_own"),
                  ("st_ph", "st_gate"), ("st_unev", "st_gate"), ("st_own", "st_gate"),
                  ("st_gate", "st_call")],
    },
    "findings": [
        ("medium", "Chapter 'Customer impact' has no rule stated for it and no "
                   "analyzer checking it."),
    ],
    "warnings": 1,  # c_norepeat has no EVIDENCED_BY, on purpose.
}

# ─────────────────────────────────────────────────────────────────────────────
# T5 — Vendor security questionnaire response.
# ─────────────────────────────────────────────────────────────────────────────
T5 = {
    "file": "vendor-security-questionnaire-review.json",
    "id": "m_vendor_questionnaire",
    "name": "Vendor security questionnaire — review template",
    "domain": "third party security assurance",
    "reviewDomain": "document-review",
    "question": "Which of this vendor's answers are evidenced by somebody other "
                "than the vendor?",
    "summary": "A completed third-party security questionnaire modelled as a "
               "document graph. Its point is the distinction prose flattens: one "
               "claim is evidenced by an independent audit report, another only by "
               "the vendor's own completed questionnaire, and a third by nothing at "
               "all. All three read identically in the response document; only the "
               "graph separates them. One chapter is left unchecked so the gap audit "
               "reports it passing by default. No real vendor, product, certificate "
               "or audit reference appears here.",
    "layers": [
        ("l1", "The response as submitted",
         "The document and its chapters. No claims belong here."),
        ("l2", "What the vendor asserts and owes",
         "Claims that could be false, obligations they create, and the analyzers "
         "responsible for them. No evidence belongs here."),
        ("l3", "What would settle it",
         "Independent reports and signed instruments. The vendor's own word is "
         "recorded here too, marked as what it is."),
    ],
    "nodes": [
        ("doc", "l1", "document", "Third-party security questionnaire response", ""),
        ("ch_access", "l1", "chapter", "Access control", ""),
        ("ch_encrypt", "l1", "chapter", "Encryption",
         "No analyzer is pointed here, so it passes by default. Deliberate."),
        ("ch_subproc", "l1", "chapter", "Sub-processors", ""),
        ("ch_ir", "l1", "chapter", "Incident response", ""),
        ("c_mfa", "l2", "claim", "Administrative access requires multi-factor authentication", ""),
        ("c_rest", "l2", "claim", "Customer data is encrypted at rest",
         "Evidenced only by the vendor's own questionnaire. That is an assertion repeated, not evidence."),
        ("c_notify", "l2", "claim", "A breach is notified within twenty-four hours",
         "Deliberately unevidenced. Nothing here would settle it."),
        ("c_nosub", "l2", "claim", "No sub-processor handles customer data", ""),
        ("o_pentest", "l2", "obligation", "Provide an annual penetration test report", ""),
        ("o_subnotice", "l2", "obligation", "Notify before adding a sub-processor", ""),
        ("act_assurance", "l2", "actor", "Security assurance lead", ""),
        ("a_unev", "l2", "analyzer", "Claim with no evidence at all",
         "An answer nothing would settle.",
         {"domains": ["document-review"], "targetKinds": ["claim"], "requires": []},
         ["claim list"], ["unevidenced claims"]),
        ("a_self", "l2", "analyzer", "Claim evidenced only by the vendor",
         "An answer whose only support is the document making it.",
         {"domains": ["document-review"], "targetKinds": ["claim"], "requires": []},
         ["claim list", "evidence list"], ["self-attested claims"]),
        ("a_placeholder", "l2", "analyzer", "Chapter promised and never written",
         "A section the response commits to and does not contain.",
         {"domains": ["document-review"], "targetKinds": ["document", "chapter"], "requires": []},
         ["chapter list"], ["missing content"]),
        ("ev_audit", "l3", "evidence", "Independent third-party audit report", ""),
        ("ev_self", "l3", "evidence", "The vendor's own completed questionnaire",
         "Recorded as evidence so the graph can show that it is the only thing behind a claim."),
        ("ev_dpa", "l3", "evidence", "Signed processing agreement, sub-processor annex", ""),
    ],
    "edges": [
        ("ch_access", "PART_OF", "doc", ""),
        ("ch_encrypt", "PART_OF", "doc", ""),
        ("ch_subproc", "PART_OF", "doc", ""),
        ("ch_ir", "PART_OF", "doc", ""),
        ("ch_access", "ASSERTS", "c_mfa", ""),
        ("ch_encrypt", "ASSERTS", "c_rest", ""),
        ("ch_ir", "ASSERTS", "c_notify", ""),
        ("ch_subproc", "ASSERTS", "c_nosub", ""),
        ("c_mfa", "EVIDENCED_BY", "ev_audit", "Independent."),
        ("c_rest", "EVIDENCED_BY", "ev_self", "The vendor's own word, and nothing else."),
        ("c_nosub", "EVIDENCED_BY", "ev_dpa", ""),
        ("c_mfa", "IMPOSES", "o_pentest", ""),
        ("c_nosub", "IMPOSES", "o_subnotice", ""),
        ("o_pentest", "OWNED_BY", "act_assurance", ""),
        ("o_subnotice", "OWNED_BY", "act_assurance", ""),
        ("a_unev", "CHECKS", "c_notify", ""),
        ("a_self", "CHECKS", "c_rest", ""),
        ("a_placeholder", "CHECKS", "ch_access", ""),
        ("a_placeholder", "CHECKS", "ch_subproc", ""),
        ("a_placeholder", "CHECKS", "ch_ir", ""),
    ],
    "logic": {
        "goal": "Separate the answers an independent party would confirm from the "
                "ones only the vendor asserts.",
        "steps": [
            ("st_ext", "Extract chapters, claims and evidence", "extract",
             "Lift the structure of the response before judging any answer.",
             [], ["chapter list", "claim list", "evidence list"], None),
            ("st_ph", "Missing content check", "analyzer",
             "Sections promised and not written.",
             ["chapter list"], ["missing content"], "a_placeholder"),
            ("st_unev", "No evidence check", "analyzer",
             "Answers with nothing behind them.",
             ["claim list"], ["unevidenced claims"], "a_unev"),
            ("st_self", "Self-attestation check", "analyzer",
             "Answers supported only by the document making them.",
             ["claim list", "evidence list"], ["self-attested claims"], "a_self"),
            ("st_gate", "Proportion gate", "proportions",
             "Is the assurance effort this vendor needs inside what the team can absorb?",
             ["missing content", "unevidenced claims", "self-attested claims"],
             ["assurance verdict"], None),
            ("st_call", "Assurance decision", "human",
             "A named person accepts the vendor, accepts with conditions, or refuses.",
             ["assurance verdict"], [], None),
        ],
        "edges": [("st_ext", "st_ph"), ("st_ext", "st_unev"), ("st_ext", "st_self"),
                  ("st_ph", "st_gate"), ("st_unev", "st_gate"), ("st_self", "st_gate"),
                  ("st_gate", "st_call")],
    },
    "findings": [
        ("medium", "Chapter 'Encryption' has no rule stated for it and no analyzer "
                   "checking it."),
    ],
    "warnings": 1,  # c_notify has no EVIDENCED_BY, on purpose.
}

# ─────────────────────────────────────────────────────────────────────────────
# T6 — A system model. No analyzer applies, and that is the lesson.
# ─────────────────────────────────────────────────────────────────────────────
T6 = {
    "file": "data-capture-pipeline-system.json",
    "id": "m_capture_pipeline",
    "name": "Change data capture pipeline — system model",
    "domain": "data distribution platform",
    "reviewDomain": "system",
    "question": "What runs in this pipeline, what does it write to, and who is "
                "named for each part of it?",
    "summary": "A change data capture pipeline as a system model: a source store, a "
               "capture connector, a streaming platform, a sink and a backup "
               "process, with the ownership actually declared. It is here for two "
               "reasons. First, it is the shape most platform teams start with. "
               "Second, it reads as a system model, so no analyzer applies to it — "
               "the Analyzers page shows all ten greyed with a reason, which is the "
               "correct answer and not a bug. One component is deliberately left "
               "with no owner. No hostname, cluster name, vendor or topic name "
               "appears; every label is generic on purpose.",
    "layers": [
        ("l1", "Capability and ownership",
         "What the pipeline is for and who is accountable. Nothing deployed belongs here."),
        ("l2", "What runs",
         "Connectors, the streaming platform, the source store and the scheduled "
         "jobs. No ownership statements belong here."),
        ("l3", "Where it lands",
         "Downstream stores and the third parties behind them."),
    ],
    "nodes": [
        ("cap_distribute", "l1", "capability", "Near-real-time data distribution", ""),
        ("ctrl_rpo", "l1", "control", "Recovery point objective standard", ""),
        ("act_platform", "l1", "actor", "Platform engineering team", ""),
        ("act_data", "l1", "actor", "Data platform team", ""),
        ("ds_source", "l2", "datastore", "Operational relational cluster", ""),
        ("app_capture", "l2", "app", "Change data capture connector", ""),
        ("int_bus", "l2", "integration", "Event streaming platform", ""),
        ("app_sink", "l2", "app", "Downstream sink connector",
         "Deliberately left with no OWNED_BY edge. In practice this is the component "
         "a vendor wrote and nobody internally adopted."),
        ("proc_backup", "l2", "process", "Scheduled base backup", ""),
        ("ev_failover", "l2", "event", "Source primary failover", ""),
        ("ds_lake", "l3", "datastore", "Analytics lake store", ""),
        ("prov_object", "l3", "provider", "Object storage service", ""),
    ],
    "edges": [
        ("cap_distribute", "OWNED_BY", "act_data", ""),
        ("ctrl_rpo", "OWNED_BY", "act_platform", ""),
        ("ctrl_rpo", "GOVERNS", "proc_backup", ""),
        ("app_capture", "IMPLEMENTS", "cap_distribute", ""),
        ("app_capture", "READS_FROM", "ds_source", ""),
        ("app_capture", "WRITES_TO", "int_bus", ""),
        ("app_sink", "LISTENS_TO", "int_bus", ""),
        ("app_sink", "WRITES_TO", "ds_lake", ""),
        ("proc_backup", "READS_FROM", "ds_source", ""),
        ("proc_backup", "WRITES_TO", "prov_object", ""),
        ("ev_failover", "TRIGGERS", "app_capture",
         "A failover moves the write position. The connector has to be told."),
        ("ds_source", "OWNED_BY", "act_platform", ""),
        ("app_capture", "OWNED_BY", "act_data", ""),
        ("proc_backup", "OWNED_BY", "act_platform", ""),
        ("ds_lake", "OWNED_BY", "act_data", ""),
    ],
    "logic": {
        "goal": "List every component that runs, and name the ones with nobody "
                "accountable for them.",
        "steps": [
            ("st_map", "Map what runs", "extract",
             "Enumerate the deployed components and the ownership actually declared.",
             [], ["running components", "declared owners"], None),
            ("st_gap", "Match components to owners", "transform",
             "Set difference, not judgement. No analyzer applies to a system model.",
             ["running components", "declared owners"], ["components with no owner"], None),
            ("st_gate", "Proportion gate", "proportions",
             "Can the team named actually carry the components attributed to it?",
             ["components with no owner"], ["operability verdict"], None),
            ("st_call", "Platform review", "human",
             "A named person assigns the orphans or accepts the risk.",
             ["operability verdict"], [], None),
        ],
        "edges": [("st_map", "st_gap"), ("st_gap", "st_gate"), ("st_gate", "st_call")],
    },
    "findings": [
        ("low", "'Downstream sink connector' has no owner."),
    ],
    "warnings": 0,
}

T7 = {
    "file": "live-event-production-review.json",
    "id": "m_live_event",
    "name": "Live event production plan — review template",
    "domain": "live event production",
    "reviewDomain": "document-review",
    "question": "Can this plan be executed in the order it is written, by the people "
                "it names, before doors open?",
    "summary": "A production plan modelled as a document graph, built around the "
               "failure that reads as competence in prose: the schedule claims "
               "rigging and sound check run in parallel to save four hours, while a "
               "DEPENDS_ON edge says sound check cannot start until the rig is up. "
               "Both sentences pass a read-through; only the graph puts them side "
               "by side, which is why they are wired with CONTRADICTS. The abort "
               "criterion is deliberately unevidenced and the contingency chapter "
               "has no analyzer pointed at it, so it passes by default. No real "
               "venue, artist, supplier or date appears; the load figures are "
               "invented and must be replaced before this is used to rig anything.",
    "layers": [
        ("l1", "The plan as written",
         "The document, its chapters and the steps that actually run on the day. "
         "No claims belong here."),
        ("l2", "What it commits to",
         "Assertions that could be false, obligations they create, who is "
         "accountable, and the analyzers responsible for checking them."),
        ("l3", "What would settle it",
         "Signed instruments and measurements from previous events. A confident "
         "estimate is not evidence."),
    ],
    "nodes": [
        ("doc", "l1", "document", "Live event production plan", ""),
        ("ch_runofshow", "l1", "chapter", "Run of show", ""),
        ("ch_rigging", "l1", "chapter", "Rig and de-rig schedule", ""),
        ("ch_contingency", "l1", "chapter", "Contingency and abort criteria",
         "No analyzer is pointed here, so it passes by default. Deliberate."),
        ("ch_contacts", "l1", "chapter", "On-site contacts", ""),
        ("proc_rig", "l1", "process", "Rig the stage", ""),
        ("proc_soundcheck", "l1", "process", "Sound check", ""),
        ("proc_doors", "l1", "process", "Doors open", ""),
        ("c_ready", "l2", "claim", "The stage is ready before doors open", ""),
        ("c_parallel", "l2", "claim", "Rigging and sound check run in parallel, saving four hours",
         "The claim the whole schedule is built on. The dependency edge below says it cannot hold."),
        ("c_load", "l2", "claim", "The venue is certified for the rigged load", ""),
        ("c_abort", "l2", "claim", "There is a stated criterion for abandoning the show",
         "Deliberately unevidenced. Everybody agrees there is one; nothing here says what it is."),
        ("o_contact", "l2", "obligation", "Name an on-site contact reachable during the show",
         "No owner and no medium. A phone number nobody is holding is not a contact."),
        ("o_permit", "l2", "obligation", "File the venue safety certificate before rig day", ""),
        ("act_producer", "l2", "actor", "Production manager", ""),
        ("a_timeline", "l2", "analyzer", "Milestone with no duration or an impossible overlap",
         "Reads the schedule as a schedule: what has to finish before what.",
         {"domains": ["document-review"],
          "targetKinds": ["chapter", "obligation", "process"], "requires": []},
         ["schedule steps", "chapter list"], ["impossible overlaps"]),
        ("a_unev", "l2", "analyzer", "Unevidenced claim",
         "A claim with nothing behind it that would settle it.",
         {"domains": ["document-review"], "targetKinds": ["claim"], "requires": []},
         ["claim list"], ["unevidenced claims"]),
        ("a_contact", "l2", "analyzer", "Obligation with no named owner or medium",
         "Who, and on what number. Either missing makes it undeliverable.",
         {"domains": ["document-review"],
          "targetKinds": ["obligation", "chapter"], "requires": []},
         ["obligation list", "chapter list"], ["unreachable contacts"]),
        ("ev_cert", "l3", "evidence", "Venue load certification, signed", ""),
        ("ev_rigplan", "l3", "evidence", "Rigging plan with load calculations", ""),
        ("ev_timings", "l3", "evidence", "Timed rehearsal log from the previous event", ""),
    ],
    "edges": [
        ("ch_runofshow", "PART_OF", "doc", ""),
        ("ch_rigging", "PART_OF", "doc", ""),
        ("ch_contingency", "PART_OF", "doc", ""),
        ("ch_contacts", "PART_OF", "doc", ""),
        ("proc_rig", "FLOWS_TO", "proc_soundcheck", ""),
        ("proc_soundcheck", "FLOWS_TO", "proc_doors", ""),
        ("proc_soundcheck", "DEPENDS_ON", "proc_rig",
         "Sound check cannot begin until the rig is up. This is the edge that refutes the parallel claim."),
        ("proc_rig", "OWNED_BY", "act_producer", ""),
        ("proc_soundcheck", "OWNED_BY", "act_producer", ""),
        ("proc_doors", "OWNED_BY", "act_producer", ""),
        ("ch_runofshow", "ASSERTS", "c_ready", ""),
        ("ch_rigging", "ASSERTS", "c_parallel", ""),
        ("ch_rigging", "ASSERTS", "c_load", ""),
        ("ch_contingency", "ASSERTS", "c_abort", ""),
        ("c_parallel", "CONTRADICTS", "c_ready",
         "If sound check waits for the rig, the four hours do not exist and the stage is not ready."),
        ("c_ready", "IMPOSES", "o_contact", ""),
        ("c_load", "IMPOSES", "o_permit", ""),
        ("c_ready", "EVIDENCED_BY", "ev_timings", ""),
        ("c_parallel", "EVIDENCED_BY", "ev_rigplan", ""),
        ("c_load", "EVIDENCED_BY", "ev_cert", ""),
        ("o_permit", "OWNED_BY", "act_producer", ""),
        ("a_timeline", "CHECKS", "proc_soundcheck", ""),
        ("a_timeline", "CHECKS", "ch_rigging", ""),
        ("a_timeline", "CHECKS", "ch_runofshow", ""),
        ("a_unev", "CHECKS", "c_abort", ""),
        ("a_contact", "CHECKS", "o_contact", ""),
        ("a_contact", "CHECKS", "ch_contacts", ""),
    ],
    "logic": {
        "goal": "Decide go or no-go, and name the step that stops it if it is no-go.",
        "steps": [
            ("st_ext", "Extract the plan", "extract",
             "Lift chapters, claims, obligations and the schedule out of the document.",
             [], ["chapter list", "claim list", "obligation list", "schedule steps"], None),
            ("st_time", "Schedule feasibility check", "analyzer",
             "Overlaps the dependencies forbid, and milestones with no duration.",
             ["schedule steps", "chapter list"], ["impossible overlaps"], "a_timeline"),
            ("st_unev", "Unevidenced claim check", "analyzer",
             "Assertions with nothing behind them.",
             ["claim list"], ["unevidenced claims"], "a_unev"),
            ("st_contact", "Reachability check", "analyzer",
             "Obligations with nobody named and no medium.",
             ["obligation list", "chapter list"], ["unreachable contacts"], "a_contact"),
            ("st_gate", "Proportion gate", "proportions",
             "Is the crew this plan needs the crew that is actually available?",
             ["impossible overlaps", "unevidenced claims", "unreachable contacts"],
             ["go/no-go verdict"], None),
            ("st_call", "Go or no-go", "human",
             "A named person calls it, holding the verdict and the blocking step.",
             ["go/no-go verdict"], [], None),
        ],
        "edges": [("st_ext", "st_time"), ("st_ext", "st_unev"), ("st_ext", "st_contact"),
                  ("st_time", "st_gate"), ("st_unev", "st_gate"), ("st_contact", "st_gate"),
                  ("st_gate", "st_call")],
    },
    "findings": [
        ("high", "CONTRADICTS between the parallel-schedule claim and stage readiness."),
        ("medium", "Chapter 'Contingency and abort criteria' has no analyzer checking it."),
    ],
    "warnings": 1,   # c_abort has no EVIDENCED_BY, on purpose.
}

TEMPLATES = [T1, T2, T3, T4, T5, T6, T7]


def slug(text):
    import re
    return re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")


def build(spec):
    nodes = []
    for row in spec["nodes"]:
        nid, layer, kind, label, note = row[0], row[1], row[2], row[3], row[4]
        n = {"id": nid, "layer": layer, "kind": kind, "label": label,
             "props": {}, "note": note}
        if len(row) > 5:                      # analyzer contract
            n["appliesTo"] = row[5]
            n["consumes"] = row[6]
            n["produces"] = row[7]
        nodes.append(n)

    edges = [{"id": f"e_{i+1:04d}", "from": f, "rel": r, "to": t, "note": note}
             for i, (f, r, t, note) in enumerate(spec["edges"])]

    steps = []
    for sid, name, kind, intent, cons, prod, src in spec["logic"]["steps"]:
        s = {"id": sid, "name": name, "kind": kind, "intent": intent,
             "prompt": "", "consumes": cons, "produces": prod}
        if src is not None:
            s["srcNode"] = src
        steps.append(s)

    ledges = [{"id": f"le_{i+1:04d}", "from": f, "to": t, "rel": "needs"}
              for i, (f, t) in enumerate(spec["logic"]["edges"])]

    model = {
        "schemaVersion": GRAPH_SCHEMA,
        "id": spec["id"],
        "name": spec["name"],
        "domain": spec["domain"],
        "domainId": slug(spec["domain"]),
        "reviewDomain": spec["reviewDomain"],
        "question": spec["question"],
        "summary": spec["summary"],
        "anonymised": True,
        "createdAt": CREATED,
        "layers": [{"id": i, "name": n, "role": r} for i, n, r in spec["layers"]],
        "nodes": nodes,
        "edges": edges,
        "logic": {"goal": spec["logic"]["goal"], "steps": steps, "edges": ledges},
    }
    return {"kind": PACK_KIND, "schemaVersion": PACK_VERSION, "model": model}


def selfcheck(spec, model):
    """Assert the things the validator does not, and fail loudly."""
    errs = []
    ids = {n["id"] for n in model["nodes"]}
    layers = [l["id"] for l in model["layers"]]
    by_id = {n["id"]: n for n in model["nodes"]}

    for n in model["nodes"]:
        if n["kind"] not in KINDS:
            errs.append(f"unknown node kind '{n['kind']}' on {n['id']}")
        if n["layer"] not in layers:
            errs.append(f"node {n['id']} in undeclared layer {n['layer']}")
    for e in model["edges"]:
        if e["rel"] not in RELS:
            errs.append(f"unknown relationship '{e['rel']}' on {e['id']}")
        for end in ("from", "to"):
            if e[end] not in ids:
                errs.append(f"edge {e['id']}: {end} '{e[end]}' is not a node")
    if model["reviewDomain"] not in REVIEW_DOMAINS:
        errs.append(f"unknown reviewDomain '{model['reviewDomain']}'")
    for s in model["logic"]["steps"]:
        if s["kind"] not in STEP_KINDS:
            errs.append(f"unknown step kind '{s['kind']}' on {s['id']}")

    # Consecutive layers must be joined, or the file holds two models.
    for a, b in zip(layers, layers[1:]):
        joined = any(
            (by_id[e["from"]]["layer"], by_id[e["to"]]["layer"]) in {(a, b), (b, a)}
            for e in model["edges"]
            if e["from"] in by_id and e["to"] in by_id)
        if not joined:
            errs.append(f"no edge crosses between layer {a} and {b}")

    # No orphan nodes.
    touched = set()
    for e in model["edges"]:
        touched.add(e["from"]); touched.add(e["to"])
    for n in model["nodes"]:
        if n["id"] not in touched:
            errs.append(f"node {n['id']} has no relationships")

    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="templates")
    args = ap.parse_args()

    bad = 0
    for spec in TEMPLATES:
        pack = build(spec)
        errs = selfcheck(spec, pack["model"])
        path = os.path.join(args.out, spec["file"])
        if errs:
            bad += 1
            print(f"FAIL {spec['file']}")
            for e in errs:
                print("       " + e)
            continue
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(pack, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        m = pack["model"]
        print(f"OK   {spec['file']:46} {m['reviewDomain']:15} "
              f"{len(m['nodes'])} nodes  {len(m['edges'])} edges  "
              f"{len(m['logic']['steps'])} steps")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
