'use strict';
// High-rank item timing reference (U13). Talks only to /api/meta and /api/item-timing.
const $ = id => document.getElementById(id);
const state = {meta: null, spec: null, request: 0};
const STORE = 'coach-app-items-v2';

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function save() {
  try { localStorage.setItem(STORE, JSON.stringify({spec: state.spec})); } catch (e) { /* storage unavailable */ }
}
function restore() {
  try { const v = JSON.parse(localStorage.getItem(STORE) || 'null'); if (v && typeof v.spec === 'string') state.spec = v.spec; } catch (e) { /* ignore */ }
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
  renderSetup();
  update();
}
init();
