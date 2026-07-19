import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import TaskTemplatesAdmin from './TaskTemplatesAdmin';

const SUBJECTS = [
  { id: 1, name: 'Phishing', slug: 'phishing', archived: false },
  { id: 2, name: 'Malware', slug: 'malware', archived: false },
];

const TEMPLATES = [
  {
    id: 1,
    name: 'Phishing Playbook',
    subject: 1,
    subject_slug: 'phishing',
    subject_name: 'Phishing',
    description: 'Phishing response steps.',
    is_auto_apply: true,
    archived: false,
    created_by: null,
    created_by_username: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    items: [
      { id: 1, title: 'Step 1', description: '', display_order: 1 },
      { id: 2, title: 'Step 2', description: '', display_order: 2 },
    ],
  },
  {
    id: 2,
    name: 'Malware Playbook',
    subject: 2,
    subject_slug: 'malware',
    subject_name: 'Malware',
    description: '',
    is_auto_apply: false,
    archived: true,
    created_by: null,
    created_by_username: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    items: [],
  },
];

function mockGet(templates = TEMPLATES, subjects = SUBJECTS) {
  api.get.mockImplementation(url => {
    if (url === '/api/subjects/') return Promise.resolve({ data: subjects });
    return Promise.resolve({ data: templates });
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <TaskTemplatesAdmin />
    </MemoryRouter>
  );
}

// Both a mobile card list and a desktop table render in jsdom (no media
// queries), so the desktop table is the deterministic surface for assertions.
function table() {
  return screen.getByRole('table');
}

// Open a template's desktop kebab and return the rendered menu container.
async function openKebab(user, name) {
  await user.click(within(table()).getByLabelText(`Actions for ${name}`));
  return within(table()).getByRole('menu');
}

describe('TaskTemplatesAdmin', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders page heading', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('Task Templates'));
  });

  it('shows loading state', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getAllByText('Loading…').length).toBeGreaterThan(0);
  });

  it('shows empty state', async () => {
    mockGet([], SUBJECTS);
    renderPage();
    await waitFor(() => expect(screen.getAllByText('No templates.').length).toBeGreaterThan(0));
  });

  it('renders template rows with subject and status', async () => {
    mockGet();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    expect(within(table()).getByText('Malware Playbook')).toBeInTheDocument();
    expect(within(table()).getByText('Auto-apply')).toBeInTheDocument();
    expect(within(table()).getByText('Archived')).toBeInTheDocument();
    expect(within(table()).getByText('Active')).toBeInTheDocument();
  });

  it('shows item count in table', async () => {
    mockGet();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    expect(within(table()).getByText('2')).toBeInTheDocument();
  });

  it('creates a new template', async () => {
    mockGet();
    api.post.mockResolvedValue({
      data: {
        id: 3, name: 'New Template', subject: 1, subject_slug: 'phishing',
        subject_name: 'Phishing', description: '', is_auto_apply: false,
        archived: false, created_by: null, created_by_username: null,
        created_at: '2026-05-01T00:00:00Z', updated_at: '2026-05-01T00:00:00Z', items: [],
      },
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByPlaceholderText('Template name'));
    await user.type(screen.getByPlaceholderText('Template name'), 'New Template');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Subject' }), '1');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/task-templates/', expect.objectContaining({ name: 'New Template' })));
    await waitFor(() => within(table()).getByText('New Template'));
  });

  it('filters by search query', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    await user.type(screen.getByLabelText('Search templates'), 'malware');
    await waitFor(() => expect(within(table()).queryByText('Phishing Playbook')).not.toBeInTheDocument());
    expect(within(table()).getByText('Malware Playbook')).toBeInTheDocument();
  });

  it('filters by status', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    await user.selectOptions(screen.getByLabelText('Status filter'), 'archived');
    await waitFor(() => expect(within(table()).queryByText('Phishing Playbook')).not.toBeInTheDocument());
    expect(within(table()).getByText('Malware Playbook')).toBeInTheDocument();
  });

  it('filters by subject', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    await user.selectOptions(screen.getByLabelText('Subject filter'), '2');
    await waitFor(() => expect(within(table()).queryByText('Phishing Playbook')).not.toBeInTheDocument());
    expect(within(table()).getByText('Malware Playbook')).toBeInTheDocument();
  });

  it('sorts by name', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    // default name asc → Malware Playbook first
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Malware Playbook')).toBeInTheDocument();
    await user.click(within(table()).getByRole('button', { name: 'Sort by Name' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Phishing Playbook')).toBeInTheDocument();
  });

  it('archives a template via DELETE through the kebab', async () => {
    mockGet();
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    const menu = await openKebab(user, 'Phishing Playbook');
    await user.click(within(menu).getByRole('menuitem', { name: 'Archive' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/task-templates/1/'));
  });

  it('bulk-archives selected templates', async () => {
    mockGet();
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    await user.click(within(table()).getByLabelText('Select Phishing Playbook'));
    await user.click(screen.getByRole('button', { name: 'Archive selected' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/task-templates/1/'));
  });

  it('opens template editor when Edit items clicked', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    const menu = await openKebab(user, 'Phishing Playbook');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit items' }));
    expect(screen.getByRole('heading', { name: 'Phishing Playbook' })).toBeInTheDocument();
    expect(screen.getByText('Step 1')).toBeInTheDocument();
    expect(screen.getByText('Step 2')).toBeInTheDocument();
  });

  it('opens meta editor modal when Edit clicked', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    const menu = await openKebab(user, 'Phishing Playbook');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit' }));
    expect(screen.getByRole('heading', { name: 'Edit Template' })).toBeInTheDocument();
  });

  it('pre-fills meta editor with existing template values', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    const menu = await openKebab(user, 'Phishing Playbook');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit' }));
    expect(screen.getByDisplayValue('Phishing Playbook')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Phishing response steps.')).toBeInTheDocument();
    const modal = screen.getByRole('heading', { name: 'Edit Template' }).closest('div[class*="fixed"]');
    expect(modal.querySelector('input[type="checkbox"]')).toBeChecked();
  });

  it('saves template metadata via PATCH and updates the row', async () => {
    mockGet();
    api.patch.mockResolvedValue({
      data: { ...TEMPLATES[0], name: 'Updated Name', description: 'New desc', is_auto_apply: false },
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    const menu = await openKebab(user, 'Phishing Playbook');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit' }));
    const nameInput = screen.getByDisplayValue('Phishing Playbook');
    await user.clear(nameInput);
    await user.type(nameInput, 'Updated Name');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/api/task-templates/1/',
      expect.objectContaining({ name: 'Updated Name', description: 'Phishing response steps.', is_auto_apply: true })
    ));
    await waitFor(() => within(table()).getByText('Updated Name'));
  });

  it('shows backend error in meta editor on PATCH failure', async () => {
    mockGet();
    api.patch.mockRejectedValue({
      response: { data: { name: ['A template with this name already exists.'] } },
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    const menu = await openKebab(user, 'Phishing Playbook');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => screen.getByText('A template with this name already exists.'));
  });

  it('closes meta editor on Cancel', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    const menu = await openKebab(user, 'Phishing Playbook');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit' }));
    expect(screen.getByRole('heading', { name: 'Edit Template' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('heading', { name: 'Edit Template' })).not.toBeInTheDocument();
  });

  it('adds an item in the template editor', async () => {
    mockGet();
    api.post.mockResolvedValue({
      data: { id: 99, title: 'New Step', description: '', display_order: 3 },
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    const menu = await openKebab(user, 'Phishing Playbook');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit items' }));
    await waitFor(() => screen.getByPlaceholderText('Title'));
    await user.type(screen.getByPlaceholderText('Title'), 'New Step');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/task-templates/1/items/',
      expect.objectContaining({ title: 'New Step' })
    ));
    await waitFor(() => screen.getByText('New Step'));
  });

  it('adds a contact-task item with role and body (#721)', async () => {
    mockGet();
    api.post.mockResolvedValue({
      data: { id: 100, title: 'Notify owner', description: '', display_order: 3, is_contact_task: true },
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing Playbook'));
    const menu = await openKebab(user, 'Phishing Playbook');
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit items' }));
    await waitFor(() => screen.getByPlaceholderText('Title'));

    await user.type(screen.getByPlaceholderText('Title'), 'Notify owner');
    await user.click(screen.getByRole('button', { name: 'Contact' }));
    expect(screen.getByText('Available placeholders')).toBeInTheDocument();
    expect(screen.getByText('{{ org_name }}')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Contact message body'), 'Please contact the owner.');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/task-templates/1/items/',
      expect.objectContaining({
        title: 'Notify owner',
        is_contact_task: true,
        contact_role: 'notified',
        contact_body: 'Please contact the owner.',
      })
    ));
  });
});
