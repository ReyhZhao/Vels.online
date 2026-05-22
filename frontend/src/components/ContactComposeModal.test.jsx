import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { post: vi.fn() },
}));

import api from '../lib/axios';
import ContactComposeModal from './ContactComposeModal';

const CONTACT = { contact_id: 42, name: 'Carol', email: 'carol@example.com' };

describe('ContactComposeModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders with contact name in header', () => {
    render(
      <ContactComposeModal
        displayId="INC-001"
        contact={CONTACT}
        onClose={vi.fn()}
        onSent={vi.fn()}
      />
    );
    expect(screen.getByText('Message Carol')).toBeInTheDocument();
  });

  it('renders role selector and message textarea', () => {
    render(
      <ContactComposeModal
        displayId="INC-001"
        contact={CONTACT}
        onClose={vi.fn()}
        onSent={vi.fn()}
      />
    );
    expect(screen.getByText('Role')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Write your message…')).toBeInTheDocument();
  });

  it('calls POST with correct payload on submit', async () => {
    const onSent = vi.fn();
    api.post.mockResolvedValue({});

    render(
      <ContactComposeModal
        displayId="INC-001"
        contact={CONTACT}
        onClose={vi.fn()}
        onSent={onSent}
      />
    );

    fireEvent.change(screen.getByPlaceholderText('Write your message…'), {
      target: { value: 'Hello Carol' },
    });
    fireEvent.click(screen.getByText('Send'));

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/api/incidents/INC-001/contact-messages/', {
        contact_id: 42,
        role: 'notified',
        body: 'Hello Carol',
      })
    );
    expect(onSent).toHaveBeenCalled();
  });

  it('closes on cancel', () => {
    const onClose = vi.fn();
    render(
      <ContactComposeModal
        displayId="INC-001"
        contact={CONTACT}
        onClose={onClose}
        onSent={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('disables send when body is empty', () => {
    render(
      <ContactComposeModal
        displayId="INC-001"
        contact={CONTACT}
        onClose={vi.fn()}
        onSent={vi.fn()}
      />
    );
    expect(screen.getByText('Send')).toBeDisabled();
  });

  it('shows error message on failure', async () => {
    api.post.mockRejectedValue({ response: { data: { detail: 'Server error' } } });

    render(
      <ContactComposeModal
        displayId="INC-001"
        contact={CONTACT}
        onClose={vi.fn()}
        onSent={vi.fn()}
      />
    );

    fireEvent.change(screen.getByPlaceholderText('Write your message…'), {
      target: { value: 'Test message' },
    });
    fireEvent.click(screen.getByText('Send'));

    await waitFor(() => screen.getByText('Server error'));
  });
});
