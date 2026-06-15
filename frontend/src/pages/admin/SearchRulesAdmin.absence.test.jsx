import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import SearchRulesAdmin from './SearchRulesAdmin';

const CATALOG = {
  search_operators: [
    { value: 'equals', label: 'Equals' },
    { value: 'contains', label: 'Contains' },
  ],
  correlation_keys: [
    { value: 'none', label: 'None (org-wide)' },
    { value: 'user.name', label: 'Username (user.name)' },
  ],
  count_operators: [
    { value: 'gte', label: 'At least (≥)' },
    { value: 'lte', label: 'At most (≤)' },
  ],
  severities: ['critical', 'high', 'medium', 'low', 'info'],
};

const ORGS = [{ id: 1, name: 'Acme', slug: 'acme' }];

function mockGet() {
  api.get.mockImplementation(url => {
    if (url === '/api/correlations/catalog/') return Promise.resolve({ data: CATALOG });
    if (url === '/api/security/organizations/') return Promise.resolve({ data: ORGS });
    return Promise.resolve({ data: [] }); // search-rules list
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <SearchRulesAdmin />
    </MemoryRouter>
  );
}

async function openNewRuleDrawer(user) {
  await waitFor(() => screen.getByText('New rule'));
  await user.click(screen.getByText('New rule'));
  await waitFor(() => screen.getByLabelText('Leg 1 count operator'));
}

describe('SearchRulesAdmin — Absence Firing (count operator)', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('reveals the absence hint once the ≤ operator is selected', async () => {
    const user = userEvent.setup();
    mockGet();
    renderPage();
    await openNewRuleDrawer(user);

    expect(screen.queryByText(/Absence firing/i)).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Leg 1 count operator'), 'lte');
    expect(screen.getByText(/Absence firing/i)).toBeInTheDocument();
  });

  it('warns that ≤ is only supported with the None correlation key', async () => {
    const user = userEvent.setup();
    mockGet();
    renderPage();
    await openNewRuleDrawer(user);

    await user.selectOptions(screen.getByLabelText('Leg 1 count operator'), 'lte');
    // Default key is "none" → no guard.
    expect(screen.queryByText(/only supported when the correlation key is/i)).not.toBeInTheDocument();

    // Switching to a real correlation key surfaces the guard.
    await user.selectOptions(screen.getByLabelText('Correlation key'), 'user.name');
    expect(screen.getByText(/only supported when the correlation key is/i)).toBeInTheDocument();
  });

  it('submits the leg with count_operator=lte', async () => {
    const user = userEvent.setup();
    mockGet();
    api.post.mockResolvedValue({ data: { id: 1, legs: [] } });
    renderPage();
    await openNewRuleDrawer(user);

    await user.type(screen.getByPlaceholderText('Rule name'), 'No firewall logs');
    await user.selectOptions(screen.getByLabelText('Leg 1 count operator'), 'lte');
    await user.click(screen.getByText('Create rule'));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const body = api.post.mock.calls[0][1];
    expect(body.legs[0].count_operator).toBe('lte');
  });
});
