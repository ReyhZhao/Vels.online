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

describe('SearchRulesAdmin — clone rule', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('opens the builder in create mode pre-filled with a "Copy of" name', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Brute Force');
    await user.click(screen.getByText('Clone'));

    // Create mode, not edit mode.
    expect(await screen.findByText('New Scheduled Search Rule')).toBeInTheDocument();
    expect(screen.getByText('Create rule')).toBeInTheDocument();
    // Source values carried over, name disambiguated.
    expect(screen.getByDisplayValue('Copy of Brute Force')).toBeInTheDocument();
    expect(screen.getByDisplayValue('detect brute force')).toBeInTheDocument();
    expect(screen.getByDisplayValue('5710')).toBeInTheDocument();
  });

  it('saves a clone via POST (create), leaving the source rule untouched', async () => {
    mockGet();
    api.post.mockResolvedValue({ data: { ...RULE, id: 6, name: 'Copy of Brute Force' } });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Brute Force');
    await user.click(screen.getByText('Clone'));
    await screen.findByText('Create rule');
    await user.click(screen.getByText('Create rule'));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [url, payload] = api.post.mock.calls[0];
    expect(url).toBe('/api/correlations/search-rules/');
    expect(payload.name).toBe('Copy of Brute Force');
    expect(payload.correlation_key).toBe('source_ip');
    expect(payload.legs).toHaveLength(1);
    expect(payload.legs[0].conditions[0].value).toBe('5710');
    // The original rule must never be PATCHed by a clone.
    expect(api.patch).not.toHaveBeenCalled();
  });
});
