// DOM/Canvas contract regressions; these do not certify browser rendering.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../scripts/decision_review_assets/app.js'),'utf8');
const all=n=>[n,...n.children.flatMap(all)];
const content=n=>all(n).map(n=>n.textContent).join(' ');
const flush=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
function boot(input){
 const elements={},requests=[];
 const ctx=new Proxy({}, {get:(o,k)=>o[k]||(o[k]=()=>{}),set:(o,k,v)=>(o[k]=v,true)});
 class Element{
  constructor(){this.children=[];this.attrs={};this.textContent='';this.hidden=false;this.listeners={};this.width=1100;this.height=1035;}
  append(...children){this.children.push(...children);}
  replaceChildren(){this.children=[];}
  setAttribute(k,v){this.attrs[k]=v;}
  addEventListener(type,fn){this.listeners[type]=fn;}
  getContext(){return ctx;}
  getBoundingClientRect(){return this.rect||{left:10,top:20,width:550,height:517.5};}
  click(){return this.listeners.click?.();}
 }
 const document={getElementById:id=>elements[id]||(elements[id]=new Element()),createElement:()=>new Element()};
 const p={player_slot:0,hero_id:8,relation:'ally',visibility:'visible',life_state:0,current_position:{x:10000,y:11000},position_status:'available',last_seen:null};
 const make=id=>({case:{id,slot:0,match_id:1,tick:30,title:id,status:'manual',action_axis:'candidate',attention:'<script>unsafe</script>',action:'act',reason:'why',stop_condition:'stop',counterevidence:'unknown'},evidence:{decision_input:{time:1,tick:30,positions:[p],inventory:{slots:[]}},provenance:{raw_sha256:'pinned'},state_refs:[]},past_frames:[]});
 const data=input||{names:{8:'主宰'},advice_sha256:'sealed',cards:[make('first'),make('second')]};
 const sandbox={document,Image:class{decode(){return Promise.resolve();}},console};
 sandbox.fetch=async url=>{requests.push(url);return {ok:true,json:async()=>url==='/api/cases'?data:{frames:[{time:2,tick:60,players:[p]}]}};};
 vm.createContext(sandbox);vm.runInContext(source,sandbox);return{elements,requests,sandbox,data};
}
test('initial advice never requests future; explicit reveal is separate and switch clears it',async()=>{
 const s=boot();await flush();const e=s.elements;
 assert.deepEqual(s.requests,['/api/cases']);
 assert.equal(e.cases.children.length,2);
 assert.equal(e.outcome.hidden,true);
 assert.match(e.advice.children[0].children[1].textContent,/<script>/);
 await e.reveal.click();await flush();
 assert.equal(s.requests.at(-1),'/api/first-after.json');
 assert.equal(e.outcome.hidden,false);assert.equal(e.outcome.children.length,2);
 e.cases.children[1].click();
 assert.equal(e.outcome.hidden,true);assert.equal(e.outcome.children.length,0);
 assert.equal(e.reveal.disabled,false);assert.match(e.title.textContent,/second/);
});
test('late outcome from a previous case cannot paint current case',async()=>{
 const s=boot();await flush();let resolveOld;
 s.sandbox.fetch=url=>{s.requests.push(url);return new Promise(r=>{resolveOld=r;});};
 const pending=s.elements.reveal.click();await flush();
 s.elements.cases.children[1].click();
 resolveOld({ok:true,json:async()=>({frames:[{time:99999,tick:99999,players:[]}]})});
 await pending;await flush();
 assert.equal(s.elements.outcome.hidden,true);assert.equal(s.elements.outcome.children.length,0);
 assert.match(s.elements.title.textContent,/second/);
});
test('enhanced alternatives and unadmitted context render without fetching outcomes',async()=>{
 const s=boot();await flush();
 s.data.cards[0].enhancement={user_feedback:'compare farm vs fight',alternatives:[{name:'继续发育',conditions:'资源存在',opportunity_cost:'放弃支援',stop:'新威胁'}],unresolved:['TP就绪'],source_context:{last10s_hero_damage_count:2,last10s_participant_hero_ids:[8],history_game_seconds:60,own_farming_activity:{neutral_damage_records:3},friendly_recent_ward_placements:[],friendly_recent_smoke_activations:[]}};
 s.elements.cases.children[0].click();
 assert.equal(s.elements.enhancements.hidden,false);
 assert.ok(s.elements.enhancements.children.some(e=>e.textContent.includes('尚未准入')));
 assert.deepEqual(s.requests,['/api/cases']);
 s.elements.focus.value='0';s.elements.focus.listeners.change();
 s.elements.cases.children[1].click();
 assert.equal(s.elements.enhancements.hidden,true);
});
test('state card displays source cooldown but never asserts castability',async()=>{
 const s=boot();await flush();
 s.data.cards[0].enhancement={user_feedback:'review',alternatives:[],unresolved:[],source_context:{last10s_hero_damage_count:0,last10s_participant_hero_ids:[],history_game_seconds:60,own_farming_activity:{},friendly_recent_ward_placements:[],friendly_recent_smoke_activations:[]},live_state_card:{tick:30,level:14,health:{current:100,max:200},tp:{cooldown_source_value:0,charges:2},abilities:[{name:'juggernaut_omni_slash',level:2,cooldown_source_value:30.7,past_countdown_consistent:true}]}};
 s.elements.cases.children[0].click();
 const text=content(s.elements['hero-state']);
 assert.ok(text.includes('未证明可施放'));assert.ok(text.includes('30.7 秒'));
 assert.ok(text.includes('未认证 · 已定位解码范围异常'));
 assert.deepEqual(s.requests,['/api/cases']);
});
test('comparison review preserves draft across cases, exports restrictions and never fetches hidden state',async()=>{
 const s=boot();await flush();let saved;
 s.sandbox.Blob=class{constructor(chunks){this.text=chunks.join('');}};
 s.sandbox.URL={createObjectURL:b=>{saved=JSON.parse(b.text);return 'blob:review';},revokeObjectURL:()=>{}};
 s.sandbox.setTimeout=fn=>fn();
 const actions=['join','farm','reposition'];
 const x={team_state:[{relation:'enemy',hero_id:8,player_slot:128,position_status:'hidden',health:null,inventory:null}],verified_constraints:['无敌斩约30.7秒'],arrival:{formula:'冷却 + 通道 + 赶路',tp_cooldown_wait_source_seconds:3,warning:'不能给出到场区间'},alternatives:actions.map(action=>({action,name:action,requirements:'未知',potential_benefit:'待判断',opportunity_cost:'待判断',stop:'窗口关闭'})),blocking_unknowns:['合法落点'],annotation:{actions:actions.map(action=>({action,judgment:null,reason:null,conditions:[],evidence_refs:[]})),facts_that_could_change_judgment:[],outcome_revealed:null,protocol_approved:false,training_allowed:false}};
 s.data.cards[0].enhancement={user_feedback:'review',alternatives:[],unresolved:[],comparison_card:x,source_context:{last10s_hero_damage_count:0,last10s_participant_hero_ids:[],history_game_seconds:60,own_farming_activity:{},friendly_recent_ward_placements:[],friendly_recent_smoke_activations:[]}};
 s.elements.cases.children[0].click();
 const all=n=>[n,...n.children.flatMap(all)];
 let nodes=all(s.elements.enhancements);
 const select=nodes.find(n=>n.attrs['aria-label']==='join判断');select.value='conditional';select.listeners.change();
 const conditions=nodes.find(n=>n.attrs['aria-label']==='join成立条件（每行一条）');conditions.value='合法落点\n赶上窗口';conditions.listeners.input();
 await s.elements.reveal.click();await flush();
 s.elements.cases.children[1].click();s.elements.cases.children[0].click();
 nodes=all(s.elements.enhancements);
 assert.equal(nodes.find(n=>n.attrs['aria-label']==='join判断').value,'conditional');
 nodes.find(n=>n.textContent==='下载本案例试标草稿').click();
 assert.equal(saved.actions[0].judgment,'conditional');assert.deepEqual(saved.actions[0].conditions,['合法落点','赶上窗口']);
 assert.equal(saved.outcome_revealed,true);assert.equal(saved.protocol_approved,false);assert.equal(saved.training_allowed,false);
 assert.deepEqual(s.requests,['/api/cases','/api/first-after.json']);
});
test('case-specific review questions replace generic questions on switch without outcome reads',async()=>{
 const s=boot();await flush();
 s.data.cards[0].case.review_questions=[{axis:'attention',prompt:'大圣消失22秒，先看上方哪名英雄？'},{axis:'action',prompt:'无敌斩约31秒，收线还是准备支援？'}];
 s.elements.cases.children[0].click();
 assert.equal(s.elements['review-questions'].children.length,2);
 assert.match(s.elements['review-questions'].children[0].textContent,/22秒/);
 s.elements.cases.children[1].click();
 assert.equal(s.elements['review-questions'].children.length,4);
 assert.ok(!s.elements['review-questions'].children.some(n=>n.textContent.includes('22秒')));
 assert.deepEqual(s.requests,['/api/cases']);
});

function addHeroes(s){
 const d=s.data.cards[0].evidence.decision_input;
 d.positions.push({player_slot:1,hero_id:14,relation:'ally',visibility:'visible',position_status:'available',current_position:{x:15000,y:16000},last_seen:null});
 d.positions.push({player_slot:128,hero_id:114,relation:'enemy',visibility:'hidden',position_status:'hidden',current_position:null,last_seen:{position:{x:18000,y:18000},time:-21,source_tick:-630}});
 s.data.names[14]='帕吉';s.data.names[114]='齐天大圣';
 s.data.cards[0].enhancement={user_feedback:'review',alternatives:[],unresolved:[],source_context:{last10s_hero_damage_count:0,last10s_participant_hero_ids:[],history_game_seconds:60,own_farming_activity:{},friendly_recent_ward_placements:[],friendly_recent_smoke_activations:[]},live_state_card:{tick:30,level:14,health:{current:1313,max:1330},abilities:[{name:'juggernaut_omni_slash',level:2,cooldown_source_value:30.7,past_countdown_consistent:true}],items:[{slot:0,name:'item_magic_wand',cooldown_source_value:0,charges:20}],tp:{cooldown_source_value:0,charges:2}}};
 d.inventory={slots:[{group:'main',slot:0,status:'observed',item:'item_magic_wand'}]};
 s.elements.cases.children[0].click();
}
function clickHero(s,slot){
 const p=s.data.cards[0].evidence.decision_input.positions.find(p=>p.player_slot===slot),raw=p.current_position||p.last_seen.position;
 const rect=s.elements.map.getBoundingClientRect();
 s.elements.map.listeners.click({clientX:rect.left+(261+(raw.x-7487)*8356/18322)/8878*rect.width,clientY:rect.top+(26015-raw.y)/18322*rect.height});
}
test('scaled map click selects the nearest hero and blank clicks keep selection',async()=>{
 const s=boot();await flush();addHeroes(s);
 assert.match(content(s.elements['hero-state']),/主宰/);
 clickHero(s,1);assert.equal(s.elements['hero-select'].value,'1');
 assert.match(content(s.elements['hero-state']),/帕吉/);
 assert.ok(!content(s.elements['hero-state']).includes('30.7 秒'));
 s.elements.map.rect={left:120,top:70,width:1100,height:1035};
 clickHero(s,0);assert.equal(s.elements['hero-select'].value,'0');
 assert.match(content(s.elements['hero-state']),/30.7 秒/);
 assert.match(content(s.elements['hero-state']),/充能源读数 20/);
 s.elements.map.listeners.click({clientX:120,clientY:70});assert.equal(s.elements['hero-select'].value,'0');
 assert.deepEqual(s.requests,['/api/cases']);
});
test('filter limits hit testing; roster can select hidden or coordinate-less heroes',async()=>{
 const s=boot();await flush();addHeroes(s);
 s.elements.focus.value='0';s.elements.focus.listeners.change();clickHero(s,1);
 assert.equal(s.elements['hero-select'].value,'0');
 s.elements.focus.value='all';s.elements.focus.listeners.change();clickHero(s,128);
 assert.equal(s.elements['hero-select'].value,'128');
 assert.match(content(s.elements['hero-state']),/22 游戏秒前/);
 assert.match(content(s.elements['hero-state']),/不是当前位置/);
 const p=s.data.cards[0].evidence.decision_input.positions[2];p.last_seen=null;
 s.elements.cases.children[0].click();s.elements['hero-select'].value='128';s.elements['hero-select'].listeners.change();
 assert.match(content(s.elements['hero-state']),/齐天大圣/);
 assert.match(content(s.elements['hero-state']),/血量.*未知/);
 assert.deepEqual(s.requests,['/api/cases']);
});
test('past samples clear current health items and cooldown; returning restores them and case switch resets hero',async()=>{
 const s=boot();await flush();addHeroes(s);
 const c=s.data.cards[0];c.past_frames=[{tick:0,time:0,players:c.evidence.decision_input.positions}];
 s.elements.cases.children[0].click();
 assert.match(content(s.elements['hero-state']),/1313/);
 s.elements.history.children[0].click();
 let text=content(s.elements['hero-state']);assert.match(text,/历史位置采样/);
 for(const sentinel of ['1313','30.7','魔杖'])assert.ok(!text.includes(sentinel));
 s.elements.history.children[1].click();assert.match(content(s.elements['hero-state']),/30.7 秒/);
 clickHero(s,1);s.elements.cases.children[1].click();
 assert.equal(s.elements['hero-select'].value,'0');
 text=content(s.elements['hero-state']);for(const sentinel of ['帕吉','1313','30.7','魔杖'])assert.ok(!text.includes(sentinel));
 assert.deepEqual(s.requests,['/api/cases']);
});
test('visible same-identity row supplies health and inventory; hidden and wrong-identity rows never do',async()=>{
 const s=boot();await flush();addHeroes(s);
 const x=s.data.cards[0].enhancement;
 const row={player_slot:1,hero_id:14,visibility:'visible',health:{current:777,max:900},inventory:{slots:[{slot:0,group:'main',status:'observed',item:'item_possessed_mask'}]},source_ref:'friendly-source'};
 // Render only the inspector here so a malformed source row cannot pass via a duplicate UI.
 x.comparison_card={tick:30,team_state:[row]};
 s.elements['hero-select'].value='1';s.elements['hero-select'].listeners.change();
 assert.match(content(s.elements['hero-state']),/777 \/ 900/);
 assert.match(content(s.elements['hero-state']),/附魂面具/);
 x.comparison_card.tick=60;s.elements['hero-select'].listeners.change();
 assert.ok(!content(s.elements['hero-state']).includes('777'));
 x.comparison_card.tick=30;row.hero_id=8;s.elements['hero-select'].listeners.change();
 assert.ok(!content(s.elements['hero-state']).includes('777'));
 row.player_slot=128;row.hero_id=114;
 s.elements['hero-select'].value='128';s.elements['hero-select'].listeners.change();
 const text=content(s.elements['hero-state']);
 for(const sentinel of ['777','附魂面具','friendly-source'])assert.ok(!text.includes(sentinel));
 assert.deepEqual(s.requests,['/api/cases']);
});
test('wrong-tick live state is withheld and outcome reveal never changes the current inspector',async()=>{
 const s=boot();await flush();addHeroes(s);
 s.data.cards[0].enhancement.live_state_card.tick=60;s.elements['hero-select'].listeners.change();
 assert.ok(!content(s.elements['hero-state']).includes('1313'));
 assert.ok(!content(s.elements['hero-state']).includes('30.7'));
 const before=content(s.elements['hero-state']);await s.elements.reveal.click();await flush();
 assert.equal(content(s.elements['hero-state']),before);
 assert.deepEqual(s.requests,['/api/cases','/api/first-after.json']);
});
