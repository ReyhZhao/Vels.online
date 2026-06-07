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
  await waitFor(() => screen.getByLabelText('Leg 1 distinct field'));
}

describe('SearchRulesAdmin — Diversity Constraint UI', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('reveals the min-distinct input once a distinct field is entered', async () => {
    const user = userEvent.setup();
    mockGet();
    renderPage();
    await openNewRuleDrawer(user);

    // Before entering a distinct field, the min-distinct control is absent.
    expect(screen.queryByLabelText('Leg 1 min distinct')).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Leg 1 distinct field'), 'GeoLocation.country_name');

    expect(screen.getByLabelText('Leg 1 min distinct')).toBeInTheDocument();
  });

  it('warns that a diversity constraint requires a non-none correlation key', async () => {
    const user = userEvent.setup();
    mockGet();
    renderPage();
    await openNewRuleDrawer(user);

    // Default correlation key is "none"; entering a distinct field must surface the guard.
    await user.type(screen.getByLabelText('Leg 1 distinct field'), 'GeoLocation.country_name');
    expect(screen.getByText(/requires a correlation key/i)).toBeInTheDocument();

    // Selecting a real key clears the guard.
    await user.selectOptions(screen.getByLabelText('Correlation key'), 'user.name');
    expect(screen.queryByText(/requires a correlation key/i)).not.toBeInTheDocument();
  });

  it('surfaces a server validation error when a blocked diversity rule is saved', async () => {
    const user = userEvent.setup();
    mockGet();
    api.post.mockRejectedValue({
      response: { data: { legs: 'Leg 1: min_distinct must be at least 2 for a diversity constraint.' } },
    });
    renderPage();
    await openNewRuleDrawer(user);

    await user.type(screen.getByPlaceholderText('Rule name'), 'Bad diversity');
    await user.type(screen.getByLabelText('Leg 1 distinct field'), 'GeoLocation.country_name');
    await user.selectOptions(screen.getByLabelText('Correlation key'), 'user.name');

    await user.click(screen.getByText('Create rule'));

    await waitFor(() =>
      expect(screen.getByText(/min_distinct must be at least 2/i)).toBeInTheDocument()
    );
  });
});
