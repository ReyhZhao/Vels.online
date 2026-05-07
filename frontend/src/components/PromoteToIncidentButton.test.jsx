import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('../context/OrgContext', () => ({
  useOrganization: () => ({ selectedOrg: { slug: 'acme', name: 'Acme' } }),
}));

import api from '../lib/axios';
import PromoteToIncidentButton from './PromoteToIncidentButton';

const FORM_PAYLOAD = {
  title: 'CVE-2025-12345: Remote code execution flaw.',
  description: 'Remote code execution flaw.',
  severity: 'critical',
  source_kind: 'vulnerability',
  source_ref: { cve_id: 'CVE-2025-12345' },
};

const OPEN_INCIDENT = {
  id: 1,
  display_id: 'INC-2026-0001',
  title: 'CVE-2025-12345: RCE',
  state: 'in_progress',
  severity: 'critical',
  source_kind: 'vulnerability',
};

function mockPromoteForm(openIncidents = []) {
  api.post.mockResolvedValueOnce({
    data: { form_payload: FORM_PAYLOAD, open_incidents: openIncidents },
  });
}

function renderBtn(props = {}) {
  return render(
    <MemoryRouter>
      <PromoteToIncidentButton
        sourceKind="vulnerability"
        sourceRef={{ cve_id: 'CVE-2025-12345' }}
        orgSlug="acme"
        {...props}
      />
    </MemoryRouter>
  );
}

describe('PromoteToIncidentButton', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders the promote button', () => {
    renderBtn();
    expect(screen.getByRole('button', { name: 'Promote to incident' })).toBeInTheDocument();
  });

  it('opens modal with pre-filled form on click', async () => {
    mockPromoteForm();
    const user = userEvent.setup();
    renderBtn();
    await user.click(screen.getByRole('button', { name: 'Promote to incident' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Create Incident' }));
    expect(screen.getByDisplayValue(FORM_PAYLOAD.title)).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledWith('/api/incidents/promote/', expect.objectContaining({
      source_kind: 'vulnerability',
    }));
  });

  it('shows dup-warning panel when open incidents exist', async () => {
    mockPromoteForm([OPEN_INCIDENT]);
    const user = userEvent.setup();
    renderBtn();
    await user.click(screen.getByRole('button', { name: 'Promote to incident' }));
    await waitFor(() => screen.getByText(/Existing open incident/));
    expect(screen.getByText(/INC-2026-0001/)).toBeInTheDocument();
  });

  it('does not show dup-warning when no open incidents', async () => {
    mockPromoteForm([]);
    const user = userEvent.setup();
    renderBtn();
    await user.click(screen.getByRole('button', { name: 'Promote to incident' }));
    await waitFor(() => screen.getByRole('heading', { name: 'Create Incident' }));
    expect(screen.queryByText(/Existing open incident/)).not.toBeInTheDocument();
  });

  it('calls commit endpoint on submit and closes modal', async () => {
    mockPromoteForm();
    api.post.mockResolvedValueOnce({ data: { id: 42, display_id: 'INC-2026-0042', title: 'New' } });
    const user = userEvent.setup();
    renderBtn();
    await user.click(screen.getByRole('button', { name: 'Promote to incident' }));
    await waitFor(() => screen.getByRole('button', { name: 'Create incident' }));
    await user.click(screen.getByRole('button', { name: 'Create incident' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/promote/',
      expect.objectContaining({ commit: true, org: 'acme' })
    ));
  });

  it('shows commit error on failure', async () => {
    mockPromoteForm();
    api.post.mockRejectedValueOnce({ response: { data: { detail: 'Server error.' } } });
    const user = userEvent.setup();
    renderBtn();
    await user.click(screen.getByRole('button', { name: 'Promote to incident' }));
    await waitFor(() => screen.getByRole('button', { name: 'Create incident' }));
    await user.click(screen.getByRole('button', { name: 'Create incident' }));
    await waitFor(() => screen.getByText('Server error.'));
  });

  it('closes modal on cancel', async () => {
    mockPromoteForm();
    const user = userEvent.setup();
    renderBtn();
    await user.click(screen.getByRole('button', { name: 'Promote to incident' }));
    await waitFor(() => screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('heading', { name: 'Create Incident' })).not.toBeInTheDocument();
  });
});
