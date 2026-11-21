const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname, '../scripts/lane_decision_assets/app.js'), 'utf8');

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
        if (options) posts.push(JSON.parse(options.body));
        return {ok:true, json:async () => ({ok:true})};
      }
    });
    vm.runInContext(script, context);
    vm.runInContext("current={id:'case'};reviewer='a';", context);
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
