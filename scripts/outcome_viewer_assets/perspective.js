"use strict";

// Map coordinates are calibrated to the 7.41 terrain image used by the lane review.
function worldToMap([x, y]) {
  return [(261 + (x - 7487) * 8356 / 18322) / 8878, (26015 - y) / 18322];
}

const perspectiveColors = {self: "#fff1a4", ally: "#87f0cd", enemy: "#fd8f7d", ghost: "#ffb6aa"};
const mapDownloads = new Map();
let terrainImage;
let stopMap;

function loadTerrain() {
  if (!terrainImage) {
    terrainImage = new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("本机缺少 7.41 地图底图。"));
      image.src = "/map.jpg";
    }).catch((error) => { terrainImage = null; throw error; });
  }
  return terrainImage;
}

function loadMapMatch(id) {
  if (!mapDownloads.has(id)) {
    const request = fetch("/api/map/" + encodeURIComponent(id)).then(async (response) => {
      if (!response.ok) throw new Error(response.status === 404 ? "本场尚无地图数据。" : "地图信息载入失败。");
      const data = await response.json();
      if (data.schema !== "b5-perspective-map/1" || data.match !== id || !Array.isArray(data.clips)) {
        throw new Error("地图记录与本场比赛不匹配。");
      }
      return data;
    }).catch((error) => { mapDownloads.delete(id); throw error; });
    mapDownloads.set(id, request);
  }
  return mapDownloads.get(id);
}

function clockLabel(t) {
  return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0");
}

function enemyStatus(enemy, frame) {
  if (enemy.dead) return ["已阵亡", "dead"];
  if (frame.markers.some((m) => m.side === "enemy" && m.hero === enemy.hero)) return ["当前可见", "seen"];
  if (enemy.last_seen === frame.t) return ["可见 · 坐标缺失", "seen"];
  if (enemy.last_seen == null) return ["暂无露头记录", "unknown"];
  return [`${frame.t - enemy.last_seen} 秒前露头`, "last"];
}

function describeFrame(root, frame) {
  const list = root.querySelector(".map-enemies");
  list.replaceChildren();
  for (const enemy of frame?.enemies || []) {
    const [status, kind] = enemyStatus(enemy, frame);
    const li = element("li", kind);
    li.append(element("strong", "", enemy.hero), element("span", "", status));
    if (enemy.last_seen != null) li.title = "最近可见 " + clockLabel(enemy.last_seen);
    list.append(li);
  }
  if (!list.childElementCount) list.append(element("li", "unknown", "本秒没有敌方视野记录。"));
  const kit = root.querySelector(".map-kit");
  kit.hidden = !frame?.equipment?.length;
  const groups = kit.querySelector("div");
  groups.replaceChildren();
  if (kit.hidden) return;
  for (const ally of [true, false]) {
    const group = element("section");
    group.append(element("h4", "", ally ? "己方装备" : "敌方最近可见装备"));
    for (const row of frame.equipment.filter((item) => item.ally === ally)) {
      const observed = Number.isInteger(row.observed) ? clockLabel(row.observed) : "未观测";
      const inventory = row.items == null ? "装备未知" : Object.entries(row.items)
        .map(([slot, name]) => name + (Number(slot) >= 6 && Number(slot) <= 8 ? "（背包）" : "")).join("、") || "空栏";
      const line = element("p");
      line.append(element("strong", "", row.hero), element("span", "", observed), element("span", "", inventory));
      group.append(line);
    }
    groups.append(group);
  }
}

// Rasterize a frame's approximate sight cells once. Hero markers always follow replay visibility.
function sightLayer(vision) {
  const mask = atob(vision.bits);
  const layer = document.createElement("canvas");
  layer.width = layer.height = vision.width;
  const ctx = layer.getContext("2d");
  const pixels = ctx.createImageData(vision.width, vision.width);
  for (let y = 0; y < vision.width; y++) {
    for (let x = 0; x < vision.width; x++) {
      const index = y * vision.width + x;
      if (!(mask.charCodeAt(index >> 3) & (1 << (index & 7)))) continue;
      const offset = ((vision.width - 1 - y) * vision.width + x) * 4;
      pixels.data.set([87, 238, 211, 76], offset);
    }
  }
  ctx.putImageData(pixels, 0, 0);
  return layer;
}

function overlap(a, b) {
  return Math.max(0, Math.min(a.x+a.w, b.x+b.w) - Math.max(a.x,b.x)) *
    Math.max(0, Math.min(a.y+a.h, b.y+b.h) - Math.max(a.y,b.y));
}

function paintLabels(g, labels, obstacles, width, height) {
  g.font = "600 12px system-ui, 'Microsoft YaHei UI', sans-serif";
  const placed = [];
  // Prefer labels near the marker; use an outer ring and a leader for crowded groups.
  for (const label of labels) {
    const {x, y, text, color, ghost} = label;
    if (x < 0 || y < 0 || x > width || y > height) continue;
    const w = g.measureText(text).width + 9, h = 18;
    let best = null;
    for (const gap of [8, 24, 42, 64]) {
      for (const [dx,dy] of [[gap, -h], [gap, 1], [-gap-w, -h], [-gap-w, 1], [-w/2, gap], [-w/2,-gap-h]]) {
        const box = {x: x+dx, y: y+dy, w, h};
        let cost = gap / 2;
        if (box.x < 0 || box.y < 0 || box.x+w > width || box.y+h > height) cost += 100000;
        for (const other of placed) cost += 4 * overlap(box, other);
        for (const dot of obstacles) cost += overlap(box, dot);
        if (!best || cost < best.cost) best = {...box, cost};
      }
      if (best.cost === gap/2) break;
    }
    placed.push(best);
    const bx = best.x, by = best.y;
    g.strokeStyle = color;
    g.lineWidth = 1;
    g.beginPath(); g.moveTo(x,y);
    g.lineTo(Math.max(bx, Math.min(bx+w, x)), Math.max(by, Math.min(by+h, y))); g.stroke();
    g.beginPath(); g.roundRect(bx, by, w, h, 3);
    g.fillStyle = ghost ? "#372328e8" : "#091518e8"; g.fill();
    g.setLineDash(ghost ? [3,2] : []); g.stroke(); g.setLineDash([]);
    g.fillStyle = "#fff"; g.fillText(text, bx+4, by+13);
  }
}

function mapViewport(root) {
  const canvas = root.querySelector(".map-canvas");
  const output = root.querySelector(".map-zoom output");
  const toggle = root.querySelector(".map-vision-toggle");
  const zoomIn = root.querySelector('[data-zoom="in"]');
  const zoomOut = root.querySelector('[data-zoom="out"]');
  const g = canvas.getContext("2d");
  const view = {k: 1, x: 0, y: 0};
  let image, frame, layer, drag;
  function draw() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    const dpr = window.devicePixelRatio || 1;
    const bw = Math.round(w*dpr), bh = Math.round(h*dpr);
    if (canvas.width !== bw || canvas.height !== bh) { canvas.width = bw; canvas.height = bh; }
    g.setTransform(bw/w, 0, 0, bh/h, 0, 0);
    g.clearRect(0, 0, w, h);
    if (!image || !frame) return;
    const project = (pos) => {
      const [x,y] = worldToMap(pos);
      return [(x-view.x)*w*view.k, (y-view.y)*h*view.k];
    };
    g.drawImage(image, -view.x*w*view.k, -view.y*h*view.k, w*view.k, h*view.k);
    if (toggle.checked && layer) {
      const {origin, width, step} = frame.vision, end = origin + width*step;
      const [left, top] = project([origin, end]), [right, bottom] = project([end, origin]);
      g.imageSmoothingEnabled = false;
      g.drawImage(layer, left, top, right-left, bottom-top);
      g.imageSmoothingEnabled = true;
    }
    const labels = [], obstacles = [];
    for (const enemy of frame.enemies) {
      if (enemy.dead || enemy.last_seen == null || !enemy.trail?.length) continue;
      const path = enemy.trail.filter(([t]) => t <= enemy.last_seen && t <= frame.t)
        .map(([,x,y]) => project([x,y]));
      if (!path.length) continue;
      g.strokeStyle = perspectiveColors.ghost;
      g.lineWidth = 1.5; g.setLineDash([4,3]);
      g.beginPath(); path.forEach(([x,y],i) => i ? g.lineTo(x,y) : g.moveTo(x,y)); g.stroke(); g.setLineDash([]);
      if (enemy.last_seen < frame.t) {
        const [x,y] = path.at(-1);
        g.strokeRect(x-4,y-4,8,8);
        labels.push({x,y,text: enemy.hero + " · " + (frame.t-enemy.last_seen) + " 秒前", priority:3, ghost:true, color:perspectiveColors.ghost});
        obstacles.push({x:x-5,y:y-5,w:10,h:10});
      }
    }
    for (const ward of frame.wards) {
      const [x,y] = project(ward.pos);
      const observer = ward.type === "observer";
      g.fillStyle = observer ? "#f1d677" : "#9bc6ff"; g.fillRect(x-6,y-6,12,12);
      g.strokeStyle = "#142028"; g.strokeRect(x-6,y-6,12,12);
      g.font = "bold 10px sans-serif"; g.fillStyle = "#10202c"; g.fillText(observer ? "观" : "岗",x-5,y+4);
      obstacles.push({x:x-6,y:y-6,w:12,h:12});
    }
    for (const marker of frame.markers) {
      const [x,y] = project(marker.pos), r = marker.side === "self" ? 6 : 5;
      const color = perspectiveColors[marker.side];
      g.fillStyle = color; g.strokeStyle = "#0d1519"; g.lineWidth = 2;
      g.beginPath(); g.arc(x,y,r,0,Math.PI*2); g.fill(); g.stroke();
      if (marker.side === "self") {
        g.strokeStyle = color; g.lineWidth = 1.5; g.beginPath(); g.arc(x,y,r+3,0,Math.PI*2); g.stroke();
      }
      obstacles.push({x:x-r-1, y:y-r-1, w:2*r+2, h:2*r+2});
      labels.push({x,y,text:marker.hero,color,priority:{self:0,enemy:1,ally:2}[marker.side]});
    }
    paintLabels(g,labels.sort((a,b) => a.priority-b.priority),obstacles,w,h);
  }
  const clamp = (n) => Math.max(0, Math.min(1-1/view.k,n));
  function zoom(factor, x = .5, y = .5) {
    const target = Math.min(8, Math.max(1, view.k*factor));
    const delta = 1/view.k - 1/target;
    view.k = target;
    view.x = clamp(view.x + x*delta); view.y = clamp(view.y + y*delta);
    output.textContent = (Number.isInteger(view.k) ? view.k : view.k.toFixed(1)) + "×";
    zoomIn.disabled = view.k >= 8; zoomOut.disabled = view.k <= 1;
    canvas.classList.toggle("zoomed", view.k > 1);
    draw();
  }
  function point(event) {
    const rect = canvas.getBoundingClientRect();
    return [(event.clientX-rect.left)/rect.width,(event.clientY-rect.top)/rect.height];
  }
  zoomOut.onclick = () => zoom(1/1.5);
  zoomIn.onclick = () => zoom(1.5);
  root.querySelector('[data-zoom="reset"]').onclick = () => zoom(1/view.k);
  canvas.ondblclick = () => zoom(1/view.k);
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    zoom(Math.exp(-Math.max(-120, Math.min(120,e.deltaY))*.0022), ...point(e));
  }, {passive:false});
  canvas.onpointerdown = (e) => {
    if (view.k === 1 || e.button !== 0) return;
    drag = {p:point(e), x:view.x, y:view.y, id:e.pointerId};
    canvas.setPointerCapture(e.pointerId);
  };
  canvas.onpointermove = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    const [x,y] = point(e);
    view.x = clamp(drag.x + (drag.p[0]-x)/view.k);
    view.y = clamp(drag.y + (drag.p[1]-y)/view.k); draw();
  };
  canvas.onpointerup = canvas.onpointercancel = () => { drag = null; };
  toggle.addEventListener("change", draw);
  zoomOut.disabled = true;
  const resize = new ResizeObserver(draw);
  resize.observe(canvas);
  return {
    setImage(value) { image = value; draw(); },
    setFrame(value) { frame = value; layer = value?.vision ? sightLayer(value.vision) : null; draw(); },
    stop() { resize.disconnect(); },
  };
}

function clearPerspective() {
  if (stopMap) stopMap();
  stopMap = null;
}

async function mountPerspective(target, matchId, clip) {
  const root = document.querySelector("#map-panel").content.firstElementChild.cloneNode(true);
  target.append(root);
  Object.assign(root.dataset, {time:clip.time, hero:clip.hero, domain:clip.domain});
  const at = seconds(clip.time);
  const loading = root.querySelector(".map-loading");
  const imageStatus = root.querySelector(".map-image-status");
  const viewport = mapViewport(root);
  stopMap = viewport.stop;
  try {
    const data = await loadMapMatch(matchId);
    if (!root.isConnected) return;
    const map = data.clips.find((row) => row.time === clip.time && row.hero === clip.hero && row.domain === clip.domain);
    if (!map) throw new Error("本段缺少阵营视角记录。");
    root.dataset.team = map.team;
    const team = root.querySelector(".map-team");
    team.textContent = map.team + "视角";
    const buttons = root.querySelectorAll(".map-frames button");
    const toggle = root.querySelector(".map-vision-toggle");
    const warning = root.querySelector(".map-warning");
    function show(t) {
      const frame = map.frames.find((f) => f.t === t);
      root.dataset.frame = t;
      root.querySelector(".map-time").textContent = clockLabel(t);
      for (const button of buttons) button.setAttribute("aria-pressed", String(t === at+Number(button.dataset.offset)));
      const heroStatus = frame?.self_status ? clip.hero + " · " + frame.self_status : "";
      const message = frame ? [heroStatus, frame.unavailable].filter(Boolean).join("　") : "该秒缺少地图记录。可选择其他时刻。";
      warning.hidden = !message; warning.textContent = message;
      toggle.disabled = !frame?.vision;
      root.querySelector(".map-vision-note").textContent = frame?.vision ?
        "按地形和己方视野来源估算，敌人露头以录像记录为准。" : "该秒缺少普通视野估算。";
      describeFrame(root, frame);
      viewport.setFrame(frame);
    }
    for (const button of buttons) {
      const t = at + Number(button.dataset.offset);
      button.disabled = !map.frames.some((frame) => frame.t === t);
      button.title = button.disabled ? clockLabel(t) + " 缺少记录" : clockLabel(t);
      button.onclick = () => show(t);
    }
    loading.hidden = true;
    root.querySelector(".map-body").hidden = false;
    show(at);
    imageStatus.textContent = "正在载入地图底图…"; imageStatus.hidden = false;
    const image = await loadTerrain();
    if (!root.isConnected) return;
    imageStatus.hidden = true; viewport.setImage(image);
  } catch (error) {
    if (!root.isConnected) return;
    if (root.querySelector(".map-body").hidden) {
      loading.textContent = error.message || "本段地图不可用。";
    } else {
      imageStatus.hidden = false; imageStatus.textContent = error.message || "本段地图不可用。";
    }
  }
}
