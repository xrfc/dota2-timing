'use strict';
// High-rank references: item timing (U13) and 针对装 (U20). Talks only to /api/*.
const $ = id => document.getElementById(id);
const state = {meta: null, spec: null, request: 0, view: 'items', sit: null, sitSpec: null};
const STORE = 'coach-app-items-v2';
const VIEWS = ['items', 'situational'];

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function save() {
  try {
    localStorage.setItem(STORE, JSON.stringify({spec: state.spec, view: state.view, sitSpec: state.sitSpec}));
  } catch (e) { /* storage unavailable */ }
}
function restore() {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) || 'null');
    if (!v) return;
    if (typeof v.spec === 'string') state.spec = v.spec;
    if (VIEWS.includes(v.view)) state.view = v.view;
    if (typeof v.sitSpec === 'string') state.sitSpec = v.sitSpec;
  } catch (e) { /* ignore */ }
}
const heroName = id => (state.meta.heroes.find(h => h.id === id) || {}).name || `英雄 ${id}`;
const pct = p => `${Math.round(p * 100)}%`;

function renderSetup() {
  const mine = $('my-heroes'); mine.replaceChildren();
  for (const h of state.meta.my_heroes) {
    const key = `${h.hero_id}:${h.position}`;
    const b = el('button', h.name, 'seg'); b.type = 'button';
    b.append(el('small', `${h.position}号位`));
    b.setAttribute('aria-pressed', String(state.spec === key));
    b.addEventListener('click', () => { state.spec = key; renderSetup(); update(); });
    mine.append(b);
  }
}

async function update() {
  save();
  const [hero, position] = state.spec.split(':');
  const ticket = ++state.request;
  try {
    const r = await fetch(`/api/item-timing?${new URLSearchParams({hero, position})}`, {cache: 'no-store'});
    if (!r.ok) throw new Error('数据请求失败');
    const view = await r.json();
    if (ticket === state.request) { $('input-error').textContent = ''; renderResult(view); }
  } catch (e) {
    if (ticket === state.request) $('input-error').textContent = e.message;
  }
}

function renderResult(view) {
  const [hero, position] = view.spec;
  $('result-title').textContent = `${heroName(hero)} · ${position}号位 高分段出装节奏`;
  $('result-status').textContent = '超凡及以上、30 分钟以上比赛的平均；不随阵容变化。';
  const head = $('timing-head'); head.replaceChildren();
  const first = el('th', '装备'); first.scope = 'col'; head.append(first);
  for (const m of state.meta.minutes) { const th = el('th', `${m}′`, 'min'); th.scope = 'col'; head.append(th); }
  const typ = el('th', '通常完成', 'typical'); typ.scope = 'col'; head.append(typ);
  const body = $('timing-body'); body.replaceChildren();
  for (const item of view.items) {
    const tr = el('tr');
    const name = el('td', state.meta.item_names[item.item] || item.item, 'item');
    name.append(el('small', `样本 ${item.train_n}${item.train_n < 100 ? ' · 偏少' : ''}`));
    tr.append(name);
    for (const c of item.cells) {
      const td = el('td', pct(c.display_probability), 'cell');
      td.style.setProperty('--p', c.display_probability.toFixed(3));
      if (c.display_probability > 0.55) td.classList.add('dark');
      td.title = `${c.minute} 分钟前已做出：${pct(c.display_probability)}`;
      tr.append(td);
    }
    tr.append(el('td', item.typical_minute ? `${item.typical_minute} 分钟前` : '30 分钟内未过半', 'typical'));
    body.append(tr);
  }
}

function showView(view) {
  state.view = view;
  for (const t of document.querySelectorAll('.tab')) {
    if (t.dataset.view === view) t.setAttribute('aria-current', 'page'); else t.removeAttribute('aria-current');
  }
  for (const v of VIEWS) $(`view-${v}`).hidden = v !== view;
  save();
  if (view === 'situational') loadSituational();
}

async function loadSituational() {
  if (state.sit) { renderSituational(); return; }
  try {
    const r = await fetch('/api/situational', {cache: 'no-store'});
    if (!r.ok) throw new Error('针对装数据读取失败');
    state.sit = await r.json();
  } catch (e) { $('sit-status').textContent = e.message; return; }
  const notes = $('sit-notes'); for (const n of state.sit.notes) notes.append(el('li', n));
  $('sit-run').textContent = `数据：${state.sit.runs.join('、')}`;
  renderSituational();
}

function sitHeroes() {
  return [state.sit.juggernaut, ...state.sit.supports];
}

function barCell(p) {
  const td = el('td'); const bar = el('div', undefined, 'bar');
  const track = el('div', undefined, 'bar-track'); const fill = el('div', undefined, 'bar-fill');
  fill.style.setProperty('--p', p.toFixed(3)); track.append(fill);
  bar.append(track, el('span', pct(p))); td.append(bar);
  return td;
}

function headRow(labels) {
  const head = $('sit-head'); head.replaceChildren();
  for (const [text, cls] of labels) { const th = el('th', text, cls); th.scope = 'col'; head.append(th); }
}

function renderSituational() {
  const heroes = sitHeroes();
  if (!heroes.some(h => h.spec.join(':') === state.sitSpec)) state.sitSpec = heroes[0].spec.join(':');
  const box = $('sit-heroes'); box.replaceChildren();
  for (const h of heroes) {
    const key = h.spec.join(':');
    const b = el('button', h.name, 'seg'); b.type = 'button';
    b.append(el('small', `${h.spec[1]}号位`));
    b.setAttribute('aria-pressed', String(state.sitSpec === key));
    b.addEventListener('click', () => { state.sitSpec = key; save(); renderSituational(); });
    box.append(b);
  }
  const hero = heroes.find(h => h.spec.join(':') === state.sitSpec);
  const body = $('sit-body'); body.replaceChildren();
  $('sit-title').textContent = `${hero.name} · ${hero.spec[1]}号位 针对装参照`;
  if (hero === state.sit.juggernaut) {
    const v = state.sit.verdict;
    $('sit-status').textContent = `高分段 ${hero.games} 局；其中 ${hero.games_with_any} 局（${pct(hero.games_with_any / hero.games)}）出过针对装。`;
    $('sit-verdict').textContent = `敌方阵容对第一件针对装的影响未被可靠证实：模型在验证集 ${v.valid_n} 局上平均略好于基线，`
      + `但改善区间 [${v.ci95[0].toFixed(3)}, ${v.ci95[1].toFixed(3)}] 含 0（样本不足）。因此这里只显示整体比例，不按阵容调整。`;
    $('sit-caption').textContent = '出过针对装的局里，第一件是哪件；以及整局出过的比例';
    headRow([['装备'], ['第一件占比'], ['整局出过', 'opt']]);
    for (const it of hero.items) {
      const tr = el('tr'); const name = el('td', it.name, 'item');
      name.append(el('small', `第一件 ${it.first_n} 局`)); tr.append(name, barCell(it.first_share));
      tr.append(el('td', `${pct(it.bought_rate)}（${it.bought_n}）`, 'num opt'));
      body.append(tr);
    }
    $('sit-hint').textContent = '“第一件占比”只在出过针对装的局里计算，6 项合计 100%。“整局出过”以全部对局为分母，可多选。';
  } else {
    $('sit-status').textContent = `高分段 ${hero.games} 局；辅助样本少，只显示出现率，不建模。`;
    $('sit-verdict').textContent = '';
    $('sit-caption').textContent = '整局出过该装备的比例';
    headRow([['装备'], ['出过比例'], ['局数', 'opt']]);
    for (const it of hero.items) {
      const tr = el('tr'); const name = el('td', it.name, 'item');
      if (it.fixed) name.append(el('span', '固定装', 'tag'));
      if (it.small) name.append(el('small', '样本少（<10 局），仅供参考'));
      tr.append(name, barCell(it.rate), el('td', String(it.n), 'num opt'));
      body.append(tr);
    }
    $('sit-hint').textContent = '“固定装”是该英雄的常规关键装（见出装节奏参照），高出现率不代表针对性。';
  }
}

async function init() {
  restore();
  try {
    const r = await fetch('/api/meta', {cache: 'no-store'});
    if (!r.ok) throw new Error('页面数据读取失败，请检查服务日志');
    state.meta = await r.json();
  } catch (e) { $('fatal').textContent = e.message; return; }
  if (!state.meta.my_heroes.some(h => `${h.hero_id}:${h.position}` === state.spec)) {
    state.spec = `${state.meta.my_heroes[0].hero_id}:${state.meta.my_heroes[0].position}`;
  }
  const notes = $('notes'); for (const n of state.meta.notes) notes.append(el('li', n));
  $('run').textContent = `数据：${state.meta.run}`;
  for (const t of document.querySelectorAll('.tab')) {
    if (VIEWS.includes(t.dataset.view)) t.addEventListener('click', () => showView(t.dataset.view));
  }
  renderSetup();
  update();
  showView(state.view);
}
init();
