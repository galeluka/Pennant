/* Would the studio actually accept our template and the file the AI prompt asks
   for? This test answers that by taking SCHEMA from the real page script, so it
   cannot drift from the app the way a hardcoded copy would.

   The four checks below are the ones in the JSON import handler in web/index.html.
   If that handler changes, this test should be updated with it - and the point of
   pulling SCHEMA from the page is that a version bump breaks the test loudly
   rather than silently shipping templates nobody can import. */
const fs = require('fs');

/* Minimal stubs: only enough to let the page script reach its own constants. */
global.document = { getElementById: () => null, querySelectorAll: () => [],
  createElement: () => ({}), addEventListener(){}, body:{classList:{toggle(){}}}, documentElement:{} };
global.window = { addEventListener(){}, localStorage:{getItem:()=>null,setItem(){},removeItem(){}},
  location:{hash:''}, matchMedia:()=>({matches:false,addEventListener(){}}) };
global.localStorage = window.localStorage; global.location = window.location;
global.navigator = { sendBeacon:()=>true, clipboard:{writeText:async()=>{}} };
global.fetch = async () => ({ ok:false, status:0, text:async()=>'', json:async()=>({}) });
global.Blob = class {}; global.URL = { createObjectURL:()=>'', revokeObjectURL(){} };
global.FileReader = class { readAsText(){} readAsDataURL(){} };
global.vis = undefined; global.Chart = undefined;
global.getComputedStyle = () => ({ getPropertyValue: () => '' });
let raf = 0;
global.requestAnimationFrame = f => { if (raf++ < 2) f(0); return raf; };
global.cancelAnimationFrame = () => {};
process.on('unhandledRejection', () => {});

const html = fs.readFileSync(__dirname + '/../web/index.html', 'utf8');
const m = /<script>\s*\n/.exec(html);
const app = new Function(html.slice(m.index + m[0].length,
  html.indexOf('</script', m.index + m[0].length)) +
  '\nreturn { SCHEMA, KIND_IDS, RELS, modelDomain, analyzerFits, checksViolations, ANALYZER_IDS };')();

let fails = 0;
const t = (name, cond, extra) => {
  if (!cond) { fails++; console.log('FAIL  ' + name + (extra ? '\n        ' + extra : '')); }
  else console.log('PASS  ' + name + (extra ? '  (' + extra + ')' : ''));
};

/* The import handler's own conditions, in its own order. */
function importVerdict(o) {
  if (o.kind !== app.SCHEMA.kind) return 'refused: kind is ' + JSON.stringify(o.kind);
  if (o.schemaVersion !== app.SCHEMA.version) return 'refused: schemaVersion is ' + JSON.stringify(o.schemaVersion);
  if (!o.model || !Array.isArray(o.model.layers)) return 'refused: no model, or model.layers is not an array';
  return 'accepted';
}

console.log('app expects kind=' + app.SCHEMA.kind + ' schemaVersion=' + app.SCHEMA.version);

/* 1. Every template in templates/ must import. */
const dir = __dirname + '/../templates';
const files = fs.readdirSync(dir).filter(f => f.endsWith('.json'));
t('there is at least one template', files.length > 0, files.length + ' file(s)');
files.forEach(f => {
  let o;
  try { o = JSON.parse(fs.readFileSync(dir + '/' + f, 'utf8')); }
  catch (e) { t('templates/' + f + ' is valid JSON', false, e.message); return; }
  const v = importVerdict(o);
  t('templates/' + f + ' imports', v === 'accepted', v);
  t('templates/' + f + ' has nodes and edges',
    Array.isArray(o.model.nodes) && o.model.nodes.length > 0 && Array.isArray(o.model.edges),
    (o.model.nodes || []).length + ' nodes');
  /* Node kinds and relationship names must exist in this build, or the graph
     renders as untyped soup. */
  const badKinds = [...new Set((o.model.nodes || []).map(n => n.kind))].filter(k => !app.KIND_IDS.includes(k));
  t('templates/' + f + ' uses only known node kinds', badKinds.length === 0, badKinds.join(','));
  const badRels = [...new Set((o.model.edges || []).map(e => e.rel))].filter(r => !(r in app.RELS));
  t('templates/' + f + ' uses only known relationships', badRels.length === 0, badRels.join(','));
});

/* 2. The envelope the AI prompt asks for must be the envelope the app wants.
      This is the check that caught the original mistake: the prompt asked for a
      bare model with a numeric schemaVersion, which the app refuses twice over. */
const promptDoc = fs.readFileSync(__dirname + '/../prompts/generate-model.md', 'utf8');
const kindLine = /"kind":\s*"([^"]+)"/.exec(promptDoc);
const verLine = /"schemaVersion":\s*"([^"]+)"/.exec(promptDoc);
t('the prompt asks for the kind this build reads',
  kindLine && kindLine[1] === app.SCHEMA.kind, kindLine ? kindLine[1] : 'no kind in the prompt');
t('the prompt asks for the pack version this build reads',
  verLine && verLine[1] === app.SCHEMA.version, verLine ? verLine[1] : 'no string schemaVersion in the prompt');

/* 3. samples/ are BARE models, because the server unmarshals them directly. They
      must also be wired correctly: every analyzer in one has to be pointed at a
      kind it actually checks, or the sample teaches the wrong thing. */
const sdir = __dirname + '/../samples';
const samples = fs.readdirSync(sdir).filter(f => f.endsWith('.json'));
t('there are samples for the embed to find', samples.length > 0, samples.join(' '));
samples.forEach(function (f) {
  const o = JSON.parse(fs.readFileSync(sdir + '/' + f, 'utf8'));
  t('samples/' + f + ' is a bare model, not a pack', !o.kind && Array.isArray(o.layers));
  t('samples/' + f + ' has an id the app can key on', typeof o.id === 'string' && o.id.length > 0, o.id);
  const bad = app.checksViolations(o);
  t('samples/' + f + ' wires every analyzer to a kind it checks', bad.length === 0,
    bad.map(function (v) { return v.analyzer + ' -> ' + v.target + ' (' + v.kind + ')'; }).join('; '));
  const kinds = [...new Set(o.nodes.map(function (n) { return n.kind; }))]
    .filter(function (k) { return !app.KIND_IDS.includes(k); });
  t('samples/' + f + ' uses only known node kinds', kinds.length === 0, kinds.join(','));
  const rels = [...new Set(o.edges.map(function (e) { return e.rel; }))]
    .filter(function (r) { return !(r in app.RELS); });
  t('samples/' + f + ' uses only known relationships', rels.length === 0, rels.join(','));
});

/* The Analyzers page opens one sample by filename and expects a specific id. */
t('the analyzer page template exists under the name it asks for',
  samples.indexOf('document-template.json') >= 0);
(function () {
  const tpl = JSON.parse(fs.readFileSync(sdir + '/document-template.json', 'utf8'));
  t('the analyzer page template has id m_template', tpl.id === 'm_template', tpl.id);
  t('it reads as a document review', app.modelDomain(tpl) === 'document-review', app.modelDomain(tpl));
  const fits = app.ANALYZER_IDS.filter(function (id) { return app.analyzerFits(id, tpl).ok; });
  t('all ten analyzers apply to it', fits.length === app.ANALYZER_IDS.length,
    fits.length + ' of ' + app.ANALYZER_IDS.length);
  t('it contains the CONTRADICTS pair the page promises',
    tpl.edges.some(function (e) { return e.rel === 'CONTRADICTS'; }));
})();

/* 3. A bare model must be refused, so the failure mode stays loud. */
t('a bare model is refused, not silently half-loaded',
  importVerdict({ id: 'm_x', layers: [], nodes: [] }).indexOf('refused') === 0);

console.log(fails ? '\n' + fails + ' FAILURE(S)' : '\nall assertions passed');
process.exit(fails ? 1 : 0);
