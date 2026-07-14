import { useCallback, useEffect, useState } from 'react';
import api from '@/lib/axios';

const EMPTY = {
  newAlerts: 0,
  openIncidents: 0,
  myTasks: 0,
  pendingSignups: 0,
  proposedTriageLessons: 0,
  intakeInbox: 0,
};

async function fetchCount(url, params) {
  try {
    const res = await api.get(url, params ? { params } : undefined);
    return res.data?.count ?? 0;
  } catch {
    return null; // caller keeps the previous value on failure
  }
}

/**
 * Live counts surfaced as sidebar badges: new alerts, open incidents,
 * my open tasks and (staff only) pending signup requests, proposed triage
 * lessons awaiting review, and items in the partner intake inbox.
 * Refreshes every 60s and on the `signuprequest:changed` window event.
 */
export function useNavCounts(isStaff) {
  const [counts, setCounts] = useState(EMPTY);

  const refresh = useCallback(async () => {
    const [
      newAlerts,
      openIncidents,
      tasksNew,
      tasksInProgress,
      pendingSignups,
      proposedTriageLessons,
      intakeInbox,
    ] = await Promise.all([
      fetchCount('/api/alerts/', { state: 'new', per_page: 1 }),
      fetchCount('/api/incidents/', { exclude_states: 'closed', per_page: 1 }),
      fetchCount('/api/tasks/', { assignee: 'me', state: 'new', per_page: 1 }),
      fetchCount('/api/tasks/', { assignee: 'me', state: 'in_progress', per_page: 1 }),
      isStaff ? fetchCount('/api/signups/pending-count/') : Promise.resolve(0),
      isStaff ? fetchCount('/api/incidents/triage-lessons/count/') : Promise.resolve(0),
      isStaff ? fetchCount('/api/partners/intake-inbox/count/') : Promise.resolve(0),
    ]);
    setCounts((prev) => ({
      newAlerts: newAlerts ?? prev.newAlerts,
      openIncidents: openIncidents ?? prev.openIncidents,
      myTasks:
        tasksNew == null || tasksInProgress == null
          ? prev.myTasks
          : tasksNew + tasksInProgress,
      pendingSignups: pendingSignups ?? prev.pendingSignups,
      proposedTriageLessons: proposedTriageLessons ?? prev.proposedTriageLessons,
      intakeInbox: intakeInbox ?? prev.intakeInbox,
    }));
  }, [isStaff]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 60000);
    return () => clearInterval(interval);
  }, [refresh]);

  useEffect(() => {
    window.addEventListener('signuprequest:changed', refresh);
    return () => window.removeEventListener('signuprequest:changed', refresh);
  }, [refresh]);

  return counts;
}
