import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
from gui_theme.context_menu import (  # noqa: E402
    attach_context_menu,
    bind_context_menus,
    clear_text,
    select_all,
)

tk = pytest.importorskip("tkinter")
from tkinter import ttk  # noqa: E402


def _make_root():
    root = tk.Tk()
    root.withdraw()
    return root


def test_select_all_selects_full_entry_text():
    root = _make_root()
    try:
        entry = tk.Entry(root)
        entry.insert(0, "hello world")
        select_all(entry)
        assert entry.selection_get() == "hello world"
    finally:
        root.destroy()


def test_select_all_selects_full_text_widget_content():
    root = _make_root()
    try:
        text = tk.Text(root)
        text.insert("1.0", "line one")
        select_all(text)
        assert tuple(str(i) for i in text.tag_ranges("sel")) == (
            text.index("1.0"), text.index("1.0 lineend"))
    finally:
        root.destroy()


def test_clear_text_empties_entry_and_text():
    root = _make_root()
    try:
        entry = tk.Entry(root)
        entry.insert(0, "some value")
        clear_text(entry)
        assert entry.get() == ""

        text = tk.Text(root)
        text.insert("1.0", "some value")
        clear_text(text)
        assert text.get("1.0", "end-1c") == ""
    finally:
        root.destroy()


def test_attach_context_menu_binds_button3_and_is_idempotent():
    root = _make_root()
    try:
        entry = tk.Entry(root)
        attach_context_menu(entry)
        first_binding = entry.bind("<Button-3>")
        assert first_binding

        attach_context_menu(entry)
        assert entry.bind("<Button-3>") == first_binding
    finally:
        root.destroy()


def test_bind_context_menus_finds_nested_widgets():
    root = _make_root()
    try:
        outer = ttk.Frame(root)
        outer.pack()
        inner = ttk.LabelFrame(outer, text="nested")
        inner.pack()
        entry = ttk.Entry(inner)
        entry.pack()
        text = tk.Text(inner)
        text.pack()

        bind_context_menus(root)

        assert entry.bind("<Button-3>")
        assert text.bind("<Button-3>")
    finally:
        root.destroy()


def test_context_menu_disables_cut_and_paste_when_widget_is_readonly():
    root = _make_root()
    try:
        from gui_theme.context_menu import _refresh_menu_state

        combo = ttk.Combobox(root, values=["a", "b"], state="readonly")
        combo.pack()
        menu = attach_context_menu(combo)
        _refresh_menu_state(menu, combo)
        assert str(menu.entrycget("Cut", "state")) == "disabled"
        assert str(menu.entrycget("Paste", "state")) == "disabled"

        entry = tk.Entry(root)
        entry.pack()
        entry_menu = attach_context_menu(entry)
        _refresh_menu_state(entry_menu, entry)
        assert str(entry_menu.entrycget("Cut", "state")) == "normal"
        assert str(entry_menu.entrycget("Paste", "state")) == "normal"
    finally:
        root.destroy()
