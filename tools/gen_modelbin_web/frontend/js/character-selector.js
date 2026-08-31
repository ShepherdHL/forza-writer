// Shared character-selection UI (the Generator tab's "2. Characters"
// section): entire-font toggle, ASCII/derived checkboxes, custom text, and
// the catalog-driven non-Latin alphabet groups. Used by both Generator and
// Advanced Generator, which each run this against their own selected font
// -- the component itself owns no font_path and calls no charset_summary;
// the owning tab reads getSelection() and drives its own summary text,
// since "which font" differs per tab (Generator's own vs. Advanced's
// variable-font instance).
window.ForzaCharacterSelector = (function () {
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  const ASCII_BOXES = [
    ['upper', 'Latin uppercase A-Z (26)', true],
    ['lower', 'Latin lowercase a-z (26)', true],
    ['digits', 'ASCII digits 0-9 (10)', true],
    ['punct', 'ASCII punctuation (32)', true],
    ['symbols', 'Unicode symbols in font', false],
    ['private', 'Private-use glyphs (advanced)', false],
  ];

  // options: { onChange(), idPrefix }
  async function create(container, options = {}) {
    const api = window.pywebview.api;
    const prefix = options.idPrefix || 'cs';
    const onChange = options.onChange || (() => {});
    const id = (name) => `${prefix}_${name}`;

    container.innerHTML = `
      <div class="checkbox-row">
        <input type="checkbox" id="${id('all')}">
        <label for="${id('all')}">Entire font character map (advanced): generates every character the font has a glyph for, ignoring the checkboxes below.</label>
      </div>
      <div id="${id('grid')}" style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; margin: 8px 0;"></div>
      <div class="path-field" style="margin-bottom: 8px;">
        <span class="field-label">Extra characters</span>
        <input type="text" class="path-input" id="${id('custom')}" style="flex:1;">
        <button type="button" class="btn" id="${id('useonly')}">Use only this text</button>
      </div>
      <div id="${id('alphabets')}"></div>
    `;
    const els = {};
    container.querySelectorAll('[id]').forEach((el) => { els[el.id] = el; });
    const all = container.querySelector(`#${id('all')}`);
    const custom = container.querySelector(`#${id('custom')}`);
    const useOnly = container.querySelector(`#${id('useonly')}`);
    const gridEl = container.querySelector(`#${id('grid')}`);
    const alphaEl = container.querySelector(`#${id('alphabets')}`);

    gridEl.innerHTML = ASCII_BOXES.map(([key, label, checked]) => `
      <span class="checkbox-row"><input type="checkbox" class="cs-ascii" data-key="${key}" id="${id('ascii_' + key)}" ${checked ? 'checked' : ''}>
      <label for="${id('ascii_' + key)}">${esc(label)}</label></span>
    `).join('');
    const asciiBoxes = Array.from(container.querySelectorAll('.cs-ascii'));

    const alphabetState = {}; // script -> Set(labels)
    const allHanState = new Set();
    let alphaCheckboxEls = [];
    let scripts = [];

    function setEnabled(enabled) {
      [...asciiBoxes, custom, ...alphaCheckboxEls].forEach((el) => { el.disabled = !enabled; });
    }
    all.addEventListener('change', () => { setEnabled(!all.checked); onChange(); });
    asciiBoxes.forEach((cb) => cb.addEventListener('change', onChange));
    custom.addEventListener('input', onChange);
    useOnly.addEventListener('click', () => {
      const text = custom.value;
      all.checked = false;
      asciiBoxes.forEach((cb) => { cb.checked = false; });
      Object.values(alphabetState).forEach((set) => set.clear());
      allHanState.clear();
      alphaEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => { cb.checked = false; });
      custom.value = text;
      setEnabled(true);
      onChange();
    });

    const resp = await api.call('generator.get_alphabets', {});
    if (resp.ok) {
      scripts = resp.result.scripts;
      const regionOrder = resp.result.region_order || [];
      const cardHtml = (script) => {
        alphabetState[script.name] = new Set();
        const groupBoxes = script.groups.map((g, i) => `
          <span class="checkbox-row"><input type="checkbox" class="cs-alpha-group" data-script="${esc(script.name)}" data-label="${esc(g.label)}" id="${id('alpha_' + script.name + '_' + i)}">
          <label for="${id('alpha_' + script.name + '_' + i)}">${esc(g.label)} (${g.count})</label></span>`).join('');
        const hanBox = script.no_alphabet ? `
          <div class="checkbox-row"><input type="checkbox" class="cs-alpha-han" data-script="${esc(script.name)}" id="${id('han_' + script.name)}">
          <label for="${id('han_' + script.name)}">All Han ideographs supported by this font (advanced)</label></div>` : '';
        const caveat = script.caveat ? `<div class="field-hint" style="color: var(--warn);">${esc(script.caveat)}</div>` : '';
        const noAlphaHint = script.no_alphabet ? `<div class="field-hint">Chinese has no small complete alphabet. These are bounded test sets; for a usable pack, paste the exact Chinese text you need above.</div>` : '';
        const title = script.native_name ? `${esc(script.native_name)} (${esc(script.name)})` : esc(script.name);
        return `
          <div class="gen-alphabet-group">
            <div class="gen-alphabet-title">${title}</div>
            <div>${groupBoxes}</div>
            ${hanBox}
            ${caveat}
            ${noAlphaHint}
            <button type="button" class="btn cs-select-only-script" data-script="${esc(script.name)}" style="margin-top:6px;">Select only ${esc(script.name)}</button>
          </div>`;
      };
      const regions = regionOrder.length ? regionOrder : [...new Set(scripts.map((s) => s.region))];
      alphaEl.innerHTML = regions.map((region) => {
        const regionScripts = scripts.filter((s) => s.region === region);
        if (!regionScripts.length) return '';
        return `
          <div class="gen-region-title">${esc(region)}</div>
          <div class="gen-alphabet-grid">${regionScripts.map(cardHtml).join('')}</div>`;
      }).join('');
      alphaCheckboxEls = Array.from(alphaEl.querySelectorAll('.cs-alpha-group, .cs-alpha-han'));
      alphaEl.querySelectorAll('.cs-alpha-group').forEach((cb) => {
        cb.addEventListener('change', () => {
          const set = alphabetState[cb.dataset.script];
          if (cb.checked) set.add(cb.dataset.label); else set.delete(cb.dataset.label);
          onChange();
        });
      });
      alphaEl.querySelectorAll('.cs-alpha-han').forEach((cb) => {
        cb.addEventListener('change', () => {
          if (cb.checked) allHanState.add(cb.dataset.script); else allHanState.delete(cb.dataset.script);
          onChange();
        });
      });
      alphaEl.querySelectorAll('.cs-select-only-script').forEach((btn) => {
        btn.addEventListener('click', () => {
          all.checked = false;
          asciiBoxes.forEach((cb) => { cb.checked = false; });
          custom.value = '';
          Object.values(alphabetState).forEach((set) => set.clear());
          allHanState.clear();
          alphaEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => { cb.checked = false; });
          alphabetState[btn.dataset.script] = new Set(
            scripts.find((s) => s.name === btn.dataset.script).groups.map((g) => g.label));
          alphaEl.querySelectorAll(`.cs-alpha-group[data-script="${CSS.escape(btn.dataset.script)}"]`)
            .forEach((cb) => { cb.checked = true; });
          setEnabled(true);
          onChange();
        });
      });
    }

    function getSelection() {
      const byKey = {};
      asciiBoxes.forEach((cb) => { byKey[cb.dataset.key] = cb.checked; });
      return {
        all: all.checked,
        upper: byKey.upper, lower: byKey.lower, digits: byKey.digits,
        punct: byKey.punct, symbols: byKey.symbols, private: byKey.private,
        custom: custom.value,
        alphabets: Object.fromEntries(Object.entries(alphabetState).map(([k, v]) => [k, Array.from(v)])),
        all_han: Array.from(allHanState),
      };
    }

    return { getSelection };
  }

  return { create };
})();
