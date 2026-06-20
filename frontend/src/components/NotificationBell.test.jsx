import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}));

vi.mock('./SlideOver', () => ({
  default: ({ open, title, loading, children }) =>
    open ? (
      <div data-testid="slideover">
        <h2>{title}</h2>
        {loading ? <p role="status">Loading…</p> : children}
      </div>
    ) : null,
}));

import api from '../lib/axios';
import NotificationBell from './NotificationBell';

function renderBell() {
  return render(
    <MemoryRouter>
      <NotificationBell />
    </MemoryRouter>
  );
}

describe('NotificationBell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { unread_count: 0 } });
  });

  it('renders the bell button', async () => {
    renderBell();
    await waitFor(() => expect(screen.getByTestId('notification-bell')).toBeInTheDocument());
  });

  it('shows unread badge when count > 0', async () => {
    api.get.mockResolvedValueOnce({ data: { unread_count: 3 } });
    renderBell();
    await waitFor(() => expect(screen.getByTestId('unread-badge')).toHaveTextContent('3'));
  });

  it('shows 9+ when unread count exceeds 9', async () => {
    api.get.mockResolvedValueOnce({ data: { unread_count: 12 } });
    renderBell();
    await waitFor(() => expect(screen.getByTestId('unread-badge')).toHaveTextContent('9+'));
  });

  it('hides badge when no unread notifications', async () => {
    api.get.mockResolvedValueOnce({ data: { unread_count: 0 } });
    renderBell();
    await waitFor(() => expect(screen.queryByTestId('unread-badge')).not.toBeInTheDocument());
  });

  it('opens slideover and loads notifications on bell click', async () => {
    api.get
      .mockResolvedValueOnce({ data: { unread_count: 1 } })
      .mockResolvedValueOnce({
        data: {
          results: [
            {
              id: 1,
              kind: 'comment',
              incident_id: 10,
              read_at: null,
              created_at: new Date().toISOString(),
              payload: { title: 'New comment on INC-001', body: 'Hello' },
            },
          ],
        },
      });

    const user = userEvent.setup();
    renderBell();
    await waitFor(() => screen.getByTestId('notification-bell'));

    await user.click(screen.getByTestId('notification-bell'));
    await waitFor(() => expect(screen.getByTestId('slideover')).toBeInTheDocument());
    expect(screen.getByText('New comment on INC-001')).toBeInTheDocument();
  });

  it('marks notification read on click and decrements count', async () => {
    api.get
      .mockResolvedValueOnce({ data: { unread_count: 1 } })
      .mockResolvedValueOnce({
        data: {
          results: [
            {
              id: 5,
              kind: 'comment',
              incident_id: 10,
              read_at: null,
              created_at: new Date().toISOString(),
              payload: { title: 'A notification', body: '' },
            },
          ],
        },
      });
    api.post.mockResolvedValue({ data: {} });

    const user = userEvent.setup();
    renderBell();
    await waitFor(() => screen.getByTestId('notification-bell'));

    await user.click(screen.getByTestId('notification-bell'));
    await waitFor(() => screen.getByText('A notification'));

    await user.click(screen.getByText('A notification'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/me/notifications/5/read/')
    );
    expect(screen.queryByTestId('unread-badge')).not.toBeInTheDocument();
  });

  it('clears all notifications via Clear all', async () => {
    api.get
      .mockResolvedValueOnce({ data: { unread_count: 2 } })
      .mockResolvedValueOnce({
        data: {
          results: [
            { id: 1, kind: 'comment', read_at: null, created_at: new Date().toISOString(), payload: { title: 'One', body: '' } },
            { id: 2, kind: 'comment', read_at: null, created_at: new Date().toISOString(), payload: { title: 'Two', body: '' } },
          ],
        },
      });
    api.delete.mockResolvedValue({ data: { deleted: 2 } });

    const user = userEvent.setup();
    renderBell();
    await waitFor(() => screen.getByTestId('notification-bell'));

    await user.click(screen.getByTestId('notification-bell'));
    await waitFor(() => screen.getByText('One'));

    await user.click(screen.getByText('Clear all'));

    await waitFor(() =>
      expect(api.delete).toHaveBeenCalledWith('/api/me/notifications/clear-all/')
    );
    expect(screen.queryByText('One')).not.toBeInTheDocument();
    expect(screen.getByText('No notifications yet.')).toBeInTheDocument();
    expect(screen.queryByTestId('unread-badge')).not.toBeInTheDocument();
  });

  it('hides Clear all when there are no notifications', async () => {
    api.get
      .mockResolvedValueOnce({ data: { unread_count: 0 } })
      .mockResolvedValueOnce({ data: { results: [] } });

    const user = userEvent.setup();
    renderBell();
    await waitFor(() => screen.getByTestId('notification-bell'));

    await user.click(screen.getByTestId('notification-bell'));
    await waitFor(() => screen.getByTestId('slideover'));
    expect(screen.queryByText('Clear all')).not.toBeInTheDocument();
  });
});
