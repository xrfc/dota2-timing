// Real-browser acceptance for the coach app (M2-T5). Drives an isolated headless
// Chrome over CDP on 127.0.0.1:9229 against the app on 127.0.0.1:8780.
// Usage: node scripts/acceptance/coach_app_browser.cjs OUTPUT_DIR
const fs = require('node:fs');
const path = require('node:path');
const out = process.argv[2];
const APP = 'http://127.0.0.1:8780/';
const CDP = 'http://127.0.0.1:9229';

(async () => {
  const target = await (await fetch(`${CDP}/json/new?about:blank`, {method: 'PUT'})).json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0; const pending = new Map(), requests = [], errors = [];
  ws.onmessage = e => {
    const m = JSON.parse(e.data);
    if (m.id) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.reject(Error(JSON.stringify(m.error))) : p.resolve(m.result); return; }
    if (m.method === 'Network.requestWillBeSent') requests.push(new URL(m.params.request.url).pathname + new URL(m.params.request.url).search);
    if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.text);
    if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') errors.push(`${m.params.entry.text} ${m.params.entry.url || ''}`);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => { const i = ++id; pending.set(i, {resolve, reject}); ws.send(JSON.stringify({id: i, method, params})); });
  const ev = async expression => { const r = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true}); if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails)); return r.result.value; };
  const wait = ms => new Promise(r => setTimeout(r, ms));
  const shot = async name => { const r = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true}); fs.writeFileSync(path.join(out, name), Buffer.from(r.data, 'base64')); };
  const viewport = (width, height, dark = false) => Promise.all([
    send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: width < 600}),
    send('Emulation.setEmulatedMedia', {features: [{name: 'prefers-color-scheme', value: dark ? 'dark' : 'light'}]}),
  ]);
  const checks = {}; const record = (k, ok, detail) => { checks[k] = {ok: Boolean(ok), detail}; };
  const status = () => ev(`document.getElementById('result-status').textContent`);
  const rowText = item => ev(`[...document.querySelectorAll('#timing-body tr')].map(r=>r.innerText).find(t=>t.startsWith('${item}'))||''`);

  await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable'); await send('Log.enable');
  await viewport(1440, 1000);
  await send('Page.navigate', {url: APP});
  await ev(`new Promise(r=>{let n=0;const t=setInterval(()=>{if(document.querySelectorAll('#timing-body tr').length||++n>100){clearInterval(t);r(true)}},100)})`);
  await ev(`localStorage.clear()`);
  await send('Page.reload'); await wait(1500);

  record('initial_render', (await ev(`document.querySelectorAll('#timing-body tr').length`)) === 8, await ev(`document.getElementById('result-title').textContent`));
  record('baseline_reference_title', /高分段出装节奏/.test(await ev(`document.getElementById('result-title').textContent`)));
  record('bfury_baseline_row', /狂战斧[\s\S]*64%[\s\S]*91%/.test(await rowText('狂战斧')), await rowText('狂战斧'));
  record('no_lineup_inputs_or_badges', (await ev(`document.querySelectorAll('#enemies input, [data-radiant], .badge.model, td.cell.model').length`)) === 0);
  record('explains_timing_vs_lineup', /线上经济/.test(await ev(`document.querySelector('.side-note').textContent`)));
  await shot('items-baseline.png');

  await ev(`[...document.querySelectorAll('#my-heroes button')].find(b=>b.textContent.startsWith('神谕者')).click()`); await wait(700);
  const oracle = await ev(`document.getElementById('timing-body').innerText`);
  record('oracle_items', /以太透镜/.test(oracle) && /Eul/.test(oracle) && /偏少/.test(oracle), oracle.slice(0, 300));
  await shot('items-oracle.png');

  await send('Page.reload'); await wait(1500);
  record('selection_persisted', /神谕者/.test(await ev(`document.getElementById('result-title').textContent`)), await ev(`document.getElementById('result-title').textContent`));

  await viewport(390, 844, true); await wait(500);
  record('mobile_no_horizontal_scroll', await ev(`document.documentElement.scrollWidth<=window.innerWidth+1`), await ev(`[document.documentElement.scrollWidth,window.innerWidth]`));
  record('dark_mode_background', (await ev(`getComputedStyle(document.body).backgroundColor`)) === 'rgb(18, 21, 26)', await ev(`getComputedStyle(document.body).backgroundColor`));
  await shot('items-mobile-dark.png');

  record('only_whitelisted_requests', requests.every(r => ['/', '/style.css', '/app.js', '/api/meta', '/favicon.ico'].includes(r) || r.startsWith('/api/item-timing?')), [...new Set(requests)]);
  record('no_console_errors', errors.length === 0, errors);
  const result = {schema: 'coach-app-browser-acceptance/1', browser: (await (await fetch(`${CDP}/json/version`)).json()).Browser, url: APP, checks, passed: Object.values(checks).every(c => c.ok)};
  fs.writeFileSync(path.join(out, 'browser-checks.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify({passed: result.passed, failed: Object.entries(checks).filter(([, c]) => !c.ok).map(([k, c]) => [k, c.detail])}, null, 1));
  await fetch(`${CDP}/json/close/${target.id}`); ws.close();
})().catch(e => { console.error(e); process.exitCode = 1; });
