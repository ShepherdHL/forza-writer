// Direct Generator tab: generate one complete .json design straight from
// text or an image, with no fontpack step.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  const METHODS = [
    { key: 'modern', title: 'Shape Fitting (.json)',
      desc: "Analyzes each distinct glyph and approximates it using Forza's full primitive-shape library, with quality checks and exact rectangular fallback. Reuses repeated characters and the font's real metrics. This page does not use masks." },
    { key: 'legacy', title: 'Pixel Tracing (.json)',
      desc: 'Rasterizes the complete text run first, preserving its kerning and shaping, then combines filled pixels into rectangular vinyl layers. Usually much more expensive in layer count. CPU only.' },
    { key: 'image', title: 'Image to Text (.json)',
      desc: 'Lifts lettering, logos, or a signature directly from a cropped image. No font or typed text is required. The result is an exact monochrome rectangle trace.' },
  ];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  async function mount(container, opts) {
    container.innerHTML = `
      <h2 class="page-heading">Direct Generator</h2>
      <div class="intro-text">
        Type the exact text you need and generate one complete .json design. This is a minimal
        troubleshooting path. It does not build or read a fontpack.
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 340px;">
        <div>
          <div class="section">
            <div class="section-title">1. Font</div>
            <div class="path-field" style="margin-bottom: 8px;">
              <input type="text" class="path-input" id="dgFont" placeholder="Font path">
              <button type="button" class="btn" id="dgBrowseFont">Browse…</button>
            </div>
            <div class="field-label">Lettering image (Image to Text only)</div>
            <div class="path-field">
              <input type="text" class="path-input" id="dgImage" placeholder="Image path">
              <button type="button" class="btn" id="dgBrowseImage">Browse…</button>
            </div>
          </div>

          <div class="section">
            <div class="section-title">2. Exact Text</div>
            <textarea id="dgText" rows="5" style="width:100%; background:var(--entry-bg); color:var(--fg); border:1px solid var(--border); border-radius:4px; padding:8px; font-family:var(--body-font); font-size:13px; margin-bottom: 8px;"></textarea>
            <div class="field-hint">
              Repeated characters stay repeated. Shape Fitting analyzes each distinct glyph once and
              reuses it. Pixel Tracing rasterizes the complete rendered text run.
            </div>
          </div>

          <div class="section">
            <div class="section-title">3. Generation Method</div>
            <div id="dgMethodCards" style="display:flex; flex-direction:column; gap:8px; margin-bottom: 10px;"></div>
            <div style="display:flex; gap: 16px; flex-wrap: wrap; align-items: center; margin-bottom: 8px;">
              <label class="field-label" id="dgSegmentsLabel">Curve Smoothness <input type="number" class="path-input" id="dgSegments" value="8" style="width:60px; margin-left:6px;"></label>
              <span class="radio-group" id="dgAlignGroup">
                <span class="field-label">Align</span>
                <label><input type="radio" name="dgAlign" value="left" checked> Left</label>
                <label><input type="radio" name="dgAlign" value="center"> Center</label>
                <label><input type="radio" name="dgAlign" value="right"> Right</label>
              </span>
              <label class="field-label" id="dgCellSizeLabel" style="display:none;">Pixel trace cell size <input type="number" class="path-input" id="dgCellSize" value="1" style="width:60px; margin-left:6px;"></label>
            </div>
            <div id="dgImageOptions" style="display:none; gap: 16px; flex-wrap: wrap; align-items: center;">
              <span class="radio-group">
                <span class="field-label">Image foreground</span>
                <label><input type="radio" name="dgPolarity" value="auto" checked> Auto</label>
                <label><input type="radio" name="dgPolarity" value="light"> Light/white</label>
                <label><input type="radio" name="dgPolarity" value="dark"> Dark/black</label>
                <label><input type="radio" name="dgPolarity" value="alpha"> Transparency</label>
              </span>
              <label class="field-label">Threshold <input type="text" class="path-input" id="dgThreshold" value="auto" style="width:60px; margin-left:6px;"></label>
            </div>
          </div>

          <div class="field-row" style="flex-direction: row; align-items: center; gap: 10px;">
            <button type="button" class="btn accent" id="dgGenerate">Generate Preview</button>
            <button type="button" class="btn" id="dgSave" disabled>Save…</button>
            <span class="field-hint" id="dgStatus">Choose a font, enter text, and select a generation method.</span>
          </div>

          <div class="section">
            <div class="section-title">Preview</div>
            <div class="gi-diff-panel" style="aspect-ratio: auto; height: 200px;" id="dgPreviewPanel">
              <div class="gi-diff-empty"></div>
            </div>
          </div>
        </div>

        <div>
          <div class="section">
            <div class="section-title">Color</div>
            <div id="dgColorPicker"></div>
          </div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    let method = 'modern';
    let lastSignature = null;
    let color = [255, 255, 255, 255];

    function renderMethodCards() {
      const wrap = container.querySelector('#dgMethodCards');
      wrap.innerHTML = METHODS.map((m) => `
        <div class="section method-card ${method === m.key ? 'active' : ''}" data-key="${m.key}"
             style="margin-bottom:0; cursor:pointer; padding: 10px 14px; ${method === m.key ? 'border-color: var(--accent);' : ''}">
          <div style="font-family: var(--display); font-weight: 600; font-size: 12px; ${method === m.key ? 'color: var(--accent);' : ''}">${esc(m.title)}</div>
          <div class="field-hint" style="margin-top: 4px;">${esc(m.desc)}</div>
        </div>
      `).join('');
      wrap.querySelectorAll('.method-card').forEach((card) => {
        card.addEventListener('click', () => {
          method = card.dataset.key;
          renderMethodCards();
          updateMethodVisibility();
        });
      });
    }
    function updateMethodVisibility() {
      const isImage = method === 'image';
      container.querySelector('#dgSegmentsLabel').style.display = method === 'modern' ? '' : 'none';
      container.querySelector('#dgAlignGroup').style.display = method === 'modern' ? '' : 'none';
      container.querySelector('#dgCellSizeLabel').style.display = method !== 'modern' ? '' : 'none';
      container.querySelector('#dgImageOptions').style.display = isImage ? 'flex' : 'none';
    }
    renderMethodCards();
    updateMethodVisibility();

    container.querySelector('#dgBrowseFont').addEventListener('click', async () => {
      const resp = await api.call('direct.browse_font', {});
      if (resp.ok && !resp.result.cancelled) container.querySelector('#dgFont').value = resp.result.path;
    });
    container.querySelector('#dgBrowseImage').addEventListener('click', async () => {
      const resp = await api.call('direct.browse_image', {});
      if (resp.ok && !resp.result.cancelled) container.querySelector('#dgImage').value = resp.result.path;
    });

    const colorPicker = await window.ForzaColorPicker.create(container.querySelector('#dgColorPicker'), {
      settingsKey: 'color_direct',
      title: '',
      onChange: (rgba) => { color = rgba; },
    });

    function currentSignature() {
      return JSON.stringify([
        container.querySelector('#dgFont').value,
        container.querySelector('#dgImage').value,
        container.querySelector('#dgText').value,
        method,
        container.querySelector('#dgSegments').value,
        container.querySelector('input[name="dgAlign"]:checked')?.value,
        container.querySelector('#dgCellSize').value,
        container.querySelector('input[name="dgPolarity"]:checked')?.value,
        container.querySelector('#dgThreshold').value,
        color,
      ]);
    }

    container.querySelector('#dgGenerate').addEventListener('click', async () => {
      const statusEl = container.querySelector('#dgStatus');
      statusEl.textContent = method === 'modern' ? 'Fitting and quality-checking distinct glyphs…'
        : method === 'legacy' ? 'Tracing the complete text run on CPU…'
        : 'Extracting and tracing lettering from the image…';
      container.querySelector('#dgSave').disabled = true;
      const payload = {
        method,
        font_path: container.querySelector('#dgFont').value,
        image_path: container.querySelector('#dgImage').value,
        text: container.querySelector('#dgText').value,
        segments: container.querySelector('#dgSegments').value,
        align: container.querySelector('input[name="dgAlign"]:checked')?.value || 'left',
        cell_size: container.querySelector('#dgCellSize').value,
        polarity: container.querySelector('input[name="dgPolarity"]:checked')?.value || 'auto',
        threshold: container.querySelector('#dgThreshold').value,
        color,
      };
      const resp = await api.call('direct.generate', payload);
      if (!resp.ok) { statusEl.textContent = resp.error; return; }
      lastSignature = currentSignature();
      container.querySelector('#dgPreviewPanel').innerHTML =
        `<img src="${resp.result.preview_image}" alt="Direct generation preview" style="width:100%;height:100%;object-fit:contain;">`;
      statusEl.textContent = resp.result.status;
      container.querySelector('#dgSave').disabled = resp.result.shape_count === 0;
    });

    container.querySelector('#dgSave').addEventListener('click', async () => {
      const statusEl = container.querySelector('#dgStatus');
      if (lastSignature !== currentSignature()) {
        container.querySelector('#dgSave').disabled = true;
        statusEl.textContent = 'The font, text, or generation settings changed. Generate a new preview before saving.';
        return;
      }
      const resp = await api.call('direct.save', {});
      if (!resp.ok) { statusEl.textContent = resp.error; return; }
      if (resp.result.cancelled) return;
      let text = `Saved ${resp.result.shape_count} shape(s) to ${resp.result.path.split('\\').pop()}.`;
      if (resp.result.debug_error) text += ` Could not write debug output: ${resp.result.debug_error}`;
      if (resp.result.accuracy_text) text += ` Trace accuracy: ${resp.result.accuracy_text}.`;
      statusEl.textContent = text;
    });

    // Generator's "Send selected font to Direct Generator" -- transfers
    // the font without touching whatever text/options are already here.
    if (opts && opts.fontPath) container.querySelector('#dgFont').value = opts.fontPath;

    return () => { colorPicker.destroy(); };
  }

  window.ForzaTabs.direct = mount;
})();
