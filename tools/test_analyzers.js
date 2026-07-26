/* Exercises the new scoping functions inside the real page script. */
const fs = require('fs');
const path = '/mnt/user-data/outputs/pennant/tools/smoke.js';
// reuse the harness stubs by requiring nothing: replicate minimal globals
global.document = { getElementById:()=>null, querySelectorAll:()=>[], createElement:()=>({}),
  addEventListener(){}, body:{classList:{toggle(){}}}, documentElement:{} };
global.window = { addEventListener(){}, localStorage:{getItem:()=>null,setItem(){},removeItem(){}},
  location:{hash:''}, matchMedia:()=>({matches:false,addEventListener(){}}) };
global.localStorage = window.localStorage; global.location = window.location;
global.navigator = { sendBeacon:()=>true, clipboard:{writeText:async()=>{}} };
global.fetch = async () => ({ ok:false, status:0, text:async()=>'', json:async()=>({}) });
global.Blob = class {}; global.URL = { createObjectURL:()=>'', revokeObjectURL(){} };
global.FileReader = class { readAsText(){} readAsDataURL(){} };
global.vis = undefined; global.Chart = undefined;
global.getComputedStyle = () => ({ getPropertyValue: () => '' });
let raf=0; global.requestAnimationFrame = f => { if(raf++<2) f(0); return raf; };
global.cancelAnimationFrame = () => {};
process.on('unhandledRejection', () => {});

const html = fs.readFileSync(__dirname + '/../web/index.html', 'utf8');
// forward scan, same rule as the harness
// The first <script> in this file is the vendored vis-network include, which has
// a src attribute and an empty body. Take the first attribute-less one instead.
const m = /<script>\s*\n/.exec(html);
const start = m.index + m[0].length;
const end = html.indexOf('</script', start);
const src = html.slice(start, end);

const probe = `
return {
  modelDomain, analyzerFits, checksViolations, addAnalyzerNode,
  ANALYZER_IDS, REVIEW_DOMAINS, ANALYZER_SCOPE, uid
};`;
const api = new Function(src + probe)();

const node = (id,kind) => ({ id, layer:'l1', kind, label:id, props:{} });
const docM = { id:'d', layers:[{id:'l1'}], nodes:[node('doc','document'),node('c1','chapter'),node('k1','claim'),node('o1','obligation')], edges:[] };
const sysM = { id:'s', layers:[{id:'l1'}], nodes:[node('a1','app'),node('i1','integration'),node('d1','datastore')], edges:[] };
const srcM = { id:'r', layers:[{id:'l1'}], nodes:[node('r1','rule'),node('ct1','control'),node('t1','term')], edges:[] };

let fails = 0;
const t = (name, got, want) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log((ok?'PASS  ':'FAIL  ') + name + (ok ? '' : '\n        got  ' + JSON.stringify(got) + '\n        want ' + JSON.stringify(want)));
};

t('doc model domain', api.modelDomain(docM), 'document-review');
t('system model domain', api.modelDomain(sysM), 'system');
t('source model domain', api.modelDomain(srcM), 'source-review');
t('explicit override wins', api.modelDomain({...sysM, reviewDomain:'source-review'}), 'source-review');
t('null model', api.modelDomain(null), 'system');

const fitIds = mm => api.ANALYZER_IDS.filter(id => api.analyzerFits(id, mm).ok);
console.log('  doc fits   :', fitIds(docM).join(' '));
console.log('  source fits:', fitIds(srcM).join(' '));
console.log('  system fits:', fitIds(sysM).join(' ') || '(none)');
t('nothing applies to a system model', fitIds(sysM), []);
t('v_deviation applies to doc', api.analyzerFits('v_deviation', docM).ok, true);
t('v_deviation blocked on source (wrong domain)', api.analyzerFits('v_deviation', srcM).ok, false);
t('v_collision blocked on doc (no target kind present)', api.analyzerFits('v_collision', docM).ok, false);
console.log('  reason:', api.analyzerFits('v_collision', docM).reason);
console.log('  reason:', api.analyzerFits('v_deviation', srcM).reason);

// add / refuse
const mm = JSON.parse(JSON.stringify(docM));
const r1 = api.addAnalyzerNode(mm, 'v_deviation');
t('add applicable', r1.added, true);
const r2 = api.addAnalyzerNode(mm, 'v_deviation');
t('add twice refused', [r2.added, r2.reason], [false, 'already in this model']);
const r3 = api.addAnalyzerNode(mm, 'v_collision');
t('add non-applicable refused', r3.added, false);
t('refusal explains itself', r3.reason.length > 20, true);

// wiring violation: v_deviation checks document|chapter only
const bad = JSON.parse(JSON.stringify(docM));
bad.nodes.push({ id:'an1', layer:'l1', kind:'analyzer', label:'The Archivist', props:{ analyzerId:'v_deviation' } });
bad.edges.push({ id:'e1', from:'an1', to:'k1', rel:'CHECKS' });
bad.edges.push({ id:'e2', from:'an1', to:'c1', rel:'CHECKS' });
const v = api.checksViolations(bad);
t('one violation found', v.length, 1);
t('the wrong edge is the one reported', v[0] && v[0].target, 'k1');
t('clean model has none', api.checksViolations(docM), []);

console.log(fails ? '\n' + fails + ' FAILURE(S)' : '\nall assertions passed');
process.exit(fails ? 1 : 0);
