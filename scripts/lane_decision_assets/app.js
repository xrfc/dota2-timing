'use strict';
const el = id => document.getElementById(id);
const time = t => Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0');
const lanes = {top: '上路', mid: '中路', bot: '下路'};
const labels = {farm: '继续收线', retreat: '先拉开', unknown: '证据不足'};
let cases = [], names = {}, current, revision = 0;
const zh = hero => names[hero] || hero;
const map = new Image();
const storageKey = () => 'lane-review-v1:' + location.pathname + ':' + current.id;
const saved = () => JSON.parse(localStorage.getItem(storageKey()) || '{}');
const save = value => localStorage.setItem(storageKey(), JSON.stringify({...saved(), ...value}));
async function read(path) {
  const r = await fetch(path);
  if (!r.ok) throw Error('读取失败：' + path);
  return r.json();
}
function draw() {
  if (!current) return;
  const f = current.history[Number(el('frames').value)];
  el('ally').textContent = '最近存活队友：' + (f.ally ? zh(f.ally[1]) + '，距离 ' + f.ally[0] : '无位置记录');
  el('enemies').replaceChildren(...f.enemies.map(e => {
    const li = document.createElement('li');
    const seen = e.last_seen == null ? '此前没有视野记录' : e.last_seen === f.t ? '当前有视野记录，位置缺失' : (f.t - e.last_seen) + ' 秒前最后露头';
    li.textContent = zh(e.hero) + ' · ' + (e.distance == null ? seen : '可见，距离 ' + e.distance);
    return li;
  }));
  const c = el('map'), g = c.getContext('2d');
  g.clearRect(0, 0, c.width, c.height);
  if (map.naturalWidth) g.drawImage(map, 0, 0, c.width, c.height);
  if (f.wave) {
    const k = 8356 / 18322;
    const x = (261 + (f.wave[0] - 7487) * k) * c.width / 8878;
    const y = (26015 - f.wave[1]) * k * c.height / 8356;
    g.fillStyle = '#fff'; g.fillRect(x-4, y-4, 8, 8);
  }
  for (const m of f.markers) {
    const k = 8356 / 18322;
    const x = (261 + (m.pos[0] - 7487) * k) * c.width / 8878;
    const y = (26015 - m.pos[1]) * k * c.height / 8356;
    g.beginPath(); g.arc(x, y, m.side === 'self' ? 7 : 5, 0, 2 * Math.PI);
    g.fillStyle = {self:'#ffd353', ally:'#91ee9f', enemy:'#ff685b'}[m.side]; g.fill();
    g.strokeStyle = '#172424'; g.stroke();
    g.font = 'bold 12px sans-serif'; g.lineWidth = 3; g.strokeText(zh(m.hero), x+7, y-4);
    g.fillStyle = '#fff'; g.fillText(zh(m.hero), x+7, y-4); g.lineWidth = 1;
  }
}
async function judge(choice) {
  const seq = ++revision;
  const first = saved().first || choice;
  save({choice, first});
  el('first-choice').hidden = false;
  el('first-choice').textContent = '首次判断：' + labels[first]; el('review').hidden = true; el('error').textContent = '';
  for (const b of el('choices').querySelectorAll('button')) b.setAttribute('aria-pressed', b.dataset.choice === choice);
  const a = await read('actions/' + current.id + '.json');
  if (seq !== revision) return;
  el('review').hidden = false; el('outcome').textContent = ''; el('reveal').disabled = false;
  el('advice').textContent = '事前规则草案：' + labels[a.lean] + '。' + a.reason;
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
  el('outcome').textContent += ' 观察窗内记录到 ' + o.lane_last_hits + ' 个敌方线上小兵补刀。';
  el('reveal').disabled = true;
}
function openCase() {
  ++revision; current = cases[Number(el('cases').value)];
  history.replaceState(null, '', '#' + current.id);
  el('first-choice').hidden = true;
  el('title').textContent = zh(current.hero) + ' · ' + lanes[current.lane] + ' · ' + time(current.t);
  el('wave').textContent = '在此时刻补到敌方线上小兵，距己方兵线前沿 ' + current.front_distance + '。';
  el('frames').replaceChildren(...current.history.map((f,i) => new Option(time(f.t), i)));
  el('frames').selectedIndex = current.history.length-1;
  el('kit').textContent = '决策时生命 ' + current.hp.map(v => v ?? '未知').join('/') + '，魔法 ' + (current.mana ?? '未知') + '。保命手段就绪估计：' + (current.ready_names.map(zh).join('、') || '未检出') + '。距离、控制和施法条件仍会影响能否脱身。';
  el('review').hidden = true; el('notes').value = saved().note || ''; el('error').textContent = '';
  for (const b of el('choices').querySelectorAll('button')) b.setAttribute('aria-pressed', false);
  draw(); if (saved().choice) judge(saved().choice).catch(fail);
}
function fail(err) { el('error').textContent = err.message; }
el('cases').onchange = openCase; el('frames').onchange = draw;
el('notes').oninput = () => save({note: el('notes').value});
el('choices').onclick = e => { if(e.target.dataset.choice) judge(e.target.dataset.choice).catch(fail); };
el('reveal').onclick = () => reveal().catch(fail);
read('cases.json').then(doc => {
  cases = doc.cases; names = doc.names;
  el('cases').replaceChildren(...cases.map((c,i) => new Option(c.match+' · '+zh(c.hero)+' · '+time(c.t), i)));
  el('cases').selectedIndex = Math.max(0, cases.findIndex(c => c.id === location.hash.slice(1)));
  map.onload = draw; map.src = 'map.jpg'; openCase();
}).catch(fail);
