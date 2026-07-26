/* Renders the new AI panel and both views that host it, in a stubbed DOM. */
const fs = require('fs');
const els = {};
const mkEl = (id) => (els[id] = els[id] || {
  id, value:'', checked:false, textContent:'', innerHTML:'', style:{}, dataset:{},
  classList:{toggle(){},add(){},remove(){},contains:()=>false},
  addEventListener(){}, appendChild(){}, remove(){}, click(){}, focus(){},
  setAttribute(){}, getAttribute:()=>null, querySelectorAll:()=>[], onclick:null, onchange:null,
});
global.document = { getElementById:(id)=>mkEl(id), querySelectorAll:()=>[], createElement:()=>mkEl('tmp'),
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
const m = /<script>\s*\n/.exec(html);
const src = html.slice(m.index + m[0].length, html.indexOf('</script', m.index + m[0].length));
const api = new Function(src + `
return { llmPanel, wireLlmPanel, llmOn, llmBase, llmModel, viewProfile, viewAdmin, state, WS, auth, LLM_MODELS };`)();

let fails = 0;
const t = (name, cond, extra) => { if(!cond){ fails++; console.log('FAIL  ' + name + (extra?'\n        '+extra:'')); } else console.log('PASS  ' + name); };

// --- unlocked, no key: the endpoint is editable
api.state.llm = { enabled:false, baseUrl:'', model:'', temperature:0.2 };
api.WS.llm = { keyPresent:false, baseUrl:'', model:'', locked:false };
let h = api.llmPanel();
t('unlocked renders an endpoint input', h.includes('id="llmUrl"'));
t('off shows the reassurance', h.includes('nothing leaves your machine'));
t('no key: tells you where a key goes', h.includes('KE_LLM_KEY'));
t('model datalist present', h.includes('list="llmModelList"') && h.includes('<datalist'));

// --- locked by the operator: no input, explains why
api.WS.llm = { keyPresent:true, baseUrl:'http://litellm:4000/v1', model:'default', locked:true };
h = api.llmPanel();
t('locked hides the endpoint input', !h.includes('id="llmUrl"'), 'input still present');
t('locked shows the pinned address', h.includes('http://litellm:4000/v1'));
t('locked explains the pin', h.includes('cannot change it'));
t('key present is reported without the key', h.includes('A key is set on the server') && !h.includes('sk-'));

// --- effective config resolution
api.state.llm = { enabled:true, baseUrl:'http://typed-by-user', model:'m1', temperature:0.2 };
t('pinned base wins over typed', api.llmBase() === 'http://litellm:4000/v1', api.llmBase());
api.WS.llm.locked = false;
t('typed base used when not pinned', api.llmBase() === 'http://typed-by-user', api.llmBase());
t('llmOn true when both present', api.llmOn() === true);
api.state.llm.model = '';
t('model falls back to the server default', api.llmModel() === 'default');
api.WS.llm.model = '';
t('llmOn false with no model anywhere', api.llmOn() === false);

// --- discovered models reach the datalist
api.LLM_MODELS.list = ['gpt-4o-mini','llama3.1:8b','claude-sonnet'];
h = api.llmPanel();
t('discovered models are offered', h.includes('llama3.1:8b') && h.includes('3 model(s)'));

// --- the two views render
api.state.llm = { enabled:false, baseUrl:'', model:'', temperature:0.2 };
const root = mkEl('root');
try { api.viewProfile(root); t('viewProfile renders', true); }
catch(e){ t('viewProfile renders', false, e.constructor.name + ': ' + e.message); }
try { api.viewAdmin(root); t('viewAdmin renders', true); }
catch(e){ t('viewAdmin renders', false, e.constructor.name + ': ' + e.message); }

console.log(fails ? '\n' + fails + ' FAILURE(S)' : '\nall assertions passed');
process.exit(fails ? 1 : 0);
