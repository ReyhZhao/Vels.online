import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../hooks/useStatus', () => ({
  useStatus: () => ({ overallStatus: 'operational', isLoading: false }),
}));

vi.mock('../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import { useAuth } from '../../context/AuthContext';
import api from '../../lib/axios';
import TopNav from './TopNav';

function renderTopNav(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <TopNav />
    </MemoryRouter>
  );
}

describe('TopNav', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: null, isAuthenticated: false, isLoading: false });
    api.post.mockResolvedValue({ data: { detail: 'Logged out.' } });
  });

  it('renders the site brand link', () => {
    renderTopNav();
    const brand = screen.getByRole('link', { name: 'vels.online' });
    expect(brand).toBeInTheDocument();
    expect(brand).toHaveAttribute('href', '/');
  });

  it('renders a Blog navigation link pointing to /blog', () => {
    renderTopNav();
    const blogLink = screen.getByRole('link', { name: 'Blog' });
    expect(blogLink).toBeInTheDocument();
    expect(blogLink).toHaveAttribute('href', '/blog');
  });

  it('renders StatusIndicator linking to /status', () => {
    renderTopNav();
    const statusLink = screen.getByRole('link', { name: /site status/i });
    expect(statusLink).toBeInTheDocument();
    expect(statusLink).toHaveAttribute('href', '/status');
  });

  it('shows Login link when not authenticated', () => {
    renderTopNav();
    const loginLink = screen.getByRole('link', { name: /login/i });
    expect(loginLink).toBeInTheDocument();
    expect(loginLink).toHaveAttribute('href', '/auth/oidc/authentik/login/');
  });

  it('does not show Logout button when not authenticated', () => {
    renderTopNav();
    expect(screen.queryByRole('button', { name: /logout/i })).not.toBeInTheDocument();
  });

  it('shows username when authenticated', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: true },
      isAuthenticated: true,
      isLoading: false,
    });

    renderTopNav();
    expect(screen.getByTestId('nav-username')).toHaveTextContent('eddie');
  });

  it('shows Logout button when authenticated', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: true },
      isAuthenticated: true,
      isLoading: false,
    });

    renderTopNav();
    expect(screen.getByRole('button', { name: /logout/i })).toBeInTheDocument();
  });

  it('does not show Login link when authenticated', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: false },
      isAuthenticated: true,
      isLoading: false,
    });

    renderTopNav();
    expect(screen.queryByRole('link', { name: /login/i })).not.toBeInTheDocument();
  });

  it('calls POST /api/logout/ when Logout is clicked', async () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: true },
      isAuthenticated: true,
      isLoading: false,
    });

    const user = userEvent.setup();
    renderTopNav();

    await user.click(screen.getByRole('button', { name: /logout/i }));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/logout/')
    );
  });
});
