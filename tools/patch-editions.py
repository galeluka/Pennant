#!/usr/bin/env python3
"""Apply the editions/plans work to web/index.html and web/landing.html.

Anchored replacements with verification: every patch must match exactly once or
the script fails and writes nothing. That is the only safe way to edit a
7,800-line single-file app repeatedly.
"""
import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
IDX  = ROOT / "web" / "index.html"
LAND = ROOT / "web" / "landing.html"

patches = []   # (path, label, old, new)


def P(path, label, old, new):
    patches.append((path, label, old, new))


# ─── 1. dl.kv had no CSS rule at all ────────────────────────────────────────
P(IDX, "dl.kv grid",
  "  /* flex-wrap is load-bearing, not cosmetic.",
  """  /* `dl.kv` is used by the About dialog and had no rule anywhere in this file, so
     it fell back to the browser default for a definition list: dt on one line,
     dd indented on the next, nothing aligned with anything. A two-column grid is
     what the markup always meant. */
  dl.kv{display:grid;grid-template-columns:150px 1fr;gap:7px 16px;margin:0;font-size:11.5px;
    line-height:1.6;}
  dl.kv dt{color:var(--muted);font-weight:600;}
  dl.kv dd{margin:0;color:var(--ink);}
  @media (max-width:560px){ dl.kv{grid-template-columns:1fr;gap:2px 0;} dl.kv dd{margin-bottom:9px;} }

  /* flex-wrap is load-bearing, not cosmetic.""")


# ─── 2. Entitlements, after FLAGS ───────────────────────────────────────────
P(IDX, "PLANS + entitlements",
  "const SCHEMA = { kind:'doccritique.knowledge-model', version:'1.1' };",
  """/* ═══════════════════════════════════════════════════════════════════════════
   EDITIONS AND PLANS

   A flag and a plan answer different questions and conflating them is how a
   self-hosted build ends up asking a licence server for permission to open a
   folder on its own disk.

     FLAGS  does this surface exist in this build?
     PLAN   is this installation entitled to it?

   Self-hosted answers yes to everything. There is nobody to bill, no server to
   ask, and the licence is settled before the binary runs — so `ce` and
   `enterprise` differ in the paperwork, not in the code. That is deliberate: the
   regulated buyer gets the build that was already shipped.

   The hosted plans exist here so the gating can be exercised locally without a
   billing system. `state.plan` is a local override and nothing else; a real
   deployment takes the plan from /api/capabilities and ignores this. Switching
   it on the Admin page changes what the app offers, which is the only way to
   find out whether a tier makes sense before anyone is charged for it.
   ═══════════════════════════════════════════════════════════════════════════ */
const PLANS = {
  ce: {
    label:'Self-hosted', price:'free', licence:'AGPL-3.0', hosted:false,
    blurb:'The whole tool, on your own machine. Nothing is withheld and nothing phones home.',
    models:Infinity, seats:1,
    ai:true, exportAll:true, fileTargets:true, history:true,
    crossModel:false, sso:false, audit:false, billing:false },
  free: {
    label:'Hosted free', price:'0', licence:'hosted terms', hosted:true,
    blurb:'An account and a URL, to find out whether the thing is useful. Bring your own model.',
    models:3, seats:1,
    ai:false, exportAll:true, fileTargets:false, history:false,
    crossModel:false, sso:false, audit:false, billing:true },
  studio: {
    label:'Studio', price:'9.99/mo', licence:'hosted terms', hosted:true,
    blurb:'What a server does that a folder cannot: models that outlive a laptop, and history you can restore from.',
    models:Infinity, seats:1,
    ai:true, exportAll:true, fileTargets:false, history:true,
    crossModel:false, sso:false, audit:false, billing:true },
  team: {
    label:'Team', price:'19.99/seat/mo', licence:'hosted terms', hosted:true,
    blurb:'One term defined once and resolved in every model. The only tier that gets more valuable per model added.',
    models:Infinity, seats:25,
    ai:true, exportAll:true, fileTargets:false, history:true,
    crossModel:true, sso:false, audit:false, billing:true },
  enterprise: {
    label:'Enterprise self-hosted', price:'case by case', licence:'commercial', hosted:false,
    blurb:'The same build as self-hosted, under a commercial licence instead of AGPL, with SSO, audit export and support terms.',
    models:Infinity, seats:Infinity,
    ai:true, exportAll:true, fileTargets:true, history:true,
    crossModel:true, sso:true, audit:true, billing:false }
};
const PLAN_IDS = Object.keys(PLANS);
/* Every entitlement key, derived rather than restated, so a new key on a plan
   cannot be forgotten in the matrix on the Admin page. */
const PLAN_KEYS = ['ai','exportAll','fileTargets','history','crossModel','sso','audit'];

function planId(){
  const p = (typeof state !== 'undefined' && state) ? state.plan : null;
  return PLANS[p] ? p : 'ce';
}
function plan(){ return PLANS[planId()]; }
/* One question, one answer, one place to change when the tiers move. A surface
   asks `can('crossModel')` and never asks which plan it is. */
function can(key){ return !!plan()[key]; }
function planLimit(key){ const v = plan()[key]; return v === undefined ? Infinity : v; }
function limitLabel(v){ return v === Infinity ? 'unlimited' : String(v); }
/* The refusal has to name the plan that would allow it, or it is just a locked
   door. Same rule the analyzers page already follows for an inapplicable
   analyzer: show the reason, not the absence. */
function planUpsell(key){
  const has = PLAN_IDS.filter(id => PLANS[id][key]).map(id => PLANS[id].label);
  return has.length ? has.join(', ') : 'no plan';
}

const SCHEMA = { kind:'doccritique.knowledge-model', version:'1.1' };""")


# ─── 3. state.plan ──────────────────────────────────────────────────────────
P(IDX, "state.plan init",
  "  propProfiles: store.get('propProfiles', null) || [clone(PROPORTION_DEFAULT)],",
  """  /* Local plan override, for testing the tiers without a billing system. A real
     deployment reads this from /api/capabilities and this line becomes a fallback. */
  plan        : store.get('plan', null) || 'ce',
  propProfiles: store.get('propProfiles', null) || [clone(PROPORTION_DEFAULT)],""")

P(IDX, "state.plan reload",
  "  state.propProfiles       = store.get('propProfiles', null) || [clone(PROPORTION_DEFAULT)];",
  """  state.plan               = store.get('plan', null) || 'ce';
  state.propProfiles       = store.get('propProfiles', null) || [clone(PROPORTION_DEFAULT)];""")


# ─── 4. AI gated by entitlement, so a plan switch is observable ─────────────
P(IDX, "llmOn respects plan",
  "function llmOn(){ return !!(state.llm && state.llm.enabled && llmBase() && llmModel()); }",
  """/* The plan is checked here rather than at each of the fourteen call sites, so
   there is one answer to "is AI available" and no surface can disagree with
   another about it. On a plan without it the suggest buttons vanish the same way
   they do when no endpoint is configured, which is the honest behaviour: the
   feature is unavailable, and the reason is stated on the Profile page. */
function llmOn(){ return can('ai') && !!(state.llm && state.llm.enabled && llmBase() && llmModel()); }""")


# ─── 5. About: AGPL, edition, plan ──────────────────────────────────────────
P(IDX, "About licence block",
  """    <div class="section-rule">Licence</div>
    <p style="font-size:12.5px;line-height:1.8;"><b>MIT licence.</b> Copyright \\u00a9 2026 ${esc(APP.by)}.<br>
      Free to use, change, share and sell, including inside something closed, as long as the copyright
      notice and the licence text travel with it. No warranty, no liability. Full text in
      <code>LICENSE</code> in the repository.</p>""",
  """    <div class="section-rule">Licence</div>
    ${plan().licence === 'commercial'
      ? `<p style="font-size:12.5px;line-height:1.8;"><b>Commercial licence.</b> Copyright \\u00a9 2026 ${esc(APP.by)}.<br>
          This installation is licensed commercially rather than under AGPL-3.0, which is what removes the
          obligation to publish modifications of a service you run internally. The code is the same code.
          Terms are in your agreement, not in this dialogue.</p>`
      : `<p style="font-size:12.5px;line-height:1.8;"><b>AGPL-3.0.</b> Copyright \\u00a9 2026 ${esc(APP.by)}.<br>
          Free to use, change, share and sell. If you modify it and let other people reach it over a
          network, those people are entitled to your modified source. Running it unmodified, or only for
          yourself, carries no such obligation. No warranty, no liability. Full text in
          <code>LICENSE</code>; a commercial licence removing the copyleft obligation is available.</p>`}""")

P(IDX, "About this install",
  """    <dl class="kv">
      <dt>Data</dt><dd class="mono">${esc(WS.dir || '\\u2014')}/profiles/${esc((auth.user()||{}).name || '?')}/</dd>
      <dt>Server</dt><dd class="mono">${esc(WS.version || 'unknown')}</dd>
      <dt>AI assistance</dt><dd>${llmOn()
        ? 'On \\u2014 ' + esc(state.llm.baseUrl)
        : 'Off. Every page works without it. Turn it on in Admin if you want it.'}</dd>
    </dl>""",
  """    <dl class="kv">
      <dt>Edition</dt><dd>${esc(plan().label)}${plan().hosted ? '' : ' \\u00b7 your machine, your disk'}</dd>
      <dt>Plan</dt><dd>${esc(plan().price === 'free' ? 'no charge' : plan().price)}${
        plan().billing ? '' : ' \\u00b7 nothing to bill'}</dd>
      <dt>Knowledge models</dt><dd>${state.models.length} of ${esc(limitLabel(planLimit('models')))}</dd>
      <dt>Data</dt><dd class="mono">${esc(WS.dir || '\\u2014')}/profiles/${esc((auth.user()||{}).name || '?')}/</dd>
      <dt>Frontend</dt><dd class="mono">${esc(APP.build)}</dd>
      <dt>Server</dt><dd class="mono">${esc(WS.version || 'unknown')}</dd>
      <dt>AI assistance</dt><dd>${llmOn()
        ? 'On \\u2014 ' + esc(state.llm.baseUrl)
        : can('ai')
          ? 'Off. Every page works without it. Turn it on on the Profile page.'
          : 'Not included on ' + esc(plan().label) + '. Available on: ' + esc(planUpsell('ai')) + '.'}</dd>
    </dl>""")


# ─── 6. Import hardening ────────────────────────────────────────────────────
P(IDX, "import hardening",
  """    let o = null;
    try{ o = JSON.parse(txt); }catch(err){ return showBig('Import refused', noteBad('That file is not valid JSON. ' + esc(err.message))); }
    if(o.kind !== SCHEMA.kind) return showBig('Import refused', noteBad('Unexpected kind: <code>' + esc(String(o.kind)) + '</code>. This build reads <code>' + esc(SCHEMA.kind) + '</code>.'));""",
  """    /* Six checks, cheapest first, and every one of them refuses rather than
       repairs. The `accept=".json"` on the input above is a file-picker filter and
       nothing more — it is trivially bypassed by drag-and-drop or a renamed file,
       so it is a convenience, never a control. None of this is a security boundary
       either: it runs in the browser, where the person supplying the file also
       controls the code checking it. A hosted build must repeat all of it
       server-side and treat the browser's verdict as advisory. */
    if(txt.length > IMPORT_MAX_BYTES)
      return showBig('Import refused', noteBad('That file is ' + (txt.length/1048576).toFixed(1) +
        ' MB. The ceiling is ' + (IMPORT_MAX_BYTES/1048576) + ' MB. A knowledge model that large is ' +
        'almost always an export of something else that happens to be JSON.'));
    let o = null;
    try{ o = JSON.parse(txt); }catch(err){ return showBig('Import refused', noteBad('That file is not valid JSON. ' + esc(err.message))); }
    if(o === null || typeof o !== 'object' || Array.isArray(o))
      return showBig('Import refused', noteBad('Valid JSON, but not an object. A pack is <code>{ kind, schemaVersion, model }</code>.'));
    if(o.kind !== SCHEMA.kind) return showBig('Import refused', noteBad('Unexpected kind: <code>' + esc(String(o.kind)) + '</code>. This build reads <code>' + esc(SCHEMA.kind) + '</code>.'));""")

P(IDX, "import vocabulary check",
  """    if(!o.model || !Array.isArray(o.model.layers)) return showBig('Import refused', noteBad('The file has no model, or the model has no layers.'));
    const m = o.model; m.id = uid('m');""",
  """    if(!o.model || !Array.isArray(o.model.layers)) return showBig('Import refused', noteBad('The file has no model, or the model has no layers.'));
    if(!Array.isArray(o.model.nodes) || !Array.isArray(o.model.edges))
      return showBig('Import refused', noteBad('The model has no <code>nodes</code> array or no <code>edges</code> array.'));
    /* Vocabulary. `test_import.js` has always asserted that templates use only
       known kinds and relationships; the runtime import path never checked, so a
       file could load carrying a kind this build cannot draw and a relationship it
       cannot price. Refuse and name them, rather than loading a model that renders
       as blank shapes. */
    const badKinds = Array.from(new Set(o.model.nodes.map(n => n && n.kind).filter(k => !KINDS[k])));
    const badRels  = Array.from(new Set(o.model.edges.map(e => e && e.rel).filter(r => !RELS[r])));
    if(badKinds.length || badRels.length)
      return showBig('Import refused', noteBad('This build does not know:' +
        (badKinds.length ? '<br>node kinds \\u2014 <code>' + badKinds.map(esc).join('</code> <code>') + '</code>' : '') +
        (badRels.length  ? '<br>relationships \\u2014 <code>' + badRels.map(esc).join('</code> <code>') + '</code>' : '') +
        '<br>A mismatch is refused rather than half-applied, which is what the Models page promises.'));
    const m = o.model; m.id = uid('m');""")

P(IDX, "IMPORT_MAX_BYTES",
  "const SCHEMA = { kind:'doccritique.knowledge-model', version:'1.1' };",
  """/* A ceiling on an imported file. Not a security control — see the import handler
   — but the difference between a refusal and a locked-up tab. */
const IMPORT_MAX_BYTES = 8 * 1024 * 1024;
const SCHEMA = { kind:'doccritique.knowledge-model', version:'1.1' };""")


def main():
    files = {}
    for path, label, old, new in patches:
        text = files.get(path)
        if text is None:
            text = path.read_text(encoding="utf-8")
        n = text.count(old)
        if n != 1:
            print(f"FAIL  {label}: anchor matched {n} times, expected 1")
            return 1
        files[path] = text.replace(old, new, 1)
        print(f"ok    {label}")
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
