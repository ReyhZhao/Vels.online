function formatDuration(absSeconds) {
  if (absSeconds < 3600) return `${Math.round(absSeconds / 60)}m`;
  if (absSeconds < 86400) return `${Math.round(absSeconds / 3600)}h`;
  return `${Math.round(absSeconds / 86400)}d`;
}

const SHORT_LABELS = {
  'Response SLA': 'R',
  'Resolve SLA': 'Rs',
};

export default function SLAPill({ sla, label, compact = false }) {
  if (!sla || !sla.applies) return null;

  const { remaining_seconds, target_seconds, breached } = sla;
  const fractionLeft = remaining_seconds / target_seconds;

  let cls, fullText, shortText;
  if (breached) {
    cls = 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400';
    const ago = formatDuration(-remaining_seconds);
    fullText = `${label}: BREACHED ${ago} ago`;
    shortText = `${SHORT_LABELS[label] ?? label}:!${ago}`;
  } else if (fractionLeft < 0.25) {
    cls = 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400';
    const left = formatDuration(remaining_seconds);
    fullText = `${label}: ${left} left`;
    shortText = `${SHORT_LABELS[label] ?? label}:${left}`;
  } else {
    cls = 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400';
    const left = formatDuration(remaining_seconds);
    fullText = `${label}: ${left} left`;
    shortText = `${SHORT_LABELS[label] ?? label}:${left}`;
  }

  return (
    <span
      title={compact ? fullText : undefined}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${cls}`}
    >
      {compact ? shortText : fullText}
    </span>
  );
}
