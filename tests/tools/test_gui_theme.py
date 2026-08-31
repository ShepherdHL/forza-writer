import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))
import gui_settings  # noqa: E402
import gui_theme  # noqa: E402
from gui_theme import (  # noqa: E402
    INDENT_PAD,
    PAGE_INTRO_PAD,
    PALETTE,
    PALETTES,
    DENSITIES,
    ROW_PAD,
    ROW_PAD_BOTTOM,
    ROW_PAD_TOP,
    SCROLLBAR_GUTTER,
    SECTION_PAD,
    WRAP_MED,
    WRAP_NARROW,
    WRAP_WIDE,
    AutoHideScrollbar,
    _hex_to_colorref,
    apply_theme,
    apply_title_bar_theme,
    configure_text_tags,
    configure,
    hud_label,
    palette,
)

tk = pytest.importorskip("tkinter")
from tkinter import font as tkfont  # noqa: E402
from tkinter import ttk  # noqa: E402

EXPECTED_KEYS = {
    "bg", "fg", "muted_fg", "entry_bg", "entry_fg", "select_bg", "select_fg",
    "button_bg", "button_active_bg", "border", "listbox_bg", "listbox_fg",
    "log_bg", "log_fg", "canvas_bg", "disabled_fg", "accent", "accent_active",
    "accent_glow", "secondary_accent", "success", "danger", "warn", "hint",
    "info", "panel_alt", "frame_light", "frame_dark", "sash",
}

# This pass's deliberately-chosen "Eurocorp II" values (Syndicate x
# Vercel identity redesign) — not a user-dictated spec like the palette's
# first iteration, but still worth pinning: a regression test so a future
# tweak to one token doesn't silently drift the rest of the system out of
# the tonal relationships this pass was built around (near-black bg,
# workspace one tier lifted, accent reserved for active/selected state).
CHOSEN_VALUES = {
    "bg": "#1e1f22",
    "fg": "#f2f3f5",
    "panel_alt": "#2b2d31",
    "accent": "#e08a3f",
    "accent_active": "#a8611f",
    "accent_glow": "#f6b877",
    "border": "#41434a",
    "muted_fg": "#b5bac1",
    "hint": "#b5bac1",
    "warn": "#c99a52",
    "danger": "#c9645a",
    "success": "#72a08c",
    "secondary_accent": "#5c7a94",
}


def test_palette_has_all_expected_keys():
    assert set(PALETTE.keys()) == EXPECTED_KEYS


def test_palette_values_are_valid_hex_colors():
    for key, value in PALETTE.items():
        assert value.startswith("#"), f"{key} = {value!r} isn't a hex color"
        assert len(value) == 7, f"{key} = {value!r} isn't #RRGGBB"


def test_palette_helper_returns_the_palette():
    assert palette() is PALETTE


def test_background_is_soft_charcoal_not_near_black():
    assert PALETTE["bg"] != "#000000"
    r, g, b = (int(PALETTE["bg"][i:i + 2], 16) for i in (1, 3, 5))
    assert min(r, g, b) >= 28


def test_all_palettes_have_the_same_valid_color_roles():
    for values in PALETTES.values():
        assert set(values) == EXPECTED_KEYS
        assert all(value.startswith("#") and len(value) == 7 for value in values.values())


def test_density_profiles_are_ordered_and_balanced_is_the_default():
    assert DENSITIES["compact"]["body"] < DENSITIES["balanced"]["body"] < DENSITIES["spacious"]["body"]
    configure()
    assert PALETTE == PALETTES["charcoal"]


def test_configure_switches_palette_and_rejects_unknown_values_safely():
    configure("slate", "compact")
    assert PALETTE == PALETTES["slate"]
    configure("unknown", "unknown")
    assert PALETTE == PALETTES["charcoal"]


def test_chosen_palette_values_match_this_passs_design_choices():
    for key, value in CHOSEN_VALUES.items():
        assert PALETTE[key] == value


def test_workspace_surface_is_lifted_above_the_base_background():
    # panel_alt (TFrame/TLabel/TLabelframe's default bg) must read as a
    # step above bg (root/sidebar/Log chrome) — the depth cue this pass's
    # whole elevation model depends on, since Tk can't draw real shadows.
    bg = tuple(int(PALETTE["bg"][i:i + 2], 16) for i in (1, 3, 5))
    surface = tuple(int(PALETTE["panel_alt"][i:i + 2], 16) for i in (1, 3, 5))
    assert sum(surface) > sum(bg)


def test_accent_is_reserved_and_distinct_from_every_other_role():
    # "Restrained use of orange... for selected/active states" only holds
    # if accent doesn't quietly collide with an unrelated semantic color.
    other_roles = {"warn", "danger", "success", "secondary_accent", "hint", "muted_fg"}
    assert PALETTE["accent"] not in {PALETTE[role] for role in other_roles}


# --- Eurocorp ---------------------------------------------------------


def test_eurocorp_is_registered_and_matches_the_shared_contract():
    assert "eurocorp" in PALETTES
    assert set(PALETTES["eurocorp"]) == EXPECTED_KEYS


def test_eurocorp_select_fg_is_dark_on_its_solid_accent_fill():
    # Charcoal/Slate's select_fg is cream because accent there is only ever
    # a thin highlight edge. Eurocorp's accent is a broad solid fill
    # (SOLID_SELECTED_ROW), so select_fg must stay dark — reusing the
    # cream value here would silently regress into low-contrast text on a
    # solid orange row, exactly what this test guards against.
    eurocorp = PALETTES["eurocorp"]
    fg_sum = sum(int(eurocorp["select_fg"][i:i + 2], 16) for i in (1, 3, 5))
    assert fg_sum < 200  # near-black, not Charcoal/Slate's cream (~700)


def test_eurocorp_opts_into_solid_selected_row_and_the_others_dont():
    assert gui_theme.SOLID_SELECTED_ROW["eurocorp"] is True
    assert gui_theme.SOLID_SELECTED_ROW["charcoal"] is False
    assert gui_theme.SOLID_SELECTED_ROW["slate"] is False


def test_configure_eurocorp_round_trips_and_resets_cleanly():
    try:
        configure("eurocorp", "balanced")
        assert PALETTE == PALETTES["eurocorp"]
        assert gui_theme.CURRENT_PALETTE == "eurocorp"
    finally:
        configure()  # restore the default so later tests see charcoal
    assert PALETTE == PALETTES["charcoal"]


def test_display_font_family_registry_is_eurocorp_only():
    # Charcoal/Slate deliberately have no preferred display font -- only
    # Eurocorp's DIN Pro homage opts in. Not part of EXPECTED_KEYS, so this
    # is its own explicit assertion rather than folded into the token-
    # contract test.
    from gui_theme.palettes import DISPLAY_FONT_FAMILY
    assert DISPLAY_FONT_FAMILY["eurocorp"] == "DINPro-Medium"
    assert DISPLAY_FONT_FAMILY["charcoal"] is None
    assert DISPLAY_FONT_FAMILY["slate"] is None


def test_display_font_family_resolves_when_registered(monkeypatch):
    root = tk.Tk()
    try:
        root.withdraw()
        monkeypatch.setattr(gui_theme._apply.tkfont, "families",
                             lambda *_a, **_kw: ("DINPro-Medium", "Segoe UI"))
        try:
            configure("eurocorp", "balanced")
            assert gui_theme.display_font_family(root) == "DINPro-Medium"
        finally:
            configure()
    finally:
        root.destroy()


def test_display_font_family_falls_back_when_not_installed(monkeypatch):
    # The whole point of resolving through tkfont.families() rather than
    # trusting the palette blindly: a machine without this personally-
    # installed font must degrade to the same look every other palette has,
    # not error or silently hand Tk an unknown family to substitute for.
    root = tk.Tk()
    try:
        root.withdraw()
        monkeypatch.setattr(gui_theme._apply.tkfont, "families", lambda *_a, **_kw: ("Segoe UI",))
        try:
            configure("eurocorp", "balanced")
            assert gui_theme.display_font_family(root) == "Segoe UI Semibold"
        finally:
            configure()
    finally:
        root.destroy()


def test_display_font_family_ignores_charcoal_and_slate_even_if_installed(monkeypatch):
    root = tk.Tk()
    try:
        root.withdraw()
        monkeypatch.setattr(gui_theme._apply.tkfont, "families", lambda *_a, **_kw: ("DINPro-Medium",))
        for name in ("charcoal", "slate"):
            try:
                configure(name, "balanced")
                assert gui_theme.display_font_family(root) == "Segoe UI Semibold"
            finally:
                configure()
    finally:
        root.destroy()


def _spy_on_font_construction(monkeypatch):
    """Record the `family` kwarg of every tkfont.Font(...) apply.py
    constructs, without disturbing real construction. Avoids relying on
    ttk's post-hoc font-name lookup + tkfont.Font(exists=True) rebinding,
    which is fragile here: apply.py's Font objects are local variables that
    can be garbage-collected (deleting their underlying Tcl named font)
    before a test gets around to re-resolving the name ttk stored."""
    seen = []
    real_font_cls = tkfont.Font

    def spy(*args, **kwargs):
        seen.append(kwargs.get("family"))
        return real_font_cls(*args, **kwargs)

    monkeypatch.setattr(gui_theme._apply.tkfont, "Font", spy)
    return seen


def test_apply_theme_headings_actually_use_the_resolved_display_family(monkeypatch):
    # Regression guard: apply_theme()'s own heading/title/accent-button/
    # category fonts must use the resolved family, not just the standalone
    # display_font_family() helper agreeing with itself -- and body/detail/
    # button/log text must stay untouched (a display-only accent, not a
    # wholesale typography swap).
    root = tk.Tk()
    try:
        root.withdraw()
        style = ttk.Style(root)
        monkeypatch.setattr(gui_theme._apply.tkfont, "families",
                             lambda *_a, **_kw: ("DINPro-Medium", "Segoe UI"))
        seen = _spy_on_font_construction(monkeypatch)
        try:
            configure("eurocorp", "balanced")
            apply_theme(root, style)
        finally:
            configure()
        assert "DINPro-Medium" in seen
        assert "Segoe UI" in seen  # body/detail/button/link untouched
        assert "Consolas" in seen  # the inline-code font untouched
    finally:
        root.destroy()


def test_apply_theme_charcoal_and_slate_fonts_unchanged_by_the_feature(monkeypatch):
    # Even with the font available on-machine, Charcoal/Slate must never
    # construct a DINPro-Medium font -- this is opt-in per palette, not
    # global, and must fall back to the exact prior literal.
    root = tk.Tk()
    try:
        root.withdraw()
        style = ttk.Style(root)
        monkeypatch.setattr(gui_theme._apply.tkfont, "families",
                             lambda *_a, **_kw: ("DINPro-Medium", "Segoe UI"))
        for name in ("charcoal", "slate"):
            seen = _spy_on_font_construction(monkeypatch)
            try:
                configure(name, "balanced")
                apply_theme(root, style)
            finally:
                configure()
            assert "DINPro-Medium" not in seen
            assert "Segoe UI Semibold" in seen
    finally:
        root.destroy()


def test_gui_settings_valid_palettes_matches_the_registry():
    # gui_settings.py deliberately doesn't import gui_theme (see its own
    # VALID_PALETTES comment), so the two name lists can silently drift —
    # this is the test that keeps them honest, the same discipline KFPS
    # uses for its own Python/QML supporter-flag agreement test.
    assert gui_settings.VALID_PALETTES == set(PALETTES)


# --- HUD label tracking --------------------------------------------------

def test_hud_label_uppercases_and_tracks_letters():
    assert hud_label("Log") == "L O G"


def test_hud_label_widens_real_word_gaps_so_they_read_as_word_breaks():
    # A single plain space does not visually register as a word break
    # once every surrounding letter already carries its own thin-space
    # tracking (confirmed by rendering a real multi-word header) so a
    # real space becomes two plain spaces, clearly wider than the
    # single-thin-space letter tracking on either side of it.
    result = hud_label("Fontpack root folder")
    assert "  " in result
    assert result.count("  ") == 2


def test_hud_label_is_idempotent_on_already_spaced_input():
    # Guards against accidentally doubling tracking if ever applied twice
    # to the same string.
    once = hud_label("Log")
    assert hud_label(once.lower()) == once


# --- native title bar theming (Windows DWM) ---------------------------

def test_hex_to_colorref_reverses_byte_order():
    # COLORREF is 0x00BBGGRR — the reverse of a normal #RRGGBB hex string.
    assert _hex_to_colorref("#040405") == 0x00050404
    assert _hex_to_colorref("#e8ebf0") == 0x00f0ebe8
    assert _hex_to_colorref("#ff0000") == 0x000000ff
    assert _hex_to_colorref("#00ff00") == 0x0000ff00
    assert _hex_to_colorref("#0000ff") == 0x00ff0000


def test_apply_title_bar_theme_never_raises_on_a_real_window():
    root = tk.Tk()
    try:
        root.withdraw()
        apply_title_bar_theme(root)  # must not raise, on Windows or elsewhere
    finally:
        root.destroy()


def test_apply_title_bar_theme_is_a_noop_off_windows(monkeypatch):
    # apply_title_bar_theme does `import sys` locally — that's still the
    # same cached module object as this file's own top-level `import sys`
    # (Python only ever loads one `sys` module), so patching it here is
    # visible there too.
    monkeypatch.setattr(sys, "platform", "linux")
    root = tk.Tk()
    try:
        root.withdraw()
        apply_title_bar_theme(root)  # must return immediately, no ctypes/DWM access attempted
    finally:
        root.destroy()


def test_no_key_used_by_apply_theme_is_missing_from_palette():
    # apply_theme() indexes the palette by these keys directly (p["..."]);
    # a KeyError here would only surface at runtime when a widget themes
    # itself, which is exactly the kind of gap this test exists to catch
    # ahead of time.
    used_directly = {
        "bg", "fg", "entry_bg", "border", "button_bg", "fg",
        "button_active_bg", "accent", "select_fg", "accent_active",
        "disabled_fg", "entry_fg", "secondary_accent", "listbox_fg",
        "danger",
    }
    assert used_directly <= set(PALETTE.keys())


# --- design system: spacing scale + label wraplength tiers -------------

def test_spacing_tokens_are_pack_ready_kwarg_dicts():
    # SECTION_PAD/ROW_PAD/etc. get spread directly into .pack(**token) call
    # sites throughout gen_modelbin_gui.py — each must be a dict of only
    # padx/pady, nothing pack() would reject.
    for token in (SECTION_PAD, ROW_PAD, ROW_PAD_TOP, ROW_PAD_BOTTOM, PAGE_INTRO_PAD):
        assert set(token.keys()) <= {"padx", "pady"}


def test_row_pad_top_and_bottom_are_asymmetric_and_meet_in_the_middle():
    # A control (ROW_PAD_TOP) and the description glued underneath it
    # (ROW_PAD_BOTTOM) should read as one visually-coupled group: no gap
    # between them, matching the whitespace above/below the pair.
    assert ROW_PAD_TOP["pady"][1] == 0
    assert ROW_PAD_BOTTOM["pady"][0] == 0


def test_indent_pad_is_a_left_only_offset():
    assert INDENT_PAD[0] > 0
    assert INDENT_PAD[1] == 0


def test_wrap_tiers_are_ordered_wide_to_narrow():
    assert WRAP_WIDE > WRAP_MED > WRAP_NARROW


# --- design system: semantic ttk label styles ---------------------------

def test_semantic_label_styles_use_the_matching_palette_role():
    root = tk.Tk()
    try:
        root.withdraw()
        style = ttk.Style(root)
        apply_theme(root, style)
        p = palette()
        for style_name, role in (
            ("Intro.TLabel", "fg"),
            ("Hint.TLabel", "hint"),
            ("Warn.TLabel", "warn"),
            ("Danger.TLabel", "danger"),
            ("Success.TLabel", "success"),
        ):
            assert style.lookup(style_name, "foreground") == p[role]
    finally:
        root.destroy()


def test_detail_styles_carry_their_own_font_distinct_from_body_text():
    # Hint/Warn/Danger/Success read as secondary by size as well as color —
    # not just a recolored copy of the same body text — so each must carry
    # an explicit font override, unlike plain TLabel/Intro.TLabel which
    # inherit the default body font untouched.
    root = tk.Tk()
    try:
        root.withdraw()
        style = ttk.Style(root)
        apply_theme(root, style)
        body_font = style.lookup("TLabel", "font")
        assert style.lookup("Intro.TLabel", "font") == body_font
        for detail_style in ("Hint.TLabel", "Warn.TLabel", "Danger.TLabel", "Success.TLabel"):
            assert style.lookup(detail_style, "font") != body_font
    finally:
        root.destroy()


# --- design system: chrome-tier panel variant ----------------------------

def test_chrome_labelframe_sits_at_the_bg_tier_not_the_workspace_tier():
    # The Log panel is fixed UI chrome, not page content — its LabelFrame
    # must sit at the darker `bg` tier while every other LabelFrame
    # (workspace content) sits at the lifted `panel_alt` tier.
    root = tk.Tk()
    try:
        root.withdraw()
        style = ttk.Style(root)
        apply_theme(root, style)
        p = palette()
        assert style.lookup("Chrome.TLabelframe", "background") == p["bg"]
        assert style.lookup("TLabelframe", "background") == p["panel_alt"]
    finally:
        root.destroy()


# --- design system: custom checkbox/radio indicators ---------------------

def test_custom_indicator_elements_are_registered_and_used_in_layout():
    root = tk.Tk()
    try:
        root.withdraw()
        style = ttk.Style(root)
        apply_theme(root, style)
        # Element names are namespaced by the active palette (see
        # gui_theme._apply_custom_indicators's `Custom.{palette_key}...`) so
        # more than one palette's indicators can be registered on the same
        # Style without colliding — read the live CURRENT_PALETTE global
        # (module-qualified, not a direct-name import, since configure()
        # reassigns it) rather than assuming which palette is active.
        check_element = f"Custom.{gui_theme.CURRENT_PALETTE}.Checkbutton.indicator"
        radio_element = f"Custom.{gui_theme.CURRENT_PALETTE}.Radiobutton.indicator"
        assert check_element in style.element_names()
        assert radio_element in style.element_names()
        # And the checkbutton/radiobutton layouts actually reference them,
        # not just registered-but-unused elements.
        check_layout = str(style.layout("TCheckbutton"))
        radio_layout = str(style.layout("TRadiobutton"))
        assert check_element in check_layout
        assert radio_element in radio_layout
    finally:
        root.destroy()


def test_a_real_checkbutton_and_radiobutton_render_without_raising():
    # element_create/layout surgery is easy to get subtly wrong (wrong
    # image size, a missing state pairing) — this is the check that would
    # actually catch that, by forcing Tk to lay the widgets out for real.
    root = tk.Tk()
    try:
        root.withdraw()
        style = ttk.Style(root)
        apply_theme(root, style)
        cb = ttk.Checkbutton(root, text="test")
        rb = ttk.Radiobutton(root, text="test")
        cb.pack()
        rb.pack()
        root.update()
    finally:
        root.destroy()


# --- design system: flat scrollbars ---------------------------------------

def test_scrollbar_layout_has_no_arrow_buttons():
    root = tk.Tk()
    try:
        root.withdraw()
        style = ttk.Style(root)
        apply_theme(root, style)
        layout_str = str(style.layout("Vertical.TScrollbar"))
        assert "uparrow" not in layout_str.lower()
        assert "downarrow" not in layout_str.lower()
        assert "thumb" in layout_str.lower()
    finally:
        root.destroy()


def test_scrollbar_thumb_has_no_legacy_grip_dots():
    # clam's stock thumb renders a mid-thumb "grip" (a row of dots, a
    # drag-handle affordance from an older UI era) unless gripcount is
    # explicitly zeroed — confirmed by an actual screenshot showing the
    # dots still present after the flat trough/thumb layout change alone.
    root = tk.Tk()
    try:
        root.withdraw()
        style = ttk.Style(root)
        apply_theme(root, style)
        assert style.lookup("Vertical.TScrollbar", "gripcount") in ("0", 0)
    finally:
        root.destroy()


# --- design system: AutoHideScrollbar --------------------------------------
# These need a real (non-withdrawn) root — winfo_ismapped()/yscrollcommand
# only fire correctly once Tk actually lays the widget out with real pixel
# geometry, which a withdrawn root never gets. Made fully transparent
# instead of left at its default on-screen placement, so a test run doesn't
# flash a real window on screen for every one of these — the root stays
# mapped at its normal position/size (satisfying winfo_ismapped and normal
# layout) while being invisible. (An earlier version of this helper moved
# the root far off-screen via geometry() instead; that made Windows place
# it differently and broke test_autohide_scrollbar_starts_hidden_when_
# content_already_fits, so alpha=0 is used here instead.)


def _offscreen_tk_root() -> tk.Tk:
    root = tk.Tk()
    root.attributes("-alpha", 0.0)
    return root


def _make_autohide_listbox(root):
    frame = ttk.Frame(root)
    frame.pack(fill="both", expand=True)
    listbox = tk.Listbox(frame, height=3)
    scrollbar = AutoHideScrollbar(frame, orient="vertical", command=listbox.yview)
    listbox.configure(yscrollcommand=scrollbar.set)
    listbox.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    return frame, listbox, scrollbar


def test_autohide_scrollbar_starts_hidden_when_content_already_fits():
    root = _offscreen_tk_root()
    try:
        _frame, listbox, scrollbar = _make_autohide_listbox(root)
        for i in range(2):
            listbox.insert("end", f"item {i}")
        root.update()
        assert not scrollbar.winfo_ismapped()
    finally:
        root.destroy()


def test_autohide_scrollbar_appears_once_content_overflows():
    root = _offscreen_tk_root()
    try:
        _frame, listbox, scrollbar = _make_autohide_listbox(root)
        for i in range(50):
            listbox.insert("end", f"item {i}")
        root.update()
        assert scrollbar.winfo_ismapped()
    finally:
        root.destroy()


def test_autohide_scrollbar_hides_again_once_content_shrinks_back():
    root = _offscreen_tk_root()
    try:
        _frame, listbox, scrollbar = _make_autohide_listbox(root)
        for i in range(50):
            listbox.insert("end", f"item {i}")
        root.update()
        assert scrollbar.winfo_ismapped()

        listbox.delete(2, "end")  # back down to 2 items, fits within height=3
        root.update()
        assert not scrollbar.winfo_ismapped()
    finally:
        root.destroy()


def test_autohide_scrollbar_reappears_with_the_same_pack_geometry():
    # Confirms it replays the *original* pack() kwargs (side='right',
    # fill='y') rather than some default — a regression this exact bug
    # would silently pass "is mapped" but render in the wrong place.
    root = _offscreen_tk_root()
    try:
        _frame, listbox, scrollbar = _make_autohide_listbox(root)
        for i in range(50):
            listbox.insert("end", f"item {i}")
        root.update()
        info = scrollbar.pack_info()
        assert info["side"] == "right"
        assert info["fill"] == "y"
    finally:
        root.destroy()


def test_autohide_scrollbar_supports_grid_geometry_too():
    root = _offscreen_tk_root()
    try:
        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(frame, height=3)
        scrollbar = AutoHideScrollbar(frame, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        for i in range(50):
            listbox.insert("end", f"item {i}")
        root.update()
        assert scrollbar.winfo_ismapped()
        info = scrollbar.grid_info()
        assert info["row"] == 0
        assert info["column"] == 1
    finally:
        root.destroy()


def test_scrollbar_gutter_is_a_small_positive_pixel_value():
    assert 0 < SCROLLBAR_GUTTER <= 10


# --- design system: AutoHideScrollbar thumb-drag throttling ----------------
# Mouse-wheel scrolling was already coalesced to one canvas move per display
# frame (shell.py's _flush_page_scroll); a fast scrollbar thumb-drag had no
# equivalent and called straight through to the real yview command on every
# pointer-motion event, which is what produced the torn/partial repaints and
# stale doubled-up geometry caught on camera during a fast drag. These test
# the coalescing logic directly (bypassing real Tcl scrollbar events, which
# `winfo_ismapped`-style tests above already establish work) since what
# matters here is the call-batching behavior, not Tk's own drag mechanics.

def test_thumb_drag_moveto_calls_coalesce_to_one_with_the_latest_fraction():
    root = _offscreen_tk_root()
    try:
        calls = []
        scrollbar = AutoHideScrollbar(root, orient="vertical", command=lambda *a: calls.append(a))
        throttled = scrollbar._throttle_command(lambda *a: calls.append(a))
        for i in range(20):
            throttled("moveto", str(i / 20.0))
        root.update()
        assert calls == []  # nothing fires until the coalescing window elapses
        time.sleep(scrollbar._DRAG_FRAME_MS / 1000 + 0.03)
        root.update()
        assert calls == [("moveto", "0.95")]
    finally:
        root.destroy()


def test_arrow_click_scroll_calls_pass_through_immediately_uncoalesced():
    root = _offscreen_tk_root()
    try:
        calls = []
        scrollbar = AutoHideScrollbar(root, orient="vertical", command=lambda *a: calls.append(a))
        throttled = scrollbar._throttle_command(lambda *a: calls.append(a))
        throttled("scroll", 1, "units")
        throttled("scroll", 1, "units")
        root.update()
        assert calls == [("scroll", 1, "units"), ("scroll", 1, "units")]
    finally:
        root.destroy()


def test_pending_moveto_flushes_before_a_following_scroll_call():
    root = _offscreen_tk_root()
    try:
        calls = []
        scrollbar = AutoHideScrollbar(root, orient="vertical", command=lambda *a: calls.append(a))
        throttled = scrollbar._throttle_command(lambda *a: calls.append(a))
        throttled("moveto", "0.5")
        throttled("scroll", 1, "units")
        root.update()
        assert calls == [("moveto", "0.5"), ("scroll", 1, "units")]
    finally:
        root.destroy()


def test_scrollbar_still_wired_to_a_throttled_command_end_to_end():
    # Confirms __init__ actually wraps the constructor's command= argument
    # (not just that _throttle_command works in isolation): invoking the
    # widget's own registered Tcl command name directly -- exactly how Tk's
    # C-level scrollbar drag machinery invokes -command, no synthetic mouse
    # events needed -- must go through the same coalescing.
    root = _offscreen_tk_root()
    try:
        calls = []
        scrollbar = AutoHideScrollbar(root, orient="vertical", command=lambda *a: calls.append(a))
        root.update()
        tcl_command_name = scrollbar.cget("command")
        for i in range(10):
            scrollbar.tk.call(tcl_command_name, "moveto", str(i / 10.0))
        root.update()
        assert calls == []  # coalesced, not yet flushed
        time.sleep(scrollbar._DRAG_FRAME_MS / 1000 + 0.03)
        root.update()
        assert calls == [("moveto", "0.9")]
    finally:
        root.destroy()


# --- design system: Text-widget semantic tags ---------------------------

def test_configure_text_tags_matches_the_label_style_colors():
    root = tk.Tk()
    try:
        root.withdraw()
        text = tk.Text(root)
        configure_text_tags(text)
        p = palette()
        for tag, role in (("danger", "danger"), ("warn", "warn"),
                          ("success", "success"), ("hint", "hint")):
            assert text.tag_cget(tag, "foreground") == p[role]
    finally:
        root.destroy()
