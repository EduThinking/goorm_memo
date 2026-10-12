"""Small end-to-end write check against an isolated local data file."""

from pathlib import Path
import tkinter as tk
from tkinter import ttk

import app


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def test_create_and_reopen():
    test_path = Path(__file__).with_name(".write-check.json")
    original_store = app.Store
    original_hotkey = app.MemoApp.register_hotkey
    original_confirm = app.messagebox.askyesno
    app.Store = lambda: original_store(test_path)
    app.MemoApp.register_hotkey = lambda self: None
    first = None
    second = None
    try:
        first = app.MemoApp()
        first.edit_note()
        window = next(w for w in first.root.winfo_children() if isinstance(w, tk.Toplevel))
        title = next(w for w in descendants(window) if isinstance(w, ttk.Entry))
        body = next(w for w in descendants(window) if isinstance(w, tk.Text))
        save = next(w for w in descendants(window) if isinstance(w, ttk.Button) and w.cget("text").startswith("저장"))
        title.insert(0, "작성 확인")
        body.insert("1.0", "새 포스트잇 저장 테스트")
        save.invoke()
        first.root.update()
        assert len(first.store.data["notes"]) == 1
        assert first.store.data["notes"][0]["title"] == "작성 확인"
        assert first.store.data["notes"][0]["tab"] == "메모"
        first.edit_note()
        window = next(w for w in first.root.winfo_children() if isinstance(w, tk.Toplevel))
        title = next(w for w in descendants(window) if isinstance(w, ttk.Entry))
        body = next(w for w in descendants(window) if isinstance(w, tk.Text))
        category = next(w for w in descendants(window) if isinstance(w, ttk.Combobox))
        save = next(w for w in descendants(window) if isinstance(w, ttk.Button) and w.cget("text").startswith("저장"))
        title.insert(0, "할 일 확인")
        body.insert("1.0", "오늘 할 일")
        category.set("할 일")
        category.event_generate("<<ComboboxSelected>>")
        first.root.update()
        save.invoke()
        assert first.store.data["notes"][1]["tab"] == "할 일"
        assert first.store.data["notes"][1]["is_task"] is True
        assert first.store.data["notes"][1]["checklist"][0]["text"] == "오늘 할 일"
        task_check = next(w for w in descendants(first.cards_frame) if isinstance(w, tk.Checkbutton))
        task_check.invoke()
        task_note = first.store.data["notes"][1]
        assert task_note["checklist"][0]["done"] is True
        first.edit_note(task_note)
        window = next(w for w in first.root.winfo_children() if isinstance(w, tk.Toplevel))
        entries = [w for w in descendants(window) if isinstance(w, ttk.Entry)]
        task_entry = next(w for w in entries if w.get() == "오늘 할 일")
        task_entry.delete(0, "end")
        task_entry.insert(0, "수정한 할 일")
        save = next(w for w in descendants(window) if isinstance(w, ttk.Button) and w.cget("text").startswith("저장"))
        save.invoke()
        assert first.store.data["notes"][1]["checklist"][0]["text"] == "수정한 할 일"
        assert first.store.data["notes"][1]["checklist"][0]["done"] is True
        first.root.destroy()
        first = None
        second = app.MemoApp()
        assert len(second.store.data["notes"]) == 2
        assert second.store.data["notes"][0]["body"] == "새 포스트잇 저장 테스트"
        assert second.store.data["notes"][1]["checklist"][0]["done"] is True
        second.root.update()
        assert len(second.cards_frame.winfo_children()) == 2
        app.messagebox.askyesno = lambda *args, **kwargs: True
        delete_button = next(w for w in descendants(second.cards_frame) if isinstance(w, tk.Button) and w.cget("text") == "🗑")
        delete_button.invoke()
        assert len(second.store.data["notes"]) == 1
        assert len(original_store(test_path).data["notes"]) == 1
    finally:
        if first:
            first.root.destroy()
        if second:
            second.root.destroy()
        app.Store = original_store
        app.MemoApp.register_hotkey = original_hotkey
        app.messagebox.askyesno = original_confirm
        test_path.unlink(missing_ok=True)


if __name__ == "__main__":
    test_create_and_reopen()
    print("create, save, reopen, and card display: ok")
