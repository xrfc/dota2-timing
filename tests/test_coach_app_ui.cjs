// DOM contract for the coach app timing reference page; not a substitute for browser checks.
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
  addEventListener(t,f){this.listeners[t]=f;}
 }
 const document={getElementById:id=>elements[id]||(elements[id]=new Element('div')),createElement:t=>new Element(t)};
 const meta={heroes:[{id:8,name:'主宰'},{id:30,name:'巫医'}],my_heroes:[{hero_id:8,position:1,name:'主宰'},{hero_id:30,position:5,name:'巫医'}],
  item_names:{bfury:'狂战斧'},minutes:[10,15],notes:['n'],run:'r'};
 const view=q=>({spec:[Number(q.get('hero')),Number(q.get('position'))],full_lineup:false,items:[{item:'bfury',train_n:Number(q.get('hero'))===8?1458:60,any_model:false,typical_minute:15,
  cells:[{minute:10,probability:0,base_rate:0,display_probability:0,source:'baseline'},{minute:15,probability:.64,base_rate:.64,display_probability:.64,source:'baseline'}]}]});
 const storage=stored===undefined?{getItem(){throw new Error('blocked');},setItem(){throw new Error('blocked');}}:{data:{'coach-app-items-v2':stored},getItem(k){return this.data[k]??null;},setItem(k,v){this.data[k]=v;}};
 const sandbox={document,console,URLSearchParams,localStorage:storage};
 sandbox.fetch=async url=>{requests.push(url);const u=new URL(url,'http://x');return {ok:true,json:async()=>u.pathname==='/api/meta'?meta:view(u.searchParams)};};
 vm.createContext(sandbox);vm.runInContext(source,sandbox);
 return {elements,requests,storage};
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
