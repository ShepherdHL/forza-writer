"""Credits tab: attribution list for third-party code/data forza-writer
itself actually uses.
"""
from conftest import tk, ttk  # noqa: E402


def test_credits_tab_is_registered_in_sidebar(gui):
    import gen_modelbin_gui as mod
    from gen_modelbin_gui.state import TAB_LABELS
    assert 'credits' in mod.TABS
    assert TAB_LABELS['credits'] == 'Credits'
    assert 'credits' in gui._pages


def test_switching_to_credits_tab_shows_its_page(gui):
    gui._show_tab('credits')
    gui.root.update()
    assert gui._current_tab == 'credits'
    assert gui._pages['credits'].winfo_manager() == 'pack'


def test_credits_excludes_forzaliverystudio_and_fabricjs(gui):
    from gen_modelbin_gui.tabs.credits import CREDITS_SECTIONS
    names = [entry['name'] for _title, entries in CREDITS_SECTIONS for entry in entries]
    blob = ' '.join(names).lower()
    assert 'forzaliverystudio' not in blob
    assert 'fabric.js' not in blob
    assert 'fabricjs' not in blob


def test_credits_excludes_community_thanks_section(gui):
    from gen_modelbin_gui.tabs.credits import CREDITS_SECTIONS
    titles = [title.lower() for title, _entries in CREDITS_SECTIONS]
    assert not any('community' in title for title in titles)


def test_credits_includes_kfps_and_bvzrays_and_gtplanet(gui):
    from gen_modelbin_gui.tabs.credits import CREDITS_SECTIONS
    names = [entry['name'] for _title, entries in CREDITS_SECTIONS for entry in entries]
    assert any('kloudy' in name.lower() for name in names)
    assert any('bvzrays' in name.lower() for name in names)
    assert any('gtplanet' in name.lower() for name in names)


def test_credit_entry_link_opens_via_webbrowser(gui, monkeypatch):
    import gen_modelbin_gui.tabs.credits as credits_module
    opened = []
    monkeypatch.setattr(credits_module.webbrowser, 'open', lambda url: opened.append(url))

    frame = ttk.Frame(gui.root)
    link = gui._build_credit_link(frame, 'Example link', 'https://example.com')
    assert str(link.cget('cursor')) == 'hand2'
    link.event_generate('<Button-1>')
    gui.root.update()
    assert opened == ['https://example.com']


def test_credit_link_brightens_on_hover(gui):
    frame = ttk.Frame(gui.root)
    link = gui._build_credit_link(frame, 'Example link', 'https://example.com')
    assert 'active' not in link.state()
    link.event_generate('<Enter>')
    gui.root.update()
    assert 'active' in link.state()
    link.event_generate('<Leave>')
    gui.root.update()
    assert 'active' not in link.state()


def test_every_credit_entry_follows_the_same_schema(gui):
    # Every credit entry must supply the same fields in the same shape, so
    # no entry can silently regress to an inconsistent format.
    from gen_modelbin_gui.tabs.credits import CREDITS_SECTIONS
    for section_title, entries in CREDITS_SECTIONS:
        assert section_title == section_title.strip()
        assert entries, f'{section_title!r} has no entries'
        for entry in entries:
            assert isinstance(entry['name'], str) and entry['name']
            assert isinstance(entry.get('author'), str) and entry['author']
            assert entry.get('license') is None or isinstance(entry['license'], str)
            assert isinstance(entry['category'], str) and entry['category']
            # Category labels are short Title Case noun phrases, not sentences.
            assert not entry['category'].endswith('.')
            paragraphs = entry['description']
            assert isinstance(paragraphs, list) and paragraphs
            for paragraph in paragraphs:
                assert isinstance(paragraph, str) and paragraph.strip().endswith('.')
            for path in entry.get('implementation', []):
                assert isinstance(path, str) and path
            assert entry.get('links'), f'{entry["name"]!r} has no reference links'
            for link_text, url in entry['links']:
                assert isinstance(link_text, str) and link_text
                assert url.startswith('https://')


def test_credit_descriptions_avoid_conversational_and_process_language(gui):
    # Credits copy must read as matter-of-fact attribution, not
    # development-narrative phrasing ("noted here for provenance",
    # "documented for provenance", "background research only", etc.).
    # Guard against it creeping back in.
    from gen_modelbin_gui.tabs.credits import CREDITS_SECTIONS
    banned_phrases = [
        'we found', 'we determined', 'this informed our understanding', 'for completeness',
        'noted here for provenance', 'documented for provenance', 'documented anyway',
        'background research only', 'we did not copy', 'this repo showed us',
        'during development we used', 'claude identified', 'after comparing',
        'the implementation appears to', 'this was included because', 'in keeping with',
        'consistent with every other entry',
    ]
    blob = ' '.join(
        paragraph.lower()
        for _title, entries in CREDITS_SECTIONS
        for entry in entries
        for paragraph in entry['description']
    )
    for phrase in banned_phrases:
        assert phrase not in blob, f'conversational phrase leaked into Credits copy: {phrase!r}'


def test_credit_entry_builds_with_full_schema_without_raising(gui):
    frame = ttk.Frame(gui.root)
    entry = {
        'name': 'Example Project', 'author': 'Example Author', 'license': 'MIT',
        'category': 'Ported Code',
        'description': ['A single declarative sentence for the test entry.'],
        'implementation': ['forza_writer/example.py'],
        'links': [('Project repository', 'https://example.com')],
    }
    row = gui._build_credit_entry(frame, entry)
    gui.root.update()
    assert row.winfo_manager() == 'pack'
