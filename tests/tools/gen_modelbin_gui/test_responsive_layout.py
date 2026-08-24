"""Regression coverage for controls at the application's minimum window width."""

import tkinter as tk
from tkinter import ttk


def _control_text(widget):
    try:
        return str(widget.cget("text"))
    except tk.TclError:
        return ""


def test_audit_horizontal_control_rows_at_minimum_width(gui):
    gui.root.geometry("860x640")
    gui.root.update_idletasks()
    problems = []

    for density in ("compact", "balanced", "spacious"):
        gui.density_var.set(density)
        gui._preview_appearance()
        for tab_name in gui._pages:
            gui._show_tab(tab_name)
            gui.root.update_idletasks()
            page = gui._pages[tab_name]
            stack = [page]
            while stack:
                parent = stack.pop()
                children = parent.winfo_children()
                stack.extend(children)
                controls = [child for child in children
                            if isinstance(child, (ttk.Button, ttk.Checkbutton,
                                                  ttk.Radiobutton, ttk.Entry,
                                                  ttk.Combobox, ttk.Spinbox))]
                if len(controls) < 2 or parent.winfo_width() <= 1:
                    continue
                clipped = [child for child in controls
                           if child.winfo_manager()
                           and child.winfo_x() + child.winfo_width() > parent.winfo_width() + 1]
                missing = [child for child in controls
                           if child.winfo_manager() and child.winfo_width() <= 1]
                if clipped or missing:
                    labels = [_control_text(child) or child.winfo_class()
                              for child in clipped + missing]
                    problems.append(f"{density}/{tab_name}: {parent} clips {labels}")
                elif parent.winfo_reqwidth() > parent.winfo_width() + 1:
                    labels = [_control_text(child) or child.winfo_class()
                              for child in controls]
                    problems.append(
                        f"{density}/{tab_name}: {parent} requests {parent.winfo_reqwidth()}px in "
                        f"{parent.winfo_width()}px for {labels}")

    assert not problems, "\n".join(problems)


def test_generator_transfer_actions_survive_long_variable_font_status(gui):
    gui.root.geometry("860x640")
    gui.font_variation_status_var.set(
        "Variable font · file default wght=100 · 27 named instances. "
        "Use Advanced Generator to choose Regular or custom axes.")
    gui.root.update_idletasks()

    for button in (gui.generator_to_direct_btn, gui.generator_to_advanced_btn):
        assert button.winfo_width() > 1
        assert button.winfo_x() + button.winfo_width() <= gui.generator_transfer_row.winfo_width()


def test_open_configurator_stacks_columns_at_minimum_width(gui):
    gui.root.geometry("860x640")
    gui._set_configurator_workspace_open(True)
    gui.root.update_idletasks()

    assert gui._configurator_layout_wide is False
    assert gui.configurator_detail_col.winfo_y() >= (
        gui.configurator_list_col.winfo_y() + gui.configurator_list_col.winfo_height())
