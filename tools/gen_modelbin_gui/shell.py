"""Window chrome shared by every tab: sidebar/tab switching, the scrollable page
shell, the Log panel, and generation/batch orchestration (start/halt/abort, the
worker-thread message queue). Used from more than one tab, so it lives here
rather than under any single tabs/ module.
"""

import colorsys
import json
import queue
import re
import string
import sys
import gen_modelbin_gui
import threading
import unicodedata
import webbrowser
import winreg
import ctypes
from pathlib import Path

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageTk

# gen_fontpack.py lives in tools/, alongside this package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gen_fontpack import (  # noqa: E402
    OUTPUT_MODES,
    build_fontpack,
    glyph_filename,
    pack_dir_for,
    sanitize_prefix,
)
from gen_fabric_project import build_fabric_project, save_project  # noqa: E402
import file_preview  # noqa: E402
import font_preview  # noqa: E402
import glyph_reference_preview  # noqa: E402
import gui_settings  # noqa: E402
import gui_theme  # noqa: E402
import glyph_overrides as glyph_overrides_store  # noqa: E402
import generated_data_cleanup  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from forza_writer import alphabets  # noqa: E402
from forza_writer.charset import CATEGORY_ORDER, charset_from_font, is_han_char  # noqa: E402
from forza_writer.font_info import FontInfo, GlyphInfo  # noqa: E402
from forza_writer.export import save as save_composed_json, to_json as composed_to_json  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.direct_generate import generate_direct  # noqa: E402
from forza_writer.primitive_fit import (  # noqa: E402
    DEFAULT_RESOLUTION, fit_glyph_with_strategy, inspect_glyph_geometry, placements_to_shapes,
    preview_glyph_mask_options)
from forza_writer import image_debug  # noqa: E402
from forza_writer import script_detect  # noqa: E402
from forza_writer.text_compose import ALIGNMENTS, compose_text  # noqa: E402
from forza_writer.text_style import FILL_MODES, LineFill, TextStyle  # noqa: E402
from forza_writer.forza_colors import describe_color, forza_hsb_to_rgb, hex_to_rgb, rgb_to_forza_hsb  # noqa: E402
from forza_writer import manufacturer_colors  # noqa: E402
from forza_writer.variable_fonts import (  # noqa: E402
    VariableFontInfo, inspect_variable_font, instantiate_font, variation_slug)

from .state import (  # noqa: E402
    FONT_EXTENSIONS, FONTS_DIR_SYSTEM, GLYPH_CATEGORY_TILE_CAP, GLYPH_GRID_HEIGHT,
    GLYPH_PREVIEW_SIZE, GLYPH_TILE_GAP, GLYPH_TILE_SIZE, GRID_MAX_TILES, GRID_TILE_GAP, GRID_TILE_SIZE,
    ICON_PATH, LIVE_PREVIEW_SIZE, COMPOSE_PREVIEW_SIZE, OUTPUT_MODE_LABELS, PREVIEW_SIZE,
    SIDEBAR_WIDTH, TABS, TAB_LABELS, _MODE_LABELS, direct_output_filename,
    enumerate_installed_fonts, is_running_as_administrator, sidebar_tab_text)
from .i18n import t


class ShellMixin:
    _PAGE_SCROLL_INCREMENT = 8
    _WHEEL_PIXELS_PER_NOTCH = 48
    _WHEEL_FRAME_MS = 16
    # Below this window height, the Log shrinks from a comfortable 8 lines
    # to a compact 4. At the smaller end of the app's supported window
    # sizes (e.g. 1280x720 and below), 8 fixed lines of chrome was eating a
    # disproportionate share of vertical space (nearly a quarter of the
    # window at the 860x640 minimum) at the expense of the primary tab
    # content. Two states, not a continuous scale: matches the "Compact/
    # Normal/Wide" philosophy the rest of the resize behavior follows.
    _LOG_COMPACT_HEIGHT_THRESHOLD = 760
    _LOG_LINES_NORMAL = 8
    _LOG_LINES_COMPACT = 4
    _LOG_HEIGHT_DEBOUNCE_MS = 120

    _DEFAULT_WINDOW_GEOMETRY = '1000x780'

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(t('shell.window.title'))
        # Loaded here, ahead of everywhere else that used to load it, so the
        # saved window geometry/maximized state (see _apply_startup_window_
        # geometry) is available before the window's very first geometry
        # call -- setting a fixed size and then immediately overriding it
        # would flash the old hard-coded default for one frame.
        self.settings = gui_settings.load_settings()
        root.minsize(860, 640)
        self._last_normal_geometry: str | None = None
        self._apply_startup_window_geometry()
        root.protocol('WM_DELETE_WINDOW', self._on_close)
        # Window/taskbar/title-bar icon (tools/build_icon.py generates it).
        # Cosmetic, so a missing file or a non-Windows Tk build (iconbitmap
        # expects .ico only on Windows) must never block the app starting.
        # `default=` alone sets what *future* Toplevels inherit but doesn't
        # reliably apply to this window itself (confirmed via WM_GETICON:
        # it read back 0 with only `default=` set). The plain positional
        # call is what actually sets this window's own icon.
        try:
            root.iconbitmap(str(ICON_PATH))
            root.iconbitmap(default=str(ICON_PATH))
        except Exception:
            pass

        # Scanned automatically at startup (see the end of __init__) so the
        # font list is populated without the user having to ask for it;
        # "Rescan Fonts" re-runs the same scan on demand (e.g. after
        # installing a new font without restarting), and "Browse on
        # machine" skips the installed-font list entirely.
        self.fonts: dict[str, Path] = {}
        self._font_scan_generation = 0
        self._font_scripts: dict[str, set[str]] = {}
        self.selected_font: Path | None = None
        self.worker: threading.Thread | None = None
        self.msg_queue: queue.Queue = queue.Queue()
        self.prefix_edited = False
        self.font_view_var = tk.StringVar(value='list')
        self._grid_generation = 0
        self._grid_tile_refs: list = []
        # Responsive column count for the font grid. Recomputed from the
        # grid canvas's real width (see _grid_columns_for_width) rather
        # than fixed, so it fills whatever width the window actually has
        # instead of leaving a hard-coded number of columns stranded on
        # the left with empty space beside them. 1 here is just a safe
        # placeholder until the canvas has real layout.
        self._grid_columns = 1
        self._preview_photo = None  # keep a reference or Tk garbage-collects it
        self._live_preview_photo = None
        self._compose_photo = None
        self._composed_shapes: list[dict] = []
        self._direct_photo = None
        self._direct_shapes: list[dict] = []
        self._direct_payload: dict | None = None
        self._direct_suggested_name = 'direct.json'
        self._direct_preview_signature: tuple | None = None
        self._stop_requested = threading.Event()
        self._abort_requested = False
        self._live_glyph_count = 0
        self._current_tab = 'generator'
        # Per-glyph overrides for Generator's selected font. Sparse: only
        # non-"auto" entries,
        # each `{"mode": "force"/"never"/"manual", "file"?: str}` (see
        # glyph_overrides.py). Loaded when the recessed workspace scans and
        # re-saved on every edit. Generation reloads from disk so the saved
        # state remains authoritative even when the workspace is closed.
        self._configurator_overrides: dict[str, dict] = {}
        self._configurator_scan_cache: dict[str, dict] = {}
        self._configurator_scan_generation = 0
        self._configurator_detail_generation = 0
        self._configurator_fit_cache: dict[tuple, dict] = {}
        self._configurator_fit_lock = threading.Lock()
        self._cleanup_size_generation = 0
        self._configurator_selected_char: str | None = None
        self._configurator_preview_photo = None
        self._configurator_font: Path | None = None
        self._advanced_font: Path | None = None
        self._advanced_info = VariableFontInfo((), ())
        self._advanced_axis_vars: dict[str, tk.DoubleVar] = {}
        self._advanced_instance_coordinates: dict[str, dict[str, float]] = {}
        self._advanced_preview_generation = 0
        self._advanced_preview_photo = None
        # Glyph Inspector: its own font selection (independent of every
        # other tab's, same convention as Configurator/Advanced/Direct
        # above) plus the loaded FontInfo it's currently browsing.
        # _glyph_inspector_ordered_glyphs is the flat, category-then-
        # codepoint-ordered list of whatever the search box currently
        # matches. Left/Right glyph navigation walks this list, and it's
        # rebuilt each time the grid repopulates rather than re-derived on
        # every keypress.
        self._glyph_inspector_font: Path | None = None
        self._glyph_inspector_font_info: FontInfo | None = None
        self._glyph_inspector_load_generation = 0
        self._glyph_inspector_grid_generation = 0
        self._glyph_inspector_selected_glyph: GlyphInfo | None = None
        self._glyph_inspector_ordered_glyphs: list[GlyphInfo] = []
        self._glyph_inspector_tile_photos: dict[str, "ImageTk.PhotoImage"] = {}
        self._glyph_inspector_tile_widgets: dict[str, tk.Widget] = {}
        self._glyph_inspector_category_inner: dict[str, ttk.Frame] = {}
        self._glyph_inspector_category_columns: dict[str, int] = {}
        self._glyph_inspector_category_shown: dict[str, int] = {}  # category -> tile count currently rendered
        self._glyph_inspector_preview_photo = None
        self._glyph_inspector_layout_wide = None
        # Phase 2/3: Generated (run the real fit pipeline) and Compare
        # (diff Generated against either the font's own outline or a
        # hand-loaded single-glyph shape file, same {"shapes": [...]}
        # format Configurator's manual overrides already use). Generated
        # results are cached per (font, char, compute backend) exactly like
        # Configurator's _configurator_fit_cache, since re-fitting on every
        # Left/Right navigation keypress would be wasteful. Hand-made
        # comparison files are session-only (char -> shapes), never
        # persisted. The user reloads them if they restart the app.
        self._glyph_inspector_generated_cache: dict[tuple, dict] = {}
        self._glyph_inspector_generate_generation = 0
        self._glyph_inspector_compare_target_var = tk.StringVar(value='font')
        self._glyph_inspector_handmade_shapes: dict[str, list] = {}
        self._glyph_inspector_handmade_path: dict[str, str] = {}
        # Every widget that scrolls itself (a Listbox/Text/Canvas with its
        # own Scrollbar) registers here via _register_independent_scroll()
        # at construction time, so _on_mousewheel can route the wheel to
        # it instead of fighting it with the enclosing page's own scroll.
        # A set that grows with each new scrollable widget, instead of a
        # hand-maintained exclusion list that's easy to forget to update
        # (exactly how the font list ended up double-scrolling with the
        # page canvas behind it before this was introduced).
        self._independent_scroll_widgets: set = set()
        self._wheel_pending_pixels = 0.0
        self._wheel_after_id = None
        self._wheel_canvas = None
        self._debounce_after_ids: dict[str, str] = {}

        # Loaded once at startup; Settings' Save button persists whatever's
        # in self.out_var/self.direct_out_var/self.ref_var back to disk.
        # Every other tab reads these same StringVars rather than a private
        # copy, so a change on Settings (even before Save) is immediately
        # visible everywhere. out_var is the base for fontpacks (Generator
        # and Advanced both build_fontpack() into it); direct_out_var is
        # Direct Generation's own save location, kept separate since a
        # Direct save is a single standalone JSON file, not a fontpack.
        # (self.settings itself was already loaded at the top of __init__,
        # ahead of the window-geometry restore.)
        self.out_var = tk.StringVar(value=self.settings['output_dir'])
        self.modelbin_out_var = tk.StringVar(value=self.settings['modelbin_output_dir'])
        self.direct_out_var = tk.StringVar(value=self.settings['direct_output_dir'])
        self.image_out_var = tk.StringVar(value=self.settings['image_output_dir'])
        self.image_save_source_var = tk.BooleanVar(value=self.settings['image_save_source'])
        self.image_save_debug_var = tk.BooleanVar(value=self.settings['image_save_debug'])
        # Holds the human label; `image_debug_mode()` converts back to the
        # stored key so the settings file keeps a stable identifier rather
        # than display text that could be reworded later.
        self.image_debug_mode_var = tk.StringVar(
            value=image_debug.DEBUG_LABELS.get(
                self.settings['image_debug_mode'], image_debug.DEBUG_LABELS['combined']))
        self.ref_var = tk.StringVar(value=self.settings['reference_modelbin'])
        self.kfps_executable_var = tk.StringVar(value=self.settings['kfps_executable'])
        self.palette_var = tk.StringVar(value=self.settings['palette'])
        self.density_var = tk.StringVar(value=self.settings['density'])
        self.compute_backend_var = tk.StringVar(value=self.settings['compute_backend'])
        self.compute_backend_status_var = tk.StringVar(value='Detecting available processor…')
        gui_theme.configure(self.palette_var.get(), self.density_var.get())

        self.style = ttk.Style(root)
        self._build_widgets()
        self._log_startup_elevation_notice()
        self._refresh_font_list()
        self._update_preview()
        self._update_settings_status()
        self._detect_compute_backend()
        self._apply_theme()
        gui_theme.bind_context_menus(self.root)
        self._poll_queue_after_id = root.after(100, self._poll_queue)
        self._load_all_fonts()
    def _apply_theme(self):
        widgets = [self.font_list, self.grid_canvas, self.log, self.preview_canvas,
                   self.live_preview_canvas, self.configurator_preview_canvas,
                   self.advanced_preview_canvas,
                   self.direct_text_widget, self.direct_canvas,
                   self.ascii_text_widget, self.ascii_canvas,
                   self.compose_text_widget, self.compose_canvas, self.outputs_pack_listbox,
                   self.outputs_glyph_listbox, self.sidebar,
                   self.glyph_inspector_grid_canvas, self.glyph_inspector_preview_canvas,
                   self.forza_text_widget, self.forza_text_canvas,
                   self.layer_effects_preview_canvas]
        # Every ColorPickerWidget's own SB-square/hue-strip canvases are
        # deliberately excluded. They're private to that widget, not GUI
        # attributes, and it always fully repaints them with a gradient
        # create_image() before they're ever visible, so a themed bg
        # wouldn't actually show anyway.
        widgets.extend(self._scroll_canvases)
        gui_theme.apply_theme(self.root, self.style, tk_widgets=[w for w in widgets if w is not None])
        gui_theme.configure_text_tags(self.log)
        self._style_sidebar()
        self._style_script_tabs()
        # Tiles bake palette colours into a bitmap, so they need
        # repainting rather than restyling.
        if hasattr(self, '_redraw_shape_tiles'):
            self._redraw_shape_tiles()
    def _build_scroll_shell(self, parent, tab_name: str):
        """The one primary vertical scroll region for a tab page. Every
        `_build_*_page()` wraps its content in this, so there's exactly
        one owner of page-level scrolling per tab, consistently, rather
        than some tabs scrolling and others silently clipping content
        that doesn't fit (which is what happened before every page used
        this). Registered under `tab_name` for `_on_mousewheel` routing;
        the scrollbar itself auto-hides when a page's content already
        fits (see gui_theme.AutoHideScrollbar) so a short tab like
        Settings never shows a permanently-empty, do-nothing scrollbar.

        Independently-scrollable regions nested inside a page (the font
        list, the font grid, Outputs' pack/glyph lists) are the
        exception, not the rule. Each registers itself via
        `_register_independent_scroll()` so the wheel routes to whichever
        one the pointer is actually over instead of also dragging this
        outer canvas along with it.
        """
        canvas = tk.Canvas(
            parent, highlightthickness=0,
            yscrollincrement=self._PAGE_SCROLL_INCREMENT)
        scroll = gui_theme.AutoHideScrollbar(parent, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True, padx=(0, gui_theme.SCROLLBAR_GUTTER))

        content = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda _e, c=canvas: c.configure(scrollregion=c.bbox('all')))
        canvas.bind(
            '<Configure>',
            lambda e, c=canvas, w=window, body=content:
                self._on_page_canvas_configure(c, w, body, e.width))
        self._scroll_canvases.append(canvas)
        self._page_scroll_canvas[tab_name] = canvas
        self._page_scroll_content[tab_name] = content
        return content
    def _on_page_canvas_configure(self, canvas, window, content, width: int) -> None:
        canvas.itemconfigure(window, width=width)
        # Semantic wrap tiers are maximums, not minimum width requests. At a
        # narrow window, cap every wrapped label to the room its immediate
        # parent actually gives it; restore the tier automatically when the
        # window grows again.
        self.root.after_idle(lambda: self._sync_wrapped_labels(content))
    def _sync_wrapped_labels(self, parent) -> None:
        page_available = max(120, parent.winfo_width() - 48)
        stack = [parent]
        while stack:
            container = stack.pop()
            for widget in container.winfo_children():
                stack.append(widget)
                if not isinstance(widget, ttk.Label):
                    continue
                try:
                    configured = int(widget.cget('wraplength'))
                except (tk.TclError, TypeError, ValueError):
                    continue
                maximum = getattr(widget, '_forza_wrap_maximum', configured)
                if maximum <= 0:
                    continue
                widget._forza_wrap_maximum = maximum
                available = max(120, widget.master.winfo_width() - widget.winfo_x() - 8)
                desired = min(maximum, available, page_available)
                if configured != desired:
                    widget.configure(wraplength=desired)
    def _register_independent_scroll(self, widget) -> None:
        """Mark `widget` as owning its own scrolling. _on_mousewheel
        will route the wheel to it (its own native Listbox/Text/Canvas
        wheel handling) rather than also scrolling the enclosing page's
        outer canvas at the same time."""
        self._independent_scroll_widgets.add(widget)
    def _widget_or_ancestor_is_independent_scroll(self, widget) -> bool:
        parent = widget
        while parent is not None:
            if parent in self._independent_scroll_widgets:
                return True
            parent = getattr(parent, 'master', None)
        return False
    def _on_mousewheel(self, event):
        # Route the wheel to whichever independently-scrollable widget
        # (if any) the pointer is actually over: the font list, the font
        # grid, the Log, Outputs' pack/glyph lists, the compose text box,
        # rather than also scrolling the enclosing page underneath it.
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        if self._widget_or_ancestor_is_independent_scroll(widget):
            return
        canvas = self._page_scroll_canvas.get(self._current_tab)
        if canvas is None or not event.delta:
            return
        if self._wheel_canvas is not canvas:
            if self._wheel_after_id is not None:
                self.root.after_cancel(self._wheel_after_id)
            self._wheel_canvas = canvas
            self._wheel_pending_pixels = 0.0
            self._wheel_after_id = None
        # Windows reports 120 for a conventional wheel notch, but precision
        # touchpads and high-resolution wheels can send smaller deltas. Keep
        # the fraction rather than truncating it to zero, and combine a burst
        # of events into one canvas move per display frame. This substantially
        # reduces the number of full embedded-widget repaints Tk asks Windows
        # to perform during a fast scroll.
        self._wheel_pending_pixels += (
            -event.delta / 120.0 * self._WHEEL_PIXELS_PER_NOTCH)
        if self._wheel_after_id is None:
            self._wheel_after_id = self.root.after(
                self._WHEEL_FRAME_MS, self._flush_page_scroll)

    def _flush_page_scroll(self):
        self._wheel_after_id = None
        canvas = self._wheel_canvas
        if canvas is None:
            return
        steps = int(self._wheel_pending_pixels / self._PAGE_SCROLL_INCREMENT)
        if not steps:
            return
        self._wheel_pending_pixels -= steps * self._PAGE_SCROLL_INCREMENT
        canvas.yview_scroll(steps, 'units')
    def _on_page_key(self, event):
        # Page Up/Down for the current tab's primary scroll canvas. A
        # Canvas-based scroll region doesn't get this for free the way a
        # native scrollable pane would. Routed by keyboard *focus*, not
        # mouse position (unlike the wheel), since that's what Page Up/
        # Down naturally follows. Home/End are deliberately not bound
        # here: Entry/Text widgets already use Home/End to jump the
        # text cursor to the start/end
        # of the field, and rebinding them at the root level would fire
        # *both* handlers on every Home/End press while typing, which is
        # a worse regression than not adding page-level Home/End support.
        focused = self.root.focus_get()
        if focused is not None and self._widget_or_ancestor_is_independent_scroll(focused):
            return
        canvas = self._page_scroll_canvas.get(self._current_tab)
        if canvas is None:
            return
        if event.keysym == 'Prior':
            canvas.yview_scroll(-1, 'pages')
        elif event.keysym == 'Next':
            canvas.yview_scroll(1, 'pages')
    def _build_sidebar(self, parent):
        p = gui_theme.palette()
        self.sidebar = tk.Frame(parent, width=SIDEBAR_WIDTH, bg=p['bg'])
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        # A hairline divider between the sidebar (chrome, darkest tier) and
        # the workspace (panel_alt, one tier lifted). `sash`, one of the
        # palette's previously-unused tokens, finally gets a job.
        self.sidebar_divider = tk.Frame(parent, width=1, bg=p['sash'])
        self.sidebar_divider.pack(side='left', fill='y')

        # Each nav row is a composite: a slim left-edge indicator strip
        # (invisible unless the tab is active) + the label itself. The
        # "restrained accent for the active state" cue lives in that
        # strip, not a full solid-orange fill across the whole row, which
        # would read as a button rather than nav chrome.
        self._tab_rows: dict[str, tk.Frame] = {}
        self._tab_indicators: dict[str, tk.Frame] = {}
        self._tab_labels: dict[str, tk.Label] = {}
        for name in TABS:
            row = tk.Frame(self.sidebar, bg=p['bg'])
            row.pack(fill='x')
            indicator = tk.Frame(row, width=3, bg=p['bg'])
            indicator.pack(side='left', fill='y')
            lbl = tk.Label(row, text=sidebar_tab_text(TAB_LABELS[name]), anchor='w',
                            justify='left', wraplength=SIDEBAR_WIDTH - 24,
                            padx=11, pady=13, bg=p['bg'], cursor='hand2')
            lbl.pack(side='left', fill='both', expand=True)
            for widget in (row, indicator, lbl):
                widget.bind('<Button-1>', lambda _e, n=name: self._show_tab(n))
                widget.bind('<Enter>', lambda _e, n=name: self._on_tab_hover(n, True))
                widget.bind('<Leave>', lambda _e, n=name: self._on_tab_hover(n, False))
            self._tab_rows[name] = row
            self._tab_indicators[name] = indicator
            self._tab_labels[name] = lbl

        # Leftover space below the nav rows. Rows above only pack
        # `fill='x'` (no `expand`), so the fixed-width sidebar always has
        # genuine blank bg-colored space here. It's the only place in this
        # layout a full-bleed backdrop can sit without competing with real
        # text, since ttk frames elsewhere are opaque. Themes without a
        # backdrop (gui_theme.backdrop_photo_image returns None) leave this
        # a plain bg-colored canvas.
        self.sidebar_backdrop = tk.Canvas(self.sidebar, bg=p['bg'], highlightthickness=0)
        self.sidebar_backdrop.pack(side='top', fill='both', expand=True)
        self._sidebar_backdrop_image = None
        self.sidebar_backdrop.bind('<Configure>', self._on_sidebar_backdrop_configure)
    def _on_tab_hover(self, name: str, entering: bool):
        if name == self._current_tab:
            return  # the active tab keeps its own look regardless of hover
        p = gui_theme.palette()
        solid_selected = gui_theme.SOLID_SELECTED_ROW.get(gui_theme.CURRENT_PALETTE, False)
        if solid_selected and entering:
            return  # a themed hover tint would compete with the eventual solid-accent selected look
        bg = p['frame_light'] if entering else p['bg']
        self._tab_rows[name].configure(bg=bg)
        self._tab_labels[name].configure(bg=bg)
    def _on_sidebar_backdrop_configure(self, event):
        # Bound on the canvas itself, not on root. A root-level <Configure>
        # binding fires for every descendant's own resize too and has
        # previously caused a real hang in this app, so this guard matters
        # even though the canvas is the only widget bound here today.
        if event.widget is not self.sidebar_backdrop:
            return
        self._refresh_sidebar_backdrop()
    def _refresh_sidebar_backdrop(self):
        canvas = getattr(self, 'sidebar_backdrop', None)
        if canvas is None:
            return
        p = gui_theme.palette()
        canvas.configure(bg=p['bg'])
        canvas.delete('backdrop')
        width, height = canvas.winfo_width(), canvas.winfo_height()
        image = gui_theme.backdrop_photo_image(width, height, canvas)
        self._sidebar_backdrop_image = image  # keep a reference or Tk garbage-collects it
        if image is not None:
            canvas.create_image(0, 0, anchor='nw', image=image, tags='backdrop')
    def _style_sidebar(self):
        p = gui_theme.palette()
        d = gui_theme.density()
        solid_selected = gui_theme.SOLID_SELECTED_ROW.get(gui_theme.CURRENT_PALETTE, False)
        self.sidebar.configure(bg=p['bg'])
        self.sidebar_divider.configure(bg=p['sash'])
        for name in TABS:
            selected = name == self._current_tab
            if selected and solid_selected:
                row_bg, label_fg = p['accent'], p['select_fg']
            else:
                row_bg = p['panel_alt'] if selected else p['bg']
                label_fg = p['fg'] if selected else p['muted_fg']
            self._tab_rows[name].configure(bg=row_bg)
            self._tab_labels[name].configure(background=row_bg,
                                              foreground=label_fg,
                                              font=('Segoe UI Semibold', d['body']),
                                              padx=9 + d['body'] // 4, pady=3 + d['body'])
            self._tab_indicators[name].configure(bg=p['accent'] if selected else p['bg'])
        self._refresh_sidebar_backdrop()
    def _show_tab(self, name: str):
        self._current_tab = name
        for tab_name, page in self._pages.items():
            if tab_name == name:
                page.pack(fill='both', expand=True)
            else:
                page.pack_forget()
        self._style_sidebar()
        content = self._page_scroll_content.get(name)
        if content is not None:
            self.root.after_idle(lambda body=content: self._sync_wrapped_labels(body))
        if name == 'outputs':
            self._refresh_outputs_pack_list()
    def _build_widgets(self):
        self._scroll_canvases: list[tk.Canvas] = []
        self._page_scroll_canvas: dict[str, tk.Canvas] = {}
        self._page_scroll_content: dict[str, ttk.Frame] = {}
        self._pages: dict[str, ttk.Frame] = {}
        # Every bind_all() funcid created anywhere below (here and in
        # individual tab builders, e.g. glyph_inspector.py) gets appended
        # here so _on_root_destroy can free all of them -- see that
        # method's docstring for why this is necessary at all.
        self._global_bind_funcids: list[str] = []

        self._build_log_panel(self.root)  # side='bottom' first, reserves its space

        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(side='top', fill='both', expand=True)
        self._build_sidebar(self.main_frame)
        self.page_container = ttk.Frame(self.main_frame)
        self.page_container.pack(side='left', fill='both', expand=True)

        self._build_forza_font_text_page()
        self._build_generator_page()
        self._build_advanced_page()
        self._build_direct_page()
        self._build_ascii_art_page()
        self._build_glyph_inspector_page()
        self._build_layer_effects_page()
        self._build_outputs_page()
        self._build_composer_page()
        self._build_plates_page()
        self._build_settings_page()
        self._build_credits_page()

        # bind_all() registers its Tcl command through self.root._root() --
        # the real top-level Tk() interpreter, not this specific window --
        # against the interpreter-wide "all" bindtag. That command is a live
        # (GC-invisible, C-level) reference to this whole instance for as
        # long as the *interpreter* lives, regardless of this window's own
        # lifetime: window.destroy()'s _tclCommands cleanup can't reach it
        # (it was never registered through window), and unbind_all() doesn't
        # help either -- per Tkinter's own source, it clears the bound
        # script but only calls deletecommand() when a funcid is given,
        # which unbind_all() never does. Irrelevant for the app's real,
        # single, process-lifetime window, but fatal for anything that
        # builds many GeneratorGUI instances against one shared interpreter
        # (the test suite, deliberately, to dodge a separate Windows Tcl-init
        # flakiness -- see conftest.py's tk_root): each instance's bind_all
        # commands pile up forever, and eventually so do all the shapes/
        # previews/images they keep alive, exhausting Windows' GDI object
        # quota and crashing the interpreter. Capturing each funcid and
        # deleting it explicitly, on this window's own actual destruction
        # (not just window.destroy() having been called, since <Destroy>
        # also bubbles up from every descendant's own destruction), is the
        # only way to actually free them.
        self._global_bind_funcids.append(self.root.bind_all('<MouseWheel>', self._on_mousewheel))
        self._global_bind_funcids.append(self.root.bind_all('<Prior>', self._on_page_key))
        self._global_bind_funcids.append(self.root.bind_all('<Next>', self._on_page_key))
        self.root.bind('<Destroy>', self._on_root_destroy, add='+')
        self._show_tab('generator')

    def _on_root_destroy(self, event) -> None:
        if event.widget is not self.root:
            return
        interp_root = self.root._root()
        for funcid in self._global_bind_funcids:
            try:
                interp_root.deletecommand(funcid)
            except tk.TclError:
                pass
        try:
            self.root.after_cancel(self._poll_queue_after_id)
        except (tk.TclError, ValueError):
            pass
        # Same reasoning as _poll_queue_after_id above: any debounced
        # <Configure>-driven callback (log-height, per-tab resize
        # handlers, ...) still pending when this window is destroyed --
        # entirely possible, since resizing/collapsing widgets during
        # teardown itself fires <Configure> -- keeps this whole instance
        # alive for its wait, and then fires against already-destroyed
        # widgets, which is also where the "invalid command name" /
        # "application has been destroyed" bgerror noise was coming from.
        for after_id in self._debounce_after_ids.values():
            try:
                self.root.after_cancel(after_id)
            except (tk.TclError, ValueError):
                pass
        self._debounce_after_ids.clear()
        if self._wheel_after_id is not None:
            try:
                self.root.after_cancel(self._wheel_after_id)
            except (tk.TclError, ValueError):
                pass
            self._wheel_after_id = None
    def _build_log_panel(self, parent):
        # Chrome tier, not the workspace panel_alt tier: a console
        # readout, monospaced, the darkest thing on screen.
        log_frame = ttk.LabelFrame(parent, text=gui_theme.hud_label(t('shell.log.panel_title')),
                                    style='Chrome.TLabelframe')
        log_frame.pack(side='bottom', fill='x', padx=10, pady=(0, 10))

        # grid, not pack, for the classic 2D text+scrollbars layout: the
        # Text widget top-left, a vertical scrollbar to its right, a
        # horizontal one below it. pack can't express that cleanly.
        log_body = ttk.Frame(log_frame)
        log_body.pack(fill='both', expand=True, padx=6, pady=6)
        log_body.columnconfigure(0, weight=1)
        log_body.rowconfigure(0, weight=1)

        self.log = tk.Text(log_body, height=self._LOG_LINES_NORMAL, state='disabled', wrap='none',
                            font=('Consolas', 9), borderwidth=0, highlightthickness=0)
        self.log.grid(row=0, column=0, sticky='nsew')
        log_vscroll = gui_theme.AutoHideScrollbar(log_body, orient='vertical', command=self.log.yview)
        log_vscroll.grid(row=0, column=1, sticky='ns', padx=(gui_theme.SCROLLBAR_GUTTER, 0))
        # wrap='none' keeps each log line on one line (so e.g. a "--- Done:
        # ... -> C:\...\manifest.json ---" message doesn't word-wrap
        # mid-path), which means a long line needs a horizontal scrollbar
        # to actually be reachable, not silently clipped at the panel edge.
        log_hscroll = gui_theme.AutoHideScrollbar(log_body, orient='horizontal', command=self.log.xview)
        log_hscroll.grid(row=1, column=0, sticky='ew', pady=(gui_theme.SCROLLBAR_GUTTER, 0))
        self.log.configure(yscrollcommand=log_vscroll.set, xscrollcommand=log_hscroll.set)
        self._register_independent_scroll(self.log)

        self._log_compact = False
        self.root.bind('<Configure>', self._on_root_configure)

    def _on_root_configure(self, event) -> None:
        """Shrink the Log to a compact line count once the window gets
        short enough that 8 fixed lines of it would eat a disproportionate
        share of vertical space. See `_LOG_COMPACT_HEIGHT_THRESHOLD`.

        Every widget's default bindtags include its nearest toplevel's own
        path, so `self.root.bind('<Configure>', ...)`, a plain `.bind()`
        and not `.bind_all()`, fires for every *descendant* widget's own
        Configure events too, not just the window's: a single resize was
        observed to deliver 100+ events, most reporting some small child
        widget's own height (19px, 25px, ...), not the window's. Without
        this guard, whichever child happened to resize last decided
        `compact`, essentially at random, and reconfiguring the Log's
        height from directly inside a handler that fires that broadly fed
        back into Windows' own resize negotiation badly enough to hang the
        app for the whole duration of a `geometry()` call (reproduced
        directly: `window.update()` never returned).

        Debounced on top of the guard, not applied synchronously: even
        restricted to real window-Configure events, reacting immediately
        risked the same feedback pattern while the window manager was
        still settling the new size. Deferring past the current event
        lets that finish first, exactly like Composer's own resize
        handler already had to.
        """
        if event.widget is not self.root:
            return
        # Tracked continuously, not queried at close time: a maximized
        # window's own .geometry() reports the maximized rect, not the
        # size the user would actually want back on an un-maximize/restore
        # or on the next launch, and there's no cheap cross-platform way to
        # ask Windows for "what was the restored size" after the fact.
        # KFPS's own window-state persistence hits the identical problem
        # and solves it the same way: only record geometry while the
        # window is actually in its normal (not maximized/minimized) state.
        if self.root.state() == 'normal':
            self._last_normal_geometry = self.root.geometry()
        height = event.height
        self._debounce('log_height', self._LOG_HEIGHT_DEBOUNCE_MS,
                        lambda: self._apply_log_height(height))

    def _apply_log_height(self, window_height: int) -> None:
        compact = window_height < self._LOG_COMPACT_HEIGHT_THRESHOLD
        if compact == self._log_compact:
            return
        self._log_compact = compact
        self.log.configure(height=self._LOG_LINES_COMPACT if compact else self._LOG_LINES_NORMAL)

    # -- window geometry persistence --------------------------------------
    def _sanitize_saved_geometry(self, geometry: str) -> str:
        """Fall back to size-only (letting Windows place the window) if the
        saved position would land off the primary screen entirely -- e.g. a
        second monitor from last session that's no longer connected. Only a
        loose primary-monitor bound (winfo_screenwidth/height don't see
        other monitors), deliberately generous so a legitimate multi-
        monitor position isn't discarded; this exists to catch a window
        parked somewhere no longer real, not to second-guess a valid one.
        """
        match = re.match(r'^(\d+)x(\d+)([+-]\d+)([+-]\d+)$', geometry)
        if not match:
            return geometry
        width, height, x_str, y_str = match.groups()
        x, y = int(x_str), int(y_str)
        margin = 4000
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if -margin <= x <= screen_w + margin and -margin <= y <= screen_h + margin:
            return geometry
        return f'{width}x{height}'

    def _apply_startup_window_geometry(self) -> None:
        """Restore the window's size/position/maximized state from the last
        session, or use a comfortable default on a genuinely first run --
        the same save/restore pattern KFPS already uses (see app.py's
        remember_window_state), rather than a fixed startup size or a
        locked-in fullscreen mode. Resizing the window *is* the opt-out:
        nothing else to configure, and nothing that stops the window from
        being made small again whenever that's actually wanted.
        """
        geometry = self.settings.get('window_geometry') or ''
        if geometry:
            geometry = self._sanitize_saved_geometry(geometry)
        self.root.geometry(geometry or self._DEFAULT_WINDOW_GEOMETRY)
        if self.settings.get('window_maximized'):
            try:
                self.root.state('zoomed')  # Windows Tk's maximized state
            except tk.TclError:
                pass

    def _on_close(self) -> None:
        """Persist window state before the window actually closes. Reloads
        settings from disk rather than reusing self.settings (the snapshot
        from startup) so this can't silently revert anything the Settings
        tab itself saved mid-session."""
        try:
            current = gui_settings.load_settings()
            current['window_maximized'] = self.root.state() == 'zoomed'
            if self._last_normal_geometry:
                current['window_geometry'] = self._last_normal_geometry
            gui_settings.save_settings(current)
        except Exception:
            pass
        self.root.destroy()

    # -- shared text-box Clear/Select All row ----------------------------
    def _build_text_box_actions_row(self, parent, text_widget):
        """A right-aligned Clear + Select All button pair for a multi-line
        `tk.Text` box. Both delegate to gui_theme.clear_text()/select_all(),
        the same dispatch the right-click context menu's own Select All
        item uses, so there's one selection/clearing implementation, not
        two."""
        row = ttk.Frame(parent)
        select_all_btn = ttk.Button(row, text=t('shell.button.select_all'),
                                     command=lambda: gui_theme.select_all(text_widget))
        select_all_btn.pack(side='right')
        clear_btn = ttk.Button(row, text=t('shell.button.clear'),
                                command=lambda: gui_theme.clear_text(text_widget))
        clear_btn.pack(side='right', padx=(0, 4))
        return row, clear_btn, select_all_btn

    # -- shared sample-text control -------------------------------------
    def _build_sample_text_row(self, parent, target, default_script: str = 'Latin'):
        """A script picker + sample-option picker + Insert button that drops
        a sample text into `target`.

        Lives here rather than in any one tab because Direct, Composer and
        Advanced all want the same control, and the script list comes from
        `alphabets.PANGRAM_SCRIPTS` so adding a script's sample text needs no
        UI change at all. A script can offer several sample options (e.g.
        Hebrew's alphabet row vs. a real passage vs. a joke one). The second
        combobox lists whichever options `alphabets.pangrams_for()` returns
        for the currently-picked script, refreshed on every script change.

        `target` is either a `tk.Text` (Direct/Composer's multi-line boxes) or
        a `tk.StringVar` (Advanced's single-line preview field); the insert
        helper handles both.
        """
        row = ttk.Frame(parent)
        controls = ttk.Frame(row)
        controls.pack(fill='x')
        ttk.Label(controls, text=t('shell.label.sample_text')).pack(side='left')
        script_var = tk.StringVar(value=default_script)
        combo = ttk.Combobox(controls, textvariable=script_var, state='readonly',
                             width=20, values=list(alphabets.PANGRAM_SCRIPTS))
        combo.pack(side='left', padx=4)

        sample_var = tk.StringVar()
        sample_combo = ttk.Combobox(controls, textvariable=sample_var, state='readonly', width=34)
        sample_combo.pack(side='left', padx=4)

        def _refresh_sample_options(*_args):
            labels = [label for label, _text in alphabets.pangrams_for(script_var.get())]
            sample_combo['values'] = labels
            if labels and sample_var.get() not in labels:
                sample_var.set(labels[0])
            elif not labels:
                sample_var.set('')

        combo.bind('<<ComboboxSelected>>', _refresh_sample_options)
        _refresh_sample_options()

        ttk.Button(controls, text=t('shell.button.insert'),
                   command=lambda: self._insert_sample_text(target, script_var.get(), sample_var.get())
                   ).pack(side='left')
        ttk.Label(row, text=t('shell.hint.sample_text'),
                  style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                  justify='left').pack(fill='x', pady=(2, 0))
        return row, script_var

    def _insert_sample_text(self, target, script: str, label: str | None = None) -> None:
        """Insert `script`'s sample text (the option named `label`, or the
        first option if `label` doesn't match/isn't given) at the cursor,
        never replacing what's already typed.

        Inserting rather than overwriting is deliberate: it can't destroy text
        the user just entered, and inserting two scripts in a row is a genuinely
        useful way to check a font covers both.
        """
        options = alphabets.pangrams_for(script)
        if not options:
            self._log(t('shell.log.no_sample_text', script=script), tag='warn')
            return
        chosen_label, sample = next(((lbl, text) for lbl, text in options if lbl == label), options[0])
        if isinstance(target, tk.StringVar):
            target.set(sample)
        else:
            target.insert('insert', sample)
        self._log(t('shell.log.inserted_sample_text', script=script, label=chosen_label), tag='hint')

    # -- shared generation-method option row -----------------------------
    def _build_output_mode_option(self, parent, *, style: str, title: str, description: str,
                                   variable: tk.StringVar, value: str, command=None,
                                   warn_description: bool = False) -> ttk.Frame:
        """One generation-method radio option: the styled Radiobutton (its
        `style` carries that method's identity color, see
        `gui_theme.GENERATION_METHOD_STYLES`) plus its indented description
        line underneath.

        Generator and Advanced Generator's Output sections both built this
        exact row shape independently; centralizing it here is also what
        makes it easy for a page (Direct Generator) to actually pick up the
        same identity colors instead of falling back to a plain, unstyled
        Radiobutton for the same concepts.
        """
        option_frame = ttk.Frame(parent)
        option_frame.pack(fill='x', **gui_theme.ROW_PAD_TOP)
        ttk.Radiobutton(option_frame, text=title, style=style,
                         variable=variable, value=value, command=command).pack(anchor='w')
        ttk.Label(option_frame, text=description,
                  style='Warn.TLabel' if warn_description else 'Hint.TLabel',
                  wraplength=gui_theme.WRAP_MED, justify='left').pack(
                      anchor='w', padx=gui_theme.INDENT_PAD, pady=gui_theme.ROW_PAD_BOTTOM['pady'])
        return option_frame

    # -- shared responsive two-column layout -----------------------------
    def _bind_responsive_columns(self, parent, left: tk.Widget, right: tk.Widget, *,
                                  threshold: int, expand: str = 'left', left_padx=(0, 4),
                                  right_padx=(4, 0), stacked_pady=(8, 0),
                                  debounce_ms: int | None = None, state_attr: str | None = None):
        """Side-by-side above `threshold` px of `parent`'s width, stacked
        top/bottom below it. The shared shape behind Configurator's, Glyph
        Inspector's, and Composer's own column layouts, each of which
        previously reimplemented this identically (own threshold constant,
        own pack/pack_forget pair) with no shared code between them.

        `left`/`right` are already-built widgets (a plain Frame, a
        LabelFrame, whatever the page needs). This only owns *where* they
        go, not their contents. `expand` picks which side grows to fill
        spare width in wide mode (`fill='both', expand=True`) versus
        sitting at its own natural width (`fill='y'`); 'left' matches
        every caller before ASCII Art's large right-hand preview panel
        needed the opposite emphasis (a narrow fixed controls column, a
        preview that should actually use the room a maximized window
        gives it), so 'left' stays the default rather than becoming a
        required argument everywhere else. `debounce_ms` reproduces
        Composer's own resize debounce (a live window-drag fires many
        Configure events per second; reacting to every one flickers the
        layout mid-drag), and is None everywhere else, matching each
        page's prior behavior exactly. `state_attr`, if given, mirrors the
        current wide/narrow bool onto that attribute name on self, kept
        for `test_open_configurator_stacks_columns_at_minimum_width`'s
        direct read of `gui._configurator_layout_wide`.
        """
        state = {'wide': None}
        debounce_key = f'responsive_columns_{id(parent)}'

        def apply(wide: bool):
            if wide == state['wide']:
                return
            left.pack_forget()
            right.pack_forget()
            if wide:
                if expand == 'left':
                    left.pack(side='left', fill='both', expand=True, padx=left_padx)
                    right.pack(side='left', fill='y', padx=right_padx)
                else:
                    left.pack(side='left', fill='y', padx=left_padx)
                    right.pack(side='left', fill='both', expand=True, padx=right_padx)
            else:
                left.pack(side='top', fill='both', expand=True)
                right.pack(side='top', fill='x', pady=stacked_pady)
            state['wide'] = wide
            if state_attr is not None:
                setattr(self, state_attr, wide)

        def on_configure(event):
            width = event.width
            if debounce_ms is None:
                apply(width >= threshold)
                return
            # Routed through the shared _debounce helper (keyed uniquely
            # per call site via id(parent)), not a closure-local after_id,
            # so _on_root_destroy's cleanup of self._debounce_after_ids
            # reaches this pending timer too -- see that method's
            # docstring for why an uncancelled one matters.
            self._debounce(debounce_key, debounce_ms, lambda: apply(width >= threshold))

        parent.bind('<Configure>', on_configure)
        apply(False)
        return apply

    # -- shared responsive N-item grid ------------------------------------
    def _bind_responsive_grid(self, parent, items: list[tk.Widget], *, threshold: int,
                               columns: int = 2, gutter: int = 12, row_pady=(0, 10)):
        """Flow same-shaped `items` into `columns` even-width grid columns
        above `threshold` px of `parent`'s width, and a single stacked
        column below it. The general form of `_bind_responsive_columns`
        above for an arbitrary-length list rather than exactly two widgets.
        Settings' six path/output-directory panels need this: without it,
        each would run the page's full width no matter how wide the
        window gets."""
        state = {'wide': None}

        def apply(wide: bool):
            if wide == state['wide']:
                return
            for item in items:
                item.grid_forget()
            cols = columns if wide else 1
            # `uniform` ties every so-grouped column to the same width even
            # if some of them hold no widgets. Leaving all `columns` slots
            # grouped while only `cols` are actually in use silently starved
            # column 0 down to its 1/columns share of the available width
            # instead of the full width (caught by
            # test_audit_horizontal_control_rows_at_minimum_width). Only the
            # columns actually in play for this layout stay grouped/weighted;
            # the rest are reset to claim no space.
            for col in range(columns):
                if col < cols:
                    parent.columnconfigure(col, weight=1, uniform='responsive_grid')
                else:
                    parent.columnconfigure(col, weight=0, uniform='')
            for index, item in enumerate(items):
                col = index % cols
                if cols == 1:
                    padx = (0, 0)
                elif col == 0:
                    padx = (0, gutter // 2)
                else:
                    padx = (gutter // 2, 0)
                item.grid(row=index // cols, column=col, sticky='nsew', padx=padx, pady=row_pady)
            state['wide'] = wide

        def on_configure(event):
            apply(event.width >= threshold)

        parent.bind('<Configure>', on_configure)
        apply(False)
        return apply

    # -- shared resize-drag debounce ---------------------------------------
    def _debounce(self, key: str, ms: int, fn) -> None:
        """Run `fn` after `ms` idle milliseconds, canceling any call already
        pending under `key`. General form of the debounce Composer's color
        panel already used for its own resize handler. A live window-drag
        fires many <Configure> events per second, and repeating expensive
        work (e.g. re-gridding a category's worth of glyph tiles, measured
        at ~23ms per pass with a large CJK font's ~4,400 rendered tiles, so
        easily 100s of ms of cumulative work across a single drag with no
        throttling) on every intermediate width is what actually produces
        visible stutter, not the resize itself. Coalesces that burst into
        one action once the drag actually pauses.
        """
        pending = self._debounce_after_ids.get(key)
        if pending is not None:
            self.root.after_cancel(pending)
        self._debounce_after_ids[key] = self.root.after(ms, fn)

    # -- shared path/directory setting row --------------------------------
    def _build_path_setting(self, parent, *, label: str, variable: tk.StringVar, browse_command,
                             status_var: tk.StringVar | None = None, description: str | None = None
                             ) -> tuple[ttk.LabelFrame, ttk.Entry, ttk.Label | None]:
        """A directory/reference-path setting: a titled LabelFrame holding
        an Entry+Browse row, an optional status line, and an optional
        description. The shape every one of Settings' path panels
        (Reference modelbin, the output directories) previously built by
        hand, independently, one call site per panel.

        Returns `(frame, entry, status_label)`: the frame so a panel with
        more content than just the path (Image to Text's debug-output
        checkboxes) can keep packing into it, the Entry so a caller that
        needs to inspect/restyle it directly (Reference modelbin's own
        `ref_entry`) still can, and the status label so the caller can
        restyle it (Success/Danger) as the path's state changes.
        """
        frame = ttk.LabelFrame(parent, text=gui_theme.hud_label(label))
        row = ttk.Frame(frame)
        row.pack(fill='x', **gui_theme.ROW_PAD)
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(row, text=t('shell.button.browse'), command=browse_command).pack(side='left', padx=2)
        status_lbl = None
        if status_var is not None:
            status_lbl = ttk.Label(frame, textvariable=status_var, style='Hint.TLabel')
            status_lbl.pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        if description is not None:
            ttk.Label(frame, text=description, style='Hint.TLabel', wraplength=gui_theme.WRAP_MED,
                      justify='left').pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)
        return frame, entry, status_lbl

    def _log(self, line: str, tag: str | None = None):
        # tag is one of gui_theme.configure_text_tags' roles ('danger'/
        # 'warn'/'success'/'hint') so a terminal outcome (batch done,
        # export written, a blocked action) reads as that outcome instead
        # of every line looking the same regardless of what happened.
        self.log.configure(state='normal')
        self.log.insert('end', line + '\n', (tag,) if tag else ())
        self.log.see('end')
        self.log.configure(state='disabled')
    def _log_startup_elevation_notice(self):
        """Explain unexpected elevation without interrupting startup."""
        if gen_modelbin_gui.is_running_as_administrator():
            self._log(t('shell.log.admin_mode_detected'), tag='warn')
    def _resolve_overrides_for_generation(self, font_path: Path) -> tuple[dict[str, str] | None, dict[str, Path] | None]:
        """Split `font_path`'s saved per-glyph overrides for `build_fontpack`.

        Always reload from disk rather than trusting the currently displayed
        workspace state. Every edit saves immediately, so disk is the source
        of truth even when Generator has since selected another font.
        """
        overrides = glyph_overrides_store.load_overrides_for_font(font_path)
        if not overrides:
            return None, None
        mask_overrides: dict[str, str] = {}
        manual_assignments: dict[str, Path] = {}
        for char, entry in overrides.items():
            if entry['mode'] == 'manual':
                manual_assignments[char] = Path(entry['file'])
            else:
                mask_overrides[char] = entry['mode']
        return (mask_overrides or None), (manual_assignments or None)
    def _start_generation(self, *, font_path: Path | None, out_dir: Path, prefix: str, output: str,
                           reference: Path | None, segments: int, chars: set[str] | None,
                           allow_stencil: bool, source_label: str,
                           variation: dict | None = None,
                           color_mode: str = 'solid',
                           solid_color: tuple = (255, 255, 255, 255),
                           high_contrast_seed: int | None = None) -> bool:
        """Shared worker-thread entry point for fontpack generation paths.

        Generator and Advanced Generator resolve their tab-specific inputs
        before entering this common validation and execution pipeline.
        Returns True if a batch was started.

        `color_mode`/`solid_color`/`high_contrast_seed` pass straight
        through to `gen_fontpack.build_fontpack` -- see its docstring.
        Only Generator's own UI currently offers `color_mode="high_
        contrast"`; Advanced Generator always calls this with the defaults
        (its own embedded picker only ever sets `solid_color`).
        """
        if self.worker and self.worker.is_alive():
            self._log(t('shell.log.batch_already_running'), tag='warn')
            return False
        if font_path is None:
            self._log(t('shell.log.select_font_first'), tag='warn')
            return False
        if output == 'modelbin' and (reference is None or not reference.exists()):
            self._log(t('shell.log.reference_modelbin_not_found', path=reference), tag='warn')
            self._log(t('shell.log.reference_modelbin_hint'), tag='warn')
            return False
        if chars is not None and not chars:
            self._log(t('shell.log.no_characters_selected'), tag='warn')
            return False

        # Variable-instance overrides belong to the instantiated static face,
        # not the source VF: Thin and Bold can need different glyph repairs.
        # The worker resolves those after materializing the instance.
        if variation:
            mask_overrides, manual_assignments = None, None
        else:
            mask_overrides, manual_assignments = self._resolve_overrides_for_generation(font_path)
        compute_backend = self.compute_backend_var.get()
        if gen_modelbin_gui.resolve_backend(compute_backend).resolved == 'directml':
            if not messagebox.askokcancel(
                    t('shell.dialog.directml_warning_title'),
                    t('shell.dialog.directml_warning_body'),
                    icon='warning'):
                self._log(t('shell.log.directml_cancelled'), tag='warn')
                return False

        # Resolved once here, on the main thread, so every generation path
        # (Generator and Advanced Generator) runs under the same rules and
        # the worker never reads Tk variables off-thread.
        policy = self._current_generation_policy()
        problems = policy.validate()
        if problems:
            for problem in problems:
                self._log(problem, tag='danger')
            self._log(t('shell.log.fix_vinyl_shapes'), tag='warn')
            return False

        self._stop_requested.clear()
        self._abort_requested = False
        self._live_glyph_count = 0
        self.progress.start(12)
        self.generate_btn.configure(state='disabled')
        if hasattr(self, 'advanced_generate_btn'):
            self.advanced_generate_btn.configure(state='disabled')
        self.halt_btn.configure(state='normal')
        self.abort_btn.configure(state='normal')
        override_note = f', mask_overrides={len(mask_overrides)}' if mask_overrides else ''
        manual_note = f', manual_assignments={len(manual_assignments)}' if manual_assignments else ''
        color_note = (f', color_mode=high_contrast, seed={high_contrast_seed}' if color_mode == 'high_contrast'
                      else f', color_mode=solid, solid_color={tuple(solid_color)}')
        self._log(f'--- Generating fontpack "{prefix}" from {font_path.name} ({source_label}) '
                  f'(output={output}, curve_segments={segments}, allow_stencil={allow_stencil}'
                  f', compute_backend={compute_backend}{override_note}{manual_note}{color_note}) ---')

        self.worker = threading.Thread(
            target=self._run_batch,
            args=(font_path, out_dir, prefix, output, reference, segments, chars, allow_stencil,
                  mask_overrides, manual_assignments, compute_backend),
            kwargs={'policy': policy, 'color_mode': color_mode, 'solid_color': solid_color,
                    'high_contrast_seed': high_contrast_seed,
                    **({'variation': variation} if variation else {})},
            daemon=True)
        self.worker.start()
        return True
    def _confirm_variable_font_generation(self, font_path: Path | None) -> bool:
        """Block a silent generate-from-raw-defaults on a variable font.

        Only Advanced Generator pins a deliberately chosen named
        instance/axis coordinates (`instantiate_font`, wired through its own
        `variation` kwarg). The normal Generator passes the file straight through
        instead, which means fontTools extracts whatever the file's raw,
        un-instantiated glyf/gvar master happens to be: not necessarily
        Regular, and never a style the user actually chose. Returns True to
        proceed (static font, inspection failed, or the user chose to
        continue anyway), False to cancel.
        """
        if font_path is None:
            return True
        try:
            info = gen_modelbin_gui.inspect_variable_font(font_path)
        except Exception:
            return True
        if not info.is_variable:
            return True
        defaults = ', '.join(f'{axis.tag}={axis.default:g}' for axis in info.axes)
        return messagebox.askyesno(
            t('shell.dialog.variable_font_title'),
            t('shell.dialog.variable_font_body', font_name=font_path.name,
              instance_count=len(info.instances), defaults=defaults))
    def _start_batch(self):
        if not self._confirm_variable_font_generation(self.selected_font):
            self._log(t('shell.log.variable_font_cancelled'), tag='warn')
            return
        output = self.output_var.get()
        reference = Path(self.ref_var.get()) if output == 'modelbin' else None
        chars = self._selected_chars()
        if self.selected_font is not None:
            try:
                categorized, _ = gen_modelbin_gui.charset_from_font(self.selected_font)
                supported = {char for group in categorized.values() for char in group}
                glyph_count = len(supported if chars is None else supported & chars)
            except Exception:
                glyph_count = len(chars) if chars is not None else 0
            if glyph_count >= 500 and not messagebox.askyesno(
                    t('shell.dialog.large_job_title'),
                    t('shell.dialog.large_job_body', glyph_count=f'{glyph_count:,}')):
                self._log(t('shell.log.large_job_cancelled', glyph_count=f'{glyph_count:,}'), tag='warn')
                return
        color_mode = self.generator_color_mode_var.get()
        self._start_generation(
            font_path=self.selected_font,
            out_dir=Path(self.modelbin_out_var.get() if output == 'modelbin' else self.out_var.get()),
            prefix=sanitize_prefix(self.prefix_var.get()), output=output, reference=reference,
            segments=max(1, int(self.segments_var.get())), chars=chars,
            allow_stencil=self.allow_stencil_var.get(), source_label='Generator',
            color_mode=color_mode, solid_color=self.generator_color,
            high_contrast_seed=(int(self.generator_hc_seed_var.get())
                                 if color_mode == 'high_contrast' else None))
    def _halt_batch(self):
        # Stop and keep whatever's generated so far.
        self._stop_requested.set()
    def _abort_batch(self):
        # Stop and discard whatever this run wrote.
        self._abort_requested = True
        self._stop_requested.set()
    def _run_batch(self, font_path, out_dir, prefix, output, reference, segments, chars, allow_stencil=True,
                   mask_overrides=None, manual_assignments=None, compute_backend='auto', variation=None,
                   policy=None, color_mode='solid', solid_color=(255, 255, 255, 255),
                   high_contrast_seed=None):
        def log(line: str):
            self.msg_queue.put(('log', line))

        def on_glyph(category, entry):
            self.msg_queue.put(('glyph', pack_dir, category, entry))

        resolved = gen_modelbin_gui.resolve_backend(compute_backend if output == 'json' else 'cpu')
        source_font_path = font_path
        effective_prefix = prefix
        try:
            if variation:
                coordinates = variation.get('coordinates', {})
                slug = variation_slug(coordinates)
                log(f'  Preparing variable-font instance: {variation.get("named_instance", "Custom")} '
                    f'({slug})')
                font_path = gen_modelbin_gui.instantiate_font(source_font_path, coordinates)
                effective_prefix = sanitize_prefix(f'{prefix}-{slug}')
                mask_overrides, manual_assignments = self._resolve_overrides_for_generation(font_path)
                if mask_overrides or manual_assignments:
                    log(f'  Instance-specific overrides: {len(mask_overrides or {})} mask, '
                        f'{len(manual_assignments or {})} manual')
            pack_dir = pack_dir_for(out_dir, effective_prefix, output, segments, resolved.resolved)
            variation_kwargs = ({'source_font_path': source_font_path, 'variation': variation}
                                if variation else {})
            manifest = gen_modelbin_gui.build_fontpack(font_path, out_dir, effective_prefix, output, reference, segments,
                                       chars=chars, should_stop=self._stop_requested.is_set,
                                       on_glyph=on_glyph, log=log, allow_stencil=allow_stencil,
                                       mask_overrides=mask_overrides, manual_assignments=manual_assignments,
                                       compute_backend=compute_backend,
                                       policy=policy,
                                       color_mode=color_mode, solid_color=solid_color,
                                       high_contrast_seed=high_contrast_seed,
                                       **variation_kwargs)
            if self._abort_requested:
                removed = 0
                for rel in manifest.get('files_written', []):
                    file_path = pack_dir / rel
                    if file_path.exists():
                        file_path.unlink()
                        removed += 1
                manifest_path = pack_dir / 'manifest.json'
                if manifest_path.exists():
                    manifest_path.unlink()
                done_msg = t('shell.log.aborted', removed=removed)
                done_tag = 'warn'
            else:
                summary = manifest['summary']
                bits = ', '.join(f"{mode}: {summary[mode]['generated']} ok/{summary[mode]['failed']} failed"
                                  for mode in ('modelbin', 'json') if mode in summary)
                done_key = 'shell.log.done_halted' if manifest.get('halted') else 'shell.log.done'
                done_msg = t(done_key, bits=bits, skipped=summary['skipped'],
                             manifest_path=pack_dir / 'manifest.json')
                done_tag = 'success'
                for line in self._generation_diagnostics_lines(manifest):
                    self.msg_queue.put(('log', line))
        except Exception as exc:
            done_msg = t('shell.log.failed', error=exc)
            done_tag = 'danger'
        self.msg_queue.put(('done', done_msg, done_tag))
    @staticmethod
    def _generation_diagnostics_lines(manifest: dict) -> list[str]:
        """Aggregate the per-glyph diagnostics into a short run summary.

        Aggregated across the whole batch rather than reporting the last
        glyph, which is what makes it useful for comparing two Vinyl-shapes
        settings against each other: totals, the mix of vinyl types actually
        used, worst-case accuracy, and how often a fallback had to step in.
        Returns lines rather than logging directly so it can be called from
        the worker thread.
        """
        entries = [entry.get('artifacts', {}).get('json', {}).get('diagnostics')
                   for category in manifest.get('categories', {}).values()
                   for entry in category]
        stats = [d for d in entries if d]
        if not stats:
            return []

        by_shape: dict[str, int] = {}
        for record in stats:
            for shape_id, count in record.get('by_shape', {}).items():
                by_shape[shape_id] = by_shape.get(shape_id, 0) + count
        total_vinyls = sum(by_shape.values())
        ious = [d['iou'] for d in stats if d.get('iou') is not None]
        tested = sum(d.get('candidates_tested', 0) for d in stats)
        rejected = sum(d.get('candidates_rejected', 0) for d in stats)
        elapsed = sum(d.get('elapsed_seconds', 0.0) for d in stats)
        fallbacks = sum(1 for d in stats if d.get('fallback_used'))
        warned = sum(1 for d in stats if d.get('warnings'))

        mix = ', '.join(f'{shape_id} x{count}'
                        for shape_id, count in sorted(by_shape.items(), key=lambda kv: -kv[1]))
        lines = [
            f'    Diagnostics: {total_vinyls:,} vinyls across {len(stats):,} glyphs '
            f'({total_vinyls / len(stats):.1f} per glyph)',
            f'    Vinyl types used: {mix}',
        ]
        if ious:
            lines.append(f'    Accuracy: mean IoU {sum(ious) / len(ious):.3f}, '
                          f'worst {min(ious):.3f}')
        lines.append(f'    Search: {tested:,} candidates tested, {rejected:,} rejected, '
                      f'{elapsed:.1f}s fitting')
        if fallbacks:
            lines.append(t('shell.log.fallback_used', count=f'{fallbacks:,}'))
        if warned:
            lines.append(t('shell.log.quality_shortfall', count=f'{warned:,}'))
        return lines
    def _show_live_glyph_preview(self, pack_dir, category, entry):
        artifact = entry.get('artifacts', {}).get('json') or entry.get('artifacts', {}).get('modelbin')
        if not artifact or not artifact.get('file'):
            return
        file_path = pack_dir / artifact['file']
        if not file_path.exists():
            return
        p = gui_theme.palette()
        image = file_preview.render_file_preview(file_path, LIVE_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'])
        self._live_preview_photo = ImageTk.PhotoImage(image)
        self.live_preview_canvas.delete('all')
        self.live_preview_canvas.create_image(0, 0, anchor='nw', image=self._live_preview_photo)
        self._live_glyph_count += 1
        if artifact.get('quality'):
            self.live_preview_stats_var.set(t(
                'shell.status.live_preview_generating_quality',
                done=self._live_glyph_count, category=category, char=repr(entry['char']),
                verdict=artifact['quality']['verdict'].upper(),
                iou=f"{artifact['quality']['iou']:.3f}",
                boundary_f1=f"{artifact['quality']['boundary_f1']:.3f}"))
        else:
            self.live_preview_stats_var.set(t(
                'shell.status.live_preview_generating',
                done=self._live_glyph_count, category=category, char=repr(entry['char'])))
    def _poll_queue(self):
        # `after()` timers are registered against the whole Tcl interpreter,
        # not the specific widget that scheduled them, and a *pending*
        # timer -- scheduled but not yet fired -- is a live reference to
        # this whole instance for its entire wait, independent of whether
        # `root` gets destroyed in the meantime: harmless for one real app
        # window whose whole process exits with it, but fatal for the test
        # suite, which builds and destroys hundreds of GUI instances in one
        # process (see __init__'s _poll_queue_after_id and
        # _on_root_destroy, which cancel this explicitly rather than
        # relying on the guard below, which only stops it from
        # *rescheduling* once it does fire).
        if not self.root.winfo_exists():
            return
        try:
            while True:
                item = self.msg_queue.get_nowait()
                if item[0] == 'log':
                    self._log(item[1])
                elif item[0] == 'done':
                    self._log(item[1], tag=item[2])
                    self.progress.stop()
                    self.generate_btn.configure(state='normal')
                    if hasattr(self, 'advanced_generate_btn'):
                        self.advanced_generate_btn.configure(state='normal')
                    self.halt_btn.configure(state='disabled')
                    self.abort_btn.configure(state='disabled')
                elif item[0] == 'direct_done':
                    _, shapes, warnings, metadata, payload, suggested_name = item
                    self.direct_generate_btn.configure(state='normal')
                    self._apply_direct_result(
                        shapes, warnings, metadata, payload, suggested_name)
                elif item[0] == 'direct_error':
                    _, error = item
                    self._direct_preview_signature = None
                    self.direct_generate_btn.configure(state='normal')
                    self.direct_status_var.set(t('shell.status.direct_generate_failed', error=error))
                    self.direct_status_lbl.configure(style='Danger.TLabel')
                    self._log(t('shell.log.direct_generator_failed', error=error), tag='danger')
                elif item[0] == 'glyph':
                    _, pack_dir, category, entry = item
                    self._show_live_glyph_preview(pack_dir, category, entry)
                elif item[0] == 'grid_tile':
                    _, generation, name, path, pil_image = item
                    if generation == self._grid_generation:
                        self._add_grid_tile(name, path, pil_image)
                elif item[0] == 'fonts_loaded':
                    _, generation, fonts = item
                    self._on_fonts_loaded(generation, fonts)
                elif item[0] == 'font_script_detected':
                    _, generation, name, scripts = item
                    if generation == self._font_scan_generation:
                        self._font_scripts[name] = scripts
                        if self._script_filter is not None:
                            self._refresh_font_list()
                            if self.font_view_var.get() == 'grid':
                                self._populate_font_grid()
                elif item[0] == 'font_scripts_done':
                    _, generation = item
                    if generation == self._font_scan_generation:
                        self.font_scan_status_var.set(t('shell.status.font_scan_count', count=len(self.fonts)))
                elif item[0] == 'compute_backend_detected':
                    self._update_compute_backend_status()
                elif item[0] == 'cleanup_sizes_ready':
                    _, generation, sizes = item
                    if generation == self._cleanup_size_generation:
                        for key, (files, byte_count) in sizes.items():
                            self.cleanup_size_vars[key].set(t(
                                'shell.status.cleanup_size_summary',
                                size=generated_data_cleanup.format_size(byte_count), count=f'{files:,}'))
                elif item[0] == 'configurator_glyph_scanned':
                    _, generation, char, info = item
                    if generation == self._configurator_scan_generation:
                        self._apply_configurator_scan_result(char, info)
                elif item[0] == 'configurator_scan_done':
                    _, generation, total = item
                    if generation == self._configurator_scan_generation:
                        self.configurator_scan_status_var.set(
                            t('shell.status.configurator_scan_done', count=total))
                elif item[0] == 'configurator_detail_ready':
                    _, generation, char, result = item
                    if (generation == self._configurator_detail_generation
                            and char == self._configurator_selected_char):
                        self._apply_configurator_detail(char, result)
                elif item[0] == 'configurator_detail_error':
                    _, generation, char, error = item
                    if (generation == self._configurator_detail_generation
                            and char == self._configurator_selected_char):
                        self.configurator_detail_status_var.set(
                            t('shell.status.configurator_render_failed', char=repr(char), error=error))
                elif item[0] == 'advanced_preview_ready':
                    _, generation, instance_path, image = item
                    if generation == self._advanced_preview_generation:
                        self._advanced_preview_photo = ImageTk.PhotoImage(image)
                        self.advanced_preview_canvas.delete('all')
                        self.advanced_preview_canvas.create_image(
                            0, 0, anchor='nw', image=self._advanced_preview_photo)
                        self.advanced_preview_status_var.set(t(
                            'shell.status.advanced_preview_ready',
                            instance=self.advanced_instance_var.get(), instance_file=instance_path.name))
                elif item[0] == 'advanced_preview_error':
                    _, generation, error = item
                    if generation == self._advanced_preview_generation:
                        self.advanced_preview_status_var.set(
                            t('shell.status.advanced_preview_failed', error=error))
                elif item[0] == 'glyph_inspector_font_loaded':
                    _, generation, info = item
                    if generation == self._glyph_inspector_load_generation:
                        self._apply_glyph_inspector_font_loaded(info)
                elif item[0] == 'glyph_inspector_font_error':
                    _, generation, error = item
                    if generation == self._glyph_inspector_load_generation:
                        self.glyph_inspector_font_status_var.set(
                            t('shell.status.glyph_inspector_load_failed', error=error))
                        self.glyph_inspector_status_var.set('')
                elif item[0] == 'glyph_inspector_tile':
                    _, generation, category, glyph, pil_image = item
                    if generation == self._glyph_inspector_grid_generation:
                        self._add_glyph_inspector_tile(category, glyph, pil_image)
                elif item[0] == 'glyph_inspector_generated_ready':
                    _, generation, cache_key, result = item
                    self._glyph_inspector_generated_cache[cache_key] = result
                    if generation == self._glyph_inspector_generate_generation:
                        self._refresh_glyph_inspector_detail()
                elif item[0] == 'glyph_inspector_generated_error':
                    _, generation, cache_key, error = item
                    self._glyph_inspector_generated_cache[cache_key] = {'error': error}
                    if generation == self._glyph_inspector_generate_generation:
                        self._refresh_glyph_inspector_detail()
                elif item[0] == 'layer_effects_generate_ready':
                    _, generation, shapes, warnings, groups_by_char, compare_shapes = item
                    if generation == self._layer_effects_generate_generation:
                        self._apply_layer_effects_generated(shapes, warnings, groups_by_char, compare_shapes)
                elif item[0] == 'layer_effects_generate_error':
                    _, generation, error = item
                    if generation == self._layer_effects_generate_generation:
                        self.layer_effects_status_var.set(f"Couldn't generate: {error}")
                elif item[0] == 'advanced_override_instance_ready':
                    _, generation, instance_path = item
                    if generation == self._advanced_preview_generation:
                        instance_path = Path(instance_path)
                        slug = variation_slug(self._advanced_coordinates())
                        self.selected_font = instance_path
                        self.font_path_var.set(str(instance_path))
                        self.font_list.selection_clear(0, 'end')
                        self._check_lowercase_warning()
                        self._check_variable_font_status()
                        self._on_character_selection_changed()
                        self.prefix_var.set(sanitize_prefix(f'{self.prefix_var.get()}-{slug}'))
                        self._show_tab('generator')
                        self._set_configurator_workspace_open(True)
                elif item[0] == 'plates_failed':
                    _, error = item
                    self._handle_plates_failed(error)
                elif item[0] == 'plates_render_for_generate':
                    _, template, shapes, root, warnings, out_dir = item
                    self._handle_plates_render_for_generate(template, shapes, root, warnings, out_dir)
                elif item[0] == 'plates_preview_ready':
                    _, image, count, warnings = item
                    self._handle_plates_preview_ready(image, count, warnings)
                elif item[0] == 'plates_preview_failed':
                    _, error = item
                    self._handle_plates_preview_failed(error)
        except queue.Empty:
            pass
        self._poll_queue_after_id = self.root.after(100, self._poll_queue)
