import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

vi.mock('./ContactComposeModal', () => ({
  default: ({ contact, onClose }) => (
    <div data-testid="compose-modal">
      <span>Compose for {contact.name}</span>
      <button onClick={onClose}>Close Modal</button>
    </div>
  ),
}));

import api from '../lib/axios';
import ContactMessagesCard from './ContactMessagesCard';

const GROUP_WITH_MESSAGES = [
  {
    contact_id: 10,
    name: 'Carol',
    email: 'carol@example.com',
    department: 'IT',
    messages: [
      {
        id: 1,
        direction: 'outbound',
        role: 'questioned',
        body: 'Did you see this?',
        parent_id: null,
        read_at: null,
        created_at: '2026-01-01T10:00:00Z',
      },
      {
        id: 2,
        direction: 'inbound',
        role: '',
        body: 'Yes I did.',
        parent_id: 1,
        read_at: null,
        created_at: '2026-01-01T11:00:00Z',
      },
    ],
  },
];

const GROUP_NO_MESSAGES = [
  {
    contact_id: 10,
    name: 'Carol',
    email: 'carol@example.com',
    department: '',
    messages: [],
  },
];

describe('ContactMessagesCard', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders nothing while loading', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    const { container } = render(<ContactMessagesCard displayId="INC-001" />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when no groups returned', async () => {
    api.get.mockResolvedValue({ data: [] });
    const { container } = render(<ContactMessagesCard displayId="INC-001" />);
    await waitFor(() => {});
    expect(container.firstChild).toBeNull();
  });

  it('renders contact row with Message button', async () => {
    api.get.mockResolvedValue({ data: GROUP_NO_MESSAGES });
    render(<ContactMessagesCard displayId="INC-001" />);
    await waitFor(() => screen.getByText('Carol'));
    expect(screen.getByText('Message')).toBeInTheDocument();
  });

  it('shows unread badge when an inbound message has no read_at', async () => {
    api.get.mockResolvedValue({ data: GROUP_WITH_MESSAGES });
    render(<ContactMessagesCard displayId="INC-001" />);
    await waitFor(() => screen.getByTitle('Unread reply'));
    expect(screen.getByTitle('Unread reply')).toBeInTheDocument();
  });

  it('expands thread and calls mark-read when row is toggled open', async () => {
    api.get.mockResolvedValue({ data: GROUP_WITH_MESSAGES });
    api.post.mockResolvedValue({});

    render(<ContactMessagesCard displayId="INC-001" />);
    await waitFor(() => screen.getByText('Carol'));

    fireEvent.click(screen.getByText('Carol'));

    await waitFor(() => screen.getByText('Did you see this?'));
    expect(screen.getByText('Yes I did.')).toBeInTheDocument();

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith(
        '/api/incidents/INC-001/contact-messages/mark-read/',
        { contact_id: 10 }
      )
    );
  });

  it('hides unread badge after expanding (mark-read clears it)', async () => {
    api.get.mockResolvedValue({ data: GROUP_WITH_MESSAGES });
    api.post.mockResolvedValue({});

    render(<ContactMessagesCard displayId="INC-001" />);
    await waitFor(() => screen.getByTitle('Unread reply'));

    fireEvent.click(screen.getByText('Carol'));

    await waitFor(() => expect(screen.queryByTitle('Unread reply')).not.toBeInTheDocument());
  });

  it('renders inbound reply indented under outbound parent', async () => {
    api.get.mockResolvedValue({ data: GROUP_WITH_MESSAGES });
    render(<ContactMessagesCard displayId="INC-001" />);
    await waitFor(() => screen.getByText('Carol'));

    fireEvent.click(screen.getByText('Carol'));

    await waitFor(() => screen.getByText('Did you see this?'));
    expect(screen.getByText('Yes I did.')).toBeInTheDocument();
  });

  it('opens compose modal when Message button is clicked', async () => {
    api.get.mockResolvedValue({ data: GROUP_WITH_MESSAGES });
    render(<ContactMessagesCard displayId="INC-001" />);
    await waitFor(() => screen.getByText('Message'));

    fireEvent.click(screen.getByText('Message'));

    expect(screen.getByTestId('compose-modal')).toBeInTheDocument();
    expect(screen.getByText('Compose for Carol')).toBeInTheDocument();
  });

  it('closes compose modal when onClose is triggered', async () => {
    api.get.mockResolvedValue({ data: GROUP_WITH_MESSAGES });
    render(<ContactMessagesCard displayId="INC-001" />);
    await waitFor(() => screen.getByText('Message'));

    fireEvent.click(screen.getByText('Message'));
    fireEvent.click(screen.getByText('Close Modal'));

    expect(screen.queryByTestId('compose-modal')).not.toBeInTheDocument();
  });
});
