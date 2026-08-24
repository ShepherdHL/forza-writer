"""Credits tab: attribution for third-party code, data, and research
Forza Writer itself actually incorporates or drew on.

Sourced from THIRD_PARTY_NOTICES.md and README.md's own "Attribution & prior
art" section at the project root — the authoritative record of what this
project uses, not a copy of any other project's own credits page. Every
entry here should trace back to one of those two files (or to code
docstrings, e.g. forza_writer/manufacturer_colors.py) so this page can't
drift from what's actually true of forza-writer's own codebase.

Editorial conventions for CREDITS_SECTIONS — written as finished software
attribution, not development narrative. Each entry states facts about the
relationship between Forza Writer and the credited project; it does not
describe how that relationship was discovered, discussed, or verified.
  - "name" keeps the project's own official casing.
  - "author" and "license" render as one byline ("by <author> · <license>")
    directly under the name.
  - "category" is a short Title Case label, optionally split on an em dash
    into a provenance term ("Directly Incorporated Code") and a specific
    subject ("Font Mapping and Text Layout").
  - "description" is one declarative sentence, or a short list of them —
    each answering only what the project is, what was used from it,
    whether it's bundled/incorporated/referenced-only, and any license or
    runtime distinction that matters. No narration of the research or
    review process.
  - "implementation" is an optional list of the specific files/symbols
    involved, rendered in a monospace font.
  - "links" pairs a short label with a URL, one per line.
"""

import sys
import webbrowser
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import gui_theme  # noqa: E402

CREDITS_SECTIONS = [
    (
        "Ported & Adapted Code",
        [
            {
                "name": "Kloudy's Forza Painter Suite (KFPS)",
                "author": "heyitshestia",
                "license": "MIT",
                "category": "Directly Incorporated Code — Font Mapping and Text Layout",
                "description": [
                    "Font-mapping and text-layout logic is adapted from KFPS and incorporated "
                    "into Forza Writer.",
                    "Forza Writer's implementation reproduces KFPS-compatible output for "
                    "equivalent input.",
                ],
                "implementation": [
                    "forza_writer/shapes.py", "forza_writer/layout.py", "data/fh6_font_registry.json",
                ],
                "links": [
                    ("Project repository", "https://github.com/heyitshestia/kloudys-forza-painter-suite"),
                ],
            },
            {
                "name": "bvzrays' forza-painter-fh6",
                "author": "bvzrays",
                "license": "MIT",
                "category": "Adapted Code — Shape Fitting and Color Conversion",
                "description": [
                    "The legacy pixel-tracing shape fitter and the Forza color-space conversion "
                    "routines are adapted from this repository. Both were originally authored for "
                    "Forza Writer and later contributed upstream to bvzrays' repository.",
                    "This repository was also used as a reference during independent analysis of "
                    "the FH6 vinyl layer memory structure. No source code from this portion is "
                    "included in Forza Writer.",
                    "bvzrays' license also credits AE's forza-painter, Sam Twidale's geometrize-lib, "
                    "and Michael Fogleman's Primitive as upstream sources. None of these projects "
                    "are directly incorporated into Forza Writer.",
                ],
                "implementation": ["forza_writer/legacy_primitive_fit.py", "forza_writer/forza_colors.py"],
                "links": [
                    ("Project repository", "https://github.com/bvzrays/forza-painter-fh6"),
                ],
            },
        ],
    ),
    (
        "Bundled Third-Party Data",
        [
            {
                "name": "GTPlanet Colour Creation Database",
                "author": "Mitcho2001, JaCor653, and MadaraxUchiha",
                "license": None,
                "category": "Bundled Data — Manufacturer Paint Colors",
                "description": [
                    "Composer's Manufacturer Colors pack bundles a manufacturer paint-color "
                    "spreadsheet catalogued by these GTPlanet forum members. The color values were "
                    "originally derived using Bang's Forza Color Converter and official "
                    "manufacturer documentation.",
                    "No license is stated for the source spreadsheet. It is included with "
                    "attribution only.",
                ],
                "implementation": ["assets/data/manufacturer_colors.json", "forza_writer/manufacturer_colors.py"],
                "links": [
                    ("GTPlanet thread",
                     "https://www.gtplanet.net/forum/threads/forza-horizon-4-colour-creation-"
                     "database-constant-work-in-progress-read-first-post.384407/#post-12589813"),
                    ("Forza Color Converter", "https://dxbang.github.io/forza-colors/"),
                ],
            },
        ],
    ),
    (
        "Background Research & Development Tools",
        [
            {
                "name": "FH6-DBDUMPER",
                "author": "matkhl",
                "license": None,
                "category": "Development Reference — Not Bundled",
                "description": [
                    "Used as an external reference for inspecting FH6's in-memory vinyl shape "
                    "database during development. FH6-DBDUMPER is not distributed with or required "
                    "by Forza Writer.",
                    "Forza Writer's diagnostics module is an independent implementation.",
                ],
                "implementation": ["forza_writer/diagnostics/sqlite_watcher.py"],
                "links": [
                    ("Project repository", "https://github.com/matkhl/FH6-DBDUMPER"),
                ],
            },
            {
                "name": "ForzaTech Format Research",
                "author": "Nenkai, Doliman100, and D3FEKT",
                "license": None,
                "category": "Reference Material — Not Bundled",
                "description": [
                    "Forza Writer's .modelbin writer was developed through independent reverse "
                    "engineering, informed by public research on the .modelbin format and the "
                    "encrypted gamedbRC.slt database.",
                    "No code from these projects is included in Forza Writer.",
                ],
                "implementation": ["tools/gen_modelbin.py"],
                "links": [
                    ("Doliman100 — ForzaTech-extraction-tools",
                     "https://github.com/Doliman100/ForzaTech-extraction-tools"),
                    ("Doliman100 — ForzaTech-encryption-tool",
                     "https://github.com/Doliman100/ForzaTech-encryption-tool"),
                    ("D3FEKT — ForzaTechStudio", "https://github.com/D3FEKT/ForzaTechStudio"),
                ],
            },
        ],
    ),
]


class CreditsTabMixin:
    def _build_credits_page(self):
        page = ttk.Frame(self.page_container)
        self._pages['credits'] = page
        content = self._build_scroll_shell(page, 'credits')
        d = gui_theme.density()

        ttk.Label(
            content,
            text='Forza Writer is an original implementation. Selected portions incorporate code '
                 'adapted from third-party projects, bundle third-party data, or were developed '
                 'with reference to external research. THIRD_PARTY_NOTICES.md, in the project '
                 'root, contains the complete legal notices and required license text.',
            style='Intro.TLabel', wraplength=gui_theme.WRAP_WIDE, justify='left',
        ).pack(fill='x', **gui_theme.PAGE_INTRO_PAD)

        for section_title, entries in CREDITS_SECTIONS:
            frame = ttk.LabelFrame(content, text=gui_theme.hud_label(section_title))
            frame.pack(fill='x', **gui_theme.SECTION_PAD)
            for index, entry in enumerate(entries):
                self._build_credit_entry(frame, entry)
                if index < len(entries) - 1:
                    ttk.Separator(frame, orient='horizontal').pack(
                        fill='x', padx=gui_theme.ROW_PAD['padx'], pady=(d['row'][1], d['row'][1]))

        license_frame = ttk.LabelFrame(content, text=gui_theme.hud_label('License'))
        license_frame.pack(fill='x', **gui_theme.SECTION_PAD)
        ttk.Label(
            license_frame,
            text='Forza Writer is MIT-licensed; see LICENSE in the project root. Adapted '
                 'third-party code carries its own upstream attribution requirements, documented '
                 'in THIRD_PARTY_NOTICES.md.',
            style='Hint.TLabel', wraplength=gui_theme.WRAP_MED, justify='left',
        ).pack(fill='x', **gui_theme.ROW_PAD_BOTTOM)

    def _build_credit_entry(self, parent, entry: dict):
        """One credited project/source, always in the same order: name,
        a "by <author> · <license>" byline, a short category label,
        declarative description sentences, an optional monospace list of
        the specific files/symbols involved, then reference links — so
        every entry on the page reads as one consistent, factual record
        rather than some looking like prose and others like raw notes."""
        d = gui_theme.density()
        step = d['row'][1]
        row = ttk.Frame(parent)
        row.pack(fill='x', padx=gui_theme.ROW_PAD['padx'], pady=(step * 2, step * 2))

        ttk.Label(row, text=entry['name'],
                  font=('Segoe UI Semibold', d['body'] + 1)).pack(anchor='w')

        byline = f"by {entry['author']}" if entry.get('author') else ''
        if entry.get('license'):
            byline = f"{byline}  ·  {entry['license']}" if byline else entry['license']
        if byline:
            ttk.Label(row, text=byline, style='Hint.TLabel').pack(anchor='w', pady=(0, step))

        body = ttk.Frame(row)
        body.pack(fill='x', anchor='w', padx=gui_theme.INDENT_PAD)

        if entry.get('category'):
            ttk.Label(body, text=entry['category'], style='Category.TLabel').pack(
                anchor='w', pady=(0, step))

        description = entry.get('description', ())
        if isinstance(description, str):
            description = [description]
        for paragraph in description:
            ttk.Label(body, text=paragraph, style='Hint.TLabel',
                      wraplength=gui_theme.WRAP_MED, justify='left').pack(
                anchor='w', pady=(0, step))

        if entry.get('implementation'):
            ttk.Label(body, text='  ·  '.join(entry['implementation']), style='Code.TLabel',
                      wraplength=gui_theme.WRAP_MED, justify='left').pack(
                anchor='w', pady=(0, step))

        for link_text, url in entry.get('links', ()):
            self._build_credit_link(body, link_text, url)
        return row

    def _build_credit_link(self, parent, text: str, url: str):
        """One colored, underlined reference link — brightens on hover via
        ttk's 'active' pointer state, which plain ttk::label doesn't track
        on its own the way Button/Checkbutton do, so <Enter>/<Leave> set
        it by hand."""
        d = gui_theme.density()
        link = ttk.Label(parent, text=f'{text} ↗', style='Link.TLabel', cursor='hand2')
        link.pack(anchor='w', pady=(d['row'][1] // 2, d['row'][1] // 2))
        link.bind('<Button-1>', lambda _e: webbrowser.open(url))
        link.bind('<Enter>', lambda _e: link.state(['active']))
        link.bind('<Leave>', lambda _e: link.state(['!active']))
        return link
