'use strict';
const $ = id => document.getElementById(id);
const labels = {radiant:'天辉可知视角',dire:'夜魇可知视角',omniscient:'全知视角 · 仅复盘'};
const issues = {no_sample:'当前tick无采样',duplicate_tick:'重复tick，坐标不显示',not_retained_by_existing_cleaning:'清洗未保留',pause:'暂停记录',repeated_game_second:'重复游戏秒',state_ambiguous:'状态歧义',duplicate_position_tick:'重复位置tick',visibility_identity_unknown_or_ambiguous:'可见性身份不确定',state_missing:'缺少状态'};
let catalog, timeline=null, frame=null, generation=0, request=0, playing=false, timer=null, loading=false, playEpoch=0;
const map = new Image();
const ctx = $('map').getContext('2d');
const formatTime = t => t==null?'--:--':`${t<0?'-':''}${Math.floor(Math.abs(t)/60).toString().padStart(2,'0')}:${Math.floor(Math.abs(t)%60).toString().padStart(2,'0')}`;
const heroName = id => catalog?.names[String(id)] || `英雄 ${id}`;
function option(select,value,text){const o=document.createElement('option');o.value=value;o.textContent=text;select.append(o);}
function message(text){$('loading').textContent=text;$('loading').style.display='flex';}
function controls(enabled){for(const id of ['play','prev','next','time'])$(id).disabled=!enabled;for(const id of ['prev-event','next-event'])$(id).disabled=!enabled||!timeline?.event_ticks?.length;}
function stop(){playing=false;playEpoch++;clearTimeout(timer);$('play').textContent='播放';}
function clear(){frame=null;ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,$('map').width,$('map').height);$('players').replaceChildren();$('status').textContent='读取所选视角…';}
async function json(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw new Error('数据读取失败：请检查文件完整性与服务日志');return r.json();}
function pixel(p){return {x:261+(p.x-7487)*8356/18322,y:(26015-p.y)*8356/18322};}
function inside(p){return p.x>=0&&p.y>=0&&p.x<8878&&p.y<8356;}
function draw(){
 ctx.setTransform($('map').width/8878,0,0,$('map').height/8356,0,0);
 ctx.clearRect(0,0,8878,8356);
 if(!frame)return;
 ctx.drawImage(map,0,0,8878,8356);
 const focus=$('hero').value; $('players').replaceChildren();
 for(const p of frame.players){
  if(focus!=='all'&&String(p.player_slot)!==focus)continue;
  const color=p.player_slot<128?'#78f2b8':'#ff9b95';ctx.strokeStyle=color;ctx.fillStyle=color;
  ctx.lineWidth=23;ctx.globalAlpha=.75;
  for(const segment of p.segments){ctx.beginPath();let active=false;for(const raw of segment){const q=pixel(raw);if(!inside(q)){active=false;continue;}if(active)ctx.lineTo(q.x,q.y);else ctx.moveTo(q.x,q.y);active=true;}ctx.stroke();}
  ctx.globalAlpha=1;
  const current=p.current_position;const last=p.last_seen;const raw=current||(last&&last.position);
  let outOfBounds=false;
  if(raw){const q=pixel(raw);outOfBounds=!inside(q);if(!outOfBounds){
   ctx.beginPath();ctx.arc(q.x,q.y,current?68:88,0,2*Math.PI);ctx.lineWidth=22;
   if(current){ctx.fill();ctx.strokeStyle='#10171c';ctx.stroke();}else{ctx.setLineDash([28,20]);ctx.stroke();ctx.setLineDash([]);}
   ctx.font='bold 140px sans-serif';ctx.textAlign='center';ctx.strokeStyle='#10171c';ctx.lineWidth=35;
   const text=`${heroName(p.hero_id)}${current?'':' · 最后可见'}`;ctx.strokeText(text,q.x,q.y-120);ctx.fillText(text,q.x,q.y-120);
  }}
  const card=document.createElement('div');card.className='player';
  const title=document.createElement('strong');title.className=p.player_slot<128?'rad':'dire';title.textContent=`${p.player_slot<128?'天辉':'夜魇'} · ${heroName(p.hero_id)}`;card.append(title);
  const state=document.createElement('small');
  const visible={visible:'可见',hidden:'隐藏',unknown:'未知',omniscient:'全知'}[p.visibility];
  state.textContent=`${visible} · ${p.life_state===0?'存活':p.life_state===null?'生命状态未知':p.life_state===2?'死亡':p.life_state===1?'死亡过渡':'生命状态未知'} · ${current?'有可靠位置':'无当前可靠位置'}`;card.append(state);
  if(!current&&last){const l=document.createElement('small');l.textContent=`最后可靠可见 ${formatTime(last.time)} · tick ${last.source_tick}（不是当前位置）`;card.append(l);}
  const transitions={disappeared:'本帧消失',appeared:'本帧重新可见',became_unknown:'本帧可见性变未知',visible_death_state:'本帧出现非存活状态'};
  const notes=[...(p.transitions||[]).map(t=>transitions[t]),...(p.quality_flags||[]).map(f=>issues[f]||f)];if(p.display_issue)notes.push(issues[p.display_issue]);if(outOfBounds)notes.push('坐标超出底图，未裁到地图边缘');if(p.trail_breaks&&!p.break_reasons)notes.push(`轨迹保守断开 ${p.trail_breaks} 处`);
  const reasons={dead:'死亡',dying:'死亡过渡',hidden:'敌方隐藏',visibility_unknown:'可见性未知',state_missing:'状态缺失',position_withheld:'当前位置未通过投影',duplicate_tick:'重复tick，位置扣留',no_sample:'当前无采样',sampling_gap:'采样间隔',position_jump:'大跨度位置跃迁（非异常判定）'};
  for(const [reason,count] of Object.entries(p.break_reasons||{})){if(reason==='observation_unavailable')continue;const unit=['sampling_gap','position_jump'].includes(reason)?'段':'个采样点';notes.push((reasons[reason]||reason)+' '+count+unit);}
  if(frame.view==='omniscient'){
   if(frame.event_evidence_status==='not_audited')notes.push('此场尚无接入的事件审计；不是无技能/物品数据');
   for(const jump of p.jump_evidence||[]){
    const panel=document.createElement('details');const summary=document.createElement('summary');
    summary.textContent='位移关联证据 · 非确定原因 · '+jump.events.length+'条';panel.append(summary);
    const interval=document.createElement('p');interval.textContent='tick '+jump.previous_tick+' → '+jump.current_tick+' · '+Math.round(jump.distance)+'单位 · '+jump.category+' · '+jump.jump_ref;panel.append(interval);
    for(const event of jump.events){const line=document.createElement('p');line.textContent=event.log_type+' '+(event.inflictor_name||'未命名')+' · tick '+event.tick+' · '+event.scope+' · '+(event.roles||[]).join('/')+' · '+event.source_ref+(event.teleport_modifier_end?'（效果结束不证明传送成功）':'');panel.append(line);}
    card.append(panel);
   }
  }
  if(notes.length){const n=document.createElement('small');n.textContent=notes.join(' / ');card.append(n);}$('players').append(card);
 }
}
function schedule(){if(!playing)return;const epoch=playEpoch;timer=setTimeout(async()=>{if(Number($('time').value)>=timeline.frames.length-1){stop();return;}$('time').value=Number($('time').value)+1;await showFrame();if(epoch===playEpoch)schedule();},1000/Number($('speed').value));}
async function showFrame(){
 if(!timeline)return;const g=generation,n=++request;loading=true;
 const index=Number($('time').value),f=timeline.frames[index];
 // Clear old coordinates immediately: never label an older frame as the requested time.
 clear();message('加载当前帧…');
 try{const result=await json(`/api/frame?match=${$('match').value}&view=${$('view').value}&tick=${f.tick}&trail=${$('trail').value}`);
  if(g!==generation||n!==request)return;frame=result;draw();$('loading').style.display='none';$('clock').textContent=formatTime(f.time);
  const repeated=index>0&&timeline.frames[index-1].time===f.time;
  $('status').textContent=repeated?'游戏时间未前进：重复游戏秒，按tick保留':'按原始采样显示；缺口不插值';
  $('frame-label').textContent=`第 ${index+1} / ${timeline.frames.length} 帧 · tick ${f.tick}${repeated?' · 重复游戏秒':''}`;
 }catch(e){if(g===generation&&n===request){stop();clear();message(e.message);}}finally{if(g===generation&&n===request)loading=false;}
}
async function loadTimeline(){
 stop();generation++;request++;const g=generation;timeline=null;clear();controls(false);message('校验并读取所选视角…');$('view-badge').textContent=labels[$('view').value];$('clock').textContent='--:--';
 try{const result=await json(`/api/timeline?match=${$('match').value}&view=${$('view').value}`);if(g!==generation)return;timeline=result;
  $('hero').replaceChildren();option($('hero'),'all','全部英雄');for(const h of timeline.heroes)option($('hero'),h.slot,`${h.slot<128?'天辉':'夜魇'} · ${heroName(h.hero_id)}`);
  $('time').max=timeline.frames.length-1;$('time').value=0;$('end-time').textContent=`结束 ${formatTime(timeline.frames.at(-1).time)}`;
  await showFrame();if(g===generation)controls(true);
 }catch(e){if(g===generation){clear();message(e.message);}}
}
for(const [id,forward] of [['prev-event',false],['next-event',true]])$(id).addEventListener('click',()=>{
 stop();if(!timeline?.event_ticks)return;const current=timeline.frames[Number($('time').value)].tick;
 const target=forward?timeline.event_ticks.find(t=>t>current):timeline.event_ticks.findLast(t=>t<current);
 if(target===undefined)return;$('time').value=timeline.frames.findIndex(f=>f.tick===target);showFrame();
});
$('match').addEventListener('change',loadTimeline);$('view').addEventListener('change',loadTimeline);
$('hero').addEventListener('change',draw);$('trail').addEventListener('change',()=>{stop();showFrame();});
$('time').addEventListener('input',()=>{stop();showFrame();});
for(const [id,delta] of [['prev',-1],['next',1]])$(id).addEventListener('click',()=>{stop();if(!timeline)return;$('time').value=Math.max(0,Math.min(timeline.frames.length-1,Number($('time').value)+delta));showFrame();});
$('play').addEventListener('click',async()=>{if(playing){stop();return;}if(!timeline||loading)return;playing=true;$('play').textContent='暂停';const epoch=playEpoch;if(Number($('time').value)>=timeline.frames.length-1){$('time').value=0;await showFrame();}if(epoch===playEpoch)schedule();});
$('speed').addEventListener('change',()=>{if(playing){clearTimeout(timer);schedule();}});
(async()=>{try{catalog=await json('/api/catalog');for(const mid of catalog.matches)option($('match'),mid,`比赛 ${mid}`);map.src='/map.jpg';await map.decode();await loadTimeline();}catch(e){message(e.message||'底图加载失败');}})();
