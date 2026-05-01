import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../hooks/useStatus');
vi.mock('../context/AuthContext');

import { useStatus } from '../hooks/useStatus';
import { useAuth } from '../context/AuthContext';
import StatusPage from './StatusPage';

const UP = { name: 'API', status: 'up', uptime_ratio: '99.95', response_time: '120' };
const DOWN = { name: 'Database', status: 'down', uptime_ratio: '95.00', response_time: '0' };
const DEGRADED = { name: 'CDN', status: 'seems_down', uptime_ratio: '98.50', response_time: '500' };
const WITH_LOGS = {
  ...UP,
  logs: [
    { datetime: '2026-01-01T10:00:00.000Z', type: 'down', duration_seconds: 120 },
    { datetime: '2026-01-01T10:02:00.000Z', type: 'up', duration_seconds: 0 },
  ],
};

const baseStatus = { monitors: [], overallStatus: 'unknown', isLoading: false, isRefreshing: false, error: null, forceRefresh: vi.fn() };

function renderPage() {
  return render(
    <MemoryRouter>
      <StatusPage />
    </MemoryRouter>
  );
}

describe('StatusPage — public view', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ user: null });
  });

  it('shows loading banner while fetching', () => {
    useStatus.mockReturnValue({ ...baseStatus, isLoading: true });
    renderPage();
    expect(screen.getByText('Checking status…')).toBeInTheDocument();
  });

  it('shows "All systems operational" banner when all up', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByText('All systems operational')).toBeInTheDocument();
  });

  it('shows "Degraded performance" banner when degraded', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP, DEGRADED], overallStatus: 'degraded' });
    renderPage();
    expect(screen.getByText('Degraded performance')).toBeInTheDocument();
  });

  it('shows "Service disruption" banner when outage', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP, DOWN], overallStatus: 'outage' });
    renderPage();
    expect(screen.getByText('Service disruption')).toBeInTheDocument();
  });

  it('renders a card for each monitor', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP, DOWN], overallStatus: 'outage' });
    renderPage();
    expect(screen.getByText('API')).toBeInTheDocument();
    expect(screen.getByText('Database')).toBeInTheDocument();
  });

  it('shows formatted uptime and response time on each card', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByText('99.95%')).toBeInTheDocument();
    expect(screen.getByText('120 ms')).toBeInTheDocument();
  });

  it('shows status badge for each monitor', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP, DOWN], overallStatus: 'outage' });
    renderPage();
    expect(screen.getByText('Operational')).toBeInTheDocument();
    expect(screen.getByText('Down')).toBeInTheDocument();
  });

  it('shows empty state when no monitors', () => {
    useStatus.mockReturnValue({ ...baseStatus });
    renderPage();
    expect(screen.getByText(/no monitors configured/i)).toBeInTheDocument();
  });

  it('shows error message when fetch failed', () => {
    useStatus.mockReturnValue({ ...baseStatus, error: new Error('Network error') });
    renderPage();
    expect(screen.getByText(/could not reach the status api/i)).toBeInTheDocument();
  });

  it('shows dashes when uptime and response time are missing', () => {
    const monitor = { name: 'Worker', status: 'up', uptime_ratio: null, response_time: null };
    useStatus.mockReturnValue({ ...baseStatus, monitors: [monitor], overallStatus: 'operational' });
    renderPage();
    expect(screen.getAllByText('—')).toHaveLength(2);
  });

  it('does not show Force Refresh button for non-admin', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP], overallStatus: 'operational' });
    renderPage();
    expect(screen.queryByRole('button', { name: /force refresh/i })).not.toBeInTheDocument();
  });

  it('does not show incident log table for non-admin', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [WITH_LOGS], overallStatus: 'operational' });
    renderPage();
    expect(screen.queryByText('Timestamp')).not.toBeInTheDocument();
  });
});

describe('StatusPage — admin view', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ user: { id: 1, username: 'admin', is_staff: true } });
  });

  it('shows Force Refresh button for admin', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByRole('button', { name: /force refresh/i })).toBeInTheDocument();
  });

  it('calls forceRefresh when button is clicked', () => {
    const forceRefresh = vi.fn();
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP], overallStatus: 'operational', forceRefresh });
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /force refresh/i }));
    expect(forceRefresh).toHaveBeenCalledOnce();
  });

  it('disables Force Refresh button while refreshing', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [UP], overallStatus: 'operational', isRefreshing: true });
    renderPage();
    expect(screen.getByRole('button', { name: /refreshing/i })).toBeDisabled();
  });

  it('shows incident log table for admin', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [WITH_LOGS], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByText('Timestamp')).toBeInTheDocument();
    expect(screen.getByText('Type')).toBeInTheDocument();
    expect(screen.getByText('Duration')).toBeInTheDocument();
  });

  it('renders log rows with type and duration', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [WITH_LOGS], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByText('Down')).toBeInTheDocument();
    expect(screen.getByText('Recovery')).toBeInTheDocument();
    expect(screen.getByText('120s')).toBeInTheDocument();
  });

  it('shows "No incidents recorded" when logs array is empty', () => {
    const monitor = { ...UP, logs: [] };
    useStatus.mockReturnValue({ ...baseStatus, monitors: [monitor], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByText('No incidents recorded.')).toBeInTheDocument();
  });
});
