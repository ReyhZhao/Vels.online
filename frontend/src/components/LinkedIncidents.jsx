import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/axios';

const SEVERITY_CLASSES = {
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  high:     'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  medium:   'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  low:      'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  info:     'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400',
};

const STATE_CLASSES = {
  new:         'text-blue-600 dark:text-blue-400',
  triaged:     'text-purple-600 dark:text-purple-400',
  in_progress: 'text-yellow-600 dark:text-yellow-400',
  on_hold:     'text-orange-600 dark:text-orange-400',
  pending_closure: 'text-teal-600 dark:text-teal-400',
  resolved:    'text-green-600 dark:text-green-400',
  closed:      'text-muted-foreground',
};

// Longest scalar value we'll use as a linking key. Beyond this a value is a
// blob (a Wazuh alert's full_log / raw message text), not an identifier.
const MAX_KEY_VALUE_LEN = 120;

// The backend `source_ref_contains` filter AND-matches each entry as a
// top-level scalar equality, so only short scalar fields are useful linking
// keys — nested objects/arrays get JSON-exact-matched and never find siblings.
// Sending the whole source_ref also blows the query string past the proxy's
// HTTP/2 header limit for Wazuh-event incidents (full_log / all_fields blobs),
// which resets the shared connection and kills the page's sibling requests.
function identifyingRef(sourceRef) {
  const out = {};
  for (const [k, v] of Object.entries(sourceRef ?? {})) {
    if (v == null || typeof v === 'object') continue;
    if (String(v).length > MAX_KEY_VALUE_LEN) continue;
    out[k] = v;
  }
  return out;
}

export default function LinkedIncidents({ sourceKind, sourceRef, excludeId }) {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const ref = identifyingRef(sourceRef);
    if (Object.keys(ref).length === 0) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    const params = new URLSearchParams({
      source_kind: sourceKind,
      source_ref_contains: JSON.stringify(ref),
    });
    api.get(`/api/incidents/?${params}`)
      .then(res => { if (!cancelled) setIncidents(res.data.results ?? res.data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [sourceKind, JSON.stringify(sourceRef)]); // eslint-disable-line react-hooks/exhaustive-deps

  // On an incident's own page, drop the incident itself from the sibling list.
  const linked = excludeId != null
    ? incidents.filter(inc => inc.id !== excludeId)
    : incidents;

  if (loading || linked.length === 0) return null;

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Linked Incidents
      </p>
      <div className="space-y-1.5">
        {linked.map(inc => (
          <Link
            key={inc.id}
            to={`/incidents/${inc.display_id}`}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent transition-colors"
          >
            <span className="font-mono text-xs text-muted-foreground shrink-0">{inc.display_id}</span>
            <span className="flex-1 truncate text-foreground">{inc.title}</span>
            {inc.severity && (
              <span className={`shrink-0 inline-flex items-center rounded-full px-1.5 py-0.5 text-xs font-medium ${SEVERITY_CLASSES[inc.severity] ?? ''}`}>
                {inc.severity}
              </span>
            )}
            <span className={`shrink-0 text-xs font-medium ${STATE_CLASSES[inc.state] ?? 'text-muted-foreground'}`}>
              {inc.state.replace('_', ' ')}
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
