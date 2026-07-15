import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));
vi.mock('../context/OrgContext', () => ({
  useOrganization: () => ({ selectedOrg: { slug: 'acme', name: 'Acme Corp' } }),
}));
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { is_staff: true } }),
}));

import api from '../lib/axios';
import AssetsPage from './AssetsPage';

const INFRA = { id: 9, slug: 'infrastructure', name: 'Shared Infrastructure', is_infrastructure: true };

function mockRoutes({ assets = [] } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/api/security/organizations/') return Promise.resolve({ data: [INFRA] });
    if (url === '/api/assets/') return Promise.resolve({ data: { results: assets } });
    return Promise.resolve({ data: [] });
  });
}

describe('AssetsPage — Shared Infrastructure scope (staff)', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('fetches the infra org and defaults to the current tenant', async () => {
    mockRoutes({ assets: [] });
    render(<MemoryRouter><AssetsPage /></MemoryRouter>);
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/security/organizations/', { params: { include_infrastructure: 1 } })
    );
    expect(api.get).toHaveBeenCalledWith('/api/assets/', { params: { org: 'acme' } });
  });

  it('switches the list scope to the infra org', async () => {
    mockRoutes({ assets: [] });
    render(<MemoryRouter><AssetsPage /></MemoryRouter>);

    const infraBtn = await screen.findByRole('button', { name: 'Shared Infrastructure' });
    fireEvent.click(infraBtn);
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/assets/', { params: { org: 'infrastructure' } })
    );
  });
});
