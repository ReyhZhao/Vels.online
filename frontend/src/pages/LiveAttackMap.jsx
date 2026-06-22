// Live Attack Map — staff-only, cross-org SOC console (PRD #594, ADR-0027).
//
// SOC-console layout (the prototype's chosen "hybrid" design, rewritten to production
// standards): a top stat strip, a full-width glowing CanvasMap with floating
// top-source-countries / top-attack-types panels, and a scrolling recent-attack feed.
// Arcs and stats stream over SSE from the shared presence-gated snapshot. A client-side
// severity up-filter lets a viewer cut noise without touching the backend or affecting
// other viewers (ADR-0027 — per-viewer server-side floors are out of scope).
import { useMemo, useState } from 'react';
import useAttackStream from '../hooks/useAttackStream';
import CanvasMap from '../components/attackmap/CanvasMap';
import { CounterStat, BarList, RecentFeed } from '../components/attackmap/panels';

const MAX_FEED = 60;

// Client-side severity thresholds. "All" honours the server floor; the rest filter higher.
const SEVERITY_FILTERS = [
  { label: 'All', value: 0 },
  { label: 'High ≥8', value: 8 },
  { label: 'Critical ≥12', value: 12 },
  { label: 'Severe ≥13', value: 13 },
];

function GlowPanel({ title, className, children }) {
  return (
    <div className={`pointer-events-auto w-52 rounded-lg border border-white/10 bg-black/40 p-3 backdrop-blur-sm ${className ?? ''}`}>
      <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-blue-300/70">{title}</p>
      {children}
    </div>
  );
}

export default function LiveAttackMap() {
  const { events, stats, connected } = useAttackStream();
  const [minLevel, setMinLevel] = useState(0);

  // Client-side severity up-filter: cheap, local, affects only this viewer.
  const visible = useMemo(
    () => (minLevel ? events.filter((e) => e.level >= minLevel) : events),
    [events, minLevel],
  );
  const feed = useMemo(() => [...visible].slice(-MAX_FEED).reverse(), [visible]);

  const topCountries = stats?.top_countries ?? [];
  const topTypes = stats?.top_attack_types ?? [];

  return (
    <div className="flex h-full w-full flex-col gap-3 overflow-auto p-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-lg font-semibold text-foreground">Live Attack Map</h1>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 text-xs ${connected ? 'text-emerald-500' : 'text-muted-foreground'}`}
          >
            <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-muted-foreground'}`} />
            {connected ? 'Live' : 'Reconnecting…'}
          </span>
          <label className="sr-only" htmlFor="severity-filter">Minimum severity</label>
          <select
            id="severity-filter"
            value={minLevel}
            onChange={(e) => setMinLevel(Number(e.target.value))}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {SEVERITY_FILTERS.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Top stat strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ['Attacks / min', stats?.per_minute ?? 0, 'text-red-400'],
          ['Window total (15m)', stats?.total ?? 0, 'text-foreground'],
          ['Live arcs', visible.length, 'text-amber-400'],
          ['Source countries', topCountries.length, 'text-blue-400'],
        ].map(([label, value, accent]) => (
          <div key={label} className="rounded-lg border border-border bg-card p-3">
            <CounterStat label={label} value={value} accent={accent} />
          </div>
        ))}
      </div>

      {/* Full-width glowing map with floating panels */}
      <div className="relative flex min-h-[420px] flex-1 flex-col overflow-hidden rounded-lg border border-border bg-[#0a1424]">
        <div className="border-b border-white/10 px-3 py-2 text-xs font-medium uppercase tracking-wider text-blue-300/70">
          Global inbound attacks
        </div>
        <div className="relative flex-1">
          <CanvasMap events={visible} />
          <GlowPanel title="Top source countries" className="absolute left-4 top-4">
            <BarList rows={topCountries} barClass="bg-red-500" />
          </GlowPanel>
          <GlowPanel title="Top attack types" className="absolute right-4 top-4">
            <BarList rows={topTypes} barClass="bg-orange-500" />
          </GlowPanel>
        </div>
      </div>

      {/* Recent-attack feed */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-3 py-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Recent attacks
        </div>
        <div className="max-h-44 overflow-y-auto p-2">
          <RecentFeed feed={feed} />
        </div>
      </div>
    </div>
  );
}
