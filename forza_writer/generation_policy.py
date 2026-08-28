"""What the generator is *allowed* and *encouraged* to build with.

The fitting pipeline in `forza_writer.primitive_fit` already had every stage
this module needs: it just had no way to be told about user intent, because
the shape catalog was consulted directly (`PRIMITIVE_CATALOG.values()`) at the
two candidate-generation sites and the tuning constants were module globals.
This module is the missing input, not a second generator: nothing here fits,
scores, or places anything. It only describes the rules a fit must obey, so
that every present and future generation path can honour the same restrictions
instead of each growing its own copy.

The distinction the pipeline now draws, in order:

1. **Available** primitives: `primitive_shapes.PRIMITIVE_CATALOG`, the fixed
   set of FH6 shapes we can actually reproduce a silhouette for.
2. **Allowed** primitives: `GenerationPolicy.allowed`. A hard restriction:
   the search never *generates* a candidate for a disallowed shape, rather
   than generating and then discarding it, so restricting the set makes
   generation faster as well as narrower.
3. **Preferred** primitives: `GenerationPolicy.preferred`. A soft bias
   applied during scoring, deliberately small (see `preference_bonus`): it
   breaks near-ties toward shapes the user likes without letting a preferred
   shape win a placement it visibly fits worse.
4. **Candidates**, 5. **scoring/selection**, 6. **fallback**: all in
   `primitive_fit`, which reads this policy rather than the old globals.

`DEFAULT_POLICY` reproduces the pre-policy behaviour exactly: every shape
allowed, nothing preferred, and tuning values equal to the constants
`primitive_fit` used before (which now re-exports these, so there is one
source of truth rather than two that can drift).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Iterator, Literal

from forza_writer.primitive_shapes import PRIMITIVE_CATALOG, PrimitiveShape

# Deliberately imports only `primitive_shapes`. `primitive_fit` imports *this*
# module, so importing it back here would be circular; that is also why the
# tuning defaults below live here rather than being imported from there.

# What to do when the allowed set alone can't reproduce the target acceptably.
#
# "strict"   : honour the restriction no matter the result. The user asked for
#              these shapes only; a worse fit is the expected cost, not a bug.
# "warn"     : same output as "strict", but record why it fell short so the
#              caller can surface it. Never silently degrades.
# "auto"     : retry with the full catalog when the restricted fit misses the
#              quality target. Restrictions become a preference, not a rule.
# "triangle" : retry with triangles added, the universal decomposition
#              fallback: any polygon can be built from them, so this recovers
#              accuracy while staying far closer to the user's intent than
#              re-enabling every decorative primitive.
FallbackMode = Literal["strict", "warn", "auto", "triangle"]
FALLBACK_MODES: tuple[FallbackMode, ...] = ("strict", "warn", "auto", "triangle")

FALLBACK_LABELS: dict[str, str] = {
    "strict": "Strict: only the selected shapes, whatever the accuracy",
    "warn": "Warn: keep the restriction, but report when it isn't enough",
    "auto": "Automatic: allow other shapes when the selection falls short",
    "triangle": "Triangle fallback: add triangles when the selection falls short",
}

# Canonical tuning defaults. `primitive_fit` re-exports these under its
# historical names so existing callers and tests keep working unchanged.
DEFAULT_MAX_LAYERS = 16
DEFAULT_QUALITY_TARGET = 0.92  # stop once IoU against the target reaches this
DEFAULT_MIN_GAIN = 4  # stop if no candidate covers at least this many new pixels
DEFAULT_OVERSHOOT_PENALTY = 2.5  # ink outside the target costs this much more than coverage earns

# Small on purpose. A preference is a tie-breaker, not an override: at 8% a
# preferred shape wins when it is within a few percent of the best candidate,
# and loses when it genuinely fits worse. Large values here reintroduce the
# exact failure the greedy search's overshoot penalty exists to prevent:
# one favoured shape smeared over geometry it doesn't match.
DEFAULT_PREFERENCE_BONUS = 0.08

# The exact-cover strategies (`rect_decompose`'s rectilinear fill, and both
# stencil paths, which need a solid background rectangle) are built entirely
# from this one primitive; see rect_decompose.rects_to_placements, which
# asserts on it. Disallowing Square therefore doesn't just remove a shape, it
# removes whole strategies, so `primitive_fit` has to route around them rather
# than hit that assertion.
EXACT_COVER_SHAPE = "square"

# Triangulation is the universal fallback: any polygon decomposes into
# triangles, so these two recover accuracy for an over-restricted set without
# reopening the whole catalog.
TRIANGLE_FALLBACK_SHAPES: frozenset[str] = frozenset({"triangle", "right_triangle"})

ALL_SHAPE_IDS: frozenset[str] = frozenset(PRIMITIVE_CATALOG)


@dataclass(frozen=True)
class GenerationPolicy:
    """User-facing generation rules, as one immutable value.

    Frozen so a policy can be shared across worker threads and cached
    per-glyph without any risk of a fit mutating the settings it was handed.
    Use `dataclasses.replace` (or the `with_*` helpers) to derive a variant.
    """

    allowed: frozenset[str] = ALL_SHAPE_IDS
    preferred: frozenset[str] = frozenset()
    preference_bonus: float = DEFAULT_PREFERENCE_BONUS
    # "warn", not "auto", is the default deliberately. A restriction the user
    # set by hand must survive by default: auto-widening back to the full
    # catalog the moment a fit falls short would mean selecting "rectangles
    # only" quietly produces stars and arrows, which is exactly the silent
    # override this feature exists to prevent. Widening stays available, it
    # just has to be asked for. (For an unrestricted policy the two are
    # identical anyway: there is nothing to widen to, so this changes nothing
    # for anyone who never touches the shape list.)
    fallback: FallbackMode = "warn"
    # Whether the deterministic exact-cover routes may be used at all.
    # Turning this off forces the greedy primitive search even on rectilinear
    # glyphs it would normally solve exactly; that is the whole point of the
    # "Primitive Only" preset, whose complaint is precisely that an exact
    # cover answers a blocky glyph with a pile of rectangles.
    allow_exact_cover: bool = True
    max_layers: int = DEFAULT_MAX_LAYERS
    quality_target: float = DEFAULT_QUALITY_TARGET
    min_gain: int = DEFAULT_MIN_GAIN
    overshoot_penalty: float = DEFAULT_OVERSHOOT_PENALTY

    # -- queries ----------------------------------------------------------
    def shapes(self) -> Iterator[PrimitiveShape]:
        """Allowed shapes, in catalog order.

        Catalog order rather than set order on purpose: `fit_silhouette`
        iterates this to build candidates, and a nondeterministic order makes
        otherwise-identical fits differ run to run whenever two candidates
        tie exactly.
        """
        for shape_id, shape in PRIMITIVE_CATALOG.items():
            if shape_id in self.allowed:
                yield shape

    def allows(self, shape_id: str) -> bool:
        return shape_id in self.allowed

    @property
    def allows_exact_cover(self) -> bool:
        """Whether the rectilinear/stencil exact-cover routes are available."""
        return self.allow_exact_cover and EXACT_COVER_SHAPE in self.allowed

    def weight_for(self, shape_id: str) -> float:
        """Scoring multiplier for a candidate of this shape."""
        return 1.0 + self.preference_bonus if shape_id in self.preferred else 1.0

    def score(self, shape_id: str, gain: float) -> float:
        """Apply the preference bias to one candidate's raw gain.

        Only positive gains are scaled. Scaling a negative gain would make a
        preferred shape rank *below* an equally-bad non-preferred one, which
        inverts the intent: a preference must never actively push a shape
        down.
        """
        if gain <= 0:
            return gain
        return gain * self.weight_for(shape_id)

    # -- validation -------------------------------------------------------
    def validate(self) -> list[str]:
        """Human-readable reasons this policy can't generate, empty if fine.

        Returned as messages rather than raised so the GUI can disable its
        Generate button and explain *why*, which is the stated requirement:
        never crash, never silently revert to defaults.
        """
        problems: list[str] = []
        unknown = sorted(self.allowed - ALL_SHAPE_IDS)
        if unknown:
            problems.append(
                f"Unknown vinyl shape(s): {', '.join(unknown)}. "
                f"They are not in this build's primitive catalog.")
        if not self.allowed:
            problems.append(
                "No vinyl shapes are selected, so there is nothing to build glyphs from. "
                "Select at least one shape.")
        stray = sorted(self.preferred - self.allowed)
        if stray:
            names = ", ".join(PRIMITIVE_CATALOG[s].display_name if s in PRIMITIVE_CATALOG else s
                              for s in stray)
            problems.append(
                f"Preferred shape(s) not in the allowed set: {names}. "
                f"A shape cannot be preferred while it is disabled.")
        if self.fallback not in FALLBACK_MODES:
            problems.append(
                f"Unknown fallback mode {self.fallback!r}; expected one of {', '.join(FALLBACK_MODES)}.")
        if self.max_layers < 1:
            problems.append("Maximum layers must be at least 1.")
        if not 0.0 < self.quality_target <= 1.0:
            problems.append("Quality target must be greater than 0 and at most 1.0.")
        if self.overshoot_penalty < 0:
            problems.append("Overshoot penalty cannot be negative.")
        if self.preference_bonus < 0:
            problems.append("Preference bonus cannot be negative.")
        return problems

    @property
    def is_valid(self) -> bool:
        return not self.validate()

    # -- derivation -------------------------------------------------------
    def with_allowed(self, shape_ids) -> "GenerationPolicy":
        """Same policy over a different allowed set, dropping any preference
        that would be left dangling (validate() rejects preferring a disabled
        shape, so silently carrying one through here would produce an invalid
        policy from a valid one)."""
        allowed = frozenset(shape_ids)
        return replace(self, allowed=allowed, preferred=self.preferred & allowed)

    def fallback_policy(self) -> "GenerationPolicy | None":
        """The retry policy for this one's fallback mode, or None if the mode
        doesn't retry (`strict`/`warn` keep the user's restriction by
        definition; the others widen the allowed set and re-fit).

        Returns None too when widening would change nothing: an unrestricted
        policy has nothing to fall back *to*, and retrying an identical fit
        would just double the work for an identical answer.
        """
        if self.fallback in ("strict", "warn"):
            return None
        widened = (ALL_SHAPE_IDS if self.fallback == "auto"
                   else self.allowed | TRIANGLE_FALLBACK_SHAPES)
        if widened == self.allowed:
            return None
        return self.with_allowed(widened)


DEFAULT_POLICY = GenerationPolicy()

# Everything except the plain rectangle: "recognizable Forza primitives", as
# opposed to the rectangle grid an exact decomposition produces.
_EXPRESSIVE_SHAPES = frozenset(ALL_SHAPE_IDS - {EXACT_COVER_SHAPE})

# Presets are *values of the same policy*, never separate code paths: each one
# only moves the dials below, so a preset can never diverge in behaviour from
# the equivalent hand-tuned settings.
PRESETS: dict[str, GenerationPolicy] = {
    # Today's shipping behaviour, unchanged.
    "balanced": DEFAULT_POLICY,
    # Spend layers freely to match the outline: a higher ceiling, a much
    # stricter stopping IoU, and min_gain=1 so small corrective shapes that
    # the default would dismiss as not worth a layer still get placed.
    "maximum_fidelity": replace(
        DEFAULT_POLICY, max_layers=32, quality_target=0.985, min_gain=1),
    # Stop early and cheaply: a low ceiling, a relaxed target, and a large
    # min_gain so only substantial coverage earns another vinyl.
    "minimum_vinyl": replace(
        DEFAULT_POLICY, max_layers=8, quality_target=0.85, min_gain=12),
    # Favour real primitives and refuse the high-density rectangle
    # decomposition entirely, so blocky glyphs are answered with shapes
    # rather than a grid of squares.
    "primitive_only": replace(
        DEFAULT_POLICY, preferred=_EXPRESSIVE_SHAPES, allow_exact_cover=False),
}

PRESET_LABELS: dict[str, str] = {
    "balanced": "Balanced",
    "maximum_fidelity": "Maximum Fidelity",
    "minimum_vinyl": "Minimum Vinyl Count",
    "primitive_only": "Primitive Only",
}

RECOMMENDED_PRESET = "balanced"


def preset_name_for(policy: GenerationPolicy) -> str:
    """Name of the preset this policy exactly equals, or `"custom"`.

    Lets the UI show "Custom" the moment a user edits any dial, without the UI
    having to track edits itself: the policy value is the whole state.
    """
    for name, preset in PRESETS.items():
        if policy == preset:
            return name
    return "custom"


def policy_to_dict(policy: GenerationPolicy) -> dict:
    """Serializable form for settings files and fontpack manifests.

    The allowed set is stored as `[]` when nothing is restricted rather than
    as a list of all 17 ids. That keeps "no restriction" meaning exactly that
    across catalog changes: a shape added in a later build is available
    immediately instead of arriving pre-disabled for everyone who ever saved
    their settings.
    """
    return {
        "allowed_shapes": [] if policy.allowed == ALL_SHAPE_IDS else sorted(policy.allowed),
        "preferred_shapes": sorted(policy.preferred),
        "fallback": policy.fallback,
        "allow_exact_cover": policy.allow_exact_cover,
        "max_layers": policy.max_layers,
        "quality_target": policy.quality_target,
        "min_gain": policy.min_gain,
        "overshoot_penalty": policy.overshoot_penalty,
    }


def policy_from_dict(data: dict | None,
                      base: GenerationPolicy = DEFAULT_POLICY
                      ) -> tuple[GenerationPolicy, list[str]]:
    """Rebuild a policy from `policy_to_dict` output.

    Returns `(policy, dropped)`; never raises, and never silently substitutes
    defaults for something the user chose. Shape ids that no longer exist in
    this build's catalog are dropped and *named* in `dropped`, so the caller
    can say so rather than the user discovering a shape quietly re-enabled.
    Anything absent falls back to `base`.
    """
    if not data:
        return base, []

    dropped: list[str] = []

    def _shape_set(key: str, default: frozenset[str]) -> frozenset[str]:
        raw = data.get(key)
        if raw is None:
            return default
        if not isinstance(raw, (list, tuple, set, frozenset)):
            return default
        requested = {str(s) for s in raw}
        if not requested and key == "allowed_shapes":
            return ALL_SHAPE_IDS  # [] means "unrestricted", see policy_to_dict
        known = requested & ALL_SHAPE_IDS
        dropped.extend(sorted(requested - ALL_SHAPE_IDS))
        return frozenset(known)

    allowed = _shape_set("allowed_shapes", base.allowed)
    preferred = _shape_set("preferred_shapes", base.preferred) & allowed

    fallback = data.get("fallback", base.fallback)
    if fallback not in FALLBACK_MODES:
        fallback = base.fallback

    def _number(key: str, current, cast):
        value = data.get(key, current)
        try:
            return cast(value)
        except (TypeError, ValueError):
            return current

    policy = GenerationPolicy(
        allowed=allowed,
        preferred=preferred,
        preference_bonus=_number("preference_bonus", base.preference_bonus, float),
        fallback=fallback,
        allow_exact_cover=bool(data.get("allow_exact_cover", base.allow_exact_cover)),
        max_layers=_number("max_layers", base.max_layers, int),
        quality_target=_number("quality_target", base.quality_target, float),
        min_gain=_number("min_gain", base.min_gain, int),
        overshoot_penalty=_number("overshoot_penalty", base.overshoot_penalty, float),
    )
    return policy, dropped


@dataclass
class GenerationStats:
    """What actually happened during one fit.

    Mutable and accumulated in place while fitting, unlike the policy it was
    produced under. Deliberately plain data: callers (the fontpack manifest,
    the GUI results area, the Image-to-Text diagnostics sidecar) format it,
    this doesn't.
    """

    strategy: str = ""
    shapes_placed: int = 0
    by_shape: dict[str, int] = field(default_factory=dict)
    candidates_tested: int = 0
    candidates_rejected: int = 0
    layers_used: int = 0
    iou: float | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    elapsed_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)

    _started: float | None = field(default=None, repr=False, compare=False)

    def start(self) -> "GenerationStats":
        self._started = time.perf_counter()
        return self

    def finish(self) -> "GenerationStats":
        if self._started is not None:
            self.elapsed_seconds = time.perf_counter() - self._started
            self._started = None
        return self

    def record_placements(self, placements) -> None:
        """Count final placements by shape. Replaces rather than adds, so a
        fallback re-fit reports the shapes actually returned instead of the
        sum of both attempts."""
        counts: dict[str, int] = {}
        for placement in placements:
            counts[placement.shape_id] = counts.get(placement.shape_id, 0) + 1
        self.by_shape = counts
        self.shapes_placed = len(placements)
        self.layers_used = len(placements)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def to_dict(self) -> dict:
        """JSON-ready form for manifests and diagnostics sidecar files."""
        return {
            "strategy": self.strategy,
            "shapes_placed": self.shapes_placed,
            "by_shape": dict(sorted(self.by_shape.items())),
            "candidates_tested": self.candidates_tested,
            "candidates_rejected": self.candidates_rejected,
            "layers_used": self.layers_used,
            "iou": self.iou,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "elapsed_seconds": round(self.elapsed_seconds, 6),
            "warnings": list(self.warnings),
        }
