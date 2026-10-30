// DOM/Canvas stubs test control logic and request isolation, not visual rendering.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../scripts/replay_viewer_assets/app.js'),'utf8');
const flush=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
function boot(){
 const elements={},requests=[],timers=new Map();let nextTimer=0;
 const context=new Proxy({}, {get:(o,k)=>o[k]||(o[k]=()=>{}),set:(o,k,v)=>(o[k]=v,true)});
 class Element{
  constructor(id){this.id=id;this.value='';this.children=[];this.listeners={};this.style={};this.width=1600;this.height=1506;this.textContent='';}
  append(child){this.children.push(child);if(!this.value)this.value=child.value;}
  replaceChildren(){this.children=[];this.value='';}
  addEventListener(type,fn){this.listeners[type]=fn;}
  getContext(){return context;}
  fire(type){return this.listeners[type]?.();}
 }
 const document={getElementById:id=>elements[id]||(elements[id]=new Element(id)),createElement:()=>new Element('new')};
 for(const [id,v]of Object.entries({view:'radiant',hero:'all',trail:'15',speed:'1',time:'0'}))document.getElementById(id).value=v;
 const sandbox={document,Image:class{decode(){return Promise.resolve();}},setTimeout:fn=>{timers.set(++nextTimer,fn);return nextTimer;},clearTimeout:id=>timers.delete(id),console};
 sandbox.fetch=async url=>{
  requests.push(url);
  const q=new URL(url,'http://local').searchParams;const view=q.get('view');const tick=Number(q.get('tick'));
  let data;
  if(url==='/api/catalog')data={matches:[1,2],names:{14:'帕吉'}};
  else if(url.startsWith('/api/timeline'))data={frames:[{tick:0,time:0},{tick:30,time:1},{tick:35,time:1}],heroes:[{slot:0,hero_id:14}]};
  else data={view,tick,time:tick<30?0:1,players:[{player_slot:0,hero_id:14,visibility:view==='dire'?'hidden':'visible',life_state:view==='dire'?null:0,current_position:view==='dire'?null:{x:10000,y:10000},last_seen:null,quality_flags:[],segments:[]}]};
  return{ok:true,json:async()=>data};
 };
 vm.createContext(sandbox);vm.runInContext(source,sandbox);
 return{elements,requests,timers,sandbox};
}
test('death, dying and hidden sample counts are not labelled observation failure',async()=>{
 const s=boot();await flush();const original=s.sandbox.fetch;
 for(const [life,visibility,reason,label] of [[2,'visible','dead','死亡'],[1,'visible','dying','死亡过渡'],[null,'hidden','hidden','敌方隐藏']]){
  s.sandbox.fetch=async url=>{
   const r=await original(url),d=await r.json();
   if(url.startsWith('/api/frame'))Object.assign(d.players[0],{life_state:life,visibility,current_position:null,trail_breaks:2,break_reasons:{observation_unavailable:2,[reason]:2}});
   return {ok:true,json:async()=>d};
  };
  s.elements.time.value='1';s.elements.time.fire('input');await flush();
  const notes=s.elements.players.children[0].children.map(c=>c.textContent).join(' / ');
  assert.ok(notes.includes(label+' 2个采样点'),notes);
  assert.ok(!notes.includes('观测不足'),notes);
  if(life===1)assert.ok(notes.includes('死亡过渡'));
 }
});
test('default view, stepping, seek, hero filtering, and view isolation',async()=>{
 const s=boot();await flush();const e=s.elements;
 assert.equal(e.match.children.length,2);assert.equal(e.play.disabled,false);
 assert.ok(s.requests.filter(u=>u.startsWith('/api/timeline')||u.startsWith('/api/frame')).every(u=>u.includes('view=radiant')));
 e.next.fire('click');await flush();assert.equal(e.clock.textContent,'00:01');
 e.time.value='2';e.time.fire('input');await flush();assert.match(e.status.textContent,/重复游戏秒/);
 e.hero.value='128';e.hero.fire('change');assert.equal(e.players.children.length,0);
 const start=s.requests.length;e.view.value='dire';e.view.fire('change');assert.equal(e.players.children.length,0);await flush();
 assert.ok(s.requests.slice(start).every(u=>u.includes('view=dire')));assert.match(e['view-badge'].textContent,/夜魇/);
 assert.match(e.players.children[0].children[1].textContent,/隐藏/);
 e.play.fire('click');assert.equal(e.play.textContent,'暂停');const fn=Array.from(s.timers.values()).at(-1);await fn();await flush();assert.equal(Number(e.time.value),1);
 e.play.fire('click');assert.equal(e.play.textContent,'播放');
});
test('late all-knowing response cannot repaint after switching to a team view',async()=>{
 const s=boot();await flush();let resolveOld;
 const real=s.sandbox.fetch;
 s.sandbox.fetch=url=>url.includes('/api/frame')&&url.includes('view=omniscient')?new Promise(r=>{resolveOld=r;}):real(url);
 s.elements.view.value='omniscient';s.elements.view.fire('change');await flush();
 assert.equal(typeof resolveOld,'function');s.elements.view.value='dire';s.elements.view.fire('change');await flush();
 resolveOld({ok:true,json:async()=>({players:[],time:99999})});await flush();
 assert.match(s.elements['view-badge'].textContent,/夜魇/);assert.equal(s.elements.players.children.length,1);assert.equal(s.elements.clock.textContent,'00:00');
});

test('replaying at the end displays the first frame before advancing',async()=>{
 const s=boot();await flush();const e=s.elements;
 e.time.value='2';e.time.fire('input');await flush();
 assert.equal(e.clock.textContent,'00:01');
 await e.play.fire('click');await flush();
 assert.equal(Number(e.time.value),0);assert.equal(e.clock.textContent,'00:00');
 assert.match(s.requests.at(-1),/tick=0&/);assert.equal(e.play.textContent,'暂停');
});

test('event navigation is omniscient only and evidence renders as text',async()=>{
 const s=boot();await flush();assert.equal(s.elements['next-event'].disabled,true);
 const real=s.sandbox.fetch;
 s.sandbox.fetch=async url=>{
  const r=await real(url),d=await r.json();
  if(url.includes('view=omniscient')){
   if(url.startsWith('/api/timeline'))d.event_ticks=[30,35];
   else{d.event_evidence_status='available';d.players[0].jump_evidence=[{previous_tick:0,current_tick:30,distance:2000,category:'core_movement_event',jump_ref:'jumps[0]',events:[{log_type:'ITEM',inflictor_name:'<script>secret</script>',tick:20,scope:'core',roles:['attacker'],source_ref:'combat_log[0]'}]}];}
  }
  return {ok:true,json:async()=>d};
 };
 s.elements.view.value='omniscient';await s.elements.view.fire('change');await flush();
 assert.equal(s.elements['next-event'].disabled,false);
 s.elements['next-event'].fire('click');await flush();assert.equal(Number(s.elements.time.value),1);
 const panel=s.elements.players.children[0].children.find(c=>c.children.some(x=>x.textContent.includes('位移关联证据')));
 assert.ok(panel);assert.ok(panel.children.some(c=>c.textContent.includes('<script>secret</script>')));
 s.elements.view.value='radiant';await s.elements.view.fire('change');await flush();
 assert.equal(s.elements['next-event'].disabled,true);
 assert.ok(!s.elements.players.children[0].children.some(c=>c.children.some(x=>x.textContent.includes('位移关联证据'))));
});
