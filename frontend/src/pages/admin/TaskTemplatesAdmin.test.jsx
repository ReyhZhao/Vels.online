import { render, screen, waitFor } from '@testing-library/react';
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
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('shows empty state', async () => {
    mockGet([], SUBJECTS);
    renderPage();
    await waitFor(() => screen.getByText('No templates.'));
  });

  it('renders template rows with subject and status', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('Phishing Playbook'));
    expect(screen.getByText('Malware Playbook')).toBeInTheDocument();
    expect(screen.getAllByText('Auto-apply').length).toBeGreaterThan(0);
    expect(screen.getByText('Archived')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('shows item count in table', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('Phishing Playbook'));
    expect(screen.getByText('2')).toBeInTheDocument();
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
    await waitFor(() => screen.getByText('New Template'));
  });

  it('archives a template via DELETE', async () => {
    mockGet();
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Phishing Playbook'));
    const archiveBtns = screen.getAllByRole('button', { name: 'Archive' });
    await user.click(archiveBtns[0]);
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/task-templates/1/'));
  });

  it('opens template editor when Edit items clicked', async () => {
    mockGet();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Phishing Playbook'));
    const editBtns = screen.getAllByRole('button', { name: 'Edit items' });
    await user.click(editBtns[0]);
    expect(screen.getByRole('heading', { name: 'Phishing Playbook' })).toBeInTheDocument();
    expect(screen.getByText('Step 1')).toBeInTheDocument();
    expect(screen.getByText('Step 2')).toBeInTheDocument();
  });

  it('adds an item in the template editor', async () => {
    mockGet();
    api.post.mockResolvedValue({
      data: { id: 99, title: 'New Step', description: '', display_order: 3 },
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getAllByRole('button', { name: 'Edit items' }));
    await user.click(screen.getAllByRole('button', { name: 'Edit items' })[0]);
    await waitFor(() => screen.getByPlaceholderText('Title'));
    await user.type(screen.getByPlaceholderText('Title'), 'New Step');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/task-templates/1/items/',
      expect.objectContaining({ title: 'New Step' })
    ));
    await waitFor(() => screen.getByText('New Step'));
  });
});
