import { useState, useEffect, useCallback } from 'react';
import {
  AlertCircle, FilePen, MessageSquare, Pencil, Trash2,
  UserCheck, CornerDownLeft, ArrowLeftRight, LayoutTemplate,
  SquareCheck, RefreshCw, CircleX, ShieldCheck, Mail, MailOpen,
} from 'lucide-react';
import api from '../lib/axios';

// ── kind renderers ────────────────────────────────────────────────────────────

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
  const from = payload?.from_username ?? (payload?.from != null ? `#${payload.from}` : null);
  const to = payload?.to_username ?? (payload?.to != null ? `#${payload.to}` : null);
  return `Transferred from ${from ?? '(unassigned)'} to ${to ?? '(unassigned)'}.`;
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

export function renderContactMessageSent(payload) {
  const name = payload?.contact_name ?? `contact #${payload?.contact_id ?? '?'}`;
  const role = payload?.role ? ` (${payload.role})` : '';
  return `Message sent to ${name}${role}.`;
}

export function renderContactMessageReceived(payload) {
  const name = payload?.contact_name ?? `contact #${payload?.contact_id ?? '?'}`;
  return `Reply received from ${name}.`;
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
  contact_message_sent: renderContactMessageSent,
  contact_message_received: renderContactMessageReceived,
};

export function renderEvent(kind, payload) {
  const renderer = KIND_RENDERERS[kind];
  if (renderer) return renderer(payload);
  return `Event: ${kind}.`;
}

// ── kind metadata ─────────────────────────────────────────────────────────────

const KIND_CONFIG = {
  incident_created:             { Icon: AlertCircle,    badge: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',       label: 'CREATED'   },
  incident_updated:             { Icon: FilePen,        badge: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',           label: 'UPDATED'   },
  comment_added:                { Icon: MessageSquare,  badge: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',          label: 'COMMENT'   },
  comment_edited:               { Icon: Pencil,         badge: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',          label: 'EDIT'      },
  comment_deleted:              { Icon: Trash2,         badge: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',          label: 'DELETE'    },
  incident_delegated:           { Icon: UserCheck,      badge: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',   label: 'DELEGATED' },
  incident_delegation_returned: { Icon: CornerDownLeft, badge: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300',   label: 'RETURNED'  },
  incident_assignee_changed:    { Icon: ArrowLeftRight, badge: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',   label: 'TRANSFER'  },
  incident_template_applied:    { Icon: LayoutTemplate, badge: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',           label: 'TEMPLATE'  },
  incident_template_reapplied:  { Icon: LayoutTemplate, badge: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',           label: 'TEMPLATE'  },
  task_created:                 { Icon: SquareCheck,    badge: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',   label: 'TASK'      },
  task_state_changed:           { Icon: RefreshCw,      badge: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',   label: 'TASK'      },
  task_auto_cancelled:          { Icon: CircleX,        badge: 'bg-orange-100 text-orange-600 dark:bg-orange-900/30 dark:text-orange-300',   label: 'TASK'      },
  exception_created:            { Icon: ShieldCheck,    badge: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',       label: 'EXCEPTION' },
  contact_message_sent:         { Icon: Mail,           badge: 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-400',                label: 'MESSAGE'   },
  contact_message_received:     { Icon: MailOpen,       badge: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300',               label: 'REPLY'     },
};

const DEFAULT_CONFIG = { Icon: AlertCircle, badge: 'bg-muted text-muted-foreground', label: 'EVENT' };

function kindConfig(kind) {
  return KIND_CONFIG[kind] ?? DEFAULT_CONFIG;
}

// ── helpers ───────────────────────────────────────────────────────────────────

function relativeTime(isoString) {
  const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function actorInitials(username) {
  if (!username) return '?';
  return username.slice(0, 2).toUpperCase();
}

const AVATAR_COLORS = [
  'bg-blue-500', 'bg-purple-500', 'bg-green-500', 'bg-orange-500',
  'bg-pink-500', 'bg-teal-500', 'bg-red-500', 'bg-indigo-500',
];

function avatarColor(username) {
  if (!username) return 'bg-muted';
  let hash = 0;
  for (let i = 0; i < username.length; i++) hash = username.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

const TASK_KINDS = new Set(['task_created', 'task_state_changed', 'task_auto_cancelled']);

// ── sub-components ────────────────────────────────────────────────────────────

function TimelineCard({ event }) {
  const { badge, label, Icon } = kindConfig(event.kind);
  const message = renderEvent(event.kind, event.payload);
  const color = avatarColor(event.actor_username);

  return (
    <div className="flex gap-3 rounded-lg border border-border bg-card p-3 hover:border-border/80 hover:shadow-sm transition-shadow">
      <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${color} text-white text-xs font-bold`}>
        {event.actor_username ? actorInitials(event.actor_username) : <Icon size={14} />}
      </div>
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center gap-2 flex-wrap">
          {event.actor_username && (
            <span className="text-sm font-medium text-foreground">{event.actor_username}</span>
          )}
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wide ${badge}`}>
            <Icon size={10} />
            {label}
          </span>
        </div>
        <p className="text-sm text-foreground">{message}</p>
        {TASK_KINDS.has(event.kind) && (event.payload?.created_at || event.payload?.closed_at) && (
          <div className="flex gap-3 mt-1">
            {event.payload.created_at && (
              <span className="text-xs text-muted-foreground">
                Opened: <time dateTime={event.payload.created_at} className="tabular-nums">
                  {new Date(event.payload.created_at).toLocaleString()}
                </time>
              </span>
            )}
            {event.payload.closed_at && (
              <span className="text-xs text-muted-foreground">
                Closed: <time dateTime={event.payload.closed_at} className="tabular-nums">
                  {new Date(event.payload.closed_at).toLocaleString()}
                </time>
              </span>
            )}
          </div>
        )}
      </div>
      <time
        dateTime={event.created_at}
        title={new Date(event.created_at).toLocaleString()}
        className="text-xs text-muted-foreground shrink-0 pt-1 tabular-nums"
      >
        {relativeTime(event.created_at)}
      </time>
    </div>
  );
}

// ── component ─────────────────────────────────────────────────────────────────

export default function IncidentTimeline({ incidentId, refreshKey = 0 }) {
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

  useEffect(() => { load(1); }, [load, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

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
        <div className="space-y-3">
          {data.results.map(event => (
            <TimelineCard key={event.id} event={event} />
          ))}
        </div>
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
