// Live Attack Map side-panel atoms (PRD #594). Colour comes from the arc payload
// (`color`), resolved server-side from the severity band — the panels never recompute
// severity. Folded in from the prototype's panels, rewritten to production standards.

export function SeverityDot({ color }) {
  return (
    <span
      className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}` }}
    />
  );
}

export function CounterStat({ label, value, accent }) {
  return (
    <div>
      <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={`mt-0.5 text-2xl font-bold tabular-nums ${accent ?? 'text-foreground'}`}>{value}</p>
    </div>
  );
}

// Horizontal bar list (top source countries / top attack types). `rows` is [[label, count], ...].
export function BarList({ rows, barClass = 'bg-primary', emptyLabel = 'No data yet' }) {
  if (!rows?.length) {
    return <p className="text-xs text-muted-foreground">{emptyLabel}</p>;
  }
  const max = Math.max(1, ...rows.map((r) => r[1]));
  return (
    <ul className="space-y-1.5">
      {rows.map(([label, count]) => (
        <li key={label} className="text-xs">
          <div className="mb-0.5 flex items-center justify-between">
            <span className="truncate text-foreground/90">{label}</span>
            <span className="ml-2 tabular-nums text-muted-foreground">{count}</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
            <div
              className={`h-full rounded-full ${barClass} transition-all duration-300`}
              style={{ width: `${(count / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString();
}

// Scrolling recent-attack feed (source country → target org, type, severity, time).
export function RecentFeed({ feed }) {
  if (!feed?.length) {
    return <p className="p-2 text-xs text-muted-foreground">Waiting for attacks…</p>;
  }
  return (
    <table className="w-full text-xs">
      <tbody>
        {feed.map((e) => (
          <tr key={e.seq} className="border-b border-border/50 last:border-0">
            <td className="py-1 pr-2"><SeverityDot color={e.color} /></td>
            <td className="py-1 pr-2 font-mono text-[10px] text-muted-foreground">L{e.level}</td>
            <td className="py-1 pr-2 text-muted-foreground">{e.srcCountry}</td>
            <td className="py-1 pr-2">→ {e.dstOrg}</td>
            <td className="py-1 pr-2 text-muted-foreground">{e.attackType}</td>
            <td className="py-1 text-right text-[10px] text-muted-foreground tabular-nums">{formatTime(e.ts)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
