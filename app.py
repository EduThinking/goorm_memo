"""Offline Windows memo app. Run with: python app.py"""

import ctypes
import ctypes.wintypes
import json
import os
import re
import sys
import tempfile
import tkinter as tk
import uuid
from datetime import datetime, date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk


DATA_FILE = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "GoormMemo" / "data.json"
DEFAULT_TABS = ["메모", "할 일", "코드", "링크"]


def now():
    return datetime.now().isoformat(timespec="seconds")


def classify(body, is_task, examples):
    if is_task:
        return "할 일"
    tokens = set(re.findall(r"[\w가-힣]{3,}", body.lower()))
    best = (0, "미분류")
    for item in examples:
        old = set(item.get("tokens", []))
        score = len(tokens & old) / max(1, len(tokens | old))
        if score > best[0]:
            best = (score, item["tab"])
    if best[0] >= 0.35:
        return best[1]
    has_code = bool(re.search(r"```|^\s*(def |class |function |import |const |let )", body, re.M))
    has_url = bool(re.search(r"https?://\S+", body))
    if has_code and has_url:
        return "미분류"
    return "코드" if has_code else "링크" if has_url else "미분류"


def checklist_items(note):
    if isinstance(note.get("checklist"), list):
        return [dict(item) for item in note["checklist"]]
    items = []
    for index, line in enumerate(note.get("body", "").splitlines()):
        match = re.match(r"^\s*-\s*\[([ xX])\]\s*(.*)$", line)
        content = (match.group(2) if match else line).strip()
        if content:
            items.append({"id": f"{note.get('id', 'draft')}-legacy-{index}", "text": content, "done": bool(match and match.group(1).lower() == "x")})
    return items


def checklist_body(items):
    return "\n".join(f"- [{'x' if item['done'] else ' '}] {item['text']}" for item in items)


class Store:
    def __init__(self, path=DATA_FILE):
        self.path = Path(path)
        self.data = {"notes": [], "tabs": [], "examples": [], "settings": {"shortcut": "Ctrl+Alt+N", "pinned": {"visible": False, "topmost": True, "collapsed": False, "geometry": "300x350+100+100"}}}
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            self.data.update(loaded)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".memo-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


class MemoApp:
    def __init__(self):
        self.store = Store()
        self.root = tk.Tk()
        self.root.title("Goorm 메모")
        self.root.geometry("960x620")
        self.active_tab = "전체"
        self.selected_id = None
        self.pinned = None
        self.hotkey_registered = False
        self.hotkey_generation = 0
        self.build_ui()
        self.refresh()
        self.register_hotkey()
        self.root.after(15000, self.check_reminders)
        if self.store.data["settings"].get("pinned", {}).get("visible"):
            self.toggle_pinned()

    def persist(self):
        try:
            self.store.save()
            return True
        except OSError as exc:
            messagebox.showerror("저장 실패", f"저장하지 못했습니다. 다시 시도하세요.\n{exc}")
            return False

    def build_ui(self):
        self.colors = {"base": "#f6a18f", "canvas": "#fff8f5", "panel": "#fff0e9", "card": "#ffffff", "line": "#edc9bf", "text": "#654754", "muted": "#987982", "blue": "#87bfce"}
        c = self.colors
        self.root.configure(bg=c["base"])
        self.root.geometry("1120x760")
        self.root.minsize(760, 500)
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=c["panel"])
        style.configure("TLabel", background=c["panel"], foreground=c["text"], font=("Segoe UI", 10))
        style.configure("TButton", background="#ffe0d9", foreground=c["text"], borderwidth=0, padding=(10, 7), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#ffd0c6")])
        style.configure("Accent.TButton", background="#ee7899", foreground="white", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#e95f87")])
        style.configure("TEntry", fieldbackground="#fffaf8", foreground=c["text"], insertcolor=c["text"], bordercolor=c["line"], padding=7)
        style.configure("TCombobox", fieldbackground="#fffaf8", foreground=c["text"], background=c["card"])
        style.configure("TCheckbutton", background=c["panel"], foreground=c["text"])
        bar = tk.Frame(self.root, bg=c["panel"], height=66, highlightbackground=c["line"], highlightthickness=1)
        bar.pack(fill="x")
        tk.Button(bar, text="✿  Goorm 메모", command=self.go_home, bg=c["panel"], fg="#d76589", activebackground=c["panel"], activeforeground="#b94e76", borderwidth=0, relief="flat", cursor="hand2", font=("Segoe UI", 17, "bold")).pack(side="left", padx=(22, 10))
        tk.Label(bar, text="나만의 작은 기록장", bg=c["panel"], fg=c["muted"], font=("Segoe UI", 9)).pack(side="left")
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *_: self.refresh_list())
        ttk.Button(bar, text="＋ 새 포스트잇", style="Accent.TButton", command=self.quick_entry).pack(side="right", padx=16, pady=13)
        ttk.Entry(bar, textvariable=self.query, width=34).pack(side="right", padx=8, pady=9)
        body = tk.Frame(self.root, bg=c["base"])
        body.pack(fill="both", expand=True)
        side = tk.Frame(body, bg=c["panel"], width=205, padx=14, pady=22)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="MY NOTEBOOK  ♡", bg=c["panel"], fg="#d76589", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", pady=(0, 18))
        tk.Label(side, text="내 포스트잇", bg=c["panel"], fg=c["muted"], font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(0, 8))
        self.tabs_frame = tk.Frame(side, bg=c["panel"])
        self.tabs_frame.pack(fill="x")
        ttk.Button(side, text="+ 새 탭", command=self.add_tab).pack(fill="x", pady=(15, 4))
        ttk.Button(side, text="탭 이름 변경", command=self.rename_tab).pack(fill="x", pady=4)
        ttk.Button(side, text="탭 삭제", command=self.delete_tab).pack(fill="x", pady=4)
        ttk.Button(side, text="오늘 할 일 보기", command=self.toggle_pinned).pack(side="bottom", fill="x", pady=4)
        ttk.Button(side, text="JSON 내보내기", command=self.export).pack(side="bottom", fill="x", pady=4)
        ttk.Button(side, text="설정", command=self.settings).pack(side="bottom", fill="x", pady=4)
        main = tk.Frame(body, bg=c["base"], padx=28, pady=24)
        main.pack(side="left", fill="both", expand=True)
        self.stream_title = tk.Label(main, text="전체 포스트잇", bg=c["base"], fg="white", font=("Segoe UI", 21, "bold"), anchor="w")
        self.stream_title.pack(fill="x")
        tk.Label(main, text="작은 생각들을 모아 두는 곳  ✿", bg=c["base"], fg="#fff4ef", font=("Segoe UI", 10), anchor="w").pack(fill="x", pady=(4, 18))
        card_area = tk.Frame(main, bg=c["base"])
        card_area.pack(fill="both", expand=True)
        self.cards_canvas = tk.Canvas(card_area, bg=c["base"], highlightthickness=0)
        scroll = ttk.Scrollbar(card_area, orient="vertical", command=self.cards_canvas.yview)
        self.cards_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.cards_canvas.pack(side="left", fill="both", expand=True)
        self.cards_frame = tk.Frame(self.cards_canvas, bg=c["base"])
        self.cards_window = self.cards_canvas.create_window((0, 0), window=self.cards_frame, anchor="nw")
        self.cards_frame.bind("<Configure>", lambda _: self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox("all")))
        self.cards_canvas.bind("<Configure>", lambda e: self._resize_cards(e.width))

    def _resize_cards(self, width):
        self.cards_canvas.itemconfigure(self.cards_window, width=width)
        columns = max(1, width // 270)
        if getattr(self, "card_columns", None) != columns:
            self.card_columns = columns
            self.refresh_list()

    def tabs(self):
        return DEFAULT_TABS + [t["name"] for t in self.store.data["tabs"]]

    def refresh(self):
        for child in self.tabs_frame.winfo_children():
            child.destroy()
        for tab in ["전체"] + self.tabs() + ["미분류"]:
            counts = sum(1 for n in self.store.data["notes"] if tab == "전체" or n["tab"] == tab)
            selected = tab == self.active_tab
            tk.Button(self.tabs_frame, text=f"{tab}     {counts}", command=lambda t=tab: self.select_tab(t), anchor="w", bg="#ffd7df" if selected else self.colors["panel"], fg="#b94e76" if selected else self.colors["muted"], activebackground="#ffd7df", activeforeground="#b94e76", borderwidth=0, relief="flat", padx=12, pady=8, font=("Segoe UI", 10, "bold" if selected else "normal")).pack(fill="x", pady=2)
        self.refresh_list()
        self.refresh_pinned()

    def select_tab(self, tab):
        self.active_tab = tab
        self.refresh()

    def go_home(self):
        self.query.set("")
        self.active_tab = "전체"
        self.cards_canvas.yview_moveto(0)
        self.refresh()

    def refresh_list(self):
        for child in self.cards_frame.winfo_children():
            child.destroy()
        self.stream_title.config(text=f"{self.active_tab} 포스트잇")
        q = self.query.get().casefold()
        notes = sorted(self.store.data["notes"], key=lambda n: n["updated_at"], reverse=True)
        self.visible_notes = [n for n in notes if (self.active_tab == "전체" or n["tab"] == self.active_tab) and q in (n["title"] + " " + n["body"]).casefold()]
        palette = [("#fffdfb", "#82c3d2", "✿"), ("#ffe5de", "#ee88a8", "♡"), ("#e3f1f0", "#7ebfc4", "✦"), ("#fff0e7", "#f4a88e", "❀"), ("#fce9f0", "#d87b9e", "♡"), ("#fffdf8", "#86bfd0", "✿")]
        columns = getattr(self, "card_columns", 3)
        for index, n in enumerate(self.visible_notes):
            paper, accent, deco = palette[index % len(palette)]
            card = tk.Frame(self.cards_frame, bg=paper, width=235, height=230, highlightbackground="#e6b7ae", highlightthickness=1, cursor="hand2")
            card.grid(row=index // columns, column=index % columns, padx=10, pady=10, sticky="nsew")
            card.grid_propagate(False)
            card_header = tk.Frame(card, bg=paper)
            card_header.pack(fill="x", padx=12, pady=(12, 6))
            tk.Label(card_header, text=f"{deco}  {n['tab']}", bg=paper, fg=accent, font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left", fill="x", expand=True)
            tk.Button(card_header, text="🗑", command=lambda note=n: self.delete_note(note), bg=paper, fg="#bd6b83", activebackground="#ffe1e8", activeforeground="#a94d6a", borderwidth=0, relief="flat", font=("Segoe UI Emoji", 11), cursor="hand2").pack(side="right")
            title = n["title"] or (n["body"].splitlines()[0] if n["body"] else "제목 없는 메모")
            tk.Label(card, text=title[:35], bg=paper, fg="#795660", font=("Segoe UI", 13, "bold"), anchor="nw", justify="left", wraplength=200).pack(fill="x", padx=16)
            if n["is_task"]:
                list_frame = tk.Frame(card, bg=paper)
                list_frame.pack(fill="both", expand=True, padx=12, pady=8)
                for item in checklist_items(n)[:4]:
                    checked = tk.BooleanVar(value=item["done"])
                    check = tk.Checkbutton(list_frame, text=item["text"][:28], variable=checked, command=lambda note=n, item_id=item["id"]: self.toggle_checklist_item(note, item_id), bg=paper, fg="#8d7076", activebackground=paper, selectcolor=paper, anchor="w", wraplength=175, justify="left", font=("Segoe UI", 10), cursor="hand2")
                    check._value = checked
                    check.pack(fill="x", anchor="w")
            else:
                snippet = n["body"][:145] or "여기에 작은 생각을 적어 보세요."
                tk.Label(card, text=snippet, bg=paper, fg="#8d7076", font=("Segoe UI", 10), anchor="nw", justify="left", wraplength=200).pack(fill="both", expand=True, padx=16, pady=10)
            foot = "완료 ♡" if n["is_task"] and n["done"] else n["updated_at"][:10]
            tk.Label(card, text=foot, bg=paper, fg=accent, font=("Segoe UI", 9), anchor="e").pack(fill="x", padx=16, pady=(0, 12))
            def bind_open(widget, note=n):
                if isinstance(widget, (tk.Checkbutton, tk.Button)):
                    return
                widget.bind("<Button-1>", lambda _e: self.edit_note(note))
                for child in widget.winfo_children():
                    bind_open(child, note)
            bind_open(card)
        for col in range(columns):
            self.cards_frame.grid_columnconfigure(col, weight=1)
        if not self.visible_notes:
            tk.Label(self.cards_frame, text="아직 포스트잇이 없어요 ✿\n오른쪽 위에서 첫 메모를 만들어 보세요.", bg=self.colors["base"], fg="white", font=("Segoe UI", 14), justify="center").pack(pady=100)

    def delete_note(self, note):
        if not messagebox.askyesno("포스트잇 삭제", "이 포스트잇을 삭제할까요?", parent=self.root):
            return False
        previous = list(self.store.data["notes"])
        self.store.data["notes"] = [item for item in previous if item["id"] != note["id"]]
        if not self.persist():
            self.store.data["notes"] = previous
            self.refresh()
            return False
        self.refresh()
        return True

    def toggle_checklist_item(self, note, item_id):
        items = checklist_items(note)
        for item in items:
            if item["id"] == item_id:
                item["done"] = not item["done"]
                break
        else:
            return
        updated = dict(note, checklist=items, body=checklist_body(items), done=all(item["done"] for item in items), updated_at=now())
        index = self.store.data["notes"].index(note)
        self.store.data["notes"][index] = updated
        if self.persist():
            self.refresh()
        else:
            self.store.data["notes"][index] = note
            self.refresh()

    def edit_note(self, note=None, quick=False):
        original = note
        win = tk.Toplevel(self.root)
        win.title("빠른 입력" if quick else "메모 편집")
        win.geometry("690x650")
        win.configure(bg=self.colors["panel"])
        win.transient(self.root)
        frame = ttk.Frame(win, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="⚡ 빠른 입력창" if quick else "메모 편집", font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(0, 16))
        title = tk.StringVar(value=note["title"] if note else "")
        task = tk.BooleanVar(value=note["is_task"] if note else False)
        due = tk.StringVar(value=note.get("due", "") if note else "")
        remind = tk.StringVar(value=note.get("remind_at", "") if note else "")
        today = tk.BooleanVar(value=note.get("today", False) if note else False)
        done = tk.BooleanVar(value=note.get("done", False) if note else False)
        tab = tk.StringVar(value=(note["tab"] if note.get("manual_tab") else "자동 분류") if note else "메모")
        ttk.Label(frame, text="제목").pack(anchor="w")
        ttk.Entry(frame, textvariable=title).pack(fill="x")
        ttk.Label(frame, text="내용 · 할 일은 항목별 체크박스로 입력합니다").pack(anchor="w", pady=(8, 0))
        body = tk.Text(frame, wrap="word", undo=True, font=("Segoe UI", 11), bg=self.colors["canvas"], fg=self.colors["text"], insertbackground=self.colors["text"], relief="flat", padx=12, pady=12)
        body.pack(fill="both", expand=True)
        body.insert("1.0", note["body"] if note else "")
        task_frame = ttk.Frame(frame)
        task_rows = []

        def add_task_row(text="", checked=False, item_id=None):
            row = ttk.Frame(task_frame)
            row.pack(fill="x", pady=4)
            checked_var = tk.BooleanVar(value=checked)
            text_var = tk.StringVar(value=text)
            ttk.Checkbutton(row, variable=checked_var).pack(side="left")
            entry = ttk.Entry(row, textvariable=text_var)
            entry.pack(side="left", fill="x", expand=True, padx=6)
            record = (row, checked_var, text_var, item_id or str(uuid.uuid4()))
            task_rows.append(record)
            def remove_row():
                task_rows.remove(record)
                row.destroy()
            ttk.Button(row, text="×", command=remove_row).pack(side="left")
            return entry

        add_task_button = ttk.Button(task_frame, text="＋ 할 일 추가", command=lambda: add_task_row().focus_set())
        add_task_button.pack(side="bottom", anchor="w", pady=8)
        if note and note["is_task"]:
            for item in checklist_items(note):
                add_task_row(item["text"], item["done"], item["id"])
        opts = ttk.Frame(frame)
        opts.pack(fill="x", pady=6)
        ttk.Checkbutton(opts, text="할 일", variable=task).pack(side="left")
        ttk.Checkbutton(opts, text="오늘 할 일", variable=today).pack(side="left")
        ttk.Checkbutton(opts, text="완료", variable=done).pack(side="left")
        ttk.Label(opts, text="분류").pack(side="left", padx=(15, 4))
        category_picker = ttk.Combobox(opts, textvariable=tab, values=self.tabs() + ["미분류", "자동 분류"], state="readonly", width=14)
        category_picker.pack(side="left")
        category_picker.bind("<<ComboboxSelected>>", lambda _: task.set(tab.get() == "할 일") if tab.get() in ["메모", "할 일", "코드", "링크", "미분류"] else None)
        def show_task_editor(*_):
            if task.get():
                if not task_rows:
                    lines = body.get("1.0", "end-1c").splitlines()
                    for line in lines:
                        match = re.match(r"^\s*-\s*\[([ xX])\]\s*(.*)$", line)
                        content = (match.group(2) if match else line).strip()
                        if content:
                            add_task_row(content, bool(match and match.group(1).lower() == "x"))
                    if not task_rows:
                        add_task_row()
                body.pack_forget()
                task_frame.pack(fill="both", expand=True, before=opts)
            else:
                if task_frame.winfo_manager():
                    lines = [text_var.get().strip() for _, _, text_var, _ in task_rows if text_var.get().strip()]
                    if lines:
                        body.delete("1.0", "end")
                        body.insert("1.0", "\n".join(lines))
                task_frame.pack_forget()
                body.pack(fill="both", expand=True, before=opts)
        task.trace_add("write", show_task_editor)
        show_task_editor()
        dates = ttk.Frame(frame)
        dates.pack(fill="x")
        ttk.Label(dates, text="기한 YYYY-MM-DD").pack(side="left")
        ttk.Entry(dates, textvariable=due, width=14).pack(side="left", padx=4)
        ttk.Label(dates, text="알림 YYYY-MM-DD HH:MM").pack(side="left")
        ttk.Entry(dates, textvariable=remind, width=18).pack(side="left", padx=4)
        dirty = lambda: bool(title.get() or body.get("1.0", "end-1c") or any(text_var.get() for _, _, text_var, _ in task_rows))

        def close():
            if dirty() and not messagebox.askyesno("저장하지 않은 내용", "저장하지 않고 닫을까요?", parent=win):
                return
            win.destroy()

        def save():
            items = [{"id": item_id, "text": text_var.get().strip(), "done": checked_var.get()} for _, checked_var, text_var, item_id in task_rows if text_var.get().strip()] if task.get() else []
            content = checklist_body(items) if task.get() else body.get("1.0", "end-1c")
            if task.get() and not items:
                messagebox.showwarning("빈 할 일", "할 일을 하나 이상 입력하세요.", parent=win)
                return
            if not title.get().strip() and not content.strip():
                messagebox.showwarning("빈 메모", "제목이나 본문을 입력하세요.", parent=win)
                return
            try:
                if due.get().strip():
                    date.fromisoformat(due.get().strip())
                if remind.get().strip():
                    datetime.strptime(remind.get().strip(), "%Y-%m-%d %H:%M")
            except ValueError:
                messagebox.showerror("날짜 형식", "기한은 YYYY-MM-DD, 알림은 YYYY-MM-DD HH:MM 형식으로 입력하세요.", parent=win)
                return
            chosen = tab.get()
            automatic = chosen == "자동 분류"
            category = classify(content, task.get(), self.store.data["examples"]) if automatic else chosen
            record = dict(original) if original else {"id": str(uuid.uuid4()), "created_at": now(), "notified_at": None}
            record.update(title=title.get().strip(), body=content, checklist=items, is_task=task.get(), due=due.get().strip(), remind_at=remind.get().strip(), today=today.get(), done=all(item["done"] for item in items) if task.get() else done.get(), tab=category, manual_tab=not automatic, updated_at=now())
            if not automatic and (not original or original["tab"] != category):
                tokens = list(set(re.findall(r"[\w가-힣]{3,}", content.lower())))
                if tokens:
                    self.store.data["examples"].append({"tokens": tokens, "tab": category})
            previous_notes = list(self.store.data["notes"])
            if original:
                self.store.data["notes"][self.store.data["notes"].index(original)] = record
            else:
                self.store.data["notes"].append(record)
            if self.persist():
                self.refresh()
                win.destroy()
                if quick:
                    messagebox.showinfo("저장됨", f"분류: {category}", parent=self.root)
            else:
                self.store.data["notes"] = previous_notes

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="저장  Ctrl+Enter", style="Accent.TButton", command=save).pack(side="right")
        if original:
            def delete():
                if self.delete_note(original):
                    win.destroy()
            ttk.Button(buttons, text="🗑 삭제", command=delete).pack(side="left")
        win.protocol("WM_DELETE_WINDOW", close)
        win.bind("<Control-Return>", lambda _: save())
        win.bind("<Escape>", lambda _: close())
        if task.get() and task_rows:
            task_rows[0][0].winfo_children()[1].focus_set()
        else:
            body.focus_set()

    def quick_entry(self):
        self.root.deiconify()
        self.edit_note(quick=True)

    def register_hotkey(self):
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        self.hotkey_generation += 1
        if self.hotkey_registered:
            user32.UnregisterHotKey(None, 1)
            self.hotkey_registered = False
        key = self.store.data["settings"].get("shortcut", "Ctrl+Alt+N").split("+")[-1].upper()
        if len(key) != 1 or not user32.RegisterHotKey(None, 1, 0x0001 | 0x0002, ord(key)):
            messagebox.showwarning("단축키 충돌", "전역 단축키를 등록할 수 없습니다. 설정에서 다른 키를 선택하세요.")
            return
        self.hotkey_registered = True
        self.poll_hotkey(self.hotkey_generation)

    def poll_hotkey(self, generation):
        if not self.hotkey_registered or generation != self.hotkey_generation:
            return
        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0x0312, 0x0312, 0x0001):
            if msg.wParam == 1:
                self.quick_entry()
        self.root.after(100, lambda: self.poll_hotkey(generation))

    def add_tab(self):
        name = simpledialog.askstring("탭 추가", "새 탭 이름:", parent=self.root)
        if name and name.strip() and name.strip() not in ["전체", "미분류"] + self.tabs():
            self.store.data["tabs"].append({"id": str(uuid.uuid4()), "name": name.strip(), "created_at": now(), "updated_at": now()})
            if self.persist(): self.refresh()

    def rename_tab(self):
        old = self.active_tab
        custom = next((t for t in self.store.data["tabs"] if t["name"] == old), None)
        if not custom:
            messagebox.showinfo("탭", "이름을 바꿀 사용자 탭을 먼저 선택하세요.")
            return
        name = simpledialog.askstring("탭 이름 변경", "새 이름:", initialvalue=old, parent=self.root)
        if name and name.strip() not in ["전체", "미분류"] + self.tabs():
            custom.update(name=name.strip(), updated_at=now())
            for n in self.store.data["notes"]:
                if n["tab"] == old: n["tab"] = name.strip()
            for e in self.store.data["examples"]:
                if e["tab"] == old: e["tab"] = name.strip()
            self.active_tab = name.strip()
            if self.persist(): self.refresh()

    def delete_tab(self):
        old = self.active_tab
        custom = next((t for t in self.store.data["tabs"] if t["name"] == old), None)
        if custom and messagebox.askyesno("탭 삭제", f"'{old}' 탭을 삭제할까요? 메모는 미분류로 이동합니다."):
            self.store.data["tabs"].remove(custom)
            for n in self.store.data["notes"]:
                if n["tab"] == old: n["tab"] = "미분류"
            self.store.data["examples"] = [e for e in self.store.data["examples"] if e["tab"] != old]
            self.active_tab = "전체"
            if self.persist(): self.refresh()

    def export(self):
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="goorm-memo-export.json")
        if path:
            try:
                Path(path).write_text(json.dumps(self.store.data, ensure_ascii=False, indent=2), encoding="utf-8")
                messagebox.showinfo("내보내기", "JSON 파일을 저장했습니다.")
            except OSError as exc:
                messagebox.showerror("내보내기 실패", str(exc))

    def settings(self):
        win = tk.Toplevel(self.root)
        win.title("설정")
        win.geometry("390x160")
        f = ttk.Frame(win, padding=12); f.pack(fill="both", expand=True)
        ttk.Label(f, text="빠른 입력 단축키 (Ctrl+Alt+문자)").pack(anchor="w")
        shortcut = tk.StringVar(value=self.store.data["settings"].get("shortcut", "Ctrl+Alt+N"))
        ttk.Entry(f, textvariable=shortcut).pack(fill="x")
        def apply():
            if not re.fullmatch(r"Ctrl\+Alt\+[A-Z]", shortcut.get().upper().replace("CTRL", "Ctrl").replace("ALT", "Alt")):
                messagebox.showerror("단축키", "Ctrl+Alt+N 형식으로 입력하세요.", parent=win); return
            self.store.data["settings"]["shortcut"] = shortcut.get()
            if self.persist():
                self.register_hotkey()
                win.destroy()
        ttk.Button(f, text="저장", command=apply).pack(anchor="e", pady=6)
        ttk.Button(f, text="분류 학습 기록 초기화", command=self.reset_examples).pack(anchor="w")

    def reset_examples(self):
        if messagebox.askyesno("학습 기록 초기화", "저장된 분류 수정 사례를 지울까요?"):
            self.store.data["examples"] = []
            self.persist()

    def today_notes(self):
        day = date.today().isoformat()
        return [n for n in self.store.data["notes"] if n["is_task"] and not n["done"] and (n.get("today") or n.get("due") == day)]

    def toggle_pinned(self):
        if self.pinned:
            self.store.data["settings"]["pinned"]["visible"] = False
            self.pinned.destroy(); self.pinned = None; self.persist(); return
        cfg = self.store.data["settings"]["pinned"]
        self.pinned = tk.Toplevel(self.root)
        self.pinned.title("오늘 할 일")
        self.pinned.geometry(cfg.get("geometry", "300x350+100+100"))
        self.pinned.attributes("-topmost", cfg.get("topmost", True))
        self.pinned.protocol("WM_DELETE_WINDOW", self.toggle_pinned)
        cfg["visible"] = True
        self.refresh_pinned()
        self.persist()

    def refresh_pinned(self):
        if not self.pinned: return
        win = self.pinned
        cfg = self.store.data["settings"]["pinned"]
        for child in win.winfo_children(): child.destroy()
        items = self.today_notes()
        bar = ttk.Frame(win, padding=5); bar.pack(fill="x")
        ttk.Label(bar, text=f"오늘 할 일 · {len(items)}개").pack(side="left")
        def collapse():
            cfg["collapsed"] = not cfg.get("collapsed", False)
            if cfg["collapsed"]:
                cfg["expanded_geometry"] = win.geometry()
                win.geometry("250x48")
            else:
                win.geometry(cfg.get("expanded_geometry", "300x350+100+100"))
            self.refresh_pinned(); self.persist()
        ttk.Button(bar, text="펼치기" if cfg.get("collapsed") else "접기", command=collapse).pack(side="right")
        if cfg.get("collapsed"): return
        top = tk.BooleanVar(value=cfg.get("topmost", True))
        def set_top():
            cfg["topmost"] = top.get(); win.attributes("-topmost", top.get()); self.persist()
        ttk.Checkbutton(win, text="항상 위", variable=top, command=set_top).pack(anchor="w")
        for n in items:
            row = ttk.Frame(win, padding=3); row.pack(fill="x")
            def complete(item=n):
                item["done"] = True; item["updated_at"] = now()
                if self.persist(): self.refresh()
            ttk.Button(row, text="□", width=3, command=complete).pack(side="left")
            ttk.Button(row, text=n["title"] or n["body"][:30] or "(할 일)", command=lambda item=n: self.edit_note(item)).pack(side="left", fill="x", expand=True)
        win.bind("<Configure>", self.save_pinned_geometry)

    def save_pinned_geometry(self, event):
        if self.pinned and event.widget == self.pinned and not self.store.data["settings"]["pinned"].get("collapsed"):
            self.store.data["settings"]["pinned"]["geometry"] = self.pinned.geometry()
            if hasattr(self, "geometry_timer"): self.root.after_cancel(self.geometry_timer)
            self.geometry_timer = self.root.after(500, self.persist)

    def check_reminders(self):
        current = datetime.now()
        for n in self.store.data["notes"]:
            if not n["is_task"] or n["done"] or not n.get("due") or n.get("notified_at"): continue
            try:
                due = datetime.strptime(n.get("remind_at") or n["due"] + " 09:00", "%Y-%m-%d %H:%M")
            except ValueError: continue
            if current >= due:
                n["notified_at"] = now()
                if self.persist():
                    self.root.deiconify()
                    messagebox.showinfo("할 일 알림", n["title"] or n["body"][:100], parent=self.root)
                    self.edit_note(n)
        self.root.after(15000, self.check_reminders)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MemoApp().run()
