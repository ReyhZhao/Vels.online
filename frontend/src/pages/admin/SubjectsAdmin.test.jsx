import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

import api from '@/lib/axios';
import SubjectsAdmin from './SubjectsAdmin';

const SUBJECTS = [
  { id: 1, name: 'Phishing', slug: 'phishing', description: 'Phishing attacks.', archived: false, created_at: '2026-01-01T00:00:00Z' },
  { id: 2, name: 'Malware', slug: 'malware', description: 'Malware infections.', archived: true, created_at: '2026-01-01T00:00:00Z' },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <SubjectsAdmin />
    </MemoryRouter>
  );
}

describe('SubjectsAdmin', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders page heading', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => screen.getByText('Incident Subjects'));
  });

  it('shows loading state', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('shows empty state', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => screen.getByText('No subjects.'));
  });

  it('renders subject rows', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    renderPage();
    await waitFor(() => screen.getByText('Phishing'));
    expect(screen.getByText('Malware')).toBeInTheDocument();
    expect(screen.getByText('phishing')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Archived')).toBeInTheDocument();
  });

  it('creates a new subject', async () => {
    api.get.mockResolvedValue({ data: [] });
    api.post.mockResolvedValue({ data: { id: 3, name: 'Ransomware', slug: 'ransomware', description: '', archived: false, created_at: '2026-05-01T00:00:00Z' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByPlaceholderText('Subject name'));
    await user.type(screen.getByPlaceholderText('Subject name'), 'Ransomware');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/subjects/', { name: 'Ransomware', description: '' }));
    await waitFor(() => screen.getByText('Ransomware'));
  });

  it('shows form error on create failure', async () => {
    api.get.mockResolvedValue({ data: [] });
    api.post.mockRejectedValue({ response: { data: { detail: 'A subject with this name already exists.' } } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByPlaceholderText('Subject name'));
    await user.type(screen.getByPlaceholderText('Subject name'), 'Phishing');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => screen.getByText('A subject with this name already exists.'));
  });

  it('archives a subject', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    api.patch.mockResolvedValue({ data: { ...SUBJECTS[0], archived: true } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Phishing'));
    const archiveButtons = screen.getAllByRole('button', { name: 'Archive' });
    await user.click(archiveButtons[0]);
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/subjects/1/', { archived: true }));
  });
});
