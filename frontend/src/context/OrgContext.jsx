import { createContext, useContext, useEffect, useState } from 'react';
import api from '../lib/axios';

export const OrgContext = createContext(null);

export function OrgProvider({ children }) {
  const [orgs, setOrgs] = useState([]);
  const [selectedOrg, setSelectedOrg] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    api
      .get('/api/security/organizations/')
      .then((res) => {
        setOrgs(res.data);
        if (res.data.length > 0) setSelectedOrg(res.data[0]);
      })
      .catch(() => setOrgs([]))
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <OrgContext.Provider value={{ orgs, selectedOrg, setSelectedOrg, isLoading }}>
      {children}
    </OrgContext.Provider>
  );
}

export function useOrganization() {
  return useContext(OrgContext);
}
