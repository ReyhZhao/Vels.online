import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import SearchRulesAdmin from './SearchRulesAdmin';

const CATALOG = { search_operators: [], correlation_keys: [], severities: ['critical', 'high', 'medium', 'low', 'info'] };
const ORGS = [{ id: 1, name: 'Acme', slug: 'acme' }];

function mkRule(over = {}) {
  return {
    id: 1, name: 'Alpha Rule', organization: 1, severity: 'high',
    correlation_key: 'none', window_minutes: 60, interval_minutes: 15,
    enabled: true, legs: [{}], ...over,
  };
}

const RULES = [
  mkRule(),
  mkRule({ id: 2, name: 'Bravo Rule', organization: null, severity: 'critical', enabled: false }),
];

function mockGet(rules = RULES) {
  api.get.mockImplementation(url => {
    if (url === '/api/correlations/catalog/') return Promise.resolve({ data: CATALOG });
    if (url === '/api/security/organizations/') return Promise.resolve({ data: ORGS });
    return Promise.resolve({ data: rules });
  });
}

function renderPage() {
  return render(<MemoryRouter><SearchRulesAdmin /></MemoryRouter>);
}

const table = () => screen.getByRole('table');

describe('SearchRulesAdmin — list affordances', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('filters by search query', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha Rule'));
    await user.type(screen.getByLabelText('Search rules'), 'bravo');
    await waitFor(() => expect(within(table()).queryByText('Alpha Rule')).not.toBeInTheDocument());
    expect(within(table()).getByText('Bravo Rule')).toBeInTheDocument();
  });

  it('filters by enabled/disabled status', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha Rule'));
    await user.selectOptions(screen.getByLabelText('Status filter'), 'disabled');
    await waitFor(() => expect(within(table()).queryByText('Alpha Rule')).not.toBeInTheDocument());
    expect(within(table()).getByText('Bravo Rule')).toBeInTheDocument();
  });

  it('filters by organization (system vs org)', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha Rule'));
    await user.selectOptions(screen.getByLabelText('Organization filter'), 'system');
    await waitFor(() => expect(within(table()).queryByText('Alpha Rule')).not.toBeInTheDocument());
    expect(within(table()).getByText('Bravo Rule')).toBeInTheDocument();
  });

  it('sorts by name', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha Rule'));
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Alpha Rule')).toBeInTheDocument();
    await user.click(within(table()).getByRole('button', { name: 'Sort by Name' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Bravo Rule')).toBeInTheDocument();
  });

  it('bulk-disables selected rules', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: mkRule({ enabled: false }) });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha Rule'));
    await user.click(within(table()).getByLabelText('Select Alpha Rule'));
    await user.click(screen.getByRole('button', { name: 'Disable selected' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/correlations/search-rules/1/', { enabled: false }));
  });

  it('bulk-deletes selected rules after confirmation', async () => {
    mockGet();
    api.delete.mockResolvedValue({});
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha Rule'));
    await user.click(within(table()).getByLabelText('Select Alpha Rule'));
    await user.click(screen.getByRole('button', { name: 'Delete selected' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/correlations/search-rules/1/'));
  });

  it('shows empty state', async () => {
    mockGet([]);
    renderPage();
    await waitFor(() => expect(screen.getAllByText('No scheduled search rules.').length).toBeGreaterThan(0));
  });

  it('renders the kebab menu outside the overflow-hidden table wrapper so it is not clipped (#590)', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Alpha Rule'));

    const triggers = within(table()).getAllByRole('button', { name: 'Actions' });
    await user.click(triggers[triggers.length - 1]); // last row

    // The menu is portalled to the body, so all items are reachable...
    const deleteItem = await screen.findByText('Delete');
    expect(deleteItem).toBeInTheDocument();
    // ...and it is *not* a descendant of the clipped table wrapper.
    expect(within(table()).queryByText('Delete')).not.toBeInTheDocument();

    // Outside click still closes it.
    await user.click(document.body);
    await waitFor(() => expect(screen.queryByText('Delete')).not.toBeInTheDocument());
  });
});
