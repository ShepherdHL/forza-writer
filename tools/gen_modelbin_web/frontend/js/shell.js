// Shell wiring: sidebar nav (built from the real TABS/TAB_LABELS via
// api.get_tabs(), not a hand-duplicated list), tab switching, the Log
// panel's collapse/detach/dock controls, and the palette bootstrap from
// gui_settings. Runs once window.pywebview is ready.
(function () {
  function whenReady(fn) {
    if (window.pywebview) fn();
    else window.addEventListener('pywebviewready', fn);
  }

  // pywebview's WinForms/WebView2 backend has a startup race: the
  // js_api bridge can report ready (pywebviewready fires, or
  // window.pywebview already exists) slightly before the underlying
  // CoreWebView2Controller has actually finished initializing, so the
  // very first api call can fail or hang. It's transient -- confirmed
  // it recovers on its own within a couple seconds -- so retry with
  // backoff rather than leaving the shell permanently unstyled/unbuilt
  // if the first attempt lands in that window.
  async function withRetry(fn, attempts = 6, delayMs = 300) {
    for (let i = 0; i < attempts; i++) {
      try {
        return await fn();
      } catch (e) {
        if (i === attempts - 1) throw e;
        await new Promise((r) => setTimeout(r, delayMs));
        delayMs *= 2;
      }
    }
  }

  // Presentation-only grouping, not part of the backend's TABS order. Pure
  // UI concern (visual separation in the sidebar), so it stays here rather
  // than round-tripping through get_tabs -- the Tkinter app has no
  // equivalent grouping to keep in sync with.
  const NAV_GROUPS = {
    forza_font_text: 'generators', generator: 'generators', advanced: 'generators',
    direct: 'generators', ascii_art: 'generators',
    glyph_inspector: 'post', glyph_template: 'post', layer_effects: 'post',
    outputs: 'post', composer: 'post', plates: 'post',
    settings: 'settings', credits: 'settings',
  };

  function buildNav(tabs, currentTab) {
    const nav = document.getElementById('nav');
    let previousGroup = null;
    nav.innerHTML = tabs.map((tab) => {
      const group = NAV_GROUPS[tab.id] || null;
      const divider = (previousGroup !== null && group !== previousGroup) ? '<div class="nav-divider"></div>' : '';
      previousGroup = group;
      return `${divider}
      <div class="nav-row${tab.id === currentTab ? ' active' : ''}" data-tab="${tab.id}">
        <div class="nav-strip"></div>
        <div class="nav-label">${tab.label}</div>
      </div>
    `;
    }).join('');
    nav.querySelectorAll('.nav-row').forEach((row) => {
      row.addEventListener('click', () => showTab(row.dataset.tab));
    });
  }

  let currentTabUnmount = null;
  let mountToken = 0;

  // opts carries a one-shot payload into the next tab's mount(container,
  // opts) -- e.g. Generator's "Send selected font to Advanced Generator"
  // passing { fontPath } across the tab switch. Not persisted anywhere;
  // a tab that wants it later has to ask again (advanced.py's
  // get_current_generator_font), same as Tkinter's own live-object-graph
  // reads only ever reflect "right now."
  function showTab(tabId, opts) {
    if (currentTabUnmount) { currentTabUnmount(); currentTabUnmount = null; }
    const myToken = ++mountToken; // guards an async mount() against a rapid switch-away

    document.querySelectorAll('.nav-row').forEach((row) => {
      row.classList.toggle('active', row.dataset.tab === tabId);
    });
    const title = document.getElementById('pageTitle');
    const topbar = document.querySelector('.topbar');
    const rule = document.querySelector('.rule');
    const content = document.getElementById('pageContent');
    const labelEl = document.querySelector(`.nav-row[data-tab="${tabId}"] .nav-label`);
    const tabLabel = labelEl ? labelEl.textContent : tabId;

    const tabModule = window.ForzaTabs && window.ForzaTabs[tabId];
    if (tabModule) {
      // Ported tabs render their own header (matching the mockup's
      // per-page topbar), so the shell's generic one steps aside.
      if (topbar) topbar.style.display = 'none';
      if (rule) rule.style.display = 'none';
      // mount() may be sync (returns an unmount fn or null) or async
      // (returns a Promise of one) -- Settings' fetch-heavy mount is async.
      const result = tabModule(content, opts);
      if (result && typeof result.then === 'function') {
        result.then((unmount) => {
          if (myToken === mountToken) currentTabUnmount = unmount || null;
          else if (unmount) unmount(); // switched away before this resolved -- clean up immediately
        });
      } else {
        currentTabUnmount = result || null;
      }
      return;
    }

    if (topbar) topbar.style.display = '';
    if (rule) rule.style.display = '';
    if (title) title.textContent = tabLabel;
    if (content) {
      content.innerHTML = `<div class="page-placeholder">${tabLabel} -- not yet ported to the web shell. Still available in the Tkinter app.</div>`;
    }
  }

  function wireLogPanel() {
    const logbar = document.getElementById('logbar');
    const logFloat = document.getElementById('logFloat');
    const logBody = document.getElementById('logBody');
    const logBodyFloat = document.getElementById('logBodyFloat');
    const countEl = document.getElementById('logCount');
    const jumpBtn = document.getElementById('logJumpBtn');
    const jumpBtnFloat = document.getElementById('logJumpBtnFloat');
    const resizeHandle = document.getElementById('logResizeHandle');

    document.getElementById('logToggle').addEventListener('click', () => {
      logbar.classList.toggle('collapsed');
    });
    document.getElementById('logPopout').addEventListener('click', (e) => {
      e.stopPropagation();
      logbar.classList.add('detached');
      logFloat.classList.add('open');
    });
    document.getElementById('logDock').addEventListener('click', () => {
      logbar.classList.remove('detached', 'collapsed');
      logFloat.classList.remove('open');
    });

    // Quick-export: hands the whole session's log (not just what's
    // scrolled into view) to a plain .txt file via a normal Save dialog,
    // so a user hitting an unforeseen error can grab it and share it.
    // export_log() is a direct JSApi method (like get_log()), not routed
    // through api.call()'s {ok, result} registry wrapper.
    function flashExportButton(btn, ok) {
      const original = btn.innerHTML;
      btn.innerHTML = ok ? '&#10003;' : '&#10007;';
      btn.disabled = true;
      setTimeout(() => { btn.innerHTML = original; btn.disabled = false; }, 1400);
    }
    [document.getElementById('logExport'), document.getElementById('logExportFloat')].forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        let resp;
        try {
          resp = await window.pywebview.api.export_log();
        } catch (err) {
          resp = { ok: false, error: String(err) };
        }
        if (resp && resp.path) {
          flashExportButton(btn, true);
        } else if (resp && resp.ok === false) {
          flashExportButton(btn, false);
          appendLine({ ts: new Date().toTimeString().slice(0, 8), level: 'danger',
                       text: `Log export failed: ${resp.error}` });
        }
      });
    });

    // Sticky-to-bottom autoscroll: a line arriving while the user has
    // scrolled up to read earlier output must not yank them back down --
    // only follow the tail when they were already at (or very near) it,
    // and surface a jump button otherwise.
    const NEAR_BOTTOM_PX = 24;
    const isNearBottom = (el) => el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;

    function scrollToBottom(el, btn) {
      el.scrollTop = el.scrollHeight;
      btn.classList.remove('visible');
    }
    jumpBtn.addEventListener('click', () => scrollToBottom(logBody, jumpBtn));
    jumpBtnFloat.addEventListener('click', () => scrollToBottom(logBodyFloat, jumpBtnFloat));
    logBody.addEventListener('scroll', () => { if (isNearBottom(logBody)) jumpBtn.classList.remove('visible'); });
    logBodyFloat.addEventListener('scroll', () => { if (isNearBottom(logBodyFloat)) jumpBtnFloat.classList.remove('visible'); });

    function appendLine(entry) {
      const html = `<div class="log-line ${entry.level}"><span class="ts">${entry.ts}</span><span>${entry.text}</span></div>`;
      const wasAtBottom = isNearBottom(logBody);
      const wasAtBottomFloat = isNearBottom(logBodyFloat);
      logBody.insertAdjacentHTML('beforeend', html);
      logBodyFloat.insertAdjacentHTML('beforeend', html);
      if (wasAtBottom) logBody.scrollTop = logBody.scrollHeight;
      else jumpBtn.classList.add('visible');
      if (wasAtBottomFloat) logBodyFloat.scrollTop = logBodyFloat.scrollHeight;
      else jumpBtnFloat.classList.add('visible');
      const count = logBody.children.length;
      countEl.textContent = `${count} line${count === 1 ? '' : 's'}`;
    }

    withRetry(() => window.pywebview.api.get_log()).then((lines) => {
      lines.forEach(appendLine);
      // The initial backlog load should always land at the bottom rather
      // than trip the jump button.
      scrollToBottom(logBody, jumpBtn);
      scrollToBottom(logBodyFloat, jumpBtnFloat);
    });
    window.__forzaEvents.on('log_append', (_generation, entry) => appendLine(entry));

    // Drag-to-resize (docked panel only -- the floating window keeps its
    // own fixed height, matching Tkinter's detached Toplevel). Height is
    // a per-viewer chrome preference, so it lives in localStorage rather
    // than the shared gui_settings.json the Tkinter app never offers this
    // control for either.
    const MIN_LOG_HEIGHT = 80;
    const LOG_HEIGHT_KEY = 'forza.logHeight';

    function applyLogHeight(px) {
      logbar.style.setProperty('--log-height', `${px}px`);
    }
    const savedHeight = parseInt(localStorage.getItem(LOG_HEIGHT_KEY), 10);
    if (Number.isFinite(savedHeight)) applyLogHeight(savedHeight);

    let dragStartY = 0;
    let dragStartHeight = 0;
    function onDragMove(e) {
      const maxHeight = Math.max(MIN_LOG_HEIGHT, window.innerHeight - 240);
      const next = Math.min(maxHeight, Math.max(MIN_LOG_HEIGHT, dragStartHeight + (dragStartY - e.clientY)));
      applyLogHeight(next);
    }
    function onDragEnd() {
      logbar.classList.remove('resizing');
      document.removeEventListener('mousemove', onDragMove);
      document.removeEventListener('mouseup', onDragEnd);
      const px = parseInt(getComputedStyle(logBody).maxHeight, 10);
      if (Number.isFinite(px)) localStorage.setItem(LOG_HEIGHT_KEY, String(px));
    }
    resizeHandle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      logbar.classList.remove('collapsed');
      logbar.classList.add('resizing');
      dragStartY = e.clientY;
      dragStartHeight = logBody.getBoundingClientRect().height;
      document.addEventListener('mousemove', onDragMove);
      document.addEventListener('mouseup', onDragEnd);
    });
  }

  whenReady(async () => {
    const [tabs, settings] = await Promise.all([
      withRetry(() => window.pywebview.api.get_tabs()),
      withRetry(() => window.pywebview.api.get_settings()),
    ]);
    // Eurocorp only, for now. This ignores settings.palette rather than
    // overwriting it, so the shared setting the Tkinter app also reads
    // stays untouched -- this is a web-app-only display lock, not a
    // change to what palette is actually saved.
    document.documentElement.dataset.theme = 'eurocorp';
    document.documentElement.dataset.density = settings.density;
    buildNav(tabs, tabs[0].id);
    showTab(tabs[0].id);
    wireLogPanel();
  });

  window.ForzaShell = { showTab };
})();
