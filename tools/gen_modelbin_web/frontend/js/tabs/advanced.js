// Advanced Generator tab: variable-font axis/instance selection and
// generation.
//
// Characters and Vinyl Shapes reuse the same shared components Generator
// uses (js/character-selector.js, js/vinyl-shapes.js) -- see
// handlers/advanced.py's module docstring for why this tab gets its own
// instance of each rather than literally sharing Generator's live state.
// Generation shares Generator's actual batch-runner lock (only one build
// running at a time across the app), so Halt/Abort here call the same
// generator.halt/generator.abort handlers Generator's own buttons do.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  const OUTPUT_MODES = [
    { key: 'json', title: 'Shape Fitting (.json)',
      desc: "Analyzes each glyph and approximates it using Forza's full primitive-shape library, with optional masks." },
    { key: 'json_legacy', title: 'Pixel Tracing (.json)',
      desc: 'Rasterizes each glyph, then combines the filled pixels into rectangular vinyl layers.' },
    { key: 'modelbin', title: 'Custom Mesh (.modelbin)',
      desc: 'Experimental. The native files Forza games use for vinyls. KFPS cannot open this format.' },
  ];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  async function mount(container, opts) {
    container.innerHTML = `
      <h2 class="page-heading">Advanced Generator</h2>
      <div class="intro-text">
        Generate a deliberate instance from a variable font. Choose a named style such as Regular or
        Bold, or set the font axes yourself; Forza Writer pins those coordinates to one static face.
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 340px;">
        <div>
      <div class="section">
        <div class="section-title">1. Variable Font</div>
        <div class="path-field" style="margin-bottom: 8px;">
          <input type="text" class="path-input" id="advFont" placeholder="Font path">
          <button type="button" class="btn" id="advBrowseFont">Browse…</button>
          <button type="button" class="btn" id="advUseGeneratorFont">Use current from Generator</button>
        </div>
        <div class="field-hint" id="advFontStatus">Choose a variable .ttf/.otf font. Static fonts are identified clearly.</div>
      </div>

      <div class="section" id="advAxesSection" style="display:none;">
        <div class="section-title">2. Instance and Axes</div>
        <div class="path-field" style="margin-bottom: 8px;">
          <span class="field-label">Named instance</span>
          <select class="path-input" id="advInstance" style="max-width: 280px;"></select>
          <span class="field-hint">Regular is preferred when the font provides it.</span>
        </div>
        <div id="advAxesBody"></div>
        <div class="path-field" style="margin-top: 8px; margin-bottom: 0;">
          <button type="button" class="btn" id="advOpenOverrides">Open per-glyph overrides for this instance</button>
          <span class="field-hint">Instantiates this exact instance, then opens Generator's Configurator scoped to it.</span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">3. Output Method</div>
        <div id="advOutputCards" style="display:flex; flex-direction:column; gap:8px;"></div>
      </div>

      <div class="section">
        <div class="section-title">4. Preview</div>
        <div class="path-field" style="margin-bottom: 8px;">
          <input type="text" class="path-input" id="advPreviewText" value="繁體中文 字體預覽 ABC 123" style="flex:1;">
          <button type="button" class="btn" id="advRefreshPreview">Refresh instance preview</button>
        </div>
        <div class="gi-diff-panel" style="aspect-ratio: auto; height: 150px;" id="advPreviewPanel">
          <div class="gi-diff-empty"></div>
        </div>
        <div class="field-hint" id="advPreviewStatus" style="margin-top: 6px;">Select a variable font to preview it.</div>
      </div>

      <div class="section">
        <div class="section-title">5. Characters</div>
        <div id="advCharacters"></div>
        <div class="field-hint" id="advCharCount"></div>
      </div>

      <div class="section">
        <div class="section-title">6. Vinyl Shapes</div>
        <div id="advVinylShapes"></div>
      </div>

      <div class="section">
        <div class="section-title">7. Generation</div>
        <div class="field-hint" style="margin-bottom: 8px;">
          Uses this page's character selection, curve smoothness, and vinyl shapes above, plus the
          shared Fontpacks output directory and processor from Settings. Only this one instance is
          generated; named styles are never multiplied automatically.
        </div>
        <div class="path-field" style="margin-bottom: 8px;">
          <span class="field-label">Curve Smoothness</span>
          <input type="number" class="path-input" id="advSegments" value="8" min="1" max="32" style="max-width: 70px;">
          <span class="field-label" style="margin-left: 16px;">Filename prefix</span>
          <input type="text" class="path-input" id="advPrefix" value="CUSTOM" style="max-width: 200px;">
        </div>
        <div class="field-hint" id="advWorkload" style="color: var(--warn); margin-bottom: 8px;">No variable font selected.</div>
        <div class="field-row" style="flex-direction: row; align-items: center; gap: 10px; margin-bottom: 0;">
          <button type="button" class="btn accent" id="advGenerate">Generate selected instance</button>
          <button type="button" class="btn" id="advHalt" disabled>Halt</button>
          <button type="button" class="btn" id="advAbort" disabled>Abort</button>
        </div>
        <div class="gen-progress" id="advProgress"><div class="gen-progress-bar"></div></div>
        <div class="field-hint" id="advRunStatus" style="margin-top: 8px;">Progress and the final result appear in the Log panel below.</div>
      </div>
        </div>

        <div>
          <div class="section">
            <div class="section-title">Color</div>
            <div id="advColorPicker"></div>
          </div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    const els = {};
    container.querySelectorAll('[id]').forEach((el) => { els[el.id] = el; });

    let fontPath = '';
    let info = null; // last advanced.inspect_font result
    let axisValues = {}; // tag -> current value
    let settingInstance = false;
    let pendingGeneration = null;
    let policyValid = false;

    // -- 1. font -------------------------------------------------------------
    els.advBrowseFont.addEventListener('click', async () => {
      const resp = await api.call('advanced.browse_font', {});
      if (resp.ok && !resp.result.cancelled) { els.advFont.value = resp.result.path; loadFont(resp.result.path); }
    });
    els.advFont.addEventListener('change', () => { if (els.advFont.value.trim()) loadFont(els.advFont.value.trim()); });
    els.advUseGeneratorFont.addEventListener('click', async () => {
      const resp = await api.call('advanced.get_current_generator_font', {});
      if (!resp.ok || !resp.result.font_path) {
        els.advFontStatus.textContent = 'No font selected on the Generator tab yet.';
        return;
      }
      els.advFont.value = resp.result.font_path;
      loadFont(resp.result.font_path);
    });
    els.advOpenOverrides.addEventListener('click', async () => {
      if (!fontPath || !info || !info.is_variable) { els.advFontStatus.textContent = 'Choose a variable font first.'; return; }
      const resp = await api.call('advanced.open_instance_overrides', { font_path: fontPath, coordinates: axisValues });
      if (!resp.ok) { els.advFontStatus.textContent = resp.error; return; }
      window.ForzaShell.showTab('generator', {
        fontPath: resp.result.instance_path,
        prefix: `${els.advPrefix.value}-${resp.result.slug}`,
        openConfigurator: true,
      });
    });

    async function loadFont(path) {
      const resp = await api.call('advanced.inspect_font', { font_path: path });
      if (!resp.ok) { els.advFontStatus.textContent = resp.error; return; }
      fontPath = path;
      info = resp.result;
      els.advFontStatus.textContent = info.status;
      if (!info.is_variable) {
        els.advAxesSection.style.display = 'none';
        axisValues = {};
        refreshWorkload();
        return;
      }
      els.advAxesSection.style.display = '';
      els.advInstance.innerHTML = Object.keys(info.instances).map((label) =>
        `<option value="${esc(label)}">${esc(label)}</option>`).join('') + '<option value="Custom">Custom</option>';
      renderAxes();
      els.advInstance.value = info.preferred_instance;
      applyInstance(info.preferred_instance);
      refreshPreview();
    }

    function renderAxes() {
      els.advAxesBody.innerHTML = info.axes.map((axis) => `
        <div class="path-field" style="margin-bottom: 6px;" data-axis="${esc(axis.tag)}">
          <span class="field-label" style="min-width: 160px;">${esc(axis.name)} (${esc(axis.tag)})</span>
          <input type="range" class="adv-axis-slider" data-tag="${esc(axis.tag)}"
                 min="${axis.minimum}" max="${axis.maximum}" step="any" value="${axis.default}" style="flex:1;">
          <input type="number" class="path-input adv-axis-number" data-tag="${esc(axis.tag)}"
                 min="${axis.minimum}" max="${axis.maximum}" value="${axis.default}" style="max-width: 90px;">
          <span class="field-hint">${axis.minimum.toFixed(1)} – ${axis.maximum.toFixed(1)}</span>
        </div>`
      ).join('');
      container.querySelectorAll('.adv-axis-slider').forEach((el) => {
        el.addEventListener('input', () => onAxisChanged(el.dataset.tag, el.value));
      });
      container.querySelectorAll('.adv-axis-number').forEach((el) => {
        el.addEventListener('change', () => onAxisChanged(el.dataset.tag, el.value));
      });
    }
    function onAxisChanged(tag, value) {
      const axis = info.axes.find((a) => a.tag === tag);
      const v = Math.min(axis.maximum, Math.max(axis.minimum, parseFloat(value) || axis.default));
      axisValues[tag] = v;
      container.querySelectorAll(`[data-axis="${CSS.escape(tag)}"] .adv-axis-slider`).forEach((el) => { el.value = v; });
      container.querySelectorAll(`[data-axis="${CSS.escape(tag)}"] .adv-axis-number`).forEach((el) => { el.value = v; });
      if (!settingInstance) {
        els.advInstance.value = 'Custom';
        refreshWorkload();
      }
    }
    function applyInstance(label) {
      const coords = info.instances[label];
      if (!coords) return;
      settingInstance = true;
      try {
        info.axes.forEach((axis) => { onAxisChanged(axis.tag, coords[axis.tag] ?? axis.default); });
      } finally { settingInstance = false; }
      refreshWorkload();
    }
    els.advInstance.addEventListener('change', () => applyInstance(els.advInstance.value));

    // -- 3. output mode -------------------------------------------------------
    // Card style matches Direct Generator's method cards (direct.js's
    // renderMethodCards): a plain clickable div per option, no visible radio
    // dot, selected state shown purely via the orange border/title color.
    let outputMode = 'json';
    function currentOutput() {
      return outputMode;
    }
    function renderOutputCards() {
      els.advOutputCards.innerHTML = OUTPUT_MODES.map((m) => `
        <div class="section method-card ${outputMode === m.key ? 'active' : ''}" data-key="${m.key}"
             style="margin-bottom:0; cursor:pointer; padding: 10px 14px; ${outputMode === m.key ? 'border-color: var(--accent);' : ''}">
          <div style="font-family: var(--display); font-weight: 600; font-size: 12px; ${outputMode === m.key ? 'color: var(--accent);' : ''}">${esc(m.title)}</div>
          <div class="field-hint" style="margin-top: 4px;">${esc(m.desc)}</div>
        </div>
      `).join('');
      els.advOutputCards.querySelectorAll('.method-card').forEach((card) => {
        card.addEventListener('click', () => {
          outputMode = card.dataset.key;
          renderOutputCards();
        });
      });
    }
    renderOutputCards();

    // -- 4. preview ------------------------------------------------------------
    async function refreshPreview() {
      if (!fontPath || !info || !info.is_variable) { els.advPreviewStatus.textContent = 'Choose a variable font first.'; return; }
      els.advPreviewStatus.textContent = 'Preparing the instance…';
      const resp = await api.call('advanced.preview', {
        font_path: fontPath, coordinates: axisValues, text: els.advPreviewText.value,
      });
      if (!resp.ok) { els.advPreviewStatus.textContent = resp.error; return; }
      els.advPreviewPanel.innerHTML = `<img src="${resp.result.preview_image}" alt="Instance preview" style="width:100%;height:100%;object-fit:contain;">`;
      els.advPreviewStatus.textContent = resp.result.status;
    }
    els.advRefreshPreview.addEventListener('click', refreshPreview);

    // -- 5. color ---------------------------------------------------------------
    const colorPicker = await window.ForzaColorPicker.create(els.advColorPicker, {
      settingsKey: 'color_advanced', title: '',
    });

    // -- 6. characters (shared component) --------------------------------------
    async function refreshCharsetCount() {
      const resp = await api.call('generator.charset_summary', { font_path: fontPath, ...characterSelector.getSelection() });
      if (resp.ok) els.advCharCount.textContent = resp.result.text;
      refreshWorkload();
    }
    const characterSelector = await window.ForzaCharacterSelector.create(els.advCharacters, {
      idPrefix: 'adv', onChange: refreshCharsetCount,
    });

    // -- 7. vinyl shapes (shared component) -------------------------------------
    const vinylShapes = await window.ForzaVinylShapes.create(els.advVinylShapes, {
      onChange: (_policy, valid) => { policyValid = valid; els.advGenerate.disabled = !valid; },
    });

    // -- 8. generation ------------------------------------------------------------
    async function refreshWorkload() {
      if (!fontPath || !info || !info.is_variable) { els.advWorkload.textContent = 'Choose a variable font before generating.'; return; }
      const resp = await api.call('advanced.workload_summary', {
        font_path: fontPath, coordinates: axisValues, prefix: els.advPrefix.value,
        instance_label: els.advInstance.value, ...characterSelector.getSelection(),
      });
      if (resp.ok) els.advWorkload.textContent = resp.result.text;
    }
    els.advPrefix.addEventListener('input', refreshWorkload);

    function setRunning(running) {
      els.advGenerate.disabled = running || !policyValid;
      els.advHalt.disabled = !running;
      els.advAbort.disabled = !running;
      els.advProgress.classList.toggle('active', running);
    }
    els.advGenerate.addEventListener('click', async () => {
      if (!fontPath || !info || !info.is_variable) { els.advRunStatus.textContent = 'Choose a variable font on Advanced Generator first.'; return; }

      // A fresh count for this one instance, matching Tkinter's
      // _start_advanced_batch -- this is the actual gate before an
      // expensive job, so it needs the current character selection exactly.
      const summaryResp = await api.call('generator.charset_summary', { font_path: fontPath, ...characterSelector.getSelection() });
      const glyphCount = summaryResp.ok ? summaryResp.result.count : null;
      if (glyphCount !== null && glyphCount >= 500) {
        const proceed = confirm(
          `This will generate ${glyphCount.toLocaleString()} glyphs for one variable-font instance.\n\n`
          + 'Continue with this large job?'
        );
        if (!proceed) return;
      }

      const [pathsResp, settings] = await Promise.all([
        api.call('settings.get_paths', {}), api.get_settings(),
      ]);
      const pathFields = pathsResp.ok ? Object.fromEntries(pathsResp.result.fields.map((f) => [f.key, f.value])) : {};
      const output = currentOutput();
      const payload = {
        font_path: fontPath, out_dir: pathFields.output_dir,
        prefix: els.advPrefix.value, output, reference: output === 'modelbin' ? pathFields.reference_modelbin : null,
        segments: els.advSegments.value, allow_stencil: true,
        compute_backend: settings.compute_backend || 'auto',
        policy: vinylShapes.getPolicy(),
        color_mode: 'solid', solid_color: colorPicker.getColor() || [255, 255, 255, 255],
        coordinates: axisValues, instance_label: els.advInstance.value,
        ...characterSelector.getSelection(),
      };
      const resp = await api.call('advanced.start', payload);
      if (!resp.ok) { els.advRunStatus.textContent = resp.error; return; }
      pendingGeneration = resp.result.generation;
      setRunning(true);
    });
    els.advHalt.addEventListener('click', () => api.call('generator.halt', {}));
    els.advAbort.addEventListener('click', () => api.call('generator.abort', {}));

    const offDone = window.__forzaEvents.on('generator_done', (generation) => {
      if (generation !== pendingGeneration) return;
      setRunning(false);
    });

    // Generator's "Send selected font to Advanced Generator" landed here
    // with a font already picked -- load it the same way Browse… would.
    if (opts && opts.fontPath) { els.advFont.value = opts.fontPath; loadFont(opts.fontPath); }

    return () => { offDone(); colorPicker.destroy(); };
  }

  window.ForzaTabs.advanced = mount;
})();
