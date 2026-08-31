// Procedurally generated, continuously-drifting node network, ported
// verbatim from the "Glyph Audit" mockup -- the browser-side counterpart
// to gui_theme/backdrops/eurocorp.py's own generator (nearest-neighbor
// mesh + accent diagonals + hexagon/chevron motifs), now truly animated
// via requestAnimationFrame instead of a flip-book of baked PIL frames.
// Motion is slow, continuous drift -- never a flash or an opacity pulse.
(function () {
  function mulberry32(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function drawHexagon(ctx, cx, cy, r, rot) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const angle = (Math.PI / 3) * i - Math.PI / 6 + rot;
      const x = cx + r * Math.cos(angle), y = cy + r * Math.sin(angle);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
  }

  function drawChevron(ctx, cx, cy, size) {
    ctx.beginPath();
    ctx.moveTo(cx - size, cy - size * 0.6);
    ctx.lineTo(cx, cy + size * 0.6);
    ctx.lineTo(cx + size, cy - size * 0.6);
    ctx.stroke();
  }

  function drawBokeh(ctx, cx, cy, r, rgb, alpha) {
    const g = ctx.createRadialGradient(cx, cy, r * 0.45, cx, cy, r);
    g.addColorStop(0, `rgba(${rgb},0)`);
    g.addColorStop(0.72, `rgba(${rgb},${alpha})`);
    g.addColorStop(1, `rgba(${rgb},0)`);
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
  }

  const canvas = document.getElementById('bgCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  let w = 0, h = 0, nodes = [], accentLines = [], hexAccents = [], chevAccents = [], bokeh = [];
  let lastTime = 0, rafId = null;

  function initField() {
    const dpr = window.devicePixelRatio || 1;
    w = window.innerWidth;
    h = window.innerHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const rand = mulberry32(1337);
    const nodeCount = Math.max(24, Math.round((w * h) / 32000));
    const SPEED = 9;
    nodes = Array.from({ length: nodeCount }, () => {
      const angle = rand() * Math.PI * 2;
      const speed = SPEED * (0.4 + rand() * 0.9);
      return { x: rand() * w, y: rand() * h, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed };
    });

    accentLines = Array.from({ length: 5 }, () => ({
      x1: rand() * w,
      x2: rand() * w,
      drift: (rand() - 0.5) * 5,
    }));

    hexAccents = [
      { cx: w * 0.88, cy: h * 0.12, r: Math.min(52, w * 0.05), color: 'rgba(240,160,32,0.2)', rot: 0, rotSpeed: 0.05 },
      { cx: w * 0.08, cy: h * 0.82, r: Math.min(34, w * 0.035), color: 'rgba(58,52,42,0.45)', rot: 0, rotSpeed: -0.04 },
      { cx: w * 0.5, cy: h * 0.94, r: 24, color: 'rgba(58,52,42,0.45)', rot: 0, rotSpeed: 0.03 },
    ];
    chevAccents = [
      { cx: w * 0.94, cy: h * 0.55, size: 16, color: 'rgba(240,160,32,0.2)', bob: 0 },
      { cx: w * 0.05, cy: h * 0.28, size: 14, color: 'rgba(58,52,42,0.45)', bob: Math.PI },
    ];

    bokeh = Array.from({ length: 7 }, (_, i) => {
      const angle = rand() * Math.PI * 2;
      const speed = 3.5 * (0.3 + rand() * 0.8);
      const warm = i < 5;
      return {
        x: rand() * w,
        y: h * (0.35 + rand() * 0.65),
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        r: 46 + rand() * 90,
        rgb: warm ? '240,160,32' : '150,175,168',
        alpha: warm ? 0.05 + rand() * 0.06 : 0.03 + rand() * 0.03,
      };
    });
  }

  function step(timestamp) {
    const dt = lastTime ? Math.min((timestamp - lastTime) / 1000, 0.05) : 0;
    lastTime = timestamp;
    ctx.clearRect(0, 0, w, h);

    nodes.forEach((n) => {
      n.x += n.vx * dt;
      n.y += n.vy * dt;
      if (n.x < -20) n.x = w + 20; else if (n.x > w + 20) n.x = -20;
      if (n.y < -20) n.y = h + 20; else if (n.y > h + 20) n.y = -20;
    });

    bokeh.forEach((b) => {
      b.x += b.vx * dt;
      b.y += b.vy * dt;
      if (b.x < -b.r) b.x = w + b.r; else if (b.x > w + b.r) b.x = -b.r;
      if (b.y < -b.r) b.y = h + b.r; else if (b.y > h + b.r) b.y = -b.r;
      drawBokeh(ctx, b.x, b.y, b.r, b.rgb, b.alpha);
    });

    ctx.strokeStyle = 'rgba(58, 52, 42, 0.3)';
    ctx.lineWidth = 1;
    nodes.forEach((node, i) => {
      nodes
        .map((other, j) => [other, j, (other.x - node.x) ** 2 + (other.y - node.y) ** 2])
        .filter(([, j]) => j !== i)
        .sort((a, b) => a[2] - b[2])
        .slice(0, 2)
        .forEach(([other]) => {
          ctx.beginPath();
          ctx.moveTo(node.x, node.y);
          ctx.lineTo(other.x, other.y);
          ctx.stroke();
        });
    });

    ctx.strokeStyle = 'rgba(240, 160, 32, 0.15)';
    accentLines.forEach((line) => {
      line.x1 += line.drift * dt;
      line.x2 -= line.drift * dt;
      if (line.x1 < -60) line.x1 = w + 60; else if (line.x1 > w + 60) line.x1 = -60;
      if (line.x2 < -60) line.x2 = w + 60; else if (line.x2 > w + 60) line.x2 = -60;
      ctx.beginPath();
      ctx.moveTo(line.x1, 0);
      ctx.lineTo(line.x2, h);
      ctx.stroke();
    });

    ctx.lineWidth = 1.2;
    hexAccents.forEach((hx) => {
      hx.rot += hx.rotSpeed * dt;
      ctx.strokeStyle = hx.color;
      drawHexagon(ctx, hx.cx, hx.cy, hx.r, hx.rot);
    });

    chevAccents.forEach((ch) => {
      ch.bob += dt * 0.6;
      ctx.strokeStyle = ch.color;
      drawChevron(ctx, ch.cx, ch.cy + Math.sin(ch.bob) * 6, ch.size);
    });

    if (!reduceMotion) rafId = requestAnimationFrame(step);
  }

  initField();
  if (reduceMotion) {
    step(0);
  } else {
    rafId = requestAnimationFrame(step);
  }

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (rafId) cancelAnimationFrame(rafId);
      lastTime = 0;
      initField();
      if (reduceMotion) step(0); else rafId = requestAnimationFrame(step);
    }, 120);
  });
})();
