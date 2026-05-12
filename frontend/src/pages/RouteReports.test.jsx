import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import RouteReports from './RouteReports';

const ENTRIES = [
  { timestamp: '2026-05-01T10:00:00Z', ip: '1.2.3.4', rule: 'sqli', action: 'blocked' },
  { timestamp: '2026-05-01T11:00:00Z', ip: '5.6.7.8', rule: 'xss',  action: 'blocked' },
];

function renderPage(fqdn = 'app.example.com') {
  return render(
    <MemoryRouter>
      <RouteReports fqdn={fqdn} />
    </MemoryRouter>
  );
}

describe('RouteReports', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows loading indicator while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByTestId('reports-loading')).toBeInTheDocument();
  });

  it('renders report entries with timestamp, IP, rule, and action', async () => {
    api.get.mockResolvedValue({ data: { entries: ENTRIES } });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('1.2.3.4')).toBeInTheDocument();
      expect(screen.getByText('5.6.7.8')).toBeInTheDocument();
      expect(screen.getByText('sqli')).toBeInTheDocument();
      expect(screen.getByText('xss')).toBeInTheDocument();
      expect(screen.getAllByText('blocked')).toHaveLength(2);
    });
  });

  it('shows empty state when no entries', async () => {
    api.get.mockResolvedValue({ data: { entries: [] } });
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/No blocked activity recorded/i)).toBeInTheDocument()
    );
  });

  it('shows BunkerWeb unavailability message when message field is present', async () => {
    api.get.mockResolvedValue({
      data: { entries: [], message: 'BunkerWeb is currently unavailable.' },
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('BunkerWeb is currently unavailable.')).toBeInTheDocument()
    );
  });

  it('shows error state with retry button on fetch failure', async () => {
    api.get.mockRejectedValue(new Error('network error'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Failed to load reports.')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    });
  });

  it('retries fetch when Retry button is clicked', async () => {
    api.get
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce({ data: { entries: ENTRIES } });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Retry' }));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.getByText('1.2.3.4')).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it('fetches from the correct endpoint', async () => {
    api.get.mockResolvedValue({ data: { entries: [] } });
    renderPage('my.service.io');
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/api/ingress/routes/my.service.io/reports/');
    });
  });
});
