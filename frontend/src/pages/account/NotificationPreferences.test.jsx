import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../lib/axios', () => ({
  default: { get: vi.fn(), patch: vi.fn() },
}));

vi.mock('../../hooks/usePushSubscription', () => ({
  default: vi.fn(),
}));

import api from '../../lib/axios';
import usePushSubscription from '../../hooks/usePushSubscription';
import NotificationPreferences from './NotificationPreferences';

const defaultPrefs = {
  email_assignment: true,
  inapp_assignment: true,
  email_delegation: true,
  inapp_delegation: true,
  email_comment: true,
  inapp_comment: true,
  email_state_change: true,
  inapp_state_change: true,
  email_incident_alert: true,
  inapp_incident_alert: true,
  updated_at: new Date().toISOString(),
};

function renderPage() {
  return render(
    <MemoryRouter>
      <NotificationPreferences />
    </MemoryRouter>
  );
}

const defaultPushHook = { isSubscribed: false, isSupported: true, loading: false, keyError: false, subscribe: vi.fn(), unsubscribe: vi.fn() };

describe('NotificationPreferences', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.get.mockResolvedValue({ data: { ...defaultPrefs } });
    api.patch.mockResolvedValue({ data: { ...defaultPrefs } });
    usePushSubscription.mockReturnValue(defaultPushHook);
  });

  it('loads and renders the page', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Notification preferences')).toBeInTheDocument());
    expect(screen.getByText('Assignment')).toBeInTheDocument();
    expect(screen.getByText('Delegation')).toBeInTheDocument();
    expect(screen.getByText('Comments')).toBeInTheDocument();
  });

  it('saves changed preferences on button click', async () => {
    api.patch.mockResolvedValue({ data: { ...defaultPrefs, email_comment: false } });

    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Comments'));

    const emailCommentToggle = screen.getByRole('switch', { name: /comments email/i });
    await user.click(emailCommentToggle);

    await user.click(screen.getByRole('button', { name: /save preferences/i }));

    await waitFor(() =>
      expect(api.patch).toHaveBeenCalledWith(
        '/api/me/notification-prefs/',
        expect.objectContaining({ email_comment: false })
      )
    );
    expect(screen.getByRole('status')).toHaveTextContent('Preferences saved');
  });

  it('shows guardrail error when both assignment channels disabled', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Assignment'));

    const inappToggle = screen.getByRole('switch', { name: /assignment in-app/i });
    const emailToggle = screen.getByRole('switch', { name: /assignment email/i });

    await user.click(inappToggle);
    await user.click(emailToggle);

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/assignment/i)
    );
  });

  it('shows guardrail error when both delegation channels disabled', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Delegation'));

    await user.click(screen.getByRole('switch', { name: /delegation in-app/i }));
    await user.click(screen.getByRole('switch', { name: /delegation email/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(/delegation/i)
    );
  });

  it('save button is disabled when no changes are pending', async () => {
    renderPage();
    await waitFor(() => screen.getByText('Assignment'));
    expect(screen.getByRole('button', { name: /save preferences/i })).toBeDisabled();
  });

  it('shows Push column header', async () => {
    renderPage();
    await waitFor(() => screen.getByText('Assignment'));
    expect(screen.getByText('Push')).toBeInTheDocument();
  });

  it('shows enable push button when not subscribed and supported', async () => {
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /enable push notifications/i }));
  });

  it('push toggles are disabled when device is not enrolled', async () => {
    renderPage();
    await waitFor(() => screen.getByText('Assignment'));
    const pushToggles = screen.getAllByRole('switch', { name: /enroll this device first/i });
    expect(pushToggles.length).toBeGreaterThan(0);
    pushToggles.forEach(t => expect(t).toBeDisabled());
  });

  it('shows unsupported message when push is not available', async () => {
    usePushSubscription.mockReturnValue({ ...defaultPushHook, isSupported: false });
    renderPage();
    await waitFor(() => screen.getByText(/push notifications are not supported/i));
  });

  it('shows subscribed state with disable button when enrolled', async () => {
    usePushSubscription.mockReturnValue({ ...defaultPushHook, isSubscribed: true });
    renderPage();
    await waitFor(() => screen.getByText(/push notifications enabled/i));
    expect(screen.getByRole('button', { name: /disable/i })).toBeInTheDocument();
  });

  it('push toggles are enabled when device is enrolled', async () => {
    usePushSubscription.mockReturnValue({ ...defaultPushHook, isSubscribed: true });
    renderPage();
    await waitFor(() => screen.getByText('Assignment'));
    const pushToggles = screen.getAllByRole('switch', { name: /push$/i });
    pushToggles.forEach(t => expect(t).not.toBeDisabled());
  });

  it('shows error when subscribe throws due to missing VAPID key', async () => {
    const subscribe = vi.fn().mockRejectedValue(new Error('Push notifications are not available. Please try again later.'));
    usePushSubscription.mockReturnValue({ ...defaultPushHook, subscribe });

    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /enable push notifications/i }));

    await user.click(screen.getByRole('button', { name: /enable push notifications/i }));

    await waitFor(() =>
      expect(screen.getByText(/failed to enable push notifications/i)).toBeInTheDocument()
    );
  });

  it('shows permission denied error when subscribe throws Permission denied', async () => {
    const subscribe = vi.fn().mockRejectedValue(new Error('Permission denied'));
    usePushSubscription.mockReturnValue({ ...defaultPushHook, subscribe });

    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole('button', { name: /enable push notifications/i }));

    await user.click(screen.getByRole('button', { name: /enable push notifications/i }));

    await waitFor(() =>
      expect(screen.getByText(/notification permission was denied/i)).toBeInTheDocument()
    );
  });

  it('shows error message when save fails', async () => {
    api.patch.mockRejectedValue({
      response: { data: 'Server error.' },
    });

    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Comments'));

    await user.click(screen.getByRole('switch', { name: /comments email/i }));
    await user.click(screen.getByRole('button', { name: /save preferences/i }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Server error.')
    );
  });
});
