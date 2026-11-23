"use strict";

const byId = (id) => document.getElementById(id);
const portrait = {
  "幻影刺客": "phantom_assassin",
  "斯温": "sven",
  "风行者": "windrunner",
  "噬魂鬼": "life_stealer",
};

const domains = ["全部", "兵线", "打野", "支援"];
let matches = [];
let current;
let active = -1;
let filter = "全部";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function seconds(time) {
  const [m, s] = time.split(":").map(Number);
  return m * 60 + s;
}

function domainTag(name) {
  const badge = element("span", "domain", name);
  badge.dataset.domain = name;
  return badge;
}

function table(headings, records, className) {
  const scroller = element("div", "table-scroll");
  const node = element("table", className);
  const head = node.createTHead().insertRow();
  for (const heading of headings) {
    const cell = element("th", "", heading);
    cell.scope = "col";
    head.append(cell);
  }
  const body = node.createTBody();
  for (const record of records) {
    const row = body.insertRow();
    for (const value of record) row.insertCell().textContent = value;
  }
  scroller.append(node);
  return scroller;
}

function noteList(items, className = "note-list") {
  const list = element("div", className);
  for (const note of items) list.append(element("p", "", note));
  return list;
}

function banner() {
  byId("matches").value = current.id;
  const stats = byId("stats");
  stats.replaceChildren();
  for (const [key, title] of [["opportunities", "候选时刻"], ["eligible", "可复盘"], ["balanced", "可比较"]]) {
    const stat = element("div", "stat");
    const value = current.counts.reduce((sum, scene) => sum + scene[key], 0);
    stat.append(element("b", "", value), element("span", "", title));
    stats.append(stat);
  }
  const art = byId("hero-art");
  art.replaceChildren();
  for (const hero of current.heroes) {
    const fighter = element("div", "fighter no-art");
    const slug = portrait[hero];
    if (slug) {
      const img = element("img");
      img.alt = "";
      img.addEventListener("load", () => fighter.classList.remove("no-art"));
      img.addEventListener("error", () => img.remove());
      img.src = "/heroes/" + slug + ".png";
      fighter.append(img);
    }
    fighter.append(element("span", "", hero));
    art.append(fighter);
  }
  document.title = current.heroes.join(" / ") + " · 一号位行动复盘";
}

function coverage() {
  const target = byId("coverage-content");
  target.replaceChildren(table(
    ["场景", "候选机会", "可复盘", "有双动作支持", "可比较"],
    current.counts.map((row) => [row.domain, row.opportunities, row.eligible, row.supported, row.balanced]),
  ));
  if (current.notes.length) target.append(noteList(current.notes));
  if (current.coverage.length) {
    target.append(element("h3", "", "逐秒输入覆盖"), noteList(current.coverage));
  }
  if (current.excluded.length) {
    target.append(element("h3", "", "未进入复盘的候选 · " + current.excluded.length + " 段"), table(
      ["时刻", "一号位", "场景", "动作", "排除原因"],
      current.excluded.map((row) => [row.time, row.hero, row.domain, row.action, row.reason]),
    ));
  }
}

function visibleIndices() {
  return current.clips.flatMap((clip, index) => filter === "全部" || clip.domain === filter ? [index] : []);
}

function timeline() {
  const filters = byId("filters");
  filters.replaceChildren();
  for (const name of domains) {
    const button = element("button", "", name);
    button.type = "button";
    button.setAttribute("aria-pressed", String(name === filter));
    button.addEventListener("click", () => {
      const next = current.clips.findIndex((clip) => name === "全部" || clip.domain === name);
      const keep = active >= 0 && (name === "全部" || current.clips[active].domain === name);
      select(current, keep ? active : next, name);
      byId("filters").querySelector('[aria-pressed="true"]').focus({preventScroll: true});
    });
    filters.append(button);
  }
  const list = byId("clips");
  list.replaceChildren();
  const indices = visibleIndices();
  byId("clip-count").textContent = indices.length + " 段";
  if (!indices.length) list.append(element("p", "empty", "此场景没有可复盘片段。"));
  for (const index of indices) {
    const clip = current.clips[index];
    const button = element("button", "clip");
    button.type = "button";
    button.dataset.time = clip.time;
    button.dataset.domain = clip.domain;
    button.dataset.index = index;
    button.setAttribute("aria-current", String(index === active));
    button.append(element("span", "clip-time", clip.time), element("span", "clip-name", clip.hero), domainTag(clip.domain));
    button.addEventListener("click", () => {
      select(current, index, filter);
      list.querySelector('[aria-current="true"]').focus({preventScroll: true});
    });
    list.append(button);
  }
  const selected = list.querySelector('[aria-current="true"]');
  if (selected) {
    const bounds = list.getBoundingClientRect();
    const item = selected.getBoundingClientRect();
    if (item.top < bounds.top || item.bottom > bounds.bottom) {
      list.scrollTop += item.top - bounds.top - (bounds.height - item.height) / 2;
    }
  }
}

function stepButton(direction, newIndex) {
  const label = direction === "prev" ? "上一段" : "下一段";
  const button = element("button", "nav-button " + direction);
  button.type = "button";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.disabled = newIndex === undefined;
  button.addEventListener("click", () => {
    select(current, newIndex, filter);
    const nav = byId("detail").querySelector(".nav");
    (nav.querySelector("." + direction + ":enabled") || nav.querySelector(":enabled"))?.focus({preventScroll: true});
  });
  return button;
}

function sectionHead(title, meta) {
  const heading = element("div", "section-head");
  heading.append(element("h3", "", title));
  if (meta) heading.append(element("span", "window", meta));
  return heading;
}

function comparison(clip, estimates) {
  const section = element("section");
  section.append(sectionHead("两种动作的估计", "来自相似历史局面"));
  const legend = element("div", "legend");
  for (const row of estimates) legend.append(element("span", "", row.label.replace(/估计$/, "")));
  section.append(legend);
  const charts = element("div", "charts");
  // Only chart nonnegative metrics. Each pair shares one scale and prints both raw values.
  const candidates = clip.domain === "支援" ? ["队友受击时到场", "死亡"] : [clip.metrics[0], "死亡"];
  for (const key of candidates) {
    const index = clip.metrics.indexOf(key);
    if (index < 0) continue;
    const values = estimates.map((row) => row.values[index]);
    const magnitudes = values.map((value) => Number.parseFloat(value));
    if (!magnitudes.every((number) => Number.isFinite(number) && number >= 0)) continue;
    const max = Math.max(...magnitudes) || 1;
    const chart = element("div", "chart");
    chart.append(element("h3", "", key === "死亡" ? "自身死亡概率" : key === "队友受击时到场" ? "队友受击时到场率" : key));
    values.forEach((value, i) => {
      const row = element("div", "bar-row");
      row.setAttribute("aria-label", estimates[i].label + " " + value);
      const track = element("div", "track");
      const fill = element("i");
      fill.style.width = 100 * magnitudes[i] / max + "%";
      track.append(fill);
      row.append(track, element("b", "", value));
      chart.append(row);
    });
    charts.append(chart);
  }
  if (charts.childElementCount) {
    section.append(charts, element("p", "comparison-note", "每项指标内按同一刻度比较。未选动作的后果由模型估计。"));
  }
  return section;
}

function detail() {
  const target = byId("detail");
  clearPerspective();
  target.replaceChildren();
  if (active < 0) {
    target.append(element("p", "empty", "当前筛选下没有片段。可在时间线切换场景。"));
    return;
  }
  const clip = current.clips[active];
  const indices = visibleIndices();
  const offset = indices.indexOf(active);
  const header = element("div", "detail-header");
  const heading = element("div", "clip-heading");
  heading.append(element("strong", "big-time", clip.time), element("h2", "", clip.hero), domainTag(clip.domain));
  const nav = element("div", "nav");
  nav.append(stepButton("prev", indices[offset - 1]), stepButton("next", indices[offset + 1]));
  header.append(heading, nav);
  const observed = element("div", "observed");
  const action = element("div");
  action.append(element("small", "", "实际动作"), element("strong", "", clip.action));
  observed.append(action, element("span", "window", "决策后 1–6 秒"));
  target.append(header, observed);
  mountPerspective(target, current.id, clip);
  const estimates = clip.rows.slice(1);
  const comparisonNotes = clip.notes.filter((note) => note.startsWith("双动作比较证据不足。"));
  if (estimates.length === 2) {
    target.append(comparison(clip, estimates));
  } else if (comparisonNotes.length) {
    const evidence = element("aside", "evidence");
    evidence.append(element("h3", "", "本段仅展示录像实况"));
    for (const note of comparisonNotes) {
      const reason = note.replace("双动作比较证据不足。", "");
      evidence.append(element("p", "", reason));
    }
    target.append(evidence);
  }
  const outcomes = element("section", "table-block");
  outcomes.append(sectionHead("逐项结果", "观察窗 7–20 秒"));
  const results = table(["指标", ...clip.rows.map((row) => row.label)],
    clip.metrics.map((metric, index) => [metric, ...clip.rows.map((row) => row.values[index])]), "results");
  const headers = results.querySelectorAll("thead th");
  if (headers[2]) headers[2].classList.add("action-a");
  if (headers[3]) headers[3].classList.add("action-b");
  outcomes.append(results);
  target.append(outcomes);
  const notes = clip.notes.filter((note) => !comparisonNotes.includes(note));
  if (notes.length) target.append(noteList(notes, "clip-notes"));
}

function render(match, index, name) {
  const changed = current !== match;
  current = match;
  active = index;
  filter = name;
  if (changed) {
    banner();
    coverage();
    byId("coverage").open = false;
  }
  timeline();
  detail();
}

function select(match, index, name) {
  const params = new URLSearchParams({match: match.id});
  if (index >= 0) {
    const time = match.clips[index].time;
    params.set("t", seconds(time));
    // Equal timestamps can occur for different heroes or action domains.
    if (match.clips.findIndex((clip) => clip.time === time) !== index) params.set("i", index);
  }
  if (name !== "全部") params.set("scene", name);
  const next = "#" + params.toString();
  if (location.hash !== next) history.pushState(null, "", next);
  render(match, index, name);
}

function preferredClip(match, scope) {
  const preferred = match.clips.findIndex((clip) => scope(clip) && clip.domain === "支援" && clip.rows.length === 3);
  return preferred >= 0 ? preferred : match.clips.findIndex(scope);
}

function restore() {
  const params = new URLSearchParams(location.hash.slice(1));
  const match = matches.find((entry) => entry.id === params.get("match")) || matches[0];
  const name = domains.includes(params.get("scene")) ? params.get("scene") : "全部";
  const wanted = params.has("t") ? Number(params.get("t")) : -1;
  const accepts = (clip) => name === "全部" || clip.domain === name;
  const hint = params.has("i") ? Number(params.get("i")) : -1;
  const hinted = Number.isInteger(hint) && match.clips[hint];
  let index = hinted && seconds(hinted.time) === wanted && accepts(hinted)
    ? hint : match.clips.findIndex((clip) => seconds(clip.time) === wanted && accepts(clip));
  if (index < 0) index = preferredClip(match, accepts);
  render(match, index, name);
}

async function start() {
  const status = byId("status");
  try {
    const res = await fetch("/api/reports");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    matches = data.matches.slice().sort((a, b) => b.id.localeCompare(a.id, "en", {numeric: true}));
    if (!matches.length) {
      status.textContent = "当前服务尚未载入单场报告。";
      return;
    }
    const picker = byId("matches");
    for (const entry of matches) picker.add(new Option(entry.id + " · " + entry.heroes.join(" / "), entry.id));
    picker.addEventListener("change", () => {
      const match = matches.find((entry) => entry.id === picker.value);
      select(match, preferredClip(match, () => true), "全部");
    });
    byId("app").hidden = false;
    restore();
    status.hidden = true;
    window.addEventListener("hashchange", () => {
      if (location.hash !== "#review") restore();
    });
  } catch (error) {
    byId("app").hidden = true;
    status.hidden = false;
    status.textContent = "复盘数据载入失败，请刷新重试。" + (error.message ? "（" + error.message + "）" : "");
  }
}

start();
