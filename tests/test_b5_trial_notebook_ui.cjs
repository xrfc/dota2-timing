const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const template = readFileSync(path.join(__dirname, '../scripts/b5_trial_notebook_assets/notebook.html'), 'utf8');
const script = template.match(/<script>([\s\S]*?)<\/script>/)[1];
const hash = 'a'.repeat(64);
const clips = ['英雄甲', '英雄乙'].map((hero, index) => ({
  time: '15:01', seconds: 901, domain: '打野', hero,
  url: `http://127.0.0.1:8796/#match=123&t=901&i=${index}&scene=%E6%89%93%E9%87%8E`
}));
function catalog(reportHash = hash) {
  return {matches: [
    {id: '123', report_sha256: reportHash, clips},
    {id: '456', report_sha256: 'c'.repeat(64), clips: []}
  ]};
}

// Supply the DOM operations used by the standalone page; interaction goes through its listeners.
class Element extends EventTarget {
  children = [];
  selectedIndex = -1;
  textContent = '';
  value = '';
  get options() { return this.children; }
  add(option) {
    this.children.push(option);
    if (this.selectedIndex === -1) this.selectedIndex = 0;
  }
  replaceChildren() { this.children = []; this.selectedIndex = -1; }
  append(node) { this.children.push(node); }
  remove() {}
  click() { if (!this.disabled) this.dispatchEvent(new Event('click')); }
}

function page(data, storage = new Map()) {
  const el = Object.fromEntries(Array.from(template.matchAll(/\bid="([^"]+)"/g), m => [m[1], new Element()]));
  el.catalog.textContent = JSON.stringify(data);
  const window = new EventTarget();
  let download;
  vm.runInNewContext(script, {
    window, document: {getElementById: id => el[id], createElement: () => new Element(), body: new Element()},
    Option: class {}, Blob, URL: {createObjectURL(blob) { download = blob; return 'blob:test'; }, revokeObjectURL() {}},
    setTimeout() {}, localStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)}
  });
  return {
    el,
    select(id, index) { el[id].selectedIndex = index; el[id].dispatchEvent(new Event('change')); },
    write(text) { el.feedback.value = text; el.feedback.dispatchEvent(new Event('input')); },
    async export() { el.export.click(); return JSON.parse(await download.text()); }
  };
}

test('drafts follow the chosen hero even at the same second and never count as saved feedback', () => {
  const p = page(catalog());
  assert.equal(p.el.export.disabled, true);
  const original = '  我在这里看不清原因。\n  ';
  p.write(original);
  p.select('clip', 1);
  assert.equal(p.el.open.href, clips[1].url);
  assert.equal(p.el.feedback.value, '');
  p.select('match', 1);
  assert.equal(p.el.editor.hidden, true);
  assert.equal(p.el.clip.disabled, true);
  p.select('match', 0);
  assert.equal(p.el.feedback.value, original);
  assert.equal(p.el.export.disabled, true);
  p.el.save.click();
  assert.equal(p.el.export.disabled, false);
  assert.match(p.el.progress.children[0].textContent, /1 段有反馈/);
});

test('a refresh restores exact words and exports only explicitly saved entries for that report', async () => {
  const storage = new Map();
  const p = page(catalog(), storage);
  p.select('clip', 1);
  const words = '  看清了 <地图>\n但这里还有疑问。 ';
  p.write(words);
  p.el.save.click();
  p.select('clip', 0);
  p.write('一条尚未保存的草稿');
  const expected = {match: '123', report_sha256: hash, hero: '英雄乙', domain: '打野',
    time: '15:01', seconds: 901, feedback: words};
  assert.deepEqual(await p.export(), {schema: 'b5-trial-feedback/1', records: [expected]});
  const reopened = page(catalog(), storage);
  assert.equal(reopened.el.feedback.value, '');
  reopened.select('clip', 1);
  assert.equal(reopened.el.feedback.value, words);
  reopened.write('补充了原因');
  reopened.el.save.click();
  assert.deepEqual((await reopened.export()).records, [{...expected, feedback: '补充了原因'}]);
  assert.equal(page(catalog('b'.repeat(64)), storage).el.export.disabled, true);
});

test('storage failures leave feedback available for explicit export and show the recovery action', async () => {
  const denied = () => { throw new Error('storage unavailable'); };
  const p = page(catalog(), {get: denied, set: denied});
  assert.match(p.el.storage.textContent, /导出/);
  p.write('  \n');
  assert.equal(p.el.save.disabled, true);
  p.write('需要保存的意见');
  p.el.save.click();
  assert.match(p.el.storage.textContent, /导出/);
  assert.equal((await p.export()).records[0].feedback, '需要保存的意见');
});
