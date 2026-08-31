// Glyph Template tab: generate a KFPS-importable glyph template for a
// font. Second consumer of the shared font-search component.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function hexToRgb(hex) {
    let h = hex.trim().replace('#', '');
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    if (!/^[0-9a-f]{6}$/i.test(h)) return null;
    const n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgbaToHex(rgba) {
    return '#' + [rgba[0], rgba[1], rgba[2]].map((c) => c.toString(16).padStart(2, '0')).join('');
  }

  async function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">Glyph Template</h2>
      <div class="intro-text">
        Generate a KFPS-importable glyph template for a font: a labeled grid, one cell per
        character, with the font's own letterforms embedded as a tracing guide. Open the exported
        project in Kloudy's Fabric Editor, draw over each glyph, group each glyph's shapes, then run
        import_glyph_template.py to turn it into a fontpack.
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 340px;">
        <div>
      <div class="section">
        <div class="section-title">1. Font</div>
        <div style="display:flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 8px;">
          <div id="gtFontSearch"></div>
          <button type="button" class="btn" id="gtBrowseFont">Browse file…</button>
        </div>
        <div class="field-hint" id="gtFontStatus" style="margin-bottom: 10px;">Select a font to build a template for.</div>
        <div class="field-hint" style="color: var(--warn);">
          The font file is embedded directly into the generated SVG/project as a tracing guide.
          Only use a font you actually hold a license for.
        </div>
      </div>

      <div class="section">
        <div class="section-title">2. Charset</div>
        <div class="field-row" style="margin-bottom: 6px;">
          <label><input type="radio" name="gtMode" value="single" checked> Single template</label>
          <select class="path-input" id="gtCharset" style="width: 160px; display:inline-block; margin-left: 10px;"></select>
          <label style="margin-left: 14px;">Chars/row <input type="number" class="path-input" id="gtCharsPerRow" style="width: 60px; margin-left: 6px;"></label>
        </div>
        <div class="field-row" style="margin-bottom: 6px;">
          <label><input type="radio" name="gtMode" value="split"> Split by Unicode block (recommended for large libraries)</label>
          <label style="margin-left: 14px;">Min glyphs/block <input type="number" class="path-input" id="gtMinChars" style="width: 60px; margin-left: 6px;"></label>
        </div>
        <div class="field-hint" style="margin-bottom: 8px;">
          Split writes one template per Unicode block the font actually covers, its own folder and
          SVG each, so a large or non-Latin font does not produce one unwieldy grid.
        </div>
        <div id="gtBlocksWrap" style="display:none;">
          <div id="gtBlocksList" style="max-height: 220px; overflow-y: auto; margin-bottom: 6px;"></div>
        </div>
        <div class="field-hint" id="gtBlocksStatus">Load a font to see which Unicode blocks it covers.</div>
      </div>

      <div class="section">
        <div class="section-title">3. Output</div>
        <div class="field-row">
          <div class="field-label">Prefix</div>
          <input type="text" class="path-input" id="gtPrefix" value="CUSTOM" style="max-width: 300px;">
        </div>
        <div class="field-row">
          <div class="field-label">Output folder</div>
          <div class="path-field">
            <input type="text" class="path-input" id="gtOutDir">
            <button type="button" class="btn" id="gtBrowseOutDir">Browse…</button>
          </div>
        </div>
        <ul class="field-hint field-hint-list">
          <li>A separate folder from Fontpacks Output Directory. These are blank tracing templates, not finished fontpacks.</li>
          <li>Single mode writes &lt;folder&gt;/&lt;prefix&gt;/.</li>
          <li>Split mode writes one &lt;folder&gt;/&lt;prefix&gt;/&lt;prefix&gt;-&lt;BLOCK&gt;/ per checked block.</li>
        </ul>
      </div>

      <div class="field-row" style="flex-direction: row; align-items: center; gap: 10px;">
        <button type="button" class="btn accent" id="gtGenerate">Generate</button>
        <span class="field-hint" id="gtStatus"></span>
      </div>
        </div>

        <div>
          <div class="section">
            <div class="section-title">Tracing Color</div>
            <div style="display:flex; align-items: center; gap: 10px; margin-bottom: 8px;">
              <div class="cp-swatch" id="gtColorSwatch" style="width: 36px; height: 24px; cursor: pointer;"></div>
              <input type="text" class="path-input" id="gtColorHex" style="width: 90px;">
              <input type="color" id="gtColorNative" style="display:none;">
            </div>
            <div class="field-hint" style="margin-bottom: 10px;">
              Fill color of the traced letterform in the generated SVG. Type a #rgb/#rrggbb hex code,
              or pick one below. Choose something that stands out while tracing over it in KFPS.
            </div>
            <div id="gtColorPicker"></div>
          </div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    let loadedFont = null; // {path, name, summary, covered, suggested_mode, suggested_prefix}
    let prefixEdited = false;
    let pendingGeneration = null;

    // -- charset / defaults -------------------------------------------------
    const charsetsResp = await api.call('glyph_template.get_charsets', {});
    let defaultMinChars = 4;
    if (charsetsResp.ok) {
      const { charsets, default_chars_per_row, default_trace_color, default_min_chars, default_output_dir } = charsetsResp.result;
      container.querySelector('#gtCharset').innerHTML = charsets.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
      container.querySelector('#gtCharsPerRow').value = default_chars_per_row;
      container.querySelector('#gtMinChars').value = default_min_chars;
      defaultMinChars = default_min_chars;
      container.querySelector('#gtColorHex').value = default_trace_color;
      container.querySelector('#gtColorSwatch').style.background = default_trace_color;
      // A separate default from Settings' Fontpacks Output Directory --
      // these are blank tracing templates, not finished fontpacks.
      container.querySelector('#gtOutDir').value = default_output_dir;
    }

    // -- tracing color --------------------------------------------------------
    // The full shared picker (saved/recent colors, HSB sliders, OS picker)
    // external-drives off the same #gtColorHex value the compact swatch and
    // the generate payload both already read from -- one source of truth,
    // not a second color state to keep in sync. colorPicker is declared
    // before setColor can be reached by any event so a click racing the
    // picker's own (awaited) setup never hits it uninitialized.
    let colorPicker = null;
    function setColor(hex) {
      container.querySelector('#gtColorHex').value = hex;
      container.querySelector('#gtColorSwatch').style.background = hex;
      if (colorPicker) colorPicker.sync();
    }
    container.querySelector('#gtColorSwatch').addEventListener('click', () => {
      container.querySelector('#gtColorNative').value = container.querySelector('#gtColorHex').value || '#e6e6e6';
      container.querySelector('#gtColorNative').click();
    });
    container.querySelector('#gtColorNative').addEventListener('change', (e) => setColor(e.target.value));
    container.querySelector('#gtColorHex').addEventListener('change', (e) => {
      if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(e.target.value.trim())) setColor(e.target.value.trim());
    });

    colorPicker = await window.ForzaColorPicker.create(container.querySelector('#gtColorPicker'), {
      title: '',
      getColor: () => {
        const hex = container.querySelector('#gtColorHex').value.trim();
        return [...(hexToRgb(hex) || [230, 230, 230]), 255];
      },
      onChange: (rgba) => setColor(rgbaToHex(rgba)),
    });

    // -- font loading -----------------------------------------------------
    function applyLoadedFont(font) {
      loadedFont = font;
      container.querySelector('#gtFontStatus').textContent = font.summary;
      if (!prefixEdited) container.querySelector('#gtPrefix').value = font.suggested_prefix;
      container.querySelector(`input[name="gtMode"][value="${font.suggested_mode}"]`).checked = true;
      updateModeVisibility();
      renderBlockChecklist();
    }

    window.ForzaFontSearch.create(container.querySelector('#gtFontSearch'), {
      placeholder: 'Search installed fonts…',
      onSelect: async (font) => {
        container.querySelector('#gtFontStatus').textContent = `Loading ${font.name}…`;
        const resp = await api.call('glyph_template.load_font_by_path', { path: font.path });
        if (!resp.ok) { container.querySelector('#gtFontStatus').textContent = resp.error; return; }
        applyLoadedFont(resp.result);
      },
    });
    container.querySelector('#gtBrowseFont').addEventListener('click', async () => {
      container.querySelector('#gtFontStatus').textContent = 'Loading font…';
      const resp = await api.call('glyph_template.browse_font', {});
      if (!resp.ok) { container.querySelector('#gtFontStatus').textContent = resp.error; return; }
      if (resp.result.cancelled) return;
      applyLoadedFont(resp.result);
    });

    container.querySelector('#gtPrefix').addEventListener('input', () => { prefixEdited = true; });

    // -- mode / block checklist --------------------------------------------
    function updateModeVisibility() {
      const mode = container.querySelector('input[name="gtMode"]:checked').value;
      container.querySelector('#gtBlocksWrap').style.display = mode === 'split' ? '' : 'none';
    }
    container.querySelectorAll('input[name="gtMode"]').forEach((r) => r.addEventListener('change', updateModeVisibility));

    function renderBlockChecklist() {
      const listEl = container.querySelector('#gtBlocksList');
      const statusEl = container.querySelector('#gtBlocksStatus');
      if (!loadedFont) {
        statusEl.textContent = 'Load a font to see which Unicode blocks it covers.';
        listEl.innerHTML = '';
        return;
      }
      const minChars = Math.max(1, Number(container.querySelector('#gtMinChars').value || defaultMinChars));
      const eligible = loadedFont.covered.filter((b) => b.chars.length >= minChars);
      if (eligible.length === 0) {
        statusEl.textContent = `No block reaches ${minChars} glyph(s) at this threshold. Lower "Min glyphs/block".`;
        listEl.innerHTML = '';
        return;
      }
      listEl.innerHTML = eligible.map((b) => `
        <div class="checkbox-row">
          <input type="checkbox" checked data-block="${esc(b.name)}" id="gtBlock_${esc(b.name)}">
          <label for="gtBlock_${esc(b.name)}">${esc(b.name)} (${b.chars.length})</label>
        </div>
      `).join('');
      statusEl.textContent =
        `${eligible.length} of ${loadedFont.total_known_blocks} known block(s) covered at this threshold. ` +
        'Uncheck any you do not want a template for.';
    }
    container.querySelector('#gtMinChars').addEventListener('input', renderBlockChecklist);

    container.querySelector('#gtBrowseOutDir').addEventListener('click', async () => {
      const resp = await api.call('glyph_template.pick_output_dir', { initial: container.querySelector('#gtOutDir').value });
      if (resp.ok && !resp.result.cancelled) container.querySelector('#gtOutDir').value = resp.result.path;
    });

    // -- generate -----------------------------------------------------------
    container.querySelector('#gtGenerate').addEventListener('click', async () => {
      const statusEl = container.querySelector('#gtStatus');
      if (!loadedFont) { statusEl.textContent = 'Select a font first.'; return; }
      const textColor = container.querySelector('#gtColorHex').value.trim();
      if (!/^#([0-9a-f]{3}|[0-9a-f]{6})$/i.test(textColor)) {
        statusEl.textContent = `${textColor} is not a valid #rgb or #rrggbb hex color.`;
        return;
      }
      const mode = container.querySelector('input[name="gtMode"]:checked').value;
      const payload = {
        font_path: loadedFont.path,
        text_color: textColor,
        prefix: container.querySelector('#gtPrefix').value,
        out_dir: container.querySelector('#gtOutDir').value,
        mode,
        chars_per_row: container.querySelector('#gtCharsPerRow').value,
      };
      if (mode === 'split') {
        payload.min_chars = container.querySelector('#gtMinChars').value;
        payload.only_blocks = Array.from(container.querySelectorAll('#gtBlocksList input:checked')).map((el) => el.dataset.block);
        if (payload.only_blocks.length === 0) { statusEl.textContent = 'Check at least one Unicode block to generate.'; return; }
      } else {
        payload.charset = container.querySelector('#gtCharset').value;
      }

      container.querySelector('#gtGenerate').disabled = true;
      statusEl.textContent = 'Generating…';
      const resp = await api.call('glyph_template.generate', payload);
      if (!resp.ok) {
        statusEl.textContent = resp.error;
        container.querySelector('#gtGenerate').disabled = false;
        return;
      }
      pendingGeneration = resp.result.generation;
    });

    const offLog = window.__forzaEvents.on('glyph_template_log', (generation, payload) => {
      if (generation !== pendingGeneration) return;
      container.querySelector('#gtStatus').textContent = payload.line;
    });
    const offDone = window.__forzaEvents.on('glyph_template_done', (generation, payload) => {
      if (generation !== pendingGeneration) return;
      container.querySelector('#gtStatus').textContent = payload.message;
      container.querySelector('#gtGenerate').disabled = false;
    });

    return () => { offLog(); offDone(); colorPicker.destroy(); };
  }

  window.ForzaTabs.glyph_template = mount;
})();
