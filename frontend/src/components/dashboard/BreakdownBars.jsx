import { useNavigate } from 'react-router-dom';

/**
 * Horizontal bar list for a small categorical breakdown (severity, state).
 * Each row is a full-width hit target that drills into the filtered list;
 * labels and values stay in text tokens, only the bar carries the color.
 *
 * `items`: [{ key, label, count, color, to }]
 */
export default function BreakdownBars({ items, ariaLabel }) {
  const navigate = useNavigate();
  const max = Math.max(...items.map(i => i.count), 1);
  const total = items.reduce((a, i) => a + i.count, 0);

  if (total === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Nothing open. 🎉</p>;
  }

  return (
    <ul className="space-y-1" aria-label={ariaLabel}>
      {items.map(item => (
        <li key={item.key}>
          <button
            type="button"
            onClick={item.to ? () => navigate(item.to) : undefined}
            disabled={!item.to}
            title={item.to ? `View ${item.label.toLowerCase()}` : undefined}
            className="group grid w-full grid-cols-[7rem_1fr_2.5rem] items-center gap-2 rounded px-1 py-1 text-left transition-colors enabled:hover:bg-accent/60 enabled:cursor-pointer"
          >
            <span className="truncate text-xs text-muted-foreground group-hover:text-foreground">
              {item.label}
            </span>
            <span className="relative h-3 overflow-hidden rounded-r-[4px]">
              <span
                className="absolute inset-y-0 left-0 rounded-r-[4px] transition-all"
                style={{
                  width: `${(item.count / max) * 100}%`,
                  minWidth: item.count > 0 ? '3px' : 0,
                  backgroundColor: item.color,
                }}
              />
            </span>
            <span className="text-right text-xs font-medium tabular-nums text-foreground">
              {item.count}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
