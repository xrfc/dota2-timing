// DOM contract for the coach app item page; not a substitute for browser checks.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../scripts/coach_app_assets/app.js'),'utf8');
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
const all=n=>[n,...n.children.flatMap(all)];
const text=n=>all(n).map(n=>n.textContent).join(' ');

function boot(){
 const elements={},requests=[];
 class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.textContent='';this.listeners={};this.dataset={};this.value='';this.style={props:{},setProperty:(k,v)=>{this.style.props[k]=v;}};this.className='';const self=this;this.classList={add:c=>{self.className+=' '+c;}};}
  get firstChild(){return this.children[0];}
  append(...c){this.children.push(...c);}
  replaceChildren(...c){this.children=[...c];}
  setAttribute(k,v){this.attrs[k]=String(v);}
  removeAttribute(k){delete this.attrs[k];}
  addEventListener(t,f){this.listeners[t]=f;}
 }
 const radiant=[new Element('button'),new Element('button')];radiant[0].dataset.radiant='1';radiant[1].dataset.radiant='0';
 const document={getElementById:id=>elements[id]||(elements[id]=new Element('div')),createElement:t=>new Element(t),querySelectorAll:()=>radiant};
 const meta={heroes:[{id:8,name:'主宰'},{id:1,name:'敌法师'},{id:2,name:'斧王'},{id:3,name:'祸乱之源'},{id:4,name:'血魔'},{id:5,name:'水晶室女'}],
  my_heroes:[{hero_id:8,position:1,name:'主宰'},{hero_id:30,position:5,name:'巫医'}],item_names:{bfury:'狂战斧'},minutes:[10,15],notes:['n'],run:'r'};
 const view=q=>({spec:[8,1],full_lineup:q.get('enemies').split(',').filter(Boolean).length===5,items:[{item:'bfury',train_n:1458,any_model:true,typical_minute:15,
  cells:[{minute:10,probability:0,base_rate:0,display_probability:0,source:'baseline'},{minute:15,probability:.7,base_rate:.64,display_probability:.7,source:'model'}]},
  {item:'blink',train_n:50,any_model:true,typical_minute:null,cells:[{minute:10,probability:.03,base_rate:.032,display_probability:.03,source:'model'},{minute:15,probability:.1,base_rate:.1,display_probability:.1,source:'baseline'}]}]});
 const sandbox={document,console,URLSearchParams,localStorage:{getItem(){throw new Error('blocked');},setItem(){throw new Error('blocked');}}};
 sandbox.fetch=async url=>{requests.push(url);const u=new URL(url,'http://x');return {ok:true,json:async()=>u.pathname==='/api/meta'?meta:view(u.searchParams)};};
 vm.createContext(sandbox);vm.runInContext(source,sandbox);
 return {elements,requests,radiant};
}

test('renders timing table from the API and survives blocked storage',async()=>{
 const s=boot();await flush();const e=s.elements;
 assert.equal(s.requests[0],'/api/meta');
 assert.match(s.requests[1],/^\/api\/item-timing\?hero=8&position=1&radiant=1&enemies=$/);
 assert.match(e['result-title'].textContent,/主宰 · 1号位/);
 assert.match(e['result-status'].textContent,/未填满 5 人/);
 const row=e['timing-body'].children[0];
 assert.match(text(row),/狂战斧/);assert.match(text(row),/15 分钟前/);
 const cell=row.children[2];
 assert.match(cell.className,/model/);assert.equal(cell.style.props['--p'],'0.700');
 assert.match(cell.title,/高分段平均 64%/);
});

test('enemy inputs are validated: unknown, duplicate and own hero ignored',async()=>{
 const s=boot();await flush();const inputs=s.elements.enemies.children;
 const names=['敌法师','敌法师','主宰','不存在','斧王'];
 names.forEach((n,i)=>{inputs[i].value=n;inputs[i].listeners.change();});
 await flush();
 assert.match(s.requests.at(-1),/enemies=1%2C2$/);
 assert.equal(inputs[1].attrs['aria-invalid'],'true');assert.equal(inputs[2].attrs['aria-invalid'],'true');assert.equal(inputs[3].attrs['aria-invalid'],'true');
 assert.match(s.elements['input-error'].textContent,/敌法师、主宰、不存在/);
 assert.ok(s.requests.every(u=>u==='/api/meta'||u.startsWith('/api/item-timing?')));
});

test('side and hero switches re-query',async()=>{
 const s=boot();await flush();
 s.radiant[1].listeners.click();await flush();
 assert.match(s.requests.at(-1),/radiant=0/);
 s.elements['my-heroes'].children[1].listeners.click();await flush();
 assert.match(s.requests.at(-1),/hero=30&position=5/);
});

test('model cells that barely move the baseline are not badged',async()=>{
 const s=boot();await flush();
 const blink=s.elements['timing-body'].children[1];
 assert.match(text(blink),/样本 50 · 偏少/);
 assert.ok(!/阵容调整/.test(text(blink)));
 assert.ok(!/model/.test(blink.children[1].className));
 assert.match(s.elements['result-status'].textContent,/未填满/);
});
