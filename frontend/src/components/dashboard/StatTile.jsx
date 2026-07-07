import { Link } from 'react-router-dom';

function Sparkline({ points, color = '#64748b' }) {
  if (!points || points.length < 2) return null;
  const w = 72;
  const h = 24;
  const max = Math.max(...points, 1);
  const step = w / (points.length - 1);
  const coords = points.map((v, i) => `${(i * step).toFixed(1)},${(h - 2 - (v / max) * (h - 4)).toFixed(1)}`);
  const last = coords[coords.length - 1].split(',');
  return (
    <svg width={w} height={h} aria-hidden="true" className="shrink-0">
      <polyline
        points={coords.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={last[0]} cy={last[1]} r="3" fill="#3987e5" stroke="hsl(220 50% 11%)" strokeWidth="2" />
    </svg>
  );
}

/**
 * KPI stat tile: label, big value, optional signed delta ("+3 this week"),
 * optional sparkline. The whole tile links through to its detail page.
 */
export default function StatTile({ label, value, delta, deltaGood, sub, trend, to, isLoading, accent }) {
  const body = (
    <>
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <div className="mt-1 flex items-end justify-between gap-2">
        <p className={`text-3xl font-semibold leading-none ${accent ?? 'text-foreground'}`}>
          {isLoading ? (
            <span className="text-base font-normal text-muted-foreground" aria-label="loading">…</span>
          ) : (
            value ?? '—'
          )}
        </p>
        {!isLoading && trend && <Sparkline points={trend} />}
      </div>
      <p className="mt-1.5 min-h-[1rem] text-xs text-muted-foreground">
        {!isLoading && delta != null && (
          <span className={deltaGood == null ? '' : deltaGood ? 'text-emerald-500' : 'text-red-400'}>
            {delta}
          </span>
        )}
        {!isLoading && delta != null && sub && ' · '}
        {!isLoading && sub}
      </p>
    </>
  );

  const cls = 'block rounded-lg border border-border bg-card p-4 transition-colors';
  if (to) {
    return (
      <Link to={to} className={`${cls} hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring outline-none`}>
        {body}
      </Link>
    );
  }
  return <div className={cls}>{body}</div>;
}
