function formatDuration(absSeconds) {
  if (absSeconds < 3600) return `${Math.round(absSeconds / 60)}m`;
  if (absSeconds < 86400) return `${Math.round(absSeconds / 3600)}h`;
  return `${Math.round(absSeconds / 86400)}d`;
}

export default function SLAPill({ sla, label }) {
  if (!sla || !sla.applies) return null;

  const { remaining_seconds, target_seconds, breached } = sla;
  const fractionLeft = remaining_seconds / target_seconds;

  let cls, text;
  if (breached) {
    cls = 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
    text = `${label}: BREACHED ${formatDuration(-remaining_seconds)} ago`;
  } else if (fractionLeft < 0.25) {
    cls = 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400';
    text = `${label}: ${formatDuration(remaining_seconds)} left`;
  } else {
    cls = 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
    text = `${label}: ${formatDuration(remaining_seconds)} left`;
  }

  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${cls}`}>
      {text}
    </span>
  );
}
