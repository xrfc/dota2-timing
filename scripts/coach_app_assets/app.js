'use strict';
// High-rank references: item timing (U13) and 针对装 (U20). Talks only to /api/*.
const $ = id => document.getElementById(id);
const state = {meta: null, spec: null, request: 0, view: 'items', sit: null, sitSpec: null, enemies: [], seen: [], trig: 0};
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
    localStorage.setItem(STORE, JSON.stringify({spec: state.spec, view: state.view, sitSpec: state.sitSpec, enemies: state.enemies, seen: state.seen}));
  } catch (e) { /* storage unavailable */ }
}
function restore() {
  try {
    const v = JSON.parse(localStorage.getItem(STORE) || 'null');
    if (!v) return;
    if (typeof v.spec === 'string') state.spec = v.spec;
    if (VIEWS.includes(v.view)) state.view = v.view;
    if (typeof v.sitSpec === 'string') state.sitSpec = v.sitSpec;
    if (Array.isArray(v.enemies)) state.enemies = v.enemies.filter(Number.isInteger).slice(0, 5);
    if (Array.isArray(v.seen)) state.seen = v.seen.filter(x => typeof x === 'string');
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

const ENEMY_SLOTS = 5;
function renderTriggerInputs() {
  const t = state.sit.triggers;
  const known = new Set(t.enemy_heroes.map(h => h.id));
  state.enemies = state.enemies.filter(id => known.has(id));
  const okSeen = new Set(t.seen_items.map(i => i.id));
  state.seen = state.seen.filter(id => okSeen.has(id));
  const picker = $('enemy-picker'); picker.replaceChildren();
  const heroes = [...t.enemy_heroes].sort((a, b) => a.name.localeCompare(b.name, 'zh'));
  for (let slot = 0; slot < ENEMY_SLOTS; slot++) {
    const sel = el('select'); sel.id = `enemy-${slot}`; sel.setAttribute('aria-label', `敌方英雄 ${slot + 1}`);
    const none = el('option', '—'); none.value = ''; sel.append(none);
    for (const h of heroes) {
      const o = el('option', h.name); o.value = String(h.id);
      if (state.enemies[slot] === h.id) o.selected = true;
      sel.append(o);
    }
    sel.value = state.enemies[slot] ? String(state.enemies[slot]) : '';
    sel.addEventListener('change', () => {
      const picked = []; 
      for (let i = 0; i < ENEMY_SLOTS; i++) {
        const v = i === slot ? sel.value : (state.enemies[i] ? String(state.enemies[i]) : '');
        if (v && !picked.includes(Number(v))) picked[i] = Number(v);
      }
      state.enemies = picked.filter(Boolean); save(); renderTriggerInputs(); loadTriggers();
    });
    picker.append(sel);
  }
  const box = $('seen-items'); box.replaceChildren();
  for (const it of t.seen_items) {
    const lab = el('label'); const cb = el('input'); cb.type = 'checkbox'; cb.id = `seen-${it.id}`;
    cb.checked = state.seen.includes(it.id);
    cb.addEventListener('change', () => {
      state.seen = cb.checked ? [...state.seen, it.id] : state.seen.filter(x => x !== it.id);
      save(); loadTriggers();
    });
    lab.append(cb, el('span', it.name)); box.append(lab);
  }
}

async function loadTriggers() {
  const list = $('trigger-list');
  if (!state.enemies.length) {
    list.replaceChildren();
    $('trigger-status').textContent = '选择至少一个敌方英雄后，这里列出每件针对装是否触发、原因、机制和数据结论。';
    return;
  }
  const ticket = ++state.trig;
  const q = new URLSearchParams({enemies: state.enemies.join(',')});
  if (state.seen.length) q.set('seen', state.seen.join(','));
  try {
    const r = await fetch(`/api/triggers?${q}`, {cache: 'no-store'});
    if (!r.ok) throw new Error('针对装触发读取失败');
    const view = await r.json();
    if (ticket === state.trig) renderTriggers(view);
  } catch (e) {
    if (ticket === state.trig) $('trigger-status').textContent = e.message;
  }
}

function verdictLine(label, v) {
  const p = el('p', `${label}：${v.text}`, `v-${v.kind}`);
  return p;
}

function renderTriggers(view) {
  const fired = view.items.filter(i => i.pregame || i.ingame).length;
  $('trigger-status').textContent = `对 ${view.enemies.map(e => e.name).join('、')}：${fired} 件触发（共 ${view.items.length} 件）。数据来自 ${view.samples} 局高分段一号位主宰。`;
  const list = $('trigger-list'); list.replaceChildren();
  for (const it of view.items) {
    const li = el('li', undefined, 'trigger' + (it.pregame || it.ingame ? ' fired' : ''));
    const head = el('div', undefined, 'head'); head.append(el('span', it.name, 'name'));
    head.append(el('span', it.pregame ? '赛前触发' : '赛前未触发', 'chip ' + (it.pregame ? 'on' : 'off')));
    if (it.ingame_verdict) head.append(el('span', it.ingame ? '比赛中触发' : '比赛中未触发', 'chip ' + (it.ingame ? 'on' : 'off')));
    li.append(head, el('p', it.pregame_reason));
    if (it.ingame) li.append(el('p', `已看到：${it.ingame_items.join('、')}`));
    li.append(el('p', `机制：${it.rules.join('；')}`, 'muted'));
    li.append(verdictLine('赛前数据', it.pregame_verdict));
    if (it.ingame_verdict) li.append(verdictLine('比赛中数据', it.ingame_verdict));
    if (it.note) li.append(el('p', it.note, 'muted'));
    list.append(li);
  }
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
  $('sit-triggers').hidden = hero !== state.sit.juggernaut;
  if (hero === state.sit.juggernaut) {
    renderTriggerInputs(); loadTriggers();
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
