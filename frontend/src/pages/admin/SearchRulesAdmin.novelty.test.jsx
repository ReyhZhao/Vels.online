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
  await waitFor(() => screen.getByLabelText('Leg 1 novelty field'));
}

describe('SearchRulesAdmin — Novelty Constraint UI', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('exposes a baseline lookback input and a novelty field input', async () => {
    const user = userEvent.setup();
    mockGet();
    renderPage();
    await openNewRuleDrawer(user);

    expect(screen.getByLabelText('Baseline lookback days')).toBeInTheDocument();
    expect(screen.getByLabelText('Leg 1 novelty field')).toBeInTheDocument();
  });

  it('explains how novelty differs from diversity once a field is entered', async () => {
    const user = userEvent.setup();
    mockGet();
    renderPage();
    await openNewRuleDrawer(user);

    await user.type(screen.getByLabelText('Leg 1 novelty field'), 'agent.name');
    expect(screen.getByText(/never seen before/i)).toBeInTheDocument();
  });

  it('warns that a novelty constraint requires a non-none correlation key', async () => {
    const user = userEvent.setup();
    mockGet();
    renderPage();
    await openNewRuleDrawer(user);

    await user.type(screen.getByLabelText('Leg 1 novelty field'), 'agent.name');
    expect(screen.getByText(/novelty constraint requires a correlation key/i)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('Correlation key'), 'user.name');
    expect(screen.queryByText(/novelty constraint requires a correlation key/i)).not.toBeInTheDocument();
  });

  it('round-trips novelty_field and baseline_lookback_days in the create payload', async () => {
    const user = userEvent.setup();
    mockGet();
    api.post.mockResolvedValue({ data: { id: 1 } });
    renderPage();
    await openNewRuleDrawer(user);

    await user.type(screen.getByPlaceholderText('Rule name'), 'first logon');
    await user.selectOptions(screen.getByLabelText('Correlation key'), 'user.name');
    await user.type(screen.getByLabelText('Leg 1 novelty field'), 'agent.name');
    const baseline = screen.getByLabelText('Baseline lookback days');
    await user.clear(baseline);
    await user.type(baseline, '90');

    await user.click(screen.getByText('Create rule'));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const payload = api.post.mock.calls[0][1];
    expect(payload.baseline_lookback_days).toBe(90);
    expect(payload.legs[0].novelty_field).toBe('agent.name');
  });
});
