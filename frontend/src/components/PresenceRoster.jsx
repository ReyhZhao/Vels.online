import { usePresence } from '../context/PresenceContext';

/**
 * Roster chips for Incident Presence (PRD #605, ADR-0028) — who is on the
 * incident right now and what each is doing. Staff + AI actors; AI actors are
 * rendered distinctly (🤖) and the Assistant is attributed to its invoker.
 */

function activityLabel(member) {
  if (member.activity === 'working') {
    return member.target != null ? `working task ${member.target}` : 'working';
  }
  if (member.activity === 'editing') {
    return member.target != null ? 'editing a comment' : 'writing a comment';
  }
  return 'viewing';
}

function initials(name) {
  return (name || '?').slice(0, 2).toUpperCase();
}

function PresenceChip({ member }) {
  const isAI = member.actor_kind === 'ai';
  const name = isAI
    ? (member.run_by ? `${member.display_name} · run by ${member.run_by}` : member.display_name)
    : member.display_name;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs ${
        isAI
          ? 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300'
          : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
      }`}
      title={`${name} — ${activityLabel(member)}`}
      data-testid="presence-chip"
    >
      <span aria-hidden="true" className="font-medium">
        {isAI ? '🤖' : initials(member.display_name)}
      </span>
      <span className="font-medium">{isAI ? member.display_name : member.display_name}</span>
      <span className="text-[10px] opacity-70">{activityLabel(member)}</span>
    </span>
  );
}

export default function PresenceRoster() {
  const { roster } = usePresence();
  if (!roster || roster.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Who is on this incident">
      {roster.map((m) => (
        <PresenceChip key={m.actor_key} member={m} />
      ))}
    </div>
  );
}
