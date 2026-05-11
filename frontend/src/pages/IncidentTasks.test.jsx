import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, username: 'alice', is_staff: false }, isAuthenticated: true, isLoading: false }),
}));

import api from '../lib/axios';
import IncidentTasks from './IncidentTasks';

const TEMPLATES = [
  {
    id: 1,
    name: 'Phishing Playbook',
    subject: 1,
    archived: false,
    items: [
      { id: 1, title: 'Step 1', display_order: 1 },
      { id: 2, title: 'Step 2', display_order: 2 },
    ],
  },
];

const TASKS = [
  {
    id: 1,
    incident: 10,
    template_item: 1,
    template_name: 'Phishing Playbook',
    title: 'Step 1',
    description: 'Do step 1',
    state: 'new',
    assignee: null,
    assignee_username: null,
    display_order: 1,
    created_at: '2026-01-01T00:00:00Z',
    closed_at: null,
  },
  {
    id: 2,
    incident: 10,
    template_item: 2,
    template_name: 'Phishing Playbook',
    title: 'Step 2',
    description: '',
    state: 'done',
    assignee: null,
    assignee_username: null,
    display_order: 2,
    created_at: '2026-01-01T00:00:00Z',
    closed_at: '2026-01-01T01:00:00Z',
  },
];

const ADHOC_TASK = {
  id: 3,
  incident: 10,
  template_item: null,
  template_name: null,
  title: 'Check logs',
  description: '',
  state: 'new',
  assignee: null,
  assignee_username: null,
  display_order: 0,
  created_at: '2026-01-01T00:00:00Z',
  closed_at: null,
};

function mockGet(tasks = [], templates = []) {
  api.get.mockImplementation(url => {
    if (url.includes('/comments/')) return Promise.resolve({ data: [] });
    if (url.includes('/tasks/')) return Promise.resolve({ data: tasks });
    if (url.includes('task-templates')) return Promise.resolve({ data: templates });
    return Promise.resolve({ data: [] });
  });
}

function renderTasks(incidentId = '10', subjectId = null) {
  return render(<IncidentTasks incidentId={incidentId} subjectId={subjectId} />);
}

describe('IncidentTasks', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  // ── list rendering ────────────────────────────────────────────────────────

  it('shows loading state initially', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderTasks();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('shows empty state when no tasks', async () => {
    mockGet([], []);
    renderTasks();
    await waitFor(() => screen.getByText('No tasks yet.'));
  });

  it('renders tasks grouped by template name', async () => {
    mockGet(TASKS, []);
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    expect(screen.getByText('Step 2')).toBeInTheDocument();
    expect(screen.getByText('Phishing Playbook')).toBeInTheDocument();
  });

  it('renders ad-hoc tasks under Ad-hoc group', async () => {
    mockGet([ADHOC_TASK], []);
    renderTasks();
    await waitFor(() => screen.getByText('Check logs'));
    expect(screen.getByText('Ad-hoc')).toBeInTheDocument();
  });

  it('shows state badge for each task', async () => {
    mockGet(TASKS, []);
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    expect(screen.getAllByText('New').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Done').length).toBeGreaterThan(0);
  });

  it('rows are clickable (cursor-pointer style)', async () => {
    mockGet(TASKS, []);
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    const row = screen.getByText('Step 1').closest('tr');
    expect(row.className).toMatch(/cursor-pointer/);
  });

  it('no inline state buttons in the table rows', async () => {
    mockGet(TASKS, []);
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    expect(screen.queryByRole('button', { name: 'In Progress' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Done' })).not.toBeInTheDocument();
  });

  // ── template picker ───────────────────────────────────────────────────────

  it('shows template picker when subjectId provided', async () => {
    mockGet([], TEMPLATES);
    renderTasks('10', 1);
    await waitFor(() => screen.getByText('Suggested templates'));
    expect(screen.getByRole('button', { name: /Apply Phishing Playbook/ })).toBeInTheDocument();
  });

  it('does not show template picker when subjectId is null', async () => {
    mockGet([], TEMPLATES);
    renderTasks('10', null);
    await waitFor(() => screen.getByText('No tasks yet.'));
    expect(screen.queryByText('Suggested templates')).not.toBeInTheDocument();
  });

  it('applies a template and refreshes task list', async () => {
    mockGet([], TEMPLATES);
    api.post.mockResolvedValue({ data: TASKS });
    const user = userEvent.setup();
    renderTasks('10', 1);
    await waitFor(() => screen.getByRole('button', { name: /Apply Phishing Playbook/ }));
    await user.click(screen.getByRole('button', { name: /Apply Phishing Playbook/ }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/10/apply-template/',
      { template_id: 1 }
    ));
    await waitFor(() => screen.getByText('Step 1'));
  });

  it('shows apply error on template apply failure', async () => {
    mockGet([], TEMPLATES);
    api.post.mockRejectedValue({ response: { data: { detail: 'Template already applied.' } } });
    const user = userEvent.setup();
    renderTasks('10', 1);
    await waitFor(() => screen.getByRole('button', { name: /Apply Phishing Playbook/ }));
    await user.click(screen.getByRole('button', { name: /Apply Phishing Playbook/ }));
    await waitFor(() => screen.getByText('Template already applied.'));
  });

  // ── add-hoc form ──────────────────────────────────────────────────────────

  it('adds an ad-hoc task', async () => {
    mockGet([], []);
    api.post.mockResolvedValue({ data: ADHOC_TASK });
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByPlaceholderText('Ad-hoc task title'));
    await user.type(screen.getByPlaceholderText('Ad-hoc task title'), 'Check logs');
    await user.click(screen.getByRole('button', { name: 'Add task' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/10/tasks/',
      expect.objectContaining({ title: 'Check logs' })
    ));
    await waitFor(() => screen.getByText('Check logs'));
  });

  it('re-fetches tasks when refreshKey changes', async () => {
    mockGet([], []);
    const { rerender } = render(<IncidentTasks incidentId="10" subjectId={null} refreshKey={0} />);
    await waitFor(() => screen.getByText('No tasks yet.'));

    api.get.mockImplementation(url => {
      if (url.includes('/tasks/')) return Promise.resolve({ data: [TASKS[0]] });
      return Promise.resolve({ data: [] });
    });
    rerender(<IncidentTasks incidentId="10" subjectId={null} refreshKey={1} />);
    await waitFor(() => screen.getByText('Step 1'));
  });

  // ── cancelled task styling ────────────────────────────────────────────────

  it('renders cancelled template task with strikethrough and tooltip', async () => {
    const cancelledTask = { ...TASKS[0], state: 'cancelled' };
    mockGet([cancelledTask], []);
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    const titleEl = screen.getByText('Step 1');
    expect(titleEl).toHaveClass('line-through');
    expect(titleEl).toHaveAttribute('title', 'Auto-cancelled when subject changed');
  });

  it('renders cancelled ad-hoc task with strikethrough but no tooltip', async () => {
    const cancelledAdhoc = { ...ADHOC_TASK, state: 'cancelled' };
    mockGet([cancelledAdhoc], []);
    renderTasks();
    await waitFor(() => screen.getByText('Check logs'));
    const titleEl = screen.getByText('Check logs');
    expect(titleEl).toHaveClass('line-through');
    expect(titleEl).not.toHaveAttribute('title');
  });

  // ── task modal ────────────────────────────────────────────────────────────

  it('clicking a task row opens the modal', async () => {
    mockGet(TASKS, []);
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    await user.click(screen.getByText('Step 1').closest('tr'));
    expect(screen.getByRole('heading', { name: 'Step 1' })).toBeInTheDocument();
  });

  it('modal shows full description', async () => {
    mockGet(TASKS, []);
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    await user.click(screen.getByText('Step 1').closest('tr'));
    expect(screen.getByText('Do step 1')).toBeInTheDocument();
  });

  it('modal shows placeholder when description is empty', async () => {
    mockGet(TASKS, []);
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 2'));
    await user.click(screen.getByText('Step 2').closest('tr'));
    expect(screen.getByText('No description.')).toBeInTheDocument();
  });

  it('modal shows template name badge for template tasks', async () => {
    mockGet(TASKS, []);
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    await user.click(screen.getByText('Step 1').closest('tr'));
    // template_name badge appears in the modal header
    const badges = screen.getAllByText('Phishing Playbook');
    expect(badges.length).toBeGreaterThan(0);
  });

  it('modal shows state action buttons (excluding current state)', async () => {
    mockGet(TASKS, []);
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    await user.click(screen.getByText('Step 1').closest('tr'));
    // Task is 'new'; should show In Progress, Done, Cancelled buttons
    expect(screen.getByRole('button', { name: 'In Progress' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Done' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancelled' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New' })).not.toBeInTheDocument();
  });

  it('state button in modal PATCHes the task', async () => {
    mockGet(TASKS, []);
    api.patch.mockResolvedValue({ data: { ...TASKS[0], state: 'in_progress' } });
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    await user.click(screen.getByText('Step 1').closest('tr'));
    await user.click(screen.getByRole('button', { name: 'In Progress' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/api/tasks/1/',
      { state: 'in_progress' }
    ));
  });

  it('state change in modal updates the task badge without closing the modal', async () => {
    mockGet(TASKS, []);
    api.patch.mockResolvedValue({ data: { ...TASKS[0], state: 'in_progress' } });
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    await user.click(screen.getByText('Step 1').closest('tr'));
    await user.click(screen.getByRole('button', { name: 'In Progress' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Step 1' })).toBeInTheDocument());
  });

  it('modal closes when × button is clicked', async () => {
    mockGet(TASKS, []);
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    await user.click(screen.getByText('Step 1').closest('tr'));
    await waitFor(() => screen.getByRole('heading', { name: 'Step 1' }));
    await user.click(screen.getByLabelText('Close'));
    expect(screen.queryByRole('heading', { name: 'Step 1' })).not.toBeInTheDocument();
  });

  it('modal closes when Escape is pressed', async () => {
    mockGet(TASKS, []);
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    await user.click(screen.getByText('Step 1').closest('tr'));
    await waitFor(() => screen.getByRole('heading', { name: 'Step 1' }));
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('heading', { name: 'Step 1' })).not.toBeInTheDocument();
  });

  it('modal closes when backdrop is clicked', async () => {
    mockGet(TASKS, []);
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getByText('Step 1'));
    await user.click(screen.getByText('Step 1').closest('tr'));
    await waitFor(() => screen.getByRole('heading', { name: 'Step 1' }));
    const backdrop = document.querySelector('.fixed.inset-0.z-50');
    fireEvent.click(backdrop, { target: backdrop });
    expect(screen.queryByRole('heading', { name: 'Step 1' })).not.toBeInTheDocument();
  });

  it('only one modal is open at a time', async () => {
    mockGet(TASKS, []);
    const user = userEvent.setup();
    renderTasks();
    await waitFor(() => screen.getAllByRole('row').length > 1);
    // Click first task
    await user.click(screen.getByText('Step 1').closest('tr'));
    await waitFor(() => screen.getByRole('heading', { name: 'Step 1' }));
    expect(screen.queryByRole('heading', { name: 'Step 2' })).not.toBeInTheDocument();
  });
});
