import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));
vi.mock('../context/OrgContext', () => ({
  useOrganization: () => ({ selectedOrg: { slug: 'acme', name: 'Acme Corp' } }),
}));
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { is_staff: true } }),
}));

import api from '../lib/axios';
import ContactsPage from './ContactsPage';

const INFRA = { id: 9, slug: 'infrastructure', name: 'Shared Infrastructure', is_infrastructure: true };

function mockRoutes({ contacts = [] } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/api/security/organizations/') return Promise.resolve({ data: [INFRA] });
    if (url === '/api/contacts/') return Promise.resolve({ data: contacts });
    return Promise.resolve({ data: [] });
  });
}

describe('ContactsPage — Shared Infrastructure scope (staff)', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('fetches the infra org with the opt-in flag and defaults to the current tenant', async () => {
    mockRoutes({ contacts: [] });
    render(<MemoryRouter><ContactsPage /></MemoryRouter>);
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/security/organizations/', { params: { include_infrastructure: 1 } })
    );
    expect(api.get).toHaveBeenCalledWith('/api/contacts/', { params: { org: 'acme' } });
  });

  it('switches the list scope to the infra org and creates against it', async () => {
    mockRoutes({ contacts: [] });
    render(<MemoryRouter><ContactsPage /></MemoryRouter>);

    const infraBtn = await screen.findByRole('button', { name: 'Shared Infrastructure' });
    fireEvent.click(infraBtn);
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/contacts/', { params: { org: 'infrastructure' } })
    );

    api.post.mockResolvedValue({ data: { id: 5, name: 'Infra Contact', email: 'i@x.com', job_title: '', department: '' } });
    fireEvent.click(screen.getByText('New Contact'));
    fireEvent.change(screen.getByLabelText('Name *'), { target: { value: 'Infra Contact' } });
    fireEvent.change(screen.getByLabelText('Email *'), { target: { value: 'i@x.com' } });
    fireEvent.click(screen.getByText('Create'));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/contacts/', expect.objectContaining({ org: 'infrastructure' }))
    );
  });
});
