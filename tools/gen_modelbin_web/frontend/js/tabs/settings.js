// Settings tab: paths, appearance (palette/density), compute backend, and
// generated-data cleanup. Palette switching here is the load-bearing part
// of this tab per the migration plan -- it's what every other future tab
// depends on for live theming.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  const DETECTABLE_KEYS = { reference_modelbin: 'FH6 install', kfps_executable: 'KFPS install' };

  function pathFieldHtml(field) {
    const detectable = DETECTABLE_KEYS[field.key];
    return `
      <div class="field-row" data-key="${field.key}">
        <div class="field-label">${esc(field.label)}</div>
        <div class="path-field">
          <input type="text" class="path-input" value="${esc(field.value)}">
          ${detectable ? `<button type="button" class="btn detect-btn">Detect</button>` : ''}
          <button type="button" class="btn browse-btn">Browse…</button>
        </div>
        <div class="path-status ${field.exists ? 'ok' : 'pending'}">${field.exists ? '✓ exists' : field.status}: ${esc(field.value)}</div>
        ${detectable ? `<div class="field-hint" data-detect-status></div>` : ''}
      </div>`;
  }

  async function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">Settings</h2>
      <div class="intro-text">
        Paths used across every tab. Click Save settings to persist them to disk so they survive
        restarting the tool.
      </div>

      <div class="section">
        <div class="section-title">Appearance</div>
        <div class="field-row">
          <div class="field-label">Color palette</div>
          <div class="field-hint">Eurocorp only, for now. The web app does not offer Charcoal or Slate yet.</div>
        </div>
        <div class="field-row">
          <div class="field-label">Interface density</div>
          <div class="radio-group" id="settingsDensityGroup"></div>
          <ul class="field-hint field-hint-list">
            <li>Density saves immediately and applies across every tab.</li>
          </ul>
        </div>
      </div>

      <div class="section" id="settingsPathsSection">
        <div class="section-title">Paths</div>
        <div id="settingsPathFields"></div>
        <div class="checkbox-row">
          <input type="checkbox" id="settingsSaveSource">
          <label for="settingsSaveSource">Save source image alongside output</label>
        </div>
        <div class="checkbox-row">
          <input type="checkbox" id="settingsSaveDebug">
          <label for="settingsSaveDebug">Save generation debug image and diagnostics</label>
        </div>
        <div class="field-row">
          <div class="field-label">Debug view</div>
          <select class="path-input" id="settingsDebugMode" style="max-width: 280px;"></select>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Generation Processor</div>
        <div class="radio-group" id="settingsBackendGroup">
          <label><input type="radio" name="settingsBackend" value="auto" checked> Auto (prefer NVIDIA CUDA)</label>
          <label><input type="radio" name="settingsBackend" value="cuda"> NVIDIA CUDA</label>
          <label><input type="radio" name="settingsBackend" value="directml"> AMD DirectML (Experimental)</label>
          <label><input type="radio" name="settingsBackend" value="cpu"> CPU</label>
        </div>
        <div class="field-hint" id="settingsBackendStatus" style="margin-top: 8px;"></div>
      </div>

      <div class="field-row">
        <div>
          <button type="button" class="btn accent" id="settingsSaveBtn">Save settings</button>
          <span class="field-hint" id="settingsSavedStatus"></span>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Generated Data</div>
        <div id="settingsCleanupRows"></div>
        <div class="field-row" style="flex-direction: row; gap: 8px; margin-top: 10px;">
          <button type="button" class="btn" id="settingsSelectAll">Select All</button>
          <button type="button" class="btn" id="settingsSelectNone">Select None</button>
          <button type="button" class="btn" id="settingsRefreshSizes">Refresh sizes</button>
        </div>
        <div class="field-row" style="flex-direction: row; align-items: center; gap: 8px; margin-top: 10px;">
          <button type="button" class="btn danger" id="settingsCleanBtn">Clean generated data…</button>
          <span class="field-hint" id="settingsCleanupStatus"></span>
        </div>
        <div class="field-hint" style="margin-top: 8px;">
          Only checked categories are cleared. Settings, per-glyph overrides, source fonts,
          reference modelbins, and custom external output folders are always preserved.
        </div>
      </div>
    `;

    const api = window.pywebview.api;

    // -- Appearance ---------------------------------------------------
    // Palette is locked to Eurocorp in the web app for now (see shell.js).
    // This intentionally never calls settings.set_appearance with a
    // palette value, so the shared setting the Tkinter app reads stays
    // whatever the user already has it set to there.
    const appearance = await api.call('settings.get_appearance', {});
    if (appearance.ok) {
      const { densities, current } = appearance.result;
      const densityGroup = container.querySelector('#settingsDensityGroup');
      densityGroup.innerHTML = densities.map((d) => `
        <label><input type="radio" name="settingsDensity" value="${d.id}" ${d.id === current.density ? 'checked' : ''}> ${esc(d.label)}</label>
      `).join('');
      densityGroup.addEventListener('change', async () => {
        const density = densityGroup.querySelector('input:checked').value;
        document.documentElement.dataset.density = density;
        await api.call('settings.set_density', { density });
      });
    }

    // -- Paths ----------------------------------------------------------
    const pathsResp = await api.call('settings.get_paths', {});
    if (pathsResp.ok) {
      const { fields, image_save_source, image_save_debug, image_debug_mode, image_debug_labels } = pathsResp.result;
      container.querySelector('#settingsPathFields').innerHTML = fields.map(pathFieldHtml).join('');
      container.querySelector('#settingsSaveSource').checked = !!image_save_source;
      container.querySelector('#settingsSaveDebug').checked = !!image_save_debug;
      const debugSelect = container.querySelector('#settingsDebugMode');
      debugSelect.innerHTML = Object.entries(image_debug_labels).map(([key, label]) =>
        `<option value="${esc(key)}" ${key === image_debug_mode ? 'selected' : ''}>${esc(label)}</option>`
      ).join('');

      container.querySelectorAll('.browse-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const row = btn.closest('.field-row');
          const key = row.dataset.key;
          const input = row.querySelector('.path-input');
          const kind = key === 'kfps_executable' ? 'kfps'
            : key === 'reference_modelbin' ? 'file' : 'directory';
          const resp = await api.call('settings.browse', { kind, initial: input.value });
          if (resp.ok && !resp.result.cancelled) input.value = resp.result.path;
        });
      });

      const DETECT_HANDLERS = {
        reference_modelbin: 'settings.detect_reference_modelbin',
        kfps_executable: 'settings.detect_kfps_executable',
      };
      container.querySelectorAll('.detect-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const row = btn.closest('.field-row');
          const key = row.dataset.key;
          const input = row.querySelector('.path-input');
          const statusEl = row.querySelector('[data-detect-status]');
          btn.disabled = true;
          statusEl.textContent = 'Searching…';
          const resp = await api.call(DETECT_HANDLERS[key], {});
          btn.disabled = false;
          if (resp.ok && resp.result.found) {
            input.value = resp.result.path;
            statusEl.textContent = resp.result.message || `Found: ${resp.result.path}`;
          } else {
            statusEl.textContent = (resp.ok ? resp.result.message : resp.error) || 'Not found.';
            // Detection is inherently best-effort (everyone's install lives
            // somewhere different) -- fall straight into the manual picker
            // instead of making the user notice and click Browse separately.
            row.querySelector('.browse-btn').click();
          }
        });
      });
    }

    // -- Compute backend --------------------------------------------------
    async function refreshBackendStatus() {
      const requested = container.querySelector('input[name="settingsBackend"]:checked').value;
      const resp = await api.call('settings.get_compute_backend', { requested });
      container.querySelector('#settingsBackendStatus').textContent = resp.ok ? resp.result.text : resp.error;
    }
    container.querySelector('#settingsBackendGroup').addEventListener('change', async () => {
      const requested = container.querySelector('input[name="settingsBackend"]:checked').value;
      await api.call('settings.save_compute_backend', { requested });
      refreshBackendStatus();
    });
    refreshBackendStatus();

    // -- Save settings ----------------------------------------------------
    container.querySelector('#settingsSaveBtn').addEventListener('click', async () => {
      const get = (key) => container.querySelector(`.field-row[data-key="${key}"] .path-input`).value;
      const resp = await api.call('settings.save_paths', {
        reference_modelbin: get('reference_modelbin'),
        kfps_executable: get('kfps_executable'),
        output_dir: get('output_dir'),
        modelbin_output_dir: get('modelbin_output_dir'),
        direct_output_dir: get('direct_output_dir'),
        image_output_dir: get('image_output_dir'),
        image_save_source: container.querySelector('#settingsSaveSource').checked,
        image_save_debug: container.querySelector('#settingsSaveDebug').checked,
        image_debug_mode: container.querySelector('#settingsDebugMode').value,
      });
      container.querySelector('#settingsSavedStatus').textContent = resp.ok ? 'Saved.' : resp.error;
    });

    // -- Generated data cleanup -------------------------------------------
    let pendingCleanupGeneration = null;
    const cleanupResp = await api.call('settings.refresh_cleanup_sizes', {});
    let cleanupTargets = [];
    if (cleanupResp.ok) {
      cleanupTargets = cleanupResp.result.targets;
      pendingCleanupGeneration = cleanupResp.result.generation;
      container.querySelector('#settingsCleanupRows').innerHTML = cleanupTargets.map((t) => `
        <div class="cleanup-row" data-key="${t.key}">
          <div class="checkbox-row" style="margin: 0;">
            <input type="checkbox" id="cleanup_${t.key}">
            <label for="cleanup_${t.key}">${esc(t.label)}<br><span class="field-hint">${esc(t.description)}</span></label>
          </div>
          <span class="size" id="cleanupSize_${t.key}">Calculating…</span>
        </div>
      `).join('');
    }

    const offCleanupSizes = window.__forzaEvents.on('settings_cleanup_sizes_ready', (generation, payload) => {
      if (generation !== pendingCleanupGeneration) return;
      Object.entries(payload.sizes).forEach(([key, { files, bytes }]) => {
        const el = container.querySelector(`#cleanupSize_${key}`);
        if (el) el.textContent = `${files.toLocaleString()} file(s), ${(bytes / (1024 * 1024)).toFixed(1)} MB`;
      });
    });

    container.querySelector('#settingsSelectAll').addEventListener('click', () => {
      container.querySelectorAll('#settingsCleanupRows input[type="checkbox"]').forEach((cb) => { cb.checked = true; });
    });
    container.querySelector('#settingsSelectNone').addEventListener('click', () => {
      container.querySelectorAll('#settingsCleanupRows input[type="checkbox"]').forEach((cb) => { cb.checked = false; });
    });
    container.querySelector('#settingsRefreshSizes').addEventListener('click', async () => {
      container.querySelectorAll('.size').forEach((el) => { el.textContent = 'Calculating…'; });
      const resp = await api.call('settings.refresh_cleanup_sizes', {});
      if (resp.ok) pendingCleanupGeneration = resp.result.generation;
    });

    container.querySelector('#settingsCleanBtn').addEventListener('click', async () => {
      const runningResp = await api.call('settings.is_generation_running', {});
      if (runningResp.ok && runningResp.result.running) {
        alert('Generation in progress. Wait for the current generation job to finish before cleaning data.');
        return;
      }
      const selected = cleanupTargets
        .filter((t) => container.querySelector(`#cleanup_${t.key}`).checked)
        .map((t) => t.key);
      if (selected.length === 0) {
        alert('Select at least one output or cache category to clear.');
        return;
      }
      if (!confirm(`This will permanently remove the selected generated file(s) from ${selected.length} categor${selected.length === 1 ? 'y' : 'ies'}. Continue?`)) return;
      if (!confirm('Are you absolutely sure? This cannot be undone from Forza Writer.\n\nYour settings, source files, reference modelbins, and custom external folders will remain.')) return;

      const statusEl = container.querySelector('#settingsCleanupStatus');
      statusEl.textContent = 'Cleaning…';
      const resp = await api.call('settings.clean_generated_data', { selected });
      if (!resp.ok) { statusEl.textContent = resp.error; return; }
      statusEl.textContent = `Clean slate ready, removed ${resp.result.files.toLocaleString()} file(s), ${(resp.result.bytes / (1024 * 1024)).toFixed(1)} MB.`;
      container.querySelector('#settingsRefreshSizes').click();
    });

    return () => { offCleanupSizes(); };
  }

  window.ForzaTabs.settings = mount;
})();
