import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { AuthContext } from '../context/AuthContext';
import StaffOnlyRoute from './StaffOnlyRoute';

function renderStaffOnly(authValue, { initialEntry = '/admin' } = {}) {
  return render(
    <AuthContext.Provider value={authValue}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/admin" element={
            <StaffOnlyRoute><div>admin content</div></StaffOnlyRoute>
          } />
          <Route path="/incidents" element={<div>incidents page</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>
  );
}

describe('StaffOnlyRoute', () => {
  let originalLocation;

  beforeEach(() => {
    originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: { href: '' },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', {
      configurable: true,
      writable: true,
      value: originalLocation,
    });
  });

  it('renders children for an authenticated staff user', () => {
    renderStaffOnly({ user: { id: 1, is_staff: true }, isAuthenticated: true, isLoading: false });
    expect(screen.getByText('admin content')).toBeInTheDocument();
  });

  it('redirects to /incidents for an authenticated non-staff user', () => {
    renderStaffOnly({ user: { id: 2, is_staff: false }, isAuthenticated: true, isLoading: false });
    expect(screen.queryByText('admin content')).not.toBeInTheDocument();
    expect(screen.getByText('incidents page')).toBeInTheDocument();
  });

  it('redirects to the OIDC login URL when unauthenticated', () => {
    renderStaffOnly({ user: null, isAuthenticated: false, isLoading: false });
    expect(window.location.href).toBe('/auth/oidc/authentik/login/');
    expect(screen.queryByText('admin content')).not.toBeInTheDocument();
  });

  it('renders nothing while auth state is loading', () => {
    const { container } = renderStaffOnly({ user: null, isAuthenticated: false, isLoading: true });
    expect(container).toBeEmptyDOMElement();
  });
});
