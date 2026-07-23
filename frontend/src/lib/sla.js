// Shared SLA helpers for the incident list's SLA visuals.

// The single most-urgent applicable SLA on an incident (breach first, then least
// fraction of time remaining), normalised for display. Returns null when neither
// the response nor the resolve SLA currently applies.
export function worstSla(incident) {
  const candidates = [incident.response_sla, incident.resolve_sla]
    .filter(s => s && s.applies)
    .map(s => ({
      breached: s.breached,
      remaining_seconds: s.remaining_seconds,
      target_seconds: s.target_seconds,
      fraction: s.remaining_seconds / s.target_seconds,
    }));
  if (candidates.length === 0) return null;
  candidates.sort((a, b) => {
    if (a.breached !== b.breached) return a.breached ? -1 : 1;
    return a.fraction - b.fraction;
  });
  return candidates[0];
}

// Coarse human duration ("45m", "3h", "2d") from a second count.
export function formatSlaDuration(seconds) {
  const s = Math.abs(seconds);
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}
