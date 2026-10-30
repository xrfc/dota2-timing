'use strict';
// Pre-game item timing page. Talks only to /api/meta and /api/item-timing.
const $ = id => document.getElementById(id);
const state = {meta: null, spec: null, radiant: true, enemies: ['', '', '', '', ''], request: 0};
const STORE = 'coach-app-items-v1';

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function save() {
  try { localStorage.setItem(STORE, JSON.stringify({spec: state.spec, radiant: state.radiant, enemies: state.enemies})); } catch (e) { /* storage unavailable */ }
}
function restore() {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) || 'null');
    if (v && Array.isArray(v.enemies) && v.enemies.length === 5) Object.assign(state, {spec: v.spec, radiant: v.radiant !== false, enemies: v.enemies});
  } catch (e) { /* ignore */ }
}
const heroByName = name => state.meta.heroes.find(h => h.name === name.trim());
const heroName = id => (state.meta.heroes.find(h => h.id === id) || {}).name || `英雄 ${id}`;
const pct = p => `${Math.round(p * 100)}%`;
// Model cells that move the probability by <1 point look identical to the baseline; don't badge them.
const adjusted = c => c.source === 'model' && Math.abs(c.probability - c.base_rate) >= 0.01;

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
  for (const b of document.querySelectorAll('[data-radiant]')) {
    b.setAttribute('aria-pressed', String((b.dataset.radiant === '1') === state.radiant));
  }
  const list = $('hero-list');
  if (!list.children.length) for (const h of state.meta.heroes) { const o = el('option'); o.value = h.name; list.append(o); }
  const box = $('enemies');
  if (!box.children.length) {
    state.enemies.forEach((value, i) => {
      const input = el('input'); input.setAttribute('list', 'hero-list');
      input.setAttribute('aria-label', `敌方英雄 ${i + 1}`); input.placeholder = `敌方英雄 ${i + 1}`;
      input.value = value;
      input.addEventListener('change', () => { state.enemies[i] = input.value.trim(); update(); });
      box.append(input);
    });
  }
}

function enemyIds() {
  const ids = [], bad = [], myId = Number(String(state.spec).split(':')[0]);
  state.enemies.forEach((name, i) => {
    const input = $('enemies').children[i];
    if (!name) { input.removeAttribute('aria-invalid'); return; }
    const h = heroByName(name);
    const invalid = !h || ids.includes(h.id) || h.id === myId;
    input.setAttribute('aria-invalid', String(invalid));
    if (invalid) bad.push(name); else ids.push(h.id);
  });
  return {ids, bad};
}

async function update() {
  save();
  if (!state.spec) { $('result-status').textContent = '先选择你的英雄。'; return; }
  const {ids, bad} = enemyIds();
  $('enemy-count').textContent = `${ids.length}/5`;
  $('input-error').textContent = bad.length ? `无法识别或重复：${bad.join('、')}（已忽略）` : '';
  const [hero, position] = state.spec.split(':');
  const query = new URLSearchParams({hero, position, radiant: state.radiant ? '1' : '0', enemies: ids.join(',')});
  const ticket = ++state.request;
  try {
    const r = await fetch(`/api/item-timing?${query}`, {cache: 'no-store'});
    if (!r.ok) throw new Error('预测请求失败');
    const view = await r.json();
    if (ticket === state.request) renderResult(view);
  } catch (e) {
    if (ticket === state.request) $('input-error').textContent = e.message;
  }
}

function renderResult(view) {
  const [hero, position] = view.spec;
  $('result-title').textContent = `${heroName(hero)} · ${position}号位 出装节奏`;
  const changed = view.items.filter(i => i.cells.some(adjusted)).length;
  $('result-status').textContent = !view.full_lineup
    ? '敌方未填满 5 人：全部显示高分段平均节奏。'
    : changed ? `已按敌方阵容调整 ${changed} 件装备（初步）；其余为高分段平均节奏。` : '敌方阵容对这些装备没有可靠影响，显示高分段平均节奏。';
  const head = $('timing-head'); head.replaceChildren(el('th', '装备'));
  head.firstChild.scope = 'col';
  for (const m of state.meta.minutes) { const th = el('th', `${m}′`, 'min'); th.scope = 'col'; head.append(th); }
  const typ = el('th', '通常完成', 'typical'); typ.scope = 'col'; head.append(typ);
  const body = $('timing-body'); body.replaceChildren();
  for (const item of view.items) {
    const tr = el('tr');
    const name = el('td', state.meta.item_names[item.item] || item.item, 'item');
    name.append(el('small', `样本 ${item.train_n}${item.train_n < 100 ? ' · 偏少' : ''}`));
    if (item.cells.some(adjusted)) name.append(el('span', '阵容调整 · 初步', 'badge model'));
    tr.append(name);
    for (const c of item.cells) {
      const td = el('td', pct(c.display_probability), 'cell' + (adjusted(c) ? ' model' : ''));
      td.style.setProperty('--p', c.display_probability.toFixed(3));
      if (c.display_probability > 0.55) td.classList.add('dark');
      td.title = adjusted(c)
        ? `按阵容：${pct(c.probability)}（高分段平均 ${pct(c.base_rate)}）`
        : `高分段平均：${pct(c.base_rate)}`;
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
  for (const b of document.querySelectorAll('[data-radiant]')) {
    b.addEventListener('click', () => { state.radiant = b.dataset.radiant === '1'; renderSetup(); update(); });
  }
  $('clear-enemies').addEventListener('click', () => {
    state.enemies = ['', '', '', '', ''];
    for (const input of $('enemies').children) input.value = '';
    update();
  });
  const notes = $('notes'); for (const n of state.meta.notes) notes.append(el('li', n));
  $('run').textContent = `模型：${state.meta.run}`;
  renderSetup();
  update();
}
init();
