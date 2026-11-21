'use strict';
const el = id => document.getElementById(id);
const time = t => Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0');
const lanes = {top: '上路', mid: '中路', bot: '下路'};
let jungle = false;
let labels = {farm: '继续收线', retreat: '先拉开', unknown: '证据不足'};
let cases = [], names = {}, current, revision = 0;
const zh = hero => names[hero] || hero;
const map = new Image();
const storageKey = id => (jungle ? 'jungle-review-v1:' : 'lane-review-v1:') + location.pathname + ':' + id;
const portal = /^\/(lane|jungle|wave)\/(?:index\.html)?$/.test(location.pathname);
const drafts = new Map(), committed = new Map(), sending = new Set(), errors = new Map();
let reviewer;
const firstKey = id => 'review-first:'+reviewer+':'+id;
const exposureKey = id => 'review-exposure:'+reviewer+':'+id;
function saved(id = current.id) {
  if (!portal) return JSON.parse(localStorage.getItem(storageKey(id)) || '{}');
  let record = drafts.get(id) || committed.get(id) || {};
  if (!record.first) {
    const first = localStorage.getItem(firstKey(id));
    if (first) record = {...record, first, choice:record.choice || first};
  }
  if (!committed.get(id)?.first && !record.previewed && localStorage.getItem(exposureKey(id)) === '1') {
    return {...record, previewed:true};
  }
  return record;
}
function save(value) {
  if (!current) return;
  const record = {...saved(), ...value};
  if (portal) {
    if (record.first && !localStorage.getItem(firstKey(current.id))) localStorage.setItem(firstKey(current.id), record.first);
    if (record.previewed) localStorage.setItem(exposureKey(current.id), '1');
    drafts.set(current.id, record);
    errors.delete(current.id);
    submissionStatus();
  } else localStorage.setItem(storageKey(current.id), JSON.stringify(record));
}
// Each dimension is available before revealing the action or its consequences.
function scenarioFactors(c) {
  const frame = c.history?.at(-1);
  const distance = frame?.ally?.[0];
  let ally = 'unknown';
  if (frame?.ally === null) ally = 'unlocated';
  if (Number.isFinite(distance)) {
    ally = distance <= 1000 ? 'near' : distance >= 1500 ? 'far' : 'middle';
  }
  let threat = 'unknown';
  if (Array.isArray(frame?.enemies) && frame.enemies.length) {
    const alive = frame.enemies.filter(enemy => !enemy.dead);
    const near = alive.some(enemy => Number.isFinite(enemy.distance) && enemy.distance <= 1600);
    const missing = alive.filter(enemy => enemy.last_seen === null ||
      (Number.isFinite(enemy.last_seen) && frame.t - enemy.last_seen >= 10)).length;
    threat = near ? 'near' : missing >= 2 ? 'missing' : 'other';
  }
  const support = c.support_opportunity === undefined ? 'unknown' : c.support_opportunity ? 'signal' : 'none';
  const save = Array.isArray(c.ready_names) ? (c.ready_names.length ? 'detected' : 'none') : 'unknown';
  return [ally, threat, support, save];
}

function selectReviewGroups(allCases, limit = 5) {
  const groups = new Map();
  for (const c of allCases) {
    const factors = scenarioFactors(c);
    const key = factors.join('/');
    if (!groups.has(key)) groups.set(key, {factors, ids:[]});
    groups.get(key).ids.push(c.id);
  }
  // Start with common situations; then prefer evidence values not yet represented.
  const remaining = [...groups.values()].sort((a, b) => b.ids.length - a.ids.length);
  const covered = new Set(), selected = [];
  while (selected.length < limit && remaining.length) {
    let best = 0, bestScore = -1;
    remaining.forEach((group, i) => {
      const score = group.factors.filter((value, d) => !covered.has(d + ':' + value)).length;
      if (score > bestScore) { best = i; bestScore = score; }
    });
    const [group] = remaining.splice(best, 1);
    group.factors.forEach((value, d) => covered.add(d + ':' + value));
    selected.push(group);
  }
  return selected;
}

let reviewGroups = [], nextReviewId;
function reviewGroupState(group) {
  let pending, unseen;
  for (const id of group.ids) {
    const row = saved(id);
    const submitted = portal ? committed.get(id) : row;
    if (submitted?.first && !submitted.previewed) return {state:'done'};
    if (row.first && !row.previewed) pending ??= id;
    else if (!row.first && !row.choice && !row.previewed) unseen ??= id;
  }
  if (pending) return {state:'pending', id:pending};
  if (unseen) return {state:'unseen', id:unseen};
  return {state:'exposed'};
}

function refreshReviewQueue() {
  if (!reviewGroups.length) return;
  const states = reviewGroups.map(reviewGroupState);
  const count = state => states.filter(row => row.state === state).length;
  const next = states.find(row => row.state === 'pending') || states.find(row => row.state === 'unseen');
  nextReviewId = next?.id;
  el('next-review').disabled = !next;
  el('next-review').textContent = next?.state === 'pending' ? '打开待提交判断' : '打开下一段抽查';
  const summary = ['本报告 '+cases.length+' 段，选取 '+states.length+' 组', '独立完成 '+count('done')+' 组'];
  if (count('pending')) summary.push('待提交 '+count('pending')+' 组');
  if (count('exposed')) summary.push('无可盲评片段 '+count('exposed')+' 组');
  el('review-progress').textContent = summary.join(' · ');
}
function submissionStatus() {
  if (!portal || !current) return;
  const id = current.id, row = saved();
  const hasOpinion = Boolean(row.choice || row.note?.trim() || committed.has(id));
  const dirty = drafts.has(id) && JSON.stringify(drafts.get(id)) !== JSON.stringify(committed.get(id));
  el('submit-review').disabled = sending.has(id) || !dirty || !hasOpinion;
  el('submit-status').textContent = errors.get(id) || (sending.has(id) ? '提交中…' :
    dirty && hasOpinion ? '有未提交的修改' : committed.has(id) ? '已提交' : '尚未提交');
}
async function submitReview() {
  const id = current.id, row = saved();
  if (sending.has(id)) return;
  const record = {case_id:id, choice:row.choice || null, first:row.first || null,
    previewed:Boolean(row.previewed), note:row.note || ''};
  sending.add(id); errors.delete(id); submissionStatus();
  try {
    const r = await fetch('/reviews', {method:'POST', headers:{
      'Content-Type':'application/json', 'X-Review-Reviewer':reviewer}, body:JSON.stringify(record)});
    if (r.status === 401 || r.status === 409) throw Error('登录状态已变更，请重新进入评审页。');
    if (!r.ok || !(await r.json()).ok) throw Error('提交未成功，请重试。');
    committed.set(id, record);
    if (drafts.get(id) === row) drafts.delete(id);
  } catch (err) { errors.set(id, err.message); }
  finally { sending.delete(id); submissionStatus(); refreshReviewQueue(); }
}
async function read(path) {
  const r = await fetch(path);
  if (!r.ok) throw Error('读取失败：' + path);
  return r.json();
}
const controlItems = {
  item_orchid:'沉默', item_bloodthorn:'沉默', item_basher:'攻击可能触发眩晕',
  item_abyssal_blade:'近身眩晕', item_sheepstick:'变形'
};
function drawEquipment(frame) {
  const threats = [];
  const sides = [[], []];
  for (const row of frame.equipment || []) {
    const items = Object.entries(row.items || {});
    const age = frame.t - row.observed;
    const stamp = row.observed == null ? '尚无视野记录' : age ? time(row.observed)+'（'+age+'秒前）' : '当前';
    const li = document.createElement('li');
    const display = items.map(([slot,name]) => {
      const bag = Number(slot)>=6 && Number(slot)<=8;
      if (!row.ally && Number(slot)<6 && controlItems[name]) {
        threats.push(zh(row.hero)+' · '+zh(name)+'（'+controlItems[name]+'，'+stamp+'）');
      }
      return zh(name)+(bag?'［背包］':'');
    });
    li.textContent = zh(row.hero)+' · '+stamp+'：'+(row.items == null?'装备未知':display.join('、') || '空栏');
    sides[Number(row.ally)].push(li);
  }
  el('enemy-kit').replaceChildren(...sides[0]);
  el('ally-kit').replaceChildren(...sides[1]);
  el('threat').textContent = threats.length ? threats.join('；')+'。判断能否单抓时，结合先手距离、自身解控与队友接应。'
    : '已知主装备栏中未见紫怨、血棘、晕锤、深渊之刃或羊刀。仍需考虑英雄技能与未露头期间的更新。';
}
function draw() {
  if (!current) return;
  const f = current.history[Number(el('frames').value)];
  drawEquipment(f);
  el('ally').textContent = '最近存活队友：' + (f.ally ? zh(f.ally[1]) + '，距离 ' + f.ally[0] : '无位置记录');
  el('enemies').replaceChildren(...f.enemies.map(e => {
    const li = document.createElement('li');
    const seen = e.dead ? '已阵亡' : e.last_seen == null ? '此前没有视野记录' : e.last_seen === f.t ? '当前有视野记录，位置缺失' : (f.t - e.last_seen) + ' 秒前最后露头';
    li.textContent = zh(e.hero) + ' · ' + (e.distance == null ? seen : '可见，距离 ' + e.distance);
    return li;
  }));
  const c = el('map'), g = c.getContext('2d');
  g.clearRect(0, 0, c.width, c.height);
  if (map.naturalWidth) g.drawImage(map, 0, 0, c.width, c.height);
  const project = ([x,y]) => [
    (261 + (x - 7487) * 8356 / 18322) * c.width / 8878,
    (26015 - y) * c.height / 18322
  ];
  g.font = 'bold 12px sans-serif';
  if (f.vision && el('vision').checked) {
    const {origin,step,width,bits} = f.vision;
    const mask = atob(bits);
    const inside = (x,y) => {
      if (x<0 || y<0 || x>=width || y>=width) return false;
      const i = y*width+x;
      return Boolean(mask.charCodeAt(i>>3) & (1<<(i%8)));
    };
    const size = step*c.height/18322;
    g.beginPath();
    for (let y=0;y<width;y++) for (let x=0;x<width;x++) {
      if (!inside(x,y)) continue;
      const [a,b] = project([origin+x*step,origin+(y+1)*step]);
      g.fillStyle = 'rgba(119,235,226,0.20)'; g.fillRect(a,b,size,size);
      if (!inside(x-1,y)) {g.moveTo(a,b);g.lineTo(a,b+size);}
      if (!inside(x+1,y)) {g.moveTo(a+size,b);g.lineTo(a+size,b+size);}
      if (!inside(x,y+1)) {g.moveTo(a,b);g.lineTo(a+size,b);}
      if (!inside(x,y-1)) {g.moveTo(a,b+size);g.lineTo(a+size,b+size);}
    }
    g.strokeStyle = 'rgba(140,255,241,0.85)'; g.lineWidth = 1; g.stroke();
  }
  for (const enemy of f.enemies) {
    const trail = enemy.trail || [];
    if (enemy.dead || !trail.length) continue;
    const path = trail.map(([,x,y]) => project([x,y]));
    g.strokeStyle = '#ffada8'; g.lineWidth = 2; g.beginPath();
    path.forEach(([x,y],i) => i ? g.lineTo(x,y) : g.moveTo(x,y)); g.stroke();
    if (enemy.last_seen < f.t) {
      const [x,y] = path[path.length-1];
      g.strokeRect(x-3,y-3,6,6);
      g.fillStyle = '#ffe1dd';
      g.fillText(zh(enemy.hero)+' · '+(f.t-enemy.last_seen)+'秒前', x+5,y+12);
    }
  }
  g.lineWidth = 1;
  for (const ward of f.wards || []) {
    const [x,y] = project(ward.pos);
    g.fillStyle = ward.type === 'observer' ? '#ffe56d' : '#83caff';
    g.fillRect(x-7,y-7,14,14); g.fillStyle = '#101818';
    g.fillText(ward.type === 'observer' ? '观' : '真',x-6,y+5);
  }
  const landmark = jungle ? f.camp : f.wave;
  if (landmark) {
    const [x,y] = project(landmark);
    g.fillStyle = '#fff'; g.fillRect(x-4, y-4, 8, 8);
  }
  for (const m of f.markers) {
    const [x,y] = project(m.pos);
    g.beginPath(); g.arc(x, y, m.side === 'self' ? 7 : 5, 0, 2 * Math.PI);
    g.fillStyle = {self:'#ffd353', ally:'#91ee9f', enemy:'#ff685b'}[m.side]; g.fill();
    g.strokeStyle = '#172424'; g.stroke();
    g.font = 'bold 12px sans-serif'; g.lineWidth = 3; g.strokeText(zh(m.hero), x+7, y-4);
    g.fillStyle = '#fff'; g.fillText(zh(m.hero), x+7, y-4); g.lineWidth = 1;
  }
}
function judge(choice) {
  const first = saved().first || choice;
  save({choice, first});
  refreshReviewQueue();
  el('first-choice').hidden = false;
  el('first-choice').textContent = (saved().previewed ? '看过分析后的首次意见：' : '首次独立判断：') + labels[first]; el('review').hidden = true; el('error').textContent = '';
  for (const b of el('choices').querySelectorAll('button')) b.setAttribute('aria-pressed', b.dataset.choice === choice);
  return showAnalysis();
}
async function showAnalysis() {
  const seq = ++revision;
  const a = await read('actions/' + current.id + '.json');
  if (seq !== revision) return;
  if (!saved().first) { save({previewed:true}); refreshReviewQueue(); }
  el('review').hidden = false; el('outcome').textContent = ''; el('reveal').disabled = false;
  el('advice').textContent = (jungle ? '当时的行动依据：' : '事前规则草案：' + labels[a.lean] + '。') + a.reason;
  el('action').textContent = '录像动作：' + a.detail;
  el('assessment').textContent = a.action === 'unknown' || a.lean === 'unknown'
    ? '本段证据不足以评价实际选择。'
    : a.action === a.lean ? '观察到的动作与当时的视野和支援证据一致。'
    : '实际动作与草案倾向不同。可用队友技能、兵线收益或撤退路线反驳这一判断。';
}
async function reveal() {
  const seq = revision;
  const o = await read('outcomes/' + current.id + '.json');
  if (seq !== revision) return;
  el('outcome').textContent = o.death_seconds.length ? '死亡时间：' + o.death_seconds.map(time).join('、')
    : o.complete ? '随后 20 秒内没有死亡记录。' : '录像结束，后续观察窗口不完整。';
  el('outcome').textContent += jungle ? ' 观察窗内亲自击杀野怪 '+o.jungle_last_hits+' 个。' : ' 观察窗内记录到 ' + o.lane_last_hits + ' 个敌方线上小兵补刀。';
  for (const data of [o.support_followup,o.farm_value]) if (data?.summary) el('outcome').textContent += ' '+data.summary;
  el('reveal').disabled = true;
}
function openCase() {
  ++revision; current = cases[Number(el('cases').value)];
  history.replaceState(null, '', '#' + current.id);
  el('first-choice').hidden = true;
  el('title').textContent = zh(current.hero) + ' · ' + (jungle ? '野区' : lanes[current.lane]) + ' · ' + time(current.t);
  el('wave').textContent = jungle ? '此刻亲自击杀野怪，英雄距最近的营地中心（'+current.camp_id+'号）'+current.camp_distance+'。' : '在此时刻补到敌方线上小兵，距己方兵线前沿 ' + current.front_distance + '。';
  el('comparison').replaceChildren(...[['支援到场',current.arrival],['抓人威胁',current.catch],['发育收益',current.farm_value]].map(([label,data]) => {
    const p = document.createElement('p');
    p.textContent = label+'：'+(data?.summary || '没有相应线索'); return p;
  }));
  if (current.kind==='wave') el('wave').textContent = '近六秒尚无线补，己方兵线附近有 '+current.nearby_creeps+' 个推算可见的敌方小兵。';
  el('route-signal').hidden = !jungle;
  if (jungle) {
    const route = current.route_from_lane;
    el('route-signal').textContent = route
      ? '转野线索：'+time(route.lane_t)+' 线上补刀，距今 '+(current.t-route.lane_t)+' 秒。从补刀位置到当前最近的 '+route.camp_id+' 号营地中心直线距离 '+Math.round(route.radius)+'，该半径内共有 '+route.candidate_count+' 个营地中心（含当前最近营地）。对手是否看见这次转移未知；营地数只按距离计算，实际通路和野怪刷新情况未知。'
      : '此前 45 秒未检出可定位的线上补刀起点，无法据此判断转野路线。';
  }
  el('support-signal').hidden = !jungle;
  if (jungle) {
    const signal = current.support_opportunity;
    el('support-signal').textContent = signal
      ? zh(signal.hero)+'在 '+signal.seconds_ago+' 秒前受到英雄伤害，决策时距你 '+signal.distance+'。能否及时到场、到场能否改变战局仍待判断。'
      : '近 8 秒未检出仍可定位的存活队友受到英雄伤害。';
  }
  el('frames').replaceChildren(...current.history.map((f,i) => new Option(time(f.t), i)));
  el('frames').selectedIndex = current.history.length-1;
  el('kit').textContent = '决策时生命 ' + current.hp.map(v => v ?? '未知').join('/') + '，魔法 ' + (current.mana ?? '未知') + '。保命手段就绪估计：' + (current.ready_names.map(zh).join('、') || '未检出') + '。距离、控制和施法条件仍会影响能否脱身。';
  el('review').hidden = true; el('notes').value = saved().note || ''; el('error').textContent = '';
  for (const b of el('choices').querySelectorAll('button')) b.setAttribute('aria-pressed', false);
  submissionStatus(); draw(); if (saved().choice) judge(saved().choice).catch(fail);
}
function fail(err) { el('error').textContent = err.message; }
el('next-review').onclick = () => {
  refreshReviewQueue();
  if (!nextReviewId) return;
  el('cases').value = String(cases.findIndex(c => c.id === nextReviewId));
  openCase();
};
el('cases').onchange = openCase; el('frames').onchange = draw; el('vision').onchange = draw;
el('notes').oninput = () => save({note: el('notes').value});
el('choices').onclick = e => { if(e.target.dataset.choice) judge(e.target.dataset.choice).catch(fail); };
el('preview').onclick = () => showAnalysis().catch(fail);
el('reveal').onclick = () => reveal().catch(fail);
async function loadPage() {
  if (portal) {
    const r = await fetch('/reviews', {cache:'no-store'});
    if (!r.ok) throw Error('无法读取个人评审，请返回邀请入口重新登录。');
    const snapshot = await r.json();
    reviewer = snapshot.reviewer;
    if (!reviewer || !Array.isArray(snapshot.reviews)) throw Error('个人评审响应不完整，请刷新。');
    for (const row of snapshot.reviews) committed.set(row.case_id, row);
    el('online-review').hidden = false;
    el('submit-review').onclick = submitReview;
    document.querySelector('label[for=notes]').textContent = '判断依据或异议（点提交后交给组织者）';
  }
  return read('cases.json');
}
loadPage().then(doc => {
  if (doc.mode==='wave') {
    document.title = '兵线取舍复盘';
    document.querySelector('h1').textContent = document.title;
    el('question').textContent = '上前收线，还是提前离开？';
  }
  jungle = doc.mode === 'jungle';
  if (jungle) {
    document.title = '打野决策复盘';
    document.querySelector('h1').textContent = document.title;
    el('question').textContent = '继续刷野、换区，还是支援队友？';
    el('landmark-label').textContent = '白方块：附近营地中心';
    labels = {farm:'继续刷野', rotate:'换区', support:'支援队友', unknown:'证据不足'};
    const buttons = Object.entries(labels).map(([value, label]) => {
      const button = document.createElement('button');
      button.dataset.choice = value;
      button.textContent = label;
      return button;
    });
    el('choices').replaceChildren(el('choices').querySelector('legend'), ...buttons);
  }
  cases = doc.cases; names = doc.names;
  reviewGroups = selectReviewGroups(cases);
  refreshReviewQueue();
  const option = (c,label) => new Option((label ? label+' · ' : '')+c.match+' · '+zh(c.hero)+' · '+time(c.t), cases.indexOf(c));
  const samples = document.createElement('optgroup');
  samples.label = '可选抽看 · 按当时证据选取';
  const chosen = new Set();
  const examples = [
    ['敌方已见控制装', f => (f.equipment || []).some(r => !r.ally && Object.entries(r.items || {}).some(([slot,n]) => Number(slot)<6 && controlItems[n]))],
    ['附近有队友', f => f.ally && f.ally[0]<=1000],
    [jungle ? '附近缺少队友' : '孤身收线', f => !f.ally || f.ally[0]>=1500]
  ];
  for (const [label, matches] of examples) {
    const c = cases.find(c => !chosen.has(c.id) && matches(c.history[c.history.length-1]));
    if (c) {chosen.add(c.id); samples.append(option(c,label));}
  }
  const all = document.createElement('optgroup');
  all.label = '全部片段';
  all.append(...cases.map(c => option(c,'')));
  el('cases').replaceChildren(samples,all);
  const linked = cases.findIndex(c => c.id === location.hash.slice(1));
  const startIndex = linked >= 0 ? linked : cases.findIndex(c => c.id === nextReviewId);
  if (startIndex >= 0) el('cases').value = String(startIndex);
  map.onload = draw; map.src = 'map.jpg'; openCase();
}).catch(fail);
