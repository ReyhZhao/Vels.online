// Mirrors backend/incidents/services/transitions.py — the server re-validates,
// this only decides which actions to offer.
export const ALLOWED_TRANSITIONS: Record<string, string[]> = {
  new: ['triaged', 'in_progress', 'closed'],
  triaged: ['in_progress', 'on_hold'],
  in_progress: ['on_hold', 'resolved', 'needs_tuning', 'pending_closure', 'closed'],
  on_hold: ['in_progress', 'resolved', 'needs_tuning', 'pending_closure', 'closed'],
  needs_tuning: ['in_progress', 'closed'],
  pending_closure: ['in_progress', 'closed'],
  resolved: ['in_progress', 'closed'],
  closed: ['in_progress'],
};

export const CLOSURE_REASONS = [
  'resolved',
  'false_positive',
  'no_impact',
  'informational',
  'accepted_risk',
] as const;

export function allowedTransitions(state: string): string[] {
  return ALLOWED_TRANSITIONS[state] ?? [];
}
