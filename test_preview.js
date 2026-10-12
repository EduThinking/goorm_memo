// DOM-light check of preview note creation and local persistence.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() {
    this.value = '';
    this.textContent = '';
    this.children = [];
    this.listeners = {};
    this.style = {};
    this.dataset = {};
    this.classList = { add() {}, remove() {}, contains() { return false; }, toggle() {} };
  }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  dispatch(type) { for (const callback of this.listeners[type] || []) callback({ stopPropagation() {}, target: this }); }
  setAttribute() {}
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = [...children]; }
  focus() {}
}

const ids = ['grid', 'overlay', 'note-title', 'note-body', 'note-type', 'checklist-editor', 'checklist-rows', 'add-item', 'delete', 'modal-error', 'search', 'new', 'cancel', 'save', 'export', 'count-all', 'count-memo', 'count-task', 'count-code', 'count-link', 'count-other'];
const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
const stored = new Map();
const document = {
  getElementById: id => elements[id],
  querySelector: () => new Element(),
  querySelectorAll: () => [],
  createElement: () => new Element(),
  addEventListener() {},
};
let nextId = 0;
let confirmDelete = false;
const context = vm.createContext({ document, window: { confirm: () => confirmDelete }, alert: () => {}, localStorage: { getItem: key => stored.get(key) ?? null, setItem: (key, value) => stored.set(key, value) }, crypto: { randomUUID: () => `test-${++nextId}` }, Date, setTimeout, URL, Blob });
vm.runInContext(fs.readFileSync('preview.js', 'utf8'), context);
assert.equal(elements['count-all'].textContent, 0);
elements['note-title'].value = '작성 확인';
elements['note-body'].value = '포스트잇 내용';
elements['note-type'].value = '메모';
vm.runInContext('saveNote()', context);
const saved = JSON.parse(stored.get('goorm-postit-preview-v1'));
assert.equal(saved.length, 1);
assert.equal(saved[0].title, '작성 확인');
assert.equal(saved[0].body, '포스트잇 내용');
assert.equal(saved[0].category, '메모');
assert.equal(elements['count-all'].textContent, 1);
for (const category of ['할 일', '코드', '링크', '미분류']) {
  elements['note-title'].value = `${category} 작성 확인`;
  elements['note-body'].value = `${category} 내용`;
  elements['note-type'].value = category;
  if (category === '할 일') {
    vm.runInContext('addChecklistRow()', context);
    elements['checklist-rows'].children[0].children[1].value = '할 일 내용';
  }
  vm.runInContext('saveNote()', context);
}
const all = JSON.parse(stored.get('goorm-postit-preview-v1'));
assert.deepEqual(all.map(note => note.category), ['메모', '할 일', '코드', '링크', '미분류']);
assert.equal(all[1].isTask, true);
assert.equal(all[1].checklist[0].text, '할 일 내용');
const taskCard = elements.grid.children.find(card => card.children?.[0]?.textContent === '할 일');
const taskCheckbox = taskCard.children[3].children[0].children[0];
taskCheckbox.checked = true;
taskCheckbox.dispatch('change');
assert.equal(JSON.parse(stored.get('goorm-postit-preview-v1'))[1].checklist[0].done, true);
vm.runInContext('openEditor(notes[1])', context);
assert.equal(elements['checklist-rows'].children[0].children[1].value, '할 일 내용');
elements['checklist-rows'].children[0].children[1].value = '수정한 할 일';
vm.runInContext('saveNote()', context);
const edited = JSON.parse(stored.get('goorm-postit-preview-v1'))[1];
assert.equal(edited.checklist[0].text, '수정한 할 일');
assert.equal(edited.checklist[0].done, true);
assert.equal(elements['count-all'].textContent, 5);
const deleteCard = elements.grid.children.find(card => card.children?.[0]?.textContent === '할 일');
deleteCard.children[1].dispatch('click');
assert.equal(JSON.parse(stored.get('goorm-postit-preview-v1')).length, 5);
confirmDelete = true;
deleteCard.children[1].dispatch('click');
assert.equal(JSON.parse(stored.get('goorm-postit-preview-v1')).length, 4);
assert.equal(elements['count-all'].textContent, 4);
console.log('preview creation and persistence: ok');
