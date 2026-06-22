import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import SearchRulesAdmin from './SearchRulesAdmin';

const CATALOG = {
  search_operators: [{ value: 'equals', label: 'equals' }],
  correlation_keys: [{ value: 'none', label: 'None' }, { value: 'source_ip', label: 'Source IP' }],
  severities: ['critical', 'high', 'medium', 'low', 'info'],
};
const ORGS = [{ id: 1, name: 'Acme', slug: 'acme' }];

const RULE = {
  id: 5,
  name: 'Brute Force',
  description: 'detect brute force',
  organization: 1,
  severity: 'high',
  correlation_key: 'source_ip',
  window_minutes: 60,
  interval_minutes: 15,
  max_findings_per_run: 50,
  include_agentless: false,
  enabled: true,
  legs: [
    { count: 3, display_order: 0, distinct_field: '', min_distinct: 2, conditions: [{ field_name: 'rule.id', operator: 'equals', value: '5710' }] },
  ],
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
// interactions to the desktop table.
const table = () => screen.getByRole('table');

describe('SearchRulesAdmin — clickable rule name', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('opens the edit drawer pre-populated when the rule name is clicked', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => within(table()).getByRole('button', { name: 'Brute Force' }));
    await user.click(within(table()).getByRole('button', { name: 'Brute Force' }));

    // Same edit UI as the row actions menu's Edit item.
    expect(await screen.findByText('Edit Search Rule')).toBeInTheDocument();
    expect(screen.getByText('Save changes')).toBeInTheDocument();
    // Pre-populated with the rule's existing values.
    expect(screen.getByDisplayValue('Brute Force')).toBeInTheDocument();
    expect(screen.getByDisplayValue('detect brute force')).toBeInTheDocument();
  });

  it('reaches the same edit UI as the actions menu Edit item', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => within(table()).getByRole('button', { name: 'Brute Force' }));
    await user.click(within(table()).getByRole('button', { name: 'Actions' }));
    await user.click(screen.getByText('Edit'));

    expect(await screen.findByText('Edit Search Rule')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Brute Force')).toBeInTheDocument();
  });
});
