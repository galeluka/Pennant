const fs=require('fs');
global.document={getElementById:()=>null,querySelectorAll:()=>[],createElement:()=>({}),addEventListener(){},body:{classList:{toggle(){}}},documentElement:{}};
global.window={addEventListener(){},localStorage:{getItem:()=>null,setItem(){},removeItem(){}},location:{hash:''},matchMedia:()=>({matches:false,addEventListener(){}})};
global.localStorage=window.localStorage;global.location=window.location;
global.navigator={sendBeacon:()=>true,clipboard:{writeText:async()=>{}}};
global.fetch=async()=>({ok:false,status:0,text:async()=>'',json:async()=>({})});
global.Blob=class{};global.URL={createObjectURL:()=>'',revokeObjectURL(){}};
global.FileReader=class{readAsText(){}readAsDataURL(){}};
global.vis=undefined;global.Chart=undefined;global.getComputedStyle=()=>({getPropertyValue:()=>''});
let raf=0;global.requestAnimationFrame=f=>{if(raf++<2)f(0);return raf;};global.cancelAnimationFrame=()=>{};
process.on('unhandledRejection',()=>{});
const h=fs.readFileSync(__dirname + '/../web/index.html', 'utf8');
const m=/<script>\s*\n/.exec(h);
const app=new Function(h.slice(m.index+m[0].length,h.indexOf('</script',m.index+m[0].length))+
 '\nreturn {PLANS,PLAN_IDS,PLAN_KEYS,plan,planId,can,planLimit,limitLabel,planUpsell,state,llmOn,IMPORT_MAX_BYTES,KINDS,RELS};')();
let f=0; const t=(n,c,x)=>{ if(!c){f++;console.log('FAIL  '+n+(x?'  '+x:''));} else console.log('PASS  '+n+(x?'  ('+x+')':'')); };

t('default plan is self-hosted', app.planId()==='ce', app.planId());
t('self-hosted has every entitlement', app.PLAN_KEYS.filter(k=>!app.PLANS.ce[k]).length===3,
  'except crossModel/sso/audit: '+app.PLAN_KEYS.filter(k=>!app.PLANS.ce[k]).join(','));
t('self-hosted models unlimited', app.PLANS.ce.models===Infinity);
t('limitLabel renders Infinity', app.limitLabel(Infinity)==='unlimited');

app.state.plan='free';
t('free plan capped by nodes not models', app.planLimit('nodes')===2000 && app.planLimit('models')===Infinity, 'nodes='+app.planLimit('nodes'));
t('free plan has no AI', app.can('ai')===false);
t('llmOn is false on free even if configured', (()=>{ app.state.llm={enabled:true,baseUrl:'http://x',model:'m'}; return app.llmOn()===false; })());
t('upsell names the plans that allow AI', /Studio/.test(app.planUpsell('ai')), app.planUpsell('ai'));

app.state.plan='team';
t('team unlocks crossModel', app.can('crossModel')===true);
t('team has no SSO', app.can('sso')===false);
app.state.plan='enterprise';
t('enterprise has SSO and audit', app.can('sso')&&app.can('audit'));
t('enterprise licence is commercial', app.PLANS.enterprise.licence==='commercial');
t('enterprise is not hosted', app.PLANS.enterprise.hosted===false);

app.state.plan='nonsense';
t('unknown plan falls back to self-hosted', app.planId()==='ce', app.planId());

t('import cap is 8 MB', app.IMPORT_MAX_BYTES===8388608);
t('vocabulary tables reachable for import check', !!app.KINDS.claim && !!app.RELS.CHECKS);
console.log(f?'\n'+f+' failed':'\nall plan assertions passed');
process.exit(f?1:0);
