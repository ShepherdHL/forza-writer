"""outputs.py: browsing previously-generated fontpacks and previewing any
.json/.modelbin file directly. Mirrors tabs/outputs.py's manifest-scanning
and preview logic against the real backend.
"""
import json

import pytest

from gen_modelbin_web.handlers import outputs as outputs_handlers


@pytest.fixture(autouse=True)
def _register(api, window):
    outputs_handlers.register(api, window)
    return api


def _square_shape(mask=False):
    return {
        "type": 1048677, "type_word": 101,
        "data": [0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1 if mask else 0],
        "color": [0, 0, 0, 255] if mask else [255, 255, 255, 255],
        "mask": mask,
    }


def _write_manifest(pack_dir, *, prefix='TEST', output='json', profile_id='JSON-CPU-CS8', categories=None):
    pack_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        'prefix': prefix, 'output': output,
        'generation_profile': {'id': profile_id},
        'categories': categories or {},
    }
    (pack_dir / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return pack_dir / 'manifest.json'


# -- browse_root / browse_file: just Browse-dialog plumbing -------------------

def test_browse_root_returns_cancelled_when_dialog_is_dismissed(api, window):
    window.file_dialog_result = None
    resp = api.call('outputs.browse_root', {'initial': ''})
    assert resp['result'] == {'cancelled': True}


def test_browse_root_returns_the_chosen_path(api, window):
    window.file_dialog_result = ['C:/Some/Folder']
    resp = api.call('outputs.browse_root', {'initial': ''})
    assert resp['result'] == {'path': 'C:/Some/Folder'}


def test_browse_file_returns_cancelled_when_dialog_is_dismissed(api, window):
    window.file_dialog_result = None
    resp = api.call('outputs.browse_file')
    assert resp['result'] == {'cancelled': True}


# -- list_packs ----------------------------------------------------------------

def test_list_packs_empty_when_root_does_not_exist(api, tmp_path):
    resp = api.call('outputs.list_packs', {'root': str(tmp_path / 'does-not-exist')})
    assert resp['result']['packs'] == []


def test_list_packs_finds_manifests_two_levels_deep(api, tmp_path):
    _write_manifest(tmp_path / 'TEST-FONT' / 'TEST-FONT__JSON-CPU-CS8', prefix='TEST-FONT',
                     categories={'Uppercase': [{}], 'Lowercase': [{}, {}]})

    resp = api.call('outputs.list_packs', {'root': str(tmp_path)})

    assert len(resp['result']['packs']) == 1
    pack = resp['result']['packs'][0]
    assert pack['label'] == 'TEST-FONT [JSON-CPU-CS8] (3 glyphs)'


def test_list_packs_skips_a_corrupt_manifest_without_raising(api, tmp_path):
    bad_dir = tmp_path / 'BAD' / 'BAD__JSON-CPU-CS8'
    bad_dir.mkdir(parents=True)
    (bad_dir / 'manifest.json').write_text('not valid json{{{', encoding='utf-8')

    resp = api.call('outputs.list_packs', {'root': str(tmp_path)})

    assert resp['result']['packs'] == []


# -- get_pack_glyphs -------------------------------------------------------------

def test_get_pack_glyphs_orders_by_category_and_formats_labels(api, tmp_path):
    pack_dir = tmp_path / 'PACK'
    _write_manifest(pack_dir, categories={
        'Lowercase': [{'char': 'a', 'artifacts': {'json': {
            'strategy': 'rect_decompose', 'file': 'a.json',
            'quality': {'verdict': 'pass', 'iou': 0.987}}}}],
        'Uppercase': [{'char': 'A', 'artifacts': {'json': {'strategy': 'search', 'file': 'A.json'}}}],
    })

    resp = api.call('outputs.get_pack_glyphs', {'pack_dir': str(pack_dir)})
    entries = resp['result']['entries']

    # CATEGORY_ORDER puts Uppercase before Lowercase regardless of dict
    # insertion order above.
    assert entries[0]['label'] == "Uppercase  'A'  (search)"
    assert entries[1]['label'] == "Lowercase  'a'  (rect_decompose)  [PASS 0.99]"
    assert entries[1]['path'] == str(pack_dir / 'a.json')


def test_get_pack_glyphs_review_verdict_is_not_marked_pass(api, tmp_path):
    pack_dir = tmp_path / 'PACK'
    _write_manifest(pack_dir, categories={
        'Uppercase': [{'char': 'A', 'artifacts': {'json': {
            'strategy': 'search', 'file': 'A.json',
            'quality': {'verdict': 'review', 'iou': 0.5}}}}],
    })

    resp = api.call('outputs.get_pack_glyphs', {'pack_dir': str(pack_dir)})

    assert 'REVIEW' in resp['result']['entries'][0]['label']


# -- preview_file ----------------------------------------------------------------

def test_preview_file_raises_when_file_missing(api, tmp_path):
    resp = api.call('outputs.preview_file', {'path': str(tmp_path / 'nope.json')})
    assert resp['ok'] is False
    assert 'File not found' in resp['error']


def test_preview_file_json_reports_shape_and_mask_counts(api, tmp_path):
    path = tmp_path / 'A.json'
    path.write_text(json.dumps({'shapes': [_square_shape(), _square_shape(mask=True)]}), encoding='utf-8')

    resp = api.call('outputs.preview_file', {'path': str(path)})

    assert resp['ok'] is True
    assert resp['result']['preview_image'].startswith('data:image/png;base64,')
    assert '2 shape(s), 1 mask cutout(s)' in resp['result']['text']
    assert resp['result']['style'] == 'hint'


def test_preview_file_unsupported_extension_reports_hint_style(api, tmp_path):
    path = tmp_path / 'notes.txt'
    path.write_text('hello', encoding='utf-8')

    resp = api.call('outputs.preview_file', {'path': str(path)})

    assert 'Unsupported file type' in resp['result']['text']
    assert resp['result']['style'] == 'hint'


def test_preview_file_malformed_modelbin_reports_danger_style_without_raising(api, tmp_path):
    path = tmp_path / 'bad.modelbin'
    path.write_bytes(b'not a real modelbin file')

    resp = api.call('outputs.preview_file', {'path': str(path)})

    assert resp['ok'] is True  # the handler itself doesn't raise -- the error is in the returned text
    assert resp['result']['style'] == 'danger'
