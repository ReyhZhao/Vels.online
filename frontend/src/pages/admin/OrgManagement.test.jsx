import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

import api from '@/lib/axios';
import OrgManagement from './OrgManagement';

const ACME = { id: 1, name: 'Acme', slug: 'acme', wazuh_group: 'acme' };
const CONTOSO = { id: 2, name: 'Contoso', slug: 'contoso', wazuh_group: 'contoso' };
const INFRA = {
  id: 9,
  name: 'Shared Infrastructure',
  slug: 'infrastructure',
  wazuh_group: '',
  is_infrastructure: true,
  triage_fp_threshold: 0.9,
  triage_work_threshold: 0.9,
  triage_prompt_context: '',
};

const PENDING_INV = {
  id: 10,
  email: 'alice@example.com',
  full_name: 'Alice Smith',
  role: 'staff',
  status: 'pending',
};

// URL-routed mock: robust to the master–detail page auto-selecting the first org
// (which eagerly loads that org's invitations) and to per-tab rule fetches.
function mockApi({ orgs = [ACME, CONTOSO], invites = [], systemRules = [], searchRules = [] } = {}) {
  api.get.mockImplementation((url) => {
    if (url.includes('/invite/')) return Promise.resolve({ data: invites });
    if (url.includes('org-system-search-rules')) return Promise.resolve({ data: searchRules });
    if (url.includes('org-system-rules')) return Promise.resolve({ data: systemRules });
    return Promise.resolve({ data: orgs });
  });
}

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
    mockApi();
    api.post.mockResolvedValue({ data: {} });
    api.patch.mockResolvedValue({ data: {} });
    api.delete.mockResolvedValue({ data: {} });
  });

  it('renders page heading', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Organisations' })).toBeInTheDocument()
    );
  });

  it('shows loading state initially', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading…')).toBeInTheDocument();
  });

  it('lists organisations in the rail after load', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Acme' }); // first org auto-selected
    expect(screen.getByText('Contoso')).toBeInTheDocument(); // rail entry
  });

  it('auto-selects the first org in the detail pane', async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Acme' })).toBeInTheDocument()
    );
  });

  it('selecting an org in the rail shows it in the detail pane', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText('Contoso')).toBeInTheDocument());

    await user.click(screen.getByText('Contoso'));

    expect(screen.getByRole('heading', { name: 'Contoso' })).toBeInTheDocument();
  });

  it('filters the rail via the search box', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { name: 'Acme' });

    // Select Contoso so Acme is no longer shown in the detail header either,
    // then filter it out of the rail — no "Acme" should remain anywhere.
    await user.click(screen.getByText('Contoso'));
    await user.type(screen.getByLabelText('Search organisations'), 'contoso');

    expect(screen.queryByText('Acme')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Contoso' })).toBeInTheDocument();
  });

  it('shows empty state when no orgs exist', async () => {
    mockApi({ orgs: [] });
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

  describe('create org', () => {
    it('calls POST with org name on submit', async () => {
      const NEW_ORG = { id: 3, name: 'NewCo', slug: 'newco', wazuh_group: 'newco' };
      api.post.mockResolvedValue({ data: NEW_ORG });
      const user = userEvent.setup();
      renderPage();
      await screen.findByRole('heading', { name: 'Acme' });

      await user.type(screen.getByPlaceholderText('Organisation name'), 'NewCo');
      await user.click(screen.getByRole('button', { name: /^create$/i }));

      await waitFor(() =>
        expect(api.post).toHaveBeenCalledWith('/api/security/organizations/', { name: 'NewCo' })
      );
    });

    it('adds newly created org to the rail and selects it', async () => {
      const NEW_ORG = { id: 3, name: 'NewCo', slug: 'newco', wazuh_group: 'newco' };
      api.post.mockResolvedValue({ data: NEW_ORG });
      const user = userEvent.setup();
      renderPage();
      await screen.findByRole('heading', { name: 'Acme' });

      await user.type(screen.getByPlaceholderText('Organisation name'), 'NewCo');
      await user.click(screen.getByRole('button', { name: /^create$/i }));

      // Appears in both the rail and the (now selected) detail header.
      await waitFor(() => expect(screen.getAllByText('NewCo').length).toBeGreaterThan(0));
      expect(screen.getByRole('heading', { name: 'NewCo' })).toBeInTheDocument();
    });

    it('clears the name input after successful creation', async () => {
      const NEW_ORG = { id: 3, name: 'NewCo', slug: 'newco', wazuh_group: 'newco' };
      api.post.mockResolvedValue({ data: NEW_ORG });
      const user = userEvent.setup();
      renderPage();
      await screen.findByRole('heading', { name: 'Acme' });

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
      await screen.findByRole('heading', { name: 'Acme' });

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
      await screen.findByRole('heading', { name: 'Acme' });
      expect(screen.getByRole('button', { name: /^create$/i })).toBeDisabled();
    });
  });

  describe('Users tab — invite dialog', () => {
    it('opens invite dialog when Invite button is clicked', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findByRole('heading', { name: 'Acme' });

      await user.click(screen.getByRole('button', { name: /invite user to acme/i }));
      expect(screen.getByText('Invite user to Acme')).toBeInTheDocument();
    });

    it('closes dialog when Cancel is clicked', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findByRole('heading', { name: 'Acme' });

      await user.click(screen.getByRole('button', { name: /invite user to acme/i }));
      await user.click(screen.getByRole('button', { name: /cancel/i }));

      expect(screen.queryByText('Invite user to Acme')).not.toBeInTheDocument();
    });

    it('submits invite with email, full name and role', async () => {
      api.post.mockResolvedValue({ data: PENDING_INV });
      const user = userEvent.setup();
      renderPage();
      await screen.findByRole('heading', { name: 'Acme' });

      await user.click(screen.getByRole('button', { name: /invite user to acme/i }));
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
      await screen.findByRole('heading', { name: 'Acme' });

      await user.click(screen.getByRole('button', { name: /invite user to acme/i }));
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
      await screen.findByRole('heading', { name: 'Acme' });

      await user.click(screen.getByRole('button', { name: /invite user to acme/i }));
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
      await screen.findByRole('heading', { name: 'Acme' });

      await user.click(screen.getByRole('button', { name: /invite user to acme/i }));
      expect(screen.getByRole('button', { name: /send invitation/i })).toBeDisabled();
    });
  });

  describe('Users tab — invitations list', () => {
    it('auto-loads invitations for the selected org', async () => {
      mockApi({ orgs: [ACME], invites: [PENDING_INV] });
      renderPage();
      await waitFor(() =>
        expect(api.get).toHaveBeenCalledWith('/api/security/organizations/acme/invite/')
      );
    });

    it('shows invitation details', async () => {
      mockApi({ orgs: [ACME], invites: [PENDING_INV] });
      renderPage();

      const table = await screen.findByLabelText('Invitations for Acme');
      expect(within(table).getByText('alice@example.com')).toBeInTheDocument();
      expect(within(table).getByText('Alice Smith')).toBeInTheDocument();
      expect(within(table).getByText('Staff')).toBeInTheDocument();
      expect(within(table).getByText('pending')).toBeInTheDocument();
    });

    it('shows empty state when org has no invitations', async () => {
      mockApi({ orgs: [ACME], invites: [] });
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('No invitations yet.')).toBeInTheDocument()
      );
    });

    it('new invite appears in the list after creation', async () => {
      const NEW_INV = { id: 11, email: 'bob@example.com', full_name: 'Bob', role: 'member', status: 'pending' };
      mockApi({ orgs: [ACME], invites: [] });
      api.post.mockResolvedValue({ data: NEW_INV });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('No invitations yet.')).toBeInTheDocument());

      await user.click(screen.getByRole('button', { name: /invite user to acme/i }));
      await user.type(screen.getByLabelText('Email'), 'bob@example.com');
      await user.type(screen.getByLabelText('Full name'), 'Bob');
      await user.click(screen.getByRole('button', { name: /send invitation/i }));

      await waitFor(() => expect(screen.getAllByText('bob@example.com').length).toBeGreaterThan(0));
    });
  });

  describe('Detection Rules tab — system rule mute', () => {
    const RULE_ACTIVE = { id: 1, name: 'Port Scan', severity: 'high', muted: false };
    const RULE_MUTED = { id: 2, name: 'Brute Force', severity: 'critical', muted: true };

    async function openRulesTab(user) {
      await screen.findByRole('heading', { name: 'Acme' });
      await user.click(screen.getByRole('button', { name: /detection rules/i }));
    }

    it('loads system rules when the Detection Rules tab is opened', async () => {
      mockApi({ orgs: [ACME], systemRules: [RULE_ACTIVE] });
      const user = userEvent.setup();
      renderPage();
      await openRulesTab(user);

      await waitFor(() =>
        expect(api.get).toHaveBeenCalledWith('/api/correlations/org-system-rules/?org=acme')
      );
    });

    it('shows system rules in the section', async () => {
      mockApi({ orgs: [ACME], systemRules: [RULE_ACTIVE, RULE_MUTED] });
      const user = userEvent.setup();
      renderPage();
      await openRulesTab(user);

      await waitFor(() => {
        expect(screen.getByText('Port Scan')).toBeInTheDocument();
        expect(screen.getByText('Brute Force')).toBeInTheDocument();
      });
    });

    it('shows Mute button for unmuted rules', async () => {
      mockApi({ orgs: [ACME], systemRules: [RULE_ACTIVE] });
      const user = userEvent.setup();
      renderPage();
      await openRulesTab(user);

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^mute port scan for acme$/i })).toBeInTheDocument()
      );
    });

    it('shows Unmute button for muted rules', async () => {
      mockApi({ orgs: [ACME], systemRules: [RULE_MUTED] });
      const user = userEvent.setup();
      renderPage();
      await openRulesTab(user);

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^unmute brute force for acme$/i })).toBeInTheDocument()
      );
    });

    it('calls POST to mute an unmuted rule', async () => {
      mockApi({ orgs: [ACME], systemRules: [RULE_ACTIVE] });
      api.post.mockResolvedValue({ data: { rule_id: 1, muted: true } });
      const user = userEvent.setup();
      renderPage();
      await openRulesTab(user);

      const btn = await screen.findByRole('button', { name: /^mute port scan for acme$/i });
      await user.click(btn);

      await waitFor(() =>
        expect(api.post).toHaveBeenCalledWith(
          '/api/correlations/org-system-rules/1/mute/',
          { org: 'acme' }
        )
      );
    });

    it('calls DELETE to unmute a muted rule', async () => {
      mockApi({ orgs: [ACME], systemRules: [RULE_MUTED] });
      api.delete.mockResolvedValue({ data: { rule_id: 2, muted: false } });
      const user = userEvent.setup();
      renderPage();
      await openRulesTab(user);

      const btn = await screen.findByRole('button', { name: /^unmute brute force for acme$/i });
      await user.click(btn);

      await waitFor(() =>
        expect(api.delete).toHaveBeenCalledWith(
          '/api/correlations/org-system-rules/2/mute/?org=acme'
        )
      );
    });

    it('toggles button label from Mute to Unmute after muting', async () => {
      mockApi({ orgs: [ACME], systemRules: [RULE_ACTIVE] });
      api.post.mockResolvedValue({ data: { rule_id: 1, muted: true } });
      const user = userEvent.setup();
      renderPage();
      await openRulesTab(user);

      const btn = await screen.findByRole('button', { name: /^mute port scan for acme$/i });
      await user.click(btn);

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^unmute port scan for acme$/i })).toBeInTheDocument()
      );
    });

    it('shows empty state when no system rules exist', async () => {
      mockApi({ orgs: [ACME], systemRules: [], searchRules: [] });
      const user = userEvent.setup();
      renderPage();
      await openRulesTab(user);

      await waitFor(() =>
        expect(screen.getByText('No system rules defined.')).toBeInTheDocument()
      );
    });
  });

  describe('Infrastructure org (#720)', () => {
    it('requests the org list opting into the Infrastructure org', async () => {
      renderPage();
      await waitFor(() =>
        expect(api.get).toHaveBeenCalledWith(
          '/api/security/organizations/?include_infrastructure=1'
        )
      );
    });

    it('lists the Infrastructure org and badges it when selected', async () => {
      mockApi({ orgs: [ACME, INFRA] });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Shared Infrastructure')).toBeInTheDocument());

      await user.click(screen.getByText('Shared Infrastructure'));
      expect(screen.getByText('Infrastructure')).toBeInTheDocument();
    });

    it('does not offer Invite for the Infrastructure org but does for tenants', async () => {
      mockApi({ orgs: [ACME, INFRA] });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(screen.getByText('Shared Infrastructure')).toBeInTheDocument());

      // Acme is auto-selected → invite available.
      expect(screen.getByRole('button', { name: /invite user to acme/i })).toBeInTheDocument();

      await user.click(screen.getByText('Shared Infrastructure'));
      expect(
        screen.queryByRole('button', { name: /invite user to shared infrastructure/i })
      ).not.toBeInTheDocument();
      expect(screen.getByText('The Infrastructure organisation has no members.')).toBeInTheDocument();
    });

    it('saves AI-triage thresholds for the Infrastructure org via PATCH by slug', async () => {
      mockApi({ orgs: [INFRA] });
      const user = userEvent.setup();
      renderPage();
      await screen.findByRole('heading', { name: 'Shared Infrastructure' });

      await user.click(screen.getByRole('button', { name: /ai triage/i }));

      const fpInput = await screen.findByLabelText('False-positive auto-close threshold');
      await user.clear(fpInput);
      await user.type(fpInput, '0.7');
      await user.click(screen.getByRole('button', { name: /^save$/i }));

      await waitFor(() =>
        expect(api.patch).toHaveBeenCalledWith(
          '/api/security/organizations/infrastructure/',
          expect.objectContaining({ triage_fp_threshold: 0.7 })
        )
      );
    });
  });
});
