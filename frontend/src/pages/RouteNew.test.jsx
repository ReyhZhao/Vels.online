import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('../context/OrgContext', () => ({
  useOrganization: vi.fn(),
}));

import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import RouteNew from './RouteNew';

const ACME_ORG = { slug: 'acme', name: 'Acme' };

function renderPage() {
  return render(
    <MemoryRouter>
      <RouteNew />
    </MemoryRouter>
  );
}

function fillForm({ fqdn = 'app.example.com', host = '10.0.0.1', port = '8080' } = {}) {
  fireEvent.change(screen.getByPlaceholderText('app.example.com'), { target: { value: fqdn } });
  fireEvent.change(screen.getByPlaceholderText('10.0.0.1'), { target: { value: host } });
  fireEvent.change(screen.getByPlaceholderText('8080'), { target: { value: port } });
}

describe('RouteNew', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useOrganization.mockReturnValue({ selectedOrg: ACME_ORG });
    api.get.mockResolvedValue({ data: { bunkerweb_public_ip: '' } });
  });

  it('renders form fields', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByPlaceholderText('app.example.com')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('10.0.0.1')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('8080')).toBeInTheDocument();
    });
  });

  it('displays BunkerWeb IP when returned from settings', async () => {
    api.get.mockResolvedValue({ data: { bunkerweb_public_ip: '203.0.113.42' } });
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('bunkerweb-ip')).toHaveTextContent('203.0.113.42');
    });
  });

  it('does not show BunkerWeb IP banner when IP is empty', async () => {
    api.get.mockResolvedValue({ data: { bunkerweb_public_ip: '' } });
    renderPage();
    await waitFor(() => {
      expect(screen.queryByTestId('bunkerweb-ip')).not.toBeInTheDocument();
    });
  });

  it('submits form and navigates to /routes on success', async () => {
    api.get.mockResolvedValue({ data: { bunkerweb_public_ip: '' } });
    api.post.mockResolvedValue({ data: { fqdn: 'app.example.com', status: 'active' } });
    renderPage();
    await waitFor(() => screen.getByPlaceholderText('app.example.com'));

    fillForm();
    fireEvent.click(screen.getByRole('button', { name: 'Create Route' }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/api/ingress/routes/?org=acme',
        expect.objectContaining({ fqdn: 'app.example.com', backend_port: 8080 }),
      );
      expect(mockNavigate).toHaveBeenCalledWith('/routes');
    });
  });

  it('shows error message on API failure', async () => {
    api.get.mockResolvedValue({ data: { bunkerweb_public_ip: '' } });
    api.post.mockRejectedValue({ response: { data: { detail: 'A route with this FQDN already exists.' } } });
    renderPage();
    await waitFor(() => screen.getByPlaceholderText('app.example.com'));

    fillForm();
    fireEvent.click(screen.getByRole('button', { name: 'Create Route' }));

    await waitFor(() =>
      expect(screen.getByText('A route with this FQDN already exists.')).toBeInTheDocument()
    );
  });

  it('cancel navigates back to /routes', async () => {
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: 'Cancel' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockNavigate).toHaveBeenCalledWith('/routes');
  });
});
