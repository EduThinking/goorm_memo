/* Standalone browser preview. Its notes stay in this browser only. */
const storageKey = "goorm-postit-preview-v1";
const grid = document.getElementById("grid");
const overlay = document.getElementById("overlay");
const titleInput = document.getElementById("note-title");
const bodyInput = document.getElementById("note-body");
const checklistEditor = document.getElementById("checklist-editor");
const checklistRows = document.getElementById("checklist-rows");
const categoryInput = document.getElementById("note-type");
const errorLabel = document.getElementById("modal-error");
const searchInput = document.getElementById("search");
let notes = [];
let activeFilter = "전체";
let editingId = null;

function newId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function checklistFromNote(note) {
  if (Array.isArray(note?.checklist)) return note.checklist.map(item => ({ ...item }));
  return (note?.body || "").split("\n").map((line, index) => {
    const match = line.match(/^\s*-\s*\[([ xX])\]\s*(.*)$/);
    return { id: `${note?.id || "draft"}-legacy-${index}`, text: match ? match[2] : line.trim(), done: match ? match[1].toLowerCase() === "x" : false };
  }).filter(item => item.text);
}

function addChecklistRow(item = { id: newId(), text: "", done: false }) {
  const row = document.createElement("div");
  row.className = "check-row";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = !!item.done;
  const text = document.createElement("input");
  text.type = "text";
  text.placeholder = "할 일을 입력하세요";
  text.value = item.text;
  text.dataset.id = item.id;
  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "×";
  remove.addEventListener("click", () => row.remove());
  row.append(checkbox, text, remove);
  checklistRows.append(row);
  return text;
}

function editorItems() {
  return [...checklistRows.children].map(row => ({ id: row.children[1].dataset.id || newId(), text: row.children[1].value.trim(), done: row.children[0].checked })).filter(item => item.text);
}

function syncCategoryEditor() {
  const isTask = categoryInput.value === "할 일";
  if (!isTask && !checklistEditor.hidden) {
    const lines = editorItems().map(item => item.text);
    if (lines.length) bodyInput.value = lines.join("\n");
  }
  bodyInput.hidden = isTask;
  checklistEditor.hidden = !isTask;
  if (isTask && !checklistRows.children.length) {
    const lines = bodyInput.value.trim().split("\n").filter(Boolean);
    for (const line of lines) addChecklistRow({ id: newId(), text: line.replace(/^\s*-\s*\[[ xX]\]\s*/, ""), done: /^\s*-\s*\[[xX]\]/.test(line) });
    if (!lines.length) addChecklistRow();
  }
}

try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || "[]");
  if (Array.isArray(saved)) notes = saved;
} catch (error) {
  errorLabel.textContent = "저장된 미리보기 데이터를 읽을 수 없습니다.";
}

function openEditor(note = null) {
  editingId = note?.id || null;
  titleInput.value = note?.title || "";
  bodyInput.value = note?.body || "";
  categoryInput.value = note?.category || "메모";
  checklistRows.replaceChildren();
  if (categoryInput.value === "할 일") {
    const items = checklistFromNote(note);
    for (const item of items.length ? items : [{ id: newId(), text: "", done: false }]) addChecklistRow(item);
  }
  syncCategoryEditor();
  errorLabel.textContent = "";
  document.getElementById("delete").hidden = !note;
  overlay.classList.add("show");
  titleInput.focus();
}

function closeEditor() {
  overlay.classList.remove("show");
  editingId = null;
}

function deleteNote(note) {
  if (!window.confirm("이 포스트잇을 삭제할까요?")) return false;
  const updated = notes.filter(item => item.id !== note.id);
  try {
    localStorage.setItem(storageKey, JSON.stringify(updated));
  } catch (error) {
    alert("삭제 내용을 저장하지 못했습니다.");
    return false;
  }
  notes = updated;
  closeEditor();
  render();
  return true;
}

function render() {
  const counts = { "전체": notes.length, "메모": 0, "할 일": 0, "코드": 0, "링크": 0, "미분류": 0 };
  for (const note of notes) counts[note.category] = (counts[note.category] || 0) + 1;
  for (const [id, category] of [["count-all", "전체"], ["count-memo", "메모"], ["count-task", "할 일"], ["count-code", "코드"], ["count-link", "링크"], ["count-other", "미분류"]]) {
    document.getElementById(id).textContent = counts[category] || 0;
  }
  document.querySelector(".board h1").textContent = `${activeFilter} 포스트잇 ✿`;
  grid.replaceChildren();
  const query = searchInput.value.trim().toLocaleLowerCase();
  const visible = notes.filter(note => (activeFilter === "전체" || note.category === activeFilter) && `${note.title} ${note.body}`.toLocaleLowerCase().includes(query)).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  if (!visible.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = query ? "검색 결과가 없어요 ✿" : "아직 포스트잇이 없어요 ✿ 새 포스트잇을 작성해 보세요.";
    grid.append(empty);
  }
  for (const note of visible) {
    const card = document.createElement("article");
    card.className = "card";
    card.tabIndex = 0;
    const kind = document.createElement("span");
    kind.className = "kind";
    kind.textContent = note.category;
    const deleteButton = document.createElement("button");
    deleteButton.className = "card-delete";
    deleteButton.type = "button";
    deleteButton.title = "포스트잇 삭제";
    deleteButton.setAttribute("aria-label", "포스트잇 삭제");
    deleteButton.textContent = "🗑";
    deleteButton.addEventListener("click", event => {
      event.stopPropagation();
      deleteNote(note);
    });
    const title = document.createElement("h3");
    title.textContent = note.title || note.body.split("\n")[0].slice(0, 35) || "제목 없는 메모";
    const body = document.createElement("div");
    if (note.category === "할 일") {
      for (const item of checklistFromNote(note).slice(0, 5)) {
        const line = document.createElement("label");
        line.className = `check-preview${item.done ? " done" : ""}`;
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = !!item.done;
        checkbox.addEventListener("click", event => event.stopPropagation());
        checkbox.addEventListener("change", event => {
          event.stopPropagation();
          const checklist = checklistFromNote(note).map(entry => entry.id === item.id ? { ...entry, done: checkbox.checked } : entry);
          const updatedNote = { ...note, checklist, body: checklist.map(entry => `- [${entry.done ? "x" : " "}] ${entry.text}`).join("\n"), done: checklist.length > 0 && checklist.every(entry => entry.done), updatedAt: new Date().toISOString() };
          const updated = notes.map(entry => entry.id === note.id ? updatedNote : entry);
          try {
            localStorage.setItem(storageKey, JSON.stringify(updated));
            notes = updated;
            render();
          } catch (error) {
            checkbox.checked = !checkbox.checked;
            alert("체크 상태를 저장하지 못했습니다.");
          }
        });
        const label = document.createElement("span");
        label.textContent = item.text;
        line.append(checkbox, label);
        body.append(line);
      }
    } else {
      body.className = "card-body";
      body.textContent = note.body.slice(0, 140);
      body.style.whiteSpace = "pre-line";
    }
    const deco = document.createElement("span");
    deco.className = "deco";
    deco.textContent = "♡";
    const date = document.createElement("span");
    date.className = "date";
    date.textContent = new Date(note.updatedAt).toLocaleDateString("ko-KR");
    card.append(kind, deleteButton, title, body, deco, date);
    card.addEventListener("click", event => { if (event.target.type !== "checkbox" && event.target !== deleteButton) openEditor(note); });
    card.addEventListener("keydown", event => { if (event.key === "Enter") openEditor(note); });
    grid.append(card);
  }
  const add = document.createElement("button");
  add.className = "card add";
  add.textContent = "＋ 새 포스트잇";
  add.addEventListener("click", () => openEditor());
  grid.append(add);
}

function saveNote() {
  const title = titleInput.value.trim();
  const category = categoryInput.value;
  const isTask = category === "할 일";
  const checklist = isTask ? editorItems() : [];
  const body = isTask ? checklist.map(item => `- [${item.done ? "x" : " "}] ${item.text}`).join("\n") : bodyInput.value.trim();
  if (isTask && !checklist.length) {
    errorLabel.textContent = "할 일을 하나 이상 입력해 주세요.";
    return;
  }
  if (!title && !body) {
    errorLabel.textContent = "제목이나 내용을 입력해 주세요.";
    return;
  }
  const existing = notes.find(note => note.id === editingId);
  const id = existing?.id || newId();
  const note = { id, title, body, checklist, isTask, done: isTask && checklist.every(item => item.done), category, createdAt: existing?.createdAt || new Date().toISOString(), updatedAt: new Date().toISOString() };
  const updated = existing ? notes.map(item => item.id === note.id ? note : item) : [...notes, note];
  try {
    localStorage.setItem(storageKey, JSON.stringify(updated));
  } catch (error) {
    errorLabel.textContent = "저장하지 못했습니다. 브라우저 저장 공간을 확인해 주세요.";
    return;
  }
  notes = updated;
  closeEditor();
  render();
}

document.getElementById("new").addEventListener("click", () => openEditor());
document.getElementById("home").addEventListener("click", () => {
  closeEditor();
  activeFilter = "전체";
  searchInput.value = "";
  document.querySelectorAll("[data-filter]").forEach(button => button.classList.toggle("active", button.dataset.filter === "전체"));
  document.querySelector(".board").scrollTop = 0;
  render();
});
document.getElementById("cancel").addEventListener("click", closeEditor);
document.getElementById("save").addEventListener("click", saveNote);
document.getElementById("delete").addEventListener("click", () => {
  const note = notes.find(item => item.id === editingId);
  if (note) deleteNote(note);
});
document.getElementById("add-item").addEventListener("click", () => addChecklistRow().focus());
categoryInput.addEventListener("change", syncCategoryEditor);
searchInput.addEventListener("input", render);
for (const button of document.querySelectorAll("[data-filter]")) {
  button.addEventListener("click", () => {
    activeFilter = button.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach(item => item.classList.toggle("active", item === button));
    render();
  });
}
document.getElementById("export").addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(notes, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "goorm-preview-notes.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && overlay.classList.contains("show")) closeEditor();
  if (event.ctrlKey && event.key === "Enter" && overlay.classList.contains("show")) saveNote();
});
render();
