// Shared vinyl-shape generation-policy UI (the Generator tab's "Vinyl
// Shapes" section): preset select, the primitive-shape tile grid
// (allow/prefer, rendered server-side via vinyl_tiles.render_tile),
// fallback mode, and exact-cover toggle. Used by both Generator and
// Advanced Generator -- Tkinter's own Advanced Generator has no policy UI
// of its own and silently inherits whatever Generator's live controls
// say (_start_generation reads self._current_generation_policy()
// internally). The web app has no such shared live Tk-variable object, so
// each tab that can generate gets its own instance of this component
// instead, backed by the same generator.get_policy_defaults/
// render_shape_tile/validate_policy handlers Generator itself uses --
// same policy engine and same starting defaults, just not a single
// literal shared widget.
window.ForzaVinylShapes = (function () {
  const TILE_W = 104, TILE_H = 86, BADGE_CX = TILE_W - 13, BADGE_CY = 13, BADGE_HIT_R = 10;

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  // options: { onChange(policy, valid) }
  async function create(container, options = {}) {
    const api = window.pywebview.api;
    const onChange = options.onChange || (() => {});

    container.innerHTML = `
      <div class="path-field" style="margin-bottom: 8px;">
        <span class="field-label">Preset</span>
        <select class="path-input vs-preset" style="max-width: 220px;"></select>
        <button type="button" class="btn vs-apply">Apply preset</button>
        <button type="button" class="btn vs-restore">Restore Recommended Defaults</button>
      </div>
      <div class="gen-shape-grid vs-grid"></div>
      <div class="field-hint">Click a tile to allow/disallow it. Click the star badge on an allowed tile to mark it preferred.</div>
      <div class="path-field" style="margin: 10px 0 8px;">
        <span class="field-label">If the selection falls short</span>
        <select class="path-input vs-fallback" style="max-width: 420px;"></select>
      </div>
      <div class="checkbox-row">
        <input type="checkbox" class="vs-exact-cover" checked>
        <label>Allow exact rectangle/stencil cover for blocky glyphs</label>
      </div>
      <div class="field-hint vs-validation" style="margin-top: 6px;"></div>
    `;
    const presetSelect = container.querySelector('.vs-preset');
    const fallbackSelect = container.querySelector('.vs-fallback');
    const exactCover = container.querySelector('.vs-exact-cover');
    const gridEl = container.querySelector('.vs-grid');
    const validationEl = container.querySelector('.vs-validation');

    let catalog = [];
    let presets = {};
    let presetLabels = {};
    let policy = null;
    const shapeState = {};

    function expandAllowed(list) { return list.length ? list : catalog.map((s) => s.id); }
    function syncShapeStateFromPolicy(p) {
      const allowed = new Set(expandAllowed(p.allowed_shapes));
      const preferred = new Set(p.preferred_shapes);
      catalog.forEach((s) => {
        shapeState[s.id] = !allowed.has(s.id) ? 'off' : (preferred.has(s.id) ? 'preferred' : 'on');
      });
    }
    async function redrawTile(shapeId) {
      const resp = await api.call('generator.render_shape_tile', { shape_id: shapeId, state: shapeState[shapeId] });
      if (!resp.ok) return;
      const img = gridEl.querySelector(`.gen-shape-tile[data-id="${CSS.escape(shapeId)}"] img`);
      if (img) img.src = resp.result.image;
    }
    function redrawAllTiles() { catalog.forEach((s) => redrawTile(s.id)); }

    function policyFromState() {
      const allowed = catalog.filter((s) => shapeState[s.id] !== 'off').map((s) => s.id);
      const preferred = catalog.filter((s) => shapeState[s.id] === 'preferred').map((s) => s.id);
      return {
        ...policy,
        allowed_shapes: allowed.length === catalog.length ? [] : allowed,
        preferred_shapes: preferred,
        fallback: fallbackSelect.value,
        allow_exact_cover: exactCover.checked,
      };
    }
    function normPolicy(p) {
      return JSON.stringify({
        allowed: [...expandAllowed(p.allowed_shapes)].sort(), preferred: [...p.preferred_shapes].sort(),
        fallback: p.fallback, allow_exact_cover: p.allow_exact_cover, max_layers: p.max_layers,
        quality_target: p.quality_target, min_gain: p.min_gain, overshoot_penalty: p.overshoot_penalty,
        preference_bonus: p.preference_bonus,
      });
    }
    function presetNameFor(p) {
      const target = normPolicy(p);
      for (const [name, preset] of Object.entries(presets)) {
        if (normPolicy(preset) === target) return presetLabels[name];
      }
      return 'Custom';
    }
    async function refreshValidation() {
      policy = policyFromState();
      const resp = await api.call('generator.validate_policy', { policy });
      if (!resp.ok) return;
      const label = presetNameFor(policy);
      const allowedCount = policy.allowed_shapes.length || catalog.length;
      let valid = resp.result.problems.length === 0;
      if (!valid) {
        validationEl.innerHTML = `<span style="color: var(--flag);">Cannot generate: ${esc(resp.result.problems.join(' '))}</span>`;
      } else {
        let summary = `${label} preset. ${allowedCount} of ${catalog.length} vinyl shapes allowed`;
        if (policy.preferred_shapes.length) summary += `, ${policy.preferred_shapes.length} preferred`;
        if (!resp.result.allows_exact_cover) summary += '. Exact rectangle/stencil cover unavailable -- every glyph goes through the shape search.';
        validationEl.textContent = summary + '.';
      }
      onChange(policy, valid);
    }
    function onTileClick(e, shapeId) {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      const hitBadge = (x - BADGE_CX) ** 2 + (y - BADGE_CY) ** 2 <= BADGE_HIT_R ** 2;
      const cur = shapeState[shapeId];
      if (cur !== 'off' && hitBadge) shapeState[shapeId] = cur === 'preferred' ? 'on' : 'preferred';
      else shapeState[shapeId] = cur === 'off' ? 'on' : 'off';
      redrawTile(shapeId);
      refreshValidation();
    }
    function applyPolicy(p) {
      policy = { ...p };
      syncShapeStateFromPolicy(policy);
      redrawAllTiles();
      fallbackSelect.value = policy.fallback;
      exactCover.checked = policy.allow_exact_cover;
      refreshValidation();
    }

    const [catResp, defResp] = await Promise.all([
      api.call('generator.get_primitive_catalog', {}),
      api.call('generator.get_policy_defaults', {}),
    ]);
    catalog = catResp.result.shapes;
    presets = defResp.result.presets;
    presetLabels = defResp.result.preset_labels;
    const fallbackLabels = defResp.result.fallback_labels;
    const recommended = defResp.result.recommended_preset;

    presetSelect.innerHTML = Object.entries(presetLabels)
      .map(([key, label]) => `<option value="${esc(key)}" ${key === recommended ? 'selected' : ''}>${esc(label)}</option>`).join('');
    fallbackSelect.innerHTML = defResp.result.fallback_modes
      .map((mode) => `<option value="${esc(mode)}">${esc(fallbackLabels[mode])}</option>`).join('');
    gridEl.innerHTML = catalog.map((s) => `
      <button type="button" class="gen-shape-tile" data-id="${esc(s.id)}" title="${esc(s.display_name)}">
        <img width="${TILE_W}" height="${TILE_H}" alt="${esc(s.display_name)}">
      </button>`).join('');
    gridEl.querySelectorAll('.gen-shape-tile').forEach((btn) => {
      btn.addEventListener('click', (e) => onTileClick(e, btn.dataset.id));
    });

    container.querySelector('.vs-apply').addEventListener('click', () => applyPolicy(presets[presetSelect.value]));
    container.querySelector('.vs-restore').addEventListener('click', () => {
      const recName = Object.keys(presetLabels).find((k) => presetLabels[k] === 'Balanced') || Object.keys(presets)[0];
      applyPolicy(presets[recName]);
      presetSelect.value = recName;
    });
    fallbackSelect.addEventListener('change', refreshValidation);
    exactCover.addEventListener('change', refreshValidation);

    applyPolicy(defResp.result.policy);

    return { getPolicy: () => policy };
  }

  return { create };
})();
