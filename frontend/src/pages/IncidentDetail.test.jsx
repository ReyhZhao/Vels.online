import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));

import api from '../lib/axios';
import IncidentDetail from './IncidentDetail';

const INCIDENT = {
  id: 1,
  display_id: 'INC-2026-0001',
  title: 'Suspicious login attempt',
  description: 'Multiple failed logins from unusual IP.',
  severity: 'high',
  tlp: 'amber',
  pap: 'amber',
  state: 'new',
  closure_reason: null,
  subject: null,
  subject_slug: null,
  subject_name: null,
  org_slug: 'acme',
  source_kind: 'manual',
  source_ref: {},
  assignee: null,
  assignee_username: null,
  created_by: 1,
  created_by_username: 'alice',
  created_at: '2026-01-15T10:00:00Z',
  updated_at: '2026-01-15T10:00:00Z',
};

const SUBJECTS = [
  { id: 1, name: 'Phishing', slug: 'phishing', description: '', archived: false },
  { id: 2, name: 'Malware', slug: 'malware', description: '', archived: false },
];

function mockGet(incident = INCIDENT, subjects = SUBJECTS) {
  api.get.mockImplementation(url => {
    if (url === '/api/subjects/') return Promise.resolve({ data: subjects });
    return Promise.resolve({ data: incident });
  });
}

function renderPage(id = '1') {
  return render(
    <MemoryRouter initialEntries={[`/incidents/${id}`]}>
      <Routes>
        <Route path="/incidents/:incidentId" element={<IncidentDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('IncidentDetail', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('shows loading state while fetching', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('renders incident header', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('INC-2026-0001'));
    expect(screen.getByText('Suspicious login attempt')).toBeInTheDocument();
  });

  it('renders severity and TLP badges', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('high'));
    expect(screen.getByText('TLP:AMBER')).toBeInTheDocument();
    expect(screen.getByText('PAP:AMBER')).toBeInTheDocument();
  });

  it('renders description', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('Multiple failed logins from unusual IP.'));
  });

  it('shows not found message on 404', async () => {
    api.get.mockRejectedValue({ response: { status: 404 } });
    renderPage();
    await waitFor(() => screen.getByText('Incident not found.'));
  });

  it('shows back link to incidents list', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('← Incidents'));
  });

  it('fetches the correct incident by id', async () => {
    mockGet();
    renderPage('42');
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/incidents/42/'));
  });

  // ── state transition controls ─────────────────────────────────────────────

  it('shows legal next-state actions for new incident', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByText('Triage'));
    expect(screen.getByText('Start work')).toBeInTheDocument();
  });

  it('shows reopen action for closed incident', async () => {
    mockGet({ ...INCIDENT, state: 'closed', closure_reason: 'resolved' });
    renderPage();
    await waitFor(() => screen.getByText('Reopen'));
  });

  it('calls transition API when action button clicked', async () => {
    mockGet();
    api.post.mockResolvedValue({ data: { ...INCIDENT, state: 'triaged' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Triage'));
    await user.click(screen.getByRole('button', { name: 'Triage' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/1/transition/',
      { state: 'triaged' }
    ));
  });

  it('shows closure reason dialog when Close is clicked', async () => {
    mockGet({ ...INCIDENT, state: 'in_progress' });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Close'));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.getByRole('heading', { name: 'Close incident' })).toBeInTheDocument();
    expect(screen.getByLabelText('Closure reason')).toBeInTheDocument();
  });

  it('submits closure reason when closing', async () => {
    mockGet({ ...INCIDENT, state: 'in_progress' });
    api.post.mockResolvedValue({ data: { ...INCIDENT, state: 'closed', closure_reason: 'resolved' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Close'));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    await user.selectOptions(screen.getByLabelText('Closure reason'), 'resolved');
    await user.click(screen.getByRole('button', { name: 'Close incident' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/1/transition/',
      { state: 'closed', closure_reason: 'resolved' }
    ));
  });

  it('cancels closure dialog without calling API', async () => {
    mockGet({ ...INCIDENT, state: 'in_progress' });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Close'));
    await user.click(screen.getByRole('button', { name: 'Close' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(api.post).not.toHaveBeenCalled();
    expect(screen.queryByText('Close incident')).not.toBeInTheDocument();
  });

  it('shows transition error on failure', async () => {
    mockGet();
    api.post.mockRejectedValue({ response: { data: { detail: 'Invalid transition.' } } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Triage'));
    await user.click(screen.getByRole('button', { name: 'Triage' }));
    await waitFor(() => screen.getByText('Invalid transition.'));
  });

  // ── subject dropdown ──────────────────────────────────────────────────────

  it('renders subject dropdown', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByLabelText('Subject'));
    expect(screen.getByLabelText('Subject')).not.toBeDisabled();
  });

  it('subject dropdown is disabled when state is past triage', async () => {
    mockGet({ ...INCIDENT, state: 'in_progress' });
    renderPage();
    await waitFor(() => screen.getByLabelText('Subject'));
    expect(screen.getByLabelText('Subject')).toBeDisabled();
  });

  it('subject dropdown lists active subjects', async () => {
    mockGet();
    renderPage();
    await waitFor(() => screen.getByLabelText('Subject'));
    expect(screen.getByRole('option', { name: 'Phishing' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Malware' })).toBeInTheDocument();
  });

  it('calls patch when subject is selected', async () => {
    mockGet();
    api.patch.mockResolvedValue({ data: { ...INCIDENT, subject: 1, subject_slug: 'phishing', subject_name: 'Phishing' } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText('Subject'));
    await user.selectOptions(screen.getByLabelText('Subject'), '1');
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith('/api/incidents/1/', { subject: 1 }));
  });
});
