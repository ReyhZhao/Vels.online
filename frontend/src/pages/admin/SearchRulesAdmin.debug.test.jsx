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
  ],
  severities: ['critical', 'high', 'medium', 'low', 'info'],
};

const ORGS = [{ id: 1, name: 'Acme', slug: 'acme' }];

const DEBUG_RESULT = {
  mode: 'single',
  agent_count: 1,
  window_start: '2026-06-07T10:00:00',
  window_end: '2026-06-07T11:00:00',
  legs: [{ leg_id: null, display_order: 0, count: 1, hit_query: { query: { match_all: {} } } }],
};

function mockGet() {
  api.get.mockImplementation(url => {
    if (url === '/api/correlations/catalog/') return Promise.resolve({ data: CATALOG });
    if (url === '/api/security/organizations/') return Promise.resolve({ data: ORGS });
    return Promise.resolve({ data: [] });
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
  await waitFor(() => screen.getByRole('button', { name: /Test \/ Debug run/ }));
}

describe('SearchRulesAdmin — Test/Debug run from drawer (#437)', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('posts the current unsaved form values to the spec debug endpoint and renders the summary', async () => {
    const user = userEvent.setup();
    mockGet();
    api.post.mockResolvedValue({ data: DEBUG_RESULT });
    renderPage();
    await openNewRuleDrawer(user);

    await user.type(screen.getByPlaceholderText('Rule name'), 'My unsaved rule');
    await user.click(screen.getByRole('button', { name: /Test \/ Debug run/ }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [url, body] = api.post.mock.calls[0];
    expect(url).toBe('/api/correlations/search-rules/debug/');
    expect(body.org_slug).toBe('acme');
    expect(body.name).toBe('My unsaved rule');
    expect(Array.isArray(body.legs)).toBe(true);

    // The shared debug summary renders inline in the drawer.
    await waitFor(() => expect(screen.getByText('Hit query')).toBeInTheDocument());
  });
});
