// CanvasMap — the d3-geo equirectangular canvas world map with glowing animated arcs
// (PRD #594). Lifted from the prototype's validated canvas-glow renderer into the real
// page. Takes the live `events` array (arc payloads from the SSE stream) as a prop and
// owns its own requestAnimationFrame loop and projection; it is intentionally opaque to
// jsdom, so surrounding chrome (stat strip, panels, feed) is what the page tests assert.
import { useEffect, useRef } from 'react';
import { geoEquirectangular, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import worldTopo from 'world-atlas/countries-110m.json';

const LAND = feature(worldTopo, worldTopo.objects.countries).features;
const ARC_MS = 1600; // arc travel time
const FADE_MS = 900; // post-impact fade
const MAX_ARCS = 400; // animated-arc pool cap (perf bound)

function bezier(t, p0, c, p1) {
  const u = 1 - t;
  return [
    u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
    u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1],
  ];
}

export default function CanvasMap({ events }) {
  const canvasRef = useRef(null);
  const wrapRef = useRef(null);
  const arcsRef = useRef([]); // active animated arcs (canvas-owned, not React state)
  const lastSeq = useRef(-1);
  const projRef = useRef(null);
  const baseRef = useRef(null); // offscreen basemap

  // Feed → canvas arc pool: add any events newer than the last we ingested.
  useEffect(() => {
    const proj = projRef.current;
    if (!proj || !events?.length) return;
    const fresh = events.filter((e) => e.seq > lastSeq.current);
    if (fresh.length) lastSeq.current = Math.max(...fresh.map((e) => e.seq));
    for (const e of fresh) {
      const p0 = proj([e.srcLng, e.srcLat]);
      const p1 = proj([e.dstLng, e.dstLat]);
      if (!p0 || !p1) continue;
      const mid = [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
      const dx = p1[0] - p0[0];
      const dy = p1[1] - p0[1];
      const len = Math.hypot(dx, dy);
      const c = [mid[0] - dy * 0.22, mid[1] + dx * 0.22 - len * 0.12];
      arcsRef.current.push({ p0, c, p1, color: e.color, born: performance.now(), level: e.level });
    }
    if (arcsRef.current.length > MAX_ARCS) arcsRef.current = arcsRef.current.slice(-MAX_ARCS);
  }, [events]);

  // Build projection + offscreen basemap; rebuild on resize.
  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    if (!wrap || !canvas) return undefined;
    let raf;

    function setup() {
      const w = wrap.clientWidth;
      const h = wrap.clientHeight;
      if (!w || !h) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;

      const proj = geoEquirectangular().fitSize([w, h], { type: 'Sphere' });
      projRef.current = proj;

      const base = document.createElement('canvas');
      base.width = w * dpr;
      base.height = h * dpr;
      const bctx = base.getContext('2d');
      if (!bctx) return;
      bctx.scale(dpr, dpr);
      const path = geoPath(proj, bctx);
      bctx.fillStyle = '#0a1424';
      bctx.fillRect(0, 0, w, h);
      bctx.beginPath();
      path({ type: 'FeatureCollection', features: LAND });
      bctx.fillStyle = '#15233d';
      bctx.fill();
      bctx.lineWidth = 0.5;
      bctx.strokeStyle = '#24375c';
      bctx.stroke();
      baseRef.current = { base, w, h, dpr };
    }

    function frame(now) {
      const ctx = canvas.getContext('2d');
      const meta = baseRef.current;
      if (!ctx || !meta) { raf = requestAnimationFrame(frame); return; }
      const { base, dpr } = meta;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(base, 0, 0);
      ctx.scale(dpr, dpr);
      ctx.globalCompositeOperation = 'lighter'; // additive glow

      const alive = [];
      for (const a of arcsRef.current) {
        const age = now - a.born;
        if (age > ARC_MS + FADE_MS) continue;
        alive.push(a);
        const p = Math.min(1, age / ARC_MS);

        ctx.beginPath();
        ctx.moveTo(a.p0[0], a.p0[1]);
        ctx.quadraticCurveTo(a.c[0], a.c[1], a.p1[0], a.p1[1]);
        ctx.strokeStyle = a.color;
        ctx.globalAlpha = 0.12 * (1 - Math.max(0, age - ARC_MS) / FADE_MS);
        ctx.lineWidth = a.level >= 13 ? 1.6 : 1;
        ctx.stroke();

        if (p < 1) {
          const head = bezier(p, a.p0, a.c, a.p1);
          const tail = bezier(Math.max(0, p - 0.18), a.p0, a.c, a.p1);
          const grad = ctx.createLinearGradient(tail[0], tail[1], head[0], head[1]);
          grad.addColorStop(0, 'rgba(0,0,0,0)');
          grad.addColorStop(1, a.color);
          ctx.beginPath();
          ctx.moveTo(tail[0], tail[1]);
          ctx.lineTo(head[0], head[1]);
          ctx.strokeStyle = grad;
          ctx.globalAlpha = 0.95;
          ctx.lineWidth = a.level >= 13 ? 2.4 : 1.6;
          ctx.shadowBlur = 12;
          ctx.shadowColor = a.color;
          ctx.stroke();
          ctx.shadowBlur = 0;
          ctx.beginPath();
          ctx.arc(head[0], head[1], 1.8, 0, Math.PI * 2);
          ctx.fillStyle = a.color;
          ctx.fill();
        } else {
          const ring = (age - ARC_MS) / FADE_MS;
          ctx.beginPath();
          ctx.arc(a.p1[0], a.p1[1], 2 + ring * 14, 0, Math.PI * 2);
          ctx.strokeStyle = a.color;
          ctx.globalAlpha = 0.5 * (1 - ring);
          ctx.lineWidth = 1.2;
          ctx.shadowBlur = 8;
          ctx.shadowColor = a.color;
          ctx.stroke();
          ctx.shadowBlur = 0;
        }
      }
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';
      arcsRef.current = alive;
      raf = requestAnimationFrame(frame);
    }

    setup();
    raf = requestAnimationFrame(frame);
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(setup) : null;
    if (ro) ro.observe(wrap);
    return () => { cancelAnimationFrame(raf); if (ro) ro.disconnect(); };
  }, []);

  return (
    <div ref={wrapRef} className="relative h-full w-full overflow-hidden bg-[#0a1424]">
      <canvas ref={canvasRef} className="absolute inset-0" data-testid="attack-canvas" />
    </div>
  );
}
