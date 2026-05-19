import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import RouteReports from './RouteReports';

const ACCESS_LOG = {
  _id: 'abc',
  timestamp: '2026-05-19T10:00:00Z',
  data: { srcip: '1.2.3.4', http_method: 'GET', http_path: '/api/test', status_code: '200', body_bytes_sent: '512' },
};

const MODSEC_LOG = {
  _id: 'def',
  timestamp: '2026-05-19T11:00:00Z',
  data: { srcip: '5.6.7.8', http_method: 'GET', http_path: '/.env', ruleid: '949110' },
  GeoLocation: { country_name: 'Canada' },
};

function ok(logs, summary = { total: logs.length, blocked: 0 }) {
  return { data: { logs, total: logs.length, summary } };
}

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
    expect(screen.getByTestId('logs-loading')).toBeInTheDocument();
  });

  it('fetches access logs by default', async () => {
    api.get.mockResolvedValue(ok([]));
    renderPage('my.service.io');
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        expect.stringContaining('/api/ingress/routes/my.service.io/logs/?')
      );
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('type=accesslog'));
    });
  });

  it('renders access log rows with timestamp, IP, request, status, size', async () => {
    api.get.mockResolvedValue(ok([ACCESS_LOG]));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('1.2.3.4')).toBeInTheDocument();
      expect(screen.getByText('GET')).toBeInTheDocument();
      expect(screen.getByText('/api/test')).toBeInTheDocument();
      expect(screen.getByText('200')).toBeInTheDocument();
      expect(screen.getByText('512B')).toBeInTheDocument();
    });
  });

  it('shows summary total and blocked', async () => {
    api.get.mockResolvedValue(ok([ACCESS_LOG], { total: 10, blocked: 3 }));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('10')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
    });
  });

  it('switches to WAF Blocks tab and fetches modsecurity logs', async () => {
    api.get
      .mockResolvedValueOnce(ok([]))
      .mockResolvedValueOnce(ok([MODSEC_LOG], { total: 1, blocked: 1 }));
    renderPage();
    await waitFor(() => screen.getByText('WAF Blocks'));
    fireEvent.click(screen.getByText('WAF Blocks'));
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('type=modsecurity'));
    });
  });

  it('renders modsecurity rows with rule ID and country', async () => {
    api.get
      .mockResolvedValueOnce(ok([]))
      .mockResolvedValueOnce(ok([MODSEC_LOG], { total: 1, blocked: 1 }));
    renderPage();
    await waitFor(() => screen.getByText('WAF Blocks'));
    fireEvent.click(screen.getByText('WAF Blocks'));
    await waitFor(() => {
      expect(screen.getByText('5.6.7.8')).toBeInTheDocument();
      expect(screen.getByText('949110')).toBeInTheDocument();
      expect(screen.getByText('Canada')).toBeInTheDocument();
    });
  });

  it('applies srcip filter on form submit', async () => {
    api.get.mockResolvedValue(ok([]));
    renderPage();
    await waitFor(() => screen.getByPlaceholderText('Filter by IP…'));
    fireEvent.change(screen.getByPlaceholderText('Filter by IP…'), {
      target: { value: '10.0.0.1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Filter' }));
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(expect.stringContaining('srcip=10.0.0.1'));
    });
  });

  it('clears srcip filter when Clear is clicked', async () => {
    api.get.mockResolvedValue(ok([]));
    renderPage();
    await waitFor(() => screen.getByPlaceholderText('Filter by IP…'));
    fireEvent.change(screen.getByPlaceholderText('Filter by IP…'), {
      target: { value: '10.0.0.1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Filter' }));
    await waitFor(() => screen.getByRole('button', { name: 'Clear' }));
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    await waitFor(() => {
      const calls = api.get.mock.calls.map(c => c[0]);
      const lastCall = calls[calls.length - 1];
      expect(lastCall).not.toContain('srcip');
    });
  });

  it('shows empty state when no logs returned', async () => {
    api.get.mockResolvedValue(ok([]));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/No log entries found/i)).toBeInTheDocument()
    );
  });

  it('shows error state with retry button on fetch failure', async () => {
    api.get.mockRejectedValue(new Error('network error'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Failed to load logs.')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    });
  });

  it('retries fetch when Retry button is clicked', async () => {
    api.get
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce(ok([ACCESS_LOG]));
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Retry' }));
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(screen.getByText('1.2.3.4')).toBeInTheDocument());
    expect(api.get).toHaveBeenCalledTimes(2);
  });
});
