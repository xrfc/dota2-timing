// DOM contract for the coach app reference pages (timing, 针对装); not a substitute for browser checks.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../scripts/coach_app_assets/app.js'),'utf8');
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const all=n=>[n,...n.children.flatMap(all)];
const text=n=>all(n).map(n=>n.textContent).join(' ');

function boot(stored){
 const elements={},requests=[];
 class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.textContent='';this.listeners={};this.style={props:{},setProperty:(k,v)=>{this.style.props[k]=v;}};this.className='';const self=this;this.classList={add:c=>{self.className+=' '+c;}};}
  append(...c){this.children.push(...c);}
  replaceChildren(...c){this.children=[...c];}
  setAttribute(k,v){this.attrs[k]=String(v);}
  removeAttribute(k){delete this.attrs[k];}
  addEventListener(t,f){this.listeners[t]=f;}
 }
 const tabs=['items','situational','lane'].map(v=>{const t=new Element('button');t.dataset={view:v};return t;});
 const document={getElementById:id=>elements[id]||(elements[id]=new Element('div')),createElement:t=>new Element(t),querySelectorAll:()=>tabs};
 const sit={verdict:{passed:false,valid_n:240,improvement:.042,ci95:[-.007,.087],min_improvement:.01},
  juggernaut:{spec:[8,1],name:'主宰',games:1458,games_with_any:840,items:[{item:'monkey_king_bar',name:'金箍棒',first_n:259,first_share:.308,bought_n:324,bought_rate:.222}]},
  supports:[{spec:[30,5],name:'巫医',games:163,items:[{item:'glimmer_cape',name:'微光披风',n:95,rate:.583,small:false,fixed:true},{item:'pipe',name:'洞察烟斗',n:0,rate:0,small:true,fixed:false}]}],
  notes:['m'],runs:['a','b']};
 const meta={heroes:[{id:8,name:'主宰'},{id:30,name:'巫医'}],my_heroes:[{hero_id:8,position:1,name:'主宰'},{hero_id:30,position:5,name:'巫医'}],
  item_names:{bfury:'狂战斧'},minutes:[10,15],notes:['n'],run:'r'};
 const view=q=>({spec:[Number(q.get('hero')),Number(q.get('position'))],full_lineup:false,items:[{item:'bfury',train_n:Number(q.get('hero'))===8?1458:60,any_model:false,typical_minute:15,
  cells:[{minute:10,probability:0,base_rate:0,display_probability:0,source:'baseline'},{minute:15,probability:.64,base_rate:.64,display_probability:.64,source:'baseline'}]}]});
 const storage=stored===undefined?{getItem(){throw new Error('blocked');},setItem(){throw new Error('blocked');}}:{data:{'coach-app-items-v2':stored},getItem(k){return this.data[k]??null;},setItem(k,v){this.data[k]=v;}};
 const sandbox={document,console,URLSearchParams,localStorage:storage};
 sandbox.fetch=async url=>{requests.push(url);const u=new URL(url,'http://x');return {ok:true,json:async()=>u.pathname==='/api/meta'?meta:u.pathname==='/api/situational'?sit:view(u.searchParams)};};
 vm.createContext(sandbox);vm.runInContext(source,sandbox);
 return {elements,requests,storage,tabs};
}

test('renders the baseline table and requests only hero and position',async()=>{
 const s=boot();await flush();const e=s.elements;
 assert.deepEqual(s.requests,['/api/meta','/api/item-timing?hero=8&position=1']);
 assert.match(e['result-title'].textContent,/主宰 · 1号位 高分段出装节奏/);
 assert.match(e['result-status'].textContent,/不随阵容变化/);
 const row=e['timing-body'].children[0];
 assert.match(text(row),/狂战斧/);assert.match(text(row),/15 分钟前/);
 assert.equal(row.children[2].style.props['--p'],'0.640');
 assert.ok(!/阵容调整/.test(text(e['timing-body'])));
});

test('hero switch re-queries, flags small samples and persists selection',async()=>{
 const s=boot(null);await flush();
 s.elements['my-heroes'].children[1].listeners.click();await flush();
 assert.equal(s.requests.at(-1),'/api/item-timing?hero=30&position=5');
 assert.match(text(s.elements['timing-body']),/样本 60 · 偏少/);
 assert.equal(JSON.parse(s.storage.data['coach-app-items-v2']).spec,'30:5');
});

test('stored selection is restored; unknown stored hero falls back',async()=>{
 let s=boot(JSON.stringify({spec:'30:5'}));await flush();
 assert.equal(s.requests[1],'/api/item-timing?hero=30&position=5');
 s=boot(JSON.stringify({spec:'99:1'}));await flush();
 assert.equal(s.requests[1],'/api/item-timing?hero=8&position=1');
});

test('situational tab shows baseline shares, the unproven verdict and support flags',async()=>{
 const s=boot(null);await flush();
 assert.ok(!s.requests.includes('/api/situational'));  // loaded lazily
 s.tabs[1].listeners.click();await flush();
 const e=s.elements;
 assert.equal(s.requests.at(-1),'/api/situational');
 assert.equal(e['view-situational'].hidden,false);assert.equal(e['view-items'].hidden,true);
 assert.equal(s.tabs[1].attrs['aria-current'],'page');assert.equal(s.tabs[0].attrs['aria-current'],undefined);
 assert.match(e['sit-title'].textContent,/主宰 · 1号位 针对装参照/);
 assert.match(e['sit-verdict'].textContent,/未被可靠证实/);assert.match(e['sit-verdict'].textContent,/含 0/);
 assert.match(text(e['sit-body']),/金箍棒/);assert.match(text(e['sit-body']),/31%/);
 e['sit-heroes'].children[1].listeners.click();
 assert.match(e['sit-title'].textContent,/巫医 · 5号位/);assert.equal(e['sit-verdict'].textContent,'');
 const rows=e['sit-body'].children;
 assert.match(text(rows[0]),/固定装/);assert.match(text(rows[1]),/样本少/);
 assert.deepEqual(JSON.parse(s.storage.data['coach-app-items-v2']),{spec:'8:1',view:'situational',sitSpec:'30:5'});
 assert.equal(s.tabs[2].listeners.click,undefined);  // unfinished tabs stay inert
});

test('stored situational view and hero are restored on load',async()=>{
 const s=boot(JSON.stringify({spec:'8:1',view:'situational',sitSpec:'30:5'}));await flush();
 assert.ok(s.requests.includes('/api/situational'));
 assert.match(s.elements['sit-title'].textContent,/巫医/);
});
