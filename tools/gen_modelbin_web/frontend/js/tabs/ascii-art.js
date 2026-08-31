// ASCII Art tab: place pasted ASCII art on a fixed grid using one of FH6's
// 11 native in-game vinyl fonts. Second consumer of the shared color-picker
// component.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  const MAX_REMAP_ROWS = 40;
  // A native vinyl glyph's own design square, in Forza editor units.
  // Ported from KFPS editor.js. See forza_writer/layout.py's
  // PIXEL_ART_SQUARE_SIZE, which this mirrors. layout_ascii_grid scales a
  // glyph to `cell_height * 0.82 / PIXEL_ART_SQUARE_SIZE`. This is the same
  // 0.82 breathing-room ratio layout_forza_text uses for free-flowing text.
  // cell_height == PIXEL_ART_SQUARE_SIZE puts a glyph at its own natural
  // 1:1 size. cell_width == cell_height * 0.82 tiles it edge to edge with
  // no extra gap.
  const PIXEL_ART_SQUARE_SIZE = 128.498032;
  const TIGHT_CELL_HEIGHT = PIXEL_ART_SQUARE_SIZE;
  const TIGHT_CELL_WIDTH = PIXEL_ART_SQUARE_SIZE * 0.82;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">ASCII Art</h2>
      <div class="intro-text">
        Paste existing ASCII art and place it, character-for-character, using one of the 11
        native in-game vinyl fonts. Every cell advances the same fixed width/height regardless of
        its glyph, so columns stay aligned the way they were pasted.
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 340px;">
        <div>
          <div class="section">
            <div class="section-title">1. Paste ASCII Art</div>
            <textarea id="aaText" rows="12" spellcheck="false" style="width:100%; background:var(--entry-bg); color:var(--fg); border:1px solid var(--border); border-radius:4px; padding:8px; font-family:var(--mono); font-size:12px; white-space:pre;"></textarea>
            <div class="field-hint" style="margin-top: 6px;">Ragged lines are padded to a rectangle automatically. Tabs expand to 4 spaces.</div>
          </div>

          <div class="section">
            <div class="section-title">2. Grid Settings</div>
            <div style="display:flex; gap: 14px; flex-wrap: wrap; align-items: center; margin-bottom: 8px;">
              <label class="field-label">Font (1-11) <input type="number" id="aaFont" class="path-input" value="1" min="1" max="11" style="width: 60px; margin-left: 6px;"></label>
              <label class="field-label">Cell width <input type="number" id="aaCellW" class="path-input" value="18" style="width: 70px; margin-left: 6px;"></label>
              <label class="field-label">Cell height <input type="number" id="aaCellH" class="path-input" value="25" style="width: 70px; margin-left: 6px;"></label>
            </div>
            <div style="display:flex; gap: 8px; margin-bottom: 8px;">
              <button type="button" class="btn" id="aaPresetTight">Compact (1:1)</button>
              <button type="button" class="btn" id="aaPresetSpaced">Spaced (Default)</button>
            </div>
            <ul class="field-hint field-hint-list">
              <li>Cell size is in Forza editor units. It stays fixed for every cell no matter what is in it.</li>
              <li><b>Compact (1:1)</b> sizes cells to a native glyph's own design square. Glyphs tile edge to edge at their real in-game proportions. This is the closest match to how the pasted art actually looks.</li>
              <li><b>Spaced</b> is this tool's original wider default. It leaves visible gaps between glyphs.</li>
              <li>All 11 fonts support the exact same characters. Only the letterform style differs.</li>
              <li>Remapping below fixes an unsupported character. Switching fonts does not.</li>
            </ul>
          </div>

          <div class="section">
            <div class="section-title">3. Unsupported Characters</div>
            <div class="field-hint" style="margin-bottom: 8px;">Characters the selected font can't place. Leave blank to skip a cell, or type a replacement character. Nothing is substituted automatically.</div>
            <div id="aaRemapRows"></div>
            <div class="field-hint" id="aaRemapStatus" style="margin-top: 6px;">Click "Preview" to scan for unsupported characters.</div>
            <div class="checkbox-row">
              <input type="checkbox" id="aaPlaceholder">
              <label for="aaPlaceholder">Experiment: fill unsupported cells with a placeholder square</label>
            </div>
          </div>

          <div class="field-row" style="flex-direction: row; align-items: center; gap: 10px;">
            <button type="button" class="btn accent" id="aaPreview">Preview</button>
            <button type="button" class="btn" id="aaSave" disabled>Save .json…</button>
          </div>
          <div class="field-hint" id="aaStatus">Paste some ASCII art and click Preview.</div>

          <div class="section">
            <div class="section-title">Preview</div>
            <ul class="field-hint field-hint-list" style="margin-bottom: 10px;">
              <li>Layout preview only. Shows grid alignment and character coverage, not exact native vinyl letterforms.</li>
              <li>Orange text marks a cell whose character has no native shape.</li>
            </ul>
            <div class="gi-diff-panel" style="aspect-ratio: auto; height: 420px;" id="aaPreviewPanel">
              <div class="gi-diff-empty">Click Preview to see a layout.</div>
            </div>
          </div>
        </div>

        <div>
          <div class="section">
            <div class="section-title">Color</div>
            <div id="aaColorPicker"></div>
          </div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    let lastResult = null;
    let lastSignature = null;
    let color = [255, 255, 255, 255];
    let remapVars = {}; // char -> current input value

    function remapPayload() {
      const placeholder = container.querySelector('#aaPlaceholder').checked;
      const remap = {};
      Object.entries(remapVars).forEach(([char, value]) => {
        if (value) remap[char] = value[0];
        else if (!placeholder) remap[char] = null;
      });
      return remap;
    }

    function currentSignature() {
      return JSON.stringify([
        container.querySelector('#aaText').value,
        container.querySelector('#aaFont').value,
        container.querySelector('#aaCellW').value,
        container.querySelector('#aaCellH').value,
        color,
        Object.entries(remapVars).sort(),
        container.querySelector('#aaPlaceholder').checked,
      ]);
    }

    function refreshSaveButton() {
      const fresh = lastSignature !== null && lastSignature === currentSignature();
      container.querySelector('#aaSave').disabled = !(fresh && lastResult && lastResult.shapes.length);
      if (!fresh && lastSignature !== null) {
        container.querySelector('#aaStatus').textContent =
          'Settings changed since the last preview. Click Preview again before saving.';
      }
    }
    ['input', 'change'].forEach((evt) => {
      ['#aaText', '#aaFont', '#aaCellW', '#aaCellH', '#aaPlaceholder'].forEach((sel) => {
        container.querySelector(sel).addEventListener(evt, refreshSaveButton);
      });
    });

    function applyPreset(width, height) {
      container.querySelector('#aaCellW').value = Math.round(width * 100) / 100;
      container.querySelector('#aaCellH').value = Math.round(height * 100) / 100;
      refreshSaveButton();
    }
    container.querySelector('#aaPresetTight').addEventListener('click', () => applyPreset(TIGHT_CELL_WIDTH, TIGHT_CELL_HEIGHT));
    container.querySelector('#aaPresetSpaced').addEventListener('click', () => applyPreset(18, 25));

    function rebuildRemapUi(unsupported) {
      const rowsEl = container.querySelector('#aaRemapRows');
      const statusEl = container.querySelector('#aaRemapStatus');
      const kept = {};
      if (!unsupported.length) {
        remapVars = {};
        rowsEl.innerHTML = '';
        statusEl.textContent = 'No unsupported characters found. Every glyph will place.';
        return;
      }
      const shown = unsupported.slice(0, MAX_REMAP_ROWS);
      rowsEl.innerHTML = shown.map((u) => {
        const display = u.char.trim() ? u.char : JSON.stringify(u.char);
        const value = remapVars[u.char] || '';
        return `<div style="display:flex; align-items:center; gap:8px; padding: 2px 0;">
          <span style="min-width: 90px; font-family: var(--mono); font-size: 11px;">${esc(display)} x${u.count}:</span>
          <input type="text" class="path-input aa-remap-input" data-char="${esc(u.char)}" maxlength="1" style="width: 44px;" value="${esc(value)}">
          <span class="field-hint">(blank if empty)</span>
        </div>`;
      }).join('');
      rowsEl.querySelectorAll('.aa-remap-input').forEach((input) => {
        kept[input.dataset.char] = input.value;
        input.addEventListener('input', () => {
          remapVars[input.dataset.char] = input.value;
          refreshSaveButton();
        });
      });
      remapVars = kept;
      const truncatedNote = unsupported.length > MAX_REMAP_ROWS ? ` (${unsupported.length - MAX_REMAP_ROWS} more not shown)` : '';
      statusEl.textContent = `${unsupported.length} distinct unsupported character(s) found${truncatedNote}. Type a replacement above, then click Preview again.`;
    }

    const colorPickerPromise = window.ForzaColorPicker.create(container.querySelector('#aaColorPicker'), {
      settingsKey: 'color_ascii_art',
      title: '',
      onChange: (rgba) => { color = rgba; refreshSaveButton(); },
    });

    container.querySelector('#aaPreview').addEventListener('click', async () => {
      const statusEl = container.querySelector('#aaStatus');
      statusEl.textContent = 'Rendering…';
      const resp = await api.call('ascii_art.preview', {
        text: container.querySelector('#aaText').value,
        font: Number(container.querySelector('#aaFont').value || 1),
        cell_width: Number(container.querySelector('#aaCellW').value || 18),
        cell_height: Number(container.querySelector('#aaCellH').value || 25),
        color,
        remap: remapPayload(),
        placeholder: container.querySelector('#aaPlaceholder').checked,
      });
      if (!resp.ok) { statusEl.textContent = resp.error; return; }
      lastResult = resp.result;
      rebuildRemapUi(resp.result.unsupported);
      lastSignature = currentSignature();

      container.querySelector('#aaPreviewPanel').innerHTML =
        `<img src="${resp.result.preview_image}" alt="ASCII Art layout preview" style="width:100%;height:100%;object-fit:contain;">`;
      statusEl.textContent =
        `${resp.result.rows} row(s) x ${resp.result.cols} col(s): ${resp.result.placed_count} glyph(s) placed, ` +
        `${resp.result.blank_cells} cell(s) blank (${resp.result.unsupported.length} distinct unsupported character(s)).`;
      refreshSaveButton();
    });

    container.querySelector('#aaSave').addEventListener('click', async () => {
      if (!lastResult) return;
      const resp = await api.call('ascii_art.save_json', { payload: lastResult.payload });
      if (!resp.ok) { container.querySelector('#aaStatus').textContent = resp.error; return; }
      if (resp.result.cancelled) return;
      container.querySelector('#aaStatus').textContent =
        `Saved ${lastResult.shapes.length} shape(s) to ${resp.result.path.split('\\').pop()}.`;
    });

    return async () => { (await colorPickerPromise).destroy(); };
  }

  window.ForzaTabs.ascii_art = mount;
})();
