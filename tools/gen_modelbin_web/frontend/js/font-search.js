// Shared searchable installed-font picker, backed by fonts.list_installed
// (which reads both the machine-wide C:\Windows\Fonts registry key and the
// per-user %LOCALAPPDATA%\Microsoft\Windows\Fonts key -- a raw file dialog
// pointed at just the first of those misses most custom-installed fonts).
// Used by Glyph Inspector and Glyph Template; any future tab needing a
// font picker should use this instead of building its own.
window.ForzaFontSearch = (function () {
  let fontsCache = null; // shared across every instance on the page

  async function ensureFonts() {
    if (fontsCache) return fontsCache;
    const resp = await window.pywebview.api.call('fonts.list_installed', {});
    fontsCache = resp.ok ? resp.result.fonts : [];
    return fontsCache;
  }

  // Lazily kicks off fonts.classify (script support + glyph count per
  // installed font, see handlers/fonts.py) and resolves once it's ready.
  // Shared across every instance on the page, same as ensureFonts above --
  // whichever tab asks first pays the ~couple-of-seconds one-time cost,
  // everyone after that (this session) gets it instantly.
  let classificationPromise = null;

  function ensureClassification() {
    if (classificationPromise) return classificationPromise;
    classificationPromise = new Promise((resolve) => {
      window.pywebview.api.call('fonts.classify', {}).then((resp) => {
        if (resp.ok && resp.result.status === 'done') {
          resolve(resp.result.fonts);
          return;
        }
        const off = window.__forzaEvents.on('fonts_classified', (_generation, payload) => {
          off();
          resolve(payload.fonts);
        });
      });
    });
    return classificationPromise;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  // options: { onSelect(font), placeholder, width }
  function create(container, options) {
    const placeholder = options.placeholder || 'Search installed fonts…';
    const width = options.width || '220px';
    container.innerHTML = `
      <div class="font-search-wrap">
        <input type="text" class="font-search-input path-input" placeholder="${escapeHtml(placeholder)}"
               style="width: ${width};" autocomplete="off">
        <div class="font-search-results" style="display:none;"></div>
      </div>
    `;
    const input = container.querySelector('.font-search-input');
    const resultsEl = container.querySelector('.font-search-results');

    function hide() {
      resultsEl.style.display = 'none';
      resultsEl.innerHTML = '';
    }

    let requestId = 0;

    async function renderResults(query) {
      // ensureFonts() is async (a real js_api round trip the first time),
      // so a slower earlier call can resolve after a faster later one and
      // overwrite it with stale results -- only the most recent call may
      // actually render. See the fix history on this exact bug in
      // Glyph Inspector before this was extracted into a shared component.
      const id = ++requestId;
      const fonts = await ensureFonts();
      if (id !== requestId) return;

      const q = query.trim().toLowerCase();
      const matches = (q ? fonts.filter((f) => f.name.toLowerCase().includes(q)) : fonts).slice(0, 50);
      if (matches.length === 0) {
        resultsEl.innerHTML = '<div class="font-search-empty">No installed fonts match.</div>';
      } else {
        resultsEl.innerHTML = matches.map((f, i) => `<div class="font-search-row" data-i="${i}">${escapeHtml(f.name)}</div>`).join('');
        resultsEl.querySelectorAll('.font-search-row').forEach((row, i) => {
          row.addEventListener('mousedown', (e) => {
            e.preventDefault(); // keep focus so the subsequent blur still closes the list cleanly
            const font = matches[i];
            input.value = font.name;
            hide();
            options.onSelect(font);
          });
        });
      }
      resultsEl.style.display = '';
    }

    input.addEventListener('input', () => {
      renderResults(input.value);
      if (options.onQueryChange) options.onQueryChange(input.value);
    });
    input.addEventListener('focus', () => renderResults(input.value));
    input.addEventListener('blur', hide);

    return {
      destroy: () => {},
      setValue: (text) => { input.value = text; },
    };
  }

  return { create, getFonts: ensureFonts, getClassification: ensureClassification };
})();
