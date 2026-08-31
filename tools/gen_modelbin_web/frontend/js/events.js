// Receiving end of events.py's push_event: a tiny per-tag pub-sub that
// Python pushes into directly via window.evaluate_js, replacing the old
// Tkinter shell's 100ms _poll_queue tick entirely. Each listener does its
// own `generation` staleness check -- the same role the old
// (tag, generation, ...) tuple comparison played in e.g.
// tabs/glyph_inspector.py's stale-result guard.
window.__forzaEvents = (function () {
  const listeners = {};
  return {
    on(tag, fn) {
      (listeners[tag] || (listeners[tag] = [])).push(fn);
      return () => {
        listeners[tag] = (listeners[tag] || []).filter((f) => f !== fn);
      };
    },
    dispatch(tag, generation, payload) {
      (listeners[tag] || []).forEach((fn) => {
        try { fn(generation, payload); } catch (e) { console.error(e); }
      });
    },
  };
})();
