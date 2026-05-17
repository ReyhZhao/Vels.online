import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('../context/OrgContext', () => ({
  useOrganization: vi.fn(),
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import { useAuth } from '../context/AuthContext';
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

const CANDIDATES = [
  { server_name: 'import-a.example.com', backend_host: '10.1.0.1', backend_port: 80, backend_protocol: 'http' },
  { server_name: 'import-b.example.com', backend_host: '10.1.0.2', backend_port: 443, backend_protocol: 'https' },
];

describe('RouteList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrganization.mockReturnValue({ selectedOrg: ACME_ORG });
    useAuth.mockReturnValue({ user: { id: 1, is_staff: false } });
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

  it('shows em-dash when backend_host is empty', async () => {
    const routeNoHost = { ...ROUTES[0], backend_host: '' };
    api.get.mockResolvedValue({ data: [routeNoHost] });
    renderPage();
    await waitFor(() => screen.getByText('app.example.com'));
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('http://:8080')).not.toBeInTheDocument();
  });

  it('shows em-dash in import modal when candidate has no backend_host', async () => {
    useAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    const candidateNoHost = { server_name: 'x.example.com', backend_host: '', backend_port: 80, backend_protocol: 'http' };
    api.get
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: { candidates: [candidateNoHost] } });
    render(<MemoryRouter><RouteList /></MemoryRouter>);
    await waitFor(() => screen.getByText('Import from BunkerWeb'));
    fireEvent.click(screen.getByText('Import from BunkerWeb'));
    await waitFor(() => screen.getByText('x.example.com'));
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('http://:80')).not.toBeInTheDocument();
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

describe('RouteList — import button visibility', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrganization.mockReturnValue({ selectedOrg: ACME_ORG });
    api.get.mockResolvedValue({ data: [] });
  });

  it('hides import button for non-staff users', async () => {
    useAuth.mockReturnValue({ user: { id: 1, is_staff: false } });
    render(<MemoryRouter><RouteList /></MemoryRouter>);
    await waitFor(() => expect(screen.queryByText('Import from BunkerWeb')).not.toBeInTheDocument());
  });

  it('shows import button for staff users', async () => {
    useAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
    render(<MemoryRouter><RouteList /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('Import from BunkerWeb')).toBeInTheDocument());
  });
});

describe('RouteList — import modal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrganization.mockReturnValue({ selectedOrg: ACME_ORG });
    useAuth.mockReturnValue({ user: { id: 1, is_staff: true } });
  });

  it('fetches candidates when modal opens', async () => {
    api.get
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: { candidates: CANDIDATES } });
    render(<MemoryRouter><RouteList /></MemoryRouter>);
    await waitFor(() => screen.getByText('Import from BunkerWeb'));
    fireEvent.click(screen.getByText('Import from BunkerWeb'));
    await waitFor(() => expect(screen.getByText('import-a.example.com')).toBeInTheDocument());
    expect(screen.getByText('import-b.example.com')).toBeInTheDocument();
  });

  it('shows empty state when no candidates', async () => {
    api.get
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: { candidates: [] } });
    render(<MemoryRouter><RouteList /></MemoryRouter>);
    await waitFor(() => screen.getByText('Import from BunkerWeb'));
    fireEvent.click(screen.getByText('Import from BunkerWeb'));
    await waitFor(() =>
      expect(screen.getByText('No unregistered BunkerWeb services found.')).toBeInTheDocument()
    );
  });

  it('submit button is disabled when nothing selected', async () => {
    api.get
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: { candidates: CANDIDATES } });
    render(<MemoryRouter><RouteList /></MemoryRouter>);
    await waitFor(() => screen.getByText('Import from BunkerWeb'));
    fireEvent.click(screen.getByText('Import from BunkerWeb'));
    await waitFor(() => screen.getByText('import-a.example.com'));
    expect(screen.getByText('Import')).toBeDisabled();
  });

  it('enables submit and shows count when candidates are selected', async () => {
    api.get
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: { candidates: CANDIDATES } });
    render(<MemoryRouter><RouteList /></MemoryRouter>);
    await waitFor(() => screen.getByText('Import from BunkerWeb'));
    fireEvent.click(screen.getByText('Import from BunkerWeb'));
    await waitFor(() => screen.getByText('import-a.example.com'));
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    expect(screen.getByText('Import (1)')).not.toBeDisabled();
  });

  it('calls POST and prepends imported routes on success', async () => {
    const imported = [{ fqdn: 'import-a.example.com', backend_host: '10.1.0.1', backend_port: 80, backend_protocol: 'http', status: 'active', name: '' }];
    api.get
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: { candidates: CANDIDATES } });
    api.post.mockResolvedValueOnce({ data: imported });
    render(<MemoryRouter><RouteList /></MemoryRouter>);
    await waitFor(() => screen.getByText('Import from BunkerWeb'));
    fireEvent.click(screen.getByText('Import from BunkerWeb'));
    await waitFor(() => screen.getByText('import-a.example.com'));
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    fireEvent.click(screen.getByText('Import (1)'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/ingress/routes/import/',
      { fqdns: ['import-a.example.com'] },
      { params: { org: 'acme' } },
    ));
    await waitFor(() => expect(screen.queryByText('Import from BunkerWeb', { selector: 'h2' })).not.toBeInTheDocument());
  });

  it('shows error when import fails', async () => {
    api.get
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({ data: { candidates: CANDIDATES } });
    api.post.mockRejectedValueOnce({ response: { data: { detail: 'Route quota exceeded.' } } });
    render(<MemoryRouter><RouteList /></MemoryRouter>);
    await waitFor(() => screen.getByText('Import from BunkerWeb'));
    fireEvent.click(screen.getByText('Import from BunkerWeb'));
    await waitFor(() => screen.getByText('import-a.example.com'));
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    fireEvent.click(screen.getByText('Import (1)'));
    await waitFor(() => expect(screen.getByText('Route quota exceeded.')).toBeInTheDocument());
  });
});
