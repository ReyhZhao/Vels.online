import { worstSla, formatSlaDuration } from '../lib/sla';

// A compact SLA countdown bar: fill = fraction of time left, colour = urgency
// (green healthy → amber < 25% left → red breached). Hover shows the detail for
// both the response and resolve SLAs so nothing is lost versus the old pills.
function detail(sla, label) {
  if (!sla || !sla.applies) return null;
  return sla.breached
    ? `${label}: breached ${formatSlaDuration(sla.remaining_seconds)} ago`
    : `${label}: ${formatSlaDuration(sla.remaining_seconds)} left`;
}

export default function SLABar({ incident }) {
  const worst = worstSla(incident);
  const title =
    [detail(incident.response_sla, 'Response'), detail(incident.resolve_sla, 'Resolve')]
      .filter(Boolean)
      .join(' · ') || 'No active SLA';

  if (!worst) {
    return <div className="h-1.5 w-full rounded-full bg-muted" title={title} />;
  }

  const frac = Math.max(0, Math.min(1, worst.fraction));
  const color = worst.breached ? 'bg-red-500' : frac < 0.25 ? 'bg-amber-500' : 'bg-green-500';
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted" title={title}>
      <div className={`h-full ${color}`} style={{ width: `${worst.breached ? 100 : frac * 100}%` }} />
    </div>
  );
}
