"""batch_runner.py: the shared fontpack batch-generation engine used by both
the Generator and Advanced Generator handlers. Tier 1 coverage -- the pure
functions and start()'s validation branches, all synchronous and
window/thread-free, plus one end-to-end smoke test of a real generation run.
"""
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "tools"))
import glyph_overrides  # noqa: E402
from gen_modelbin_web.handlers import batch_runner  # noqa: E402

from .conftest import LIBERATION_SANS  # noqa: E402


# -- new_run_state / is_running ----------------------------------------------

def test_new_run_state_starts_idle():
    run = batch_runner.new_run_state()
    assert run['generation'] == 0
    assert run['worker'] is None
    assert run['abort_requested'] is False
    assert isinstance(run['stop_requested'], threading.Event)
    assert not run['stop_requested'].is_set()


def test_is_running_false_when_no_worker_ever_started():
    run = batch_runner.new_run_state()
    assert batch_runner.is_running(run) is False


def test_is_running_true_while_worker_thread_is_alive():
    run = batch_runner.new_run_state()
    release = threading.Event()
    run['worker'] = threading.Thread(target=release.wait, daemon=True)
    run['worker'].start()
    try:
        assert batch_runner.is_running(run) is True
    finally:
        release.set()
        run['worker'].join()


def test_is_running_false_once_worker_thread_finishes():
    run = batch_runner.new_run_state()
    run['worker'] = threading.Thread(target=lambda: None, daemon=True)
    run['worker'].start()
    run['worker'].join()
    assert batch_runner.is_running(run) is False


# -- image_to_data_uri --------------------------------------------------------

def test_image_to_data_uri_round_trips_as_a_valid_png():
    import base64
    import io

    image = Image.new('RGBA', (4, 4), (255, 0, 0, 255))
    uri = batch_runner.image_to_data_uri(image)

    assert uri.startswith('data:image/png;base64,')
    raw = base64.b64decode(uri.split(',', 1)[1])
    decoded = Image.open(io.BytesIO(raw))
    assert decoded.size == (4, 4)
    assert decoded.convert('RGBA').getpixel((0, 0)) == (255, 0, 0, 255)


# -- selected_chars -----------------------------------------------------------

def test_selected_chars_all_returns_none():
    assert batch_runner.selected_chars({'all': True}, None) is None


def test_selected_chars_empty_when_nothing_set():
    assert batch_runner.selected_chars({}, None) == set()


def test_selected_chars_basic_presets():
    import string
    assert batch_runner.selected_chars({'upper': True}, None) == set(string.ascii_uppercase)
    assert batch_runner.selected_chars({'lower': True}, None) == set(string.ascii_lowercase)
    assert batch_runner.selected_chars({'digits': True}, None) == set(string.digits)
    assert batch_runner.selected_chars({'punct': True}, None) == set(string.punctuation)


def test_selected_chars_symbols_ignored_without_a_font_path():
    # symbols/private/all_han all need a real font's cmap to categorize
    # against -- with no font selected yet, they must contribute nothing
    # rather than raise.
    assert batch_runner.selected_chars({'symbols': True}, None) == set()
    assert batch_runner.selected_chars({'private': True}, None) == set()
    assert batch_runner.selected_chars({'all_han': True}, None) == set()


def test_selected_chars_symbols_excludes_uncased_letters_and_private_use(monkeypatch):
    # Mirrors tests/tools/gen_modelbin_gui/test_generator.py's
    # test_symbols_selection_does_not_include_uncased_letters: charset_from_font
    # buckets uncased letters (Han, Hangul, ...) and private-use glyphs into
    # "Symbols" too, so the symbols flag must filter down to true Unicode
    # Symbol-category characters only.
    monkeypatch.setattr(batch_runner, 'charset_from_font', lambda _p: ({
        'Uppercase': [], 'Lowercase': [], 'Letters': ['中', '한'], 'Numbers': [],
        'Punctuation': [], 'Symbols': ['$', '']}, []))
    fake_font = Path('fake.ttf')

    assert batch_runner.selected_chars({'symbols': True}, fake_font) == {'$'}
    assert batch_runner.selected_chars({'private': True}, fake_font) == {''}


def test_selected_chars_all_han_only_includes_han_letters(monkeypatch):
    monkeypatch.setattr(batch_runner, 'charset_from_font', lambda _p: ({
        'Uppercase': [], 'Lowercase': [], 'Letters': ['中', '文', 'A'], 'Numbers': [],
        'Punctuation': [], 'Symbols': []}, []))
    fake_font = Path('fake.ttf')

    result = batch_runner.selected_chars({'all_han': True}, fake_font)

    assert result == {'中', '文'}
    assert 'A' not in result


def test_selected_chars_includes_checked_alphabet_groups():
    import forza_writer.alphabets as alphabets
    result = batch_runner.selected_chars({'alphabets': {'Cyrillic': ['Uppercase']}}, None)
    assert result == set(alphabets.ALPHABETS['Cyrillic'][0][1])


def test_selected_chars_unions_alphabet_groups_across_scripts():
    result = batch_runner.selected_chars(
        {'alphabets': {'Cyrillic': ['Uppercase'], 'Greek': ['Lowercase']}}, None)
    assert 'А' in result  # Cyrillic capital A (U+0410)
    assert 'α' in result  # Greek lowercase alpha
    assert 'Z' not in result


def test_selected_chars_custom_drops_whitespace():
    assert batch_runner.selected_chars({'custom': '中文测试 ABC'}, None) == set('中文测试ABC')


def test_selected_chars_unions_every_source():
    result = batch_runner.selected_chars({'upper': True, 'custom': '$'}, None)
    assert 'A' in result
    assert '$' in result


# -- generation_diagnostics_lines ---------------------------------------------

def test_generation_diagnostics_lines_empty_manifest_returns_nothing():
    assert batch_runner.generation_diagnostics_lines({}) == []


def test_generation_diagnostics_lines_no_diagnostics_returns_nothing():
    manifest = {'categories': {'Uppercase': [{'artifacts': {}}]}}
    assert batch_runner.generation_diagnostics_lines(manifest) == []


def test_generation_diagnostics_lines_aggregates_shape_counts_and_accuracy():
    manifest = {'categories': {'Uppercase': [
        {'artifacts': {'json': {'diagnostics': {
            'by_shape': {'square': 2, 'circle': 1}, 'iou': 0.9,
            'candidates_tested': 10, 'candidates_rejected': 4, 'elapsed_seconds': 1.5,
            'fallback_used': False, 'warnings': [],
        }}}},
        {'artifacts': {'json': {'diagnostics': {
            'by_shape': {'square': 1}, 'iou': 0.5,
            'candidates_tested': 5, 'candidates_rejected': 1, 'elapsed_seconds': 0.5,
            'fallback_used': True, 'warnings': ['low IoU'],
        }}}},
    ]}}

    lines = batch_runner.generation_diagnostics_lines(manifest)
    blob = ' '.join(lines)

    assert 'square x3' in blob  # 2 + 1, sorted first (highest count)
    assert 'circle x1' in blob
    assert 'mean IoU 0.700' in blob
    assert 'worst 0.500' in blob
    assert '15' in blob and 'candidates tested' in blob  # 10 + 5
    assert '1 glyph(s) needed a fallback' in blob
    assert '1 glyph(s) fell short' in blob


# -- resolve_overrides_for_generation -----------------------------------------

@pytest.fixture
def isolated_overrides_store(monkeypatch, tmp_path):
    monkeypatch.setattr(glyph_overrides, 'OVERRIDES_PATH', tmp_path / 'glyph_overrides.json')
    monkeypatch.setattr(glyph_overrides, 'OVERRIDES_DIR', tmp_path)


def test_resolve_overrides_returns_none_none_when_nothing_saved(isolated_overrides_store, tmp_path):
    font_path = tmp_path / 'SomeFont.ttf'
    assert batch_runner.resolve_overrides_for_generation(font_path) == (None, None)


def test_resolve_overrides_splits_mask_and_manual_entries(isolated_overrides_store, tmp_path):
    font_path = tmp_path / 'SomeFont.ttf'
    glyph_overrides.save_overrides_for_font(font_path, {
        'A': {'mode': 'force'},
        'B': {'mode': 'never'},
        'C': {'mode': 'manual', 'file': str(tmp_path / 'C.json')},
    })

    mask_overrides, manual_assignments = batch_runner.resolve_overrides_for_generation(font_path)

    assert mask_overrides == {'A': 'force', 'B': 'never'}
    assert manual_assignments == {'C': Path(str(tmp_path / 'C.json'))}


def test_resolve_overrides_returns_none_for_the_empty_side(isolated_overrides_store, tmp_path):
    font_path = tmp_path / 'SomeFont.ttf'
    glyph_overrides.save_overrides_for_font(font_path, {'A': {'mode': 'force'}})

    mask_overrides, manual_assignments = batch_runner.resolve_overrides_for_generation(font_path)

    assert mask_overrides == {'A': 'force'}
    assert manual_assignments is None


# -- halt / abort --------------------------------------------------------------

def test_halt_sets_stop_but_not_abort():
    run = batch_runner.new_run_state()
    result = batch_runner.halt(run)
    assert result == {'ok': True}
    assert run['stop_requested'].is_set()
    assert run['abort_requested'] is False


def test_abort_sets_both_stop_and_abort():
    run = batch_runner.new_run_state()
    result = batch_runner.abort(run)
    assert result == {'ok': True}
    assert run['stop_requested'].is_set()
    assert run['abort_requested'] is True


# -- start(): validation branches ---------------------------------------------

def _valid_payload(tmp_path, **overrides):
    payload = {
        'font_path': str(LIBERATION_SANS),
        'output': 'json',
        'reference': None,
        'custom': 'A',
        'policy': {},
        'out_dir': str(tmp_path),
        'prefix': 'TEST',
        'segments': 8,
        'allow_stencil': True,
        'compute_backend': 'cpu',
        'color_mode': 'solid',
        'solid_color': (255, 255, 255, 255),
    }
    payload.update(overrides)
    return payload


def test_start_raises_when_a_batch_is_already_running(window, tmp_path):
    run = batch_runner.new_run_state()
    release = threading.Event()
    run['worker'] = threading.Thread(target=release.wait, daemon=True)
    run['worker'].start()
    try:
        with pytest.raises(ValueError, match='already running'):
            batch_runner.start(window, run, _valid_payload(tmp_path), source_label='Generator')
    finally:
        release.set()
        run['worker'].join()


def test_start_raises_when_font_file_does_not_exist(window, tmp_path):
    run = batch_runner.new_run_state()
    payload = _valid_payload(tmp_path, font_path=str(tmp_path / 'missing.ttf'))
    with pytest.raises(ValueError, match='Font not found'):
        batch_runner.start(window, run, payload, source_label='Generator')


def test_start_raises_on_unknown_output_mode(window, tmp_path):
    run = batch_runner.new_run_state()
    payload = _valid_payload(tmp_path, output='not_a_real_mode')
    with pytest.raises(ValueError, match='Unknown output mode'):
        batch_runner.start(window, run, payload, source_label='Generator')


def test_start_raises_when_modelbin_output_has_no_reference(window, tmp_path):
    run = batch_runner.new_run_state()
    payload = _valid_payload(tmp_path, output='modelbin', reference=None)
    with pytest.raises(ValueError, match='Reference modelbin not found'):
        batch_runner.start(window, run, payload, source_label='Generator')


def test_start_raises_when_no_characters_selected(window, tmp_path):
    run = batch_runner.new_run_state()
    payload = _valid_payload(tmp_path, custom='')
    with pytest.raises(ValueError, match='No characters selected'):
        batch_runner.start(window, run, payload, source_label='Generator')


def test_start_raises_on_invalid_policy(window, tmp_path):
    run = batch_runner.new_run_state()
    payload = _valid_payload(tmp_path, policy={'quality_target': 0})
    with pytest.raises(ValueError, match='Cannot generate'):
        batch_runner.start(window, run, payload, source_label='Generator')


def test_start_validation_failure_does_not_spawn_a_worker(window, tmp_path):
    run = batch_runner.new_run_state()
    payload = _valid_payload(tmp_path, custom='')
    with pytest.raises(ValueError):
        batch_runner.start(window, run, payload, source_label='Generator')
    assert run['worker'] is None


# -- start(): a real end-to-end generation run --------------------------------

def _wait_for_run(run, timeout=30):
    deadline = time.time() + timeout
    while batch_runner.is_running(run) and time.time() < deadline:
        time.sleep(0.05)
    assert not batch_runner.is_running(run), 'worker did not finish in time'


def test_start_runs_a_real_generation_and_pushes_completion_event(window, tmp_path):
    run = batch_runner.new_run_state()
    payload = _valid_payload(tmp_path)

    result = batch_runner.start(window, run, payload, source_label='Generator')

    assert result == {'generation': 1}
    _wait_for_run(run)

    done_events = [js for js in window.evaluated if '"generator_done"' in js]
    assert done_events, f'no generator_done event pushed; saw: {window.evaluated}'

    # build_fontpack's own pack_dir_for() nests by prefix/output/backend --
    # just confirm *some* manifest.json landed under out_dir rather than
    # re-deriving its exact profile-specific path here.
    manifests = list(tmp_path.rglob('manifest.json'))
    assert manifests, f'no manifest.json written under {tmp_path}'
