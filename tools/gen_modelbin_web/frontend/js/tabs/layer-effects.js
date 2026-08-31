// Layer Effects tab: build a Layered Glyph Effect (inset/outset/translate/
// scale/rotate/boolean layers derived from one source glyph) and preview
// it against sample text. Mirrors tools/gen_modelbin_gui/tabs/layer_effects.py.
//
// The whole LayerStack lives here as a plain JS object -- add/duplicate/
// delete/reorder/edit all happen client-side, since EffectLayer/LayerStack
// round-trip to JSON losslessly. Three update tiers match the Tkinter tab:
//   - regenerate(): full backend re-run, for anything that changes geometry.
//   - refreshCosmetic(): re-tints the backend's cached shapes, for color/
//     opacity/name edits (keeps the opacity slider smooth while dragging).
//   - refreshPreviewOnly(): re-renders the backend's cached shapes with a
//     different enabled-layer filter or compare-to-source mode.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  const OPERATIONS = [
    'original', 'inset', 'outset', 'translate', 'scale', 'rotate',
    'boolean_union', 'boolean_difference', 'boolean_intersection',
  ];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function newLayerId() {
    return Math.random().toString(16).slice(2, 10);
  }

  async function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">Layer Effects</h2>
      <div class="intro-text">
        Derive multiple independently colored/transformed geometric layers from a source glyph
        (inset rings, outset borders, offset shadows, boolean combinations) and run each through
        the same primitive generator every other tab uses.
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 340px;">
        <div>
          <div class="section">
            <div class="section-title">1. Font &amp; Sample Text</div>
            <div class="path-field" style="margin-bottom: 8px;">
              <input type="text" class="path-input" id="leFont" placeholder="Font path">
              <button type="button" class="btn" id="leBrowseFont">Browse…</button>
            </div>
            <div class="path-field">
              <span class="field-label">Sample text</span>
              <input type="text" class="path-input" id="leSample" value="Ag" style="max-width: 120px;">
            </div>
            <div class="field-hint" id="leFontStatus" style="margin-top: 8px;">Select a font to preview a Layered Glyph Effect.</div>
          </div>

          <div class="section">
            <div class="section-title">2. Preset</div>
            <div class="path-field" style="margin-bottom: 8px;">
              <select class="path-input" id="lePresetSelect"></select>
              <button type="button" class="btn" id="leApplyPreset">Apply preset</button>
            </div>
            <div class="path-field">
              <select class="path-input" id="leSavedSelect"></select>
              <button type="button" class="btn" id="leLoadSaved">Load</button>
              <button type="button" class="btn" id="leSaveAs">Save current as…</button>
              <button type="button" class="btn danger" id="leDeleteSaved">Delete</button>
            </div>
          </div>

          <div class="section">
            <div class="section-title">3. Layers</div>
            <div class="le-layer-list" id="leLayerRows"></div>
            <div style="display:flex; gap: 6px;">
              <button type="button" class="btn" id="leAdd">+ Add</button>
              <button type="button" class="btn" id="leDuplicate">Duplicate</button>
              <button type="button" class="btn danger" id="leDelete">Delete</button>
              <button type="button" class="btn" id="leMoveUp">▲</button>
              <button type="button" class="btn" id="leMoveDown">▼</button>
            </div>
          </div>

          <div class="section">
            <div class="section-title">4. Layer Properties</div>
            <div class="le-props-grid">
              <span class="field-label">Name</span>
              <input type="text" class="path-input" id="leName">
              <span class="field-label">Enabled</span>
              <span class="checkbox-row" style="margin: 0;"><input type="checkbox" id="leEnabled"></span>
              <span class="field-label">Operation</span>
              <select class="path-input" id="leOperation"></select>
              <span class="field-label">Source</span>
              <select class="path-input" id="leSource"></select>
              <span class="field-label">Amount (inset/outset)</span>
              <input type="number" class="path-input" id="leAmount" style="max-width: 100px;">
              <span class="field-label">Offset X</span>
              <input type="number" class="path-input" id="leOffsetX" style="max-width: 100px;">
              <span class="field-label">Offset Y</span>
              <input type="number" class="path-input" id="leOffsetY" style="max-width: 100px;">
              <span class="field-label">Scale X</span>
              <input type="number" class="path-input" id="leScaleX" step="0.1" style="max-width: 100px;">
              <span class="field-label">Scale Y</span>
              <input type="number" class="path-input" id="leScaleY" step="0.1" style="max-width: 100px;">
              <span class="field-label">Rotation (deg)</span>
              <input type="number" class="path-input" id="leRotation" style="max-width: 100px;">
              <span class="field-label">Boolean operand</span>
              <select class="path-input" id="leBooleanOperand"></select>
              <span class="field-label">Opacity</span>
              <input type="range" id="leOpacity" min="0" max="1" step="0.01">
            </div>
          </div>

          <div class="section">
            <div class="section-title">Preview</div>
            <div class="gi-diff-panel" style="aspect-ratio: auto; height: 260px;" id="lePreviewPanel">
              <div class="gi-diff-empty"></div>
            </div>
            <div class="checkbox-row">
              <input type="checkbox" id="leCompare">
              <label for="leCompare">Compare to source (plain, non-layered glyph)</label>
            </div>
            <div class="field-hint" id="leVinylCount">Estimated vinyls: —</div>
            <div class="field-hint" id="leStatus">Load a font to begin.</div>
          </div>
        </div>

        <div>
          <div class="section">
            <div class="section-title">Layer Color</div>
            <div id="leColorPicker"></div>
          </div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    let fontPath = '';
    let stack = { name: 'Concentric Inline', layers: [] };
    let selectedLayerId = null;
    let layerStatuses = {};

    const els = {
      font: container.querySelector('#leFont'),
      fontStatus: container.querySelector('#leFontStatus'),
      sample: container.querySelector('#leSample'),
      presetSelect: container.querySelector('#lePresetSelect'),
      savedSelect: container.querySelector('#leSavedSelect'),
      rows: container.querySelector('#leLayerRows'),
      name: container.querySelector('#leName'),
      enabled: container.querySelector('#leEnabled'),
      operation: container.querySelector('#leOperation'),
      source: container.querySelector('#leSource'),
      amount: container.querySelector('#leAmount'),
      offsetX: container.querySelector('#leOffsetX'),
      offsetY: container.querySelector('#leOffsetY'),
      scaleX: container.querySelector('#leScaleX'),
      scaleY: container.querySelector('#leScaleY'),
      rotation: container.querySelector('#leRotation'),
      booleanOperand: container.querySelector('#leBooleanOperand'),
      opacity: container.querySelector('#leOpacity'),
      previewPanel: container.querySelector('#lePreviewPanel'),
      compare: container.querySelector('#leCompare'),
      vinylCount: container.querySelector('#leVinylCount'),
      status: container.querySelector('#leStatus'),
    };

    els.operation.innerHTML = OPERATIONS.map((op) => `<option value="${op}">${op}</option>`).join('');

    function selectedLayer() {
      return stack.layers.find((l) => l.id === selectedLayerId) || null;
    }

    function applyPreviewResult(result) {
      els.previewPanel.innerHTML =
        `<img src="${result.preview_image}" alt="Layer effects preview" style="width:100%;height:100%;object-fit:contain;">`;
      els.vinylCount.textContent = `Estimated vinyls: ${result.vinyl_count}`;
    }

    async function regenerate() {
      if (!fontPath) return;
      els.status.textContent = 'Generating…';
      const resp = await api.call('layer_effects.regenerate', {
        font_path: fontPath, sample: els.sample.value || 'A', stack,
      });
      if (!resp.ok) { els.status.textContent = resp.error; return; }
      layerStatuses = resp.result.layer_statuses;
      let text = `${resp.result.shape_count} shape(s) generated.`;
      if (resp.result.warnings.length) text += ' ' + resp.result.warnings.join('; ');
      els.status.textContent = text;
      applyPreviewResult(resp.result);
      renderLayerRows();
    }

    async function refreshPreviewOnly() {
      if (!fontPath) return;
      const enabled_ids = stack.layers.filter((l) => l.enabled).map((l) => l.id);
      const resp = await api.call('layer_effects.render_preview', { compare: els.compare.checked, enabled_ids });
      if (resp.ok) applyPreviewResult(resp.result);
    }

    async function refreshCosmetic() {
      if (!fontPath) return;
      const resp = await api.call('layer_effects.recolor', { stack });
      if (resp.ok) applyPreviewResult(resp.result);
    }

    function renderLayerRows() {
      const layers = stack.layers;
      const n = layers.length;
      els.rows.innerHTML = layers.slice().reverse().map((layer, displayIndex) => {
        const orderNum = n - displayIndex;
        const warn = layerStatuses[layer.id] ? ' ⚠' : '';
        const active = layer.id === selectedLayerId ? 'active' : '';
        return `<div class="le-layer-row ${active}" data-id="${layer.id}">
          <input type="checkbox" class="le-layer-enabled" data-id="${layer.id}" ${layer.enabled ? 'checked' : ''}>
          <span class="le-layer-label">${orderNum}  ${esc(layer.name)}${warn}</span>
        </div>`;
      }).join('') || '<div class="list-empty">No layers.</div>';

      els.rows.querySelectorAll('.le-layer-enabled').forEach((cb) => {
        cb.addEventListener('click', (e) => e.stopPropagation());
        cb.addEventListener('change', () => {
          const layer = stack.layers.find((l) => l.id === cb.dataset.id);
          layer.enabled = cb.checked;
          if (layer.id === selectedLayerId) els.enabled.checked = layer.enabled;
          refreshPreviewOnly();
        });
      });
      els.rows.querySelectorAll('.le-layer-row').forEach((row) => {
        row.addEventListener('click', () => selectLayer(row.dataset.id));
      });
    }

    function selectLayer(id) {
      selectedLayerId = id;
      renderLayerRows();
      renderProperties();
    }

    function renderProperties() {
      const layer = selectedLayer();
      if (!layer) return;
      els.name.value = layer.name;
      els.enabled.checked = layer.enabled;
      els.operation.value = layer.operation;
      els.amount.value = layer.amount;
      els.offsetX.value = layer.offset_x;
      els.offsetY.value = layer.offset_y;
      els.scaleX.value = layer.scale_x;
      els.scaleY.value = layer.scale_y;
      els.rotation.value = layer.rotation_deg;
      els.opacity.value = layer.opacity;

      const index = stack.layers.findIndex((l) => l.id === layer.id);
      const earlier = index > 0 ? stack.layers.slice(0, index) : [];
      const sourceOptions = ['<option value="original">original</option>']
        .concat(earlier.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`));
      els.source.innerHTML = sourceOptions.join('');
      els.source.value = layer.source;
      els.booleanOperand.innerHTML = '<option value="">(none)</option>'
        + earlier.map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join('');
      els.booleanOperand.value = layer.boolean_operand || '';

      colorPicker.sync();
    }

    // -- font loading -------------------------------------------------------
    function loadFont(path) {
      fontPath = path;
      els.fontStatus.textContent = `${path.split(/[\\/]/).pop()} loaded.`;
      regenerate();
    }
    els.font.addEventListener('change', () => { if (els.font.value.trim()) loadFont(els.font.value.trim()); });
    container.querySelector('#leBrowseFont').addEventListener('click', async () => {
      const resp = await api.call('layer_effects.browse_font', {});
      if (resp.ok && !resp.result.cancelled) { els.font.value = resp.result.path; loadFont(resp.result.path); }
    });
    els.sample.addEventListener('change', regenerate);

    // -- presets --------------------------------------------------------------
    async function loadPresetLists() {
      const resp = await api.call('layer_effects.get_presets', {});
      if (!resp.ok) return;
      els.presetSelect.innerHTML = resp.result.built_in.map((n) => `<option>${esc(n)}</option>`).join('');
      els.presetSelect.value = 'Concentric Inline';
      els.savedSelect.innerHTML = resp.result.saved.map((n) => `<option>${esc(n)}</option>`).join('');
    }
    async function applyStack(newStack) {
      stack = newStack;
      selectedLayerId = stack.layers.length ? stack.layers[0].id : null;
      renderLayerRows();
      renderProperties();
      regenerate();
    }
    container.querySelector('#leApplyPreset').addEventListener('click', async () => {
      const resp = await api.call('layer_effects.apply_preset', { name: els.presetSelect.value });
      if (resp.ok) applyStack(resp.result.stack);
    });
    container.querySelector('#leLoadSaved').addEventListener('click', async () => {
      const name = els.savedSelect.value;
      if (!name) return;
      const resp = await api.call('layer_effects.load_saved_preset', { name });
      if (resp.ok && resp.result.found) applyStack(resp.result.stack);
    });
    container.querySelector('#leSaveAs').addEventListener('click', async () => {
      const name = window.prompt('Preset name:', stack.name || 'Custom');
      if (!name) return;
      stack.name = name;
      const resp = await api.call('layer_effects.save_preset', { stack });
      if (resp.ok) {
        els.savedSelect.innerHTML = resp.result.saved.map((n) => `<option>${esc(n)}</option>`).join('');
        els.savedSelect.value = name;
      }
    });
    container.querySelector('#leDeleteSaved').addEventListener('click', async () => {
      const name = els.savedSelect.value;
      if (!name) return;
      const resp = await api.call('layer_effects.delete_preset', { name });
      if (resp.ok) els.savedSelect.innerHTML = resp.result.saved.map((n) => `<option>${esc(n)}</option>`).join('');
    });

    // -- add / duplicate / delete / reorder ----------------------------------
    container.querySelector('#leAdd').addEventListener('click', () => {
      const layer = {
        id: newLayerId(), name: `Layer ${stack.layers.length + 1}`, operation: 'original',
        enabled: true, source: 'original', amount: 0, offset_x: 0, offset_y: 0,
        scale_x: 1, scale_y: 1, rotation_deg: 0, origin: 'centroid',
        boolean_operand: null, color: [255, 255, 255, 255], opacity: 1.0,
      };
      stack.layers.push(layer);
      selectedLayerId = layer.id;
      renderLayerRows(); renderProperties(); regenerate();
    });
    container.querySelector('#leDuplicate').addEventListener('click', () => {
      const src = selectedLayer();
      if (!src) return;
      const copy = { ...src, id: newLayerId(), name: `${src.name} copy`, color: [...src.color] };
      const index = stack.layers.indexOf(src);
      stack.layers.splice(index + 1, 0, copy);
      selectedLayerId = copy.id;
      renderLayerRows(); renderProperties(); regenerate();
    });
    container.querySelector('#leDelete').addEventListener('click', () => {
      const layer = selectedLayer();
      if (!layer || stack.layers.length <= 1) return;
      stack.layers = stack.layers.filter((l) => l.id !== layer.id);
      selectedLayerId = stack.layers[stack.layers.length - 1].id;
      renderLayerRows(); renderProperties(); regenerate();
    });
    function moveLayer(delta) {
      const layer = selectedLayer();
      if (!layer) return;
      const index = stack.layers.indexOf(layer);
      const newIndex = Math.max(0, Math.min(stack.layers.length - 1, index + delta));
      if (newIndex === index) return;
      stack.layers.splice(index, 1);
      stack.layers.splice(newIndex, 0, layer);
      renderLayerRows(); renderProperties(); regenerate();
    }
    container.querySelector('#leMoveUp').addEventListener('click', () => moveLayer(-1));
    container.querySelector('#leMoveDown').addEventListener('click', () => moveLayer(1));

    // -- properties commits ---------------------------------------------------
    function commitFloat(field, input, fallback) {
      const layer = selectedLayer();
      if (!layer) return;
      const value = parseFloat(input.value);
      layer[field] = Number.isFinite(value) ? value : fallback;
      input.value = layer[field];
      regenerate();
    }
    els.name.addEventListener('change', () => {
      const layer = selectedLayer();
      if (!layer) return;
      layer.name = els.name.value.trim() || layer.name;
      renderLayerRows();
      refreshCosmetic();
    });
    els.enabled.addEventListener('change', () => {
      const layer = selectedLayer();
      if (!layer) return;
      layer.enabled = els.enabled.checked;
      renderLayerRows();
      refreshPreviewOnly();
    });
    els.operation.addEventListener('change', () => {
      const layer = selectedLayer();
      if (!layer) return;
      layer.operation = els.operation.value;
      regenerate();
    });
    els.source.addEventListener('change', () => {
      const layer = selectedLayer();
      if (!layer) return;
      layer.source = els.source.value;
      regenerate();
    });
    els.booleanOperand.addEventListener('change', () => {
      const layer = selectedLayer();
      if (!layer) return;
      layer.boolean_operand = els.booleanOperand.value || null;
      regenerate();
    });
    els.amount.addEventListener('change', () => commitFloat('amount', els.amount, 0));
    els.offsetX.addEventListener('change', () => commitFloat('offset_x', els.offsetX, 0));
    els.offsetY.addEventListener('change', () => commitFloat('offset_y', els.offsetY, 0));
    els.scaleX.addEventListener('change', () => commitFloat('scale_x', els.scaleX, 1));
    els.scaleY.addEventListener('change', () => commitFloat('scale_y', els.scaleY, 1));
    els.rotation.addEventListener('change', () => commitFloat('rotation_deg', els.rotation, 0));
    els.opacity.addEventListener('input', () => {
      const layer = selectedLayer();
      if (!layer) return;
      layer.opacity = parseFloat(els.opacity.value);
      refreshCosmetic();
    });
    els.compare.addEventListener('change', refreshPreviewOnly);

    // -- color picker (external-drive, keyed to the selected layer) ---------
    const colorPicker = await window.ForzaColorPicker.create(container.querySelector('#leColorPicker'), {
      title: '',
      getColor: () => { const l = selectedLayer(); return l ? l.color : null; },
      onChange: (rgba) => {
        const layer = selectedLayer();
        if (!layer) return;
        layer.color = rgba;
        refreshCosmetic();
      },
    });

    await loadPresetLists();
    const presetResp = await api.call('layer_effects.apply_preset', { name: 'Concentric Inline' });
    if (presetResp.ok) {
      stack = presetResp.result.stack;
      selectedLayerId = stack.layers.length ? stack.layers[0].id : null;
    }
    renderLayerRows();
    renderProperties();

    return () => { colorPicker.destroy(); };
  }

  window.ForzaTabs['layer_effects'] = mount;
})();
