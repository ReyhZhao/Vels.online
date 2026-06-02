import { createContext, useContext, useEffect, useState } from 'react';
import api from '../lib/axios';

export const AuthContext = createContext({ user: null, isAuthenticated: false, isLoading: true, staffProfile: null });

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [staffProfile, setStaffProfile] = useState(null);

  useEffect(() => {
    api
      .get('/api/me/')
      .then((res) => {
        const csrf = res.headers?.['x-csrftoken'];
        if (csrf) api.defaults.headers.common['X-CSRFToken'] = csrf;
        const userData = res.data;
        setUser(userData);
        if (userData?.is_staff) {
          api
            .get('/api/oncall/me/profile/')
            .then((profileRes) => setStaffProfile(profileRes.data))
            .catch(() => setStaffProfile(null));
        }
      })
      .catch((err) => {
        const csrf = err.response?.headers?.['x-csrftoken'];
        if (csrf) api.defaults.headers.common['X-CSRFToken'] = csrf;
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, isLoading, staffProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
