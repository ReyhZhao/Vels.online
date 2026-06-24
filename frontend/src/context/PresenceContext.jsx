import { createContext, useContext } from 'react';

/**
 * Shares one Incident Presence client (the useIncidentPresence hook value) across
 * the incident detail header (roster), tasks (working), and comments (editing +
 * lock). Defaults to a safe no-op so consumers work even outside a provider
 * (e.g. non-staff, or in isolated component tests).
 */
const noop = () => {};
const DEFAULT = {
  roster: [],
  setActivity: noop,
  setViewing: noop,
  acquireLock: async () => ({ granted: true }),
  refreshLock: noop,
};

export const PresenceContext = createContext(DEFAULT);

export function usePresence() {
  return useContext(PresenceContext);
}

export default PresenceContext;
