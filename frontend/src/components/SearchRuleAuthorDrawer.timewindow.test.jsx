import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '../lib/axios';
import SearchRuleAuthorDrawer from './SearchRuleAuthorDrawer';

describe('SearchRuleAuthorDrawer — time-of-day window (#440)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: [{ id: 1, name: 'Acme', slug: 'acme' }] });
  });

  it('renders the time-window controls and saves them in the payload', async () => {
    const user = userEvent.setup();
    api.post.mockResolvedValue({ data: { id: 7 } });
    render(<SearchRuleAuthorDrawer initialScope="all" onClose={() => {}} onSaved={() => {}} />);

    await waitFor(() => screen.getByLabelText('Time window start'));

    await user.type(screen.getByPlaceholderText('Rule name'), 'After hours logins');
    await user.type(screen.getByLabelText('Time window start'), '22:00');
    await user.type(screen.getByLabelText('Time window end'), '06:00');
    await user.click(screen.getByRole('button', { name: 'Sat', pressed: false }));
    await user.selectOptions(screen.getByLabelText('Time window mode'), 'outside');

    await user.click(screen.getByRole('button', { name: 'Save rule' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/correlations/search-rules/',
      expect.objectContaining({
        time_window_start: '22:00:00',
        time_window_end: '06:00:00',
        time_window_days: [6],
        time_window_mode: 'outside',
      }),
    ));
  });
});
