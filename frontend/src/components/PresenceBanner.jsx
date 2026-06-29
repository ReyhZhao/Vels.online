import { usePresence } from '../context/PresenceContext';
import { useAuth } from '../context/AuthContext';

/**
 * Incident Presence indicators (PRD #605, ADR-0028) — take 2.
 *
 * Replaces the small header roster chips with a more prominent, triage-banner-style
 * indicator, and moves the per-task signal into the task editor:
 *
 *  - <PresenceBanner/>        Full-width banner below the incident header card,
 *                             shown only when *other* people are on the incident.
 *  - <TaskPresenceStrip/>     Slim strip across the top of the task modal, shown
 *                             only when *others* are working the open task.
 *
 * By default both include the current user, which is handy for testing presence as a
 * single user. Set VITE_PRESENCE_SELF_EXCLUSION=1 to exclude yourself (the intended
 * production behaviour — a banner about yourself is noise). Both fail open: with no
 * presence data they render nothing. AI actors (🤖) are rendered distinctly and the
 * Assistant is attributed to its invoker.
 */

function initials(name) {
  return (name || '?').slice(0, 2).toUpperCase();
}

function activityLabel(member) {
  if (member.activity === 'working') {
    return member.target != null ? `working task ${member.target}` : 'working';
  }
  if (member.activity === 'editing') {
    return member.target != null ? 'editing a comment' : 'writing a comment';
  }
  return 'viewing';
}

function activityVerb(member) {
  if (member.activity === 'working') return 'working';
  if (member.activity === 'editing') return 'editing';
  return 'viewing';
}

function displayLabel(member) {
  if (member.actor_kind === 'ai' && member.run_by) {
    return `${member.display_name} · run by ${member.run_by}`;
  }
  return member.display_name;
}

// Read dynamically (not at module load) so the value is overridable in tests.
function selfExclusionEnabled() {
  const v = import.meta.env.VITE_PRESENCE_SELF_EXCLUSION;
  return v === '1' || v === 'true';
}

function useOthers() {
  const { roster } = usePresence();
  const { user } = useAuth();
  if (!selfExclusionEnabled()) return roster || [];
  return (roster || []).filter(
    (m) => !(m.actor_kind !== 'ai' && m.actor_id != null && m.actor_id === user?.id),
  );
}

function Avatar({ member, size = 'h-6 w-6' }) {
  const isAI = member.actor_kind === 'ai';
  return (
    <span
      data-testid="presence-avatar"
      title={`${displayLabel(member)} — ${activityLabel(member)}`}
      className={`relative inline-flex ${size} items-center justify-center rounded-full text-[11px] font-semibold ring-2 ring-offset-1 ring-offset-card ${
        isAI
          ? 'bg-indigo-100 text-indigo-700 ring-indigo-300 dark:bg-indigo-900/40 dark:text-indigo-300 dark:ring-indigo-700'
          : 'bg-slate-200 text-slate-700 ring-slate-300 dark:bg-slate-700 dark:text-slate-200 dark:ring-slate-500'
      }`}
    >
      {isAI ? '🤖' : initials(member.display_name)}
    </span>
  );
}

function PulseDot({ className = 'bg-emerald-500' }) {
  return (
    <span className="relative inline-flex h-2.5 w-2.5 shrink-0" aria-hidden="true">
      <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${className}`} />
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${className}`} />
    </span>
  );
}

export default function PresenceBanner() {
  const others = useOthers();
  if (others.length === 0) return null;

  const summary = others
    .slice(0, 3)
    .map((m) => `${m.display_name} (${activityVerb(m)})`)
    .join(', ');
  const extra = others.length > 3 ? ` +${others.length - 3} more` : '';

  return (
    <div
      aria-label="Who is on this incident"
      className="flex flex-wrap items-center gap-3 rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300"
    >
      <PulseDot />
      <span className="font-medium">
        {others.length} {others.length === 1 ? 'person is' : 'people are'} on this incident
      </span>
      <span className="text-emerald-600 dark:text-emerald-400">· {summary}{extra}</span>
      <span className="ml-auto flex -space-x-2">
        {others.slice(0, 5).map((m) => (
          <Avatar key={m.actor_key} member={m} />
        ))}
      </span>
    </div>
  );
}

/**
 * Slim strip shown at the top of the task modal body when other actors are working
 * the open task (presence activity `working` with `target === taskId`). Negative
 * margins let it span the modal body's horizontal padding.
 */
export function TaskPresenceStrip({ taskId }) {
  const others = useOthers().filter(
    (m) => m.activity === 'working' && String(m.target) === String(taskId),
  );
  if (others.length === 0) return null;

  const names =
    others.length === 1
      ? others[0].display_name
      : others.length === 2
        ? `${others[0].display_name} and ${others[1].display_name}`
        : `${others[0].display_name} and ${others.length - 1} others`;

  return (
    <div className="-mx-6 -mt-4 mb-2 flex items-center gap-2 border-b border-amber-300 bg-amber-50 px-6 py-2 text-xs font-medium text-amber-800 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-300">
      <PulseDot className="bg-amber-500" />
      <span>
        {names} {others.length === 1 ? 'is' : 'are'} also in this task right now
      </span>
      <span className="ml-auto flex -space-x-1.5">
        {others.map((m) => (
          <Avatar key={m.actor_key} member={m} size="h-5 w-5" />
        ))}
      </span>
    </div>
  );
}
