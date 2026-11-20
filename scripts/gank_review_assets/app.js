'use strict';
const $ = id => document.getElementById(id);
const IMG_W = 8878, IMG_H = 8356, K = 8356 / 18322;
const COLORS = {2: '#5fd08a', 3: '#f0685c', victim: '#ffd54a', smoke: '#c58bff', dim: '#96a1ab'};
const STRATA = {match: '这场比赛里1号位的每次死亡', acceptance: '验收样本（不显示规则的结论）', death: '抽样层：死亡', save_escape: '抽样层：交保命逃掉', near_miss: '抽样层：差一个条件'};
const CATEGORIES = {gank: '被抓', overextended: '自己深入', high_ground: '高地上', laning: '对线期', after_fight: '团战后留人', teamfight: '团战中', other: '其他（不算被抓）', unsure: '不确定'};
// The rule's answer in the same categories the user picks from.
const unclassified = e => e.episode_matches != null && e.episode_matches !== 1;
const ruleCategory = e => unclassified(e) ? null : !e.is_gank ? 'other' : ['death', 'save_escape'].includes(e.label) ? 'gank' : e.label;
const FLAGS = {
  enough_enemies: '敌方≥2个英雄', not_big_fight: '不在大团战', from_unseen: '从视野外出现',
  far_from_allies: '离队友远', paid: '死亡或交了保命',
};
const LABELS = {death: '被抓死', save_escape: '被抓·交出保命逃掉', overextended: '自己深入（不算被抓）', high_ground: '高地上（不考虑）', laning: '对线期、没有别路来人（不考虑）', after_fight: '小团战之后被留（不算被抓）', teamfight: '团战中（不考虑）'};
const SIGNALS = {
  enemy_tower_area: d => ['最近的塔是敌方的', d.nearest_tower_distance != null ? `距离${d.nearest_tower_distance}` : ''],
  enemy_jungle: d => ['在敌方野区', d.nearest_camp ? `离最近的野怪营地${d.nearest_camp.distance}` : ''],
  saw_attackers: d => ['看得见来的敌人', d.attackers_visible ? (d.attackers_visible.length ? d.attackers_visible.map(short).join('、') + '在之前10秒多数时间可见' : '之前10秒都基本看不见') : '算不出'],
  victim_approached: d => ['是他走向敌人', d.victim_closing_share != null ? `他走了${Math.round(d.victim_closing_share * 100)}%的靠近距离` : '算不出'],
  struck_first: d => ['他先动手', d.first_strike ? `${short(d.first_strike.name === 'attack' ? '' : d.first_strike.name) || '普攻'} → ${short(d.first_strike.target)}` : ''],
  beyond_creeps: d => ['越过己方兵线', d.beyond_creeps != null ? `${d.beyond_creeps > 0 ? '超出' : '落后'}${Math.abs(d.beyond_creeps)}` : '算不出'],
  alone_ahead: d => ['独自在队友前面', d.ahead_of_allies != null ? `比最靠前的队友${d.ahead_of_allies > 0 ? '深' : '浅'}${Math.abs(d.ahead_of_allies)}` : '无存活队友'],
};
const OUTCOMES = {death: '死亡', self_save: '自己保命逃掉', ally_save: '队友救下', self_and_ally_save: '自己加队友保命', none: '没死也没交保命'};
const map = new Image();
const canvas = $('map'), ctx = canvas.getContext('2d');
let blind = false, clips = [], names = {}, judgments = {}, clip = null, index = 0, playing = false, timer = null, verdict = null;

const zh = name => names[name] || String(name || '').replace(/^npc_dota_hero_|^item_/, '');
const short = name => zh(name).split('·').pop();
const clock = t => `${t < 0 ? '-' : ''}${Math.floor(Math.abs(t) / 60)}:${String(Math.abs(t) % 60).padStart(2, '0')}`;
const pixel = (x, y) => [261 + (x - 7487) * K, (26015 - y) * K];
function el(tag, text, cls) { const e = document.createElement(tag); if (text != null) e.textContent = text; if (cls) e.className = cls; return e; }

function buildList() {
  const list = $('list'); list.replaceChildren();
  const done = clips.filter(c => judgments[c.id]?.verdict).length;
  list.append(el('div', `已判断 ${done} / ${clips.length}`, 'progress'));
  list.firstChild.id = 'progress';
  for (const key of Object.keys(STRATA)) {
    const group = clips.filter(c => c.stratum === key);
    const decided = group.filter(c => !unclassified(c.episode) && judgments[c.id]?.verdict && judgments[c.id].verdict !== 'unsure');
    const agree = decided.filter(c => judgments[c.id].verdict === ruleCategory(c.episode)).length;
    const head = el('h3', STRATA[key] + ' ');
    head.append(el('small', decided.length && !blind ? `与规则一致 ${agree}/${decided.length}` : ''));
    if (!group.length) continue;
    list.append(head);
    for (const c of group) {
      const a = el('a'); a.tabIndex = 0; a.dataset.id = c.id;
      if (clip && c.id === clip.id) a.className = 'current';
      const v = judgments[c.id]?.verdict;
      const mark = !v ? '' : v === 'unsure' ? 'unsure' : blind || unclassified(c.episode) ? 'done' : v === ruleCategory(c.episode) ? 'right' : 'wrong';
      a.title = !v ? '' : blind || unclassified(c.episode) ? `你选的：${CATEGORIES[v] || v}` : `你选的：${CATEGORIES[v] || v}；规则：${CATEGORIES[ruleCategory(c.episode)]}`;
      a.append(el('b', c.id), el('span', short(c.episode.victim) + (c.episode.primary_reason ? ' · ' + c.episode.primary_reason[1] : ''), 'hero'), el('i', {right: '＝', wrong: '≠', unsure: '?', done: '✓'}[mark] || '', mark));
      a.addEventListener('click', () => open(c.id));
      a.addEventListener('keydown', e => { if (e.key === 'Enter') open(c.id); });
      list.append(a);
    }
  }
}

function fact(label, value, cls) { $('facts').append(el('dt', label), el('dd', value, cls)); }

function open(id) {
  stop();
  clip = clips.find(c => c.id === id) || clips[0];
  const e = clip.episode;
  history.replaceState(null, '', '#' + clip.id);
  $('title').textContent = `${clip.id} · ${zh(e.victim)} · 比赛 ${e.match_id} · ${clock(e.t0)}`;
  const failed = Object.entries(FLAGS).filter(([key]) => !e.flags?.[key]).map(([, label]) => label);
  const ruled = e.is_gank ? LABELS[e.label] : `不算被抓（不满足：${failed.join('、')}）`;
  if (blind) $('question').replaceChildren(el('span', '验收：规则已冻结，这里不显示规则的结论。你认为这次是哪一类？在右边选。'));
  else if (unclassified(e)) $('question').textContent = e.primary_reason[1] + '，可查看死亡前后的录像。';
  else $('question').replaceChildren(el('span', '规则判定：'), el('strong', ruled, ruleCategory(e)), el('span', ' 　你认为这次是哪一类？在右边选。'));
  $('facts').replaceChildren();
  if (e.primary_reason) fact('主要原因（草稿）', e.primary_reason[1], 'head');
  if (e.tags) fact('这次死亡的特征', e.tags.map(t => t[1]).join('；'), 'head');
  $('risk').hidden = !e.risk;
  if (e.risk_unavailable) fact('死亡风险', e.risk_unavailable);
  if (e.risk) {
    const r = e.risk, death = r.death ?? e.end;
    if (r.fight_measure) {
      const verdict = r.fight_start == null ? '此死亡缺少评估样本'
        : r.alert_second != null ? `在 ${clock(r.alert_second)} 提醒，距交战开始 ${r.fight_start - r.alert_second} 秒`
        : r.could_alert ? '交战前有评估样本，未触发提醒' : '预测窗口内没有合适的交战前样本';
      fact('交战前提醒', verdict, r.alert_second != null ? 'warn' : '');
      $('risk-note').textContent = `每 ${r.step} 秒估计未来 ${r.horizon} 秒的死亡概率。虚线为交战外提醒阈值，点图可跳到对应时刻。`;
    } else {
      const early = r.points.filter(p => p[0] < death && p[0] >= death - r.horizon && !p[2] && p[1] >= r.threshold);
      const peak = Math.max(0, ...r.points.filter(p => p[0] < death).map(p => p[1]));
      fact('死亡风险（模型）', (early.length ? `死前${death - early[0][0]}秒超过提醒线（那时最近3秒没挨打）` : '死前20秒内，最近3秒没挨打的时刻都没超过提醒线') + `；死前最高${Math.round(peak * 100)}%`, early.length ? 'warn' : '');
      $('risk-note').textContent = `模型估计的“${r.horizon}秒内死亡”的概率，每${r.step || 5}秒一个点，只用他当时能知道的信息；没训练过这场比赛。虚线是提醒线（在最近3秒没挨打的时刻里误报约${Math.round(r.false_alarm_rate * 100)}%），空心点表示前3秒挨过打。“最近3秒没挨打”不等于这一波还没挨过打。点图可跳到那一秒。`;
    }
  }
  fact('结果', OUTCOMES[e.outcome] || e.outcome);
  if (!unclassified(e)) {
    fact('参与的敌人', e.attackers.map(short).join('、') || '—');
    fact('视野外出现', e.unseen_attackers.map(short).join('、') || '没有', e.unseen_attackers.length ? '' : 'no');
    fact('开雾的敌人', clip.smoked_attackers.length ? clip.smoked_attackers.map(short).join('、') + `（起点前${clip.smoke_lookback}秒内）` : '没有', clip.smoked_attackers.length ? 'smoke' : '');
  }
  if (clip.wards) {
    const vi0 = clip.heroes.findIndex(h => h.hero === e.victim), f0 = clip.frames.find(f => f.t === e.t0), me = f0 && f0.h[vi0];
    const team = clip.heroes[vi0].team;
    const near = me ? clip.wards.filter(w => w.type === 'observer' && w.team !== team && w.start <= e.t0 && w.end >= e.t0 && Math.hypot(w.x - me[0], w.y - me[1]) <= 1600).length : 0;
    fact('起点时敌方假眼', me ? (near ? `${near}个在1600以内（没算地形和树的遮挡）` : '1600以内没有') : '算不出', near ? 'warn' : '');
  }
  if (!unclassified(e)) {
    fact('用掉的保命', [...e.self_saves, ...e.ally_saves].map(s => short(s.name)).join('、') || '—');
    fact('最近队友', e.nearest_ally == null ? '无存活队友' : `${Math.round(e.nearest_ally)}（门槛1500）`);
    fact('附近英雄', `最多${e.most_heroes_near}个，我方${e.most_allies_near}个（门槛：合计≤6、我方≤2）`);
    if (!blind) for (const [key, label] of Object.entries(FLAGS)) fact(label, e.flags[key] ? '✓ 满足' : '✗ 不满足', e.flags[key] ? 'yes' : 'no');
  }
  if (e.depth) {
    const d = e.depth, final = e.is_gank ? e.label : null, laneEnd = d.laning_end ?? 600;
    const where = d.high_ground ? ` · 在${d.high_ground === 2 ? '天辉' : '夜魇'}高地范围内` : '';
    const lane = d.laning ? ' · 对线期且来的都是本路对手' : (d.attackers_from_other_lanes || []).length && e.t0 < laneEnd ? ` · 别路来人：${d.attackers_from_other_lanes.map(short).join('、')}` : '';
    if (!blind) $('facts').append(el('dt', '信号', 'head'), el('dd', `越过中线${d.depth}${where}${lane}`, 'head'));
    if (d.attackers_from_other_lanes) {
      const other = d.attackers_from_other_lanes, same = e.attackers.filter(a => !other.includes(a));
      fact('来的人对线时', `本路：${same.map(short).join('、') || '—'}；别路：${other.map(short).join('、') || '—'}${e.t0 >= laneEnd ? '（对线期已过，仅供参考）' : ''}`);
      if (!blind && d.laning_end != null) fact('这一路对线期到', `${clock(d.laning_end)}（一塔倒或一半英雄离线，草稿）`);
    }
    if (!blind && d.attackers_accounted) fact('来的人此前有着落', `${d.attackers_accounted.length}/${e.attackers.length}（60秒内死过，或在5000以外露过面${d.attackers_accounted.length ? '：' + d.attackers_accounted.map(short).join('、') : ''}）`);
    const f = d.after_fight;
    if (!blind) fact('之前30秒打过架', f ? `✓ 是（起点前${e.t0 - f.first_trade}秒开始交手；${f.deaths.length ? `附近阵亡：${f.deaths.map(x => short(x.hero)).join('、')}` : `身边最多${f.most_heroes}个英雄`}）` : '✗ 否', f ? 'warn' : '');
    for (const [key, describe] of blind ? [] : Object.entries(SIGNALS)) {
      const [label, detail] = describe(d), on = d.signals[key];
      fact(label, (on == null ? '？' : on ? '✓ 是' : '✗ 否') + (detail ? `（${detail}）` : ''), on ? 'warn' : '');
    }
    if (!blind) fact('规则判定', final ? LABELS[final] : '不算被抓（四个条件没全满足）', final === 'death' || final === 'save_escape' ? 'yes' : 'no');
  }
  const saved = judgments[clip.id] || {};
  verdict = saved.verdict || null; $('note').value = saved.note || ''; $('saved').textContent = '';
  showVerdict();
  $('time').max = clip.frames.length - 1;
  buildEvents(); buildList();
  const alert = e.risk?.alert_second;
  seek(alert == null ? 0 : Math.max(0, clip.frames.findIndex(f => f.t >= alert)));
  document.querySelector('#list a.current')?.scrollIntoView({block: 'nearest'});
}

function showVerdict() {
  for (const b of document.querySelectorAll('#verdicts button')) b.classList.toggle('on', b.dataset.verdict === verdict);
}

function eventText(ev) {
  if (ev.kind === 'damage') return `${short(ev.source)} 打了 ${short(ev.target)} ${ev.value}`;
  if (ev.kind === 'death') return `${short(ev.target)} 死亡${ev.source && names[ev.source] ? '（' + short(ev.source) + '）' : ''}`;
  if (ev.kind === 'smoke') return `${short(ev.target)} 进入开雾状态`;
  const to = ev.target && ev.target !== ev.source ? ' → ' + short(ev.target) : ev.target_other ? ' → 非英雄单位' : '';
  const hits = (ev.hits || []).filter(h => h !== ev.target);
  return `${zh(ev.source).split('·')[0]} 用 ${short(ev.name)}${to}${hits.length ? `（${to ? '还' : ''}打中 ${hits.map(short).join('、')}）` : ''}`;
}

function buildEvents() {
  const e = clip.episode, involved = new Set([e.victim, ...e.attackers]);
  const saves = new Set([...e.self_saves, ...e.ally_saves].map(s => `${s.t}|${s.name}`));
  const list = $('events'); list.replaceChildren();
  for (const ev of clip.events) {
    const mine = ev.kind !== 'cast' || involved.has(ev.source);
    if (!mine && !$('all-casts').checked) continue;
    if (ev.kind === 'death' && !$('all-casts').checked && !involved.has(ev.target)) continue;
    const isSave = ev.kind === 'cast' && saves.has(`${ev.t}|${ev.name}`);
    const li = el('li', null, ev.kind + (isSave ? ' save' : '')); li.dataset.t = ev.t;
    const rel = ev.t - e.t0;
    li.append(el('time', (rel >= 0 ? '+' : '') + rel), el('span', eventText(ev) + (isSave ? '（保命）' : '')));
    li.addEventListener('click', () => { stop(); seek(clip.frames.findIndex(f => f.t >= ev.t)); });
    list.append(li);
  }
}

function view() {
  const half = Number($('zoom').value);
  if (!half) return {x: 0, y: 0, w: IMG_W, h: IMG_W};
  const e = clip.episode, vi = clip.heroes.findIndex(h => h.hero === e.victim);
  const fixed = clip.frames.find(f => f.t >= e.t0 && f.h[vi]) || clip.frames.find(f => f.h[vi]);
  const at = $('follow').checked && clip.frames[index].h[vi] ? clip.frames[index] : fixed;
  const [cx, cy] = pixel(at.h[vi][0], at.h[vi][1]);
  const w = half * 2 * K;
  return {x: cx - w / 2, y: cy - w / 2, w, h: w};
}

function draw() {
  if (!clip) return;
  const v = view(), S = canvas.width / v.w, frame = clip.frames[index], e = clip.episode;
  const P = (x, y) => { const [px, py] = pixel(x, y); return [(px - v.x) * S, (py - v.y) * S]; };
  ctx.fillStyle = '#0b0e11'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (map.complete && map.naturalWidth) ctx.drawImage(map, v.x, v.y, v.w, v.h, 0, 0, canvas.width, canvas.height);
  ctx.fillStyle = 'rgba(8,10,12,.35)'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  const vi = clip.heroes.findIndex(h => h.hero === e.victim), vs = frame.h[vi];
  if (vs) {
    const [x, y] = P(vs[0], vs[1]);
    ctx.lineWidth = 1.5; ctx.strokeStyle = 'rgba(255,213,74,.7)';
    ctx.setLineDash([8, 6]); ctx.beginPath(); ctx.arc(x, y, 1500 * K * S, 0, 7); ctx.stroke();
    ctx.setLineDash([2, 5]); ctx.beginPath(); ctx.arc(x, y, 1600 * K * S, 0, 7); ctx.stroke();
    ctx.setLineDash([]);
  }
  for (const [team, tx, ty] of clip.towers || []) {  // towers standing at the start
    const [x, y] = P(tx, ty);
    ctx.fillStyle = COLORS[team]; ctx.strokeStyle = '#10171c'; ctx.lineWidth = 2;
    ctx.fillRect(x - 7, y - 7, 14, 14); ctx.strokeRect(x - 7, y - 7, 14, 14);
  }
  for (const w of clip.wards || []) {  // wards standing this second (U152)
    if (frame.t < w.start || frame.t > w.end || !$('wards').checked) continue;
    const [x, y] = P(w.x, w.y), observer = w.type === 'observer';
    if (observer) {  // an observer ward sees 1600 around it (terrain and trees not applied)
      ctx.beginPath(); ctx.arc(x, y, 1600 * K * S, 0, 7);
      ctx.fillStyle = w.team === 2 ? 'rgba(95,208,138,.07)' : 'rgba(240,104,92,.07)'; ctx.fill();
      ctx.strokeStyle = COLORS[w.team]; ctx.globalAlpha = .35; ctx.lineWidth = 1; ctx.stroke(); ctx.globalAlpha = 1;
    }
    ctx.beginPath(); ctx.moveTo(x, y - 9); ctx.lineTo(x + 7, y); ctx.lineTo(x, y + 9); ctx.lineTo(x - 7, y); ctx.closePath();
    ctx.fillStyle = observer ? '#ffe066' : '#6ab8ff'; ctx.fill();
    ctx.strokeStyle = COLORS[w.team]; ctx.lineWidth = 2.5; ctx.stroke();
  }
  const r = Math.max(9, Math.min(16, 300 * K * S));
  clip.heroes.forEach((h, i) => {  // trails of the last 6 seconds
    ctx.beginPath(); let started = false;
    for (let j = Math.max(0, index - 6); j <= index; j++) {
      const s = clip.frames[j].h[i]; if (!s || !s[4]) { started = false; continue; }
      const [x, y] = P(s[0], s[1]); started ? ctx.lineTo(x, y) : ctx.moveTo(x, y); started = true;
    }
    ctx.strokeStyle = COLORS[h.team]; ctx.globalAlpha = .55; ctx.lineWidth = 3; ctx.stroke(); ctx.globalAlpha = 1;
  });
  for (const ev of clip.events) {  // hits on the victim this second
    if (ev.kind !== 'damage' || ev.t !== frame.t || !vs) continue;
    const s = frame.h[clip.heroes.findIndex(h => h.hero === ev.source)]; if (!s) continue;
    const [x1, y1] = P(s[0], s[1]), [x2, y2] = P(vs[0], vs[1]);
    ctx.strokeStyle = '#ffb0a8'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }
  clip.heroes.forEach((h, i) => {
    const s = frame.h[i]; if (!s) return;
    const [x, y] = P(s[0], s[1]), alive = s[4], seen = s[5], smoked = s[6];
    const isVictim = h.hero === e.victim, isAttacker = e.attackers.includes(h.hero);
    if (!alive) {
      ctx.strokeStyle = COLORS.dim; ctx.lineWidth = 3; ctx.beginPath();
      ctx.moveTo(x - r * .7, y - r * .7); ctx.lineTo(x + r * .7, y + r * .7); ctx.moveTo(x + r * .7, y - r * .7); ctx.lineTo(x - r * .7, y + r * .7); ctx.stroke();
    } else {
      ctx.beginPath(); ctx.arc(x, y, r, 0, 7);
      ctx.fillStyle = COLORS[h.team]; ctx.globalAlpha = seen ? 1 : .35; ctx.fill(); ctx.globalAlpha = 1;
      ctx.lineWidth = isVictim || isAttacker ? 3.5 : 2;
      ctx.strokeStyle = isVictim ? COLORS.victim : isAttacker ? '#fff' : '#10171c';
      if (!seen) ctx.setLineDash([5, 4]);
      ctx.stroke(); ctx.setLineDash([]);
      if (smoked) { ctx.beginPath(); ctx.arc(x, y, r + 6, 0, 7); ctx.strokeStyle = COLORS.smoke; ctx.lineWidth = 3; ctx.stroke(); }
      if (s[3]) {
        const w = r * 2.4, share = Math.max(0, Math.min(1, s[2] / s[3]));
        ctx.fillStyle = '#10171c'; ctx.fillRect(x - w / 2, y + r + 5, w, 5);
        ctx.fillStyle = share > .5 ? '#5fd08a' : share > .25 ? '#e0b040' : '#f0685c'; ctx.fillRect(x - w / 2, y + r + 5, w * share, 5);
      }
    }
    ctx.font = `${isVictim ? 'bold ' : ''}13px system-ui, "Microsoft YaHei", sans-serif`; ctx.textAlign = 'center';
    ctx.lineWidth = 4; ctx.strokeStyle = '#10171c'; ctx.fillStyle = alive ? '#fff' : COLORS.dim;
    const label = short(h.hero) + (alive ? '' : '（死亡）');
    ctx.strokeText(label, x, y - r - 6); ctx.fillText(label, x, y - r - 6);
  });
  const evidence = $('team-evidence');
  evidence.hidden = e.death_second == null;
  if (!evidence.hidden) {
    const team = clip.heroes[vi].team;
    const visible = clip.heroes.filter((hero, i) => hero.team !== team && frame.h[i]?.[4] && frame.h[i][5]);
    const allies = clip.heroes.flatMap((hero, i) => {
      const state = frame.h[i];
      return hero.team === team && i !== vi && vs?.[4] && state?.[4]
        ? [Math.hypot(state[0] - vs[0], state[1] - vs[1])] : [];
    });
    evidence.textContent = `${clock(frame.t)} 己方视野记录：${visible.map(h => short(h.hero)).join('、') || '未记录到可见敌方英雄'}。最近存活队友距离：${allies.length ? Math.round(Math.min(...allies)) : '无可用距离'}。`;
  }
  const rel = frame.t - e.t0;
  $('clock').textContent = `起点${rel >= 0 ? '后' : '前'} ${Math.abs(rel)} 秒 · 游戏时间 ${clock(frame.t)}`;
  for (const li of $('events').children) {
    const t = Number(li.dataset.t);
    li.classList.toggle('past', t < frame.t); li.classList.toggle('now', t === frame.t);
  }
}

const RISK_PAD = {l: 34, r: 8, t: 8, b: 18};
function riskX(t, w) { const f = clip.frames; return RISK_PAD.l + (t - f[0].t) / Math.max(1, f[f.length - 1].t - f[0].t) * (w - RISK_PAD.l - RISK_PAD.r); }
function drawRisk(now) {
  const r = clip.episode.risk; if (!r) return;
  const c = $('risk-chart'), g = c.getContext('2d'), w = c.width, h = c.height;
  const top = Math.max(r.threshold * 1.5, ...r.points.map(p => p[1]), 0.05);
  const y = v => h - RISK_PAD.b - v / top * (h - RISK_PAD.t - RISK_PAD.b);
  g.fillStyle = '#0b0e11'; g.fillRect(0, 0, w, h);
  g.font = '11px system-ui, sans-serif'; g.fillStyle = COLORS.dim;
  g.fillText('0', 4, y(0) + 4); g.fillText(`${Math.round(top * 100)}%`, 4, y(top) + 8);
  g.strokeStyle = '#2c353d'; g.beginPath(); g.moveTo(RISK_PAD.l, y(0)); g.lineTo(w - RISK_PAD.r, y(0)); g.stroke();
  g.setLineDash([6, 5]); g.strokeStyle = '#e0b040'; g.beginPath(); g.moveTo(RISK_PAD.l, y(r.threshold)); g.lineTo(w - RISK_PAD.r, y(r.threshold)); g.stroke(); g.setLineDash([]);
  const e = clip.episode;
  for (const [t, label] of [[e.t0, '起点'], [r.death, '死亡']]) {
    if (t == null) continue; const x = riskX(t, w);
    g.strokeStyle = '#2c353d'; g.beginPath(); g.moveTo(x, RISK_PAD.t); g.lineTo(x, h - RISK_PAD.b); g.stroke();
    g.fillStyle = COLORS.dim; g.fillText(label, x + 3, h - 5);
  }
  g.strokeStyle = COLORS.victim; g.lineWidth = 1.5; g.beginPath();
  r.points.forEach(([t, v], i) => { const x = riskX(t, w); i ? g.lineTo(x, y(v)) : g.moveTo(x, y(v)); }); g.stroke(); g.lineWidth = 1;
  for (const [t, v, hit] of r.points) {
    g.beginPath(); g.arc(riskX(t, w), y(v), 3.5, 0, 7);
    if (r.fight_measure) { g.fillStyle = t === r.alert_second ? '#e0b040' : COLORS.victim; g.fill(); }
    else if (hit) { g.strokeStyle = COLORS.victim; g.stroke(); } else { g.fillStyle = v >= r.threshold ? '#e0b040' : COLORS.victim; g.fill(); }
  }
  const x = riskX(now, w); g.strokeStyle = '#4aa3ff'; g.beginPath(); g.moveTo(x, RISK_PAD.t); g.lineTo(x, h - RISK_PAD.b); g.stroke();
}
$('risk-chart').addEventListener('click', ev => {
  if (!clip || !clip.episode.risk) return;
  const c = $('risk-chart'), box = c.getBoundingClientRect(), px = (ev.clientX - box.left) * c.width / box.width;
  const f = clip.frames, t = f[0].t + (px - RISK_PAD.l) / (c.width - RISK_PAD.l - RISK_PAD.r) * (f[f.length - 1].t - f[0].t);
  let best = 0; f.forEach((fr, i) => { if (Math.abs(fr.t - t) < Math.abs(f[best].t - t)) best = i; }); stop(); seek(best);
});

function seek(i) { index = Math.max(0, Math.min(clip.frames.length - 1, i)); $('time').value = index; draw(); drawRisk(clip.frames[index].t); }
function stop() { playing = false; clearTimeout(timer); $('play').textContent = '播放'; }
function tick() {
  if (!playing) return;
  if (index >= clip.frames.length - 1) { stop(); return; }
  seek(index + 1); timer = setTimeout(tick, 1000 / Number($('speed').value));
}
function toggle() {
  if (playing) { stop(); return; }
  if (index >= clip.frames.length - 1) seek(0);
  playing = true; $('play').textContent = '暂停'; timer = setTimeout(tick, 1000 / Number($('speed').value));
}

async function save(next) {
  $('saved').textContent = '保存中…';
  try {
    const r = await fetch('/api/judgment', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: clip.id, verdict, note: $('note').value})});
    if (!r.ok) throw new Error(String(r.status));
    judgments[clip.id] = {verdict, note: $('note').value};
    $('saved').textContent = '已保存'; buildList();
    if (next) { const i = clips.indexOf(clip); if (i < clips.length - 1) open(clips[i + 1].id); else $('saved').textContent = '已保存，这是最后一个'; }
  } catch (err) { $('saved').textContent = '保存失败，请确认页面服务还在运行'; }
}

$('play').addEventListener('click', toggle);
$('restart').addEventListener('click', () => { stop(); seek(0); });
$('to-start').addEventListener('click', () => { stop(); seek(clip.frames.findIndex(f => f.t >= clip.episode.t0)); });
$('time').addEventListener('input', () => { stop(); seek(Number($('time').value)); });
$('zoom').addEventListener('change', draw);
$('follow').addEventListener('change', draw);
$('all-casts').addEventListener('change', () => { buildEvents(); draw(); });
$('wards').addEventListener('change', draw);
$('save').addEventListener('click', () => save(true));
for (const b of document.querySelectorAll('#verdicts button')) b.addEventListener('click', () => { verdict = verdict === b.dataset.verdict ? null : b.dataset.verdict; showVerdict(); save(false); });
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' && e.target.type === 'text' || e.target.tagName === 'SELECT') return;
  if (e.key === ' ') { e.preventDefault(); toggle(); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); stop(); seek(index - 1); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); stop(); seek(index + 1); }
});
map.addEventListener('load', draw);

(async () => {
  try {
    const [c, j] = await Promise.all([fetch('/api/clips').then(r => r.json()), fetch('/api/judgments').then(r => r.json())]);
    clips = c.clips; names = c.names; blind = !!c.blind; judgments = j.judgments || {};
    map.src = '/map.jpg';
    if (!clips.length) { $('title').textContent = '本次复盘没有可播放的死亡片段'; return; }
    open(location.hash.slice(1) || (clips.find(x => !judgments[x.id]?.verdict) || clips[0]).id);
  } catch (err) { $('title').textContent = '读取失败：请确认页面服务还在运行'; }
})();
