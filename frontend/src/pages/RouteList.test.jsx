import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

vi.mock('../context/OrgContext', () => ({
  useOrganization: vi.fn(),
}));

import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import RouteList from './RouteList';

const ACME_ORG = { slug: 'acme', name: 'Acme' };

const ROUTES = [
  {
    fqdn: 'app.example.com',
    name: 'My App',
    backend_host: '10.0.0.1',
    backend_port: 8080,
    backend_protocol: 'http',
    status: 'active',
  },
  {
    fqdn: 'api.example.com',
    name: '',
    backend_host: '10.0.0.2',
    backend_port: 3000,
    backend_protocol: 'https',
    status: 'pending',
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <RouteList />
    </MemoryRouter>
  );
}

describe('RouteList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrganization.mockReturnValue({ selectedOrg: ACME_ORG });
  });

  it('shows loading state while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('shows empty state when no routes', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText('No routes yet.')).toBeInTheDocument());
  });

  it('renders route rows with FQDN and backend', async () => {
    api.get.mockResolvedValue({ data: ROUTES });
    renderPage();
    await waitFor(() => screen.getByText('app.example.com'));
    expect(screen.getByText('api.example.com')).toBeInTheDocument();
    expect(screen.getByText('http://10.0.0.1:8080')).toBeInTheDocument();
    expect(screen.getByText('https://10.0.0.2:3000')).toBeInTheDocument();
  });

  it('renders optional name below FQDN', async () => {
    api.get.mockResolvedValue({ data: ROUTES });
    renderPage();
    await waitFor(() => screen.getByText('My App'));
  });

  it('renders status badges', async () => {
    api.get.mockResolvedValue({ data: ROUTES });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('active')).toBeInTheDocument();
      expect(screen.getByText('pending')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    api.get.mockRejectedValue(new Error('network error'));
    renderPage();
    await waitFor(() => expect(screen.getByText('Failed to load routes.')).toBeInTheDocument());
  });

  it('fetches routes using the selected org slug', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/api/ingress/routes/', { params: { org: 'acme' } });
    });
  });
});
