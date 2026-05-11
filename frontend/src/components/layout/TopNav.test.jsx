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

vi.mock('../OrgSwitcher', () => ({
  default: () => <div data-testid="org-switcher" />,
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

  it('shows Dashboard link when authenticated', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: true },
      isAuthenticated: true,
      isLoading: false,
    });

    renderTopNav();
    const dashboardLink = screen.getByRole('link', { name: 'Dashboard' });
    expect(dashboardLink).toBeInTheDocument();
    expect(dashboardLink).toHaveAttribute('href', '/dashboard');
  });

  it('does not show Dashboard link when not authenticated', () => {
    renderTopNav();
    expect(screen.queryByRole('link', { name: 'Dashboard' })).not.toBeInTheDocument();
  });

  it('renders OrgSwitcher when authenticated', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: false },
      isAuthenticated: true,
      isLoading: false,
    });

    renderTopNav();
    expect(screen.getByTestId('org-switcher')).toBeInTheDocument();
  });

  it('does not render OrgSwitcher when not authenticated', () => {
    renderTopNav();
    expect(screen.queryByTestId('org-switcher')).not.toBeInTheDocument();
  });

  it('shows Report issue button for staff users', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: true },
      isAuthenticated: true,
      isLoading: false,
    });
    renderTopNav();
    expect(screen.getByRole('button', { name: /report issue/i })).toBeInTheDocument();
  });

  it('does not show Report issue button for non-staff users', () => {
    useAuth.mockReturnValue({
      user: { id: 2, username: 'member', email: 'member@vels.online', is_staff: false },
      isAuthenticated: true,
      isLoading: false,
    });
    renderTopNav();
    expect(screen.queryByRole('button', { name: /report issue/i })).not.toBeInTheDocument();
  });

  // ── responsive visibility ─────────────────────────────────────────────────

  it('Blog link carries hidden md:inline-flex for mobile hiding', () => {
    renderTopNav();
    const blogLink = screen.getByRole('link', { name: 'Blog' });
    expect(blogLink.className).toContain('hidden');
    expect(blogLink.className).toContain('md:inline-flex');
  });

  it('StatusIndicator is wrapped in a hidden md:flex container', () => {
    renderTopNav();
    const statusLink = screen.getByRole('link', { name: /site status/i });
    expect(statusLink.closest('span').className).toContain('hidden');
    expect(statusLink.closest('span').className).toContain('md:flex');
  });

  it('Dashboard link carries hidden md:inline-flex for mobile hiding', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: true },
      isAuthenticated: true,
      isLoading: false,
    });
    renderTopNav();
    const dashboardLink = screen.getByRole('link', { name: 'Dashboard' });
    expect(dashboardLink.className).toContain('hidden');
    expect(dashboardLink.className).toContain('md:inline-flex');
  });

  it('Report issue button carries hidden md:inline-flex for mobile hiding', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: true },
      isAuthenticated: true,
      isLoading: false,
    });
    renderTopNav();
    const reportBtn = screen.getByRole('button', { name: /report issue/i });
    expect(reportBtn.className).toContain('hidden');
    expect(reportBtn.className).toContain('md:inline-flex');
  });

  it('username span carries hidden md:inline for mobile hiding', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: true },
      isAuthenticated: true,
      isLoading: false,
    });
    renderTopNav();
    const usernameEl = screen.getByTestId('nav-username');
    expect(usernameEl.className).toContain('hidden');
    expect(usernameEl.className).toContain('md:inline');
  });

  it('Logout button has no hidden class — always visible', () => {
    useAuth.mockReturnValue({
      user: { id: 1, username: 'eddie', email: 'eddie@vels.online', is_staff: true },
      isAuthenticated: true,
      isLoading: false,
    });
    renderTopNav();
    const logoutBtn = screen.getByRole('button', { name: /logout/i });
    expect(logoutBtn.className).not.toContain('hidden');
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
