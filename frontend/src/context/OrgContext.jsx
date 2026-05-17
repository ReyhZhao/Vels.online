import { createContext, useContext, useEffect, useState } from 'react';
import api from '../lib/axios';
import { useAuth } from './AuthContext';

export const OrgContext = createContext(null);

export function OrgProvider({ children }) {
  const { user } = useAuth();
  const [orgs, setOrgs] = useState([]);
  const [selectedOrg, setSelectedOrg] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

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
    <OrgContext.Provider value={{ orgs, selectedOrg, setSelectedOrg, setDefaultOrg, isLoading }}>
      {children}
    </OrgContext.Provider>
  );
}

export function useOrganization() {
  return useContext(OrgContext);
}
