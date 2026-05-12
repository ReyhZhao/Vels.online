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

import api from '../lib/axios';
import RouteDetail from './RouteDetail';

const ROUTE = {
  fqdn: 'app.example.com',
  name: 'My App',
  backend_host: '10.0.0.1',
  backend_port: 8080,
  backend_protocol: 'http',
  status: 'active',
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

  it('switches to Reports tab on click', async () => {
    api.get.mockResolvedValue({ data: ROUTE });
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Reports' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reports' }));
    expect(screen.getByText(/blocked activity reports/i)).toBeInTheDocument();
  });

  it('shows error state when route not found', async () => {
    api.get.mockRejectedValue(new Error('not found'));
    renderPage();
    await waitFor(() => expect(screen.getByText('Route not found.')).toBeInTheDocument());
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
