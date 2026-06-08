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
  search_operators: [{ value: 'contains', label: 'Contains' }],
  correlation_keys: [{ value: 'none', label: 'None (org-wide)' }],
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
  return render(<MemoryRouter><SearchRulesAdmin /></MemoryRouter>);
}

describe('SearchRulesAdmin — time-of-day window (#440)', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('submits the time window (start/end/days/mode) in the create payload', async () => {
    const user = userEvent.setup();
    mockGet();
    api.post.mockResolvedValue({ data: { id: 1, name: 'R', legs: [] } });
    renderPage();

    await waitFor(() => screen.getByText('New rule'));
    await user.click(screen.getByText('New rule'));
    await waitFor(() => screen.getByLabelText('Time window start'));

    await user.type(screen.getByPlaceholderText('Rule name'), 'After hours');
    await user.type(screen.getByLabelText('Time window start'), '22:00');
    await user.type(screen.getByLabelText('Time window end'), '06:00');
    await user.click(screen.getByRole('button', { name: 'Mon', pressed: false }));
    await user.click(screen.getByRole('button', { name: 'Tue', pressed: false }));
    await user.selectOptions(screen.getByLabelText('Time window mode'), 'outside');

    await user.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/correlations/search-rules/',
      expect.objectContaining({
        time_window_start: '22:00:00',
        time_window_end: '06:00:00',
        time_window_days: [1, 2],
        time_window_mode: 'outside',
      }),
    ));
  });

  it('sends a cleared window when no times are set', async () => {
    const user = userEvent.setup();
    mockGet();
    api.post.mockResolvedValue({ data: { id: 1, name: 'R', legs: [] } });
    renderPage();

    await waitFor(() => screen.getByText('New rule'));
    await user.click(screen.getByText('New rule'));
    await waitFor(() => screen.getByPlaceholderText('Rule name'));
    await user.type(screen.getByPlaceholderText('Rule name'), 'Plain');
    await user.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/correlations/search-rules/',
      expect.objectContaining({
        time_window_start: null,
        time_window_end: null,
        time_window_days: [],
      }),
    ));
  });
});
