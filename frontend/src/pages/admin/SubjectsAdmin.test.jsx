import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import SubjectsAdmin from './SubjectsAdmin';

const SUBJECTS = [
  { id: 1, name: 'Phishing', slug: 'phishing', description: 'Phishing attacks.', archived: false, created_at: '2026-01-01T00:00:00Z', correction_count: 0 },
  { id: 2, name: 'Malware', slug: 'malware', description: 'Malware infections.', archived: true, created_at: '2026-01-01T00:00:00Z', correction_count: 2 },
];

const CORRECTIONS = [
  {
    id: 10, incident_display_id: 'INC-2026-0007', incident_title: 'Suspicious executable', organization_slug: 'acme',
    agent_subject_name: 'Brute Force', human_subject_name: 'Malware',
    agent_severity: '', human_severity: '', agent_disposition: '', human_disposition: '',
    actor_username: 'eddie', created_at: '2026-07-11T09:00:00Z',
  },
];

function renderPage() {
  return render(
    <MemoryRouter>
      <SubjectsAdmin />
    </MemoryRouter>
  );
}

// The component renders both a mobile card list and a desktop table in jsdom
// (no CSS media queries), so the desktop table is the deterministic surface.
function table() {
  return screen.getByRole('table');
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
    expect(screen.getAllByText('Loading…').length).toBeGreaterThan(0);
  });

  it('shows empty state', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getAllByText('No subjects.').length).toBeGreaterThan(0));
  });

  it('renders subject rows', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    expect(within(table()).getByText('Malware')).toBeInTheDocument();
    expect(within(table()).getByText('phishing')).toBeInTheDocument();
    expect(within(table()).getByText('Active')).toBeInTheDocument();
    expect(within(table()).getByText('Archived')).toBeInTheDocument();
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
    await waitFor(() => within(table()).getByText('Ransomware'));
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
    await waitFor(() => within(table()).getByText('Phishing'));
    const archiveButtons = within(table()).getAllByRole('button', { name: 'Archive' });
    await user.click(archiveButtons[0]);
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/subjects/1/', { archived: true }));
  });

  it('filters by search query', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    await user.type(screen.getByLabelText('Search subjects'), 'malw');
    await waitFor(() => expect(within(table()).queryByText('Phishing')).not.toBeInTheDocument());
    expect(within(table()).getByText('Malware')).toBeInTheDocument();
  });

  it('filters by status', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    await user.selectOptions(screen.getByLabelText('Status filter'), 'archived');
    await waitFor(() => expect(within(table()).queryByText('Phishing')).not.toBeInTheDocument());
    expect(within(table()).getByText('Malware')).toBeInTheDocument();
  });

  it('sorts by name', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    // default sort name asc → Malware before Phishing
    let rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Malware')).toBeInTheDocument();
    await user.click(within(table()).getByRole('button', { name: 'Sort by Name' }));
    rows = within(table()).getAllByRole('row').slice(1);
    expect(within(rows[0]).getByText('Phishing')).toBeInTheDocument();
  });

  it('bulk-archives selected subjects', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    api.patch.mockResolvedValue({ data: { ...SUBJECTS[0], archived: true } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    await user.click(within(table()).getByLabelText('Select Phishing'));
    await user.click(screen.getByRole('button', { name: 'Archive selected' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/subjects/1/', { archived: true }));
  });

  it('edits a subject name and description', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    api.patch.mockResolvedValue({ data: { ...SUBJECTS[0], name: 'Spear Phishing', description: 'Targeted.' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    await user.click(within(table()).getByLabelText('Edit Phishing'));
    const nameInput = within(table()).getByLabelText('Edit name');
    await user.clear(nameInput);
    await user.type(nameInput, 'Spear Phishing');
    await user.click(within(table()).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/subjects/1/', { name: 'Spear Phishing', description: 'Phishing attacks.' }));
    await waitFor(() => within(table()).getByText('Spear Phishing'));
  });

  it('shows an inline error when editing collides', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    api.patch.mockRejectedValue({ response: { data: { detail: 'A subject with this name already exists.' } } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    await user.click(within(table()).getByLabelText('Edit Phishing'));
    const nameInput = within(table()).getByLabelText('Edit name');
    await user.clear(nameInput);
    await user.type(nameInput, 'Malware');
    await user.click(within(table()).getByRole('button', { name: 'Save' }));
    await waitFor(() => within(table()).getByText('A subject with this name already exists.'));
  });

  it('deletes a subject after confirmation', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    api.delete.mockResolvedValue({ status: 204 });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    await user.click(within(table()).getByLabelText('Delete Phishing'));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/subjects/1/'));
    await waitFor(() => expect(within(table()).queryByText('Phishing')).not.toBeInTheDocument());
  });

  it('surfaces a server error when delete is blocked', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    api.delete.mockRejectedValue({ response: { data: { detail: 'This subject has task templates; remove them or archive the subject instead.' } } });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    await user.click(within(table()).getByLabelText('Delete Phishing'));
    await waitFor(() => screen.getByText('This subject has task templates; remove them or archive the subject instead.'));
  });

  it('does not delete when confirmation is cancelled', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Phishing'));
    await user.click(within(table()).getByLabelText('Delete Phishing'));
    expect(api.delete).not.toHaveBeenCalled();
  });

  // ── Classification Corrections (ADR-0030) ──────────────────────────────────
  function mockWithCorrections() {
    api.get.mockImplementation((url) => {
      if (url.includes('/corrections/')) return Promise.resolve({ data: CORRECTIONS });
      return Promise.resolve({ data: SUBJECTS });
    });
  }

  it('shows a correction count badge and no toggle for subjects with none', async () => {
    api.get.mockResolvedValue({ data: SUBJECTS });
    renderPage();
    await waitFor(() => within(table()).getByText('Malware'));
    // Malware has 2 corrections → a toggle button; Phishing has 0 → none.
    expect(within(table()).getByLabelText('Show corrections for Malware')).toBeInTheDocument();
    expect(within(table()).queryByLabelText('Show corrections for Phishing')).not.toBeInTheDocument();
  });

  it('lazily fetches and renders corrections on expand', async () => {
    mockWithCorrections();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Malware'));

    expect(api.get).not.toHaveBeenCalledWith('/api/subjects/2/corrections/');
    await user.click(within(table()).getByLabelText('Show corrections for Malware'));

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/subjects/2/corrections/'));
    expect(await within(table()).findByText('INC-2026-0007')).toBeInTheDocument();
    // The subject delta (agent → human) is rendered.
    expect(within(table()).getByText('Brute Force')).toBeInTheDocument();
    expect(within(table()).getAllByText('Malware').length).toBeGreaterThan(1);
    expect(within(table()).getByText(/by eddie/)).toBeInTheDocument();
  });

  it('surfaces a corrections-fetch error inline', async () => {
    api.get.mockImplementation((url) => {
      if (url.includes('/corrections/')) return Promise.reject(new Error('boom'));
      return Promise.resolve({ data: SUBJECTS });
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Malware'));
    await user.click(within(table()).getByLabelText('Show corrections for Malware'));
    expect(await within(table()).findByText('Failed to load corrections.')).toBeInTheDocument();
  });

  it('collapses the panel and does not refetch on re-expand', async () => {
    mockWithCorrections();
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Malware'));

    await user.click(within(table()).getByLabelText('Show corrections for Malware'));
    await within(table()).findByText('INC-2026-0007');
    const fetchCalls = api.get.mock.calls.filter(([u]) => u.includes('/corrections/')).length;

    await user.click(within(table()).getByLabelText('Hide corrections for Malware'));
    await waitFor(() => expect(within(table()).queryByText('INC-2026-0007')).not.toBeInTheDocument());

    await user.click(within(table()).getByLabelText('Show corrections for Malware'));
    await within(table()).findByText('INC-2026-0007');
    // Re-expanding reuses the cached result — no second fetch.
    expect(api.get.mock.calls.filter(([u]) => u.includes('/corrections/')).length).toBe(fetchCalls);
  });
});
