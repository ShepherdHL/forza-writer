// Generator tab: font selection, character selection, output mode, vinyl
// shape policy, and the main batch-generation run. The actual batch worker
// is shared with Advanced Generator via handlers/batch_runner.py.
//
// Character selection and vinyl-shape policy are shared components
// (js/character-selector.js, js/vinyl-shapes.js) also used by Advanced
// Generator -- see vinyl-shapes.js's module comment for why Advanced
// Generator needs its own instance rather than literally sharing this
// tab's live state.
//
// One deliberate, non-functionality-losing scope simplification (see
// handlers/generator.py's module docstring for the full rationale):
//   - The Characters section's non-Latin alphabet groups are all shown at
//     once rather than gated behind Tkinter's separate font-browser script
//     tab bar. The visual Grid font browser itself (fonts rendered in
//     their own typeface, sortable, filterable by file type and by
//     script) IS ported and goes further than Tkinter's tab bar in one
//     way: clicking "Select only <Script>" in the Characters section
//     drives the same script filter, via character-selector.js's
//     onScriptFilter -- see renderFontGrid()/updateScriptChip() below.
// Per-glyph Configurator overrides and variable-font instancing stay
// Advanced Generator's territory, same as in Tkinter.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  const OUTPUT_MODES = [
    { key: 'json', title: 'Shape Fitting (.json)',
      desc: "Analyzes each glyph and approximates it using Forza's full primitive-shape library, with optional masks." },
    { key: 'json_legacy', title: 'Pixel Tracing (.json)',
      desc: 'Rasterizes each glyph, then combines the filled pixels into rectangular vinyl layers.' },
    { key: 'modelbin', title: 'Custom Mesh (.modelbin)',
      desc: 'Experimental. The native files Forza games use for vinyls. Adding one to the game requires a catalog hijack or SQLite injection. KFPS cannot open this format.' },
  ];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  async function mount(container, opts) {
    container.innerHTML = `
      <h2 class="page-heading">Generator</h2>
      <div class="intro-text">
        Pick a font, choose which characters to include, pick an output type, then click Generate.
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 340px;">
        <div>
      <div class="section">
        <div class="section-title">1. Font</div>
        <div class="gen-font-toolbar">
          <select class="path-input" id="genFontSort" style="max-width: 170px;">
            <option value="az">Sort: A → Z</option>
            <option value="za">Sort: Z → A</option>
            <option value="glyphs">Sort: Glyph Count</option>
          </select>
          <span class="gen-font-type-filters">
            <label><input type="checkbox" class="gen-font-type" value=".ttf" checked> .ttf</label>
            <label><input type="checkbox" class="gen-font-type" value=".otf" checked> .otf</label>
            <label><input type="checkbox" class="gen-font-type" value=".woff2" checked> .woff2</label>
          </span>
        </div>
        <div class="gen-font-filter-chip" id="genFontScriptChip" style="display:none;"></div>
        <div class="path-field" style="margin-bottom: 8px;">
          <div id="genFontSearch" style="flex:1;"></div>
          <button type="button" class="btn" id="genRescanFonts" title="Re-scan installed fonts -- only needed if you installed a new font while the app was already running">Rescan Fonts</button>
          <button type="button" class="btn" id="genBrowseFont">Browse on machine…</button>
        </div>
        <div class="field-hint" id="genFontGridStatus"></div>
        <div class="gen-font-grid" id="genFontGrid"></div>
        <div class="field-hint" id="genFontPath">(no font selected)</div>
        <div class="field-hint" id="genLowercaseWarning" style="color: var(--warn);"></div>
        <div class="field-hint" id="genLargeFontWarning" style="color: var(--warn);"></div>
        <div class="field-hint" id="genVariationStatus"></div>
        <div class="path-field" style="margin-bottom: 0; margin-top: 6px;">
          <button type="button" class="btn" id="genSendToAdvanced">Send selected font to Advanced Generator</button>
          <button type="button" class="btn" id="genSendToDirect">Send selected font to Direct Generator</button>
        </div>
      </div>

      <div class="section">
        <div class="section-title">2. Characters</div>
        <div id="genCharacters"></div>
        <div class="field-hint" id="genCharCount"></div>
      </div>

      <div class="section">
        <div class="section-title">3. Output</div>
        <div id="genOutputCards" style="display:flex; flex-direction:column; gap:8px; margin-bottom: 10px;"></div>
        <div class="checkbox-row">
          <input type="checkbox" id="genAllowStencil" checked>
          <label for="genAllowStencil">Allow layer masks (stencil mode), Shape Fitting only.</label>
        </div>
      </div>

      <div class="section">
        <div class="section-title">4. Options</div>
        <div class="path-field" style="margin-bottom: 8px;">
          <span class="field-label">Curve Smoothness</span>
          <input type="number" class="path-input" id="genSegments" value="8" min="1" max="32" style="max-width: 70px;">
          <span class="field-label" style="margin-left: 16px;">Filename prefix</span>
          <input type="text" class="path-input" id="genPrefix" value="CUSTOM" style="max-width: 200px;">
          <span class="field-hint" id="genFilenamePreview"></span>
        </div>
        <div class="field-hint" id="genPathsSummary" style="margin-bottom: 8px;"></div>
        <button type="button" class="btn" id="genGotoSettings" style="margin-bottom: 10px;">Settings…</button>
        <div class="radio-group" id="genBackendGroup" style="margin-bottom: 6px;">
          <span class="field-label">Generation Processor</span>
          <label><input type="radio" name="genBackend" value="auto" checked> Auto (prefer GPU)</label>
          <label><input type="radio" name="genBackend" value="cuda"> NVIDIA CUDA</label>
          <label><input type="radio" name="genBackend" value="directml"> AMD DirectML (Experimental)</label>
          <label><input type="radio" name="genBackend" value="cpu"> CPU</label>
        </div>
        <div class="field-hint" id="genBackendStatus"></div>
        <div class="field-hint" id="genReferenceWarning" style="color: var(--warn);"></div>
      </div>

      <div class="section">
        <div class="section-title">5. Vinyl Shapes</div>
        <div id="genVinylShapes"></div>
      </div>

      <div class="section">
        <div class="path-field" style="margin-bottom: 0;">
          <button type="button" class="btn" id="cfgToggle">▶ Open per-glyph overrides</button>
          <span class="field-hint" id="cfgSummary">Closed -- glyph scanning and previews are deferred.</span>
        </div>
        <div id="cfgBody" style="display:none; margin-top: 12px;">
          <div class="field-hint" style="margin-bottom:10px;">
            Overrides apply to the font currently selected above. Force or forbid masks per glyph, or assign
            an already-made .json file. Changes save immediately and the main Generate button uses them.
          </div>
          <div class="path-field" style="margin-bottom: 8px;">
            <button type="button" class="btn" id="cfgRescan">Rescan glyphs</button>
            <span class="field-hint" id="cfgScanStatus">Open this workspace to inspect the selected font.</span>
          </div>
          <div class="path-field" style="margin-bottom: 10px;">
            <button type="button" class="btn" id="cfgResetAll">Reset all to Auto</button>
            <button type="button" class="btn" id="cfgForceAll">Force mask on all eligible rectilinear glyphs</button>
          </div>
          <div class="cfg-columns">
            <div class="cfg-list-col">
              <div class="cfg-glyph-table-wrap" id="cfgGlyphTableWrap">
                <table class="cfg-glyph-table">
                  <thead>
                    <tr><th>Glyph</th><th>Category</th><th>Rectilinear</th><th>Auto picks</th><th>Mode</th></tr>
                  </thead>
                  <tbody id="cfgGlyphTableBody"></tbody>
                </table>
              </div>
            </div>
            <div class="cfg-detail-col">
              <div class="section-title">Selected Glyph</div>
              <div class="gi-diff-panel" style="aspect-ratio: 1; width:160px; height:160px;" id="cfgPreviewPanel">
                <div class="gi-diff-empty"></div>
              </div>
              <div class="radio-group" id="cfgModeGroup" style="flex-direction:column; align-items:flex-start; gap:4px; margin-top:8px;">
                <label><input type="radio" name="cfgMode" value="auto"> Auto</label>
                <label><input type="radio" name="cfgMode" value="force" id="cfgModeForce"> Force Mask</label>
                <label><input type="radio" name="cfgMode" value="never"> Force No Mask</label>
              </div>
              <button type="button" class="btn" id="cfgAssignFile" style="margin-top:8px;">Assign file…</button>
              <div class="field-hint" id="cfgDetailStatus" style="margin-top:8px;">Select a glyph on the left.</div>
            </div>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="field-row" style="flex-direction: row; align-items: center; gap: 10px; margin-bottom: 0;">
          <button type="button" class="btn accent" id="genGenerate">Generate</button>
          <button type="button" class="btn" id="genHalt" disabled>Halt</button>
          <button type="button" class="btn" id="genAbort" disabled>Abort</button>
          <button type="button" class="btn" id="genOpenOutput" style="margin-left: auto;">Open Output Folder</button>
          <button type="button" class="btn" id="genExportKfps">Export to KFPS…</button>
        </div>
        <div class="gen-progress" id="genProgress"><div class="gen-progress-bar"></div></div>
        <div class="field-hint" id="genRunStatus" style="margin-top: 8px;">
          Halt finishes the glyph in progress, then keeps what generated so far. Abort does the same, then
          deletes every file this run wrote. Progress and the final result appear in the Log panel below.
        </div>
      </div>

      <div class="section">
        <div class="section-title">Live Preview</div>
        <div class="gen-live-preview">
          <div class="gi-diff-panel" style="aspect-ratio: auto; width: 160px; height: 160px;" id="genLivePreviewPanel">
            <div class="gi-diff-empty"></div>
          </div>
          <div class="field-hint" id="genLiveStats">Click Generate to watch glyphs appear here.</div>
        </div>
      </div>
        </div>

        <div>
          <div class="section">
            <div class="section-title">Color</div>
            <div class="radio-group" style="margin-bottom: 8px;">
              <label><input type="radio" name="genColorMode" value="solid" checked> Solid Color</label>
              <label><input type="radio" name="genColorMode" value="high_contrast"> High Contrast (KFPS Fabric Editor)</label>
            </div>
            <div id="genColorPicker"></div>
            <div id="genHcSection" style="display:none;">
              <div class="path-field" style="margin-bottom: 8px;">
                <span class="field-label">Seed</span>
                <input type="number" class="path-input" id="genHcSeed" value="0" min="0" style="max-width: 140px;">
                <button type="button" class="btn" id="genHcRandomize">Randomize</button>
              </div>
              <div class="field-hint">Each glyph's own shapes get an individual color from a curated high-contrast palette, applied to the exported shapes themselves. Deterministic for a given seed.</div>
            </div>
          </div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    const els = {};
    container.querySelectorAll('[id]').forEach((el) => { els[el.id] = el; });

    let fontPath = '';
    let prefixEdited = false;
    let pendingGeneration = null;
    let policyValid = false;
    let lastFontInfo = null; // structured generator.font_info result, for the variable-font confirm at generate time

    // -- 1. font -----------------------------------------------------------
    function refreshFontInfo() {
      lastFontInfo = null;
      if (!fontPath) {
        els.genLowercaseWarning.textContent = '';
        els.genLargeFontWarning.textContent = '';
        els.genVariationStatus.textContent = '';
        return;
      }
      api.call('generator.font_info', { font_path: fontPath }).then((resp) => {
        if (!resp.ok) return;
        lastFontInfo = resp.result;
        els.genLowercaseWarning.textContent = resp.result.lowercase_warning
          ? `⚠ ${resp.result.lowercase_warning}` : '';
        els.genLargeFontWarning.textContent = resp.result.total_supported > 1000
          ? `⚠ This font contains ${resp.result.total_supported.toLocaleString()} unique characters. `
            + 'Consider using Advanced Generation to manage this large font more carefully.'
          : '';
        els.genVariationStatus.textContent = resp.result.variation_status;
      });
    }
    function onFontChosen(path, suggestedName) {
      fontPath = path;
      els.genFontPath.textContent = path;
      api.call('generator.set_current_font', { font_path: path });
      if (!prefixEdited) {
        const stem = (suggestedName || path.split(/[\\/]/).pop().replace(/\.[^.]+$/, ''));
        els.genPrefix.value = stem.toUpperCase().replace(/\s+/g, '-').replace(/[^A-Z0-9_-]/g, '') || 'CUSTOM';
        refreshFilenamePreview();
      }
      refreshFontInfo();
      refreshCharsetSummary();
      renderFontGrid();
    }
    const fontSearch = window.ForzaFontSearch.create(els.genFontSearch, {
      placeholder: 'Search installed fonts…', width: '100%',
      onSelect: (font) => onFontChosen(font.path, font.name),
      onQueryChange: (q) => {
        fontGridQuery = q;
        clearTimeout(fontGridDebounce);
        fontGridDebounce = setTimeout(renderFontGrid, 120);
      },
    });
    els.genBrowseFont.addEventListener('click', async () => {
      const resp = await api.call('generator.browse_font', {});
      if (resp.ok && !resp.result.cancelled) { fontSearch.setValue(resp.result.path.split(/[\\/]/).pop()); onFontChosen(resp.result.path); }
    });
    els.genRescanFonts.addEventListener('click', async () => {
      // The app already loads and classifies every installed font
      // automatically at startup (see handlers/fonts.py's register()) --
      // this is only needed if a font got installed after that already
      // ran, so it's a deliberate manual action, not something that
      // happens on its own.
      const original = els.genRescanFonts.textContent;
      els.genRescanFonts.disabled = true;
      els.genRescanFonts.textContent = 'Rescanning…';
      await window.ForzaFontSearch.rescan();
      allFontsPromise = null;
      fontGridImageCache.clear();
      await renderFontGrid();
      els.genRescanFonts.textContent = original;
      els.genRescanFonts.disabled = false;
    });
    els.genSendToAdvanced.addEventListener('click', () => {
      if (!fontPath) { els.genVariationStatus.textContent = 'Select a font first.'; return; }
      window.ForzaShell.showTab('advanced', { fontPath });
    });
    els.genSendToDirect.addEventListener('click', () => {
      if (!fontPath) { els.genVariationStatus.textContent = 'Select a font first.'; return; }
      window.ForzaShell.showTab('direct', { fontPath });
    });

    // Visual "Grid" font browser: every installed font rendered in its own
    // typeface. Filters live off the same search box above (via
    // onQueryChange) instead of a separate List/Grid toggle -- the text
    // dropdown already covers "list", so this only adds the part that was
    // actually missing: seeing fonts rendered in their own typeface.
    // Unlike Tkinter's old Grid view, this shows every matching font with
    // no display cap -- the app already classifies and pre-renders every
    // installed font's tile at startup (handlers/fonts.py), so there's no
    // per-tile cost left to cap against, and a scrollable grid of a few
    // hundred small divs is cheap for a browser to lay out.
    //
    // Sort/type-filter toolbar and the script filter (below) both narrow
    // this same grid; the search dropdown above stays a plain by-name
    // search across every installed font regardless -- it's a shared
    // component used by several other tabs, so tying its results to
    // Generator-only sort/filter state would be a surprising side effect
    // for those other tabs.
    let allFontsPromise = null;
    let fontGridQuery = '';
    let fontGridDebounce = null;
    let fontGridRequestId = 0;
    let fontSort = 'az';
    let activeTypeFilters = new Set(['.ttf', '.otf', '.woff2']);
    let activeScriptFilter = null; // e.g. "Japanese", set via "Select only <Script>"
    const fontGridImageCache = new Map(); // font name -> data URI

    // script_detect.py's cmap-coverage heuristic doesn't cover every script
    // the Characters section offers a "Select only <Script>" button for --
    // Khmer/Tamil/Vietnamese have alphabet cards but no detection
    // threshold (see forza_writer/script_detect.py's _SIMPLE_SCRIPTS).
    // Filtering the font grid by one of these would just hide every font,
    // which reads as broken rather than "no matches" -- so these fall back
    // to leaving the grid unfiltered, with a hint explaining why.
    const SCRIPT_FILTER_UNSUPPORTED = new Set(['Khmer', 'Tamil', 'Vietnamese']);

    function updateScriptChip() {
      if (!activeScriptFilter) {
        els.genFontScriptChip.style.display = 'none';
        els.genFontScriptChip.innerHTML = '';
        return;
      }
      els.genFontScriptChip.style.display = '';
      const message = SCRIPT_FILTER_UNSUPPORTED.has(activeScriptFilter)
        ? `Script detection isn't available for ${esc(activeScriptFilter)} yet -- showing all fonts.`
        : `Showing only ${esc(activeScriptFilter)}-capable fonts`;
      els.genFontScriptChip.innerHTML = `${message} <button type="button" class="chip-x" id="genFontScriptChipClear">✕</button>`;
      els.genFontScriptChip.querySelector('#genFontScriptChipClear').addEventListener('click', () => {
        activeScriptFilter = null;
        updateScriptChip();
        renderFontGrid();
      });
    }

    function renderGridTile(f) {
      return `<button type="button" class="gen-font-tile ${f.path === fontPath ? 'selected' : ''}"
                style="background-image:url('${fontGridImageCache.get(f.name) || ''}')"
                title="${esc(f.name)}"></button>`;
    }
    async function renderFontGrid() {
      const id = ++fontGridRequestId;
      if (!allFontsPromise) allFontsPromise = window.ForzaFontSearch.getFonts();
      const fonts = await allFontsPromise;
      if (id !== fontGridRequestId) return;

      const scriptFilterActive = activeScriptFilter && !SCRIPT_FILTER_UNSUPPORTED.has(activeScriptFilter);
      const needsClassification = scriptFilterActive || fontSort === 'glyphs';
      let classification = null;
      if (needsClassification) {
        els.genFontGridStatus.textContent = 'Checking script support and glyph counts (first time only)…';
        classification = await window.ForzaFontSearch.getClassification();
        if (id !== fontGridRequestId) return;
      }

      const q = fontGridQuery.trim().toLowerCase();
      let matches = fonts.filter((f) => {
        if (q && !f.name.toLowerCase().includes(q)) return false;
        const ext = `.${f.path.split('.').pop().toLowerCase()}`;
        if (!activeTypeFilters.has(ext)) return false;
        if (scriptFilterActive) {
          const info = classification[f.name];
          if (!info || !info.scripts.includes(activeScriptFilter)) return false;
        }
        return true;
      });
      if (fontSort === 'za') {
        matches = matches.slice().reverse(); // fonts arrives A-Z already
      } else if (fontSort === 'glyphs') {
        matches = matches.slice().sort((a, b) =>
          (classification[b.name]?.glyph_count || 0) - (classification[a.name]?.glyph_count || 0));
      }

      const visible = matches;
      els.genFontGridStatus.textContent = `${visible.length} font${visible.length === 1 ? '' : 's'}`;
      if (visible.length === 0) {
        els.genFontGrid.innerHTML = '<div class="field-hint" style="padding:6px;">No installed fonts match.</div>';
        return;
      }

      const uncached = visible.filter((f) => !fontGridImageCache.has(f.name));
      if (uncached.length > 0) {
        const resp = await api.call('fonts.render_grid_tiles',
          { fonts: uncached.map((f) => ({ name: f.name, path: f.path })) });
        if (id !== fontGridRequestId) return;
        if (resp.ok) resp.result.tiles.forEach((t) => fontGridImageCache.set(t.name, t.image));
      }
      if (id !== fontGridRequestId) return;

      els.genFontGrid.innerHTML = visible.map(renderGridTile).join('');
      els.genFontGrid.querySelectorAll('.gen-font-tile').forEach((btn, i) => {
        btn.addEventListener('click', () => {
          const font = visible[i];
          fontSearch.setValue(font.name);
          onFontChosen(font.path, font.name);
        });
      });
    }
    renderFontGrid();

    els.genFontSort.addEventListener('change', () => {
      fontSort = els.genFontSort.value;
      renderFontGrid();
    });
    container.querySelectorAll('.gen-font-type').forEach((cb) => {
      cb.addEventListener('change', () => {
        activeTypeFilters = new Set(
          Array.from(container.querySelectorAll('.gen-font-type:checked')).map((c) => c.value));
        renderFontGrid();
      });
    });

    // -- 2. characters (shared component) ------------------------------------
    async function refreshCharsetSummary() {
      const resp = await api.call('generator.charset_summary', { font_path: fontPath, ...characterSelector.getSelection() });
      if (!resp.ok) return;
      els.genCharCount.textContent = resp.result.text;
      els.genGenerate.textContent = resp.result.button_text;
    }
    const characterSelector = await window.ForzaCharacterSelector.create(els.genCharacters, {
      idPrefix: 'gen', onChange: refreshCharsetSummary,
      onScriptFilter: (script) => {
        activeScriptFilter = script;
        updateScriptChip();
        renderFontGrid();
      },
    });

    // -- 3. output mode -------------------------------------------------------
    // Card style matches Direct Generator's method cards (direct.js's
    // renderMethodCards): a plain clickable div per option, no visible radio
    // dot, selected state shown purely via the orange border/title color.
    let outputMode = 'json';
    function currentOutput() {
      return outputMode;
    }
    function renderOutputCards() {
      els.genOutputCards.innerHTML = OUTPUT_MODES.map((m) => `
        <div class="section method-card ${outputMode === m.key ? 'active' : ''}" data-key="${m.key}"
             style="margin-bottom:0; cursor:pointer; padding: 10px 14px; ${outputMode === m.key ? 'border-color: var(--accent);' : ''}">
          <div style="font-family: var(--display); font-weight: 600; font-size: 12px; ${outputMode === m.key ? 'color: var(--accent);' : ''}">${esc(m.title)}</div>
          <div class="field-hint" style="margin-top: 4px;">${esc(m.desc)}</div>
        </div>
      `).join('');
      els.genOutputCards.querySelectorAll('.method-card').forEach((card) => {
        card.addEventListener('click', () => {
          outputMode = card.dataset.key;
          renderOutputCards();
          refreshFilenamePreview();
          refreshReferenceWarning();
        });
      });
    }
    renderOutputCards();

    // -- 4. options ----------------------------------------------------------
    async function refreshFilenamePreview() {
      const resp = await api.call('generator.filename_preview', { prefix: els.genPrefix.value, output: currentOutput() });
      if (resp.ok) els.genFilenamePreview.textContent = `e.g. ${resp.result.upper} / ${resp.result.lower}`;
    }
    els.genPrefix.addEventListener('input', () => { prefixEdited = true; refreshFilenamePreview(); });

    let pathFields = {};
    async function refreshPathsSummary() {
      const resp = await api.call('settings.get_paths', {});
      if (!resp.ok) return;
      pathFields = Object.fromEntries(resp.result.fields.map((f) => [f.key, f.value]));
      els.genPathsSummary.textContent =
        `Reference modelbin: ${pathFields.reference_modelbin}   |   Fontpacks output dir: ${pathFields.output_dir}   |   Modelbin output dir: ${pathFields.modelbin_output_dir}`;
    }
    function refreshReferenceWarning() {
      els.genReferenceWarning.textContent = (currentOutput() === 'modelbin' && !pathFields.reference_modelbin)
        ? '⚠ Reference modelbin not set -- set it in Settings.' : '';
    }
    els.genGotoSettings.addEventListener('click', () => {
      document.querySelector('.nav-row[data-tab="settings"]')?.click();
    });

    async function refreshBackendStatus() {
      const requested = container.querySelector('input[name="genBackend"]:checked').value;
      const resp = await api.call('settings.get_compute_backend', { requested });
      els.genBackendStatus.textContent = resp.ok ? resp.result.text : resp.error;
    }
    els.genBackendGroup.addEventListener('change', async () => {
      const requested = container.querySelector('input[name="genBackend"]:checked').value;
      await api.call('settings.save_compute_backend', { requested });
      refreshBackendStatus();
    });

    // -- 5. color -------------------------------------------------------------
    const colorPicker = await window.ForzaColorPicker.create(els.genColorPicker, {
      settingsKey: 'color_generator', title: '',
    });
    container.querySelectorAll('input[name="genColorMode"]').forEach((radio) => {
      radio.addEventListener('change', () => {
        const hc = container.querySelector('input[name="genColorMode"]:checked').value === 'high_contrast';
        els.genColorPicker.style.display = hc ? 'none' : '';
        els.genHcSection.style.display = hc ? '' : 'none';
      });
    });
    els.genHcRandomize.addEventListener('click', () => {
      els.genHcSeed.value = Math.floor(Math.random() * (2 ** 31 - 1));
    });

    // -- 6. vinyl shapes (shared component) -----------------------------------
    const vinylShapes = await window.ForzaVinylShapes.create(els.genVinylShapes, {
      onChange: (_policy, valid) => { policyValid = valid; els.genGenerate.disabled = !valid; },
    });

    // -- per-glyph overrides (Configurator) -----------------------------------
    // Deliberately mirrors a real Tkinter quirk, not an oversight: opening
    // this workspace snapshots whichever font is selected above at that
    // moment. Changing the font selection while the workspace stays open
    // does NOT retarget it -- only closing and reopening (or Rescan) does.
    // Ported as-is rather than "fixed" to stay behaviorally identical to
    // the reference implementation.
    let cfgOpen = false;
    let cfgFontPath = '';
    let cfgOverrides = {};
    let cfgScanResults = {};
    let cfgSelectedChar = null;
    let cfgPendingScan = null;

    function cfgModeLabel(char) {
      const entry = cfgOverrides[char];
      if (!entry) return 'Auto';
      if (entry.mode === 'manual') return `Manual: ${(entry.file || '').split(/[\\/]/).pop()}`;
      return { force: 'Force Mask', never: 'Force No Mask' }[entry.mode] || 'Auto';
    }
    function cfgRowCells(char, rectText, autoText) {
      return `<td>${esc(char)}</td><td class="cfg-cat"></td><td class="cfg-rect">${esc(rectText)}</td>`
        + `<td class="cfg-auto">${esc(autoText)}</td><td class="cfg-mode">${esc(cfgModeLabel(char))}</td>`;
    }
    function cfgUpdateRow(char, rectText, autoText) {
      const row = els.cfgGlyphTableBody.querySelector(`tr[data-char="${CSS.escape(char)}"]`);
      if (!row) return;
      const category = row.querySelector('.cfg-cat').textContent;
      if (rectText === undefined) rectText = row.querySelector('.cfg-rect').textContent;
      if (autoText === undefined) autoText = row.querySelector('.cfg-auto').textContent;
      row.innerHTML = cfgRowCells(char, rectText, autoText);
      row.querySelector('.cfg-cat').textContent = category;
      if (char === cfgSelectedChar) row.classList.add('active');
    }
    function cfgApplyScanInfo(char, info) {
      cfgScanResults[char] = info;
      if (info.manual) { cfgUpdateRow(char, '(manual file)', '(manual file)'); return; }
      if (info.error) { cfgUpdateRow(char, '?', `error: ${info.error}`); return; }
      const rectText = info.rectilinear ? 'yes' : 'no';
      const autoText = info.auto_strategy ? `${info.auto_strategy} (${info.auto_shape_count})` : 'select to fit';
      cfgUpdateRow(char, rectText, autoText);
    }

    function cfgSetOpen(open) {
      if (open === cfgOpen) return;
      cfgOpen = open;
      els.cfgBody.style.display = open ? '' : 'none';
      els.cfgToggle.textContent = open ? '▼ Close per-glyph overrides' : '▶ Open per-glyph overrides';
      if (!open) { els.cfgSummary.textContent = 'Closed -- glyph scanning and previews are deferred.'; return; }
      if (!fontPath) {
        els.cfgScanStatus.textContent = 'Select a font above to inspect its glyphs.';
        els.cfgSummary.textContent = 'Open -- waiting for a Generator font selection.';
        return;
      }
      const needsScan = cfgFontPath !== fontPath;
      cfgFontPath = fontPath;
      els.cfgSummary.textContent = `Open -- editing ${fontPath.split(/[\\/]/).pop()}.`;
      if (needsScan || !els.cfgGlyphTableBody.children.length) cfgRescan();
    }
    els.cfgToggle.addEventListener('click', () => cfgSetOpen(!cfgOpen));

    async function cfgRescan() {
      cfgScanResults = {};
      cfgSelectedChar = null;
      els.cfgDetailStatus.textContent = 'Select a glyph on the left.';
      els.cfgPreviewPanel.innerHTML = '<div class="gi-diff-empty"></div>';
      container.querySelectorAll('input[name="cfgMode"]').forEach((r) => { r.checked = false; });

      const resp = await api.call('configurator.list_glyphs', { font_path: cfgFontPath });
      if (!resp.ok) { els.cfgScanStatus.textContent = resp.error; return; }
      cfgOverrides = resp.result.overrides;
      const entries = resp.result.entries;
      if (!entries.length) { els.cfgScanStatus.textContent = 'This font has no glyphs.'; return; }
      els.cfgGlyphTableBody.innerHTML = entries.map(([char, category]) => `
        <tr data-char="${esc(char)}">${cfgRowCells(char, '…', 'select to fit')}</tr>`).join('');
      els.cfgGlyphTableBody.querySelectorAll('tr').forEach((row, i) => {
        row.querySelector('.cfg-cat').textContent = entries[i][1];
      });
      els.cfgScanStatus.textContent = `Inspecting ${entries.length} glyph outline(s)…`;

      const scanResp = await api.call('configurator.start_scan', { font_path: cfgFontPath, segments: els.genSegments.value });
      if (scanResp.ok) cfgPendingScan = scanResp.result.generation;
    }
    els.cfgRescan.addEventListener('click', cfgRescan);

    const offScanProgress = window.__forzaEvents.on('configurator_scan_progress', (generation, payload) => {
      if (generation !== cfgPendingScan) return;
      Object.entries(payload.results).forEach(([char, info]) => cfgApplyScanInfo(char, info));
      els.cfgScanStatus.textContent = `Inspected ${payload.done} of ${payload.total} glyph outline(s)…`;
    });
    const offScanDone = window.__forzaEvents.on('configurator_scan_done', (generation, payload) => {
      if (generation !== cfgPendingScan) return;
      els.cfgScanStatus.textContent = `Inspected ${payload.total} glyph outline(s).`;
    });

    async function cfgSelectGlyph(char) {
      cfgSelectedChar = char;
      els.cfgGlyphTableBody.querySelectorAll('tr').forEach((row) => {
        row.classList.toggle('active', row.dataset.char === char);
      });
      const entry = cfgOverrides[char] || { mode: 'auto' };
      container.querySelectorAll('input[name="cfgMode"]').forEach((r) => { r.checked = (r.value === entry.mode); });
      await cfgRefreshDetail(char);
    }
    els.cfgGlyphTableBody.addEventListener('click', (e) => {
      const row = e.target.closest('tr');
      if (row) cfgSelectGlyph(row.dataset.char);
    });

    async function cfgRefreshDetail(char) {
      els.cfgDetailStatus.textContent = `Analyzing ${JSON.stringify(char)} in the background…`;
      const resp = await api.call('configurator.get_glyph_detail', {
        font_path: cfgFontPath, char, segments: els.genSegments.value,
        compute_backend: container.querySelector('input[name="genBackend"]:checked').value,
      });
      if (!resp.ok) { els.cfgDetailStatus.textContent = resp.error; return; }
      if (char !== cfgSelectedChar) return; // superseded by a newer selection
      const r = resp.result;
      els.cfgPreviewPanel.innerHTML = `<img src="${r.preview_image}" alt="Glyph preview" style="width:100%;height:100%;object-fit:contain;">`;
      els.cfgModeForce.disabled = !r.can_force_mask;
      if (r.effective_mode !== 'manual' && r.effective_mode !== (cfgOverrides[char] || {}).mode) {
        container.querySelectorAll('input[name="cfgMode"]').forEach((rb) => { rb.checked = (rb.value === r.effective_mode); });
      }
      if (r.info) cfgApplyScanInfo(char, r.info);
      if (r.mode === 'manual') {
        els.cfgDetailStatus.textContent =
          `${JSON.stringify(char)}: ${r.shape_count} shape(s), ${r.mask_count} mask cutout(s) -- manual: ${r.file_name}`;
      } else {
        let status = `${JSON.stringify(char)}: ${r.shape_count} shape(s), ${r.mask_count} mask cutout(s) (${r.strategy}, ${(r.backend || '').toUpperCase()}).`;
        const info = r.info || {};
        if (!info.rectilinear && info.can_force_mask && info.forced_iou != null) {
          status += ` Forcing costs IoU ${info.forced_iou.toFixed(2)} at ${info.forced_shape_count} shape(s).`;
        }
        els.cfgDetailStatus.textContent = status;
      }
    }

    container.querySelectorAll('input[name="cfgMode"]').forEach((radio) => {
      radio.addEventListener('change', async () => {
        if (!cfgSelectedChar) return;
        const mode = radio.value;
        if (mode === 'auto') delete cfgOverrides[cfgSelectedChar]; else cfgOverrides[cfgSelectedChar] = { mode };
        await api.call('configurator.set_override', { font_path: cfgFontPath, char: cfgSelectedChar, mode });
        cfgUpdateRow(cfgSelectedChar);
        cfgRefreshDetail(cfgSelectedChar);
      });
    });
    els.cfgAssignFile.addEventListener('click', async () => {
      if (!cfgSelectedChar) { els.cfgDetailStatus.textContent = 'Select a glyph first.'; return; }
      const resp = await api.call('configurator.assign_file', { font_path: cfgFontPath, char: cfgSelectedChar });
      if (!resp.ok || resp.result.cancelled) return;
      cfgOverrides[cfgSelectedChar] = { mode: 'manual', file: resp.result.path };
      container.querySelectorAll('input[name="cfgMode"]').forEach((r) => { r.checked = false; });
      cfgUpdateRow(cfgSelectedChar);
      cfgRefreshDetail(cfgSelectedChar);
    });
    els.cfgResetAll.addEventListener('click', async () => {
      if (!cfgFontPath) return;
      await api.call('configurator.reset_all', { font_path: cfgFontPath });
      cfgOverrides = {};
      els.cfgGlyphTableBody.querySelectorAll('tr').forEach((row) => cfgUpdateRow(row.dataset.char));
      if (cfgSelectedChar) {
        container.querySelectorAll('input[name="cfgMode"]').forEach((r) => { r.checked = (r.value === 'auto'); });
        cfgRefreshDetail(cfgSelectedChar);
      }
    });
    els.cfgForceAll.addEventListener('click', async () => {
      if (!cfgFontPath) return;
      const eligible = Object.entries(cfgScanResults)
        .filter(([char, info]) => info.rectilinear && info.can_force_mask
          && (cfgOverrides[char] || {}).mode !== 'manual')
        .map(([char]) => char);
      const resp = await api.call('configurator.force_all_rectilinear', { font_path: cfgFontPath, chars: eligible });
      if (!resp.ok) return;
      eligible.forEach((char) => { cfgOverrides[char] = { mode: 'force' }; cfgUpdateRow(char); });
      els.cfgScanStatus.textContent = `Forced mask on ${resp.result.changed} eligible rectilinear glyph(s).`;
      if (cfgSelectedChar && (cfgOverrides[cfgSelectedChar] || {}).mode === 'force') {
        container.querySelectorAll('input[name="cfgMode"]').forEach((r) => { r.checked = (r.value === 'force'); });
        cfgRefreshDetail(cfgSelectedChar);
      }
    });

    // -- run: generate / halt / abort / export -------------------------------
    function setRunning(running) {
      els.genGenerate.disabled = running || !policyValid;
      els.genHalt.disabled = !running;
      els.genAbort.disabled = !running;
      els.genProgress.classList.toggle('active', running);
    }
    els.genGenerate.addEventListener('click', async () => {
      if (!fontPath) { els.genRunStatus.textContent = 'Select a font first.'; return; }

      // Generator always passes the file straight through -- fontTools
      // extracts whatever the file's raw, un-instantiated glyf/gvar master
      // happens to be, not necessarily Regular and never a style the user
      // actually chose. Block a silent generate-from-raw-defaults, matching
      // Tkinter's _confirm_variable_font_generation (shell.py).
      if (lastFontInfo && lastFontInfo.is_variable) {
        const fontName = fontPath.split(/[\\/]/).pop();
        const proceed = confirm(
          `"${fontName}" is a variable font with ${lastFontInfo.instance_count} named instance(s) `
          + `(file default: ${lastFontInfo.defaults}).\n\n`
          + "Generating here uses the file's raw, un-instantiated outlines, not a deliberately chosen "
          + 'weight or style. Use Advanced Generator to pick a named instance, such as Regular or Bold, '
          + 'or custom axis coordinates instead.\n\n'
          + 'Continue anyway with the raw default outlines?'
        );
        if (!proceed) { els.genRunStatus.textContent = 'Generation cancelled. Use Advanced Generator for this variable font.'; return; }
      }

      // A fresh count, not whatever refreshCharsetSummary last cached --
      // this is the actual gate before an expensive/long-running job, so it
      // needs to reflect the current character selection exactly.
      const summaryResp = await api.call('generator.charset_summary', { font_path: fontPath, ...characterSelector.getSelection() });
      const glyphCount = summaryResp.ok ? summaryResp.result.count : null;
      if (glyphCount !== null && glyphCount >= 500) {
        const proceed = confirm(
          `This will generate ${glyphCount.toLocaleString()} glyphs and may take a long time.\n\n`
          + 'Continue with this large job?'
        );
        if (!proceed) { els.genRunStatus.textContent = `Large generation cancelled before starting (${glyphCount.toLocaleString()} glyphs).`; return; }
      }

      const output = currentOutput();
      const payload = {
        font_path: fontPath, out_dir: output === 'modelbin' ? pathFields.modelbin_output_dir : pathFields.output_dir,
        prefix: els.genPrefix.value, output, reference: output === 'modelbin' ? pathFields.reference_modelbin : null,
        segments: els.genSegments.value, allow_stencil: els.genAllowStencil.checked,
        compute_backend: container.querySelector('input[name="genBackend"]:checked').value,
        policy: vinylShapes.getPolicy(),
        color_mode: container.querySelector('input[name="genColorMode"]:checked').value,
        solid_color: colorPicker.getColor() || [255, 255, 255, 255],
        high_contrast_seed: parseInt(els.genHcSeed.value, 10) || 0,
        ...characterSelector.getSelection(),
      };
      const resp = await api.call('generator.start', payload);
      if (!resp.ok) { els.genRunStatus.textContent = resp.error; return; }
      pendingGeneration = resp.result.generation;
      setRunning(true);
      els.genLiveStats.textContent = 'Generating…';
      els.genLivePreviewPanel.innerHTML = '<div class="gi-diff-empty"></div>';
    });
    els.genHalt.addEventListener('click', () => api.call('generator.halt', {}));
    els.genAbort.addEventListener('click', () => api.call('generator.abort', {}));
    els.genOpenOutput.addEventListener('click', async () => {
      const output = currentOutput();
      const resp = await api.call('generator.open_output_folder', {
        prefix: els.genPrefix.value, output,
        out_dir: output === 'modelbin' ? pathFields.modelbin_output_dir : pathFields.output_dir,
        segments: els.genSegments.value,
        compute_backend: container.querySelector('input[name="genBackend"]:checked').value,
      });
      if (resp.ok && !resp.result.opened) {
        els.genRunStatus.textContent = `This folder doesn't exist yet: ${resp.result.path}`;
      } else if (!resp.ok) {
        els.genRunStatus.textContent = resp.error;
      }
    });
    els.genExportKfps.addEventListener('click', async () => {
      const resp = await api.call('generator.export_kfps', {
        prefix: els.genPrefix.value, out_dir: pathFields.output_dir, segments: els.genSegments.value,
        compute_backend: container.querySelector('input[name="genBackend"]:checked').value,
      });
      els.genRunStatus.textContent = resp.ok ? `Exported to KFPS: ${resp.result.path}` : resp.error;
    });

    const offGlyph = window.__forzaEvents.on('generator_glyph', (generation, payload) => {
      if (generation !== pendingGeneration) return;
      els.genLivePreviewPanel.innerHTML = `<img src="${payload.preview_image}" alt="Live glyph preview" style="width:100%;height:100%;object-fit:contain;">`;
      els.genLiveStats.textContent = payload.stats;
    });
    const offDone = window.__forzaEvents.on('generator_done', (generation) => {
      if (generation !== pendingGeneration) return;
      setRunning(false);
    });

    // -- initial load -----------------------------------------------------
    await refreshPathsSummary();
    refreshFilenamePreview();
    refreshBackendStatus();
    refreshReferenceWarning();
    refreshCharsetSummary();

    // A tab switch carrying a font (Advanced Generator's "Open per-glyph
    // overrides for this instance" sends the instantiated instance path
    // plus a variation-slugged prefix and asks to land straight in the
    // Configurator workspace already scoped to it) -- see shell.js's
    // showTab(tabId, opts) and handlers/advanced.py's open_instance_overrides.
    if (opts && opts.fontPath) {
      fontSearch.setValue(opts.fontPath.split(/[\\/]/).pop());
      onFontChosen(opts.fontPath);
      if (opts.prefix) { els.genPrefix.value = opts.prefix; prefixEdited = true; refreshFilenamePreview(); }
      if (opts.openConfigurator) cfgSetOpen(true);
    }

    return () => { offGlyph(); offDone(); offScanProgress(); offScanDone(); colorPicker.destroy(); };
  }

  window.ForzaTabs.generator = mount;
})();
