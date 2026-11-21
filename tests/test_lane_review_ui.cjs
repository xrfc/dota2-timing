const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '../scripts/lane_decision_assets/app.js'), 'utf8');

function queuePage(pathname = '/lane/') {
  const storage = new Map();
  const nodes = new Map();
  const context = vm.createContext({
    document: {getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, {});
      return nodes.get(id);
    }},
    location: {pathname}, Image: class {},
    localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
    fetch: () => new Promise(() => {})
  });
  vm.runInContext(script, context);
  return code => vm.runInContext(code, context);
}

test('a fixed five-group budget uses decision-time evidence and preserves rare evidence values', () => {
  const run = queuePage();
  run(`
    function example(id, distance, saves, support) {
      return {id, ready_names: saves, support_opportunity: support, history: [{
        t: 900, ally: [distance, 'ally'], enemies: [{dead:true, distance:500}, {last_seen:900, distance:2000}]
      }], get outcome() {throw Error('future accessed')}, get action() {throw Error('action accessed')}};
    }
    cases = [example('a',500,[],null), example('b',600,[],null)];
    for (const d of [500,1200,1800]) {
      cases.push(example('save'+d,d,['blink'],null), example('target'+d,d,[],{hero:'ally'}));
    }
    reviewGroups = selectReviewGroups(cases);
  `);
  assert.equal(run('reviewGroups.length'), 5);
  assert.equal(run('reviewGroups[0].ids.join()'), 'a,b');
  assert.equal(run('reviewGroups[0].factors[1]'), 'other');
  assert.equal(run("reviewGroups.some(group => group.factors[2] === 'signal')"), true);
  assert.equal(run("reviewGroups.some(group => group.factors[3] === 'detected')"), true);
  assert.equal(run("scenarioFactors({}).join()"), 'unknown,unknown,unknown,unknown');
});

test('only an independent response completes a group, with explicit portal submission', () => {
  const run = queuePage();
  run("reviewer='one'; reviewGroups=[{ids:['a','b']},{ids:['c']}]; cases=[{id:'a'},{id:'b'},{id:'c'}];");
  run("committed.set('a', {first:'farm',previewed:true}); refreshReviewQueue()");
  assert.equal(run('nextReviewId'), 'b');
  run("localStorage.setItem(firstKey('b'),'unknown'); refreshReviewQueue()");
  assert.equal(run("el('next-review').textContent"), '打开待提交判断');
  run("committed.set('b',{first:'unknown',previewed:false}); refreshReviewQueue()");
  assert.equal(run('nextReviewId'), 'c');
  run("localStorage.setItem(exposureKey('c'),'1'); refreshReviewQueue()");
  assert.equal(run("el('next-review').disabled"), true);
  assert.match(run("el('review-progress').textContent"), /独立完成 1 组.*无可盲评片段 1 组/);
  run("reviewer='two'; committed.clear(); refreshReviewQueue()");
  assert.equal(run('nextReviewId'), 'a');
});

test('standalone review accepts a locally saved first opinion and can use an unseen alternate', () => {
  const run = queuePage('/local-report/');
  run("reviewGroups=[{ids:['a','b']}]; cases=[{id:'a'},{id:'b'}];");
  run("localStorage.setItem(storageKey('a'), JSON.stringify({previewed:true})); refreshReviewQueue()");
  assert.equal(run('nextReviewId'), 'b');
  run("localStorage.setItem(storageKey('b'), JSON.stringify({first:'unknown'})); refreshReviewQueue()");
  assert.equal(run("el('next-review').disabled"), true);
  assert.match(run("el('review-progress').textContent"), /独立完成 1 组/);
});

test('first independent choice survives viewing analysis and reloading before submission', async () => {
  const storage = new Map();
  const posts = [];
  function page() {
    const nodes = new Map();
    const context = vm.createContext({
      document: {getElementById(id) {
        if (!nodes.has(id)) nodes.set(id, {querySelectorAll: () => []});
        return nodes.get(id);
      }},
      location: {pathname:'/lane/'}, Image:class {},
      localStorage: {getItem:k => storage.get(k), setItem:(k,v) => storage.set(k,v)},
      fetch:async (url, options) => {
        if (url === '/reviews' && !options) return new Promise(() => {});
        if (options?.method === 'POST') posts.push(JSON.parse(options.body));
        return {ok:true, json:async () => ({ok:true})};
      }
    });
    vm.runInContext(script, context);
    vm.runInContext("current={id:'case'};reviewer='a';caseVersions.case='sha';", context);
    return context;
  }
  await vm.runInContext("judge('farm')", page());
  assert.equal(posts.length, 0);
  const reopened = page();
  await vm.runInContext("judge('retreat');", reopened);
  await vm.runInContext("submitReview()", reopened);
  assert.deepEqual([posts[0].choice, posts[0].first, posts[0].previewed], ['retreat','farm',false]);
});

test('support window is revealed with the outcome and older reports still open', async () => {
  const nodes = new Map();
  const urls = [];
  let outcome = {death_seconds: [], complete: true, lane_last_hits: 1};
  const element = id => {
    if (!nodes.has(id)) nodes.set(id, {});
    return nodes.get(id);
  };
  const context = vm.createContext({
    document: {getElementById: element}, location: {pathname: '/lane/'}, Image: class {},
    localStorage: {getItem: () => null, setItem: () => {}},
    fetch: async url => {
      if (url === '/reviews') return new Promise(() => {});
      urls.push(url);
      return {ok: true, json: async () => url.startsWith('actions/') ? {lean: 'unknown'} : outcome};
    }
  });
  vm.runInContext(script, context);
  vm.runInContext("current = {id:'case'}", context);
  await vm.runInContext('showAnalysis()', context);
  assert.deepEqual(urls, ['actions/case.json']);
  await vm.runInContext('reveal()', context);
  assert.doesNotMatch(element('outcome').textContent, /再刷六秒/);
  outcome = {...outcome, walk_hit_window: {now:'both_before_hit', after_six:'after_observed_hits'}};
  await vm.runInContext('reveal()', context);
  assert.match(element('outcome').textContent, /立即出发，.*同秒到达.*再刷六秒，.*晚于/);
});

test('changing case evidence cannot restore a previous version as a fresh blind choice', () => {
  const run = queuePage();
  run("reviewer='a'; current={id:'k'}; caseVersions.k='old'; save({choice:'farm',first:'farm'});");
  run("localStorage.setItem(lastAnalysisKey('k'), 'old'); drafts.clear(); caseVersions.k='new';");
  assert.equal(run("saved('k').first"), undefined);
  assert.equal(run("saved('k').previewed"), true);
  run("localStorage.setItem('review-first:a:legacy','farm'); caseVersions.legacy='new';");
  assert.equal(run("saved('legacy').first"), undefined);
  assert.equal(run("saved('legacy').previewed"), true);
});
