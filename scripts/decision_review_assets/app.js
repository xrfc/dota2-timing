'use strict';
const $=id=>document.getElementById(id);
const image=new Image();
let data,selected,epoch=0,activeMapFrame,selectedHero,mapMarkers=[];
const reviewDrafts=new Map();
const time=t=>`${Math.floor(t/60).toString().padStart(2,'0')}:${Math.floor(t%60).toString().padStart(2,'0')}`;
const hero=id=>data.names[String(id)]||`英雄 ${id}`;
const itemNames={bfury:'狂战斧',yasha:'夜叉',magic_wand:'魔杖',power_treads:'动力鞋',wind_lace:'风灵之纹',clarity:'净化药水',tpscroll:'回城卷轴',mjollnir:'雷神之锤（大电锤）',quelling_blade:'压制之刃',pers:'坚韧球',broadsword:'阔剑',recipe_bfury:'狂战斧配方',diadem:'王冠组件（diadem）',javelin:'标枪',gloves:'加速手套',possessed_mask:'附魂面具'};
const item=s=>itemNames[s?.replace(/^item_/,'')]||s||'未解析物品';
const status={available:'当前可靠位置',hidden:'隐藏',visibility_unknown:'可见性未知',dying:'死亡过渡',dead:'死亡',state_missing:'状态缺失',no_sample:'当前无采样',duplicate_tick:'同tick重复，扣留位置',position_withheld:'当前坐标未通过可靠投影'};
function el(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function paragraph(parent,label,text){const p=el('p');const s=el('span',label+'：');s.className='label';p.append(s,el('span',text));parent.append(p);}
async function json(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw Error('案例读取失败，请检查服务日志与证据完整性');return r.json();}
const abilityNames={juggernaut_blade_fury:'剑刃风暴',juggernaut_healing_ward:'治疗守卫',juggernaut_blade_dance:'剑舞',juggernaut_swift_slash:'迅风斩',juggernaut_omni_slash:'无敌斩'};
const slotGroups={main:'主槽',backpack:'背包',reserve:'储备槽',special_unverified:'特殊槽（语义待核）'};
function cooldown(entry){
 const value=entry?.cooldown_source_value;
 if(!Number.isFinite(value)||value<0)return 'CD 未知';
 if(value===0)return 'CD 源读数 0 · 未证明可施放';
 return entry.past_countdown_consistent?`CD 约 ${value.toFixed(1)} 秒（过去倒计时一致）`:`CD 源读数 ${value.toFixed(2)}（时间语义未认证）`;
}
function mapPoint(raw){return {x:(261+(raw.x-7487)*8356/18322)/8878,y:(26015-raw.y)/18322};}
function selectHero(slot){if($('focus').value&&$('focus').value!=='all'&&$('focus').value!==String(slot))$('focus').value='all';selectedHero=slot;$('hero-select').value=String(slot);if(activeMapFrame)showMap(activeMapFrame);}
function renderHeroState(){
 const parent=$('hero-state');parent.replaceChildren();
 const frame=activeMapFrame,p=frame?.players.find(p=>p.player_slot===selectedHero);
 if(!p){paragraph(parent,'状态','该采样无此英雄记录，不能沿用其他时点状态。');return;}
 const d=selected.evidence.decision_input,x=selected.enhancement;
 const isDecision=frame.tick===d.tick,visible=p.visibility==='visible';
 const rows=isDecision&&visible&&x?.comparison_card?.tick===frame.tick?x.comparison_card.team_state.filter(r=>r.player_slot===p.player_slot&&r.hero_id===p.hero_id&&r.visibility==='visible'):[];
 const row=rows?.length===1?rows[0]:null;
 const live=isDecision&&visible&&p.player_slot===selected.case.slot&&x?.live_state_card?.tick===frame.tick?x.live_state_card:null;
 const friendly=(selected.case.view||'radiant')==='radiant'?p.player_slot<128:p.player_slot>=128;
 parent.append(el('h3',`${hero(p.hero_id)} · ${friendly?'友方':'敌方'}${row?.level!=null||live?.level!=null?` · 等级 ${row?.level??live.level}`:''}`));
 paragraph(parent,'采样',`${time(frame.time)} · tick ${frame.tick}${isDecision?' · 决策时点':' · 历史位置采样（无同刻战力卡）'}`);
 paragraph(parent,'位置',status[p.position_status]||p.position_status||'未知');
 if(!p.current_position&&p.last_seen)paragraph(parent,'最后可见',`${time(p.last_seen.time)} · ${Math.max(0,frame.time-p.last_seen.time)} 游戏秒前；不是当前位置或已到场证据`);
 const hp=row?.health||live?.health;
 paragraph(parent,'血量',hp?`${hp.current??'未知'} / ${hp.max??'未知'}（同刻来源观测）`:'未知 · 没有该采样可用的可见血量证据');
 if(hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0){const bar=el('progress');bar.max=hp.max;bar.value=Math.max(0,Math.min(hp.current,hp.max));bar.setAttribute('aria-label',`${hero(p.hero_id)}血量 ${hp.current}/${hp.max}`);parent.append(bar);}
 paragraph(parent,'蓝量',live?'未认证 · 已定位解码范围异常，旧读数不作为游戏蓝量或施放依据':'未知 · 没有该采样已认证蓝量');
 parent.append(el('h4','技能与 TP'));
 const abilities=live?.abilities.filter(a=>!a.name.startsWith('special_bonus_'))||[];
 for(const a of abilities){const n=el('div');n.className='hero-entry';n.append(el('strong',`${abilityNames[a.name]||a.name} · 等级 ${a.level??'未知'}`),el('small',`${a.hidden?'隐藏技能；':a.level===0?'未学习；':''}${cooldown(a)}`));parent.append(n);}
 if(!abilities.length)paragraph(parent,'技能 CD','未知 · 当前没有该英雄同刻技能冷却取证，不能用技能等级或过去施法代替');
 paragraph(parent,'TP',live?.tp?`${cooldown(live.tp)}；卷轴充能源读数 ${live.tp.charges??'未知'}`:'CD / 充能未知；持有卷轴不代表能立刻 TP');
 paragraph(parent,'施放条件','CD 为 0 不等于能施放；蓝量、控制/禁用、目标与落点等条件尚未完整核验。');
 parent.append(el('h4','装备 · 按槽位'));
 const inventory=row?.inventory||(isDecision&&visible&&p.player_slot===selected.case.slot?d.inventory:null);
 if(inventory?.slots.length){
  const grid=el('div');grid.className='hero-items';
  for(const s of inventory.slots){if(s.status==='empty'&&s.group==='reserve')continue;
   const n=el('div');n.className='hero-entry';n.append(el('small',`${slotGroups[s.group]||'槽位'} ${s.slot}`),el('strong',s.status==='empty'?'空槽':s.status==='observed'?item(s.item):'未知，非空槽'));
   const matching=live?.items?.filter(i=>i.slot===s.slot&&i.name===s.item)||[],probe=matching.length===1?matching[0]:null;
   if(s.status==='observed')n.append(el('small',probe?`${cooldown(probe)}${probe.charges>0?`；充能源读数 ${probe.charges}`:''}`:'主动 CD / 充能未知'));
   grid.append(n);
  }parent.append(grid);
  paragraph(parent,'装备边界','持有不等于主动可用；背包/特殊槽不冒充主槽。未计算被动收益，空储备槽折叠省略。');
 }else paragraph(parent,'装备',!isDecision?'未知 · 历史地图没有同刻装备卡':!friendly?'未知 · 未建立敌方装备检查证据，不读取隐藏库存':'未知 · 同刻库存缺失或未通过核验');
 const details=el('details');details.append(el('summary','该英雄的来源与未认证原始读数'));details.append(el('pre',JSON.stringify({tick:frame.tick,position_source:p.source_tick??frame.tick,state_ref:row?.source_ref??null,live_state:live||null},null,2)));parent.append(details);
}
$('hero-select').addEventListener('change',()=>selectHero(Number($('hero-select').value)));
$('map').addEventListener('click',event=>{
 const rect=$('map').getBoundingClientRect();if(!rect.width||!rect.height)return;
 const candidates=mapMarkers.map(p=>({...p,distance:Math.hypot(event.clientX-rect.left-p.x*rect.width,event.clientY-rect.top-p.y*rect.height)})).filter(p=>p.distance<=26).sort((a,b)=>a.distance-b.distance);
 if(candidates.length)selectHero(candidates[0].slot);
});
function draw(canvas,players,target){
 if(canvas===$('map'))mapMarkers=[];
 const c=canvas.getContext('2d');c.setTransform(canvas.width/8878,0,0,canvas.height/8356,0,0);c.clearRect(0,0,8878,8356);c.drawImage(image,0,0,8878,8356);
 for(const p of players){if(canvas===$('map')&&$('focus').value&&$('focus').value!=='all'&&String(p.player_slot)!==$('focus').value)continue;const current=p.current_position,last=p.last_seen;const raw=current||last?.position;if(!raw)continue;
  const point=mapPoint(raw),x=point.x*8878,y=point.y*8356;if(x<0||y<0||x>=8878||y>=8356)continue;
  if(canvas===$('map'))mapMarkers.push({...point,slot:p.player_slot});
  c.strokeStyle=p.player_slot<128?'#9affd1':'#ff9e99';c.fillStyle=c.strokeStyle;c.lineWidth=24;c.setLineDash(current?[]:[35,25]);c.beginPath();c.arc(x,y,78,0,Math.PI*2);if(current)c.fill();c.stroke();c.setLineDash([]);
  if(p.player_slot===target){c.strokeStyle='#ffffff';c.beginPath();c.arc(x,y,130,0,Math.PI*2);c.stroke();}
  if(canvas===$('map')&&p.player_slot===selectedHero){c.strokeStyle='#5ddfff';c.lineWidth=32;c.beginPath();c.arc(x,y,180,0,Math.PI*2);c.stroke();}
  c.font='bold 120px sans-serif';c.textAlign='center';c.strokeStyle='#101920';c.lineWidth=30;
  const label=hero(p.hero_id)+(current?'':` 最后${time(last.time)}`);c.strokeText(label,x,y-150);c.fillText(label,x,y-150);
 }
}
function showMap(frame){activeMapFrame=frame;draw($('map'),frame.players,selected.case.slot);$('map-time').textContent=`地图采样 ${time(frame.time)} · tick ${frame.tick}`;renderHeroState();}
function renderComparison(parent,x,cs){
 parent.append(el('h3','支援 vs 刷钱：条件对照与试标草稿'));
 paragraph(parent,'当前边界','已有反馈的开发案例，不是盲评。关键事实未齐，可讨论条件，不能强制生成完整动作标签。');
 paragraph(parent,'英雄信息','双方血量、装备和已取证CD已集中到地图旁的英雄状态面板，点击英雄或用名单选择。');
 for(const c of x.verified_constraints)paragraph(parent,'已观测约束',c);
 paragraph(parent,'到场拆解',x.arrival.formula);
 paragraph(parent,'TP冷却等待源读数',x.arrival.tp_cooldown_wait_source_seconds===null?'未知':`${x.arrival.tp_cooldown_wait_source_seconds.toFixed(2)}秒；不是总到场时间`);
 paragraph(parent,'到场区间',x.arrival.warning);
 paragraph(parent,'蓝量取证','两例原生网络范围上限65536被早期补丁改为8192（schema时build=0，随后为6965）；旧值未修正，不能用于耗蓝或可施放判断。');
 for(const a of x.alternatives){const section=el('article');section.append(el('h4',a.name));for(const [label,key] of [['成立条件','requirements'],['潜在贡献','potential_benefit'],['机会成本','opportunity_cost'],['重新判断条件','stop']])paragraph(section,label,a[key]);parent.append(section);}
 paragraph(parent,'仍缺关键事实',x.blocking_unknowns.join('；'));
 const draft=reviewDrafts.get(cs.id)||JSON.parse(JSON.stringify(x.annotation));reviewDrafts.set(cs.id,draft);
 const form=el('section');form.append(el('h4','试标草稿：允许多项合理，也允许信息不足'));
 paragraph(form,'保存方式','仅本页内存暂存，切案例保留，刷新后丢失；下载JSON自行保存。不回写服务器、不进入训练。');
 const labels={acceptable:'可接受',conditional:'有条件接受',not_recommended:'不推荐',insufficient_evidence:'信息不足'};
 for(const a of draft.actions){const label=el('label',x.alternatives.find(v=>v.action===a.action).name+'：');const select=el('select');select.setAttribute('aria-label',`${a.action}判断`);for(const [value,text] of [['','暂不填写'],...Object.entries(labels)]){const o=el('option',text);o.value=value;select.append(o);}select.value=a.judgment||'';select.addEventListener('change',()=>{a.judgment=select.value||null;});label.append(select);form.append(label);const reason=el('textarea');reason.setAttribute('aria-label',`${a.action}理由、条件及可改变判断的事实`);reason.value=a.reason||'';reason.addEventListener('input',()=>{a.reason=reason.value||null;});form.append(reason);for(const [key,title] of [['conditions','成立条件（每行一条）'],['evidence_refs','证据引用（每行一条）']]){const field=el('textarea');field.setAttribute('aria-label',`${a.action}${title}`);field.placeholder=title;field.value=a[key].join('\n');field.addEventListener('input',()=>{a[key]=field.value.split('\n').map(v=>v.trim()).filter(Boolean);});form.append(field);}}
 const changes=el('textarea');changes.setAttribute('aria-label','哪些事实可能改变判断（每行一条）');changes.placeholder='哪些事实可能改变判断（每行一条）';changes.value=draft.facts_that_could_change_judgment.join('\n');changes.addEventListener('input',()=>{draft.facts_that_could_change_judgment=changes.value.split('\n').map(v=>v.trim()).filter(Boolean);});form.append(changes);const save=el('button','下载本案例试标草稿');save.addEventListener('click',()=>{draft.outcome_revealed=Boolean(draft.outcome_revealed)||!$('outcome').hidden;const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));const a=el('a');a.href=url;a.download=`${cs.id}-review-draft.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});form.append(save);parent.append(form);
}
$('focus').addEventListener('change',()=>{if(activeMapFrame)showMap(activeMapFrame);});
function render(index){
 epoch++;selected=data.cards[index];const {case:cs,evidence:e}=selected,d=e.decision_input;selectedHero=cs.slot;
 $('hero-select').replaceChildren();for(const p of d.positions){const o=el('option',`${hero(p.hero_id)} · ${p.relation==='ally'?'友':'敌'}`);o.value=String(p.player_slot);$('hero-select').append(o);}$('hero-select').value=String(selectedHero);
 for(const [i,b] of Array.from($('cases').children).entries())b.setAttribute('aria-pressed',String(i===index));
 $('title').textContent=`案例 ${index+1} · ${cs.title}`;$('identity').textContent=`比赛 ${cs.match_id} · 天辉主宰 · ${time(d.time)} · tick ${cs.tick}`;
 $('case-status').textContent=cs.status;$('advice').replaceChildren();
 $('review-questions').replaceChildren();
 const questions=cs.review_questions||[
  {prompt:`${time(d.time)}这一刻，你会先看地图上哪名英雄或哪块区域？点名一项最先确认的信息即可。`},
  {prompt:'主宰下一步优先收线、清野、准备支援还是换区？当前信息不足以选择也可以。'},
  {prompt:'如果按你的动作执行，具体哪名敌人的露头/失踪、哪条退路变化会让你停手？这个信号单独出现够不够？'},
  {prompt:'双方血量/关键技能、TP落点和赶路、本地安全资源，最先补哪一项会改变选择？什么结果会让你改选？'}
 ];for(const q of questions)$('review-questions').append(el('li',q.prompt));
 $('focus').replaceChildren();for(const [value,label] of [['all','全部英雄'],...d.positions.map(p=>[String(p.player_slot),`${p.relation==='ally'?'友':'敌'} · ${hero(p.hero_id)}`])]){const o=el('option',label);o.value=value;$('focus').append(o);}$('focus').value='all';
 for(const [label,key] of [['注意对象','attention'],['行动倾向','action_axis'],['具体动作','action'],['理由','reason'],['停止与撤退条件','stop_condition'],['反证与局限','counterevidence']])paragraph($('advice'),label,cs[key]);
 $('inventory-warning').textContent='槽位与持有已经观测；主槽不等于尚未送达。未核验的是主动冷却、充能和切背包延迟，不代表狂战斧、夜叉等被动效果无效；被动收益数值未计算。隐藏敌方库存不读取。';
 $('inventory').replaceChildren();const groups={main:'主槽',backpack:'背包',reserve:'储备槽',special_unverified:'特殊槽（语义待核）'};
 const inv=d.inventory;
 if(!inv.slots.length)$('inventory').append(el('li','库存未知：缺少唯一、身份匹配的同tick状态'));
 for(const s of inv.slots){if(s.status==='empty')continue;$('inventory').append(el('li',`${groups[s.group]} ${s.slot}：${s.status==='observed'?item(s.item):'未知，不能当作空槽'} · 主动就绪未核验／被动收益未计算`));}
 $('positions').replaceChildren();
 for(const p of d.positions){const last=p.last_seen;const label=status[p.position_status]||p.position_status;
  const note=!p.current_position&&last?`；最后可见 ${time(last.time)}，${last.age_ticks} tick / ${last.age_game_seconds}游戏秒前` : '';
  $('positions').append(el('li',`${p.relation==='ally'?'友':'敌'} · ${hero(p.hero_id)}：${label}${note}`));
 }
 $('missing').replaceChildren();paragraph($('missing'),'缺失','血蓝单位和技能可用性、兵线/目标状态、完整地形/迷雾、敌方已知库存。');paragraph($('missing'),'建议来源','人工候选，不是机器学习或因果结论。原生直线距离不是可走路径、到达时间或技能范围。');
 $('provenance').textContent=JSON.stringify({source:e.provenance,state_refs:e.state_refs,advice_sha256:data.advice_sha256},null,2);
 const extra=$('enhancements');extra.replaceChildren();extra.hidden=!selected.enhancement;
 if(selected.enhancement){
  const x=selected.enhancement,c=x.source_context;extra.append(el('h3','增强复审：行动条件与机会成本'));
  paragraph(extra,'评审阶段','用户反馈后的修订，已知原案例后续；不是新的盲评，不生成训练标签。');
  paragraph(extra,'你的原评审（历史原文保留）',x.user_feedback);
  if(x.review_update){paragraph(extra,'本次追加反馈',x.review_update.user_feedback_verbatim);paragraph(extra,'修订后的解释',x.review_update.user_game_interpretation);paragraph(extra,'已核对与未证实','已核对最后可见至当前相隔22游戏秒；跳树/TP转移是可能性，不证明已到团战，也不证明仍在原地。');}
  if(x.comparison_card)renderComparison(extra,x.comparison_card,cs);
  for(const a of x.alternatives){const section=el('article');section.append(el('h4',a.name));paragraph(section,'成立条件',a.conditions);paragraph(section,'机会成本',a.opportunity_cost);paragraph(section,'停止条件',a.stop);extra.append(section);}
  extra.append(el('h3','来源附录：尚未准入模型，不等同于独立游戏真值'));
  paragraph(extra,'近期接触',`截至决策tick之前，近10游戏秒记录到 ${c.last10s_hero_damage_count} 条己方可见标记的真英雄间伤害日志，涉及 ${c.last10s_participant_hero_ids.map(hero).join('、')||'无记录'}。不是伤害次数／人数优势或当前团战结论。`);
  paragraph(extra,'近期发育活动',`近${c.history_game_seconds}游戏秒，主宰对野怪的伤害日志 ${c.own_farming_activity.neutral_damage_records||0} 条，对兵的伤害日志 ${c.own_farming_activity.creep_damage_records||0} 条；这不表示当前还有多少资源。`);
  paragraph(extra,'己方视野线索',`窗口内己方插眼记录 ${c.friendly_recent_ward_placements.length} 条、开雾施加记录 ${c.friendly_recent_smoke_activations.length} 条；不认证当前眼位覆盖或仍在雾中，不显示敌方真实眼／雾。`);
  paragraph(extra,'仍不能确定',x.unresolved.join('；'));
  const details=el('details');details.append(el('summary','展开原始来源引用及未认证数值（不是建议输入）'));details.append(el('pre',JSON.stringify(c,null,2)));extra.append(details);
 }
 $('history').replaceChildren();
 for(const frame of selected.past_frames){const b=el('button',`过去 ${time(frame.time)}`);b.addEventListener('click',()=>showMap(frame));$('history').append(b);}
 const back=el('button','回到建议时点');back.addEventListener('click',()=>showMap({players:d.positions,time:d.time,tick:d.tick}));$('history').append(back);
 showMap({players:d.positions,time:d.time,tick:d.tick});$('outcome').replaceChildren();$('outcome').hidden=true;$('reveal').disabled=false;$('reveal').textContent='展开后续采样';$('review').hidden=false;$('error').textContent='';
}
$('reveal').addEventListener('click',async()=>{
 const generation=epoch,cs=selected.case;$('reveal').disabled=true;
 try{const after=await json(`/api/${cs.id}-after.json`);if(generation!==epoch)return;
  const out=$('outcome');out.replaceChildren();out.append(el('p','后续仅供对照，不自动改写建议、不判定动作正确。'));
  for(const frame of after.frames){const s=el('section');s.append(el('h4',`${time(frame.time)} · tick ${frame.tick}`));const canvas=el('canvas');canvas.width=900;canvas.height=847;canvas.setAttribute('aria-label','事后对照采样地图');s.append(canvas);out.append(s);draw(canvas,frame.players,cs.slot);
   const p=frame.players.find(p=>p.player_slot===cs.slot);s.append(el('p',`主宰：${p.life_state===0?'存活':p.life_state===1?'死亡过渡':p.life_state===2?'死亡':'未知'}；${p.current_position?'有可靠位置':'无当前可靠位置'}。三点抽样不能证明中间没有死亡或危险。`));
  }
  if(!after.frames.length)out.append(el('p','没有后续采样。'));out.hidden=false;if(reviewDrafts.has(cs.id))reviewDrafts.get(cs.id).outcome_revealed=true;$('reveal').textContent='已展开后续（与当时地图分开）';
 }catch(e){if(generation===epoch){$('error').textContent=e.message;$('reveal').disabled=false;}}
});
(async()=>{try{data=await json('/api/cases');image.src='/map.jpg';await image.decode();data.cards.forEach((card,index)=>{const b=el('button',`${index+1} · ${card.case.action_axis}`);b.addEventListener('click',()=>render(index));$('cases').append(b);});render(0);}catch(e){$('error').textContent=e.message;}})();
