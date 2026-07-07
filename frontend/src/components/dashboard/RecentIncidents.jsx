import { Link } from 'react-router-dom';
import { SEVERITY_COLORS } from './palette';

// Badge conventions mirror IncidentList so states/severities read the same
// everywhere.
const STATE_CLASSES = {
  new: 'text-blue-600 dark:text-blue-400',
  triaged: 'text-purple-600 dark:text-purple-400',
  in_progress: 'text-yellow-600 dark:text-yellow-400',
  on_hold: 'text-orange-600 dark:text-orange-400',
  needs_tuning: 'text-amber-600 dark:text-amber-400',
  pending_closure: 'text-teal-600 dark:text-teal-400',
};

const prettyState = s => s.replace(/_/g, ' ');

function relativeTime(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * The five most recent open incidents, straight off the overview payload.
 * A severity dot (with label in the row) keys each row; rows click through.
 */
export default function RecentIncidents({ incidents, loading }) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between px-4 pt-3 pb-1">
        <h3 className="text-sm font-medium text-foreground">Recent incidents</h3>
        <Link to="/incidents" className="text-xs font-medium text-primary hover:underline">
          View all
        </Link>
      </div>
      <div className="px-2 pb-2 pt-1">
        {loading ? (
          <p className="py-8 text-center text-sm text-muted-foreground" role="status">Loading…</p>
        ) : !incidents || incidents.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">No open incidents.</p>
        ) : (
          <ul>
            {incidents.map(inc => (
              <li key={inc.display_id}>
                <Link
                  to={`/incidents/${inc.display_id}`}
                  className="flex items-center gap-3 rounded-md px-2 py-2 transition-colors hover:bg-accent/60"
                >
                  <span
                    aria-hidden="true"
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: SEVERITY_COLORS[inc.severity] ?? SEVERITY_COLORS.info }}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-foreground">{inc.title}</span>
                    <span className="block text-xs text-muted-foreground">
                      {inc.display_id} · {inc.severity}
                      {inc.assignee ? ` · ${inc.assignee}` : ' · unassigned'}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className={`block text-xs font-medium capitalize ${STATE_CLASSES[inc.state] ?? 'text-foreground'}`}>
                      {prettyState(inc.state)}
                    </span>
                    <span className="block text-xs text-muted-foreground">{relativeTime(inc.created_at)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
