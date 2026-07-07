import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import api from '../lib/api';
import type { Organization } from '../lib/types';
import { useAuth } from './AuthContext';

interface OrgContextValue {
  orgs: Organization[];
  selectedOrg: Organization | null;
  setSelectedOrg: (org: Organization | null) => void;
  isLoading: boolean;
}

export const OrgContext = createContext<OrgContextValue>({
  orgs: [],
  selectedOrg: null,
  setSelectedOrg: () => {},
  isLoading: true,
});

export function OrgProvider({ children }: { children: React.ReactNode }) {
  const { user, isAuthenticated } = useAuth();
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!isAuthenticated) {
      setOrgs([]);
      setSelectedOrg(null);
      return;
    }
    setIsLoading(true);
    api
      .get('/api/security/organizations/')
      .then((res) => {
        setOrgs(res.data);
        const preferred = user?.default_org_slug
          ? res.data.find((o: Organization) => o.slug === user.default_org_slug)
          : null;
        setSelectedOrg(preferred ?? null);
      })
      .catch(() => setOrgs([]))
      .finally(() => setIsLoading(false));
  }, [isAuthenticated, user?.default_org_slug]);

  const value = useMemo(
    () => ({ orgs, selectedOrg, setSelectedOrg, isLoading }),
    [orgs, selectedOrg, isLoading],
  );

  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

export function useOrganization() {
  return useContext(OrgContext);
}
