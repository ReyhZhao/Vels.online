import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { post: vi.fn() },
}));

vi.mock('../context/OrgContext', () => ({
  useOrganization: vi.fn(),
}));

import api from '../lib/axios';
import { useOrganization } from '../context/OrgContext';
import CreateIncidentModal from './CreateIncidentModal';

const WITH_ORG   = { selectedOrg: { slug: 'acme', name: 'Acme' } };
const NO_ORG     = { selectedOrg: null };

function renderModal(props = {}, orgContext = WITH_ORG) {
  useOrganization.mockReturnValue(orgContext);
  return render(
    <MemoryRouter>
      <CreateIncidentModal open={true} onClose={vi.fn()} {...props} />
    </MemoryRouter>
  );
}

describe('CreateIncidentModal', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('renders nothing when open=false', () => {
    useOrganization.mockReturnValue(WITH_ORG);
    const { container } = render(
      <MemoryRouter>
        <CreateIncidentModal open={false} onClose={vi.fn()} />
      </MemoryRouter>
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the modal heading when open', () => {
    renderModal();
    expect(screen.getByRole('heading', { name: 'New Incident' })).toBeInTheDocument();
  });

  it('renders title, description, severity, TLP, and PAP fields', () => {
    renderModal();
    expect(screen.getByRole('textbox', { name: /title/i })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /description/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /severity/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /tlp/i })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: /pap/i })).toBeInTheDocument();
  });

  it('defaults severity to medium, TLP to amber, PAP to amber', () => {
    renderModal();
    expect(screen.getByRole('combobox', { name: /severity/i })).toHaveValue('medium');
    expect(screen.getByRole('combobox', { name: /tlp/i })).toHaveValue('amber');
    expect(screen.getByRole('combobox', { name: /pap/i })).toHaveValue('amber');
  });

  it('submit button is disabled when title is empty', () => {
    renderModal();
    expect(screen.getByRole('button', { name: /create incident/i })).toBeDisabled();
  });

  it('submit button is disabled when no org is selected', () => {
    renderModal({}, NO_ORG);
    fireEvent.change(screen.getByRole('textbox', { name: /title/i }), { target: { value: 'Test' } });
    expect(screen.getByRole('button', { name: /create incident/i })).toBeDisabled();
  });

  it('shows no-org hint when no organisation is selected', () => {
    renderModal({}, NO_ORG);
    expect(screen.getByText(/no organisation selected/i)).toBeInTheDocument();
  });

  it('submit button is enabled when title is filled and org is selected', () => {
    renderModal();
    fireEvent.change(screen.getByRole('textbox', { name: /title/i }), { target: { value: 'Test incident' } });
    expect(screen.getByRole('button', { name: /create incident/i })).not.toBeDisabled();
  });

  it('submits correct payload to POST /api/incidents/', async () => {
    api.post.mockResolvedValue({ data: { display_id: 'INC-2026-0001' } });
    renderModal();
    fireEvent.change(screen.getByRole('textbox', { name: /title/i }), { target: { value: 'My incident' } });
    fireEvent.click(screen.getByRole('button', { name: /create incident/i }));
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/incidents/', {
        title: 'My incident',
        description: '',
        severity: 'medium',
        tlp: 'amber',
        pap: 'amber',
        source_kind: 'manual',
        org: 'acme',
      })
    );
  });

  it('calls onClose after successful submission', async () => {
    const onClose = vi.fn();
    api.post.mockResolvedValue({ data: { display_id: 'INC-2026-0001' } });
    renderModal({ onClose });
    fireEvent.change(screen.getByRole('textbox', { name: /title/i }), { target: { value: 'Test' } });
    fireEvent.click(screen.getByRole('button', { name: /create incident/i }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('shows inline error on API failure without closing modal', async () => {
    const onClose = vi.fn();
    api.post.mockRejectedValue({ response: { data: { detail: 'Permission denied.' } } });
    renderModal({ onClose });
    fireEvent.change(screen.getByRole('textbox', { name: /title/i }), { target: { value: 'Test' } });
    fireEvent.click(screen.getByRole('button', { name: /create incident/i }));
    await waitFor(() => expect(screen.getByText('Permission denied.')).toBeInTheDocument());
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose when ✕ is clicked', () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
