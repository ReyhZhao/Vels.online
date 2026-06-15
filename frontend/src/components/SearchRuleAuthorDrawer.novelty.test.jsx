import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '../lib/axios';
import SearchRuleAuthorDrawer from './SearchRuleAuthorDrawer';

describe('SearchRuleAuthorDrawer — Novelty Constraint (ADR-0021)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: [{ id: 1, name: 'Acme', slug: 'acme' }] });
  });

  it('exposes the baseline lookback and per-leg novelty field controls', async () => {
    render(<SearchRuleAuthorDrawer initialScope="all" onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => screen.getByLabelText('Baseline lookback days'));
    expect(screen.getByLabelText('Leg 1 novelty field')).toBeInTheDocument();
  });

  it('warns that a novelty constraint needs a non-none correlation key', async () => {
    const user = userEvent.setup();
    render(<SearchRuleAuthorDrawer initialScope="all" onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => screen.getByLabelText('Leg 1 novelty field'));

    await user.type(screen.getByLabelText('Leg 1 novelty field'), 'agent.name');
    expect(screen.getByText(/novelty constraint requires a correlation key/i)).toBeInTheDocument();
  });

  it('saves novelty_field and baseline_lookback_days in the payload', async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValue({ data: { id: 7 } });
    render(<SearchRuleAuthorDrawer initialScope="all" onClose={() => {}} onSaved={() => {}} />);
    await waitFor(() => screen.getByLabelText('Baseline lookback days'));

    await user.type(screen.getByPlaceholderText('Rule name'), 'first logon');
    const baseline = screen.getByLabelText('Baseline lookback days');
    await user.clear(baseline);
    await user.type(baseline, '90');
    await user.type(screen.getByLabelText('Leg 1 novelty field'), 'agent.name');

    await user.click(screen.getByRole('button', { name: 'Save rule' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/correlations/search-rules/',
      expect.objectContaining({ baseline_lookback_days: 90 }),
    ));
    const payload = api.post.mock.calls[0][1];
    expect(payload.legs[0].novelty_field).toBe('agent.name');
  });
});
