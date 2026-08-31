// Output tab: browse previously-generated fontpacks and their glyphs, or
// preview any .json/.modelbin file directly.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  async function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">Output</h2>
      <div class="intro-text">
        Browse fontpacks you have already generated. Pick one on the left to list its glyphs, then
        pick a glyph to preview it. Or browse any .json/.modelbin file directly below, whether or
        not it belongs to a recognized pack.
      </div>

      <div class="section">
        <div class="section-title">Fontpack Root Folder</div>
        <div class="path-field">
          <input type="text" class="path-input" id="outRoot">
          <button type="button" class="btn" id="outBrowseRoot">Browse…</button>
          <button type="button" class="btn" id="outRefresh">Refresh</button>
        </div>
      </div>

      <div class="settings-grid" style="margin-bottom: 16px;">
        <div class="section" style="margin-bottom: 0;">
          <div class="section-title">Fontpacks</div>
          <div class="list-box" id="outPackList"><div class="list-empty">No fontpack root loaded yet.</div></div>
        </div>
        <div class="section" style="margin-bottom: 0;">
          <div class="section-title">Glyphs</div>
          <div class="list-box" id="outGlyphList"><div class="list-empty">Pick a fontpack first.</div></div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Preview</div>
        <div class="path-field" style="margin-bottom: 12px;">
          <input type="text" class="path-input" id="outPreviewPath" placeholder="Or browse any file directly">
          <button type="button" class="btn" id="outBrowseFile">Browse…</button>
          <button type="button" class="btn" id="outPreviewBtn">Preview</button>
        </div>
        <div style="display:flex; gap: 16px; align-items: flex-start;">
          <div class="gi-diff-panel" style="aspect-ratio: auto; width: 280px; height: 280px;" id="outPreviewPanel">
            <div class="gi-diff-empty">Pick a fontpack on the left, or browse a file directly.</div>
          </div>
          <div class="stats-text hint" id="outStats"></div>
        </div>
      </div>
    `;

    const api = window.pywebview.api;
    let packs = [];
    let glyphEntries = [];

    async function refreshPacks() {
      const root = container.querySelector('#outRoot').value;
      const resp = await api.call('outputs.list_packs', { root });
      const listEl = container.querySelector('#outPackList');
      if (!resp.ok) { listEl.innerHTML = `<div class="list-empty">${esc(resp.error)}</div>`; return; }
      packs = resp.result.packs;
      if (packs.length === 0) {
        listEl.innerHTML = '<div class="list-empty">No fontpacks found under this folder.</div>';
        return;
      }
      listEl.innerHTML = packs.map((p, i) => `<div class="list-row" data-i="${i}">${esc(p.label)}</div>`).join('');
      listEl.querySelectorAll('.list-row').forEach((row, i) => {
        row.addEventListener('click', () => selectPack(i, row));
      });
    }

    async function selectPack(i, rowEl) {
      container.querySelectorAll('#outPackList .list-row').forEach((r) => r.classList.remove('active'));
      rowEl.classList.add('active');
      const glyphListEl = container.querySelector('#outGlyphList');
      glyphListEl.innerHTML = '<div class="list-empty">Loading…</div>';
      const resp = await api.call('outputs.get_pack_glyphs', { pack_dir: packs[i].path });
      if (!resp.ok) { glyphListEl.innerHTML = `<div class="list-empty">${esc(resp.error)}</div>`; return; }
      glyphEntries = resp.result.entries;
      if (glyphEntries.length === 0) {
        glyphListEl.innerHTML = '<div class="list-empty">This pack has no glyphs.</div>';
        return;
      }
      glyphListEl.innerHTML = glyphEntries.map((g, gi) => `<div class="list-row" data-i="${gi}">${esc(g.label)}</div>`).join('');
      glyphListEl.querySelectorAll('.list-row').forEach((row, gi) => {
        row.addEventListener('click', () => {
          glyphListEl.querySelectorAll('.list-row').forEach((r) => r.classList.remove('active'));
          row.classList.add('active');
          const entry = glyphEntries[gi];
          if (!entry.path) return;
          container.querySelector('#outPreviewPath').value = entry.path;
          runPreview(entry.path);
        });
      });
    }

    async function runPreview(path) {
      const panel = container.querySelector('#outPreviewPanel');
      const statsEl = container.querySelector('#outStats');
      const resp = await api.call('outputs.preview_file', { path });
      if (!resp.ok) {
        statsEl.className = 'stats-text danger';
        statsEl.textContent = resp.error;
        return;
      }
      panel.innerHTML = `<img src="${resp.result.preview_image}" alt="File preview" style="width:100%;height:100%;object-fit:contain;">`;
      statsEl.className = `stats-text ${resp.result.style}`;
      statsEl.textContent = resp.result.text;
    }

    container.querySelector('#outBrowseRoot').addEventListener('click', async () => {
      const resp = await api.call('outputs.browse_root', { initial: container.querySelector('#outRoot').value });
      if (resp.ok && !resp.result.cancelled) {
        container.querySelector('#outRoot').value = resp.result.path;
        refreshPacks();
      }
    });
    container.querySelector('#outRefresh').addEventListener('click', refreshPacks);

    container.querySelector('#outBrowseFile').addEventListener('click', async () => {
      const resp = await api.call('outputs.browse_file', {});
      if (resp.ok && !resp.result.cancelled) {
        container.querySelector('#outPreviewPath').value = resp.result.path;
        runPreview(resp.result.path);
      }
    });
    container.querySelector('#outPreviewBtn').addEventListener('click', () => {
      const path = container.querySelector('#outPreviewPath').value.trim();
      if (path) runPreview(path);
    });

    // default root: the shared Fontpacks Output Directory from Settings
    const pathsResp = await api.call('settings.get_paths', {});
    if (pathsResp.ok) {
      const outField = pathsResp.result.fields.find((f) => f.key === 'output_dir');
      if (outField) container.querySelector('#outRoot').value = outField.value;
    }
    refreshPacks();

    return null;
  }

  window.ForzaTabs.outputs = mount;
})();
