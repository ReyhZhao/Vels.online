import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import SearchRulesAdmin from './SearchRulesAdmin';

const CATALOG = { search_operators: [], correlation_keys: [], severities: ['high'] };
const ORGS = [{ id: 1, name: 'Acme', slug: 'acme' }];

const RULE = {
  id: 5, name: 'Brute Force', organization: 1, severity: 'high',
  correlation_key: 'none', window_minutes: 60, interval_minutes: 15,
  enabled: true, legs: [{}], test_summary: { total: 4, passing: 3, failing: 1, error: 0, never: 0 },
};

function mockGet(rules = [RULE]) {
  api.get.mockImplementation(url => {
    if (url === '/api/correlations/catalog/') return Promise.resolve({ data: CATALOG });
    if (url === '/api/security/organizations/') return Promise.resolve({ data: ORGS });
    return Promise.resolve({ data: rules });
  });
}

function renderPage() {
  return render(<MemoryRouter><SearchRulesAdmin /></MemoryRouter>);
}

// Both a mobile card list and a desktop table render in jsdom; scope row
// assertions to the desktop table.
const table = () => screen.getByRole('table');

describe('SearchRulesAdmin — test health badge + run all', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows the test health badge from the rule summary', async () => {
    mockGet();
    renderPage();
    await waitFor(() => expect(within(table()).getByText('Tests 3/4')).toBeInTheDocument());
  });

  it('runs all tests and updates the badge from the response', async () => {
    mockGet();
    api.post.mockResolvedValue({ data: { summary: { total: 4, passing: 4, failing: 0, error: 0, never: 0 }, results: [] } });
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => within(table()).getByText('Tests 3/4'));
    await user.click(within(table()).getByRole('button', { name: 'Actions' }));
    await user.click(screen.getByText('Run tests'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/correlations/search-rules/5/tests/run-all/'));
    await waitFor(() => expect(within(table()).getByText('Tests 4/4')).toBeInTheDocument());
  });

  it('shows "No tests" when the rule has none', async () => {
    mockGet([{ ...RULE, test_summary: { total: 0, passing: 0, failing: 0, error: 0, never: 0 } }]);
    renderPage();
    await waitFor(() => expect(within(table()).getByText('No tests')).toBeInTheDocument());
  });
});
