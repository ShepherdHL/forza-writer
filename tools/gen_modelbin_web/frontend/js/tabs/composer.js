// Composer tab: compose multi-line vinyl text from an already-generated
// fontpack's glyphs, with per-line color fills (solid/sequence/rainbow)
// and a Manufacturer Colors browser. Third consumer of the shared
// color-picker component (external-drive mode this time, not self-drive).
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  const SEQ_MODES = [['solid', 'Solid'], ['sequence', 'Sequence'], ['rainbow', 'Rainbow ~']];
  const SEQ_PRESETS = {
    roygbiv: [[226, 69, 60, 255], [236, 138, 46, 255], [240, 201, 58, 255], [95, 168, 90, 255],
      [63, 127, 209, 255], [75, 79, 176, 255], [138, 79, 176, 255]],
    grayscale: [[0, 0, 0, 255], [54, 69, 79, 255], [128, 128, 128, 255], [132, 136, 132, 255], [255, 255, 255, 255]],
  };
  const MAX_SEQ_STOPS = 12;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }
  function rgbaToHex(rgba) {
    return '#' + [rgba[0], rgba[1], rgba[2]].map((c) => c.toString(16).padStart(2, '0')).join('');
  }
  function readableFgFor(hex) {
    const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
    return luminance > 140 ? '#17181a' : '#f2f3f5';
  }
  function newLineFill() {
    return { mode: 'solid', colors: [[255, 255, 255, 255]], blend: false };
  }

  async function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">Composer</h2>
      <div class="intro-text">
        Type text using an already-generated fontpack's glyphs, with real per-glyph spacing and a
        shared baseline. Not just glyphs placed side by side, which would render a period the same
        size as a capital M.
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 360px;">
        <div>
          <div class="section">
            <div class="section-title">Compose Text</div>
            <div class="path-field" style="margin-bottom: 10px;">
              <input type="text" class="path-input" id="cpPackDir" placeholder="Fontpack folder">
              <button type="button" class="btn" id="cpBrowsePack">Browse…</button>
            </div>
            <textarea id="cpText" rows="4" style="width:100%; background:var(--entry-bg); color:var(--fg); border:1px solid var(--border); border-radius:4px; padding:8px; font-family:var(--body-font); font-size:13px; margin-bottom: 12px;"></textarea>

            <div class="section-title" style="border: none; padding-bottom: 0;">Per-Line Color</div>
            <div class="field-hint" style="margin-bottom: 8px;">
              Each line picks its own fill: Solid (one color), Sequence (an editable list of color
              stops, blended smoothly or stepped as repeating bands), or Rainbow (a continuous hue
              sweep across that line). Click a swatch, then use the Color panel to change it.
            </div>
            <div id="cpLineRows"></div>

            <div class="section-title" style="border: none; padding-bottom: 0; margin-top: 14px;">Layered Glyph Effect</div>
            <div class="checkbox-row">
              <input type="checkbox" id="cpLayerEffectEnabled">
              <label for="cpLayerEffectEnabled">Enable Layered Glyph Effect</label>
            </div>
            <div class="path-field" style="margin-bottom: 6px;">
              <select class="path-input" id="cpLayerEffectPreset" style="max-width: 240px;"></select>
              <button type="button" class="btn" id="cpApplyLayerPreset">Apply preset</button>
            </div>
            <div class="field-hint" id="cpLayerEffectSummary" style="margin-bottom: 4px;"></div>
            <div class="field-hint">
              Bold/Italic/Underline/Strikethrough still reshape the result. Per-Line Color above is
              ignored while this is enabled -- each layer keeps its own configured color instead
              (built on the Layer Effects tab's presets; this doesn't share a live stack with that
              tab, so re-apply the preset here after editing it there).
            </div>

            <div class="section-title" style="border: none; padding-bottom: 0; margin-top: 14px;">Style</div>
            <div class="field-hint" style="margin-bottom: 6px;">Applies to the whole block. Color is set per line above.</div>
            <div style="display:flex; gap: 16px; flex-wrap: wrap; align-items: center; margin-bottom: 8px;">
              <label class="field-label">Size <input type="number" class="path-input" id="cpSize" value="100" style="width:70px; margin-left:6px;"> %</label>
              <label><input type="checkbox" id="cpBold"> Bold</label>
              <label><input type="checkbox" id="cpItalic"> Italic</label>
              <label><input type="checkbox" id="cpUnderline"> Underline</label>
              <label><input type="checkbox" id="cpStrikethrough"> Strikethrough</label>
            </div>
            <div style="display:flex; gap: 16px; flex-wrap: wrap; align-items: center; margin-bottom: 10px;">
              <label class="field-label">Letter spacing <input type="number" class="path-input" id="cpLetterSpacing" value="0" style="width:70px; margin-left:6px;"></label>
              <label class="field-label">Line spacing <input type="number" class="path-input" id="cpLineSpacing" value="100" style="width:70px; margin-left:6px;"> %</label>
            </div>
            <div class="field-hint" style="margin-bottom: 10px;">
              Bold/Italic reshape existing shapes in place. No extra vinyl layers. Underline/Strikethrough each add one bar shape per line.
            </div>

            <div class="radio-group" style="margin-bottom: 10px;">
              <label class="field-label">Align</label>
              <label><input type="radio" name="cpAlign" value="left" checked> Left</label>
              <label><input type="radio" name="cpAlign" value="center"> Center</label>
              <label><input type="radio" name="cpAlign" value="right"> Right</label>
              <label><input type="radio" name="cpAlign" value="justify"> Justify</label>
              <button type="button" class="btn accent" id="cpCompose" style="margin-left: 14px;">Compose</button>
              <button type="button" class="btn" id="cpSave" disabled>Save…</button>
            </div>
            <div class="field-hint" style="margin-bottom: 10px;">
              Justify spreads extra space across word gaps to fill the widest line. The last line of
              multi-line text stays left-aligned either way. Characters with no generated glyph in
              the pack are skipped and listed below, not treated as errors.
            </div>

            <div class="gi-diff-panel" style="aspect-ratio: auto; height: 200px;" id="cpPreviewPanel">
              <div class="gi-diff-empty">Pick a fontpack folder, type some text, and click Compose.</div>
            </div>
            <div class="field-hint" id="cpStats" style="margin-top: 8px;"></div>
          </div>
        </div>

        <div>
          <div class="section">
            <div class="section-title">Color</div>
            <div class="field-hint" id="cpEditingTarget" style="margin-bottom: 8px;">No line selected</div>
            <div id="cpColorPicker"></div>
            <a class="link" href="#" id="cpConverterLink">Open Bang's Forza Color Converter ↗</a>

            <div class="section-title" style="margin-top: 14px;">Manufacturer Colors</div>
            <input type="text" class="path-input" id="cpMfgSearch" placeholder="Search…" style="width:100%; margin-bottom: 6px;">
            <select class="path-input" id="cpMfgMake" style="width:100%; margin-bottom: 6px;"></select>
            <div class="field-hint" id="cpMfgCount" style="margin-bottom: 6px;"></div>
            <div class="list-box" id="cpMfgList" style="height: 220px;"></div>
            <div class="field-hint" style="margin-top: 8px;">
              Each row's exact hue/saturation/brightness slider notation shows above once selected,
              for reproducing the precise in-game shade.
            </div>
            <div class="field-hint" style="margin-top: 6px;">
              Source: GTPlanet. Catalogued by Mitcho2001, JaCor653 and MadaraxUchiha.
            </div>
          </div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    let lineFills = [];
    let editing = null; // [lineIndex, slotIndex]
    let lastLineCount = -1;
    let lastComposedShapes = null;
    let mfgRows = [];
    let layerEffectStack = null; // LayerStack.to_dict(), from the last "Apply preset" click

    // -- Layered Glyph Effect ------------------------------------------------
    function updateLayerEffectSummary() {
      const summaryEl = container.querySelector('#cpLayerEffectSummary');
      if (!layerEffectStack) { summaryEl.textContent = 'No preset applied yet.'; return; }
      const state = container.querySelector('#cpLayerEffectEnabled').checked ? 'Active' : 'Configured, not enabled';
      summaryEl.textContent = `${state}: "${layerEffectStack.name}" -- ${layerEffectStack.layers.length} layer(s).`;
    }
    container.querySelector('#cpLayerEffectEnabled').addEventListener('change', updateLayerEffectSummary);

    (async () => {
      const resp = await api.call('layer_effects.get_presets', {});
      if (!resp.ok) return;
      const sel = container.querySelector('#cpLayerEffectPreset');
      sel.innerHTML = resp.result.built_in.map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join('');
      if (resp.result.built_in.includes('Concentric Inline')) sel.value = 'Concentric Inline';
    })();

    container.querySelector('#cpApplyLayerPreset').addEventListener('click', async () => {
      const name = container.querySelector('#cpLayerEffectPreset').value;
      if (!name) return;
      const resp = await api.call('layer_effects.apply_preset', { name });
      if (!resp.ok) { container.querySelector('#cpLayerEffectSummary').textContent = resp.error; return; }
      layerEffectStack = resp.result.stack;
      updateLayerEffectSummary();
    });

    function lineTexts() {
      return container.querySelector('#cpText').value.split('\n');
    }

    function currentColor() {
      if (!editing) return null;
      const [li, si] = editing;
      const fill = lineFills[li];
      const s = Math.min(si, fill.colors.length - 1);
      return fill.colors[s];
    }

    function setCurrentColor(rgba) {
      if (!editing) return;
      const [li, si] = editing;
      const fill = lineFills[li];
      const s = Math.min(si, fill.colors.length - 1);
      fill.colors[s] = rgba;
      const swatch = container.querySelector(`.cp-line-swatch[data-li="${li}"][data-si="${s}"]`);
      if (swatch) swatch.style.background = rgbaToHex(rgba);
    }

    const colorPicker = await window.ForzaColorPicker.create(container.querySelector('#cpColorPicker'), {
      title: '',
      getColor: currentColor,
      onChange: setCurrentColor,
    });

    function refreshEditingTarget() {
      const el = container.querySelector('#cpEditingTarget');
      if (!editing || editing[0] >= lineFills.length) {
        el.textContent = 'No line selected';
      } else {
        const [li, si] = editing;
        const fill = lineFills[li];
        const label = fill.mode === 'sequence' ? `Stop ${Math.min(si, fill.colors.length - 1) + 1}` : 'Color';
        el.textContent = `Line ${li + 1} · ${label}`;
      }
      colorPicker.sync();
    }

    function onTextChanged() {
      const lines = lineTexts();
      if (lines.length === lastLineCount) return;
      lastLineCount = lines.length;
      while (lineFills.length < lines.length) lineFills.push(newLineFill());
      lineFills.length = lines.length;
      if (!editing || editing[0] >= lines.length) editing = lines.length ? [0, 0] : null;
      renderLineRows();
    }

    function lineSwatchHtml(li, si) {
      const fill = lineFills[li];
      const color = fill.colors[si];
      const isEditing = editing && editing[0] === li && editing[1] === si;
      return `<div class="cp-line-swatch" data-li="${li}" data-si="${si}"
        style="width:28px; height:22px; border-radius:3px; cursor:pointer; background:${rgbaToHex(color)};
        border: ${isEditing ? '2px solid var(--accent)' : '1px solid var(--border)'};"></div>`;
    }

    function renderLineRows() {
      const rowsEl = container.querySelector('#cpLineRows');
      const texts = lineTexts();
      rowsEl.innerHTML = texts.map((text, li) => {
        const fill = lineFills[li];
        let preview = text.trim() || '(empty)';
        if (preview.length > 24) preview = preview.slice(0, 23) + '…';
        const pills = SEQ_MODES.map(([key, label]) => `
          <button type="button" class="cp-mode-pill ${fill.mode === key ? 'active' : ''}" data-li="${li}" data-mode="${key}">${esc(label)}</button>
        `).join('');
        let body;
        if (fill.mode === 'solid') {
          body = lineSwatchHtml(li, 0);
        } else if (fill.mode === 'rainbow') {
          body = '<span class="field-hint">(continuous hue sweep across this line)</span>';
        } else {
          const stops = fill.colors.map((_c, si) => `
            <span style="display:inline-flex; flex-direction:column; align-items:center; gap:2px; margin-right:4px;">
              ${lineSwatchHtml(li, si)}
              ${fill.colors.length > 2 ? `<button type="button" class="btn cp-remove-stop" data-li="${li}" data-si="${si}" style="padding:0 4px; font-size:10px;">×</button>` : ''}
            </span>
          `).join('');
          const addBtn = fill.colors.length < MAX_SEQ_STOPS ? `<button type="button" class="btn cp-add-stop" data-li="${li}" style="padding:2px 6px;">+</button>` : '';
          const blendBtns = ['Blend', 'Step'].map((label, i) => {
            const val = i === 0;
            return `<button type="button" class="btn cp-blend-toggle ${fill.blend === val ? 'accent' : ''}" data-li="${li}" data-blend="${val}" style="padding:2px 8px; font-size:10px;">${label}</button>`;
          }).join('');
          const presetBtns = ['roygbiv', 'grayscale'].map((key) =>
            `<button type="button" class="btn cp-preset" data-li="${li}" data-preset="${key}" style="padding:2px 8px; font-size:10px;">${key === 'roygbiv' ? 'ROYGBIV' : 'Grayscale'}</button>`
          ).join('');
          body = `<div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <span style="display:flex; gap:4px;">${blendBtns}</span>
            <span style="display:flex; align-items:center;">${stops}${addBtn}</span>
            <span style="display:flex; gap:4px;">${presetBtns}</span>
          </div>`;
        }
        return `
          <div style="display:flex; align-items:center; gap:10px; padding: 4px 0; border-top: 1px solid var(--frame-light);">
            <span style="width:20px; color:var(--muted); font-size:11px;">${li + 1}.</span>
            <span class="field-hint" style="width:170px; flex-shrink:0;">"${esc(preview)}"</span>
            <span style="display:flex; gap:3px;">${pills}</span>
            <span>${body}</span>
          </div>
        `;
      }).join('');

      rowsEl.querySelectorAll('.cp-mode-pill').forEach((btn) => {
        btn.addEventListener('click', () => {
          const li = Number(btn.dataset.li);
          const fill = lineFills[li];
          fill.mode = btn.dataset.mode;
          if (fill.mode === 'solid') fill.colors = [fill.colors[0]];
          else if (fill.mode === 'sequence' && fill.colors.length < 2) fill.colors = [fill.colors[0], fill.colors[0]];
          editing = [li, 0];
          renderLineRows();
          refreshEditingTarget();
        });
      });
      rowsEl.querySelectorAll('.cp-line-swatch').forEach((el) => {
        el.addEventListener('click', () => {
          editing = [Number(el.dataset.li), Number(el.dataset.si)];
          renderLineRows();
          refreshEditingTarget();
        });
      });
      rowsEl.querySelectorAll('.cp-add-stop').forEach((btn) => {
        btn.addEventListener('click', () => {
          const li = Number(btn.dataset.li);
          const fill = lineFills[li];
          if (fill.colors.length >= MAX_SEQ_STOPS) return;
          fill.colors.push(fill.colors[fill.colors.length - 1]);
          editing = [li, fill.colors.length - 1];
          renderLineRows();
          refreshEditingTarget();
        });
      });
      rowsEl.querySelectorAll('.cp-remove-stop').forEach((btn) => {
        btn.addEventListener('click', () => {
          const li = Number(btn.dataset.li), si = Number(btn.dataset.si);
          const fill = lineFills[li];
          if (fill.colors.length <= 2) return;
          fill.colors.splice(si, 1);
          if (editing && editing[0] === li && editing[1] >= fill.colors.length) editing = [li, fill.colors.length - 1];
          renderLineRows();
          refreshEditingTarget();
        });
      });
      rowsEl.querySelectorAll('.cp-blend-toggle').forEach((btn) => {
        btn.addEventListener('click', () => {
          lineFills[Number(btn.dataset.li)].blend = btn.dataset.blend === 'true';
          renderLineRows();
        });
      });
      rowsEl.querySelectorAll('.cp-preset').forEach((btn) => {
        btn.addEventListener('click', () => {
          const li = Number(btn.dataset.li);
          const fill = lineFills[li];
          fill.colors = SEQ_PRESETS[btn.dataset.preset].map((c) => [...c]);
          fill.blend = false;
          editing = [li, 0];
          renderLineRows();
          refreshEditingTarget();
        });
      });
    }

    container.querySelector('#cpText').addEventListener('input', onTextChanged);
    onTextChanged();

    container.querySelector('#cpBrowsePack').addEventListener('click', async () => {
      const resp = await api.call('composer.pick_pack_dir', { initial: container.querySelector('#cpPackDir').value });
      if (resp.ok && !resp.result.cancelled) container.querySelector('#cpPackDir').value = resp.result.path;
    });

    container.querySelector('#cpConverterLink').addEventListener('click', (e) => {
      e.preventDefault();
      window.open('https://dxbang.github.io/forza-colors/', '_blank');
    });

    container.querySelector('#cpCompose').addEventListener('click', async () => {
      const statsEl = container.querySelector('#cpStats');
      onTextChanged();
      updateLayerEffectSummary();
      const useLayerEffect = container.querySelector('#cpLayerEffectEnabled').checked;
      if (useLayerEffect && !layerEffectStack) {
        statsEl.textContent = 'Click Apply preset under Layered Glyph Effect first.';
        return;
      }
      const basePayload = {
        pack_dir: container.querySelector('#cpPackDir').value,
        text: container.querySelector('#cpText').value,
        align: container.querySelector('input[name="cpAlign"]:checked').value,
        size: container.querySelector('#cpSize').value,
        letter_spacing: container.querySelector('#cpLetterSpacing').value,
        line_spacing: container.querySelector('#cpLineSpacing').value,
        bold: container.querySelector('#cpBold').checked,
        italic: container.querySelector('#cpItalic').checked,
        underline: container.querySelector('#cpUnderline').checked,
        strikethrough: container.querySelector('#cpStrikethrough').checked,
      };
      statsEl.textContent = 'Composing…';
      const resp = useLayerEffect
        ? await api.call('composer.compose_layered', { ...basePayload, stack: layerEffectStack })
        : await api.call('composer.compose', { ...basePayload, fills: lineFills });
      if (!resp.ok) { statsEl.textContent = resp.error; return; }
      lastComposedShapes = resp.result.shapes;
      container.querySelector('#cpPreviewPanel').innerHTML =
        `<img src="${resp.result.preview_image}" alt="Composed text preview" style="width:100%;height:100%;object-fit:contain;">`;
      let text = resp.result.stats;
      if (resp.result.warnings.length) text += ' ' + resp.result.warnings.join(' ');
      statsEl.textContent = text;
      container.querySelector('#cpSave').disabled = resp.result.shapes.length === 0;
    });

    container.querySelector('#cpSave').addEventListener('click', async () => {
      if (!lastComposedShapes) return;
      const resp = await api.call('composer.save', { shapes: lastComposedShapes });
      if (!resp.ok) { container.querySelector('#cpStats').textContent = resp.error; return; }
      if (resp.result.cancelled) return;
      container.querySelector('#cpStats').textContent = `Saved to ${resp.result.path.split('\\').pop()}.`;
    });

    // -- Manufacturer Colors --------------------------------------------
    const makesResp = await api.call('composer.mfg_makes', {});
    if (makesResp.ok) {
      const sel = container.querySelector('#cpMfgMake');
      sel.innerHTML = ['All makes', ...makesResp.result.makes].map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join('');
    }

    async function refreshMfg() {
      const term = container.querySelector('#cpMfgSearch').value;
      const make = container.querySelector('#cpMfgMake').value;
      const resp = await api.call('composer.mfg_search', { term, make: make === 'All makes' ? null : make });
      if (!resp.ok) return;
      mfgRows = resp.result.rows;
      container.querySelector('#cpMfgCount').textContent = resp.result.capped
        ? `Showing ${mfgRows.length} of ${resp.result.total.toLocaleString()}. Refine your search.`
        : `${resp.result.total.toLocaleString()} match(es).`;
      const listEl = container.querySelector('#cpMfgList');
      if (mfgRows.length === 0) {
        listEl.innerHTML = '<div class="list-empty">No matches.</div>';
        return;
      }
      listEl.innerHTML = mfgRows.map((c, i) => `
        <div class="list-row" data-i="${i}" style="background:${c.hex1}; color:${readableFgFor(c.hex1)};">
          ${esc(c.make)} · ${esc(c.name)} (${esc(c.paint_type)})
        </div>
      `).join('');
      listEl.querySelectorAll('.list-row').forEach((row, i) => {
        row.addEventListener('click', async () => {
          const color = mfgRows[i];
          const rgbaResp = await api.call('composer.mfg_color_rgba', { hex1: color.hex1 });
          if (!rgbaResp.ok || !editing) return;
          setCurrentColor(rgbaResp.result.rgba);
          renderLineRows();
          const el = container.querySelector('#cpEditingTarget');
          el.textContent = `${el.textContent}  ·  H ${color.hue}  S ${color.saturation}  B ${color.brightness}`;
          colorPicker.sync();
        });
      });
    }
    container.querySelector('#cpMfgSearch').addEventListener('input', refreshMfg);
    container.querySelector('#cpMfgMake').addEventListener('change', refreshMfg);
    refreshMfg();

    return () => { colorPicker.destroy(); };
  }

  window.ForzaTabs.composer = mount;
})();
