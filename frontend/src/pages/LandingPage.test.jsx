import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

vi.mock('../context/AuthContext');
vi.mock('../lib/axios');

import { useAuth } from '../context/AuthContext';
import api from '../lib/axios';
import LandingPage from './LandingPage';

const STATS = {
  window_days: 30,
  alerts_ingested: 4_180_000,
  incidents_resolved: 1847,
  endpoints_monitored: 8930,
  organizations_protected: 62,
  detection_rules_live: 1214,
  generated_at: '2026-07-22T10:00:00Z',
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function signedIn() {
  useAuth.mockReturnValue({ isAuthenticated: true, isLoading: false });
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({ isAuthenticated: false, isLoading: false });
  api.get.mockResolvedValue({ data: STATS });
});

describe('LandingPage', () => {
  it('shows the landing page to authenticated users instead of redirecting them away', async () => {
    signedIn();

    renderPage();

    // The page renders in place — no bounce to /dashboard.
    expect(screen.getByRole('heading', { name: /already triaged/i })).toBeInTheDocument();
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('stat-alerts')).toHaveTextContent('4.2M'));
  });

  it('points authenticated visitors into the app rather than at a login', async () => {
    signedIn();

    renderPage();
    await waitFor(() => expect(screen.getByTestId('stat-alerts')).toHaveTextContent('4.2M'));

    const dashboardLinks = screen
      .getAllByRole('link')
      .filter((link) => link.getAttribute('href') === '/dashboard');
    expect(dashboardLinks.length).toBeGreaterThan(0);
    expect(screen.queryByRole('link', { name: /^sign in/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /request access/i })).not.toBeInTheDocument();
  });

  it('renders nothing while auth is still resolving', () => {
    useAuth.mockReturnValue({ isAuthenticated: false, isLoading: true });

    const { container } = renderPage();

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the pitch and a sign-in affordance to anonymous visitors', async () => {
    renderPage();

    expect(screen.getByRole('heading', { name: /already triaged/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign in to polaris/i })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('stat-alerts')).toHaveTextContent('4.2M'));
  });

  it('renders real figures from the public stats endpoint', async () => {
    renderPage();

    await waitFor(() => expect(screen.getByTestId('stat-alerts')).toHaveTextContent('4.2M'));
    expect(screen.getByTestId('stat-incidents')).toHaveTextContent('1,847');
    expect(screen.getByTestId('stat-endpoints')).toHaveTextContent('8,930');
    expect(screen.getByTestId('stat-rules')).toHaveTextContent('1,214');
    expect(screen.getByText(/across 62 organisations/i)).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/api/public/stats/');
  });

  it('shows a dash rather than inventing a number when stats fail to load', async () => {
    api.get.mockRejectedValue(new Error('boom'));

    renderPage();

    await waitFor(() => expect(screen.getByTestId('stat-alerts')).toHaveTextContent('—'));
    expect(screen.getByTestId('stat-incidents')).toHaveTextContent('—');
    expect(screen.getByTestId('stat-endpoints')).toHaveTextContent('—');
    expect(screen.getByTestId('stat-rules')).toHaveTextContent('—');
  });

  it('points at the documentation page rather than inlining the handbook', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId('stat-alerts')).toHaveTextContent('4.2M'));

    const docsLinks = screen
      .getAllByRole('link')
      .filter((link) => link.getAttribute('href')?.startsWith('/docs'));

    expect(docsLinks.length).toBeGreaterThan(0);
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });
});
