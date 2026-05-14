import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import SignupRequests from './SignupRequests';

const PENDING_REQ = {
  id: 1,
  email: 'alice@example.com',
  full_name: 'Alice Smith',
  org_name: 'Acme Corp',
  intended_use: 'Security monitoring',
  status: 'pending',
  submitted_at: '2026-05-01T10:00:00Z',
  approved_org_name: '',
  invite_expires_at: null,
  rejection_reason: '',
  rejection_note: '',
};

const APPROVED_REQ = {
  ...PENDING_REQ,
  id: 2,
  email: 'bob@example.com',
  status: 'approved',
  approved_org_name: 'Acme Corp',
  org_slug: 'acme-corp',
  invite_expires_at: '2026-05-08T10:00:00Z',
};

const EXPIRED_REQ = {
  ...APPROVED_REQ,
  id: 3,
  email: 'carol@example.com',
  status: 'expired',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <SignupRequests />
    </MemoryRouter>
  );
}

describe('SignupRequests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: [PENDING_REQ] });
    api.post.mockResolvedValue({ data: { ...PENDING_REQ, status: 'approved' } });
    api.delete.mockResolvedValue({});
  });

  it('renders page heading', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Signup Requests')).toBeInTheDocument());
  });

  it('shows email and org name for each request', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('alice@example.com')).toBeInTheDocument();
      expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    });
  });

  it('fetches requests filtered by the active status tab', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/signups/?status=pending'));

    await user.click(screen.getByRole('button', { name: 'Approved' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/signups/?status=approved'));
  });

  it('fetches all requests when All tab is selected', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('button', { name: 'All' }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/signups/'));
  });

  it('shows empty state when no requests match filter', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText('No requests found.')).toBeInTheDocument());
  });

  describe('approve panel', () => {
    it('shows approve panel when pending row is expanded', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('alice@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('alice@example.com'));
      expect(screen.getByText('Approve & provision')).toBeInTheDocument();
    });

    it('calls approve endpoint with org name override', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('alice@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('alice@example.com'));
      const orgInput = screen.getByPlaceholderText('Acme Corp');
      await user.clear(orgInput);
      await user.type(orgInput, 'Acme Renamed');
      await user.click(screen.getByRole('button', { name: /approve & provision/i }));

      await waitFor(() =>
        expect(api.post).toHaveBeenCalledWith('/api/signups/1/approve/', {
          approved_org_name: 'Acme Renamed',
        })
      );
    });

    it('shows conflict warning when API returns conflict error', async () => {
      api.post.mockRejectedValue({
        response: { data: { conflict: true, detail: 'Name conflict — provide a different name.' } },
      });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('alice@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('alice@example.com'));
      await user.click(screen.getByRole('button', { name: /approve & provision/i }));

      await waitFor(() =>
        expect(screen.getByText('Name conflict — provide a different name.')).toBeInTheDocument()
      );
    });
  });

  describe('reject panel', () => {
    it('shows reject panel with reason dropdown for pending rows', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('alice@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('alice@example.com'));
      expect(screen.getByRole('combobox')).toBeInTheDocument();
      expect(screen.getByLabelText(/send rejection email/i)).toBeChecked();
    });

    it('reject dropdown contains backend preset reason strings', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('alice@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('alice@example.com'));
      const select = screen.getByRole('combobox');
      expect(select).toHaveValue('Unable to verify organisation');
      expect(screen.getByRole('option', { name: 'Duplicate request' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'Outside our service area' })).toBeInTheDocument();
    });

    it('calls reject endpoint with correct payload', async () => {
      api.post.mockResolvedValue({ data: { ...PENDING_REQ, status: 'rejected' } });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('alice@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('alice@example.com'));
      await user.click(screen.getByRole('button', { name: /^reject$/i }));

      await waitFor(() =>
        expect(api.post).toHaveBeenCalledWith('/api/signups/1/reject/', {
          rejection_reason: 'Unable to verify organisation',
          rejection_note: '',
          send_rejection_email: true,
        })
      );
    });
  });

  describe('resend panel', () => {
    it('shows resend button for approved rows', async () => {
      api.get.mockResolvedValue({ data: [APPROVED_REQ] });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('bob@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('bob@example.com'));
      expect(screen.getByRole('button', { name: /resend invite/i })).toBeInTheDocument();
    });

    it('shows resend button for expired rows', async () => {
      api.get.mockResolvedValue({ data: [EXPIRED_REQ] });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('carol@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('carol@example.com'));
      expect(screen.getByRole('button', { name: /resend invite/i })).toBeInTheDocument();
    });

    it('calls resend endpoint on click', async () => {
      api.get.mockResolvedValue({ data: [EXPIRED_REQ] });
      api.post.mockResolvedValue({ data: { ...EXPIRED_REQ, status: 'approved' } });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('carol@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('carol@example.com'));
      await user.click(screen.getByRole('button', { name: /resend invite/i }));

      await waitFor(() =>
        expect(api.post).toHaveBeenCalledWith('/api/signups/3/resend/', {})
      );
    });
  });

  describe('delete action', () => {
    it('calls delete endpoint after confirmation', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(true);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('alice@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('alice@example.com'));
      await user.click(screen.getByRole('button', { name: /delete request/i }));

      await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/signups/1/'));
    });

    it('does not call delete when confirmation is cancelled', async () => {
      vi.spyOn(window, 'confirm').mockReturnValue(false);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('alice@example.com')).toBeInTheDocument());

      await user.click(screen.getByText('alice@example.com'));
      await user.click(screen.getByRole('button', { name: /delete request/i }));

      expect(api.delete).not.toHaveBeenCalled();
    });
  });
});
