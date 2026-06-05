import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import OrgManagement from './OrgManagement';

const ACME = { id: 1, name: 'Acme', slug: 'acme', wazuh_group: 'acme' };
const CONTOSO = { id: 2, name: 'Contoso', slug: 'contoso', wazuh_group: 'contoso' };

const PENDING_INV = {
  id: 10,
  email: 'alice@example.com',
  full_name: 'Alice Smith',
  role: 'staff',
  status: 'pending',
};

function renderPage() {
  return render(
    <MemoryRouter>
      <OrgManagement />
    </MemoryRouter>
  );
}

describe('OrgManagement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: [ACME, CONTOSO] });
    api.post.mockResolvedValue({ data: {} });
  });

  it('renders page heading', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Organisations')).toBeInTheDocument());
  });

  it('shows loading state initially', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('renders org rows after load', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Acme')).toBeInTheDocument();
      expect(screen.getByText('Contoso')).toBeInTheDocument();
    });
  });

  it('shows empty state when no orgs exist', async () => {
    api.get.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText('No organisations yet.')).toBeInTheDocument());
  });

  it('shows error when org load fails', async () => {
    api.get.mockRejectedValue(new Error('Network error'));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('Failed to load organisations.')).toBeInTheDocument()
    );
  });

  describe('create org form', () => {
    it('calls POST with org name on submit', async () => {
      const NEW_ORG = { id: 3, name: 'NewCo', slug: 'newco', wazuh_group: 'newco' };
      api.post.mockResolvedValue({ data: NEW_ORG });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.type(screen.getByPlaceholderText('Organisation name'), 'NewCo');
      await user.click(screen.getByRole('button', { name: /^create$/i }));

      await waitFor(() =>
        expect(api.post).toHaveBeenCalledWith('/api/security/organizations/', { name: 'NewCo' })
      );
    });

    it('adds newly created org to the list', async () => {
      const NEW_ORG = { id: 3, name: 'NewCo', slug: 'newco', wazuh_group: 'newco' };
      api.post.mockResolvedValue({ data: NEW_ORG });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.type(screen.getByPlaceholderText('Organisation name'), 'NewCo');
      await user.click(screen.getByRole('button', { name: /^create$/i }));

      await waitFor(() => expect(screen.getByText('NewCo')).toBeInTheDocument());
    });

    it('clears the name input after successful creation', async () => {
      const NEW_ORG = { id: 3, name: 'NewCo', slug: 'newco', wazuh_group: 'newco' };
      api.post.mockResolvedValue({ data: NEW_ORG });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      const input = screen.getByPlaceholderText('Organisation name');
      await user.type(input, 'NewCo');
      await user.click(screen.getByRole('button', { name: /^create$/i }));

      await waitFor(() => expect(input).toHaveValue(''));
    });

    it('shows error message on create failure', async () => {
      api.post.mockRejectedValue({
        response: { data: { detail: 'An organisation with that name already exists.' } },
      });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.type(screen.getByPlaceholderText('Organisation name'), 'Acme');
      await user.click(screen.getByRole('button', { name: /^create$/i }));

      await waitFor(() =>
        expect(
          screen.getByText('An organisation with that name already exists.')
        ).toBeInTheDocument()
      );
    });

    it('disables Create button when name is empty', async () => {
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());
      expect(screen.getByRole('button', { name: /^create$/i })).toBeDisabled();
    });
  });

  describe('OrgRow invite dialog', () => {
    it('opens invite dialog when Invite button is clicked', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getAllByRole('button', { name: /invite user to acme/i })[0]);
      expect(screen.getByText('Invite user to Acme')).toBeInTheDocument();
    });

    it('closes dialog when Cancel is clicked', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getAllByRole('button', { name: /invite user to acme/i })[0]);
      await user.click(screen.getByRole('button', { name: /cancel/i }));

      expect(screen.queryByText('Invite user to Acme')).not.toBeInTheDocument();
    });

    it('submits invite with email, full name and role', async () => {
      api.post.mockResolvedValue({ data: PENDING_INV });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getAllByRole('button', { name: /invite user to acme/i })[0]);

      await user.type(screen.getByLabelText('Email'), 'alice@example.com');
      await user.type(screen.getByLabelText('Full name'), 'Alice Smith');
      await user.selectOptions(screen.getByLabelText('Role'), 'staff');
      await user.click(screen.getByRole('button', { name: /send invitation/i }));

      await waitFor(() =>
        expect(api.post).toHaveBeenCalledWith(
          '/api/security/organizations/acme/invite/',
          { email: 'alice@example.com', full_name: 'Alice Smith', role: 'staff' }
        )
      );
    });

    it('closes dialog after successful invite', async () => {
      api.post.mockResolvedValue({ data: PENDING_INV });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getAllByRole('button', { name: /invite user to acme/i })[0]);
      await user.type(screen.getByLabelText('Email'), 'alice@example.com');
      await user.type(screen.getByLabelText('Full name'), 'Alice Smith');
      await user.click(screen.getByRole('button', { name: /send invitation/i }));

      await waitFor(() =>
        expect(screen.queryByText('Invite user to Acme')).not.toBeInTheDocument()
      );
    });

    it('shows error in dialog when invite API fails', async () => {
      api.post.mockRejectedValue({
        response: { data: { detail: 'User already has a pending invitation.' } },
      });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getAllByRole('button', { name: /invite user to acme/i })[0]);
      await user.type(screen.getByLabelText('Email'), 'alice@example.com');
      await user.type(screen.getByLabelText('Full name'), 'Alice Smith');
      await user.click(screen.getByRole('button', { name: /send invitation/i }));

      await waitFor(() =>
        expect(screen.getByText('User already has a pending invitation.')).toBeInTheDocument()
      );
    });

    it('disables Send button when email or name is empty', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getAllByRole('button', { name: /invite user to acme/i })[0]);
      expect(screen.getByRole('button', { name: /send invitation/i })).toBeDisabled();
    });
  });

  describe('OrgRow expand invitations', () => {
    it('loads invitations when row is expanded', async () => {
      api.get
        .mockResolvedValueOnce({ data: [ACME] })
        .mockResolvedValueOnce({ data: [PENDING_INV] })
        .mockResolvedValueOnce({ data: [] });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));

      await waitFor(() =>
        expect(api.get).toHaveBeenCalledWith('/api/security/organizations/acme/invite/')
      );
    });

    it('shows invitation details in sub-table', async () => {
      api.get
        .mockResolvedValueOnce({ data: [ACME] })
        .mockResolvedValueOnce({ data: [PENDING_INV] })
        .mockResolvedValueOnce({ data: [] });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));

      await waitFor(() => {
        expect(screen.getByText('alice@example.com')).toBeInTheDocument();
        expect(screen.getByText('Alice Smith')).toBeInTheDocument();
        expect(screen.getByText('Staff')).toBeInTheDocument();
        expect(screen.getByText('pending')).toBeInTheDocument();
      });
    });

    it('shows empty state when org has no invitations', async () => {
      api.get
        .mockResolvedValueOnce({ data: [ACME] })
        .mockResolvedValueOnce({ data: [] })
        .mockResolvedValueOnce({ data: [] });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));

      await waitFor(() =>
        expect(screen.getByText('No invitations yet.')).toBeInTheDocument()
      );
    });

    it('collapses row when chevron is clicked again', async () => {
      api.get
        .mockResolvedValueOnce({ data: [ACME] })
        .mockResolvedValueOnce({ data: [PENDING_INV] })
        .mockResolvedValueOnce({ data: [] });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));
      await waitFor(() => expect(screen.getByText('alice@example.com')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Collapse Acme invitations'));
      expect(screen.queryByText('alice@example.com')).not.toBeInTheDocument();
    });

    it('new invite appears in expanded list after creation', async () => {
      const NEW_INV = { id: 11, email: 'bob@example.com', full_name: 'Bob', role: 'member', status: 'pending' };
      api.get
        .mockResolvedValueOnce({ data: [ACME] })
        .mockResolvedValueOnce({ data: [] })
        .mockResolvedValueOnce({ data: [] });
      api.post.mockResolvedValue({ data: NEW_INV });

      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));
      await waitFor(() => expect(screen.getByText('No invitations yet.')).toBeInTheDocument());

      await user.click(screen.getAllByRole('button', { name: /invite user to acme/i })[0]);
      await user.type(screen.getByLabelText('Email'), 'bob@example.com');
      await user.type(screen.getByLabelText('Full name'), 'Bob');
      await user.click(screen.getByRole('button', { name: /send invitation/i }));

      await waitFor(() => expect(screen.getByText('bob@example.com')).toBeInTheDocument());
    });
  });

  describe('OrgRow system rules mute', () => {
    const SYSTEM_RULE_ACTIVE = { id: 1, name: 'Port Scan', severity: 'high', muted: false, organization: null, legs: [] };
    const SYSTEM_RULE_MUTED = { id: 2, name: 'Brute Force', severity: 'critical', muted: true, organization: null, legs: [] };

    function setupWithSystemRules(rules) {
      api.get
        .mockResolvedValueOnce({ data: [ACME] })
        .mockResolvedValueOnce({ data: [] })
        .mockResolvedValueOnce({ data: rules });
    }

    it('loads system rules when row is expanded', async () => {
      setupWithSystemRules([SYSTEM_RULE_ACTIVE]);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));

      await waitFor(() =>
        expect(api.get).toHaveBeenCalledWith('/api/correlations/org-system-rules/?org=acme')
      );
    });

    it('shows system rules in section', async () => {
      setupWithSystemRules([SYSTEM_RULE_ACTIVE, SYSTEM_RULE_MUTED]);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));

      await waitFor(() => {
        expect(screen.getByText('Port Scan')).toBeInTheDocument();
        expect(screen.getByText('Brute Force')).toBeInTheDocument();
      });
    });

    it('shows Mute button for unmuted rules', async () => {
      setupWithSystemRules([SYSTEM_RULE_ACTIVE]);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^mute port scan for acme$/i })).toBeInTheDocument()
      );
    });

    it('shows Unmute button for muted rules', async () => {
      setupWithSystemRules([SYSTEM_RULE_MUTED]);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^unmute brute force for acme$/i })).toBeInTheDocument()
      );
    });

    it('calls POST to mute an unmuted system rule', async () => {
      setupWithSystemRules([SYSTEM_RULE_ACTIVE]);
      api.post.mockResolvedValue({ data: { rule_id: 1, muted: true } });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^mute port scan for acme$/i })).toBeInTheDocument()
      );

      await user.click(screen.getByRole('button', { name: /^mute port scan for acme$/i }));

      await waitFor(() =>
        expect(api.post).toHaveBeenCalledWith(
          '/api/correlations/org-system-rules/1/mute/',
          { org: 'acme' }
        )
      );
    });

    it('calls DELETE to unmute a muted system rule', async () => {
      setupWithSystemRules([SYSTEM_RULE_MUTED]);
      api.delete.mockResolvedValue({ data: { rule_id: 2, muted: false } });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^unmute brute force for acme$/i })).toBeInTheDocument()
      );

      await user.click(screen.getByRole('button', { name: /^unmute brute force for acme$/i }));

      await waitFor(() =>
        expect(api.delete).toHaveBeenCalledWith(
          '/api/correlations/org-system-rules/2/mute/?org=acme'
        )
      );
    });

    it('toggles button label from Mute to Unmute after muting', async () => {
      setupWithSystemRules([SYSTEM_RULE_ACTIVE]);
      api.post.mockResolvedValue({ data: { rule_id: 1, muted: true } });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^mute port scan for acme$/i })).toBeInTheDocument()
      );

      await user.click(screen.getByRole('button', { name: /^mute port scan for acme$/i }));

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^unmute port scan for acme$/i })).toBeInTheDocument()
      );
    });

    it('shows empty state when no system rules exist', async () => {
      setupWithSystemRules([]);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Acme')).toBeInTheDocument());

      await user.click(screen.getByLabelText('Expand Acme invitations'));

      await waitFor(() =>
        expect(screen.getByText('No system rules defined.')).toBeInTheDocument()
      );
    });
  });
});
