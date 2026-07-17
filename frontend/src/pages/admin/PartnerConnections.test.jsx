import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import PartnerConnections from './PartnerConnections';

const ORGS = [
  { id: 1, name: 'Acme', slug: 'acme', is_infrastructure: false },
  { id: 99, name: 'Shared Infrastructure', slug: 'infrastructure', is_infrastructure: true },
];

function mkConn(over = {}) {
  return {
    id: 1, name: 'Peer CSIRT', kind: 'csirt_peer', organization: 1,
    organization_name: 'Acme', direction: 'bidirectional',
    external_reference_regex: '', field_mappings: {},
    sender_addresses: ['soc@peer.example'], active: true, ...over,
  };
}

function mockGet(conns = [mkConn()]) {
  api.get.mockImplementation(url => {
    if (url === '/api/security/organizations/') return Promise.resolve({ data: ORGS });
    return Promise.resolve({ data: conns });
  });
}

function renderPage(entries = ['/admin/partners/connections']) {
  return render(
    <MemoryRouter initialEntries={entries}><PartnerConnections /></MemoryRouter>,
  );
}

const table = () => screen.getByRole('table');

describe('PartnerConnections', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('lists connections and filters by search', async () => {
    mockGet([mkConn(), mkConn({ id: 2, name: 'Fortinet PSIRT', kind: 'vendor', organization_name: 'Shared Infrastructure' })]);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Peer CSIRT'));
    await user.type(screen.getByLabelText('Search connections'), 'fortinet');
    await waitFor(() => expect(within(table()).queryByText('Peer CSIRT')).not.toBeInTheDocument());
    expect(within(table()).getByText('Fortinet PSIRT')).toBeInTheDocument();
  });

  it('filters by kind', async () => {
    mockGet([mkConn(), mkConn({ id: 2, name: 'Fortinet PSIRT', kind: 'vendor' })]);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Peer CSIRT'));
    await user.selectOptions(screen.getByLabelText('Kind filter'), 'vendor');
    await waitFor(() => expect(within(table()).queryByText('Peer CSIRT')).not.toBeInTheDocument());
    expect(within(table()).getByText('Fortinet PSIRT')).toBeInTheDocument();
  });

  it('vendor kind defaults org to Infrastructure and direction to inbound-only', async () => {
    mockGet([]);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: 'New Connection' }));
    await user.selectOptions(screen.getByLabelText('Connection kind'), 'vendor');
    expect(screen.getByLabelText('Target organization')).toHaveValue('99');
    expect(screen.getByLabelText('Connection direction')).toHaveValue('inbound_only');
  });

  it('creates a connection', async () => {
    mockGet([]);
    api.post.mockResolvedValue({ data: mkConn({ id: 5, name: 'New Peer' }) });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: 'New Connection' }));
    await user.type(screen.getByLabelText('Connection name'), 'New Peer');
    await user.type(screen.getByLabelText('Sender addresses'), 'soc@new.example');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/partners/connections/', expect.objectContaining({
      name: 'New Peer',
      sender_addresses: ['soc@new.example'],
    })));
  });

  it('pre-fills the sender from a ?sender= deep link (Intake Inbox onboarding)', async () => {
    mockGet([]);
    renderPage(['/admin/partners/connections?sender=unknown@peer.example']);
    await waitFor(() => expect(screen.getByLabelText('Sender addresses')).toHaveValue('unknown@peer.example'));
  });

  it('offers replay after saving when covered held messages exist, and POSTs the replay', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/security/organizations/') return Promise.resolve({ data: ORGS });
      if (url.includes('/replay-intake/')) return Promise.resolve({ data: {
        count: 2, without_reference: 1,
        messages: [
          { id: 1, subject: '[CASE-1] a', external_reference: 'CASE-1', has_reference: true },
          { id: 2, subject: 'no ref', external_reference: '', has_reference: false },
        ],
      } });
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValue({ data: mkConn({ id: 5, name: 'New Peer' }) });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: 'New Connection' }));
    await user.type(screen.getByLabelText('Connection name'), 'New Peer');
    await user.type(screen.getByLabelText('Sender addresses'), 'soc@new.example');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await screen.findByText('Replay held messages?');
    // Ref-less messages are flagged as fragmenting into separate incidents.
    expect(screen.getByText(/separate flagged incident/i)).toBeInTheDocument();

    api.post.mockResolvedValueOnce({ data: { results: [] } });
    await user.click(screen.getByRole('button', { name: 'Replay now' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/partners/connections/5/replay-intake/'));
  });

  it('shows no replay offer when no held messages are covered', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/security/organizations/') return Promise.resolve({ data: ORGS });
      if (url.includes('/replay-intake/')) return Promise.resolve({ data: { count: 0, without_reference: 0, messages: [] } });
      return Promise.resolve({ data: [] });
    });
    api.post.mockResolvedValue({ data: mkConn({ id: 5, name: 'New Peer' }) });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: 'New Connection' }));
    await user.type(screen.getByLabelText('Connection name'), 'New Peer');
    await user.type(screen.getByLabelText('Sender addresses'), 'soc@new.example');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/partners/connections/5/replay-intake/'));
    expect(screen.queryByText('Replay held messages?')).not.toBeInTheDocument();
  });
});
