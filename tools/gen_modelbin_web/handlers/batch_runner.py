"""Shared fontpack batch-generation runner, used by both the Generator and
Advanced Generator handlers: one shared engine, one shared "only one batch
at a time" worker lock. `app.py` creates a single `new_run_state()` dict
and passes it to both handler modules' `register()` so that invariant
holds -- starting a batch from either tab while the other's is still
running raises.
"""
from __future__ import annotations

import base64
import io
import string
import sys
import threading
import time
import unicodedata
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _TOOLS_DIR.parent
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import file_preview  # noqa: E402
import glyph_overrides as glyph_overrides_store  # noqa: E402
import gui_settings  # noqa: E402
import theme_palettes  # noqa: E402
from gen_fontpack import OUTPUT_MODES, build_fontpack, pack_dir_for, sanitize_prefix  # noqa: E402
from forza_writer import alphabets  # noqa: E402
from forza_writer.charset import charset_from_font, is_han_char  # noqa: E402
from forza_writer.compute_backend import resolve_backend  # noqa: E402
from forza_writer.generation_policy import policy_from_dict  # noqa: E402
from forza_writer.variable_fonts import variation_slug  # noqa: E402

from ..events import push_event  # noqa: E402

LIVE_PREVIEW_SIZE = (160, 160)


def new_run_state() -> dict:
    return {'generation': 0, 'worker': None, 'stop_requested': threading.Event(), 'abort_requested': False}


def is_running(run: dict) -> bool:
    """Mirrors Tkinter's `self.worker and self.worker.is_alive()` guard --
    shared by start() (only one batch at a time) and Settings' Clean
    generated data (never delete out from under a live write)."""
    return run['worker'] is not None and run['worker'].is_alive()


def image_to_data_uri(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def selected_chars(payload: dict, font_path: Path | None) -> set[str] | None:
    """Mirrors GeneratorTabMixin._selected_chars exactly, driven by a plain
    payload dict instead of Tk variables. Shared by Generator (against its
    own selected font) and Advanced Generator (against its variable-font
    instance) -- the selection logic itself doesn't care which."""
    if payload.get('all'):
        return None
    chars: set[str] = set()
    if payload.get('upper'):
        chars.update(string.ascii_uppercase)
    if payload.get('lower'):
        chars.update(string.ascii_lowercase)
    if payload.get('digits'):
        chars.update(string.digits)
    if payload.get('punct'):
        chars.update(string.punctuation)
    if payload.get('symbols') and font_path is not None:
        categorized, _ = charset_from_font(font_path)
        chars.update(c for c in categorized.get('Symbols', []) if unicodedata.category(c).startswith('S'))
    if payload.get('private') and font_path is not None:
        categorized, _ = charset_from_font(font_path)
        chars.update(c for c in categorized.get('Symbols', []) if unicodedata.category(c) == 'Co')
    for script, labels in (payload.get('alphabets') or {}).items():
        groups = dict(alphabets.groups_for_script(script))
        for label in labels:
            chars.update(groups.get(label, ''))
    if font_path is not None and (payload.get('all_han') or []):
        categorized, _ = charset_from_font(font_path)
        chars.update(c for c in categorized.get('Letters', []) if is_han_char(c))
    for c in payload.get('custom', ''):
        if not c.isspace():
            chars.add(c)
    return chars


def generation_diagnostics_lines(manifest: dict) -> list[str]:
    """Pure aggregation over a completed batch's manifest dict into the
    Log panel's human-readable summary lines."""
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

    mix = ', '.join(f'{shape_id} x{count}' for shape_id, count in sorted(by_shape.items(), key=lambda kv: -kv[1]))
    lines = [
        f'Diagnostics: {total_vinyls:,} vinyls across {len(stats):,} glyphs ({total_vinyls / len(stats):.1f} per glyph)',
        f'Vinyl types used: {mix}',
    ]
    if ious:
        lines.append(f'Accuracy: mean IoU {sum(ious) / len(ious):.3f}, worst {min(ious):.3f}')
    lines.append(f'Search: {tested:,} candidates tested, {rejected:,} rejected, {elapsed:.1f}s fitting')
    if fallbacks:
        lines.append(f'{fallbacks:,} glyph(s) needed a fallback shape.')
    if warned:
        lines.append(f'{warned:,} glyph(s) fell short of the quality target.')
    return lines


def resolve_overrides_for_generation(font_path: Path) -> tuple[dict | None, dict | None]:
    """Splits font_path's saved per-glyph overrides into build_fontpack's
    mask_overrides/manual_assignments kwargs. Always reloads from disk
    rather than trusting any in-memory Configurator state -- every edit
    there saves immediately, so disk is the source of truth.

    Only called for a plain (non-variation) font_path here. Tkinter's own
    Advanced Generator additionally resolves overrides against a
    variation's *instantiated* static font path via a separate "per
    instance" workspace -- this web port's Configurator only edits
    overrides for Generator's own plain font selection, so a variation
    generation always passes (None, None) rather than silently resolving
    overrides that no reachable UI here could have set in the first place.
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


def halt(run: dict) -> dict:
    run['stop_requested'].set()
    return {'ok': True}


def abort(run: dict) -> dict:
    run['abort_requested'] = True
    run['stop_requested'].set()
    return {'ok': True}


def start(window, run: dict, payload: dict, *, source_label: str, variation: dict | None = None) -> dict:
    """Validate `payload` and spawn the background worker. Raises ValueError
    (surfaced to the page as resp.error) on any validation failure, exactly
    mirroring _start_generation's early-return-with-log checks."""
    if is_running(run):
        raise ValueError('A batch is already running. Halt or Abort it first.')

    font_path = Path(payload['font_path'])
    if not font_path.exists():
        raise ValueError(f'Font not found: {font_path}')
    output = payload['output']
    if output not in OUTPUT_MODES:
        raise ValueError(f'Unknown output mode: {output!r}')
    reference = Path(payload['reference']) if (output == 'modelbin' and payload.get('reference')) else None
    if output == 'modelbin' and (reference is None or not reference.exists()):
        raise ValueError(f'Reference modelbin not found: {reference}. Set it in Settings.')
    chars = selected_chars(payload, font_path)
    if chars is not None and not chars:
        raise ValueError('No characters selected.')

    policy, _dropped = policy_from_dict(payload['policy'])
    problems = policy.validate()
    if problems:
        raise ValueError('Cannot generate: ' + ' '.join(problems))

    out_dir = Path(payload['out_dir'])
    prefix = sanitize_prefix(payload['prefix'])
    segments = max(1, int(payload['segments']))
    allow_stencil = bool(payload.get('allow_stencil', True))
    compute_backend = payload.get('compute_backend', 'auto')
    color_mode = payload.get('color_mode', 'solid')
    solid_color = tuple(payload.get('solid_color', (255, 255, 255, 255)))
    high_contrast_seed = payload.get('high_contrast_seed') if color_mode == 'high_contrast' else None

    run['stop_requested'].clear()
    run['abort_requested'] = False
    run['generation'] += 1
    gen = run['generation']

    # Resolved once, not per glyph: same file_preview.kfps_vinyls_dir(...)
    # call the Plates tab already makes, so a font_reuse glyph's live
    # preview during this run shows the real letterform instead of a plain
    # box, same as its exported .json and its quality-gate score already do.
    vinyls_dir = file_preview.kfps_vinyls_dir(gui_settings.load_settings().get('kfps_executable', ''))

    def log(line: str, level: str = 'plain') -> None:
        # Routed through the shared Log panel (shell.js's log_append
        # listener), not a tab-local log -- matching Tkinter's _log(),
        # which every tab's messages funnel through the one widget.
        push_event(window, 'log_append', 0, {
            'ts': time.strftime('%H:%M:%S'), 'level': level, 'text': line})

    def on_glyph(category: str, entry: dict) -> None:
        artifact = entry.get('artifacts', {}).get('json') or entry.get('artifacts', {}).get('modelbin')
        if not artifact or not artifact.get('file'):
            return
        file_path = pack_dir / artifact['file']
        if not file_path.exists():
            return
        p = theme_palettes.palette()
        image = file_preview.render_file_preview(file_path, LIVE_PREVIEW_SIZE, bg=p['canvas_bg'], fg=p['fg'],
                                                  vinyls_dir=vinyls_dir)
        quality = artifact.get('quality')
        if quality:
            stats = (f"{category} {entry['char']!r}: {quality['verdict'].upper()} "
                     f"(IoU {quality['iou']:.3f}, boundary F1 {quality['boundary_f1']:.3f})")
        else:
            stats = f"{category} {entry['char']!r} generated."
        push_event(window, 'generator_glyph', gen, {'preview_image': image_to_data_uri(image), 'stats': stats})

    resolved = resolve_backend(compute_backend if output == 'json' else 'cpu')
    effective_prefix = prefix
    if variation:
        effective_prefix = sanitize_prefix(f"{prefix}-{variation_slug(variation.get('coordinates', {}))}")
    pack_dir = pack_dir_for(out_dir, effective_prefix, output, segments, resolved.resolved)

    color_note = (f', color_mode=high_contrast, seed={high_contrast_seed}' if color_mode == 'high_contrast'
                  else f', color_mode=solid, solid_color={solid_color}')
    log(f'--- Generating fontpack "{prefix}" from {font_path.name} ({source_label}) '
        f'(output={output}, curve_segments={segments}, allow_stencil={allow_stencil}, '
        f'compute_backend={compute_backend}{color_note}) ---')

    mask_overrides, manual_assignments = (None, None) if variation else resolve_overrides_for_generation(font_path)
    if mask_overrides or manual_assignments:
        log(f'  Per-glyph overrides: {len(mask_overrides or {})} mask, {len(manual_assignments or {})} manual')

    def worker():
        try:
            variation_kwargs = ({'source_font_path': font_path, 'variation': variation} if variation else {})
            manifest = build_fontpack(
                font_path, out_dir, prefix, output, reference, segments, chars=chars,
                should_stop=run['stop_requested'].is_set, on_glyph=on_glyph, log=log,
                allow_stencil=allow_stencil, compute_backend=compute_backend, policy=policy,
                color_mode=color_mode, solid_color=solid_color, high_contrast_seed=high_contrast_seed,
                mask_overrides=mask_overrides, manual_assignments=manual_assignments,
                **variation_kwargs)
            # build_fontpack may have renamed pack_dir (appending the total
            # shape count) after this function's own pack_dir_for call
            # above computed it -- recover the actual directory it wrote to
            # rather than operating on a path that no longer exists.
            if manifest.get('pack_dir_name'):
                nonlocal pack_dir
                pack_dir = pack_dir.parent / manifest['pack_dir_name']
            if run['abort_requested']:
                removed = 0
                for rel in manifest.get('files_written', []):
                    file_path = pack_dir / rel
                    if file_path.exists():
                        file_path.unlink()
                        removed += 1
                manifest_path = pack_dir / 'manifest.json'
                if manifest_path.exists():
                    manifest_path.unlink()
                done_msg, done_tag = f'Aborted. Removed {removed} file(s).', 'warn'
            else:
                summary = manifest['summary']
                bits = ', '.join(f"{mode}: {summary[mode]['generated']} ok/{summary[mode]['failed']} failed"
                                  for mode in ('modelbin', 'json') if mode in summary)
                halted_note = ' (halted early -- kept what finished)' if manifest.get('halted') else ''
                done_msg = (f'Done{halted_note}. {bits}, {summary["skipped"]} skipped. '
                            f"Manifest: {pack_dir / 'manifest.json'}")
                done_tag = 'success'
                for line in generation_diagnostics_lines(manifest):
                    log(line)
        except Exception as exc:
            done_msg, done_tag = f'Generation failed: {exc}', 'danger'
        log(done_msg, done_tag)
        push_event(window, 'generator_done', gen, {'tag': done_tag})

    run['worker'] = threading.Thread(target=worker, daemon=True)
    run['worker'].start()
    return {'generation': gen}
