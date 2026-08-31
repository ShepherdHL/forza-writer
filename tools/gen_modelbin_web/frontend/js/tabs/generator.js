// Generator tab: font selection, character selection, output mode, vinyl
// shape policy, and the main batch-generation run. Mirrors
// tools/gen_modelbin_gui/tabs/generator.py + the shared batch runner on
// tools/gen_modelbin_gui/shell.py.
//
// Character selection and vinyl-shape policy are shared components
// (js/character-selector.js, js/vinyl-shapes.js) also used by Advanced
// Generator -- see vinyl-shapes.js's module comment for why Advanced
// Generator needs its own instance rather than literally sharing this
// tab's live state.
//
// Two deliberate, non-functionality-losing scope simplifications (see
// handlers/generator.py's module docstring for the full rationale):
//   - Font browsing is search-only (ForzaFontSearch) + "Browse on machine…",
//     dropping the List/Grid toggle and script-tab filter.
//   - Non-Latin alphabet groups are all shown at once rather than gated
//     behind a font-browser script tab.
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

  async function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">Generator</h2>
      <div class="intro-text">
        Pick a font, choose which characters to include, pick an output type, then click Generate.
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 340px;">
        <div>
      <div class="section">
        <div class="section-title">1. Font</div>
        <div class="path-field" style="margin-bottom: 8px;">
          <div id="genFontSearch" style="flex:1;"></div>
          <button type="button" class="btn" id="genBrowseFont">Browse on machine…</button>
        </div>
        <div class="field-hint" id="genFontPath">(no font selected)</div>
        <div class="field-hint" id="genLowercaseWarning" style="color: var(--warn);"></div>
        <div class="field-hint" id="genLargeFontWarning" style="color: var(--warn);"></div>
        <div class="field-hint" id="genVariationStatus"></div>
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
          <button type="button" class="btn" id="genExportKfps" style="margin-left: auto;">Export to KFPS…</button>
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
      if (!prefixEdited) {
        const stem = (suggestedName || path.split(/[\\/]/).pop().replace(/\.[^.]+$/, ''));
        els.genPrefix.value = stem.toUpperCase().replace(/\s+/g, '-').replace(/[^A-Z0-9_-]/g, '') || 'CUSTOM';
        refreshFilenamePreview();
      }
      refreshFontInfo();
      refreshCharsetSummary();
    }
    const fontSearch = window.ForzaFontSearch.create(els.genFontSearch, {
      placeholder: 'Search installed fonts…', width: '100%',
      onSelect: (font) => onFontChosen(font.path, font.name),
    });
    els.genBrowseFont.addEventListener('click', async () => {
      const resp = await api.call('generator.browse_font', {});
      if (resp.ok && !resp.result.cancelled) { fontSearch.setValue(resp.result.path.split(/[\\/]/).pop()); onFontChosen(resp.result.path); }
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
    });

    // -- 3. output mode -------------------------------------------------------
    function currentOutput() {
      return container.querySelector('input[name="genOutput"]:checked')?.value || 'json';
    }
    function renderOutputCards() {
      const chosen = currentOutput();
      els.genOutputCards.innerHTML = OUTPUT_MODES.map((m) => `
        <label class="section method-card ${chosen === m.key ? 'active' : ''}"
               style="margin-bottom:0; cursor:pointer; padding: 10px 14px; display:block; ${chosen === m.key ? 'border-color: var(--accent);' : ''}">
          <input type="radio" name="genOutput" value="${m.key}" ${chosen === m.key ? 'checked' : ''} style="margin-right:8px;">
          <span style="font-family: var(--display); font-weight: 600; font-size: 12px; ${chosen === m.key ? 'color: var(--accent);' : ''}">${esc(m.title)}</span>
          <div class="field-hint" style="margin-top: 4px; margin-left: 22px;">${esc(m.desc)}</div>
        </label>
      `).join('');
      container.querySelectorAll('input[name="genOutput"]').forEach((radio) => {
        radio.addEventListener('change', () => { renderOutputCards(); refreshFilenamePreview(); refreshReferenceWarning(); });
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

    return () => { offGlyph(); offDone(); offScanProgress(); offScanDone(); colorPicker.destroy(); };
  }

  window.ForzaTabs.generator = mount;
})();
