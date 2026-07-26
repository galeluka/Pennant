/* Every template's findings, computed by the app's own auditModel rather than by
   a copy of it. A template that produces findings its own summary does not
   mention is a template that teaches the wrong lesson, so this prints them and
   the count is reviewed rather than asserted blindly. */
const fs = require('fs');

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
  '\nreturn { auditModel, modelDomain, analyzerFits, ANALYZER_IDS, checksViolations };')();

const dir = __dirname + '/../templates';
let fails = 0;
fs.readdirSync(dir).filter(f => f.endsWith('.json')).sort().forEach(f => {
  const model = JSON.parse(fs.readFileSync(dir + '/' + f, 'utf8')).model;
  const dom = app.modelDomain(model);
  const fit = app.ANALYZER_IDS.filter(id => app.analyzerFits(id, model).ok).length;
  const findings = app.auditModel(model);
  const bad = app.checksViolations(model);
  console.log(`\n${f}`);
  console.log(`  domain ${dom}   analyzers applying ${fit}/${app.ANALYZER_IDS.length}` +
              `   findings ${findings.length}   CHECKS violations ${bad.length}`);
  findings.forEach(x => console.log(`    ${x.sev.padEnd(6)} ${x.text}`));
  if (bad.length) { fails++; bad.forEach(v => console.log(`    VIOLATION ${v.analyzer} -> ${v.target}`)); }
});
console.log(fails ? '\nCHECKS violations present' : '\nno CHECKS violations');
process.exit(fails ? 1 : 0);
