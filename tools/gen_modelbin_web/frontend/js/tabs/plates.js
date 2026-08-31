// License Plates tab: browse a plate standard, fill in its fields, watch a
// live preview, and generate ordinary Forza Writer shapes from it. Mirrors
// tools/gen_modelbin_gui/tabs/plates.py -- the drill-down browser
// resolution (auto-skipping a grouping level with only one distinct
// value), breadcrumb, and Back history-stack are all ported behaviorally;
// see handlers/plates.py's module docstring for the (small, called-out)
// UI simplifications.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  const debounceTimers = {};
  function debounce(key, ms, fn) {
    clearTimeout(debounceTimers[key]);
    debounceTimers[key] = setTimeout(fn, ms);
  }

  async function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">License Plates</h2>
      <div class="intro-text">
        Pick a plate standard, fill in its fields, and watch the preview update live. Generate writes
        ordinary Forza Writer shapes -- the same output every other tab produces.
      </div>

      <div class="section" style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;">
        <div class="pl-library-row" id="plLibraryRow"></div>
        <div class="path-field" style="margin-bottom:0;">
          <select class="path-input" id="plConfigSelect" style="max-width:180px;"></select>
          <button type="button" class="btn" id="plConfigLoad">Load</button>
          <button type="button" class="btn danger" id="plConfigDelete">Delete</button>
        </div>
      </div>

      <div class="pl-breadcrumb" id="plBreadcrumb"></div>

      <div class="pl-columns">
        <div class="section" style="margin-bottom:0;">
          <div class="section-title">Browse</div>
          <input type="text" class="path-input" id="plSearch" placeholder="Search..." style="margin-bottom:8px;">
          <div class="list-box pl-browser-list" id="plBrowserList"></div>
          <button type="button" class="btn" id="plDetailsBtn" style="margin-top:8px; width:100%;">Details…</button>
        </div>

        <div class="section" style="margin-bottom:0;">
          <div class="section-title">Preview</div>
          <div class="pl-preview-panel" id="plPreviewPanel"><div class="gi-diff-empty"></div></div>
          <div class="field-hint" id="plShapeCount" style="margin-top:8px;">Pick a plate to preview it here.</div>
        </div>

        <div class="section" style="margin-bottom:0;">
          <div id="plModeSection" style="display:none;">
            <div class="section-title">Plate Rules</div>
            <div class="pl-mode-row">
              <label><input type="radio" name="plMode" value="authentic" checked> <span id="plModeBaselineLabel">Authentic</span></label>
              <label><input type="radio" name="plMode" value="vanity"> Customized</label>
            </div>
            <div class="field-hint" id="plVanityBadge" style="display:none; color: var(--warn);">Customized -- not regulation-compliant</div>
          </div>

          <div class="section-title" style="margin-top: 14px;">Placeholder Font</div>
          <div class="pl-font-picker" id="plFontPicker">
            <button type="button" class="path-input pl-font-trigger" id="plFontTrigger">
              <img class="pl-font-thumb" id="plFontTriggerThumb" style="display:none;" alt="">
              <span id="plFontTriggerLabel">Boxes (no letterforms)</span>
              <span class="pl-font-chevron">▾</span>
            </button>
            <div class="pl-font-dropdown" id="plFontDropdown" style="display:none;"></div>
          </div>
          <div class="field-hint" id="plFontRealHint" style="display:none; margin-bottom: 8px;">
            Showing plain boxes, not real letterforms -- set KFPS's executable path in Settings to see each
            font's actual shape here.
          </div>

          <div class="section-title">Plate Settings</div>
          <div id="plFieldsBody"><div class="field-hint">Select a plate from the browser to begin.</div></div>
        </div>
      </div>

      <div class="section" style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
        <button type="button" class="btn" id="plSaveConfig">Save Current…</button>
        <div style="flex:1;"></div>
        <button type="button" class="btn" id="plSendKfps" disabled>Send to KFPS</button>
        <button type="button" class="btn accent" id="plGenerate">Generate Plate</button>
      </div>
      <div class="field-hint" id="plGenerateStatus"></div>
    `;

    const api = window.pywebview.api;
    const els = {};
    container.querySelectorAll('[id]').forEach((el) => { els[el.id] = el; });

    let libraries = [];
    let library = 'real';
    let search = '';
    let breadcrumb = []; // [[level_index, key], ...]
    let navHistory = [];
    let lastTrail = [];
    let lastLeavesSingle = false;
    let selectedTemplateId = null;
    let templateDetail = null;
    let fieldValues = {};
    let mode = 'authentic';
    let placeholderFont = 0;
    let lastGeneratedPath = null;

    // -- library selector -----------------------------------------------------
    function renderLibraryButtons() {
      els.plLibraryRow.innerHTML = libraries.map((lib) =>
        `<button type="button" class="btn ${lib.key === library ? 'active' : ''}" data-lib="${esc(lib.key)}">${esc(lib.label)}</button>`
      ).join('');
      els.plLibraryRow.querySelectorAll('button').forEach((btn) => {
        btn.addEventListener('click', () => setLibrary(btn.dataset.lib));
      });
    }
    function setLibrary(lib) {
      if (lib === library) return;
      pushHistory();
      library = lib;
      breadcrumb = [];
      search = '';
      els.plSearch.value = '';
      clearSelection();
      renderLibraryButtons();
      refreshBrowser();
    }

    // -- browser / breadcrumb ---------------------------------------------------
    function snapshot() {
      return { library, breadcrumb: breadcrumb.map((p) => [...p]), search, templateId: selectedTemplateId };
    }
    function pushHistory() {
      navHistory.push(snapshot());
      if (navHistory.length > 50) navHistory.shift();
    }
    function renderBreadcrumb() {
      const rootLabel = (libraries.find((l) => l.key === library) || {}).label || library;
      const isRootCurrent = lastTrail.length === 0 && selectedTemplateId === null;
      let html = `<button type="button" class="btn" id="plBackBtn" ${navHistory.length ? '' : 'disabled'} style="margin-right:6px;">‹ Back</button>`;
      html += `<span class="crumb ${isRootCurrent ? 'current' : ''}" data-jump="root">${esc(rootLabel)}</span>`;
      lastTrail.forEach((entry, i) => {
        const isLast = i === lastTrail.length - 1 && selectedTemplateId === null;
        html += `<span class="sep">›</span><span class="crumb ${isLast ? 'current' : ''}" data-jump="${entry.level_index}">${esc(entry.label)}</span>`;
      });
      if (selectedTemplateId !== null && templateDetail) {
        html += `<span class="sep">›</span><span class="crumb current">${esc(templateDetail.display_name)}</span>`;
      }
      els.plBreadcrumb.innerHTML = html;
      const backBtn = els.plBreadcrumb.querySelector('#plBackBtn');
      if (backBtn) backBtn.addEventListener('click', goBack);
      els.plBreadcrumb.querySelectorAll('.crumb:not(.current)').forEach((crumb) => {
        crumb.addEventListener('click', () => breadcrumbJump(crumb.dataset.jump === 'root' ? null : parseInt(crumb.dataset.jump, 10)));
      });
    }
    function breadcrumbJump(levelIndex) {
      pushHistory();
      breadcrumb = levelIndex === null ? [] : breadcrumb.filter(([li]) => li < levelIndex);
      clearSelection();
      refreshBrowser();
    }
    function goBack() {
      if (!navHistory.length) return;
      const snap = navHistory.pop();
      library = snap.library;
      breadcrumb = snap.breadcrumb;
      search = snap.search;
      els.plSearch.value = search;
      renderLibraryButtons();
      refreshBrowser().then(() => {
        if (snap.templateId) selectTemplate(snap.templateId); else clearSelection();
      });
    }

    async function refreshBrowser() {
      const resp = await api.call('plates.browse', { library, search, breadcrumb });
      if (!resp.ok) return;
      lastTrail = resp.result.trail;
      const listEl = els.plBrowserList;
      if (resp.result.mode === 'empty') {
        listEl.innerHTML = `<div class="list-empty">${resp.result.empty_reason === 'empty_community'
          ? 'No community plate kits yet. Credited, imported community work will appear here once added.'
          : 'No plates match your search in this library.'}</div>`;
        lastLeavesSingle = false;
      } else if (resp.result.mode === 'groups') {
        listEl.innerHTML = resp.result.items.map((item) =>
          `<div class="list-row" data-group="${esc(item.key)}">${esc(item.label)}  (${item.count})</div>`).join('');
        listEl.querySelectorAll('.list-row').forEach((row) => {
          row.addEventListener('click', () => {
            pushHistory();
            breadcrumb = [...breadcrumb, [lastTrail.length, row.dataset.group]];
            refreshBrowser();
          });
        });
        lastLeavesSingle = false;
      } else {
        lastLeavesSingle = resp.result.single;
        listEl.innerHTML = resp.result.items.map((item) =>
          `<div class="list-row ${item.template_id === selectedTemplateId ? 'active' : ''}" data-template="${esc(item.template_id)}">${esc(item.label)}  [${esc(item.era)}]</div>`).join('');
        listEl.querySelectorAll('.list-row').forEach((row) => {
          row.addEventListener('click', () => {
            if (!lastLeavesSingle) pushHistory();
            selectTemplate(row.dataset.template);
          });
        });
      }
      renderBreadcrumb();
    }
    els.plSearch.addEventListener('input', () => {
      search = els.plSearch.value;
      debounce('pl_search', 200, refreshBrowser);
    });
    els.plDetailsBtn.addEventListener('click', () => {
      if (selectedTemplateId) api.call('plates.show_details', { template_id: selectedTemplateId });
    });

    // -- selection / fields -----------------------------------------------------
    function clearSelection() {
      selectedTemplateId = null;
      templateDetail = null;
      fieldValues = {};
      els.plFieldsBody.innerHTML = '<div class="field-hint">Select a plate from the browser to begin.</div>';
      els.plModeSection.style.display = 'none';
      els.plPreviewPanel.innerHTML = '<div class="gi-diff-empty"></div>';
      els.plShapeCount.textContent = 'Pick a plate to preview it here.';
      forgetLastGenerated();
      renderBreadcrumb();
    }
    function forgetLastGenerated() {
      lastGeneratedPath = null;
      els.plSendKfps.disabled = true;
    }

    async function selectTemplate(templateId) {
      forgetLastGenerated();
      const resp = await api.call('plates.get_template', { template_id: templateId });
      if (!resp.ok) { els.plGenerateStatus.textContent = resp.error; return; }
      selectedTemplateId = templateId;
      templateDetail = resp.result;

      if (templateDetail.mode_baseline_label) {
        els.plModeBaselineLabel.textContent = templateDetail.mode_baseline_label;
        els.plModeSection.style.display = '';
        mode = 'authentic';
      } else {
        els.plModeSection.style.display = 'none';
        mode = 'vanity';
      }
      container.querySelector(`input[name="plMode"][value="${mode}"]`).checked = true;
      onModeChanged(false);

      fieldValues = {};
      els.plFieldsBody.innerHTML = templateDetail.field_groups.map((group) => `
        ${templateDetail.show_group_headers ? `<div class="pl-field-group-title">${esc(group.group)}</div>` : ''}
        ${group.fields.map((f) => {
          fieldValues[f.field_id] = f.default_text;
          return `
          <div class="pl-field-row" data-field="${esc(f.field_id)}">
            <label>${esc(f.label)}</label>
            <input type="text" class="path-input pl-field-input" data-field="${esc(f.field_id)}" value="${esc(f.default_text)}">
            <div class="pl-field-hint" style="display:none;"></div>
          </div>`;
        }).join('')}
      `).join('');
      els.plFieldsBody.querySelectorAll('.pl-field-input').forEach((input) => {
        input.addEventListener('input', () => {
          fieldValues[input.dataset.field] = input.value;
          debounce('pl_validate', 150, refreshValidation);
          debounce('pl_preview', 350, renderPreview);
        });
      });

      renderBreadcrumb();
      refreshValidation();
      renderPreview();
    }

    function onModeChanged(reschedule = true) {
      els.plVanityBadge.style.display = mode === 'vanity' ? '' : 'none';
      if (reschedule) { refreshValidation(); renderPreview(); }
    }
    container.querySelectorAll('input[name="plMode"]').forEach((radio) => {
      radio.addEventListener('change', () => {
        mode = container.querySelector('input[name="plMode"]:checked').value;
        onModeChanged();
      });
    });

    async function refreshValidation() {
      if (!selectedTemplateId) return;
      const resp = await api.call('plates.validate', { template_id: selectedTemplateId, mode, field_values: fieldValues });
      els.plFieldsBody.querySelectorAll('.pl-field-hint').forEach((hint) => { hint.style.display = 'none'; hint.textContent = ''; });
      if (!resp.ok) return;
      resp.result.errors.forEach((err) => {
        const row = els.plFieldsBody.querySelector(`.pl-field-row[data-field="${CSS.escape(err.field_id)}"] .pl-field-hint`);
        if (row) {
          row.textContent = `${err.reason}\nExpected format: ${err.format_hint}`;
          row.style.display = '';
        }
      });
    }

    async function renderPreview() {
      if (!selectedTemplateId) return;
      els.plShapeCount.textContent = 'Rendering…';
      const rect = els.plPreviewPanel.getBoundingClientRect();
      const resp = await api.call('plates.preview', {
        template_id: selectedTemplateId, mode, field_values: fieldValues, placeholder_font: placeholderFont,
        width: Math.round(rect.width), height: Math.round(rect.height),
      });
      if (!resp.ok) {
        els.plShapeCount.textContent = 'Pick a plate to preview it here.';
        els.plGenerateStatus.textContent = `Couldn't generate this plate: ${resp.error}`;
        return;
      }
      els.plPreviewPanel.innerHTML = `<img src="${resp.result.preview_image}" alt="Plate preview">`;
      let status = resp.result.over_threshold
        ? `~${resp.result.shape_count} shapes -- this exceeds the usual budget (${resp.result.threshold}) and may be slow or unstable in-game.`
        : `~${resp.result.shape_count} shapes`;
      if (resp.result.font_not_shown) {
        status += "  (showing boxes -- set KFPS's executable path in Settings to preview this font's real letterforms here)";
      }
      els.plShapeCount.textContent = status;
      els.plGenerateStatus.textContent = resp.result.warnings.join(' / ');
    }

    // -- placeholder font (custom picker: a plain <select> can't show images) -----
    let placeholderFonts = []; // [{value, label, sample_image?}, ...]
    function setPlaceholderFont(value) {
      placeholderFont = value;
      const font = placeholderFonts.find((f) => f.value === value);
      els.plFontTriggerLabel.textContent = font ? font.label : 'Boxes (no letterforms)';
      if (font && font.sample_image) {
        els.plFontTriggerThumb.src = font.sample_image;
        els.plFontTriggerThumb.style.display = '';
      } else {
        els.plFontTriggerThumb.style.display = 'none';
      }
      els.plFontDropdown.querySelectorAll('.pl-font-row').forEach((row) => {
        row.classList.toggle('active', parseInt(row.dataset.value, 10) === value);
      });
    }
    function renderFontDropdown() {
      els.plFontDropdown.innerHTML = placeholderFonts.map((f) => `
        <div class="pl-font-row ${f.value === placeholderFont ? 'active' : ''}" data-value="${f.value}">
          ${f.sample_image ? `<img class="pl-font-thumb" src="${f.sample_image}" alt="">`
            : '<div class="pl-font-thumb pl-font-thumb-empty"></div>'}
          <span>${esc(f.label)}</span>
        </div>`).join('');
      els.plFontDropdown.querySelectorAll('.pl-font-row').forEach((row) => {
        row.addEventListener('click', () => {
          setPlaceholderFont(parseInt(row.dataset.value, 10));
          els.plFontDropdown.style.display = 'none';
          renderPreview();
        });
      });
    }
    els.plFontTrigger.addEventListener('click', () => {
      const showing = els.plFontDropdown.style.display !== 'none';
      els.plFontDropdown.style.display = showing ? 'none' : '';
    });
    const onDocumentClickCloseFontDropdown = (e) => {
      if (!els.plFontPicker.contains(e.target)) els.plFontDropdown.style.display = 'none';
    };
    document.addEventListener('click', onDocumentClickCloseFontDropdown);

    // -- generate / send to KFPS ---------------------------------------------------
    els.plGenerate.addEventListener('click', async () => {
      if (!selectedTemplateId) return;
      els.plGenerate.disabled = true;
      els.plGenerateStatus.textContent = 'Rendering…';
      let resp = await api.call('plates.generate', {
        template_id: selectedTemplateId, mode, field_values: fieldValues, placeholder_font: placeholderFont,
      });
      if (resp.ok && resp.result.needs_confirm) {
        const proceed = window.confirm(
          `This plate is estimated at ~${resp.result.shape_count} shapes, above the usual budget of `
          + `${resp.result.threshold}. Generate anyway?`);
        if (!proceed) {
          els.plGenerate.disabled = false;
          els.plGenerateStatus.textContent = '';
          return;
        }
        resp = await api.call('plates.generate', {
          template_id: selectedTemplateId, mode, field_values: fieldValues, placeholder_font: placeholderFont,
          confirmed: true,
        });
      }
      els.plGenerate.disabled = false;
      if (!resp.ok) { els.plGenerateStatus.textContent = `Couldn't generate this plate: ${resp.error}`; return; }
      els.plGenerateStatus.textContent = `Generated ${resp.result.shape_count} shapes -> ${resp.result.path}`;
      lastGeneratedPath = resp.result.path;
      els.plSendKfps.disabled = false;
    });
    els.plSendKfps.addEventListener('click', async () => {
      if (!lastGeneratedPath) { els.plGenerateStatus.textContent = 'Generate a plate first, then Send to KFPS.'; return; }
      const resp = await api.call('plates.send_to_kfps', { json_path: lastGeneratedPath });
      els.plGenerateStatus.textContent = resp.ok ? `Sent ${resp.result.path} to KFPS.` : resp.error;
    });

    // -- saved configs -------------------------------------------------------------
    async function refreshConfigList() {
      const resp = await api.call('plates.list_configs', {});
      if (!resp.ok) return;
      els.plConfigSelect.innerHTML = resp.result.names.length
        ? resp.result.names.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join('')
        : '<option value="">No saved configurations</option>';
    }
    els.plSaveConfig.addEventListener('click', async () => {
      if (!selectedTemplateId) return;
      const name = window.prompt('Name for this saved configuration:');
      if (!name) return;
      const resp = await api.call('plates.save_config', {
        name, template_id: selectedTemplateId, mode, field_values: fieldValues, placeholder_font: placeholderFont,
      });
      if (resp.ok) refreshConfigList();
    });
    els.plConfigLoad.addEventListener('click', async () => {
      const name = els.plConfigSelect.value;
      if (!name) return;
      const resp = await api.call('plates.load_config', { name });
      if (!resp.ok || !resp.result.found) { els.plGenerateStatus.textContent = 'No saved configurations yet.'; return; }
      pushHistory();
      await jumpToTemplate(resp.result.template_id);
      mode = resp.result.mode;
      container.querySelector(`input[name="plMode"][value="${mode}"]`).checked = true;
      onModeChanged(false);
      setPlaceholderFont(resp.result.placeholder_font || 0);
      Object.entries(resp.result.field_values).forEach(([fieldId, value]) => {
        fieldValues[fieldId] = value;
        const input = els.plFieldsBody.querySelector(`.pl-field-input[data-field="${CSS.escape(fieldId)}"]`);
        if (input) input.value = value;
      });
      refreshValidation();
      renderPreview();
    });
    els.plConfigDelete.addEventListener('click', async () => {
      const name = els.plConfigSelect.value;
      if (!name) return;
      const resp = await api.call('plates.delete_config', { name });
      if (resp.ok) refreshConfigList();
    });

    async function jumpToTemplate(templateId) {
      // Mirrors _plates_jump_to_template: sets library/breadcrumb so the
      // browser's state is consistent with templateId, regardless of
      // where the browser currently is, then selects it.
      const probe = await api.call('plates.get_template', { template_id: templateId });
      if (!probe.ok) return;
      library = probe.result.library;
      breadcrumb = probe.result.default_breadcrumb;
      search = '';
      els.plSearch.value = '';
      renderLibraryButtons();
      await refreshBrowser();
      await selectTemplate(templateId);
    }

    // -- initial load -----------------------------------------------------------
    const [libResp, fontResp] = await Promise.all([
      api.call('plates.get_libraries', {}),
      api.call('plates.get_placeholder_fonts', {}),
    ]);
    if (libResp.ok) libraries = libResp.result.libraries;
    if (fontResp.ok) {
      placeholderFonts = fontResp.result.fonts;
      els.plFontRealHint.style.display = fontResp.result.has_real_letterforms ? 'none' : '';
      renderFontDropdown();
      setPlaceholderFont(0);
    }
    renderLibraryButtons();
    await refreshConfigList();
    await refreshBrowser();

    return () => { document.removeEventListener('click', onDocumentClickCloseFontDropdown); };
  }

  window.ForzaTabs.plates = mount;
})();
