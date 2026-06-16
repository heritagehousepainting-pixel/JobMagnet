/* ============================================================================
   JobMagnet — public-site motion (Firecrawl-inspired, adapted to our brand).
   Vanilla, no dependencies, deferred. Everything here is gated on
   prefers-reduced-motion: when the user asks for less motion, content is shown
   immediately, numbers jump to final, and the ember field renders one static
   frame (no animation loop). Zero layout shift — motion only touches opacity,
   transform, and a decorative <canvas>.
   ============================================================================ */
(function () {
  'use strict';
  var REDUCE = !window.matchMedia ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var HAS_IO = 'IntersectionObserver' in window;

  /* ---------------------------------------------------------------- reveal */
  // The <head> already added .js-reveal to <html> (only when motion is allowed
  // and IO exists), so [data-reveal] elements start hidden with no flash. Here
  // we assign stagger delays and reveal each element as it enters the viewport.
  function setupReveal() {
    // stagger: each [data-reveal] inside a [data-reveal-stagger] gets a delay
    document.querySelectorAll('[data-reveal-stagger]').forEach(function (group) {
      var step = parseInt(group.getAttribute('data-reveal-stagger'), 10) || 70;
      group.querySelectorAll('[data-reveal]').forEach(function (el, i) {
        el.style.setProperty('--reveal-delay', (i * step) + 'ms');
      });
    });

    var items = Array.prototype.slice.call(document.querySelectorAll('[data-reveal]'));
    // auto containers: reveal each direct child with a gentle stagger. Lets the
    // signed-in app opt every page in with one attribute and no per-template edits.
    document.querySelectorAll('[data-reveal-auto]').forEach(function (c) {
      var step = parseInt(c.getAttribute('data-reveal-auto'), 10) || 80;
      Array.prototype.forEach.call(c.children, function (kid, i) {
        kid.style.setProperty('--reveal-delay', (Math.min(i, 8) * step) + 'ms');
        items.push(kid);
      });
    });

    if (REDUCE || !HAS_IO) {
      items.forEach(function (el) { el.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });
    items.forEach(function (el) { io.observe(el); });
  }

  /* --------------------------------------------------------------- countup */
  function animateCount(el) {
    var raw = el.getAttribute('data-countup');
    var target = parseFloat(raw);
    if (isNaN(target)) { return; }
    var prefix = el.getAttribute('data-prefix') || '';
    var suffix = el.getAttribute('data-suffix') || '';
    if (REDUCE) { el.textContent = prefix + raw + suffix; return; }
    var start = null, dur = 1100;
    function frame(t) {
      if (start === null) { start = t; }
      var p = Math.min((t - start) / dur, 1);
      var eased = 1 - Math.pow(1 - p, 3);            // easeOutCubic
      el.textContent = prefix + Math.round(eased * target) + suffix;
      if (p < 1) { requestAnimationFrame(frame); }
      else { el.textContent = prefix + raw + suffix; }
    }
    requestAnimationFrame(frame);
  }
  function setupCountup() {
    var nodes = document.querySelectorAll('[data-countup]');
    if (!nodes.length) { return; }
    if (REDUCE || !HAS_IO) { nodes.forEach(animateCount); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { animateCount(e.target); io.unobserve(e.target); }
      });
    }, { threshold: 0.6 });
    nodes.forEach(function (el) { io.observe(el); });
  }

  /* ------------------------------------------------------------ ember field */
  // A subtle emerald dot/ember field with a few twinkling "+" crosshairs — the
  // "alive" technical texture, in our brand. Drifts slowly upward like embers.
  function EmberField(canvas) {
    var ctx = canvas.getContext('2d');
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = 0, h = 0, dots = [], crosses = [], raf = 0, running = false, t0 = 0;

    function rand(a, b) { return a + Math.random() * (b - a); }

    function build() {
      var rect = canvas.getBoundingClientRect();
      w = Math.max(1, rect.width); h = Math.max(1, rect.height);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // density scales with area, capped for performance
      var n = Math.min(90, Math.round((w * h) / 14000));
      dots = [];
      for (var i = 0; i < n; i++) {
        dots.push({
          x: rand(0, w), y: rand(0, h), r: rand(0.6, 1.8),
          vy: rand(6, 20),                 // px/sec upward drift
          sway: rand(8, 26), sp: rand(0.2, 0.7), ph: rand(0, Math.PI * 2),
          tw: rand(0.4, 1), tsp: rand(0.6, 1.6)
        });
      }
      // a handful of crosshair markers on a loose grid
      crosses = [];
      var gx = 5, gy = 3;
      for (var a = 1; a < gx; a++) {
        for (var b = 1; b < gy; b++) {
          if (Math.random() < 0.55) {
            crosses.push({ x: (a / gx) * w + rand(-20, 20), y: (b / gy) * h + rand(-16, 16),
              ph: rand(0, Math.PI * 2), tsp: rand(0.5, 1.1), s: rand(4, 6) });
          }
        }
      }
    }

    function drawDot(d, time) {
      var x = d.x + Math.sin(time * d.sp + d.ph) * d.sway;
      var y = d.y - (time * d.vy);
      // wrap vertically (ember rising)
      y = ((y % (h + 40)) + (h + 40)) % (h + 40) - 20;
      var a = 0.18 + 0.32 * (0.5 + 0.5 * Math.sin(time * d.tsp + d.ph)) * d.tw;
      ctx.beginPath();
      ctx.arc(x, y, d.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(16,185,129,' + a.toFixed(3) + ')';
      ctx.fill();
    }

    function drawCross(c, time) {
      var a = 0.10 + 0.22 * (0.5 + 0.5 * Math.sin(time * c.tsp + c.ph));
      ctx.strokeStyle = 'rgba(52,211,153,' + a.toFixed(3) + ')';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(c.x - c.s, c.y); ctx.lineTo(c.x + c.s, c.y);
      ctx.moveTo(c.x, c.y - c.s); ctx.lineTo(c.x, c.y + c.s);
      ctx.stroke();
    }

    function render(time) {
      ctx.clearRect(0, 0, w, h);
      for (var i = 0; i < crosses.length; i++) { drawCross(crosses[i], time); }
      for (var j = 0; j < dots.length; j++) { drawDot(dots[j], time); }
    }

    function loop(now) {
      if (!running) { return; }
      render((now - t0) / 1000);
      raf = requestAnimationFrame(loop);
    }
    function start() {
      if (running || REDUCE) { return; }
      running = true; t0 = performance.now(); raf = requestAnimationFrame(loop);
    }
    function stop() { running = false; if (raf) { cancelAnimationFrame(raf); raf = 0; } }

    build();
    render(0); // paint one frame immediately (also the reduced-motion still)

    // pause when offscreen or tab hidden
    if (HAS_IO) {
      new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { e.isIntersecting ? start() : stop(); });
      }, { threshold: 0 }).observe(canvas);
    } else { start(); }
    document.addEventListener('visibilitychange', function () {
      document.hidden ? stop() : start();
    });
    var rt;
    window.addEventListener('resize', function () {
      clearTimeout(rt); rt = setTimeout(function () { build(); render(0); }, 150);
    });
  }

  function setupEmber() {
    document.querySelectorAll('canvas[data-ember]').forEach(function (c) {
      try { EmberField(c); } catch (e) { /* decorative; never break the page */ }
    });
  }

  /* ----------------------------------------------------------------- start */
  function init() { setupReveal(); setupCountup(); setupEmber(); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else { init(); }
})();
