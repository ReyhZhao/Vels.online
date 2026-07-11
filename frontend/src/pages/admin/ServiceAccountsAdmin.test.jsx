import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import ServiceAccountsAdmin from './ServiceAccountsAdmin';

const ORGS = [
  { slug: 'acme', name: 'Acme' },
  { slug: 'contoso', name: 'Contoso' },
];

const ACCOUNTS = [
  {
    id: 1,
    name: 'CI pipeline',
    description: 'for CI',
    orgs: [{ slug: 'acme', name: 'Acme' }],
    created_by_username: 'alice',
    created_at: '2026-01-15T10:00:00Z',
  },
];

function mockGet(accounts = ACCOUNTS, orgs = ORGS) {
  api.get.mockImplementation(url => {
    if (url.includes('/service-accounts/')) return Promise.resolve({ data: accounts });
    if (url.includes('/organizations/')) return Promise.resolve({ data: orgs });
    return Promise.resolve({ data: [] });
  });
}

describe('ServiceAccountsAdmin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom lacks clipboard by default
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue() } });
  });

  it('lists existing service accounts with their orgs', async () => {
    mockGet();
    render(<ServiceAccountsAdmin />);
    await waitFor(() => screen.getByText('CI pipeline'));
    expect(screen.getByText(/Created by alice/)).toBeInTheDocument();
    // The account's granted org renders as a chip.
    expect(screen.getAllByText('Acme').length).toBeGreaterThan(0);
  });

  it('creates a service account and reveals the token once', async () => {
    mockGet([]);
    api.post.mockResolvedValue({
      data: { id: 2, name: 'New', orgs: [], token: 'sekret-token-value' },
    });
    render(<ServiceAccountsAdmin />);
    await waitFor(() => screen.getByText('No service accounts yet.'));

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'New' } });
    fireEvent.click(screen.getByRole('button', { name: /Create service account/i }));

    await waitFor(() => screen.getByText('sekret-token-value'));
    expect(api.post).toHaveBeenCalledWith(
      '/api/security/service-accounts/',
      expect.objectContaining({ name: 'New' }),
    );
    expect(screen.getByText(/will not be shown again/i)).toBeInTheDocument();
  });

  it('rotates a token and shows the new value', async () => {
    mockGet();
    api.post.mockResolvedValue({ data: { token: 'rotated-token' } });
    render(<ServiceAccountsAdmin />);
    await waitFor(() => screen.getByText('CI pipeline'));

    fireEvent.click(screen.getByRole('button', { name: /Rotate token/i }));

    await waitFor(() => screen.getByText('rotated-token'));
    expect(api.post).toHaveBeenCalledWith('/api/security/service-accounts/1/rotate-token/');
  });

  it('revokes a service account after confirmation', async () => {
    mockGet();
    api.delete.mockResolvedValue({ data: {} });
    render(<ServiceAccountsAdmin />);
    await waitFor(() => screen.getByText('CI pipeline'));

    fireEvent.click(screen.getByRole('button', { name: /Revoke/i }));
    fireEvent.click(screen.getByRole('button', { name: /Confirm/i }));

    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/security/service-accounts/1/'));
  });
});
