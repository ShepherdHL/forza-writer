"""License Plates tab: browse a plate standard, fill in its fields, watch a
live preview, and generate ordinary Forza Writer shapes from it.

One tab, not split like Generator/Advanced/Direct: those are different
*generation strategies* over the same font input, while a plate is one
linear workflow (standard -> fields -> appearance -> preview -> generate)
operating on one selected template. Splitting that workflow across tabs
would fragment a single task across tab-switches.

**Redesigned 2026-08-26** around three problems in the original layout:
real-world and fictional plates competing for the same narrow tree,
navigation consuming more visual weight than the plate itself, and preview
requiring a manual click. None of the *generator* -- template loading,
validation, rendering, export, saved configs -- changed; every call into
`forza_writer.plates.*`/`plate_config_store`/`fabric_project`/`export`
below is the same call the previous layout made. This file only changed
how that machinery is presented.

**Library, not one flat tree.** `_plate_library()` sorts every template
into `real` / `fictional` / `community` / `custom` -- a segmented control
at the top of the page picks one, and the browser only ever shows that
library's plates (`_LIBRARY_LABELS`, `_LIBRARY_SEARCH_HINTS`). A fictional
GTA V plate and a real DMV standard are never visible in the same list.
`community` has no shipped templates yet (see spec) -- selecting it shows
an explicit empty state rather than nothing.

**Drill-down, not a fully-expanded tree.** `_GROUP_LEVELS` defines an
ordered list of grouping keys per library (country/franchise, then
jurisdiction/location); `_plates_resolve_browser_state()` walks them,
silently skipping a level whose remaining templates all share one value
(nothing to disambiguate yet, but the level still exists for when more
templates fill it in) and stopping at the first level with more than one
distinct value to show as a clickable group list. A breadcrumb row above
the browser shows the full effective path (including auto-skipped levels,
since that's still real information about what's being viewed) and lets
the user jump back to any point in it. Once every level is either chosen
or trivially skipped, the remaining templates show as leaf rows.

**Preview is live, debounced.** Every field now only ever renders a plain
placeholder box per character, sized/spaced from a font's real metrics
(see forza_writer/plates/glyph_resolve.py's module docstring -- no
letterform geometry is ever produced), and background/border/decorations
are pre-rendered too (forza_writer/plates/blank_library.py) -- a render is
now cheap enough (all 17 shipped templates: 9-62 shapes) that debounced
live preview no longer costs what it used to when this was pixel-traced
letterforms and font-fitting. Rendering still always runs on a background
thread (via msg_queue/_poll_queue) so a slow first render (a template with
no cached blank yet) can't freeze the UI.
"""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
import tkinter as tk

from PIL import ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import file_preview  # noqa: E402
import gui_theme  # noqa: E402
import plate_config_store  # noqa: E402
from gen_forza_fonts_reference import FONT_IDENTIFICATION  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
from forza_writer.export import to_json as plate_to_json  # noqa: E402
from forza_writer.fabric_project import save as save_fabric_project, to_fabric_project  # noqa: E402
from forza_writer.plates.instance import FieldOverride, PlateInstance  # noqa: E402
from forza_writer.plates.loader import list_templates, reload_templates  # noqa: E402
from forza_writer.plates.renderer import PLATE_SHAPE_WARN_THRESHOLD, render_plate  # noqa: E402
from forza_writer.plates.template import FieldRole, PlateTemplate  # noqa: E402
from forza_writer.plates.validation import is_valid_for_generation, validate_instance  # noqa: E402

from ..state import PLATES_PREVIEW_SIZE  # noqa: E402
from ..i18n import t  # noqa: E402

# A dedicated top-level output folder, not a subfolder of the shared
# fontpacks output directory (which defaults to data/fontpacks -- writing
# plates as data/fontpacks/plates/... nested plate output inside a folder
# meant for character fontpacks, confusing given plates aren't fontpacks at
# all; see forza_writer/plates/glyph_resolve.py's module docstring for why
# a plate field never touches the fontpack pipeline anymore). Fixed, not a
# Settings-configurable path like the fontpack/modelbin/direct/image output
# dirs -- those exist because their generators are reused across machines
# with different setups; the plate generator is comparatively new and this
# keeps its output easy to find without another setting to configure first.
_PLATES_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'plates'

_VALIDATION_DEBOUNCE_MS = 150   # cheap (no font work) -- fine to run on nearly every keystroke
_PREVIEW_DEBOUNCE_MS = 350      # a real render, but a cheap one now -- see module docstring

_BROWSER_WIDTH = 260
_FIELDS_WIDTH = 340
# Both columns lock width via pack_propagate(False) so entries never
# stretch across the page (see module docstring). Height needs locking
# too, not just width: with nothing else forcing it, the browser/fields
# row's natural height came from whichever sibling asked for less --
# too short once a field's stacked label+entry+validation-hint layout
# needed more room than the old single-row layout did (a real bug this
# caught: a validation hint silently clipped outside its unmapped parent
# instead of showing). A generous fixed minimum avoids depending on
# incidental sibling sizing at all.
_COLUMN_HEIGHT = 470  # comfortably fits the tallest case (Japan's 4 grouped fields + a hint + the
# Plate Rules/Placeholder Font rows above them: ~448px measured)

# ---------------------------------------------------------------------------
# Library taxonomy: real-world jurisdictions, fictional game universes,
# credited community kits (empty today), and the standalone custom/blank
# builder. Every template belongs to exactly one, decided from its own data
# (never a hardcoded template-id list) so a new template just needs the
# right tag/country to land in the right place.
# ---------------------------------------------------------------------------

LIBRARY_REAL = "real"
LIBRARY_FICTIONAL = "fictional"
LIBRARY_COMMUNITY = "community"
LIBRARY_CUSTOM = "custom"
_LIBRARY_ORDER = (LIBRARY_REAL, LIBRARY_FICTIONAL, LIBRARY_COMMUNITY, LIBRARY_CUSTOM)


def _plate_library(template: PlateTemplate) -> str:
    if template.country == "XX":
        return LIBRARY_CUSTOM
    if "community" in template.tags:
        return LIBRARY_COMMUNITY
    if "fictional-game" in template.tags:
        return LIBRARY_FICTIONAL
    return LIBRARY_REAL


# Display names for country/franchise codes across both real-world and
# fictional libraries -- deliberately small and hand-picked rather than a
# full ISO-3166 table/dependency; extend as templates for more
# countries/franchises get added. An unlisted code just falls back to
# showing the raw code, never a crash.
_COUNTRY_NAMES = {
    "US": "United States",
    "GB": "United Kingdom",
    "JP": "Japan",
    "DE": "Germany",
    "GTA": "Grand Theft Auto V",
    "NFS": "Need for Speed",
    "SR": "Saints Row",
    "HALO": "Halo",
    "CP2077": "Cyberpunk 2077",
    "MEDGE": "Mirror's Edge",
    "DL": "Dying Light",
    "PHAS": "Phasmophobia",
    "XX": "Blank Template",
}


def _country_display_name(code: str) -> str:
    return _COUNTRY_NAMES.get(code, code)


def _level_country(template: PlateTemplate) -> tuple[str, str]:
    return template.country, _country_display_name(template.country)


def _level_jurisdiction(template: PlateTemplate) -> tuple[str, str]:
    value = template.jurisdiction or "General"
    return value, value


# Real-world specialty-plate categories: the shape most US state DMV
# programs use to organize plates beyond the standard passenger issue
# (modeled on Louisiana DPS's own published categories --
# https://expresslane.dps.louisiana.gov/specialplatespublic/specialplatesviewer.aspx
# -- but the categories themselves aren't Louisiana-specific; most states
# run some version of military/university/organization/Greek plates).
# `plate_type` is a free string (see forza_writer/plates/template.py) --
# this is a *display* registry, not a validated enum, so a template using
# a value not listed here still works, just falls back to a title-cased
# rendering of the raw value rather than crashing.
#
# This exists purely as browsing/search skeleton -- see
# docs/PLATE_TEMPLATE_SCHEMA.md's "Real-world specialty categories"
# section for the full rationale. No templates use anything but
# "passenger" yet; adding one that does needs no further code change here,
# same as any other _GROUP_LEVELS level (auto-skipped while every
# template in a jurisdiction shares one value, exactly like jurisdiction
# itself already does for a single-jurisdiction country).
PLATE_CATEGORIES: dict[str, str] = {
    "passenger": "Standard / Passenger",
    "military": "Military & Veteran",
    "law_enforcement": "Law Enforcement",
    "university": "University / College",
    "organization": "Organization / Service",
    "special_interest": "Special Interest",
    "high_school": "High School",
    "greek": "Sorority / Fraternity",
}


def _category_display_name(plate_type: str) -> str:
    return PLATE_CATEGORIES.get(plate_type, plate_type.replace('_', ' ').title())


def _level_category(template: PlateTemplate) -> tuple[str, str]:
    return template.plate_type, _category_display_name(template.plate_type)


# One ordered tuple of (template -> (key, label)) functions per library --
# real-world and fictional currently share most of this shape (country ==
# jurisdiction/state or franchise, jurisdiction == state/location) since
# both fields already carry the right meaning for either; nothing stops a
# future library from defining a different level shape -- see
# _plates_resolve_browser_state, which skips any level with only one
# distinct value automatically, so adding a level here never adds a dead
# screen for today's sparse data. Real-world's 3rd level (category) is
# scoped to real-world only -- fictional games don't run specialty-plate
# programs the way state DMVs do, so a 3rd level there would just be dead
# weight.
_GROUP_LEVELS: dict[str, tuple] = {
    LIBRARY_REAL: (_level_country, _level_jurisdiction, _level_category),
    LIBRARY_FICTIONAL: (_level_country, _level_jurisdiction),
    LIBRARY_COMMUNITY: (),
    LIBRARY_CUSTOM: (),
}

_FIELD_ROLE_GROUPS = {
    FieldRole.REGISTRATION: "plates.fields.group.registration",
    FieldRole.REGION_CODE: "plates.fields.group.registration",
    FieldRole.CLASSIFICATION: "plates.fields.group.registration",
    FieldRole.JURISDICTION_TEXT: "plates.fields.group.header",
    FieldRole.DECORATIVE_TEXT: "plates.fields.group.decorative",
    FieldRole.FREE_TEXT: "plates.fields.group.custom",
}


# Placeholder-font choices for the combobox below: 0 is the sentinel for
# "plain boxes" (PlateInstance.placeholder_font=None); 1-11 are FH6's
# native in-game fonts. Labels mirror forza_font_text.py's own
# _font_choice_label so the same font reads the same way in both tabs.
_PLACEHOLDER_FONT_CHOICES = (0,) + tuple(range(1, 12))


def _placeholder_font_label(font: int) -> str:
    if font == 0:
        return 'Boxes (no letterforms)'
    ident = FONT_IDENTIFICATION.get(font, {"confirmed": False, "note": "Unidentified."})
    mark = "Confirmed" if ident["confirmed"] else "Lead"
    note = ident["note"]
    if note.strip().lower() == "unidentified.":
        return f"Forza Font {font}"
    return f"Forza Font {font} ({mark}: {note})"


def _template_display_name(template: PlateTemplate) -> str:
    return t(template.display_name_key) if _has_string(template.display_name_key) else template.template_id


def _plate_matches_search(template: PlateTemplate, search: str) -> bool:
    haystack = " ".join((
        _template_display_name(template), template.country, _country_display_name(template.country),
        template.jurisdiction or "", template.era, template.plate_type,
        _category_display_name(template.plate_type),
        " ".join(template.tags), template.accuracy_status.value,
    )).lower()
    return search in haystack


class PlatesTabMixin:
    def _build_plates_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['plates'] = page
        content = self._build_scroll_shell(page, 'plates')

        self._plates_template: PlateTemplate | None = None
        self._plates_field_vars: dict[str, tk.StringVar] = {}
        self._plates_field_hint_labels: dict[str, ttk.Label] = {}
        self._plates_photo = None
        self._plates_library = LIBRARY_REAL
        self._plates_breadcrumb: list[tuple[int, str]] = []  # [(level_index, chosen_key), ...]
        self._plates_library_buttons: dict[str, ttk.Button] = {}
        self._plates_nav_history: list[tuple] = []  # stack of _plates_snapshot() results, for "Back"

        self._build_plates_header(content)
        self.plates_breadcrumb_row = ttk.Frame(content)
        self.plates_breadcrumb_row.pack(fill='x', padx=12, pady=(0, 6))

        # A dedicated wrapper, not `content` itself, as the parent handed to
        # _bind_responsive_columns: that call does `parent.bind('<Configure>',
        # ...)` for its own width-threshold tracking, which -- bound
        # directly on `content` -- silently replaced _build_scroll_shell's
        # own `content.bind('<Configure>', ...)` that keeps the page
        # canvas's scrollregion in sync (Tk's bind() replaces a widget's
        # existing handler for the same event by default; it doesn't
        # stack). With no scrollregion ever set, the page canvas had
        # nothing to clamp the view against, so the mouse wheel scrolled
        # this tab indefinitely in both directions past its actual content.
        # No other tab passes `content` straight into a responsive-columns
        # call this way, which is why this was Plates-only.
        columns_row = ttk.Frame(content)
        columns_row.pack(fill='both', expand=True)
        browser = ttk.Frame(columns_row)
        right = ttk.Frame(columns_row)
        self._bind_responsive_columns(columns_row, browser, right, threshold=900,
                                       expand='right', debounce_ms=150)
        preview_col = ttk.Frame(right)
        fields_col = ttk.Frame(right)
        self._bind_responsive_columns(right, preview_col, fields_col, threshold=620,
                                       expand='left', debounce_ms=150)

        self._build_plates_browser(browser)
        self._build_plates_preview(preview_col)
        self._build_plates_fields(fields_col)
        self._build_plates_actions(content)

        self._refresh_plates_library_buttons()
        self._refresh_plates_browser()

    # -- Header: library selector + saved-configs menu -----------------------

    def _build_plates_header(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill='x', padx=12, pady=(12, 4))

        selector = ttk.Frame(header)
        selector.pack(side='left')
        for library in _LIBRARY_ORDER:
            btn = ttk.Button(selector, text=t(f'plates.library.{library}'),
                              command=lambda lib=library: self._set_plates_library(lib))
            btn.pack(side='left', padx=(0, 4))
            self._plates_library_buttons[library] = btn

        config_area = ttk.Frame(header)
        config_area.pack(side='right')
        self.plates_config_menu_btn = ttk.Menubutton(config_area, text=t('plates.config.menu_button'))
        self.plates_config_menu = tk.Menu(self.plates_config_menu_btn, tearoff=False)
        self.plates_config_menu_btn.configure(menu=self.plates_config_menu)
        self.plates_config_menu_btn.pack(side='right')
        self._refresh_plates_config_menu()

    def _set_plates_library(self, library: str):
        if library == self._plates_library:
            return
        self._plates_push_history()
        self._plates_library = library
        self._plates_breadcrumb = []
        self.plates_search_var.set('')
        self._clear_plates_selection()
        self._refresh_plates_library_buttons()
        self._refresh_plates_browser()

    def _refresh_plates_library_buttons(self):
        for library, btn in self._plates_library_buttons.items():
            btn.configure(style='Accent.TButton' if library == self._plates_library else 'TButton')

    # -- Browser: search + drill-down list + breadcrumb ----------------------

    def _build_plates_browser(self, parent):
        parent.configure(width=_BROWSER_WIDTH, height=_COLUMN_HEIGHT)
        parent.pack_propagate(False)

        self.plates_search_var = tk.StringVar()
        search_entry = ttk.Entry(parent, textvariable=self.plates_search_var)
        search_entry.pack(fill='x', padx=4, pady=(4, 0))
        self.plates_search_var.trace_add('write', lambda *_: self._debounce(
            'plates_search', 200, self._refresh_plates_browser))

        tree_row = ttk.Frame(parent)
        tree_row.pack(fill='both', expand=True, padx=4, pady=(4, 4))
        self.plates_template_tree = ttk.Treeview(tree_row, show='tree', height=16)
        scroll = gui_theme.AutoHideScrollbar(tree_row, orient='vertical',
                                              command=self.plates_template_tree.yview)
        self.plates_template_tree.configure(yscrollcommand=scroll.set)
        self.plates_template_tree.pack(side='left', fill='both', expand=True,
                                        padx=(0, gui_theme.SCROLLBAR_GUTTER))
        scroll.pack(side='right', fill='y')
        self.plates_template_tree.bind('<<TreeviewSelect>>', self._on_plates_row_selected)
        self._register_independent_scroll(self.plates_template_tree)

        ttk.Button(parent, text=t('plates.browser.details_button'),
                   command=self._show_plates_details).pack(fill='x', padx=4, pady=(0, 4))

    def _plates_pool_for_library(self, library: str) -> list[PlateTemplate]:
        return [tpl for tpl in self._plates_listed if _plate_library(tpl) == library]

    def _plates_resolve_browser_state(self):
        """Applies the active library + search + breadcrumb, auto-skipping
        any grouping level whose remaining templates all share one value.
        Returns (pool, trail, distinct) where `trail` is the full effective
        path as (level_index, key, label, is_explicit) tuples (for the
        breadcrumb) and `distinct` is either None (pool is ready to show as
        leaf template rows) or a dict of {key: (label, count)} for the next
        undecided level (pool should show as clickable group rows)."""
        library = self._plates_library
        pool = self._plates_pool_for_library(library)
        search = self.plates_search_var.get().strip().lower() or None
        if search:
            pool = [tpl for tpl in pool if _plate_matches_search(tpl, search)]

        levels = _GROUP_LEVELS.get(library, ())
        explicit = dict(self._plates_breadcrumb)
        trail: list[tuple[int, str, str, bool]] = []

        for idx, level_fn in enumerate(levels):
            if search:
                break  # a search flattens navigation straight to matching leaves
            pairs = [level_fn(tpl) for tpl in pool]
            if idx in explicit:
                key = explicit[idx]
                label = next((lab for k, lab in pairs if k == key), key)
                pool = [tpl for tpl, (k, _lab) in zip(pool, pairs) if k == key]
                trail.append((idx, key, label, True))
                continue
            distinct: dict[str, list] = {}
            for k, lab in pairs:
                entry = distinct.setdefault(k, [lab, 0])
                entry[1] += 1
            if len(distinct) <= 1:
                if distinct:
                    only_key, (only_label, _count) = next(iter(distinct.items()))
                    pool = [tpl for tpl, (k, _lab) in zip(pool, pairs) if k == only_key]
                    trail.append((idx, only_key, only_label, False))
                continue
            return pool, trail, {k: tuple(v) for k, v in distinct.items()}

        return pool, trail, None

    def _refresh_plates_browser(self):
        reload_templates()
        self._plates_listed = list_templates()
        self._plates_by_id = {tpl.template_id: tpl for tpl in self._plates_listed}

        pool, trail, distinct = self._plates_resolve_browser_state()
        self._plates_browser_trail = trail

        tree = self.plates_template_tree
        tree.delete(*tree.get_children())

        if not pool:
            empty_key = 'plates.browser.empty_community' if (
                self._plates_library == LIBRARY_COMMUNITY and not self._plates_pool_for_library(LIBRARY_COMMUNITY)
            ) else 'plates.browser.empty_search'
            tree.insert('', 'end', iid='empty', text=t(empty_key))
        elif distinct is not None:
            for key, (label, count) in sorted(distinct.items(), key=lambda kv: kv[1][0]):
                tree.insert('', 'end', iid=f'group:{key}', text=f'{label}  ({count})')
        else:
            for template in sorted(pool, key=_template_display_name):
                tree.insert('', 'end', iid=template.template_id,
                            text=f'{_template_display_name(template)}  [{template.era}]')

        self._rebuild_plates_breadcrumb()

        if self._plates_template is not None and self._plates_template.template_id not in self._plates_by_id:
            self._clear_plates_selection()

    def _rebuild_plates_breadcrumb(self):
        row = self.plates_breadcrumb_row
        for child in row.winfo_children():
            child.destroy()

        back_btn = ttk.Button(row, text=t('plates.browser.back_button'), command=self._plates_go_back)
        back_btn.pack(side='left', padx=(0, 10))
        if not self._plates_nav_history:
            back_btn.state(['disabled'])

        def crumb(text, command=None, is_current=False):
            style = 'TLabel' if is_current else 'Link.TLabel'
            lbl = ttk.Label(row, text=text, style=style, cursor='' if is_current else 'hand2')
            lbl.pack(side='left')
            if command is not None:
                lbl.bind('<Button-1>', lambda _e: command())

        is_root_current = not self._plates_browser_trail and self._plates_template is None
        crumb(t(f'plates.browser.breadcrumb_root.{self._plates_library}'),
              command=None if is_root_current else lambda: self._plates_breadcrumb_jump(None),
              is_current=is_root_current)

        for i, (level_index, _key, label, is_explicit) in enumerate(self._plates_browser_trail):
            ttk.Label(row, text='  ›  ', style='Hint.TLabel').pack(side='left')
            is_last = (i == len(self._plates_browser_trail) - 1) and self._plates_template is None
            crumb(label, command=None if is_last else lambda idx=level_index: self._plates_breadcrumb_jump(idx),
                  is_current=is_last)

        if self._plates_template is not None:
            ttk.Label(row, text='  ›  ', style='Hint.TLabel').pack(side='left')
            crumb(_template_display_name(self._plates_template), is_current=True)

    def _plates_breadcrumb_jump(self, level_index: int | None):
        self._plates_push_history()
        if level_index is None:
            self._plates_breadcrumb = []
        else:
            self._plates_breadcrumb = [(li, k) for li, k in self._plates_breadcrumb if li < level_index]
        self._clear_plates_selection()
        self._refresh_plates_browser()

    def _on_plates_row_selected(self, _event=None):
        selection = self.plates_template_tree.selection()
        if not selection:
            return
        row_id = selection[0]
        if row_id.startswith('group:'):
            _pool, _trail, distinct = self._plates_resolve_browser_state()
            if distinct is None:
                return
            # The next undecided level is however many entries are already
            # in the trail (explicit or auto-skipped) -- both narrow `pool`
            # before we got here, so both count toward "how deep are we."
            level_index = len(self._plates_browser_trail)
            key = row_id[len('group:'):]
            self._plates_push_history()
            self._plates_breadcrumb.append((level_index, key))
            self._refresh_plates_browser()
            return

        template = self._plates_by_id.get(row_id)
        if template is None:
            return
        # A pool of exactly one template means this row was never a real
        # choice among options -- it's the only thing the previous group
        # click (or search) could possibly have led to. Pushing a history
        # entry just for that made Back look broken for a single-template
        # franchise (GTA, CP2077, any single-template real-world country):
        # undoing only the selection restores the *identical* one-row list,
        # the sole visible change being the detail panel clearing, which is
        # easy to miss and reads as "nothing happened." Skipping the push
        # here means Back instead returns straight to wherever the browser
        # last actually had more than one option to pick from.
        pool, _trail, distinct = self._plates_resolve_browser_state()
        if not (distinct is None and len(pool) == 1):
            self._plates_push_history()
        self._select_plates_template(template)

    # -- Back navigation: a history stack, not just breadcrumb-click-to-jump.
    # The breadcrumb only lets you jump to an *ancestor* of where you are --
    # "Back" retraces whatever you actually did (drill down, switch library,
    # pick a template), one step at a time, the way a browser's back button
    # does, so returning to a plate you looked at two selections ago doesn't
    # require remembering/aiming for the right breadcrumb segment.

    def _plates_snapshot(self):
        return (self._plates_library, tuple(self._plates_breadcrumb), self.plates_search_var.get(),
                self._plates_template.template_id if self._plates_template else None)

    def _plates_push_history(self):
        self._plates_nav_history.append(self._plates_snapshot())
        if len(self._plates_nav_history) > 50:  # cap so a long session can't grow this unboundedly
            self._plates_nav_history.pop(0)

    def _plates_go_back(self):
        if not self._plates_nav_history:
            return
        library, breadcrumb, search, template_id = self._plates_nav_history.pop()
        self._plates_library = library
        self._plates_breadcrumb = list(breadcrumb)
        self.plates_search_var.set(search)
        self._refresh_plates_library_buttons()
        self._refresh_plates_browser()
        template = self._plates_by_id.get(template_id) if template_id else None
        if template is not None:
            if self.plates_template_tree.exists(template_id):
                self.plates_template_tree.selection_set(template_id)
            self._select_plates_template(template)
        else:
            self._clear_plates_selection()

    def _clear_plates_selection(self):
        self._plates_template = None
        self._plates_field_vars = {}
        self._plates_field_hint_labels = {}
        for child in self.plates_fields_body.winfo_children():
            child.destroy()
        ttk.Label(self.plates_fields_body, text=t('plates.browser.none_selected'),
                  style='Hint.TLabel').pack(anchor='w')
        self.plates_mode_frame.pack_forget()
        self.plates_canvas.delete('all')
        self._plates_photo = None
        self.plates_shape_count_var.set(t('plates.preview.not_yet_rendered'))
        self._plates_forget_last_generated()
        self._rebuild_plates_breadcrumb()

    def _plates_forget_last_generated(self):
        """A previously-generated file no longer matches what's on screen
        (a new/different template got selected) -- Send to KFPS must not
        keep offering to send it."""
        self._plates_last_generated_json = None
        if hasattr(self, 'plates_send_kfps_btn'):
            self.plates_send_kfps_btn.configure(state='disabled')

    def _select_plates_template(self, template: PlateTemplate):
        self._plates_forget_last_generated()
        self._plates_template = template
        library = _plate_library(template)
        baseline_key = f'plates.mode.baseline.{library}' if library != LIBRARY_CUSTOM else None
        if baseline_key is not None:
            self.plates_mode_baseline_radio.configure(text=t(baseline_key))
            self.plates_mode_frame.pack(fill='x', **gui_theme.SECTION_PAD, before=self.plates_fields_group_frame)
            self.plates_mode_var.set('authentic')
        else:
            self.plates_mode_frame.pack_forget()
            self.plates_mode_var.set('vanity')
        self._on_plates_mode_changed()
        self._rebuild_plates_field_entries()
        self._update_plates_validation_hints()
        self._rebuild_plates_breadcrumb()
        self._schedule_plates_preview()

    def _show_plates_details(self):
        # A modal popup blocked the workspace and had to be dismissed before
        # doing anything else, for content the user only ever reads, never
        # acts on -- the shared Log panel (bottom of the window, visible
        # regardless of tab) already exists for exactly this: a non-blocking
        # readout with its own scrollback, so provenance/sourcing notes from
        # several plates stay comparable side by side instead of vanishing
        # the moment the dialog closes.
        template = self._plates_template
        if template is None:
            return
        self._log(f'--- {t("plates.details.title")} ---', tag='hint')
        for line in _format_plate_details(template).split('\n'):
            self._log(line)

    # -- Preview + fields + mode ----------------------------------------------

    def _build_plates_preview(self, parent):
        self.plates_canvas = tk.Canvas(parent, width=PLATES_PREVIEW_SIZE[0],
                                        height=PLATES_PREVIEW_SIZE[1], highlightthickness=1)
        self.plates_canvas.pack(padx=4, pady=(4, 0), fill='both', expand=True)
        self._plates_last_preview_size = None
        self.plates_canvas.bind('<Configure>', lambda _e: self._debounce(
            'plates_preview_resize', 150, self._on_plates_preview_canvas_resized))
        status_row = ttk.Frame(parent)
        status_row.pack(fill='x', padx=4, pady=4)
        self.plates_shape_count_var = tk.StringVar(value=t('plates.preview.not_yet_rendered'))
        ttk.Label(status_row, textvariable=self.plates_shape_count_var,
                  style='Hint.TLabel').pack(side='left')

    def _on_plates_preview_canvas_resized(self):
        """Re-renders at the canvas's new size once a resize (window drag,
        responsive column reflow) settles -- so the plate keeps filling the
        panel rather than staying whatever size it was on last render."""
        size = (self.plates_canvas.winfo_width(), self.plates_canvas.winfo_height())
        if size == self._plates_last_preview_size:
            return
        self._schedule_plates_preview()

    def _build_plates_fields(self, parent):
        parent.configure(width=_FIELDS_WIDTH, height=_COLUMN_HEIGHT)
        parent.pack_propagate(False)

        self.plates_mode_frame = ttk.LabelFrame(parent, text=gui_theme.hud_label(t('plates.mode.title')))
        self.plates_mode_var = tk.StringVar(value='authentic')
        mode_row = ttk.Frame(self.plates_mode_frame)
        mode_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.plates_mode_baseline_radio = ttk.Radiobutton(
            mode_row, text=t('plates.mode.baseline.real'), value='authentic',
            variable=self.plates_mode_var, command=self._on_plates_mode_changed)
        self.plates_mode_baseline_radio.pack(side='left', padx=(0, 12))
        ttk.Radiobutton(mode_row, text=t('plates.mode.customized'), value='vanity',
                         variable=self.plates_mode_var,
                         command=self._on_plates_mode_changed).pack(side='left')
        self.plates_vanity_badge = ttk.Label(self.plates_mode_frame, text=t('plates.mode.vanity_badge'),
                                              style='Warn.TLabel', wraplength=_FIELDS_WIDTH - 16)

        # Placeholder font: swaps every character's plain box for one of
        # FH6's 11 native in-game fonts (real, final letterform meshes --
        # see glyph_resolve.py's module docstring). Always visible
        # regardless of library/mode, since it's a rendering choice, not a
        # standard-specific one -- unlike Plate Rules above, this doesn't
        # get hidden for the Custom library.
        font_frame = ttk.LabelFrame(parent, text=gui_theme.hud_label(t('plates.placeholder_font.title')))
        font_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        font_row = ttk.Frame(font_frame)
        font_row.pack(fill='x', **gui_theme.ROW_PAD)
        self.plates_placeholder_font_var = tk.IntVar(value=0)
        self.plates_placeholder_font_combo = ttk.Combobox(
            font_row, state='readonly', width=40,
            values=[_placeholder_font_label(f) for f in _PLACEHOLDER_FONT_CHOICES])
        self.plates_placeholder_font_combo.current(0)
        self.plates_placeholder_font_combo.pack(side='left', fill='x', expand=True)
        self.plates_placeholder_font_combo.bind('<<ComboboxSelected>>', self._on_plates_placeholder_font_changed)

        self.plates_fields_group_frame = ttk.LabelFrame(parent, text=gui_theme.hud_label(t('plates.fields.title')))
        self.plates_fields_group_frame.pack(fill='both', expand=True, **gui_theme.SECTION_PAD)
        self.plates_fields_body = ttk.Frame(self.plates_fields_group_frame)
        self.plates_fields_body.pack(fill='both', expand=True, **gui_theme.ROW_PAD)
        ttk.Label(self.plates_fields_body, text=t('plates.browser.none_selected'),
                  style='Hint.TLabel').pack(anchor='w')

    def _build_plates_actions(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Button(row, text=t('plates.config.save_button'),
                   command=self._save_plate_config).pack(side='left')
        self.plates_send_kfps_btn = ttk.Button(row, text=t('plates.generate.send_to_kfps'),
                                                command=self._send_plate_to_kfps, state='disabled')
        self.plates_send_kfps_btn.pack(side='right', padx=(0, 8))
        self.plates_generate_btn = ttk.Button(row, text=t('plates.generate.button'), style='Accent.TButton',
                                               command=self._generate_plate)
        self.plates_generate_btn.pack(side='right')
        self.plates_generate_status_var = tk.StringVar(value='')
        ttk.Label(parent, textvariable=self.plates_generate_status_var, style='Hint.TLabel',
                  wraplength=gui_theme.WRAP_WIDE, justify='left').pack(
            fill='x', padx=12, pady=(0, 8), anchor='w')
        self._plates_last_generated_json: Path | None = None

    def _on_plates_placeholder_font_changed(self, _event=None):
        index = self.plates_placeholder_font_combo.current()
        self.plates_placeholder_font_var.set(_PLACEHOLDER_FONT_CHOICES[index])
        self._schedule_plates_preview()

    def _on_plates_mode_changed(self):
        if self.plates_mode_var.get() == 'vanity':
            self.plates_vanity_badge.pack(fill='x', padx=4, pady=(0, 4))
        else:
            self.plates_vanity_badge.pack_forget()
        self._update_plates_validation_hints()
        self._schedule_plates_preview()

    def _rebuild_plates_field_entries(self):
        for child in self.plates_fields_body.winfo_children():
            child.destroy()
        self._plates_field_vars = {}
        self._plates_field_hint_labels = {}
        template = self._plates_template
        if template is None:
            return

        groups: dict[str, list] = {}
        for field in template.fields:
            group_key = _FIELD_ROLE_GROUPS.get(field.role, 'plates.fields.group.custom')
            groups.setdefault(group_key, []).append(field)
        show_group_headers = len(groups) > 1

        for group_key, fields in groups.items():
            if show_group_headers:
                ttk.Label(self.plates_fields_body, text=gui_theme.hud_label(t(group_key)),
                          style='Category.TLabel').pack(anchor='w', pady=(6, 2))
            for field in fields:
                # Label stacked above its entry, not beside it: a fixed-width
                # side-by-side label truncates on longer field names (e.g.
                # "Micro-Print (Easter Egg)") in a column deliberately kept
                # narrow (see _FIELDS_WIDTH) so entries don't stretch across
                # the page -- stacking is the layout that stays readable at
                # either extreme.
                row = ttk.Frame(self.plates_fields_body)
                row.pack(fill='x', pady=(2, 4))
                ttk.Label(row, text=t(field.label_key) if _has_string(field.label_key) else field.field_id,
                          style='Hint.TLabel').pack(anchor='w')
                # field.editable_in_authentic_mode is not enforced anywhere
                # yet (schema-only -- see docs/PLATE_GENERATOR_ARCHITECTURE.md's
                # "Known limitations"); every entry stays editable regardless.
                var = tk.StringVar(value=field.default_text)
                entry = ttk.Entry(row, textvariable=var)
                entry.pack(fill='x', expand=True)
                var.trace_add('write', lambda *_: self._debounce(
                    'plates_validation', _VALIDATION_DEBOUNCE_MS, self._on_plates_field_changed))
                self._plates_field_vars[field.field_id] = var
                hint = ttk.Label(self.plates_fields_body, text='', style='Danger.TLabel',
                                  wraplength=_FIELDS_WIDTH - 16, justify='left')
                self._plates_field_hint_labels[field.field_id] = hint

    def _on_plates_field_changed(self):
        self._update_plates_validation_hints()
        self._schedule_plates_preview()

    def _current_plate_instance(self) -> PlateInstance | None:
        template = self._plates_template
        if template is None:
            return None
        return PlateInstance(
            template_id=template.template_id,
            mode=self.plates_mode_var.get(),
            field_values={fid: var.get() for fid, var in self._plates_field_vars.items()},
            placeholder_font=self.plates_placeholder_font_var.get() or None,
        )

    def _update_plates_validation_hints(self):
        """Cheap: length/pattern/exclusion checks only, no font/shape work
        at all -- safe to run on nearly every keystroke."""
        template = self._plates_template
        instance = self._current_plate_instance()
        if template is None or instance is None:
            return

        for hint in self._plates_field_hint_labels.values():
            hint.pack_forget()
        if instance.mode == 'authentic':
            errors = validate_instance(template, instance)
            for error in errors:
                hint = self._plates_field_hint_labels.get(error.field_id)
                if hint is not None:
                    hint.configure(text=t('plates.validation.blocked', field_label=error.field_id,
                                           reason=error.reason, format_hint=t(error.format_hint_key)
                                           if _has_string(error.format_hint_key) else error.format_hint_key))
                    hint.pack(fill='x', pady=(0, 4))

    # -- Live preview ----------------------------------------------------------

    def _schedule_plates_preview(self):
        """Debounced, not on every raw keystroke -- see module docstring for
        why this is safe to do live now (it wasn't with the earlier
        pixel-traced/font-fitting pipeline)."""
        if self._plates_template is None:
            return
        self._debounce('plates_preview', _PREVIEW_DEBOUNCE_MS, self._render_plates_preview)

    def _render_plates_preview(self):
        template = self._plates_template
        instance = self._current_plate_instance()
        if template is None or instance is None:
            return

        # Real letterforms in preview: this repo has no local mesh data for
        # FH6's native fonts (still true), but KFPS -- a separate sibling
        # app -- ships a per-glyph raster alongside its own vertex mesh for
        # exactly this purpose (Resources/Vinyls/{family}/{index}.png).
        # file_preview.kfps_vinyls_dir locates that folder from the
        # Settings-configured KFPS.exe path; render_composed_preview draws
        # the real raster when it's found, falling back to the plain box
        # (same as before) when KFPS isn't configured or that folder is
        # missing -- see _handle_plates_preview_ready for the caveat shown
        # in that fallback case.
        vinyls_dir = file_preview.kfps_vinyls_dir(self.kfps_executable_var.get())

        # The canvas fills its column (`fill='both', expand=True`), so it's
        # usually already wider/taller than PLATES_PREVIEW_SIZE by the time
        # a template is selected -- render at its *actual* current size so
        # the plate fills the panel instead of sitting in one corner with a
        # dead zone around it (spec: preview should expand to fill
        # available space). winfo_width()/height() must be read here, on
        # the main thread, before the worker starts -- unsafe from a
        # background thread. Falls back to the configured default before
        # the canvas has been mapped/sized at least once.
        width = self.plates_canvas.winfo_width()
        height = self.plates_canvas.winfo_height()
        size = (width, height) if width > 1 and height > 1 else PLATES_PREVIEW_SIZE

        self.plates_shape_count_var.set(t('plates.preview.rendering'))

        def work():
            try:
                shapes, _root, warnings = render_plate(template, instance)
                p = gui_theme.palette()
                image = file_preview.render_composed_preview(shapes, size,
                                                               bg=p['canvas_bg'], fg=p['fg'],
                                                               vinyls_dir=vinyls_dir)
                self.msg_queue.put(('plates_preview_ready', image, len(shapes), warnings))
            except Exception as exc:  # noqa: BLE001 -- surfaced to the user, not swallowed
                self.msg_queue.put(('plates_preview_failed', str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _handle_plates_preview_ready(self, image, count, warnings):
        self._plates_photo = ImageTk.PhotoImage(image)
        self.plates_canvas.delete('all')
        self.plates_canvas.create_image(0, 0, anchor='nw', image=self._plates_photo)
        self._plates_last_preview_size = image.size

        if count > PLATE_SHAPE_WARN_THRESHOLD:
            status = t('plates.preview.shape_count_warning', count=count, threshold=PLATE_SHAPE_WARN_THRESHOLD)
        else:
            status = t('plates.preview.shape_count', count=count)
        if self.plates_placeholder_font_var.get() and \
                file_preview.kfps_vinyls_dir(self.kfps_executable_var.get()) is None:
            status += '  ' + t('plates.preview.font_not_shown')
        self.plates_shape_count_var.set(status)
        self.plates_generate_status_var.set(' / '.join(warnings) if warnings else '')

    def _handle_plates_preview_failed(self, error):
        self.plates_shape_count_var.set(t('plates.preview.not_yet_rendered'))
        self.plates_generate_status_var.set(t('plates.generate.failed', error=error))

    # -- Generate ------------------------------------------------------------

    def _generate_plate(self):
        """Renders exactly once, on a background thread. The size-check
        confirmation, if needed, happens after the render completes, back
        on the main thread (a Tk dialog can't be shown from a worker
        thread); actually writing the files only happens once the user has
        had a chance to cancel."""
        template = self._plates_template
        instance = self._current_plate_instance()
        if template is None or instance is None:
            return

        if not is_valid_for_generation(template, instance):
            self.plates_generate_status_var.set(t('plates.generate.blocked'))
            return

        out_dir = _PLATES_OUTPUT_DIR

        self.plates_generate_btn.configure(state='disabled')
        self.plates_generate_status_var.set(t('plates.preview.rendering'))

        def work():
            try:
                shapes, root, warnings = render_plate(template, instance)
                self.msg_queue.put(('plates_render_for_generate', template, shapes, root, warnings, out_dir))
            except Exception as exc:  # noqa: BLE001 -- surfaced to the user, not swallowed
                self.msg_queue.put(('plates_failed', str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _handle_plates_render_for_generate(self, template, shapes, root, warnings, out_dir):
        self.plates_generate_btn.configure(state='normal')
        if len(shapes) > PLATE_SHAPE_WARN_THRESHOLD:
            proceed = messagebox.askokcancel(
                t('plates.generate.button'),
                t('plates.generate.confirm_large', count=len(shapes), threshold=PLATE_SHAPE_WARN_THRESHOLD),
                parent=self.root,
            )
            if not proceed:
                self.plates_generate_status_var.set('')
                return
        self._write_plate_files(template, shapes, root, out_dir)

    def _write_plate_files(self, template, shapes, root, out_dir):
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            json_path = out_dir / f'{template.template_id}.json'
            from forza_writer.export import save as save_json
            data = plate_to_json(shapes)
            data['plate_groups'] = _group_tree_to_dict(root)
            save_json(data, json_path)

            fabric_path = out_dir / f'{template.template_id}.fabric-project.json'
            project = to_fabric_project(shapes, template.template_id, groups=root.to_group_tuples())
            save_fabric_project(project, fabric_path)

            self._handle_plates_done(len(shapes), json_path)
        except Exception as exc:  # noqa: BLE001 -- surfaced to the user, not swallowed
            self._handle_plates_failed(str(exc))

    def _handle_plates_done(self, count, path):
        self.plates_generate_status_var.set(t('plates.generate.done', count=count, path=path))
        self._plates_last_generated_json = path
        self.plates_send_kfps_btn.configure(state='normal')

    def _handle_plates_failed(self, error):
        self.plates_generate_status_var.set(t('plates.generate.failed', error=error))

    def _send_plate_to_kfps(self):
        """Launches KFPS.exe with the last-generated plate's geometry .json
        -- the same file format/argument load_geometry() in KFPS's own
        main.py already expects (confirmed by reading it: `geometry_path`,
        a positional .json argument). Never auto-launches after Generate --
        this is its own explicit action, since sending a file to an
        external program (and, per KFPS's own behavior, potentially
        live-injecting it into a running game) shouldn't happen as a side
        effect of something else."""
        json_path = self._plates_last_generated_json
        if json_path is None or not json_path.exists():
            self.plates_generate_status_var.set(t('plates.generate.kfps_nothing_generated'))
            return
        kfps_path = self.kfps_executable_var.get().strip() if hasattr(self, 'kfps_executable_var') else ''
        if not kfps_path:
            self.plates_generate_status_var.set(t('plates.generate.kfps_not_configured'))
            return
        try:
            subprocess.Popen([kfps_path, str(json_path)])
            self.plates_generate_status_var.set(t('plates.generate.kfps_sent', path=json_path))
        except OSError as exc:
            self.plates_generate_status_var.set(t('plates.generate.kfps_failed', error=str(exc)))

    # -- Saved configs (compact menu near the header) --------------------------

    def _refresh_plates_config_menu(self):
        menu = self.plates_config_menu
        menu.delete(0, 'end')
        menu.add_command(label=t('plates.config.save_button'), command=self._save_plate_config)
        names = plate_config_store.list_plate_configs()
        menu.add_separator()
        if not names:
            menu.add_command(label=t('plates.config.empty_menu'), state='disabled')
        for name in names:
            submenu = tk.Menu(menu, tearoff=False)
            submenu.add_command(label=name, command=lambda n=name: self._load_plate_config(n))
            submenu.add_command(label=t('plates.config.delete_button', name=name),
                                 command=lambda n=name: self._delete_plate_config(n))
            menu.add_cascade(label=name, menu=submenu)

    def _save_plate_config(self):
        instance = self._current_plate_instance()
        if instance is None:
            return
        name = simpledialog.askstring(t('plates.config.save_button'), t('plates.config.name_prompt'),
                                       parent=self.root)
        if not name:
            return
        plate_config_store.save_plate_config(name, instance)
        self._refresh_plates_config_menu()

    def _load_plate_config(self, name: str):
        instance = plate_config_store.load_plate_config(name)
        if instance is None:
            messagebox.showinfo(t('plates.config.menu_button'), t('plates.config.none_saved'), parent=self.root)
            return
        matching = next((tpl for tpl in list_templates() if tpl.template_id == instance.template_id), None)
        if matching is None:
            return
        # _plates_jump_to_template itself never pushes history (it's also a
        # bare teleport-helper for tests) -- without this, loading a saved
        # config left Back with nothing to retrace to, so the button came
        # up permanently disabled the moment a plate was reached this way,
        # not just visually inert like the single-template bug above.
        self._plates_push_history()
        self._plates_jump_to_template(matching.template_id)
        self.plates_mode_var.set(instance.mode)
        self._on_plates_mode_changed()
        chosen_font = instance.placeholder_font or 0
        self.plates_placeholder_font_var.set(chosen_font)
        self.plates_placeholder_font_combo.current(_PLACEHOLDER_FONT_CHOICES.index(chosen_font))
        for field_id, value in instance.field_values.items():
            var = self._plates_field_vars.get(field_id)
            if var is not None:
                var.set(value)
        self._update_plates_validation_hints()
        self._schedule_plates_preview()

    def _delete_plate_config(self, name: str):
        if name and plate_config_store.delete_plate_config(name):
            self._refresh_plates_config_menu()

    def _plates_jump_to_template(self, template_id: str) -> bool:
        """Sets the library/breadcrumb/search so `template_id` is the
        active leaf selection, regardless of where the browser currently
        is -- used by saved-config loading (and handy for tests) so the
        caller never needs to replay browser clicks by hand."""
        template = self._plates_by_id.get(template_id) or next(
            (tpl for tpl in list_templates() if tpl.template_id == template_id), None)
        if template is None:
            return False
        library = _plate_library(template)
        levels = _GROUP_LEVELS.get(library, ())
        breadcrumb = [(idx, level_fn(template)[0]) for idx, level_fn in enumerate(levels)]

        self._plates_library = library
        self._plates_breadcrumb = breadcrumb
        self.plates_search_var.set('')
        self._refresh_plates_library_buttons()
        self._refresh_plates_browser()
        if self.plates_template_tree.exists(template_id):
            self.plates_template_tree.selection_set(template_id)
            self.plates_template_tree.see(template_id)
        self._select_plates_template(template)
        return True


def _has_string(key: str) -> bool:
    try:
        t(key)
        return True
    except KeyError:
        return False


def _format_plate_details(template: PlateTemplate) -> str:
    library = _plate_library(template)
    lines = [_template_display_name(template), '']

    country_key = 'plates.details.field.country.fictional' if library == LIBRARY_FICTIONAL \
        else 'plates.details.field.country.real'
    jurisdiction_key = 'plates.details.field.jurisdiction.fictional' if library == LIBRARY_FICTIONAL \
        else 'plates.details.field.jurisdiction.real'

    if library != LIBRARY_CUSTOM:
        lines.append(f"{t(country_key)}: {_country_display_name(template.country)}")
        if template.jurisdiction:
            lines.append(f"{t(jurisdiction_key)}: {template.jurisdiction}")
        lines.append(f"{t('plates.details.field.era')}: {template.era}")
        lines.append(f"{t('plates.details.field.plate_type')}: {_category_display_name(template.plate_type)}")
    lines.append(f"{t('plates.details.field.dimensions')}: {template.width_mm:g}mm x {template.height_mm:g}mm")
    lines.append(f"{t('plates.details.field.accuracy')}: {template.accuracy_status.value}")

    prov = template.provenance
    if prov.contributors:
        lines.append(f"{t('plates.details.field.contributors')}: {', '.join(prov.contributors)}")
    if prov.reconstruction_author:
        lines.append(f"{t('plates.details.field.reconstruction_author')}: {prov.reconstruction_author}")
    if prov.year_documented:
        lines.append(f"{t('plates.details.field.year_documented')}: {prov.year_documented}")
    if prov.reference_urls:
        lines.append(f"{t('plates.details.field.sources')}:")
        lines.extend(f"  {url}" for url in prov.reference_urls)
    lines.append('')
    lines.append(f"{t('plates.details.field.notes')}: {prov.source_notes}")
    return '\n'.join(lines)


def _group_tree_to_dict(node) -> dict:
    return {
        'node_id': node.node_id,
        'kind': node.kind.value,
        'name_key': node.name_key,
        'shape_indices': list(node.shape_indices),
        'editable': node.editable,
        'deletable': node.deletable,
        'children': [_group_tree_to_dict(child) for child in node.children],
    }
