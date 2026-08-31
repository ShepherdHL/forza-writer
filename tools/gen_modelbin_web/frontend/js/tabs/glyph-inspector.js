// Glyph Inspector: browse every glyph a font supports (categorized by
// Unicode block, searchable), then inspect one at large scale in one of
// three modes -- Reference (the font's own outline + metric guides),
// Generated (the real generation pipeline's output), or Compare (diff
// Generated against a target, with the ring-gauge/pill/filmstrip/ledger
// from the original Phase 0 pass). Mirrors
// tools/gen_modelbin_gui/tabs/glyph_inspector.py's full feature set --
// this used to be Compare-mode-only, a stopgap after the initial
// architecture-proving pass never got its promised follow-up.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  // compare_masks() never individually flags a percentage metric (iou,
  // boundary_f1) -- these thresholds mirror forza_writer.glyph_quality's
  // own DEFAULT_PASS_IOU/DEFAULT_PASS_BOUNDARY_F1, used here only to
  // color the ledger's "Overall Match" summary count the same way
  // compare_masks()'s own verdict is computed, not to flag individual cards.
  const PASS_IOU = 0.90;
  const PASS_BOUNDARY_F1 = 0.80;

  const METRIC_ORDER = ['iou', 'boundary_f1', 'components', 'holes'];
  const METRIC_LABELS = { iou: 'IoU', boundary_f1: 'Boundary F1', components: 'Components', holes: 'Holes' };

  // A category this large stops offering "Show N more" -- narrow with
  // search to reach the rest instead. Mirrors gen_modelbin_gui/state.py's
  // GLYPH_CATEGORY_HARD_CAP (that module isn't importable here without
  // pulling in tkinter transitively, so the constant is kept in sync by
  // hand -- the backend's own category_tile_cap in the load-font response
  // is the one value that actually has to match).
  const GLYPH_CATEGORY_HARD_CAP = 1000;
  const GLYPH_CATEGORY_EXPAND_STEP = 200;

  function isShortfall(metrics, key) {
    if (key !== 'components' && key !== 'holes') return false;
    return metrics[`${key}_generated`] < metrics[`${key}_expected`];
  }

  function buildMetricViews(metrics) {
    return METRIC_ORDER.map((key) => {
      const name = METRIC_LABELS[key];
      if (key === 'iou' || key === 'boundary_f1') {
        const value = metrics[key];
        return {
          key, name, kind: 'gauge',
          generated: value, target: 1.0,
          display: (value * 100).toFixed(1) + '%',
          score: value.toFixed(3),
          change: null, flagged: false,
        };
      }
      const generated = metrics[`${key}_generated`];
      const expected = metrics[`${key}_expected`];
      const flagged = isShortfall(metrics, key);
      return {
        key, name, kind: 'pill',
        generatedCount: generated, targetCount: expected,
        score: `${generated} / ${expected}`,
        change: flagged ? `▼ missing ${expected - generated}` : null,
        flagged,
      };
    });
  }

  function overallMatchCount(metrics) {
    let n = 0;
    if (metrics.iou >= PASS_IOU) n++;
    if (metrics.boundary_f1 >= PASS_BOUNDARY_F1) n++;
    if (metrics.components_generated === metrics.components_expected) n++;
    if (metrics.holes_generated === metrics.holes_expected) n++;
    return n;
  }

  function gaugeSvg(m) {
    const r = 74, c = 2 * Math.PI * r;
    return `
      <div class="gi-gauge">
        <svg viewBox="0 0 168 168">
          <circle class="gi-gauge-track" cx="84" cy="84" r="${r}"/>
          <circle class="gi-gauge-fill-target" cx="84" cy="84" r="${r}" stroke-dasharray="${c * m.target} ${c}"/>
          <circle class="gi-gauge-fill" cx="84" cy="84" r="${r}" stroke-dasharray="${c * m.generated} ${c}"/>
        </svg>
        <div class="gi-gauge-center">
          <div class="value">${m.display}</div>
          <div class="vs">vs <b>100%</b> target</div>
        </div>
      </div>`;
  }

  function pillSvg(m) {
    const genIcons = Array.from({ length: Math.max(m.generatedCount, m.targetCount) }, (_, i) =>
      i < m.generatedCount ? '<span class="gi-icon-dot"></span>' : '<span class="gi-icon-dot missing"></span>'
    ).join('');
    const tgtIcons = Array.from({ length: m.targetCount }, () => '<span class="gi-icon-dot ghost"></span>').join('');
    const captionFlag = m.flagged
      ? `<b class="flag">missing ${m.targetCount - m.generatedCount}</b> vs target`
      : 'matches target';
    return `
      <div class="gi-pill-badge">
        <div class="gi-pill-half generated">
          <span class="gi-pill-count">${m.generatedCount}</span>
          <span class="gi-pill-icons">${genIcons}</span>
        </div>
        <div class="gi-pill-half target">
          <span class="gi-pill-count">${m.targetCount}</span>
          <span class="gi-pill-icons">${tgtIcons}</span>
        </div>
        <div class="gi-pill-caption">Generated vs target -- ${captionFlag}</div>
      </div>`;
  }

  function renderCompare(container, tabState) {
    const { metrics, focusIndex } = tabState;
    const readout = container.querySelector('#giReadout');
    const filmstrip = container.querySelector('#giFilmstrip');
    const dotnav = container.querySelector('#giDotnav');
    const ledgerRows = container.querySelector('#giLedgerRows');
    const ledgerTotal = container.querySelector('#giLedgerTotalScore');
    const verdictBadge = container.querySelector('#giVerdictBadge');
    if (!metrics) {
      readout.innerHTML = '';
      filmstrip.innerHTML = '';
      dotnav.innerHTML = '';
      ledgerRows.innerHTML = '';
      ledgerTotal.textContent = '– / 4';
      verdictBadge.textContent = '–';
      verdictBadge.className = 'gi-verdict-badge';
      return;
    }

    const views = buildMetricViews(metrics);
    const m = views[focusIndex];
    readout.innerHTML = `
      <div class="gi-readout-label">${m.name}</div>
      ${m.kind === 'gauge' ? gaugeSvg(m) : pillSvg(m)}
    `;

    filmstrip.innerHTML = views.map((mm, i) => `
      <button type="button" class="gi-film-card ${i === focusIndex ? 'active' : ''}" data-i="${i}">
        <span class="k">${mm.name}</span>
        <span class="v">${mm.score}</span>
        ${mm.flagged ? `<span class="flag-chip">${mm.change}</span>` : ''}
      </button>
    `).join('');

    dotnav.innerHTML = views.map((mm, i) => `
      <button type="button" class="gi-dot ${i === focusIndex ? 'active' : ''}" data-i="${i}"
        role="tab" aria-selected="${i === focusIndex}" aria-label="${mm.name}"></button>
    `).join('');

    ledgerRows.innerHTML = views.map((mm, i) => `
      <div class="gi-ledger-row ${mm.flagged ? 'flagged' : 'pass'} ${i === focusIndex ? 'current' : ''}" data-i="${i}">
        <span class="name">${mm.name}</span>
        <span><span class="score">${mm.score}</span>${mm.change ? `<span class="change">${mm.change}</span>` : ''}</span>
      </div>
    `).join('');

    ledgerTotal.textContent = `${overallMatchCount(metrics)} / 4`;

    const verdict = metrics.verdict;
    if (verdict !== 'pass' && verdict !== 'review') {
      // compare_masks() only ever returns "pass"/"review" -- silently
      // defaulting to one of them here would misreport a result the
      // underlying data doesn't actually support.
      throw new Error(`unrecognized verdict from compare_masks(): ${verdict}`);
    }
    verdictBadge.textContent = verdict === 'pass'
      ? 'PASS'
      : `REVIEW · ${views.filter((v) => v.flagged).length} FLAGGED`;
    verdictBadge.className = `gi-verdict-badge ${verdict}`;

    container.querySelectorAll('#giCompareExtras [data-i]').forEach((el) => {
      el.onclick = () => { tabState.focusIndex = Number(el.dataset.i); renderCompare(container, tabState); };
    });
  }

  function setStatus(container, text, isError) {
    const el = container.querySelector('#giStatus');
    el.textContent = text;
    el.classList.toggle('error', !!isError);
  }

  function metaHtml(m) {
    if (!m) {
      return ['Character', 'Codepoint', 'Unicode name', 'Glyph name', 'Category',
        'Advance width', 'Side bearings', 'Bounding box'].map((label) => metaRow(label, '—')).join('');
    }
    return [
      ['Character', m.char], ['Codepoint', m.codepoint], ['Unicode name', m.unicode_name],
      ['Glyph name', m.glyph_name], ['Category', m.category],
      ['Advance width', m.advance_width], ['Side bearings', m.bearings], ['Bounding box', m.bbox],
    ].map(([label, value]) => metaRow(label, value)).join('');
  }
  function metaRow(label, value) {
    return `<div style="display:flex; gap:8px; padding:2px 0; font-size:11.5px;">
      <span style="color:var(--muted); min-width:104px; flex-shrink:0;">${esc(label)}:</span>
      <span style="color:var(--fg); word-break:break-word;">${esc(value)}</span>
    </div>`;
  }

  function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">Glyph Inspector</h2>
      <div class="intro-text">
        Browse every glyph a font supports, grouped by Unicode block, and inspect one at large
        scale against the font's own metrics -- what the font itself says a character should
        look like.
      </div>

      <div class="section">
        <div class="section-title">1. Font</div>
        <div style="display:flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 8px;">
          <div id="giFontSearch"></div>
          <button type="button" class="btn" id="giLoadFont">Browse file…</button>
        </div>
        <div class="field-hint" id="giFontStatus">Select a font to inspect its glyphs.</div>
        <div class="field-hint" id="giFontPath" style="font-family: var(--mono); margin-top: 2px;">No font loaded.</div>
        <div class="field-hint" id="giFontSuggestion" style="display:none; margin-top: 6px;"></div>
      </div>

      <div class="gi-content" style="grid-template-columns: 1fr 420px;">
        <div>
          <div class="section">
            <div class="section-title">2. Glyphs</div>
            <input type="text" class="path-input" id="giSearch" placeholder="Character, U+codepoint, Unicode name, or glyph name" style="width:100%; margin-bottom:8px;">
            <div class="field-hint" id="giGridStatus" style="margin-bottom:8px;">Select a font to inspect its glyphs.</div>
            <div class="gi-tile-scroll" id="giGrid"></div>
          </div>
        </div>

        <div>
          <div class="section">
            <div class="section-title">Selected Glyph</div>
            <div class="radio-group" id="giModeGroup" style="margin-bottom:8px;">
              <label><input type="radio" name="giMode" value="reference" checked> Reference</label>
              <label><input type="radio" name="giMode" value="generated"> Generated</label>
              <label><input type="radio" name="giMode" value="compare"> Compare</label>
            </div>

            <div id="giCompareRow" style="display:none; margin-bottom:8px;">
              <div class="gi-target-toggle" role="group" aria-label="Compare target source" style="margin-bottom:6px;">
                <button type="button" id="giTargetOutline" aria-pressed="true">Font Outline</button>
                <button type="button" id="giTargetHandmade" aria-pressed="false">Hand-made File</button>
              </div>
              <button type="button" class="btn" id="giLoadHandmade" style="width:100%;">Load hand-made file…</button>
              <div class="field-hint" id="giHandmadePath" style="display:none; margin-top:4px; font-family: var(--mono);"></div>
            </div>

            <div class="gi-diff-panel" id="giDiffPanel" style="margin-bottom:8px;">
              <div class="gi-diff-empty">Select a glyph on the left.</div>
            </div>

            <div id="giCompareExtras" style="display:none;">
              <div class="gi-readout" id="giReadout"></div>
              <div class="gi-filmstrip" id="giFilmstrip" style="margin-top:10px;"></div>
              <div class="gi-dotnav" id="giDotnav" role="tablist" aria-label="Metric pages" style="margin-top:6px;"></div>
              <div class="gi-prompt">Press <b>◀ ▶</b> or click a card to change metric</div>
              <div class="gi-ledger" aria-label="All metrics for this glyph" style="margin-top:10px;">
                <div class="gi-ledger-head"><span>Metric</span><span>Score · Δ</span></div>
                <div id="giLedgerRows"></div>
                <div class="gi-ledger-hatch"></div>
                <div class="gi-ledger-total"><span class="name">Overall Match</span><span class="score" id="giLedgerTotalScore">– / 4</span></div>
                <div class="gi-ledger-hatch"></div>
                <div class="gi-verdict-row">
                  <span class="name">Verdict</span>
                  <span class="gi-verdict-badge" id="giVerdictBadge">–</span>
                </div>
              </div>
            </div>

            <div id="giMeta" style="margin-top:10px;">${metaHtml(null)}</div>
            <div class="gi-status" id="giStatus" style="margin-top:8px;"></div>
          </div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    const tabState = {
      fontInfo: null,           // {path, name, status, categories, metrics, category_tile_cap}
      mode: 'reference',        // 'reference' | 'generated' | 'compare'
      compareTarget: 'font',    // 'font' | 'handmade'
      selectedChar: null,
      orderedChars: [],         // every currently search-matched char, in display order (arrow-key nav)
      categoryShown: {},        // category name -> how many of its tiles are currently rendered
      tileCache: new Map(),     // char -> data URI, cleared on font (re)load
      handmadePaths: {},        // char -> path, for the status line + compare's target label
      pendingGeneration: null,
      metrics: null, focusIndex: 3, // compare-only; lands on Holes like the mockup, matching prior behavior
    };
    let tileButtons = new Map(); // char -> button element, valid until the next renderGrid()
    let selectedTileBtn = null;

    renderCompare(container, tabState);
    container.querySelector('#giMeta').innerHTML = metaHtml(null);

    // -- 1. font ------------------------------------------------------------
    function applyLoadedFont(payload) {
      tabState.fontInfo = payload;
      tabState.categoryShown = {};
      tabState.tileCache.clear();
      tabState.selectedChar = null;
      selectedTileBtn = null;
      container.querySelector('#giFontStatus').textContent = payload.status;
      container.querySelector('#giFontPath').textContent = payload.path;
      setStatus(container, `Loaded ${payload.name}.`);
      container.querySelector('#giSearch').value = '';
      renderGrid();
      clearDetail();
    }

    container.querySelector('#giLoadFont').addEventListener('click', async () => {
      setStatus(container, 'Loading font…');
      const resp = await api.call('glyph_inspector.load_font', {});
      if (!resp.ok) { setStatus(container, resp.error, true); return; }
      if (resp.result.cancelled) { setStatus(container, ''); return; }
      applyLoadedFont(resp.result);
    });

    window.ForzaFontSearch.create(container.querySelector('#giFontSearch'), {
      placeholder: 'Search installed fonts…',
      onSelect: async (font) => {
        setStatus(container, `Loading ${font.name}…`);
        const resp = await api.call('glyph_inspector.load_font_by_path', { path: font.path });
        if (!resp.ok) { setStatus(container, resp.error, true); return; }
        applyLoadedFont(resp.result);
      },
    });

    // -- 2. categorized, searchable glyph grid -------------------------------
    function glyphMatches(glyph, needle) {
      if (!needle) return true;
      if (glyph.char.toLowerCase().includes(needle)) return true;
      if (needle.startsWith('u+') || needle.startsWith('0x')) {
        const hex = needle.slice(2);
        if (hex && glyph.codepoint.toString(16).padStart(4, '0').includes(hex)) return true;
      }
      if (glyph.unicode_name && glyph.unicode_name.toLowerCase().includes(needle)) return true;
      if (glyph.glyph_name.toLowerCase().includes(needle)) return true;
      return false;
    }

    async function fetchTilesForCategory(chars) {
      const missing = chars.filter((c) => !tabState.tileCache.has(c));
      if (missing.length === 0) return;
      const resp = await api.call('glyph_inspector.render_tiles', { chars: missing });
      if (!resp.ok) return;
      missing.forEach((c, i) => {
        tabState.tileCache.set(c, resp.result.tiles[i]);
        const btn = tileButtons.get(c);
        if (btn) btn.style.backgroundImage = `url(${resp.result.tiles[i]})`;
      });
    }

    function renderGrid() {
      const gridEl = container.querySelector('#giGrid');
      const statusEl = container.querySelector('#giGridStatus');
      tileButtons = new Map();
      tabState.orderedChars = [];
      selectedTileBtn = null;

      if (!tabState.fontInfo) {
        gridEl.innerHTML = '';
        statusEl.textContent = 'Select a font to inspect its glyphs.';
        return;
      }

      const needle = container.querySelector('#giSearch').value.trim().toLowerCase();
      const cap = tabState.fontInfo.category_tile_cap;
      let totalMatched = 0;
      const fetchJobs = [];

      const categoriesHtml = tabState.fontInfo.categories.map((cat) => {
        const matched = cat.glyphs.filter((g) => glyphMatches(g, needle));
        if (matched.length === 0) return '';
        totalMatched += matched.length;
        tabState.orderedChars.push(...matched.map((g) => g.char));

        const alreadyShown = tabState.categoryShown[cat.name];
        const shownCount = alreadyShown !== undefined ? Math.min(alreadyShown, matched.length) : Math.min(matched.length, cap);
        tabState.categoryShown[cat.name] = shownCount;
        const shown = matched.slice(0, shownCount);
        const overflow = matched.length - shown.length;
        fetchJobs.push(shown.map((g) => g.char));

        const tilesHtml = shown.map((g) => {
          const cp = g.codepoint.toString(16).toUpperCase().padStart(4, '0');
          return `<button type="button" class="gi-tile" data-char="${esc(g.char)}" title="${esc(g.char)} (U+${cp})"></button>`;
        }).join('');

        let moreHtml = '';
        if (overflow > 0) {
          if (shownCount >= GLYPH_CATEGORY_HARD_CAP) {
            moreHtml = `<div class="field-hint" style="margin-top:4px;">${overflow.toLocaleString()} more in ${esc(cat.name)} -- narrow with search to reach them (showing up to ${GLYPH_CATEGORY_HARD_CAP.toLocaleString()} per category at once).</div>`;
          } else {
            const step = Math.min(GLYPH_CATEGORY_EXPAND_STEP, overflow, GLYPH_CATEGORY_HARD_CAP - shownCount);
            moreHtml = `<button type="button" class="btn gi-tile-more" data-category="${esc(cat.name)}">Show ${step.toLocaleString()} more in ${esc(cat.name)} (${overflow.toLocaleString()} remaining)</button>`;
          }
        }

        return `
          <div class="gi-tile-category">
            <div class="gi-tile-category-title">${esc(cat.name)} (${matched.length.toLocaleString()})</div>
            <div class="gi-tile-grid">${tilesHtml}</div>
            ${moreHtml}
          </div>`;
      }).join('');

      gridEl.innerHTML = categoriesHtml;
      statusEl.textContent = needle
        ? `${totalMatched.toLocaleString()} glyph(s) match.`
        : `${totalMatched.toLocaleString()} glyph(s).`;

      gridEl.querySelectorAll('.gi-tile').forEach((btn) => {
        const c = btn.dataset.char;
        tileButtons.set(c, btn);
        if (tabState.tileCache.has(c)) btn.style.backgroundImage = `url(${tabState.tileCache.get(c)})`;
        if (c === tabState.selectedChar) { btn.classList.add('selected'); selectedTileBtn = btn; }
        btn.addEventListener('click', () => selectChar(c));
      });
      gridEl.querySelectorAll('.gi-tile-more').forEach((btn) => {
        btn.addEventListener('click', () => {
          const name = btn.dataset.category;
          tabState.categoryShown[name] = (tabState.categoryShown[name] || 0) + GLYPH_CATEGORY_EXPAND_STEP;
          renderGrid();
        });
      });

      fetchJobs.forEach((chars) => { if (chars.length) fetchTilesForCategory(chars); });
    }

    container.querySelector('#giSearch').addEventListener('input', renderGrid);

    // -- selection + shared metadata -----------------------------------------
    function clearDetail() {
      container.querySelector('#giDiffPanel').innerHTML = '<div class="gi-diff-empty">Select a glyph on the left.</div>';
      container.querySelector('#giMeta').innerHTML = metaHtml(null);
      setStatus(container, 'Select a glyph on the left.');
      tabState.metrics = null;
      renderCompare(container, tabState);
    }

    async function refreshMeta() {
      const resp = await api.call('glyph_inspector.get_geometry', { char: tabState.selectedChar });
      container.querySelector('#giMeta').innerHTML = resp.ok ? metaHtml(resp.result) : metaHtml(null);
    }

    async function refreshDetail() {
      const char = tabState.selectedChar;
      if (char === null) { clearDetail(); return; }
      refreshMeta();

      if (tabState.mode === 'reference') {
        const resp = await api.call('glyph_inspector.get_reference', { char });
        if (!resp.ok) { setStatus(container, resp.error, true); return; }
        container.querySelector('#giDiffPanel').innerHTML = `<img src="${resp.result.image}" alt="Reference render of ${esc(char)}">`;
        setStatus(container, resp.result.status);
      } else if (tabState.mode === 'generated') {
        setStatus(container, 'Generating…');
        const resp = await api.call('glyph_inspector.get_generated', { char, compute_backend: 'auto' });
        if (!resp.ok) { setStatus(container, resp.error, true); return; }
        tabState.pendingGeneration = resp.result.generation;
      } else {
        await runCompare();
      }
    }

    async function selectChar(char) {
      tabState.selectedChar = char;
      if (selectedTileBtn) selectedTileBtn.classList.remove('selected');
      const btn = tileButtons.get(char);
      if (btn) { btn.classList.add('selected'); selectedTileBtn = btn; }
      else selectedTileBtn = null;
      await refreshDetail();
    }

    // -- mode switching -------------------------------------------------------
    function updateCompareRowVisibility() {
      const isCompare = tabState.mode === 'compare';
      container.querySelector('#giCompareRow').style.display = isCompare ? '' : 'none';
      container.querySelector('#giCompareExtras').style.display = isCompare ? '' : 'none';
    }
    container.querySelector('#giModeGroup').addEventListener('change', () => {
      tabState.mode = container.querySelector('input[name="giMode"]:checked').value;
      updateCompareRowVisibility();
      refreshDetail();
    });

    container.querySelector('#giTargetOutline').addEventListener('click', () => {
      tabState.compareTarget = 'font';
      container.querySelector('#giTargetOutline').setAttribute('aria-pressed', 'true');
      container.querySelector('#giTargetHandmade').setAttribute('aria-pressed', 'false');
      if (tabState.mode === 'compare') refreshDetail();
    });
    container.querySelector('#giTargetHandmade').addEventListener('click', () => {
      tabState.compareTarget = 'handmade';
      container.querySelector('#giTargetOutline').setAttribute('aria-pressed', 'false');
      container.querySelector('#giTargetHandmade').setAttribute('aria-pressed', 'true');
      if (tabState.mode === 'compare') refreshDetail();
    });

    container.querySelector('#giLoadHandmade').addEventListener('click', async () => {
      const char = tabState.selectedChar;
      if (!char) { setStatus(container, 'Select a glyph on the left first.', true); return; }
      setStatus(container, 'Loading hand-made file…');
      const resp = await api.call('glyph_inspector.load_handmade', { char });
      if (!resp.ok) { setStatus(container, resp.error, true); return; }
      if (resp.result.cancelled) { setStatus(container, ''); return; }
      tabState.handmadePaths[char] = resp.result.path;
      tabState.compareTarget = 'handmade';
      container.querySelector('#giTargetOutline').setAttribute('aria-pressed', 'false');
      container.querySelector('#giTargetHandmade').setAttribute('aria-pressed', 'true');
      setStatus(container, 'Hand-made file loaded.');

      const handmadePathEl = container.querySelector('#giHandmadePath');
      handmadePathEl.style.display = '';
      handmadePathEl.textContent = `Hand-made file for '${char}': ${resp.result.path}`;

      const suggestionEl = container.querySelector('#giFontSuggestion');
      const suggestion = resp.result.suggested_font;
      if (suggestion) {
        suggestionEl.style.display = '';
        suggestionEl.innerHTML =
          `This might be <b>${esc(suggestion.name)}</b>. ` +
          `<a class="link" href="#" id="giApplySuggestedFont" style="display:inline;">Load this font</a>` +
          ` <a class="link" href="#" id="giDismissSuggestedFont" style="display:inline;">Dismiss</a>`;
        suggestionEl.querySelector('#giApplySuggestedFont').addEventListener('click', async (e) => {
          e.preventDefault();
          setStatus(container, `Loading ${suggestion.name}…`);
          const loadResp = await api.call('glyph_inspector.load_font_by_path', { path: suggestion.path });
          if (!loadResp.ok) { setStatus(container, loadResp.error, true); return; }
          applyLoadedFont(loadResp.result);
          suggestionEl.style.display = 'none';
        });
        suggestionEl.querySelector('#giDismissSuggestedFont').addEventListener('click', (e) => {
          e.preventDefault();
          suggestionEl.style.display = 'none';
        });
      } else {
        suggestionEl.style.display = 'none';
      }

      if (tabState.mode === 'compare') refreshDetail();
    });

    // -- Compare mode (existing pipeline, now driven by the selected glyph) --
    async function runCompare() {
      const char = tabState.selectedChar;
      if (!char) { setStatus(container, 'Select a glyph on the left first.', true); return; }
      setStatus(container, 'Generating…');
      const resp = await api.call('glyph_inspector.compare', {
        char, target: tabState.compareTarget === 'handmade' ? 'handmade' : 'outline', compute_backend: 'auto',
      });
      if (!resp.ok) { setStatus(container, resp.error, true); return; }
      tabState.pendingGeneration = resp.result.generation;
    }

    const offGeneratedReady = window.__forzaEvents.on('glyph_inspector_generated_ready', (generation, payload) => {
      if (generation !== tabState.pendingGeneration) return;
      container.querySelector('#giDiffPanel').innerHTML = `<img src="${payload.image}" alt="Generated render">`;
      setStatus(container, payload.status);
    });
    const offGeneratedError = window.__forzaEvents.on('glyph_inspector_generated_error', (generation, payload) => {
      if (generation !== tabState.pendingGeneration) return;
      setStatus(container, payload.error, true);
    });
    const offCompareReady = window.__forzaEvents.on('glyph_inspector_compare_ready', (generation, payload) => {
      if (generation !== tabState.pendingGeneration) return;
      tabState.metrics = payload.metrics;
      tabState.focusIndex = 3; // land on the flagged-or-not "Holes" metric, matching the mockup
      const panel = container.querySelector('#giDiffPanel');
      panel.innerHTML = `
        <img src="${payload.overlay}" alt="Diff overlay: generated glyph outline against target outline">
        <div class="gi-diff-legend">
          <span><i class="dot" style="background:var(--generated)"></i>Generated</span>
          <span><i class="dot" style="background:var(--target)"></i>Target</span>
          <span><i class="dot" style="background:var(--flag)"></i>Missed</span>
        </div>`;
      const targetLabel = tabState.compareTarget === 'handmade'
        ? `hand-made (${(tabState.handmadePaths[tabState.selectedChar] || '').split(/[\\/]/).pop()})`
        : 'font outline';
      setStatus(container, `Compared. Strategy: ${payload.strategy}. Target: ${targetLabel}.`);
      renderCompare(container, tabState);
    });
    const offCompareError = window.__forzaEvents.on('glyph_inspector_compare_error', (generation, payload) => {
      if (generation !== tabState.pendingGeneration) return;
      setStatus(container, payload.error, true);
    });

    // -- keyboard navigation ---------------------------------------------------
    // Left/Right steps through the visible glyph list in Reference/Generated
    // mode, or through Compare's 4 metric cards in Compare mode -- matching
    // Tkinter's _on_glyph_inspector_key branching on mode, not on focus.
    const onKey = (e) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const active = document.activeElement;
      if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) return;
      const step = e.key === 'ArrowLeft' ? -1 : 1;
      if (tabState.mode === 'compare') {
        if (!tabState.metrics) return;
        tabState.focusIndex = (tabState.focusIndex + step + METRIC_ORDER.length) % METRIC_ORDER.length;
        renderCompare(container, tabState);
        return;
      }
      const glyphs = tabState.orderedChars;
      if (!glyphs.length) return;
      const index = tabState.selectedChar === null ? -1 : glyphs.indexOf(tabState.selectedChar);
      const nextIndex = index >= 0 ? Math.max(0, Math.min(glyphs.length - 1, index + step)) : 0;
      selectChar(glyphs[nextIndex]);
    };
    document.addEventListener('keydown', onKey);

    return () => {
      offGeneratedReady(); offGeneratedError(); offCompareReady(); offCompareError();
      document.removeEventListener('keydown', onKey);
    };
  }

  window.ForzaTabs.glyph_inspector = mount;
})();
