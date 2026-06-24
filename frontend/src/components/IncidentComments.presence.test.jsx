import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '../lib/axios';
import IncidentComments from './IncidentComments';
import { PresenceContext } from '../context/PresenceContext';

function ownComment(overrides = {}) {
  return {
    id: 5,
    kind: 'user',
    author: 1,
    author_username: 'dana',
    body: 'my comment',
    is_internal: false,
    created_at: new Date().toISOString(), // within edit window
    metadata: {},
    deleted_at: null,
    ...overrides,
  };
}

function renderWith(presence, comments) {
  api.get.mockResolvedValue({ data: comments });
  return render(
    <PresenceContext.Provider value={presence}>
      <IncidentComments incidentId="INC-1" currentUserId={1} isStaff />
    </PresenceContext.Provider>,
  );
}

describe('IncidentComments presence lock (slices #608/#609)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an inline marker when another analyst is editing a comment', async () => {
    const presence = {
      roster: [{ actor_key: 'user:2', actor_id: 2, display_name: 'eve', activity: 'editing', target: 5 }],
      setActivity: vi.fn(), setViewing: vi.fn(), acquireLock: vi.fn(), refreshLock: vi.fn(),
    };
    renderWith(presence, [ownComment()]);
    await waitFor(() => expect(screen.getByTestId('comment-edit-marker')).toBeInTheDocument());
    expect(screen.getByTestId('comment-edit-marker')).toHaveTextContent('eve is editing');
  });

  it('opens a read-only editor attributed to the holder on a 409 lock denial', async () => {
    const presence = {
      roster: [],
      setActivity: vi.fn(),
      setViewing: vi.fn(),
      acquireLock: vi.fn().mockResolvedValue({ granted: false, holder: 'eve' }),
      refreshLock: vi.fn(),
    };
    renderWith(presence, [ownComment()]);
    await waitFor(() => expect(screen.getByText('Edit')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Edit'));

    await waitFor(() => expect(screen.getByTestId('comment-lock-banner')).toBeInTheDocument());
    expect(screen.getByTestId('comment-lock-banner')).toHaveTextContent('eve is editing');
    // Read-only: no Save button, textarea is readOnly.
    expect(screen.queryByText('Save')).not.toBeInTheDocument();
    expect(presence.acquireLock).toHaveBeenCalledWith(5);
  });

  it('opens an editable editor when the lock is granted', async () => {
    const presence = {
      roster: [],
      setActivity: vi.fn(),
      setViewing: vi.fn(),
      acquireLock: vi.fn().mockResolvedValue({ granted: true }),
      refreshLock: vi.fn(),
    };
    renderWith(presence, [ownComment()]);
    await waitFor(() => expect(screen.getByText('Edit')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Edit'));

    await waitFor(() => expect(screen.getByText('Save')).toBeInTheDocument());
    expect(screen.queryByTestId('comment-lock-banner')).not.toBeInTheDocument();
  });

  it('announces composing a new comment as editing on focus', async () => {
    const presence = {
      roster: [],
      setActivity: vi.fn(),
      setViewing: vi.fn(),
      acquireLock: vi.fn(),
      refreshLock: vi.fn(),
    };
    renderWith(presence, []);
    const box = await screen.findByPlaceholderText('Add a comment…');
    fireEvent.focus(box);
    expect(presence.setActivity).toHaveBeenCalledWith('editing', null);
    fireEvent.blur(box);
    expect(presence.setViewing).toHaveBeenCalled();
  });
});
