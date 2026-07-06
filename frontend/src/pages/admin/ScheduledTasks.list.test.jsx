import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

import api from '@/lib/axios';
import ScheduledTasks from './ScheduledTasks';

function mkTask(over = {}) {
  return {
    id: 1,
    name: 'poll-inbound-mail-every-2-min',
    task: 'inbound_mail.tasks.poll_inbound_mail',
    schedule_display: 'every 2 minutes',
    last_run_at: '2026-07-06T10:00:00Z',
    next_run: '2026-07-06T10:02:00Z',
    enabled: true,
    ...over,
  };
}

const TASKS = [
  mkTask(),
  mkTask({
    id: 2,
    name: 'auto-close-stale-incidents-daily',
    task: 'incidents.tasks.auto_close_stale_incidents',
    schedule_display: '0 2 * * *',
    enabled: false,
  }),
];

function mockGet(tasks = TASKS) {
  api.get.mockResolvedValue({ data: tasks });
}

const table = () => screen.getByRole('table');

describe('ScheduledTasks — list affordances', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('filters by search query (name or task path)', async () => {
    mockGet();
    const user = userEvent.setup();
    render(<ScheduledTasks />);
    await waitFor(() => within(table()).getByText('poll-inbound-mail-every-2-min'));
    await user.type(screen.getByLabelText('Search tasks'), 'auto_close');
    await waitFor(() =>
      expect(within(table()).queryByText('poll-inbound-mail-every-2-min')).not.toBeInTheDocument(),
    );
    expect(within(table()).getByText('auto-close-stale-incidents-daily')).toBeInTheDocument();
  });

  it('filters by enabled/disabled status', async () => {
    mockGet();
    const user = userEvent.setup();
    render(<ScheduledTasks />);
    await waitFor(() => within(table()).getByText('poll-inbound-mail-every-2-min'));
    await user.selectOptions(screen.getByLabelText('Status filter'), 'disabled');
    await waitFor(() =>
      expect(within(table()).queryByText('poll-inbound-mail-every-2-min')).not.toBeInTheDocument(),
    );
    expect(within(table()).getByText('auto-close-stale-incidents-daily')).toBeInTheDocument();
  });

  it('sorts by name and toggles direction', async () => {
    mockGet();
    const user = userEvent.setup();
    render(<ScheduledTasks />);
    await waitFor(() => within(table()).getByText('poll-inbound-mail-every-2-min'));
    // Default sort is name asc: auto-close < poll.
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('auto-close-stale-incidents-daily')).toBeInTheDocument();
    // Clicking Name toggles to desc: poll first.
    await user.click(within(table()).getByRole('button', { name: 'Sort by Name' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('poll-inbound-mail-every-2-min')).toBeInTheDocument();
  });

  it('shows a no-match state when search excludes everything', async () => {
    mockGet();
    const user = userEvent.setup();
    render(<ScheduledTasks />);
    await waitFor(() => within(table()).getByText('poll-inbound-mail-every-2-min'));
    await user.type(screen.getByLabelText('Search tasks'), 'zzzznope');
    await waitFor(() => expect(screen.getByText('No tasks match your search.')).toBeInTheDocument());
  });
});
