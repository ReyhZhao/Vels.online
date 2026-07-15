import { createContext, useContext, useEffect, useState } from 'react';
import api from '../lib/axios';
import { useAuth } from './AuthContext';

export const OrgContext = createContext(null);

export function OrgProvider({ children }) {
  const { user } = useAuth();
  const [orgs, setOrgs] = useState([]);
  const [selectedOrg, setSelectedOrg] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  // Staff-only "All organisations" view. Kept separate from selectedOrg, which
  // stays a concrete org so every other page keeps working; only the dashboard
  // reads this flag. Cleared when leaving the dashboard.
  const [viewAllOrgs, setViewAllOrgs] = useState(false);

  useEffect(() => {
    api
      .get('/api/security/organizations/')
      .then((res) => {
        setOrgs(res.data);
        if (res.data.length > 0) {
          const preferred = user?.default_org_slug
            ? res.data.find((o) => o.slug === user.default_org_slug)
            : null;
          setSelectedOrg(preferred ?? res.data[0]);
        }
      })
      .catch(() => setOrgs([]))
      .finally(() => setIsLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function setDefaultOrg(org) {
    await api.patch('/api/me/', { default_org_slug: org ? org.slug : null });
  }

  return (
    <OrgContext.Provider value={{ orgs, selectedOrg, setSelectedOrg, setDefaultOrg, isLoading, viewAllOrgs, setViewAllOrgs }}>
      {children}
    </OrgContext.Provider>
  );
}

export function useOrganization() {
  return useContext(OrgContext);
}
