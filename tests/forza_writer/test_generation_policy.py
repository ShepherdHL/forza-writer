"""Generation policy: allowed/preferred primitives, fallback, presets, stats."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "tools"))

from forza_writer.generation_policy import (  # noqa: E402
    ALL_SHAPE_IDS, DEFAULT_POLICY, EXACT_COVER_SHAPE, FALLBACK_MODES, PRESETS,
    RECOMMENDED_PRESET, TRIANGLE_FALLBACK_SHAPES, GenerationPolicy, GenerationStats,
    preset_name_for)
from forza_writer.primitive_fit import fit_placements, fit_silhouette  # noqa: E402
from forza_writer.primitive_shapes import PRIMITIVE_CATALOG  # noqa: E402

# A rectilinear L: solvable exactly by rectangle decomposition, so it also
# exercises the exact-cover routes that structurally require Square.
L_CONTOURS = [[(-60, -60), (20, -60), (20, 0), (-20, 0), (-20, 60), (-60, 60)]]


def _square_mask(resolution: int = 64) -> np.ndarray:
    mask = np.zeros((resolution, resolution), dtype=bool)
    mask[16:48, 16:48] = True
    return mask


# --- the catalog is the single source of truth --------------------------

def test_all_shape_ids_tracks_the_catalog_rather_than_a_duplicate_list():
    # The requirement is explicitly that the shape list is populated from the
    # real catalog, not a parallel hard-coded copy that can drift from it.
    assert ALL_SHAPE_IDS == frozenset(PRIMITIVE_CATALOG)


def test_default_policy_allows_every_catalog_shape():
    assert DEFAULT_POLICY.allowed == ALL_SHAPE_IDS
    assert list(DEFAULT_POLICY.shapes()) == list(PRIMITIVE_CATALOG.values())


def test_shapes_are_yielded_in_catalog_order_not_set_order():
    # Set iteration order would make tied candidates resolve differently
    # between runs; catalog order keeps a fit reproducible.
    policy = DEFAULT_POLICY.with_allowed({"triangle", "square", "circle"})
    ordered = [s.shape_id for s in policy.shapes()]
    assert ordered == [sid for sid in PRIMITIVE_CATALOG if sid in policy.allowed]


# --- no regression: the default must behave exactly as before ------------

def test_default_policy_reproduces_unrestricted_fitting_exactly():
    mask = _square_mask()
    assert (fit_silhouette(mask, 64, policy=DEFAULT_POLICY)
            == fit_silhouette(mask, 64))


def test_balanced_preset_is_the_default_policy():
    assert PRESETS[RECOMMENDED_PRESET] == DEFAULT_POLICY


def test_explicit_tuning_arguments_still_win_over_the_policy():
    # Existing callers pass these positionally; the policy supplies defaults
    # only where the caller stayed silent.
    policy = GenerationPolicy(max_layers=32)
    assert len(fit_silhouette(_square_mask(), 64, max_layers=1, policy=policy)) <= 1


# --- allowed: a hard restriction ----------------------------------------

def test_restricting_allowed_shapes_excludes_them_from_the_result():
    placements = fit_silhouette(_square_mask(), 64,
                                policy=DEFAULT_POLICY.with_allowed({"circle"}))
    assert placements
    assert {p.shape_id for p in placements} == {"circle"}


def test_empty_allowed_set_produces_no_placements_rather_than_crashing():
    assert fit_silhouette(_square_mask(), 64,
                          policy=DEFAULT_POLICY.with_allowed(set())) == []


def test_allowed_restriction_reduces_the_candidates_actually_generated():
    # Disallowed shapes must never become candidates at all: restricting the
    # set should make the search cheaper, not merely filter its output.
    wide, narrow = GenerationStats(), GenerationStats()
    fit_silhouette(_square_mask(), 64, policy=DEFAULT_POLICY, stats=wide)
    fit_silhouette(_square_mask(), 64, stats=narrow,
                   policy=DEFAULT_POLICY.with_allowed({"circle"}))
    assert narrow.candidates_tested < wide.candidates_tested


# --- preferred: a soft bias ---------------------------------------------

def test_preference_scales_positive_gains_only():
    policy = GenerationPolicy(preferred=frozenset({"square"}), preference_bonus=0.1)
    assert policy.score("square", 100.0) == pytest.approx(110.0)
    assert policy.score("circle", 100.0) == pytest.approx(100.0)


def test_preference_never_pushes_a_bad_candidate_further_down():
    # Scaling a negative gain would rank a preferred shape below an equally
    # poor unpreferred one, inverting what a preference means.
    policy = GenerationPolicy(preferred=frozenset({"square"}), preference_bonus=0.5)
    assert policy.score("square", -40.0) == -40.0


def test_preference_does_not_override_a_clearly_better_shape():
    # An exact square target is fit perfectly by Square; an 8% tie-break must
    # not be able to displace that.
    policy = GenerationPolicy(preferred=frozenset({"circle"}))
    placements = fit_silhouette(_square_mask(), 64, policy=policy)
    assert placements[0].shape_id == "square"


# --- exact-cover strategies structurally need Square --------------------

def test_default_policy_solves_a_rectilinear_glyph_with_exact_cover():
    _placements, strategy = fit_placements(L_CONTOURS, 64)
    assert strategy == "rect_decompose"


def test_disallowing_square_routes_around_exact_cover_instead_of_asserting():
    # rect_decompose asserts that Square exists; withholding it must skip the
    # whole strategy rather than reach that assertion.
    policy = DEFAULT_POLICY.with_allowed(ALL_SHAPE_IDS - {EXACT_COVER_SHAPE})
    assert not policy.allows_exact_cover
    placements, strategy = fit_placements(L_CONTOURS, 64, policy=policy)
    assert strategy == "primitive_search"
    assert EXACT_COVER_SHAPE not in {p.shape_id for p in placements}


def test_allow_exact_cover_false_forces_the_search_even_with_square_allowed():
    policy = GenerationPolicy(allow_exact_cover=False)
    assert EXACT_COVER_SHAPE in policy.allowed
    assert not policy.allows_exact_cover
    _placements, strategy = fit_placements(L_CONTOURS, 64, policy=policy)
    assert strategy == "primitive_search"


# --- fallback ------------------------------------------------------------

def _over_restricted(mode: str) -> GenerationPolicy:
    """Circle alone cannot cover a rectilinear L to the quality target."""
    return GenerationPolicy(allowed=frozenset({"circle"}), fallback=mode)


def test_strict_fallback_keeps_the_restriction_even_when_it_falls_short():
    stats = GenerationStats()
    fit_placements(L_CONTOURS, 64, policy=_over_restricted("strict"), stats=stats)
    assert set(stats.by_shape) == {"circle"}
    assert stats.fallback_used is False
    assert stats.iou < DEFAULT_POLICY.quality_target


def test_warn_fallback_keeps_the_restriction_but_reports_the_shortfall():
    stats = GenerationStats()
    fit_placements(L_CONTOURS, 64, policy=_over_restricted("warn"), stats=stats)
    assert set(stats.by_shape) == {"circle"}
    assert stats.fallback_used is False
    assert stats.warnings, "warn mode must explain why the selection fell short"


def test_auto_fallback_widens_to_the_full_catalog_and_improves_the_fit():
    strict, auto = GenerationStats(), GenerationStats()
    fit_placements(L_CONTOURS, 64, policy=_over_restricted("strict"), stats=strict)
    fit_placements(L_CONTOURS, 64, policy=_over_restricted("auto"), stats=auto)
    assert auto.fallback_used is True
    assert auto.iou > strict.iou
    assert set(auto.by_shape) - {"circle"}


def test_triangle_fallback_adds_only_triangles():
    stats = GenerationStats()
    fit_placements(L_CONTOURS, 64, policy=_over_restricted("triangle"), stats=stats)
    assert stats.fallback_used is True
    assert set(stats.by_shape) <= {"circle"} | set(TRIANGLE_FALLBACK_SHAPES)


def test_fallback_records_a_reason_so_it_is_never_silent():
    stats = GenerationStats()
    fit_placements(L_CONTOURS, 64, policy=_over_restricted("auto"), stats=stats)
    assert stats.fallback_reason and "IoU" in stats.fallback_reason


def test_no_fallback_when_the_restricted_fit_already_meets_the_target():
    stats = GenerationStats()
    fit_placements(L_CONTOURS, 64, policy=GenerationPolicy(fallback="auto"), stats=stats)
    assert stats.fallback_used is False


def test_fallback_policy_derivation_per_mode():
    restricted = GenerationPolicy(allowed=frozenset({"circle"}))
    from dataclasses import replace
    assert replace(restricted, fallback="strict").fallback_policy() is None
    assert replace(restricted, fallback="warn").fallback_policy() is None
    assert replace(restricted, fallback="auto").fallback_policy().allowed == ALL_SHAPE_IDS
    assert (replace(restricted, fallback="triangle").fallback_policy().allowed
            == frozenset({"circle"}) | TRIANGLE_FALLBACK_SHAPES)


def test_unrestricted_policy_has_nothing_to_fall_back_to():
    # Retrying an identical fit would double the cost for an identical answer.
    assert GenerationPolicy(fallback="auto").fallback_policy() is None


# --- validation: explain, never crash or silently reset -----------------

def test_valid_default_policy_reports_no_problems():
    assert DEFAULT_POLICY.validate() == []
    assert DEFAULT_POLICY.is_valid


def test_no_shapes_selected_is_reported_as_a_blocking_problem():
    problems = DEFAULT_POLICY.with_allowed(set()).validate()
    assert problems and "No vinyl shapes are selected" in problems[0]


def test_unknown_shape_id_is_named_in_the_problem_text():
    problems = GenerationPolicy(allowed=frozenset({"square", "not_a_shape"})).validate()
    assert any("not_a_shape" in p for p in problems)


def test_preferring_a_disabled_shape_is_rejected_by_display_name():
    problems = GenerationPolicy(
        allowed=frozenset({"square"}), preferred=frozenset({"circle"})).validate()
    assert any("Circle" in p for p in problems)


def test_with_allowed_drops_preferences_that_would_become_invalid():
    policy = GenerationPolicy(preferred=frozenset({"circle", "square"}))
    narrowed = policy.with_allowed({"square"})
    assert narrowed.preferred == frozenset({"square"})
    assert narrowed.is_valid


@pytest.mark.parametrize("kwargs", [
    {"max_layers": 0},
    {"quality_target": 0.0},
    {"quality_target": 1.5},
    {"overshoot_penalty": -1.0},
    {"preference_bonus": -0.1},
    {"fallback": "teleport"},
])
def test_nonsensical_tuning_values_are_reported(kwargs):
    assert GenerationPolicy(**kwargs).validate()


# --- presets -------------------------------------------------------------

def test_every_preset_is_valid_and_round_trips_to_its_own_name():
    for name, preset in PRESETS.items():
        assert preset.is_valid, name
        assert preset_name_for(preset) == name


def test_an_edited_policy_reports_as_custom():
    from dataclasses import replace
    assert preset_name_for(replace(DEFAULT_POLICY, max_layers=7)) == "custom"


def test_presets_differ_in_the_dials_they_are_named_for():
    assert PRESETS["maximum_fidelity"].quality_target > PRESETS["balanced"].quality_target
    assert PRESETS["maximum_fidelity"].max_layers > PRESETS["balanced"].max_layers
    assert PRESETS["minimum_vinyl"].max_layers < PRESETS["balanced"].max_layers
    assert PRESETS["minimum_vinyl"].min_gain > PRESETS["balanced"].min_gain
    assert PRESETS["primitive_only"].allow_exact_cover is False


def test_primitive_only_prefers_shapes_other_than_the_plain_rectangle():
    preferred = PRESETS["primitive_only"].preferred
    assert EXACT_COVER_SHAPE not in preferred
    assert "circle" in preferred


def test_minimum_vinyl_preset_places_no_more_shapes_than_balanced():
    balanced = fit_placements(L_CONTOURS, 64, policy=PRESETS["balanced"])[0]
    minimal = fit_placements(L_CONTOURS, 64, policy=PRESETS["minimum_vinyl"])[0]
    assert len(minimal) <= len(balanced)


def test_a_hand_set_restriction_survives_by_default():
    # The load-bearing guarantee: restricting shapes and pressing Generate
    # must not quietly produce shapes that were switched off. Widening is
    # opt-in, so the default fallback keeps the selection and reports the
    # shortfall instead of silently re-enabling the catalog.
    assert DEFAULT_POLICY.fallback == "warn"
    restricted = DEFAULT_POLICY.with_allowed({"square", "triangle", "circle"})
    stats = GenerationStats()
    fit_placements(L_CONTOURS, 64, policy=restricted, stats=stats)
    assert set(stats.by_shape) <= {"square", "triangle", "circle"}
    assert stats.fallback_used is False


def test_default_fallback_is_a_no_op_for_an_unrestricted_policy():
    # Which is why changing the default is safe: with everything allowed
    # there is nothing to widen to either way.
    assert DEFAULT_POLICY.fallback_policy() is None
    from dataclasses import replace
    assert replace(DEFAULT_POLICY, fallback="auto").fallback_policy() is None


def test_fallback_modes_constant_matches_the_documented_set():
    assert set(FALLBACK_MODES) == {"strict", "warn", "auto", "triangle"}


# --- diagnostics ---------------------------------------------------------

def test_stats_report_shape_counts_by_type_summing_to_the_total():
    stats = GenerationStats()
    placements, _strategy = fit_placements(L_CONTOURS, 64, stats=stats)
    assert stats.shapes_placed == len(placements)
    assert sum(stats.by_shape.values()) == len(placements)


def test_stats_record_strategy_and_achieved_accuracy():
    stats = GenerationStats()
    fit_placements(L_CONTOURS, 64, stats=stats)
    assert stats.strategy == "rect_decompose"
    assert stats.iou == pytest.approx(1.0)  # exact cover


def test_stats_count_candidates_tested_and_rejected():
    stats = GenerationStats()
    fit_silhouette(_square_mask(), 64, stats=stats)
    assert stats.candidates_tested > 0
    assert stats.candidates_rejected > 0


def test_stats_measure_elapsed_time_between_start_and_finish():
    stats = GenerationStats().start()
    fit_silhouette(_square_mask(), 64, stats=stats)
    stats.finish()
    assert stats.elapsed_seconds > 0


def test_stats_serialize_to_json_ready_primitives():
    import json
    stats = GenerationStats()
    fit_placements(L_CONTOURS, 64, stats=stats)
    payload = stats.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert payload["strategy"] == "rect_decompose"


def test_fallback_refit_reports_the_shapes_returned_not_both_attempts():
    # record_placements replaces rather than accumulates, so a re-fit doesn't
    # double-count the discarded first attempt.
    stats = GenerationStats()
    placements, _strategy = fit_placements(
        L_CONTOURS, 64, policy=_over_restricted("auto"), stats=stats)
    assert sum(stats.by_shape.values()) == len(placements)


def test_warn_is_deduplicated():
    stats = GenerationStats()
    stats.warn("same")
    stats.warn("same")
    assert stats.warnings == ["same"]
