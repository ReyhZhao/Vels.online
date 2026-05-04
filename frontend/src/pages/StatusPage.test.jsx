import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../hooks/useStatus');
vi.mock('../context/AuthContext');

import { useStatus } from '../hooks/useStatus';
import { useAuth } from '../context/AuthContext';
import StatusPage, { formatDuration } from './StatusPage';

const UP = { name: 'API', status: 'up', uptime_ratio: '99.95', response_time: '120' };
const DOWN = { name: 'Database', status: 'down', uptime_ratio: '95.00', response_time: '0' };
const DEGRADED = { name: 'CDN', status: 'seems_down', uptime_ratio: '98.50', response_time: '500' };

const daysAgo = (n) => new Date(Date.now() - n * 24 * 60 * 60 * 1000).toISOString();

const WITH_LOGS = {
  ...UP,
  logs: [
    { datetime: daysAgo(1), type: 'down', duration_seconds: 120 },
    { datetime: daysAgo(2), type: 'up', duration_seconds: 0 },
  ],
};

// 3 recent + 2 older-than-7-days logs
const WITH_MIXED_LOGS = {
  ...UP,
  logs: [
    { datetime: daysAgo(1), type: 'down', duration_seconds: 60 },
    { datetime: daysAgo(3), type: 'up',   duration_seconds: 0 },
    { datetime: daysAgo(5), type: 'down', duration_seconds: 120 },
    { datetime: daysAgo(8),  type: 'up',  duration_seconds: 0 },
    { datetime: daysAgo(10), type: 'down', duration_seconds: 300 },
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

// ---------------------------------------------------------------- formatDuration

describe('formatDuration', () => {
  it('returns seconds for values under 60', () => {
    expect(formatDuration(45)).toBe('45s');
    expect(formatDuration(0)).toBe('0s');
    expect(formatDuration(59)).toBe('59s');
  });

  it('returns minutes for values 60–3599', () => {
    expect(formatDuration(180)).toBe('3m');
    expect(formatDuration(90)).toBe('1.5m');
    expect(formatDuration(60)).toBe('1m');
  });

  it('returns hours for values 3600 and above', () => {
    expect(formatDuration(7200)).toBe('2h');
    expect(formatDuration(5400)).toBe('1.5h');
    expect(formatDuration(3600)).toBe('1h');
  });
});

// ---------------------------------------------------------------- public view

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

  it('rounds response time to a whole number', () => {
    const monitor = { ...UP, response_time: '120.7' };
    useStatus.mockReturnValue({ ...baseStatus, monitors: [monitor], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByText('121 ms')).toBeInTheDocument();
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

// ---------------------------------------------------------------- admin view

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

  it('renders log rows with formatted duration', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [WITH_LOGS], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByText('Down')).toBeInTheDocument();
    expect(screen.getByText('Recovery')).toBeInTheDocument();
    expect(screen.getByText('2m')).toBeInTheDocument();
  });

  it('shows "No incidents recorded" when logs array is empty', () => {
    const monitor = { ...UP, logs: [] };
    useStatus.mockReturnValue({ ...baseStatus, monitors: [monitor], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByText('No incidents recorded.')).toBeInTheDocument();
  });

  it('shows only recent logs (last 7 days) by default', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [WITH_MIXED_LOGS], overallStatus: 'operational' });
    renderPage();
    const rows = screen.getAllByRole('row').filter((r) => within(r).queryAllByRole('columnheader').length === 0);
    expect(rows).toHaveLength(3);
  });

  it('shows "Load older incidents" button when there are older logs', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [WITH_MIXED_LOGS], overallStatus: 'operational' });
    renderPage();
    expect(screen.getByRole('button', { name: /load older incidents/i })).toBeInTheDocument();
  });

  it('shows all logs when "Load older incidents" is clicked', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [WITH_MIXED_LOGS], overallStatus: 'operational' });
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /load older incidents/i }));
    const rows = screen.getAllByRole('row').filter((r) => within(r).queryAllByRole('columnheader').length === 0);
    expect(rows).toHaveLength(5);
  });

  it('does not show load-more button once all logs are visible', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [WITH_MIXED_LOGS], overallStatus: 'operational' });
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /load older incidents/i }));
    expect(screen.queryByRole('button', { name: /load older incidents/i })).not.toBeInTheDocument();
  });

  it('does not show load-more button when all logs are within 7 days', () => {
    useStatus.mockReturnValue({ ...baseStatus, monitors: [WITH_LOGS], overallStatus: 'operational' });
    renderPage();
    expect(screen.queryByRole('button', { name: /load older/i })).not.toBeInTheDocument();
  });
});
