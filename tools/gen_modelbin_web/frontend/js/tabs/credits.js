// Credits tab: static attribution content fetched from the real
// CREDITS_SECTIONS data (tools/gen_modelbin_gui/tabs/credits.py) via
// credits.get_sections, not a hand-duplicated copy.
window.ForzaTabs = window.ForzaTabs || {};

(function () {
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function renderEntry(entry) {
    let byline = entry.author ? `by ${entry.author}` : '';
    if (entry.license) byline = byline ? `${byline}  ·  ${entry.license}` : entry.license;

    const description = Array.isArray(entry.description) ? entry.description
      : entry.description ? [entry.description] : [];

    return `
      <div class="entry">
        <div class="entry-name">${escapeHtml(entry.name)}</div>
        ${byline ? `<div class="entry-byline">${escapeHtml(byline)}</div>` : ''}
        <div class="entry-body">
          ${entry.category ? `<div class="category-label">${escapeHtml(entry.category)}</div>` : ''}
          ${description.map((p) => `<div class="hint-text">${escapeHtml(p)}</div>`).join('')}
          ${(entry.implementation && entry.implementation.length)
            ? `<div class="code-text">${entry.implementation.map(escapeHtml).join('  ·  ')}</div>` : ''}
          ${(entry.links || []).map(([text, url]) =>
            `<a class="link" href="#" data-url="${escapeHtml(url)}">${escapeHtml(text)} ↗</a>`
          ).join('')}
        </div>
      </div>`;
  }

  function mount(container) {
    container.innerHTML = `
      <h2 class="page-heading">Credits</h2>
      <div class="intro-text">
        Forza Writer is an original implementation. Selected portions incorporate code adapted
        from third-party projects, bundle third-party data, or were developed with reference to
        external research. THIRD_PARTY_NOTICES.md, in the project root, contains the complete
        legal notices and required license text.
      </div>
      <div id="creditsSections"></div>
      <div class="section">
        <div class="section-title">License</div>
        <div class="hint-text">
          Forza Writer is MIT-licensed; see LICENSE in the project root. Adapted third-party code
          carries its own upstream attribution requirements, documented in THIRD_PARTY_NOTICES.md.
        </div>
      </div>
    `;

    window.pywebview.api.call('credits.get_sections', {}).then((resp) => {
      if (!resp.ok) {
        container.querySelector('#creditsSections').innerHTML =
          `<div class="hint-text">Couldn't load credits: ${resp.error}</div>`;
        return;
      }
      container.querySelector('#creditsSections').innerHTML = resp.result.sections.map((section) => `
        <div class="section">
          <div class="section-title">${escapeHtml(section.title)}</div>
          ${section.entries.map(renderEntry).join('')}
        </div>
      `).join('');

      container.querySelectorAll('.link').forEach((link) => {
        link.addEventListener('click', (e) => {
          e.preventDefault();
          window.pywebview.api.call('credits.open_link', { url: link.dataset.url });
        });
      });
    });

    return null; // nothing to clean up on tab switch
  }

  window.ForzaTabs.credits = mount;
})();
