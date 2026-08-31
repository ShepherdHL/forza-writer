// Shared color-picker component -- the web counterpart to
// tools/gen_modelbin_gui/color_picker_widget.py's ColorPickerWidget.
// Two drive modes, matching the Python widget exactly:
//   - self-drive (settingsKey set): the widget owns one color, persisted
//     under that key via color_picker.get/set_setting_color.
//   - external-drive (getColor/onChange set): the owner is the source of
//     truth; the widget just reflects getColor() and calls onChange(rgba).
// Saved/recent colors are a single shared library (not per-instance) --
// every live instance on the page is notified when any other one changes
// it, mirroring the Python widget's _LIVE_INSTANCES broadcast.
window.ForzaColorPicker = (function () {
  const SB_SIZE = 130;

  // -- color math -------------------------------------------------------
  // Standard HSV, reimplemented directly here rather than round-tripped
  // through Python per drag pixel -- forza_colors.py's own docstring notes
  // "Forza's H,S,B is already plain normalized HSV", so this is the same
  // well-known formula, not proprietary logic. Only *persisted* state
  // (saved/recent library, settings_key colors) goes through the backend.
  function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    let h, s; const l = (max + min) / 2;
    if (max === min) { h = 0; s = 0; } else {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
      else if (max === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h /= 6;
    }
    return [h * 360, s * 100, l * 100];
  }

  function rgbToHsb(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const v = max, d = max - min;
    const s = max === 0 ? 0 : d / max;
    let h;
    if (d === 0) h = 0;
    else if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6;
    return [h * 360, s * 100, v * 100];
  }

  function hsvToRgb(h, s, v) {
    const i = Math.floor(h * 6);
    const f = h * 6 - i;
    const p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s);
    let r, g, b;
    switch (i % 6) {
      case 0: r = v; g = t; b = p; break;
      case 1: r = q; g = v; b = p; break;
      case 2: r = p; g = v; b = t; break;
      case 3: r = p; g = q; b = v; break;
      case 4: r = t; g = p; b = v; break;
      default: r = v; g = p; b = q; break;
    }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
  }

  function rgbaToHex(rgba) {
    return '#' + [rgba[0], rgba[1], rgba[2]].map((c) => c.toString(16).padStart(2, '0')).join('');
  }

  function hexToRgb(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function readableFgFor(hex) {
    const [r, g, b] = hexToRgb(hex) || [0, 0, 0];
    const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
    return luminance > 140 ? '#17181a' : '#f2f3f5';
  }

  // -- shared library state (saved/recent), broadcast to every instance --
  const instances = new Set();
  let library = { saved: [], recent: [] };
  let libraryLoaded = false;

  async function ensureLibrary() {
    if (libraryLoaded) return library;
    const resp = await window.pywebview.api.call('color_picker.get_library', {});
    if (resp.ok) { library = resp.result; libraryLoaded = true; }
    return library;
  }

  function broadcastLibrary(newLibrary, exceptInstance) {
    library = newLibrary;
    instances.forEach((inst) => { if (inst !== exceptInstance) inst._onLibraryChanged(); });
  }

  let presetsCache = null;
  async function ensurePresets() {
    if (presetsCache) return presetsCache;
    const resp = await window.pywebview.api.call('color_picker.get_presets', {});
    presetsCache = resp.ok ? resp.result.presets : [];
    return presetsCache;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function namedSwatchHtml(cls, rgba, name, { extra = '', showHex = true } = {}) {
    const hex = rgbaToHex(rgba);
    const fg = readableFgFor(hex);
    const label = name.length > 11 ? name.slice(0, 10) + '…' : name;
    const inner = showHex
      ? `<span class="cp-swatch-name">${escapeHtml(label)}</span><span class="cp-swatch-hex">${escapeHtml(hex)}</span>`
      : escapeHtml(label);
    return `<button type="button" class="${cls}" style="background:${hex};color:${fg}" ${extra} title="${escapeHtml(name)} (${escapeHtml(hex)})">${inner}</button>`;
  }

  async function create(container, options) {
    const opts = Object.assign({ title: 'Color', initial: [255, 255, 255, 255] }, options);
    let color = opts.initial;
    let pickerHue = 0; // held steady for near-grayscale colors, matching the Tk widget

    if (opts.settingsKey) {
      const resp = await window.pywebview.api.call('color_picker.get_setting_color', { key: opts.settingsKey });
      if (resp.ok && resp.result.rgba) color = resp.result.rgba;
    } else if (opts.getColor) {
      color = opts.getColor();
    }

    container.innerHTML = `
      <div class="cp-title">${escapeHtml(opts.title)}</div>
      <div class="cp-main">
        <div class="cp-sb" tabindex="0"><div class="cp-sb-marker"></div></div>
        <div class="cp-hue" tabindex="0"><div class="cp-hue-marker"></div></div>
        <div class="cp-swatch-col">
          <div class="cp-swatch"></div>
          <input type="color" class="cp-native-input" style="display:none;">
          <button type="button" class="btn cp-native-btn">Pick… (OS)</button>
        </div>
      </div>
      <div class="cp-fields">
        <label>Hex <input type="text" class="cp-hex" size="8"></label>
        <label>R <input type="text" class="cp-r" size="3"></label>
        <label>G <input type="text" class="cp-g" size="3"></label>
        <label>B <input type="text" class="cp-b" size="3"></label>
        <label>A <input type="text" class="cp-a" size="3"></label>
      </div>
      <div class="cp-readout">
        <span class="cp-readout-label">HSL</span><span class="cp-hsl-0"></span><span class="cp-hsl-1"></span><span class="cp-hsl-2"></span>
        <span class="cp-readout-label">HSB</span><span class="cp-hsb-0"></span><span class="cp-hsb-1"></span><span class="cp-hsb-2"></span>
        <span class="cp-readout-label">Forza H,S,B</span><span class="cp-forza-0"></span><span class="cp-forza-1"></span><span class="cp-forza-2"></span>
      </div>
      <div class="cp-presets"></div>
      <div class="cp-section-label">Saved Colors</div>
      <div class="cp-save-row">
        <input type="text" class="cp-save-name" placeholder="Name" size="12">
        <button type="button" class="btn cp-save-btn">Save current</button>
      </div>
      <div class="cp-saved-grid"></div>
      <div class="field-hint">Click to apply. Right-click to remove.</div>
      <div class="cp-section-label">Recently Used</div>
      <div class="cp-recent-row"></div>
    `;

    const el = {
      sb: container.querySelector('.cp-sb'),
      sbMarker: container.querySelector('.cp-sb-marker'),
      hue: container.querySelector('.cp-hue'),
      hueMarker: container.querySelector('.cp-hue-marker'),
      swatch: container.querySelector('.cp-swatch'),
      nativeInput: container.querySelector('.cp-native-input'),
      nativeBtn: container.querySelector('.cp-native-btn'),
      hex: container.querySelector('.cp-hex'),
      r: container.querySelector('.cp-r'), g: container.querySelector('.cp-g'),
      b: container.querySelector('.cp-b'), a: container.querySelector('.cp-a'),
      hsl: [0, 1, 2].map((i) => container.querySelector(`.cp-hsl-${i}`)),
      hsb: [0, 1, 2].map((i) => container.querySelector(`.cp-hsb-${i}`)),
      forza: [0, 1, 2].map((i) => container.querySelector(`.cp-forza-${i}`)),
      presets: container.querySelector('.cp-presets'),
      saveName: container.querySelector('.cp-save-name'),
      saveBtn: container.querySelector('.cp-save-btn'),
      savedGrid: container.querySelector('.cp-saved-grid'),
      recentRow: container.querySelector('.cp-recent-row'),
    };

    function currentColor() {
      return opts.getColor ? opts.getColor() : color;
    }

    async function pushRecent(rgba) {
      const resp = await window.pywebview.api.call('color_picker.push_recent', { rgba });
      if (resp.ok) broadcastLibrary(resp.result, instance);
      renderSwatches();
    }

    function setColor(rgba, { recordRecent = true } = {}) {
      rgba = rgba.map((c) => Math.max(0, Math.min(255, Math.round(c))));
      if (!opts.getColor) {
        color = rgba;
        if (opts.settingsKey) {
          window.pywebview.api.call('color_picker.set_setting_color', { key: opts.settingsKey, rgba });
        }
      }
      if (recordRecent) pushRecent(rgba);
      redrawAll();
      if (opts.onChange) opts.onChange(rgba);
    }

    function readAlpha() {
      const v = parseInt(el.a.value, 10);
      return Number.isFinite(v) ? Math.max(0, Math.min(255, v)) : 255;
    }

    function redrawAll() {
      const c = currentColor();
      const enabled = c !== null && c !== undefined;
      el.nativeBtn.disabled = !enabled;
      el.saveBtn.disabled = !enabled;
      el.sb.classList.toggle('disabled', !enabled);
      el.hue.classList.toggle('disabled', !enabled);

      if (!enabled) {
        el.swatch.style.background = 'transparent';
        [el.hex, el.r, el.g, el.b].forEach((i) => { i.value = ''; });
        [...el.hsl, ...el.hsb, ...el.forza].forEach((span) => { span.textContent = ''; });
        el.sbMarker.style.display = 'none';
        el.hueMarker.style.display = 'none';
        renderSwatches();
        return;
      }
      el.sbMarker.style.display = '';
      el.hueMarker.style.display = '';

      const [r, g, b, a] = c;
      const hex = rgbaToHex(c);
      el.swatch.style.background = hex;
      el.hex.value = hex;
      el.r.value = r; el.g.value = g; el.b.value = b; el.a.value = a;

      const [hslH, hslS, hslL] = rgbToHsl(r, g, b);
      const [hsbH, hsbS, hsbB] = rgbToHsb(r, g, b);
      const setRow = (spans, values) => values.forEach((v, i) => { spans[i].textContent = v; });
      setRow(el.hsl, [`${hslH.toFixed(1)}°`, `${hslS.toFixed(1)}%`, `${hslL.toFixed(1)}%`]);
      setRow(el.hsb, [`${hsbH.toFixed(1)}°`, `${hsbS.toFixed(1)}%`, `${hsbB.toFixed(1)}%`]);
      setRow(el.forza, [(hsbH / 360).toFixed(3), (hsbS / 100).toFixed(3), (hsbB / 100).toFixed(3)]);

      const hue = hsbS > 1 ? hsbH / 360 : pickerHue; // hold hue steady near-grayscale, matching the Tk widget
      pickerHue = hue;
      el.sb.style.background =
        `linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, hsl(${hue * 360}, 100%, 50%))`;
      el.sbMarker.style.left = `${(hsbS / 100) * 100}%`;
      el.sbMarker.style.top = `${100 - hsbB}%`;
      el.hueMarker.style.top = `${hue * 100}%`;

      renderSwatches();
    }

    function pickFromSb(clientX, clientY) {
      if (currentColor() === undefined || currentColor() === null) return;
      const rect = el.sb.getBoundingClientRect();
      const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
      const y = Math.max(0, Math.min(rect.height, clientY - rect.top));
      const s = x / rect.width, v = 1 - y / rect.height;
      const rgb = hsvToRgb(pickerHue, s, v);
      setColor([...rgb, readAlpha()], { recordRecent: false });
    }

    function pickFromHue(clientY) {
      const c = currentColor();
      if (c === undefined || c === null) return;
      const rect = el.hue.getBoundingClientRect();
      const y = Math.max(0, Math.min(rect.height, clientY - rect.top));
      pickerHue = y / rect.height;
      const [, hsbS, hsbB] = rgbToHsb(c[0], c[1], c[2]);
      const rgb = hsvToRgb(pickerHue, hsbS / 100, hsbB / 100);
      setColor([...rgb, readAlpha()], { recordRecent: false });
    }

    function wireDrag(elm, onMove, onCommit) {
      let dragging = false;
      elm.addEventListener('mousedown', (e) => { dragging = true; onMove(e); });
      window.addEventListener('mousemove', (e) => { if (dragging) onMove(e); });
      window.addEventListener('mouseup', () => { if (dragging) { dragging = false; onCommit(); } });
    }
    wireDrag(el.sb, (e) => pickFromSb(e.clientX, e.clientY), () => { const c = currentColor(); if (c) pushRecent(c); });
    wireDrag(el.hue, (e) => pickFromHue(e.clientY), () => { const c = currentColor(); if (c) pushRecent(c); });

    el.nativeBtn.addEventListener('click', () => {
      const c = currentColor();
      if (!c) return;
      el.nativeInput.value = rgbaToHex(c);
      el.nativeInput.click();
    });
    el.nativeInput.addEventListener('change', () => {
      const rgb = hexToRgb(el.nativeInput.value);
      if (rgb) setColor([...rgb, readAlpha()]);
    });

    function commitHex() {
      const rgb = hexToRgb(el.hex.value);
      if (rgb) setColor([...rgb, readAlpha()]);
    }
    function commitRgb() {
      const r = parseInt(el.r.value, 10), g = parseInt(el.g.value, 10), b = parseInt(el.b.value, 10);
      if ([r, g, b].every(Number.isFinite)) setColor([r, g, b, readAlpha()]);
    }
    el.hex.addEventListener('change', commitHex);
    [el.r, el.g, el.b, el.a].forEach((i) => i.addEventListener('change', commitRgb));

    function renderPresets(presets) {
      el.presets.innerHTML = presets.map((p) => namedSwatchHtml('cp-swatch-btn', p.rgba, p.name)).join('');
      Array.from(el.presets.children).forEach((btn, i) => {
        btn.addEventListener('click', () => setColor(presets[i].rgba));
      });
    }

    function renderSwatches() {
      el.savedGrid.innerHTML = library.saved.map((s) =>
        namedSwatchHtml('cp-swatch-btn', s.rgba, s.name, { extra: `data-name="${escapeHtml(s.name)}"` })
      ).join('');
      Array.from(el.savedGrid.children).forEach((btn, i) => {
        const s = library.saved[i];
        btn.addEventListener('click', () => setColor(s.rgba));
        btn.addEventListener('contextmenu', async (e) => {
          e.preventDefault();
          const resp = await window.pywebview.api.call('color_picker.delete_saved', { name: s.name });
          if (resp.ok) broadcastLibrary(resp.result, instance);
          renderSwatches();
        });
      });

      el.recentRow.innerHTML = library.recent.map((rgba) =>
        namedSwatchHtml('cp-swatch-btn cp-swatch-btn-sm', rgba, rgbaToHex(rgba), { showHex: false })
      ).join('');
      Array.from(el.recentRow.children).forEach((btn, i) => {
        btn.addEventListener('click', () => setColor(library.recent[i], { recordRecent: false }));
      });
    }

    el.saveBtn.addEventListener('click', async () => {
      const c = currentColor();
      const name = el.saveName.value.trim();
      if (!c || !name) return;
      const resp = await window.pywebview.api.call('color_picker.save_named', { name, rgba: c });
      if (resp.ok) { broadcastLibrary(resp.result, instance); el.saveName.value = ''; renderSwatches(); }
    });

    const instance = {
      _onLibraryChanged: () => renderSwatches(),
      sync: () => redrawAll(),
      getColor: () => currentColor(),
      setColor,
      destroy: () => instances.delete(instance),
    };
    instances.add(instance);

    await ensureLibrary();
    renderPresets(await ensurePresets());
    redrawAll();

    return instance;
  }

  return { create };
})();
