import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

vi.mock('../context/OrgContext', () => {
  const selectedOrg = { slug: 'acme', name: 'Acme Corp' };
  return { useOrganization: vi.fn(() => ({ selectedOrg })) };
});

import api from '../lib/axios';
import AssetsPage from './AssetsPage';

const ASSETS = [
  { id: 1, name: 'zulu-host', kind: 'host', agent_name: 'zulu', ip_address: '10.0.0.9', role: 'server', is_active: true, is_permanent: false, internet_facing: false, last_seen_at: '2026-06-01T10:00:00Z' },
  { id: 2, name: 'alpha-host', kind: 'host', agent_name: 'alpha', ip_address: '10.0.0.1', role: 'workstation', is_active: true, is_permanent: false, internet_facing: true, last_seen_at: '2026-06-10T10:00:00Z' },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <AssetsPage />
    </MemoryRouter>
  );
}

describe('AssetsPage — mobile layout + sort', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { results: ASSETS } });
  });

  it('renders a sm:hidden mobile card list containing each asset', async () => {
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/assets/', expect.any(Object)));

    // Wait for the async load to render before asserting on content.
    await waitFor(() => {
      const cardList = document.querySelector('.sm\\:hidden');
      expect(cardList.textContent).toContain('alpha-host');
    });
    const cardList = document.querySelector('.sm\\:hidden');
    expect(cardList.textContent).toContain('zulu-host');
    expect(cardList.textContent).toContain('alpha-host');
  });

  it('renders sortable Name, Kind and Last Seen headers', async () => {
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: /sort by name/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sort by kind/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sort by last seen/i })).toBeInTheDocument();
  });

  it('sorts by name ascending by default and toggles to descending on header click', async () => {
    renderPage();

    // Wait for the async load to render real rows (not the "Loading…" row).
    await waitFor(() => {
      const rows = within(document.querySelector('table')).getAllByRole('row').slice(1);
      expect(rows[0].textContent).toContain('alpha-host'); // asc default
    });

    fireEvent.click(screen.getByRole('button', { name: /sort by name/i }));

    await waitFor(() => {
      const rows = within(document.querySelector('table')).getAllByRole('row').slice(1);
      expect(rows[0].textContent).toContain('zulu-host'); // desc after toggle
    });
  });
});
