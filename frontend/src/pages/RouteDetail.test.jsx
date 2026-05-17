import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), delete: vi.fn() },
}));

vi.mock('./RouteSettings', () => ({ default: () => <div data-testid="route-settings" /> }));
vi.mock('./RouteReports', () => ({ default: () => <div data-testid="route-reports" /> }));

import api from '../lib/axios';
import RouteDetail from './RouteDetail';

const ROUTE = {
  fqdn: 'app.example.com',
  name: 'My App',
  backend_host: '10.0.0.1',
  backend_port: 8080,
  backend_protocol: 'http',
  status: 'active',
  dns_ok: true,
};

function renderPage(fqdn = 'app.example.com') {
  return render(
    <MemoryRouter initialEntries={[`/routes/${fqdn}`]}>
      <Routes>
        <Route path="/routes/:fqdn" element={<RouteDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('RouteDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('confirm', () => true);
  });

  it('shows loading then renders route', async () => {
    api.get.mockResolvedValue({ data: ROUTE });
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('app.example.com')).toBeInTheDocument());
    expect(screen.getByText('My App')).toBeInTheDocument();
    expect(screen.getByText('http://10.0.0.1:8080')).toBeInTheDocument();
  });

  it('renders status badge', async () => {
    api.get.mockResolvedValue({ data: ROUTE });
    renderPage();
    await waitFor(() => expect(screen.getByText('active')).toBeInTheDocument());
  });

  it('renders Settings and Reports tabs', async () => {
    api.get.mockResolvedValue({ data: ROUTE });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Reports' })).toBeInTheDocument();
    });
  });

  it('switches to Reports tab on click and shows RouteReports', async () => {
    api.get.mockResolvedValue({ data: ROUTE });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Reports' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reports' }));
    expect(screen.getByTestId('route-reports')).toBeInTheDocument();
  });

  it('shows error state when route not found', async () => {
    api.get.mockRejectedValue(new Error('not found'));
    renderPage();
    await waitFor(() => expect(screen.getByText('Route not found.')).toBeInTheDocument());
  });

  it('shows DNS warning banner when dns_ok is false', async () => {
    api.get.mockResolvedValue({ data: { ...ROUTE, dns_ok: false } });
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/DNS not yet pointing to BunkerWeb/i)
    );
  });

  it('shows DNS pending indicator when dns_ok is null', async () => {
    api.get.mockResolvedValue({ data: { ...ROUTE, dns_ok: null } });
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId('dns-pending')).toBeInTheDocument()
    );
  });

  it('shows no DNS banner when dns_ok is true', async () => {
    api.get.mockResolvedValue({ data: { ...ROUTE, dns_ok: true } });
    renderPage();
    await waitFor(() => screen.getByText('app.example.com'));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dns-pending')).not.toBeInTheDocument();
  });

  it('does not fetch reports until Reports tab is opened', async () => {
    api.get.mockResolvedValue({ data: ROUTE });
    renderPage();
    await waitFor(() => screen.getByText('app.example.com'));
    const reportsCalls = api.get.mock.calls.filter(c => c[0].includes('/reports/'));
    expect(reportsCalls).toHaveLength(0);
  });

  it('mounts RouteReports only after Reports tab is clicked', async () => {
    api.get.mockResolvedValue({ data: ROUTE });
    renderPage();
    await waitFor(() => screen.getByText('app.example.com'));
    expect(screen.queryByTestId('route-reports')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Reports' }));
    expect(screen.getByTestId('route-reports')).toBeInTheDocument();
  });

  it('shows FQDN in DNS banner when bunkerweb_public_fqdn is set', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/api/ingress/settings/')) return Promise.resolve({ data: { bunkerweb_public_fqdn: 'bw.example.com', bunkerweb_public_ip: '1.2.3.4' } });
      return Promise.resolve({ data: { ...ROUTE, dns_ok: false } });
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('bw.example.com')
    );
    expect(screen.queryByText('1.2.3.4')).not.toBeInTheDocument();
  });

  it('falls back to IP in DNS banner when only bunkerweb_public_ip is set', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/api/ingress/settings/')) return Promise.resolve({ data: { bunkerweb_public_fqdn: '', bunkerweb_public_ip: '1.2.3.4' } });
      return Promise.resolve({ data: { ...ROUTE, dns_ok: false } });
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('1.2.3.4')
    );
  });

  it('shows generic DNS message when both bunkerweb settings are empty', async () => {
    api.get.mockImplementation(url => {
      if (url.includes('/api/ingress/settings/')) return Promise.resolve({ data: { bunkerweb_public_fqdn: '', bunkerweb_public_ip: '' } });
      return Promise.resolve({ data: { ...ROUTE, dns_ok: false } });
    });
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('ensure your FQDN resolves to the BunkerWeb public IP')
    );
  });

  it('does not fetch ingress settings when dns_ok is true', async () => {
    api.get.mockResolvedValue({ data: ROUTE });
    renderPage();
    await waitFor(() => screen.getByText('app.example.com'));
    const settingsCalls = api.get.mock.calls.filter(c => c[0].includes('/api/ingress/settings/'));
    expect(settingsCalls).toHaveLength(0);
  });

  it('deletes route and navigates away', async () => {
    api.get.mockResolvedValue({ data: ROUTE });
    api.delete.mockResolvedValue({});
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/api/ingress/routes/app.example.com/');
      expect(mockNavigate).toHaveBeenCalledWith('/routes');
    });
  });
});
