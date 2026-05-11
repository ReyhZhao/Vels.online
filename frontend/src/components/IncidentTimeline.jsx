import { useState, useEffect, useCallback } from 'react';
import api from '../lib/axios';

// ── kind renderers ────────────────────────────────────────────────────────────
// Each is a pure function: (payload) => string | null

export function renderIncidentUpdated(payload) {
  const changes = payload?.changes;
  if (!changes || Object.keys(changes).length === 0) return 'Incident updated.';
  const parts = Object.entries(changes).map(([field, diff]) => {
    const label = field.replace(/_/g, ' ');
    return `${label}: ${diff.old ?? '—'} → ${diff.new ?? '—'}`;
  });
  return parts.join(' · ');
}

export function renderCommentAdded(payload) {
  const target = payload?.target_id ? `#${payload.target_id}` : '';
  const internal = payload?.is_internal ? ' (internal)' : '';
  return `Comment added${target ? ` ${target}` : ''}${internal}.`;
}

export function renderCommentEdited(payload) {
  const target = payload?.target_id ? ` #${payload.target_id}` : '';
  return `Comment${target} edited.`;
}

export function renderCommentDeleted(payload) {
  const target = payload?.target_id ? ` #${payload.target_id}` : '';
  return `Comment${target} deleted.`;
}

export function renderIncidentDelegated(payload) {
  const delegate = payload?.delegate_id ? `user #${payload.delegate_id}` : 'someone';
  const note = payload?.note ? ` — "${payload.note}"` : '';
  return `Delegated to ${delegate}${note}.`;
}

export function renderIncidentDelegationReturned(payload) {
  const delegate = payload?.delegate_id ? `user #${payload.delegate_id}` : 'delegate';
  return `${delegate} returned the delegation.`;
}

export function renderIncidentAssigneeChanged(payload) {
  const from = payload?.from != null ? `#${payload.from}` : '(unassigned)';
  const to = payload?.to != null ? `#${payload.to}` : '(unassigned)';
  return `Transferred from ${from} to ${to}.`;
}

export function renderTemplateApplied(payload) {
  const name = payload?.template_name ?? `template #${payload?.template_id ?? '?'}`;
  return `Template applied: ${name}.`;
}

export function renderTaskCreated(payload) {
  const title = payload?.title ?? `task #${payload?.task_id ?? '?'}`;
  return `Task created: "${title}".`;
}

export function renderTaskStateChanged(payload) {
  const title = payload?.title ?? `task #${payload?.task_id ?? '?'}`;
  return `Task "${title}": ${payload?.old ?? '?'} → ${payload?.new ?? '?'}.`;
}

export function renderTaskAutoCancelled(payload) {
  const count = payload?.count;
  return count != null ? `${count} task(s) auto-cancelled.` : 'Tasks auto-cancelled.';
}

export function renderExceptionCreated(payload) {
  const desc = payload?.description ? `"${payload.description}"` : `rule #${payload?.wazuh_rule_id ?? '?'}`;
  return `Exception rule created: ${desc}.`;
}

const KIND_RENDERERS = {
  incident_updated: renderIncidentUpdated,
  incident_created: () => 'Incident created.',
  comment_added: renderCommentAdded,
  comment_edited: renderCommentEdited,
  comment_deleted: renderCommentDeleted,
  incident_delegated: renderIncidentDelegated,
  incident_delegation_returned: renderIncidentDelegationReturned,
  incident_assignee_changed: renderIncidentAssigneeChanged,
  incident_template_applied: renderTemplateApplied,
  incident_template_reapplied: renderTemplateApplied,
  task_created: renderTaskCreated,
  task_state_changed: renderTaskStateChanged,
  task_auto_cancelled: renderTaskAutoCancelled,
  exception_created: renderExceptionCreated,
};

export function renderEvent(kind, payload) {
  const renderer = KIND_RENDERERS[kind];
  if (renderer) return renderer(payload);
  return `Event: ${kind}.`;
}

// ── component ─────────────────────────────────────────────────────────────────

function RelativeTime({ isoString }) {
  const date = new Date(isoString);
  const diff = Math.floor((Date.now() - date.getTime()) / 1000);
  let label;
  if (diff < 60) label = 'just now';
  else if (diff < 3600) label = `${Math.floor(diff / 60)}m ago`;
  else if (diff < 86400) label = `${Math.floor(diff / 3600)}h ago`;
  else label = `${Math.floor(diff / 86400)}d ago`;
  return (
    <time dateTime={isoString} title={date.toLocaleString()} className="text-xs text-muted-foreground shrink-0">
      {label}
    </time>
  );
}

function TimelineRow({ event }) {
  const message = renderEvent(event.kind, event.payload);
  return (
    <li className="flex items-start gap-3 py-2">
      <div className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-border" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-foreground">{message}</p>
        {event.actor_username && (
          <p className="text-xs text-muted-foreground">{event.actor_username}</p>
        )}
      </div>
      <RelativeTime isoString={event.created_at} />
    </li>
  );
}

export default function IncidentTimeline({ incidentId }) {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async (p) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(`/api/incidents/${incidentId}/timeline/?page=${p}`);
      setData(res.data);
      setPage(p);
    } catch (err) {
      if (err.response?.status === 403) {
        setError('Timeline not available at this classification level.');
      } else {
        setError('Failed to load timeline.');
      }
    } finally {
      setLoading(false);
    }
  }, [incidentId]);

  useEffect(() => { load(1); }, [load]);

  if (loading) return <p className="text-sm text-muted-foreground">Loading timeline…</p>;
  if (error) return <p className="text-sm text-muted-foreground italic">{error}</p>;
  if (!data) return null;

  const totalPages = Math.ceil(data.count / data.page_size);

  return (
    <div className="space-y-2">
      <h2 className="text-base font-semibold text-foreground">Timeline</h2>
      {data.results.length === 0 ? (
        <p className="text-sm text-muted-foreground">No events yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {data.results.map(event => (
            <TimelineRow key={event.id} event={event} />
          ))}
        </ul>
      )}
      {totalPages > 1 && (
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={() => load(page - 1)}
            disabled={page <= 1}
            className="text-sm text-muted-foreground hover:text-foreground disabled:opacity-40"
          >
            ← Newer
          </button>
          <span className="text-xs text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => load(page + 1)}
            disabled={page >= totalPages}
            className="text-sm text-muted-foreground hover:text-foreground disabled:opacity-40"
          >
            Older →
          </button>
        </div>
      )}
    </div>
  );
}
