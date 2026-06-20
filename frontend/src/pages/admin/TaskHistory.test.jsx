import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '@/lib/axios';
import TaskHistory from './TaskHistory';

const TASKS = [
  { task_id: 'a1', task_name: 'app.tasks.alpha', status: 'SUCCESS', date_created: '2026-06-01T10:00:00Z', date_done: '2026-06-01T10:00:10Z', duration: 10, worker: 'w1' },
  { task_id: 'b2', task_name: 'app.tasks.bravo', status: 'PENDING', date_created: '2026-06-02T10:00:00Z', date_done: null, duration: 120, worker: 'w2' },
];

function mockGet(tasks = TASKS) {
  api.get.mockImplementation(url => {
    if (url === '/api/admin/celery/history/') return Promise.resolve({ data: { results: tasks, count: tasks.length } });
    // detail endpoint
    return Promise.resolve({ data: tasks.find(t => url.endsWith(`${t.task_id}/`)) ?? tasks[0] });
  });
}

function renderPage() {
  return render(<MemoryRouter><TaskHistory /></MemoryRouter>);
}

// Both a mobile card list and a desktop table render in jsdom; the table is
// the deterministic surface for assertions.
const table = () => screen.getByRole('table');

describe('TaskHistory', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders heading and task rows', async () => {
    mockGet();
    renderPage();
    await waitFor(() => within(table()).getByText('…tasks.alpha'));
    expect(within(table()).getByText('…tasks.bravo')).toBeInTheDocument();
  });

  it('shows empty state', async () => {
    mockGet([]);
    renderPage();
    await waitFor(() => expect(screen.getByText('No task results found.')).toBeInTheDocument());
  });

  it('sorts by duration', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('…tasks.alpha'));
    // default duration desc → bravo (120) first
    await user.click(within(table()).getByRole('button', { name: 'Sort by Duration' }));
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('…tasks.bravo')).toBeInTheDocument();
    // toggle asc → alpha (10) first
    await user.click(within(table()).getByRole('button', { name: 'Sort by Duration' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('…tasks.alpha')).toBeInTheDocument();
  });

  it('opens the detail modal when a row is clicked', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('…tasks.bravo'));
    // PENDING task opens the modal directly (no detail fetch).
    await user.click(within(table()).getByText('…tasks.bravo'));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'app.tasks.bravo' })).toBeInTheDocument());
  });

  it('keeps search box and status filter', async () => {
    mockGet();
    renderPage();
    await waitFor(() => within(table()).getByText('…tasks.alpha'));
    expect(screen.getByPlaceholderText('Search task name…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'FAILURE' })).toBeInTheDocument();
  });
});
