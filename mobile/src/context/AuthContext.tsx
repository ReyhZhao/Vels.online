import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import api from '../lib/api';
import { loadServerUrl } from '../lib/server';
import type { User } from '../lib/types';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  refresh: () => Promise<User | null>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  refresh: async () => null,
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async (): Promise<User | null> => {
    try {
      // /api/me/ also echoes the CSRF token header, captured by the api client.
      const res = await api.get('/api/me/');
      setUser(res.data);
      return res.data;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.post('/api/logout/');
    } catch {
      // session may already be gone — still clear local state
    }
    setUser(null);
  }, []);

  useEffect(() => {
    (async () => {
      await loadServerUrl();
      await refresh();
      setIsLoading(false);
    })();
  }, [refresh]);

  const value = useMemo(
    () => ({ user, isAuthenticated: !!user, isLoading, refresh, signOut }),
    [user, isLoading, refresh, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
