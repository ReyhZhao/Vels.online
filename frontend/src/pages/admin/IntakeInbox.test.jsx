import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), delete: vi.fn(), post: vi.fn() },
}));

import api from '@/lib/axios';
import IntakeInbox from './IntakeInbox';

const ROWS = [
  { id: 1, sender: 'unknown@peer.example', subject: 'We detected X', drop_reason: 'dropped:unrecognised_to', body_excerpt: 'hi', received_at: '2026-07-06T10:00:00Z' },
  { id: 2, sender: 'spoof@bad.example', subject: 'spoofed', drop_reason: 'partner:dropped:verification_failed', body_excerpt: 'x', received_at: '2026-07-06T09:00:00Z' },
];

function renderPage() {
  return render(<MemoryRouter><IntakeInbox /></MemoryRouter>);
}

const table = () => screen.getByRole('table');

describe('IntakeInbox', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('lists rows and filters by search', async () => {
    api.get.mockResolvedValue({ data: ROWS });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('unknown@peer.example'));
    await user.type(screen.getByLabelText('Search intake inbox'), 'spoof');
    await waitFor(() => expect(within(table()).queryByText('unknown@peer.example')).not.toBeInTheDocument());
    expect(within(table()).getByText('spoof@bad.example')).toBeInTheDocument();
  });

  it('Create Connection deep-links with the sender pre-filled', async () => {
    api.get.mockResolvedValue({ data: [ROWS[0]] });
    renderPage();
    await waitFor(() => within(table()).getByText('unknown@peer.example'));
    const link = within(table()).getByRole('link', { name: 'Create Connection' });
    expect(link).toHaveAttribute('href', '/admin/partners/connections?sender=unknown%40peer.example');
  });

  it('dismisses a row', async () => {
    api.get.mockResolvedValue({ data: [ROWS[0]] });
    api.delete.mockResolvedValue({});
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('unknown@peer.example'));
    await user.click(within(table()).getByRole('button', { name: 'Dismiss' }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/api/partners/intake-inbox/1/'));
  });

  it('offers Replay for a covered row and POSTs the Connection replay', async () => {
    const covered = { ...ROWS[0], covering_connection: { id: 9, name: 'Peer CSIRT' }, has_raw: true, replayed_incident: null };
    api.get.mockResolvedValueOnce({ data: [covered] }).mockResolvedValueOnce({ data: [covered] });
    api.post.mockResolvedValue({ data: { results: [] } });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('unknown@peer.example'));
    await user.click(within(table()).getByRole('button', { name: 'Replay → Peer CSIRT' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/partners/connections/9/replay-intake/'));
  });

  it('shows a Replayed link once a row has become an incident', async () => {
    const replayed = { ...ROWS[0], replayed_incident: { id: 42, display_id: 'INC-42' } };
    api.get.mockResolvedValue({ data: [replayed] });
    renderPage();
    await waitFor(() => within(table()).getByText('unknown@peer.example'));
    const link = within(table()).getByRole('link', { name: 'Replayed → INC-42' });
    expect(link).toHaveAttribute('href', '/incidents/42');
    expect(within(table()).queryByRole('link', { name: 'Create Connection' })).not.toBeInTheDocument();
  });
});
