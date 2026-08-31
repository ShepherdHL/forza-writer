// Forza Font Text tab: lay out text with one of FH6's 11 native in-game
// vinyl fonts. First tab to use the shared color-picker component.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">Forza Font Text</h2>
      <div class="intro-text">
        Type text and lay it out with one of FH6's 11 built-in native fonts. Every glyph is the
        game's own letter mesh, not a fitted or traced substitute. Output drops straight into
        KFPS as finished, editable shapes.
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 340px;">
        <div>
          <div class="section">
            <div class="section-title">1. Text</div>
            <textarea id="fftText" rows="6" style="width:100%; background:var(--entry-bg); color:var(--fg); border:1px solid var(--border); border-radius:4px; padding:8px; font-family:var(--body-font); font-size:13px;"></textarea>
          </div>

          <div class="section">
            <div class="section-title">2. Font &amp; Layout</div>
            <div class="field-hint" style="margin-bottom: 10px;">
              All 11 fonts support the exact same characters. Switching fonts changes letterform style
              only. It never adds character support.
            </div>
            <div style="display:flex; gap: 20px; flex-wrap: wrap; align-items: center;">
              <label class="field-label">Forza Font
                <select id="fftFont" class="path-input" style="margin-left: 8px; min-width: 320px;"></select>
              </label>
              <label class="field-label">Height
                <input type="number" id="fftHeight" class="path-input" value="360" min="10" max="5000" step="10" style="width: 90px; margin-left: 8px;">
              </label>
            </div>
          </div>

          <div class="field-row" style="flex-direction: row; align-items: center; gap: 10px;">
            <button type="button" class="btn accent" id="fftPreview">Preview</button>
            <button type="button" class="btn" id="fftSaveJson" disabled>Save .json…</button>
            <button type="button" class="btn" id="fftSaveProject" disabled>Save .fabric-project.json…</button>
            <span class="field-hint" id="fftStatus">Type some text and click Preview.</span>
          </div>

          <div class="section">
            <div class="section-title">Preview</div>
            <div class="field-hint" style="margin-bottom: 10px;">
              Layout preview only. It shows line breaks and character coverage, not the exact native
              vinyl letterforms. Orange text marks a character with no native shape. It will not place.
            </div>
            <div class="gi-diff-panel" style="aspect-ratio: auto; height: 280px; width: 280px;" id="fftPreviewPanel">
              <div class="gi-diff-empty">Click Preview to see a layout.</div>
            </div>
          </div>
        </div>

        <div>
          <div class="section">
            <div class="section-title">Color</div>
            <div id="fftColorPicker"></div>
          </div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    let lastResult = null;
    let lastSignature = null;
    let color = [255, 255, 255, 255];

    function currentSignature() {
      return JSON.stringify([
        container.querySelector('#fftText').value,
        container.querySelector('#fftFont').value,
        container.querySelector('#fftHeight').value,
        color,
      ]);
    }

    function refreshSaveButtons() {
      const fresh = lastSignature !== null && lastSignature === currentSignature();
      container.querySelector('#fftSaveJson').disabled = !(fresh && lastResult && lastResult.shapes.length);
      container.querySelector('#fftSaveProject').disabled = !(fresh && lastResult && lastResult.shapes.length);
      if (!fresh && lastSignature !== null) {
        container.querySelector('#fftStatus').textContent =
          'Settings changed since the last preview. Click Preview again before saving.';
      }
    }
    ['input', 'change'].forEach((evt) => {
      container.querySelector('#fftText').addEventListener(evt, refreshSaveButtons);
      container.querySelector('#fftFont').addEventListener(evt, refreshSaveButtons);
      container.querySelector('#fftHeight').addEventListener(evt, refreshSaveButtons);
    });

    api.call('forza_font_text.get_fonts', {}).then((resp) => {
      if (!resp.ok) return;
      const sel = container.querySelector('#fftFont');
      sel.innerHTML = resp.result.fonts.map((f) => `<option value="${f.value}">${f.label}</option>`).join('');
    });

    const colorPickerPromise = window.ForzaColorPicker.create(container.querySelector('#fftColorPicker'), {
      settingsKey: 'color_forza_font_text',
      title: '',
      onChange: (rgba) => { color = rgba; refreshSaveButtons(); },
    });

    container.querySelector('#fftPreview').addEventListener('click', async () => {
      const text = container.querySelector('#fftText').value;
      if (!text.trim()) {
        container.querySelector('#fftStatus').textContent = 'Type some text first.';
        return;
      }
      const font = Number(container.querySelector('#fftFont').value || 1);
      const height = Number(container.querySelector('#fftHeight').value || 360);
      const statusEl = container.querySelector('#fftStatus');
      statusEl.textContent = 'Rendering…';
      const resp = await api.call('forza_font_text.preview', { text, font, height, color });
      if (!resp.ok) { statusEl.textContent = resp.error; return; }
      lastResult = resp.result;
      lastSignature = currentSignature();

      container.querySelector('#fftPreviewPanel').innerHTML =
        `<img src="${resp.result.preview_image}" alt="Forza Font Text layout preview" style="width:100%;height:100%;object-fit:contain;">`;
      statusEl.textContent =
        `${resp.result.placed_count} of ${resp.result.total_chars} character(s) placed. ` +
        `${resp.result.unsupported.length} distinct unsupported character(s).`;
      refreshSaveButtons();
    });

    container.querySelector('#fftSaveJson').addEventListener('click', async () => {
      if (!lastResult) return;
      const resp = await api.call('forza_font_text.save_json', { payload: lastResult.payload });
      if (!resp.ok) { container.querySelector('#fftStatus').textContent = resp.error; return; }
      if (resp.result.cancelled) return;
      container.querySelector('#fftStatus').textContent =
        `Saved ${lastResult.shapes.length} shape(s) to ${resp.result.path.split('\\').pop()}.`;
    });

    container.querySelector('#fftSaveProject').addEventListener('click', async () => {
      if (!lastResult) return;
      const resp = await api.call('forza_font_text.save_project', {
        shapes: lastResult.shapes, chars: lastResult.chars,
      });
      if (!resp.ok) { container.querySelector('#fftStatus').textContent = resp.error; return; }
      if (resp.result.cancelled) return;
      container.querySelector('#fftStatus').textContent =
        `Saved ${lastResult.shapes.length} shape(s) to ${resp.result.path.split('\\').pop()}, ${resp.result.groups} group(s).`;
    });

    return async () => { (await colorPickerPromise).destroy(); };
  }

  window.ForzaTabs.forza_font_text = mount;
})();
