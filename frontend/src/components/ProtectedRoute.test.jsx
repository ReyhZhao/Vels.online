import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { AuthContext } from '../context/AuthContext';
import ProtectedRoute from './ProtectedRoute';

function renderWithAuth(authValue, children) {
  return render(
    <AuthContext.Provider value={authValue}>
      <ProtectedRoute>{children}</ProtectedRoute>
    </AuthContext.Provider>
  );
}

describe('ProtectedRoute', () => {
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

  it('renders children when authenticated', () => {
    renderWithAuth(
      { user: { id: 1 }, isAuthenticated: true, isLoading: false },
      <div>protected content</div>
    );

    expect(screen.getByText('protected content')).toBeInTheDocument();
  });

  it('redirects to Authentik login URL when unauthenticated', () => {
    renderWithAuth(
      { user: null, isAuthenticated: false, isLoading: false },
      <div>protected content</div>
    );

    expect(window.location.href).toBe('/auth/oidc/authentik/login/');
    expect(screen.queryByText('protected content')).not.toBeInTheDocument();
  });

  it('renders nothing while auth state is loading', () => {
    const { container } = renderWithAuth(
      { user: null, isAuthenticated: false, isLoading: true },
      <div>protected content</div>
    );

    expect(container).toBeEmptyDOMElement();
  });
});
