"""Glyph Inspector's Compare-mode focus readout, filmstrip, and ledger.

These drive the real render/focus methods directly against a synthetic
metrics dict shaped exactly like forza_writer.glyph_quality.compare_masks()'s
real return value, rather than running the full async font-load + fit-
generation pipeline through real font assets -- that pipeline has no
dedicated test coverage of its own yet, and reproducing it here would be
a much larger undertaking than this change's actual scope. What's tested
here is the logic this change actually adds: shortfall flagging, palette-
correct coloring, verdict mapping, and filmstrip focus navigation.
"""
import gui_theme

SAMPLE_METRICS = {
    'resolution': 128, 'iou': 0.947, 'precision': 0.95, 'recall': 0.94, 'boundary_f1': 0.912,
    'components_expected': 2, 'components_generated': 2,
    'holes_expected': 2, 'holes_generated': 1,
    'unknown_type_words': [], 'verdict': 'review',
}


def _set_metrics(gui, **overrides):
    metrics = dict(SAMPLE_METRICS, **overrides)
    gui._glyph_inspector_compare_metrics = metrics
    return metrics


def test_shortfall_flags_only_count_metrics_that_fall_short(gui):
    _set_metrics(gui, components_generated=2, components_expected=2,
                 holes_generated=1, holes_expected=2)
    assert gui._glyph_inspector_compare_metric_shortfall('components') is False
    assert gui._glyph_inspector_compare_metric_shortfall('holes') is True


def test_shortfall_never_flags_percentage_metrics(gui):
    # No invented numeric threshold for IoU/boundary F1 -- compare_masks()
    # doesn't supply one, so these are never individually flagged
    # regardless of value.
    _set_metrics(gui, iou=0.01, boundary_f1=0.02)
    assert gui._glyph_inspector_compare_metric_shortfall('iou') is False
    assert gui._glyph_inspector_compare_metric_shortfall('boundary_f1') is False


def test_shortfall_generated_exceeding_expected_is_not_flagged(gui):
    _set_metrics(gui, components_generated=3, components_expected=2)
    assert gui._glyph_inspector_compare_metric_shortfall('components') is False


def test_compare_focus_defaults_to_iou_and_renders_a_ring_gauge(gui):
    _set_metrics(gui)
    gui._glyph_inspector_compare_focus_index = 0
    gui._render_glyph_inspector_compare_focus()
    assert gui._glyph_inspector_compare_focus_photo is not None
    assert str(gui.glyph_inspector_compare_focus_label.cget('image')) != ''


def test_compare_focus_selected_card_uses_the_accent_color(gui):
    p = gui_theme.palette()
    _set_metrics(gui)
    gui._set_glyph_inspector_compare_focus('holes')
    assert gui._glyph_inspector_compare_focus_index == 3
    cards = gui._glyph_inspector_compare_cards
    assert cards['holes'].cget('bg') == p['accent']
    assert cards['iou'].cget('bg') == p['panel_alt']


def test_compare_focus_shortfall_card_is_danger_colored_when_not_selected(gui):
    p = gui_theme.palette()
    _set_metrics(gui, holes_generated=1, holes_expected=2)
    gui._set_glyph_inspector_compare_focus('iou')  # focus elsewhere
    assert gui._glyph_inspector_compare_cards['holes'].cget('fg') == p['danger']
    assert gui._glyph_inspector_compare_cards['components'].cget('fg') == p['fg']


def test_set_focus_ignores_an_unknown_key(gui):
    _set_metrics(gui)
    gui._set_glyph_inspector_compare_focus('holes')
    gui._set_glyph_inspector_compare_focus('not_a_real_metric')
    assert gui._glyph_inspector_compare_focus_index == 3  # unchanged


def test_step_focus_wraps_in_both_directions(gui):
    _set_metrics(gui)
    gui._glyph_inspector_compare_focus_index = 0
    gui._step_glyph_inspector_compare_focus(-1)
    assert gui._glyph_inspector_compare_focus_index == 3  # wrapped backward past the start
    gui._step_glyph_inspector_compare_focus(1)
    assert gui._glyph_inspector_compare_focus_index == 0  # back to the start
    gui._step_glyph_inspector_compare_focus(1)
    assert gui._glyph_inspector_compare_focus_index == 1


def test_step_focus_does_nothing_before_any_compare_has_run(gui):
    gui._glyph_inspector_compare_metrics = None
    gui._glyph_inspector_compare_focus_index = 0
    gui._step_glyph_inspector_compare_focus(1)
    assert gui._glyph_inspector_compare_focus_index == 0


def test_arrow_key_in_compare_mode_steps_focus_not_the_glyph_grid(gui):
    import types
    _set_metrics(gui)
    gui._glyph_inspector_compare_focus_index = 0
    gui._current_tab = 'glyph_inspector'
    gui.glyph_inspector_mode_var.set('compare')
    selected_before = gui._glyph_inspector_selected_glyph
    gui._on_glyph_inspector_key(types.SimpleNamespace(keysym='Right', widget=gui.root))
    assert gui._glyph_inspector_compare_focus_index == 1
    assert gui._glyph_inspector_selected_glyph is selected_before  # glyph selection untouched


def test_ledger_colors_a_shortfall_metric_as_danger(gui):
    p = gui_theme.palette()
    _set_metrics(gui, holes_generated=1, holes_expected=2, components_generated=2, components_expected=2)
    gui._render_glyph_inspector_compare_ledger()
    labels = gui._glyph_inspector_compare_ledger_labels
    assert labels['holes'].cget('fg') == p['danger']
    assert labels['holes'].cget('text') == '1 / 2'
    assert labels['components'].cget('fg') == p['fg']
    assert labels['components'].cget('text') == '2 / 2'


def test_ledger_formats_percentage_metrics_to_three_decimals(gui):
    _set_metrics(gui, iou=0.94651, boundary_f1=0.9)
    gui._render_glyph_inspector_compare_ledger()
    labels = gui._glyph_inspector_compare_ledger_labels
    assert labels['iou'].cget('text') == '0.947'
    assert labels['boundary_f1'].cget('text') == '0.900'


def test_ledger_verdict_pass_is_success_colored(gui):
    p = gui_theme.palette()
    _set_metrics(gui, verdict='pass')
    gui._render_glyph_inspector_compare_ledger()
    assert gui.glyph_inspector_compare_verdict.cget('fg') == p['success']
    assert 'PASS' in gui.glyph_inspector_compare_verdict.cget('text')


def test_ledger_verdict_review_is_warn_colored(gui):
    p = gui_theme.palette()
    _set_metrics(gui, verdict='review')
    gui._render_glyph_inspector_compare_ledger()
    assert gui.glyph_inspector_compare_verdict.cget('fg') == p['warn']
    assert 'REVIEW' in gui.glyph_inspector_compare_verdict.cget('text')


def test_ledger_raises_loudly_on_an_unrecognized_verdict(gui):
    # compare_masks() only ever returns "pass"/"review" -- silently
    # defaulting to one of them here would misreport a result the
    # underlying data doesn't actually support.
    import pytest
    _set_metrics(gui, verdict='something_else')
    with pytest.raises(ValueError):
        gui._render_glyph_inspector_compare_ledger()


def test_leaving_compare_mode_clears_the_stored_metrics(gui):
    _set_metrics(gui)
    gui._update_glyph_inspector_compare_row('reference')
    assert gui._glyph_inspector_compare_metrics is None
