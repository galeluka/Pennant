#!/usr/bin/env python3
"""Admin becomes an edition and plan page; Profile gains a subscription section;
the landing page explains the tiers. Same anchored-and-verified approach."""
import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
IDX  = ROOT / "web" / "index.html"
LAND = ROOT / "web" / "landing.html"
patches = []
def P(path, label, old, new): patches.append((path, label, old, new))


# ─── Admin: the page becomes about the installation, not the folder ──────────
P(IDX, "admin header + plan section",
  """    <div class="eyebrow">Workspace</div>
    <h1>What is on disk.</h1>
    <p class="lede">This is housekeeping, not administration — there is no installation to run and no other
      user to govern. Everything below concerns the files under
      <code>${esc(WS.dir || 'the mounted data directory')}</code>, which you can read, copy and version
      with ordinary tools whether this page is open or not.</p>""",
  """    <div class="eyebrow">Installation</div>
    <h1>Which edition this is, and what it is entitled to.</h1>
    <p class="lede">Two separate questions, kept separate. A <b>feature flag</b> says whether a surface
      exists in this build. A <b>plan</b> says whether this installation may use it. Below that is the
      housekeeping: the files under <code>${esc(WS.dir || 'the mounted data directory')}</code>, which you
      can read, copy and version with ordinary tools whether this page is open or not.</p>

    <div class="section-rule">Edition</div>
    <dl class="kv">
      <dt>Running as</dt><dd><b>${esc(plan().label)}</b> \\u00b7 ${esc(plan().price === 'free' ? 'no charge' : plan().price)}</dd>
      <dt>Licence</dt><dd>${esc(plan().licence)}</dd>
      <dt>Deployment</dt><dd>${plan().hosted
        ? 'Hosted. Models live on the server; the plan is enforced there.'
        : 'Self-hosted. Files on your disk, no plan check at runtime, nothing phones home.'}</dd>
      <dt>Knowledge models</dt><dd>${state.models.length} of ${esc(limitLabel(planLimit('models')))}</dd>
      <dt>Seats</dt><dd>${esc(limitLabel(planLimit('seats')))}</dd>
    </dl>

    <div class="note"><b>Self-hosted and Enterprise self-hosted are the same build.</b> They differ in the
      licence, not the code: AGPL-3.0 obliges you to publish modifications of a service other people reach
      over a network, and the commercial licence removes that obligation. Nothing is withheld from the free
      edition to create the paid one, which is why this page can state the difference plainly.</div>

    <div class="section-rule">Test a plan locally</div>
    <p class="lede" style="margin-bottom:10px;">Switching this changes what the app offers, immediately and
      for real \\u2014 it is the same check the hosted build runs. It is stored in this workspace and has no
      billing behind it, so it proves the tier boundaries make sense before anybody is charged. On a hosted
      deployment the plan arrives from the server and this control is not shown.</p>
    <div class="row" style="align-items:center;gap:8px;flex-wrap:wrap;">
      <label class="f" style="font-size:10px;">Behave as</label>
      <select class="in" id="aPlan" style="max-width:280px;">
        ${PLAN_IDS.map(id => `<option value="${esc(id)}"${id === planId() ? ' selected' : ''}>${
          esc(PLANS[id].label)} \\u2014 ${esc(PLANS[id].price)}</option>`).join('')}
      </select>
      ${planId() === 'ce' ? '<span style="font-size:10px;color:var(--muted);">the default</span>'
        : '<button class="linkbtn" id="aPlanReset">back to self-hosted</button>'}
    </div>
    <p style="font-size:11px;color:var(--muted);line-height:1.6;margin:8px 0 0;">${esc(plan().blurb)}</p>

    <table class="t" style="margin-top:12px;"><thead><tr><th style="width:190px;">Entitlement</th>
      ${PLAN_IDS.map(id => `<th style="text-align:center;">${esc(PLANS[id].label)}</th>`).join('')}
    </tr></thead><tbody>
      ${[['models','Knowledge models'],['seats','Seats']].map(([k,lbl]) => `<tr>
        <td><b>${esc(lbl)}</b></td>
        ${PLAN_IDS.map(id => `<td style="text-align:center;${id===planId()?'background:var(--card);font-weight:700;':''}">${
          esc(limitLabel(PLANS[id][k]))}</td>`).join('')}</tr>`).join('')}
      ${PLAN_KEYS.map(k => `<tr>
        <td><b>${esc(({ai:'AI suggestions',exportAll:'All export artefacts',fileTargets:'Repository file targets',
                        history:'Version history',crossModel:'Cross-model vocabulary',sso:'SSO / OIDC',
                        audit:'Audit export'})[k] || k)}</b></td>
        ${PLAN_IDS.map(id => `<td style="text-align:center;${id===planId()?'background:var(--card);':''}">${
          PLANS[id][k] ? '<i class="fas fa-check" style="color:var(--green);"></i>'
                       : '<span style="color:var(--muted);">\\u2014</span>'}</td>`).join('')}</tr>`).join('')}
    </tbody></table>
    <p style="font-size:11px;color:var(--muted);line-height:1.6;margin:8px 0 0;">Visual editing and the
      five export artefacts appear in no row above, on purpose. They are in every plan including the free
      one. Charging for the canvas would gate the one thing that makes somebody understand what the tool is
      for, and the export files are generated in your browser from a file you already hold.</p>""")

P(IDX, "admin plan handlers",
  """  on('[data-hist]','click', e => openHistory(e.currentTarget.dataset.hist), root);""",
  """  on('[data-hist]','click', e => openHistory(e.currentTarget.dataset.hist), root);
  const ap = $('aPlan');
  if(ap) ap.onchange = () => { state.plan = ap.value; store.set('plan', state.plan); render(); };
  const apr = $('aPlanReset');
  if(apr) apr.onclick = () => { state.plan = 'ce'; store.set('plan', state.plan); render(); };""")


# ─── Profile: a real profile, with the subscription on it ───────────────────
P(IDX, "profile subscription section",
  """    <div class="section-rule">Appearance</div>
    <div class="row" style="display:flex;gap:8px;flex-wrap:wrap;">
      <button class="btn sm ghost" id="pfTheme">""",
  """    <div class="section-rule">Plan</div>
    ${plan().hosted
      ? `<dl class="kv">
          <dt>Plan</dt><dd><b>${esc(plan().label)}</b> \\u00b7 ${esc(plan().price)}</dd>
          <dt>Models</dt><dd>${state.models.length} of ${esc(limitLabel(planLimit('models')))}</dd>
          <dt>Seats</dt><dd>${esc(limitLabel(planLimit('seats')))}</dd>
          <dt>AI suggestions</dt><dd>${can('ai') ? 'included' : 'not on this plan \\u2014 available on ' + esc(planUpsell('ai'))}</dd>
          <dt>Cross-model vocabulary</dt><dd>${can('crossModel') ? 'included' : 'not on this plan \\u2014 available on ' + esc(planUpsell('crossModel'))}</dd>
        </dl>
        <p style="font-size:11px;color:var(--muted);line-height:1.6;margin:8px 0 0;">Billing, seats and
          cancellation are on this page and nowhere else, so there is one place to look. Cancelling stops
          the hosting; it does not delete anything, and every model can be exported as JSON first.</p>`
      : `<dl class="kv">
          <dt>Edition</dt><dd><b>${esc(plan().label)}</b></dd>
          <dt>Licence</dt><dd>${esc(plan().licence)}</dd>
          <dt>Billing</dt><dd>None. There is no account and nothing to charge for.</dd>
        </dl>
        <p style="font-size:11px;color:var(--muted);line-height:1.6;margin:8px 0 0;">This is a folder on
          your disk, so there is no subscription to show. The plan machinery exists for the hosted build and
          can be exercised from the Admin page without one.</p>`}

    <div class="section-rule">Appearance</div>
    <div class="row" style="display:flex;gap:8px;flex-wrap:wrap;">
      <button class="btn sm ghost" id="pfTheme">""")


# ─── Landing: say what the editions are ─────────────────────────────────────
P(LAND, "landing tiers",
  """    <p id="msg" class="msg" role="status" aria-live="polite"></p>
  </form>
</main>""",
  """    <p id="msg" class="msg" role="status" aria-live="polite"></p>
  </form>

  <!-- Editions. This page's stated job is a front door and not a brochure, so this
       is four lines and a link rather than a pricing table: enough that somebody
       who arrived from a README knows which thing they are signing into, and not
       so much that the door becomes a sales page. If it needs to grow, it should
       grow into a separate /pricing page instead of here. -->
  <section class="editions" aria-label="Editions">
    <h2>Which one is this?</h2>
    <dl>
      <dt>Self-hosted</dt>
      <dd>The whole tool, on your machine, under AGPL-3.0. Nothing withheld, nothing phones home.
          This is what you are signing into.</dd>
      <dt>Hosted</dt>
      <dd>An account instead of a folder: models that outlive a laptop, history you can restore from,
          and more than one person in a workspace.</dd>
      <dt>Team</dt>
      <dd>One term defined once and resolved across every model, rather than re-typed in each.</dd>
      <dt>Enterprise, self-hosted</dt>
      <dd>The same build under a commercial licence rather than AGPL, with SSO, audit export and support
          terms. For the people whose data cannot leave the building.</dd>
    </dl>
  </section>
</main>""")

P(LAND, "landing footer licence",
  """  <span id="status">MIT</span>""",
  """  <span id="status">AGPL-3.0</span>""")


def main():
    files = {}
    for path, label, old, new in patches:
        text = files.get(path)
        if text is None: text = path.read_text(encoding="utf-8")
        n = text.count(old)
        if n != 1:
            print(f"FAIL  {label}: anchor matched {n} times, expected 1"); return 1
        files[path] = text.replace(old, new, 1)
        print(f"ok    {label}")
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
