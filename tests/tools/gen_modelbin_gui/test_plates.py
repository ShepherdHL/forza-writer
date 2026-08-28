"""Plates tab: library-scoped browsing (real-world/fictional/community/
custom, drill-down + breadcrumb), editing fields, live debounced preview,
generating, and saved configs. Follows the same invisible-Toplevel `gui`
fixture every other tab's tests use (conftest.py) -- no visible windows.
"""
import json
import sys
import time
from pathlib import Path
from tkinter import ttk

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))
import plate_config_store  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_plate_configs(tmp_path, monkeypatch):
    monkeypatch.setattr(plate_config_store, "CONFIGS_DIR", tmp_path / "plate_configs")


def _select_template(gui, template_id):
    """Jumps the browser straight to `template_id` regardless of its
    current library/drill position -- what a saved-config load does for
    real, and the standard test entry point so every test doesn't need to
    replay browser clicks by hand."""
    assert gui._plates_jump_to_template(template_id), f"{template_id!r} not found"


def _wait_for_plates_preview(gui, timeout=20):
    """Preview is live and debounced now (see tabs/plates.py's module
    docstring) -- pumps the event loop/queue until the debounce timer
    fires and the background render lands, the same wait pattern
    test_generate_writes_json_and_fabric_project already uses for Generate."""
    deadline = time.time() + timeout
    while gui._plates_photo is None and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)


def test_plates_tab_builds_and_lists_the_shipped_templates(gui):
    assert len(gui._plates_listed) >= 5


def test_switching_to_plates_tab_does_not_break_other_tabs(gui):
    gui._show_tab("plates")
    gui._show_tab("generator")
    gui._show_tab("plates")
    gui._show_tab("composer")
    # No assertion beyond "didn't raise" -- this is the regression guard
    # spec asks for: tab switching must not corrupt other tabs' state.


def test_page_scroll_region_stays_bounded(gui):
    # Real bug, reported directly: the mouse wheel scrolled this tab
    # indefinitely in both directions, well past its actual content.
    # Root cause: _build_plates_page's first _bind_responsive_columns call
    # passed `content` (the page's own scrollable frame, from
    # shell.py's _build_scroll_shell) straight in as *its own* parent --
    # and that call does `parent.bind('<Configure>', ...)` for its width-
    # threshold tracking. Tk's bind() replaces a widget's existing handler
    # for the same event rather than stacking handlers, so this silently
    # threw away _build_scroll_shell's own `content.bind('<Configure>',
    # ...)` that keeps the page canvas's scrollregion in sync. With no
    # scrollregion ever set, the canvas had nothing to clamp the view
    # against. Fixed by giving that call its own wrapper frame instead of
    # `content` itself. A real (non-alpha0-sized) window is needed here --
    # the responsive-column threshold logic this bug lives in only reacts
    # to genuine width changes.
    gui.root.geometry("1400x900")
    gui.root.update()
    gui._show_tab('plates')
    gui.root.update()
    canvas = gui._page_scroll_canvas['plates']
    region = canvas.cget('scrollregion')
    assert region != ''
    assert tuple(int(v) for v in region.split()) == canvas.bbox('all')

    canvas.yview_scroll(100000, 'units')
    gui.root.update()
    assert canvas.yview()[1] <= 1.0
    canvas.yview_scroll(-100000, 'units')
    gui.root.update()
    assert canvas.yview()[0] >= 0.0


# ---------------------------------------------------------------------------
# Library separation (the user's actual request: real-world and fictional
# must never share a browsing space) and drill-down browsing
# ---------------------------------------------------------------------------

def test_plates_library_separates_fictional_from_real_world():
    from gen_modelbin_gui.tabs.plates import _plate_library

    from forza_writer.plates.loader import list_templates, reload_templates
    reload_templates()
    by_id = {t.template_id: t for t in list_templates()}
    assert _plate_library(by_id["gta-sa-passenger-fictional"]) != _plate_library(by_id["us-ca-passenger-current"])
    assert _plate_library(by_id["gta-sa-passenger-fictional"]) == _plate_library(by_id["halo-reach-barcode-fictional"])


def test_real_world_root_shows_country_groups_not_individual_templates(gui):
    gui._set_plates_library("real")
    rows = gui.plates_template_tree.get_children()
    assert all(r.startswith("group:") for r in rows)
    assert "us-ca-passenger-current" not in rows


def test_fictional_root_never_shows_a_real_world_row(gui):
    gui._set_plates_library("fictional")
    rows = gui.plates_template_tree.get_children()
    assert "group:US" not in rows and "group:GB" not in rows
    assert "us-ca-passenger-current" not in rows


def test_single_jurisdiction_country_skips_straight_to_its_template(gui):
    # Germany has exactly one shipped template (jurisdiction=None) -- the
    # jurisdiction level has nothing to disambiguate, so clicking Germany's
    # group must land directly on its one template, not an intermediate
    # single-item "General" screen.
    gui._set_plates_library("real")
    tree = gui.plates_template_tree
    tree.selection_set("group:DE")
    gui._on_plates_row_selected()
    assert tree.get_children() == ("de-current-eu-band",)


# ---------------------------------------------------------------------------
# Real-world specialty-plate category skeleton (browsing/search plumbing
# for a 3rd "category" level -- Military/University/Organization/etc. --
# with no actual specialty templates shipped yet; see PLATE_CATEGORIES).
# ---------------------------------------------------------------------------

def test_category_level_stays_invisible_while_every_template_is_passenger(gui):
    # Today every real-world template is plate_type="passenger" -- the new
    # category level must auto-skip exactly like jurisdiction already does
    # for a single-jurisdiction country, so browsing today has zero extra
    # clicks. This is the explicit design choice (over always showing the
    # full category list, empty entries included) the user picked.
    gui._set_plates_library("real")
    tree = gui.plates_template_tree
    tree.selection_set("group:DE")
    gui._on_plates_row_selected()
    assert tree.get_children() == ("de-current-eu-band",)


def test_category_display_name_resolves_known_and_unknown_plate_types(gui):
    from gen_modelbin_gui.tabs.plates import _category_display_name

    assert _category_display_name("military") == "Military & Veteran"
    assert _category_display_name("university") == "University / College"
    assert _category_display_name("greek") == "Sorority / Fraternity"
    # A plate_type outside the registry (e.g. a fictional/custom template's
    # "police"/"commercial"/"custom") must still render something sane
    # rather than crash or show a raw underscored slug.
    assert _category_display_name("some_future_category") == "Some Future Category"


def test_category_level_activates_once_a_jurisdiction_has_two_categories(gui, monkeypatch):
    # Proves the level actually works once populated, without shipping any
    # real specialty template: synthesize a second California template
    # with a different plate_type and confirm the browser starts showing
    # a category picker instead of jumping straight to a template.
    import dataclasses

    import gen_modelbin_gui.tabs.plates as plates_module

    base = gui._plates_by_id["us-ca-passenger-current"]
    military = dataclasses.replace(base, template_id="us-ca-military-fictional-test", plate_type="military")
    extra_pool = list(plates_module.list_templates()) + [military]
    monkeypatch.setattr(plates_module, "list_templates", lambda: extra_pool)

    gui._set_plates_library("real")
    tree = gui.plates_template_tree
    tree.selection_set("group:US")
    gui._on_plates_row_selected()
    # Jurisdiction (CA) still has only one distinct value even with the
    # synthetic template added, so it auto-skips straight to category --
    # the new level, not an extra click.
    assert set(tree.get_children()) == {"group:passenger", "group:military"}


def test_multi_jurisdiction_franchise_shows_a_location_level(gui):
    # Halo has two distinct jurisdictions (New Mombasa, Reach) -- that
    # level must actually show up as a real choice, not be skipped.
    gui._set_plates_library("fictional")
    tree = gui.plates_template_tree
    tree.selection_set("group:HALO")
    gui._on_plates_row_selected()
    rows = set(tree.get_children())
    assert rows == {"group:New Mombasa", "group:Reach"}


def test_breadcrumb_reflects_the_drill_path(gui):
    _select_template(gui, "halo-reach-barcode-fictional")
    texts = [c.cget("text") for c in gui.plates_breadcrumb_row.winfo_children()
             if hasattr(c, "cget") and c.winfo_class() in ("TLabel",)]
    joined = " ".join(texts)
    assert "Fictional" in joined and "Halo" in joined and "Reach" in joined


def test_breadcrumb_click_navigates_back_up(gui):
    gui._set_plates_library("fictional")
    tree = gui.plates_template_tree
    tree.selection_set("group:HALO")
    gui._on_plates_row_selected()
    all_franchises = {"group:CP2077", "group:DL", "group:GTA", "group:HALO", "group:MEDGE", "group:NFS", "group:PHAS", "group:SR"}
    assert tree.get_children() != tuple(sorted(all_franchises))
    gui._plates_breadcrumb_jump(None)  # click the library-root crumb
    assert set(tree.get_children()) == all_franchises


def test_back_button_retraces_navigation_one_step_at_a_time(gui):
    tree = gui.plates_template_tree
    gui._set_plates_library("fictional")
    # selection_set() fires <<TreeviewSelect>> asynchronously (queued, not
    # run inline) -- root.update() between each click lets the handler for
    # the previous one actually run before the tree it repopulates is
    # queried for the next row, the same as real mouse clicks a beat apart.
    tree.selection_set("group:HALO")
    gui.root.update()
    tree.selection_set("group:Reach")
    gui.root.update()
    tree.selection_set("halo-reach-barcode-fictional")
    gui.root.update()
    assert len(gui._plates_nav_history) == 4  # library switch + 3 drill/select steps
    assert gui._plates_template.template_id == "halo-reach-barcode-fictional"

    gui._plates_go_back()
    assert gui._plates_template is None
    assert set(tree.get_children()) == {"halo-reach-barcode-fictional", "halo-reach-standard-fictional"}

    gui._plates_go_back()
    assert gui._plates_breadcrumb == [(0, "HALO")]
    assert set(tree.get_children()) == {"group:New Mombasa", "group:Reach"}

    gui._plates_go_back()
    assert gui._plates_breadcrumb == []
    assert gui._plates_library == "fictional"

    gui._plates_go_back()
    assert gui._plates_library == "real"
    assert gui._plates_nav_history == []


def test_back_button_works_after_loading_a_saved_config(gui):
    # _load_plate_config reaches its template via _plates_jump_to_template,
    # a bare teleport that never pushed history on its own (it's also used
    # as the _select_template test helper below, which deliberately doesn't
    # touch nav_history). Without a push somewhere on the *real* load path,
    # Back had nothing to retrace to the moment a plate was reached via a
    # saved config -- the button came up permanently disabled, not just
    # visually inert like the single-template case above. Reproduced this
    # directly (a fresh gui, load a saved fictional-plate config, check the
    # actual back_btn widget state) before writing the fix.
    _select_template(gui, "halo-reach-barcode-fictional")
    instance = gui._current_plate_instance()
    plate_config_store.save_plate_config("back-button-repro", instance)
    gui._clear_plates_selection()
    gui._plates_nav_history = []  # isolate: only test what loading itself does, from nothing selected

    gui._load_plate_config("back-button-repro")
    assert gui._plates_template.template_id == "halo-reach-barcode-fictional"
    assert gui._plates_nav_history != []
    back_btn = gui.plates_breadcrumb_row.winfo_children()[0]
    assert 'disabled' not in back_btn.state()

    back_btn.invoke()
    gui.root.update()
    assert gui._plates_template is None


def test_back_button_disabled_with_empty_history(gui):
    assert gui._plates_nav_history == []
    gui._plates_go_back()  # must not raise with nothing to go back to
    assert gui._plates_nav_history == []


def test_back_from_a_single_template_franchise_returns_to_a_different_view(gui):
    # GTA has exactly one shipped template, so its group row is never a real
    # choice among options -- selecting it doesn't get its own history stop
    # (see _on_plates_row_selected). Before that fix, Back from here
    # restored the *identical* one-row list (only the detail panel
    # cleared), which read as "Back does nothing" -- this is that bug
    # report, reproduced directly.
    tree = gui.plates_template_tree
    gui._set_plates_library("fictional")
    tree.selection_set("group:GTA")
    gui.root.update()
    assert tuple(tree.get_children()) == ("gta-sa-passenger-fictional",)
    tree.selection_set("gta-sa-passenger-fictional")
    gui.root.update()
    assert gui._plates_template.template_id == "gta-sa-passenger-fictional"

    gui._plates_go_back()
    assert gui._plates_template is None
    # Back must land somewhere visibly different from the one-row list the
    # user was just looking at -- the full franchise list, not the same
    # single GTA row with nothing selected.
    assert set(tree.get_children()) == {
        "group:CP2077", "group:DL", "group:GTA", "group:HALO", "group:MEDGE", "group:NFS", "group:PHAS", "group:SR"}
    assert gui._plates_breadcrumb == []


def test_community_library_shows_an_explicit_empty_state(gui):
    gui._set_plates_library("community")
    rows = gui.plates_template_tree.get_children()
    assert rows == ("empty",)
    text = gui.plates_template_tree.item("empty", "text")
    assert text  # a real message, not a blank/placeholder row


def test_custom_library_shows_the_blank_template_with_no_mode_selector(gui):
    _select_template(gui, "custom-blank")
    assert gui._plates_template.template_id == "custom-blank"
    assert not gui.plates_mode_frame.winfo_ismapped()  # no "Authentic" baseline for a template tied to nothing


def test_plates_browser_shows_resolved_display_names_not_raw_keys(gui):
    for template in gui._plates_listed:
        _select_template(gui, template.template_id)
        label = gui.plates_template_tree.item(template.template_id, "text")
        assert template.display_name_key not in label


def test_details_writes_to_the_log_not_a_modal_dialog(gui):
    # A modal messagebox blocked the whole workspace for content the user
    # only ever reads -- moved to the shared Log panel instead, which is
    # visible regardless of tab and keeps its own scrollback so provenance
    # notes from several plates stay comparable side by side.
    from gen_modelbin_gui.tabs.plates import _format_plate_details

    _select_template(gui, "gta-sa-passenger-fictional")
    before = gui.log.get('1.0', 'end-1c')
    gui._show_plates_details()
    after = gui.log.get('1.0', 'end-1c')
    assert after != before
    for line in _format_plate_details(gui._plates_template).split('\n'):
        if line:
            assert line in after


# ---------------------------------------------------------------------------
# Search: scoped to the active library, flattens straight to matching leaves
# ---------------------------------------------------------------------------

def test_search_scopes_to_the_active_library(gui):
    gui._set_plates_library("real")
    gui.plates_search_var.set("barcode")  # only exists in the fictional library
    gui._refresh_plates_browser()
    assert gui.plates_template_tree.get_children() == ("empty",)

    gui._set_plates_library("fictional")
    gui.plates_search_var.set("barcode")
    gui._refresh_plates_browser()
    assert gui.plates_template_tree.get_children() == ("halo-reach-barcode-fictional",)

    gui.plates_search_var.set("")
    gui._refresh_plates_browser()


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------

def test_selecting_a_template_populates_field_entries(gui):
    _select_template(gui, "gb-current-standard")
    assert "registration" in gui._plates_field_vars
    assert gui._plates_field_vars["registration"].get() == "AB12 CDE"


def test_switching_templates_replaces_field_entries_cleanly(gui):
    _select_template(gui, "gb-current-standard")
    assert set(gui._plates_field_vars) == {"registration"}
    _select_template(gui, "jp-private-passenger-current")
    assert set(gui._plates_field_vars) == {"region_kanji", "classification_number", "hiragana", "serial"}


def test_field_labels_show_resolved_text_not_raw_keys(gui):
    _select_template(gui, "us-ca-passenger-current")
    labels = [
        child.cget("text") for row in gui.plates_fields_body.winfo_children()
        for child in row.winfo_children() if isinstance(child, ttk.Label)
    ]
    assert "jurisdiction_header" not in labels  # the raw field_id/label_key, not a resolved label
    assert any("Header" in label or "California" in label for label in labels)


def test_multi_field_template_groups_related_fields(gui):
    # Japan's four fields (registration + region/classification/hiragana)
    # span two role groups -- confirms the field editor is actually
    # grouping, not just relabeling one flat list.
    _select_template(gui, "jp-private-passenger-current")
    headers = [
        child.cget("text") for child in gui.plates_fields_body.winfo_children()
        if isinstance(child, ttk.Label) and child.cget("style") == "Category.TLabel"
    ]
    assert len(headers) >= 2


# ---------------------------------------------------------------------------
# Live preview: auto-renders (debounced), no manual button anymore
# ---------------------------------------------------------------------------

def test_selecting_a_template_eventually_renders_a_live_preview(gui):
    _select_template(gui, "custom-blank")
    _wait_for_plates_preview(gui)
    assert gui._plates_photo is not None
    assert "shapes" in gui.plates_shape_count_var.get()


def test_typing_in_a_field_schedules_a_new_preview_render(gui):
    _select_template(gui, "custom-blank")
    _wait_for_plates_preview(gui)
    gui._plates_photo = None
    gui.plates_canvas.delete("all")
    gui._plates_field_vars["registration"].set("SOMETHING ELSE")
    _wait_for_plates_preview(gui)
    assert gui._plates_photo is not None


# ---------------------------------------------------------------------------
# Validation hints (cheap -- no font/shape work, always live)
# ---------------------------------------------------------------------------

def test_authentic_mode_invalid_text_shows_a_field_specific_hint(gui):
    _select_template(gui, "us-ca-passenger-current")
    gui.plates_mode_var.set("authentic")
    gui._on_plates_mode_changed()
    gui._plates_field_vars["registration"].set("1IBC234")  # 'I' in the excluded first-letter position
    gui._update_plates_validation_hints()
    gui.root.update_idletasks()
    hint = gui._plates_field_hint_labels["registration"]
    assert hint.winfo_ismapped()
    assert hint.cget("text") != ""


def test_authentic_mode_valid_text_shows_no_hint(gui):
    _select_template(gui, "us-ca-passenger-current")
    gui.plates_mode_var.set("authentic")
    gui._on_plates_mode_changed()
    gui._update_plates_validation_hints()  # default_text is a valid example
    gui.root.update_idletasks()
    hint = gui._plates_field_hint_labels["registration"]
    assert not hint.winfo_ismapped()


# ---------------------------------------------------------------------------
# Plate Rules (mode) terminology adapts per library -- "Authentic" is never
# forced onto fictional content
# ---------------------------------------------------------------------------

def test_mode_terminology_is_authentic_for_real_world(gui):
    _select_template(gui, "us-ca-passenger-current")
    assert gui.plates_mode_baseline_radio.cget("text") == "Authentic"


def test_mode_terminology_is_source_accurate_for_fictional(gui):
    _select_template(gui, "gta-sa-passenger-fictional")
    assert gui.plates_mode_baseline_radio.cget("text") == "Source Accurate"


def test_vanity_badge_shows_only_in_customized_mode(gui):
    # custom-blank has no mode selector at all (nothing to be "authentic"
    # to -- see test_custom_library_shows_the_blank_template_with_no_mode_selector),
    # so this needs a template that actually has one.
    _select_template(gui, "us-ca-passenger-current")
    gui.plates_mode_var.set("vanity")
    gui._on_plates_mode_changed()
    gui.root.update_idletasks()
    assert gui.plates_vanity_badge.winfo_ismapped()
    gui.plates_mode_var.set("authentic")
    gui._on_plates_mode_changed()
    gui.root.update_idletasks()
    assert not gui.plates_vanity_badge.winfo_ismapped()


# ---------------------------------------------------------------------------
# Details panel
# ---------------------------------------------------------------------------

def test_details_panel_labels_country_as_franchise_for_fictional_plates(gui):
    from gen_modelbin_gui.tabs.plates import _format_plate_details
    _select_template(gui, "gta-sa-passenger-fictional")
    text = _format_plate_details(gui._plates_template)
    assert "Franchise: Grand Theft Auto V" in text
    assert "Country:" not in text  # real-world-only label must not leak into fictional output


def test_details_panel_labels_country_for_real_world_plates(gui):
    from gen_modelbin_gui.tabs.plates import _format_plate_details
    _select_template(gui, "us-ca-passenger-current")
    text = _format_plate_details(gui._plates_template)
    assert "Country: United States" in text


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

def test_generate_blocked_in_authentic_mode_with_invalid_text(gui):
    _select_template(gui, "us-ca-passenger-current")
    gui.plates_mode_var.set("authentic")
    gui._on_plates_mode_changed()
    gui._plates_field_vars["registration"].set("1IBC234")
    gui._generate_plate()
    assert "Fix the highlighted" in gui.plates_generate_status_var.get() or \
        gui.plates_generate_status_var.get() != ""


def test_generate_writes_json_and_fabric_project(gui, tmp_path, monkeypatch):
    # Plates has its own dedicated output directory (data/plates, not a
    # subfolder of the shared fontpacks out_var -- see _PLATES_OUTPUT_DIR's
    # own comment for why), so isolating this test means monkeypatching
    # that constant directly rather than out_var. An earlier version of
    # this test didn't and leaked real files into the actual repo's
    # data/plates/ the moment out_dir stopped being derived from out_var.
    import gen_modelbin_gui.tabs.plates as plates_module
    monkeypatch.setattr(plates_module, "_PLATES_OUTPUT_DIR", tmp_path)

    _select_template(gui, "custom-blank")
    gui._generate_plate()

    # _generate_plate sets status to "Rendering..." immediately (before the
    # background render/write even starts), so waiting for merely
    # non-empty would exit before the real work finished -- wait for it to
    # change to something else instead.
    deadline = time.time() + 20
    while gui.plates_generate_status_var.get() in ("", "Rendering...") and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)

    assert "Generated" in gui.plates_generate_status_var.get()
    json_path = tmp_path / "custom-blank.json"
    fabric_path = tmp_path / "custom-blank.fabric-project.json"
    assert json_path.exists()
    assert fabric_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "shapes" in data and "plate_groups" in data
    assert len(data["shapes"]) > 0

    project = json.loads(fabric_path.read_text(encoding="utf-8"))
    assert project["format"] == "kloudy_fabric_editor_project_v1"
    assert len(project["shapes"]) == len(data["shapes"])


# ---------------------------------------------------------------------------
# Saved configs -- a compact menu near the header now, not a full-width strip
# ---------------------------------------------------------------------------

def test_send_to_kfps_disabled_until_a_plate_is_generated(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui.tabs.plates as plates_module
    monkeypatch.setattr(plates_module, "_PLATES_OUTPUT_DIR", tmp_path)

    _select_template(gui, "custom-blank")
    assert str(gui.plates_send_kfps_btn["state"]) == "disabled"

    gui._generate_plate()
    deadline = time.time() + 20
    while gui.plates_generate_status_var.get() in ("", "Rendering...") and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)
    assert str(gui.plates_send_kfps_btn["state"]) == "normal"

    # Switching to a different plate makes the just-generated file stale --
    # Send to KFPS must not keep offering to send it.
    _select_template(gui, "gb-current-standard")
    assert str(gui.plates_send_kfps_btn["state"]) == "disabled"


def test_send_to_kfps_without_a_configured_path_shows_a_message(gui, tmp_path, monkeypatch):
    import gen_modelbin_gui.tabs.plates as plates_module
    monkeypatch.setattr(plates_module, "_PLATES_OUTPUT_DIR", tmp_path)
    gui.kfps_executable_var.set("")

    _select_template(gui, "custom-blank")
    gui._generate_plate()
    deadline = time.time() + 20
    while gui.plates_generate_status_var.get() in ("", "Rendering...") and time.time() < deadline:
        gui._poll_queue()
        gui.root.update()
        time.sleep(0.05)

    gui._send_plate_to_kfps()
    assert "Settings" in gui.plates_generate_status_var.get()


def test_placeholder_font_defaults_to_boxes(gui):
    _select_template(gui, "custom-blank")
    assert gui._current_plate_instance().placeholder_font is None


def test_placeholder_font_selection_flows_into_the_instance(gui):
    _select_template(gui, "custom-blank")
    gui.plates_placeholder_font_combo.current(7)  # _PLACEHOLDER_FONT_CHOICES[7] == Forza Font 7
    gui._on_plates_placeholder_font_changed()
    assert gui._current_plate_instance().placeholder_font == 7


def test_placeholder_font_choice_persists_across_template_switches(gui):
    _select_template(gui, "custom-blank")
    gui.plates_placeholder_font_combo.current(3)
    gui._on_plates_placeholder_font_changed()
    _select_template(gui, "gb-current-standard")
    assert gui._current_plate_instance().placeholder_font == 3


def test_placeholder_font_renders_a_live_preview(gui):
    _select_template(gui, "custom-blank")
    gui.plates_placeholder_font_combo.current(7)
    gui._on_plates_placeholder_font_changed()
    _wait_for_plates_preview(gui)
    assert gui._plates_photo is not None


def _fake_kfps_with_vinyls(tmp_path):
    """A fake KFPS install exposing just enough of the real layout for
    file_preview.kfps_vinyls_dir to resolve it -- no actual glyph PNGs
    needed for these tests, which only check the caveat message, not the
    rendered pixels (file_preview's own tests cover the glyph compositing
    itself)."""
    (tmp_path / "tools" / "fabric-editor" / "Resources" / "Vinyls").mkdir(parents=True)
    exe = tmp_path / "KFPS.exe"
    exe.write_bytes(b"")
    return str(exe)


def test_placeholder_font_preview_caveat_when_kfps_not_configured(gui):
    from gen_modelbin_gui.i18n import t

    gui.kfps_executable_var.set("")
    _select_template(gui, "custom-blank")
    _wait_for_plates_preview(gui)
    gui._plates_photo = None  # force the wait below onto the *next* render
    gui.plates_placeholder_font_combo.current(7)
    gui._on_plates_placeholder_font_changed()
    _wait_for_plates_preview(gui)
    assert t('plates.preview.font_not_shown') in gui.plates_shape_count_var.get()


def test_placeholder_font_preview_no_caveat_once_kfps_vinyls_found(gui, tmp_path):
    from gen_modelbin_gui.i18n import t

    gui.kfps_executable_var.set(_fake_kfps_with_vinyls(tmp_path))
    _select_template(gui, "custom-blank")
    _wait_for_plates_preview(gui)
    gui._plates_photo = None
    gui.plates_placeholder_font_combo.current(7)
    gui._on_plates_placeholder_font_changed()
    _wait_for_plates_preview(gui)
    assert t('plates.preview.font_not_shown') not in gui.plates_shape_count_var.get()


def test_no_placeholder_font_preview_never_shows_the_caveat(gui):
    from gen_modelbin_gui.i18n import t

    gui.kfps_executable_var.set("")
    _select_template(gui, "custom-blank")
    _wait_for_plates_preview(gui)
    assert t('plates.preview.font_not_shown') not in gui.plates_shape_count_var.get()


def test_save_and_load_plate_config_round_trips_field_values(gui):
    _select_template(gui, "custom-blank")
    gui._plates_field_vars["registration"].set("HELLO")
    gui.plates_mode_var.set("vanity")
    gui._on_plates_mode_changed()
    gui.plates_placeholder_font_combo.current(7)
    gui._on_plates_placeholder_font_changed()

    instance = gui._current_plate_instance()
    plate_config_store.save_plate_config("my-test-config", instance)

    # Switch away, then load back -- confirms load actually restores state
    # rather than the test trivially passing because nothing changed.
    _select_template(gui, "gb-current-standard")
    gui.plates_mode_var.set("authentic")
    gui._on_plates_mode_changed()
    gui.plates_placeholder_font_combo.current(0)
    gui._on_plates_placeholder_font_changed()

    gui._load_plate_config("my-test-config")
    assert gui._plates_template.template_id == "custom-blank"
    assert gui.plates_mode_var.get() == "vanity"
    assert gui._plates_field_vars["registration"].get() == "HELLO"
    from gen_modelbin_gui.tabs.plates import _PLACEHOLDER_FONT_CHOICES
    assert gui.plates_placeholder_font_var.get() == 7
    assert gui.plates_placeholder_font_combo.current() == _PLACEHOLDER_FONT_CHOICES.index(7)


def test_delete_plate_config_removes_it(gui):
    _select_template(gui, "custom-blank")
    plate_config_store.save_plate_config("to-delete", gui._current_plate_instance())
    assert "to-delete" in plate_config_store.list_plate_configs()
    gui._delete_plate_config("to-delete")
    assert "to-delete" not in plate_config_store.list_plate_configs()


def test_saved_config_menu_lists_saved_names(gui):
    _select_template(gui, "custom-blank")
    plate_config_store.save_plate_config("menu-test", gui._current_plate_instance())
    gui._refresh_plates_config_menu()
    labels = [gui.plates_config_menu.entrycget(i, "label")
              for i in range(gui.plates_config_menu.index("end") + 1)
              if gui.plates_config_menu.type(i) == "cascade"]
    assert "menu-test" in labels
