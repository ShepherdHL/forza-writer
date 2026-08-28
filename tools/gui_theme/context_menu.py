"""A shared right-click Cut/Copy/Paste/Select All menu for every text-input
widget in the GUI, plus the select-all/clear helpers reused by dedicated
Select All / Clear buttons on the multi-line text boxes.

Nothing in gen_modelbin_gui wires this up per-widget at creation time —
`bind_context_menus()` is called once, centrally, after every tab has built
its widgets (mirroring how apply_theme() itself is applied once from
shell.py rather than at each widget's creation site), and walks the whole
widget tree binding as it goes. That means a new tab or a new text field
never needs to remember to opt in.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

_ENTRY_LIKE = (tk.Entry, tk.Spinbox)
_TEXT_LIKE = (tk.Text,)
_BOUND_MARKER = "_context_menu_bound"


def select_all(widget: tk.Widget) -> str:
    """Select every character in an Entry/Spinbox/Combobox or Text widget."""
    if isinstance(widget, _TEXT_LIKE):
        widget.tag_add("sel", "1.0", "end-1c")
    else:
        widget.selection_range(0, "end")
        widget.icursor("end")
    return "break"


def clear_text(widget: tk.Widget) -> str:
    """Delete every character in an Entry/Spinbox/Combobox or Text widget."""
    if isinstance(widget, _TEXT_LIKE):
        widget.delete("1.0", "end")
    else:
        widget.delete(0, "end")
    widget.focus_set()
    return "break"


def _widget_state(widget: tk.Widget) -> str:
    try:
        return str(widget.cget("state"))
    except tk.TclError:
        return "normal"


def _refresh_menu_state(menu: tk.Menu, widget: tk.Widget) -> None:
    editable = _widget_state(widget) not in ("disabled", "readonly")
    menu.entryconfigure("Cut", state="normal" if editable else "disabled")
    menu.entryconfigure("Paste", state="normal" if editable else "disabled")


def attach_context_menu(widget: tk.Widget) -> tk.Menu:
    """Bind a right-click Cut/Copy/Paste/Select All menu (and Ctrl+A) to one
    widget, returning the Menu. Safe to call more than once on the same
    widget — a second call is a no-op that returns the existing menu."""
    if getattr(widget, _BOUND_MARKER, False):
        return widget._context_menu

    menu = tk.Menu(widget, tearoff=0)
    menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
    menu.add_separator()
    menu.add_command(label="Select All", command=lambda: select_all(widget))

    def _post(event):
        _refresh_menu_state(menu, widget)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    # *_args rather than a single positional event: some widget classes'
    # bind scripts (observed on readonly ttk.Combobox) invoke this callback
    # without the usual event-substitution argument.
    widget.bind("<Button-3>", _post)
    widget.bind("<Control-a>", lambda *_args: select_all(widget))
    widget.bind("<Control-A>", lambda *_args: select_all(widget))
    widget._context_menu = menu
    setattr(widget, _BOUND_MARKER, True)
    return menu


def bind_context_menus(root: tk.Misc) -> None:
    """Recursively attach a context menu to every Entry/Text/Combobox/
    Spinbox widget under `root`, at any depth."""
    pending = list(root.winfo_children())
    while pending:
        widget = pending.pop()
        pending.extend(widget.winfo_children())
        if isinstance(widget, _ENTRY_LIKE + _TEXT_LIKE + (ttk.Entry, ttk.Combobox, ttk.Spinbox)):
            attach_context_menu(widget)
