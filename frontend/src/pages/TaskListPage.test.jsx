import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import TaskListPage from './TaskListPage';

const TASKS = [
  {
    id: 1,
    title: 'Review phishing email',
    state: 'new',
    created_at: '2026-05-01T10:00:00Z',
    incident_display_id: 'INC-2026-0001',
    incident_title: 'Phishing Attack',
  },
  {
    id: 2,
    title: 'Patch affected systems',
    state: 'done',
    created_at: '2026-05-02T12:00:00Z',
    incident_display_id: 'INC-2026-0002',
    incident_title: 'Malware Detected',
  },
];

const PAGE_RESPONSE = (results = TASKS, extras = {}) => ({
  data: { count: results.length, page: 1, per_page: 25, total_pages: 1, results, ...extras },
});

function renderPage(initialEntry = '/tasks') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <TaskListPage />
    </MemoryRouter>
  );
}

describe('TaskListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue(PAGE_RESPONSE());
  });

  it('renders page heading', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Tasks')).toBeInTheDocument());
  });

  it('shows loading state initially', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('renders Assignee column header', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole('button', { name: /sort by assignee/i })).toBeInTheDocument());
  });

  it('shows — in Assignee column when assignee_username is absent', async () => {
    renderPage();
    await waitFor(() => screen.getByText('Review phishing email'));
    const cells = screen.getAllByRole('cell');
    const dashCells = cells.filter(c => c.textContent === '—');
    expect(dashCells.length).toBeGreaterThan(0);
  });

  it('shows assignee_username in Assignee column when set', async () => {
    const tasksWithAssignee = [{ ...TASKS[0], assignee: 5, assignee_username: 'bob' }];
    api.get.mockResolvedValue(PAGE_RESPONSE(tasksWithAssignee));
    renderPage();
    await waitFor(() => expect(screen.getByText('bob')).toBeInTheDocument());
  });

  it('shows task titles and state badges', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Review phishing email')).toBeInTheDocument();
      expect(screen.getByText('Patch affected systems')).toBeInTheDocument();
      expect(screen.getAllByText('New').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Done').length).toBeGreaterThan(0);
    });
  });

  it('shows incident display_id as a link', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('INC-2026-0001')).toBeInTheDocument());
    const link = screen.getByText('INC-2026-0001').closest('a');
    expect(link).toHaveAttribute('href', '/incidents/INC-2026-0001');
  });

  it('shows incident title alongside display_id', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/Phishing Attack/)).toBeInTheDocument());
  });

  it('shows empty state when no tasks', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE([]));
    renderPage();
    await waitFor(() => expect(screen.getByText('No tasks found.')).toBeInTheDocument());
  });

  it('shows error on fetch failure', async () => {
    api.get.mockRejectedValue({ response: { data: { detail: 'Permission denied.' } } });
    renderPage();
    await waitFor(() => expect(screen.getByText('Permission denied.')).toBeInTheDocument());
  });

  it('fetches from /api/tasks/ on mount', async () => {
    renderPage();
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/tasks/', expect.any(Object))
    );
  });

  it('title search input re-fetches with q param', async () => {
    renderPage();
    await waitFor(() => screen.getByLabelText('Search tasks'));
    fireEvent.change(screen.getByLabelText('Search tasks'), { target: { value: 'phishing' } });
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/tasks/', expect.objectContaining({
        params: expect.objectContaining({ q: 'phishing' }),
      }))
    );
  });

  it('state filter dropdown re-fetches with state param', async () => {
    renderPage();
    await waitFor(() => screen.getByLabelText('State filter'));
    fireEvent.change(screen.getByLabelText('State filter'), { target: { value: 'done' } });
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/tasks/', expect.objectContaining({
        params: expect.objectContaining({ state: 'done' }),
      }))
    );
  });

  it('renders sortable column headers', async () => {
    renderPage();
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    expect(screen.getByLabelText('Sort by State')).toBeInTheDocument();
    expect(screen.getByLabelText('Sort by Incident')).toBeInTheDocument();
    expect(screen.getByLabelText('Sort by Created')).toBeInTheDocument();
  });

  it('clicking a sort header adds sort and order params', async () => {
    renderPage();
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    fireEvent.click(screen.getByLabelText('Sort by Title'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/tasks/', expect.objectContaining({
        params: expect.objectContaining({ sort: 'title', order: 'asc' }),
      }))
    );
  });

  it('clicking the active sort header toggles direction', async () => {
    renderPage('/tasks?sort=title&order=asc');
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    fireEvent.click(screen.getByLabelText('Sort by Title'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/tasks/', expect.objectContaining({
        params: expect.objectContaining({ sort: 'title', order: 'desc' }),
      }))
    );
  });

  it('shows direction indicator on active sort column', async () => {
    renderPage('/tasks?sort=title&order=asc');
    await waitFor(() => screen.getByLabelText('Sort by Title'));
    expect(screen.getByLabelText('Sort by Title').textContent).toContain('▲');
  });

  it('renders pagination when total_pages > 1', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE(TASKS, { count: 50, total_pages: 2 }));
    renderPage();
    await waitFor(() => screen.getByText('2'));
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('clicking page button re-fetches with page param', async () => {
    api.get.mockResolvedValue(PAGE_RESPONSE(TASKS, { count: 50, total_pages: 2 }));
    renderPage();
    await waitFor(() => screen.getByText('2'));
    fireEvent.click(screen.getByText('2'));
    await waitFor(() =>
      expect(api.get).toHaveBeenCalledWith('/api/tasks/', expect.objectContaining({
        params: expect.objectContaining({ page: '2' }),
      }))
    );
  });
});
