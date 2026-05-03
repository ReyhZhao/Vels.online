import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthProvider, useAuth } from './AuthContext';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), defaults: { headers: { common: {} } } },
}));

import api from '../lib/axios';

function TestConsumer() {
  const { user, isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <div>loading</div>;
  return (
    <div>
      <span data-testid="authenticated">{String(isAuthenticated)}</span>
      <span data-testid="username">{user?.username ?? 'none'}</span>
    </div>
  );
}

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.defaults.headers.common = {};
  });

  it('returns authenticated user when /api/me/ resolves', async () => {
    api.get.mockResolvedValue({
      data: { id: 1, username: 'eddie', email: 'eddie@vels.online' },
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
      expect(screen.getByTestId('username')).toHaveTextContent('eddie');
    });
  });

  it('returns unauthenticated state when /api/me/ returns 401', async () => {
    api.get.mockRejectedValue({ response: { status: 401 } });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
      expect(screen.getByTestId('username')).toHaveTextContent('none');
    });
  });

  it('starts in loading state', () => {
    api.get.mockReturnValue(new Promise(() => {}));

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    expect(screen.getByText('loading')).toBeInTheDocument();
  });

  it('stores X-CSRFToken default header from authenticated /api/me/ response', async () => {
    api.get.mockResolvedValue({
      data: { id: 1, username: 'eddie', email: 'eddie@vels.online' },
      headers: { 'x-csrftoken': 'csrf-from-me' },
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(api.defaults.headers.common['X-CSRFToken']).toBe('csrf-from-me');
    });
  });

  it('stores X-CSRFToken default header from 401 /api/me/ response', async () => {
    api.get.mockRejectedValue({
      response: { status: 401, headers: { 'x-csrftoken': 'csrf-from-401' } },
    });

    render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(api.defaults.headers.common['X-CSRFToken']).toBe('csrf-from-401');
    });
  });
});
