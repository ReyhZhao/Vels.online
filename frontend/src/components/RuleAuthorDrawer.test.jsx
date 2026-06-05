import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import api from '../lib/axios';
import RuleAuthorDrawer from './RuleAuthorDrawer';

const STUB_DRAFT = {
  name: 'Brute force rule',
  description: 'Detects repeated failed logins',
  correlation_key: 'user.name',
  window_minutes: 10,
  severity: 'high',
  enabled: true,
  legs: [
    {
      count: 5,
      display_order: 0,
      conditions: [
        { field_kind: 'alert_field', field_name: 'severity', operator: 'equals', value: 'high' },
      ],
    },
  ],
  organization: null,
};

const STUB_CATALOG = {
  fields: {
    alert_field: [
      { value: 'severity', label: 'severity' },
      { value: 'source_kind', label: 'source_kind' },
    ],
    entity: [{ value: 'host.name', label: 'host.name' }],
    source_ref: [{ value: 'rule_id', label: 'rule_id' }],
  },
  operators: {
    alert_field: [{ value: 'equals', label: 'Equals' }],
    entity: [{ value: 'equals', label: 'Equals' }],
    source_ref: [{ value: 'equals', label: 'Equals' }],
  },
  field_kinds: [
    { value: 'alert_field', label: 'Alert field' },
    { value: 'entity', label: 'ECS entity' },
    { value: 'source_ref', label: 'Source ref key' },
  ],
  correlation_keys: [
    { value: 'none', label: 'None (org-wide)' },
    { value: 'user.name', label: 'Username (user.name)' },
  ],
  severities: ['critical', 'high', 'medium', 'low', 'info'],
};

function mockGetDefault() {
  api.get.mockImplementation(url => {
    if (url.includes('catalog')) return Promise.resolve({ data: STUB_CATALOG });
    if (url.includes('organizations')) return Promise.resolve({ data: [] });
    return Promise.reject(new Error(`Unmocked GET: ${url}`));
  });
}

function renderDrawer(props = {}) {
  return render(
    <RuleAuthorDrawer onClose={vi.fn()} onSaved={vi.fn()} {...props} />
  );
}

describe('RuleAuthorDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetDefault();
  });

  it('renders heading and subheading', () => {
    renderDrawer();
    expect(screen.getByText('Draft with AI')).toBeInTheDocument();
    expect(screen.getByText(/converse to refine/i)).toBeInTheDocument();
  });

  it('renders message input and send button', () => {
    renderDrawer();
    expect(screen.getByPlaceholderText(/describe what to detect/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send message/i })).toBeInTheDocument();
  });

  it('shows empty-thread hint before any messages', () => {
    renderDrawer();
    expect(screen.getByText(/describe what to detect/i, { selector: 'p' })).toBeInTheDocument();
  });

  it('send button is disabled when input is empty', () => {
    renderDrawer();
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled();
  });

  it('save button is disabled when draft name is empty', () => {
    renderDrawer();
    expect(screen.getByRole('button', { name: /save rule/i })).toBeDisabled();
  });

  it('save button is enabled after typing a name manually', async () => {
    const user = userEvent.setup();
    renderDrawer();
    await user.type(screen.getByPlaceholderText('Rule name'), 'My Rule');
    expect(screen.getByRole('button', { name: /save rule/i })).not.toBeDisabled();
  });

  it('appends user message to thread after sending', async () => {
    api.post.mockResolvedValue({
      data: {
        updated_draft: STUB_DRAFT,
        assistant_reply: 'I drafted a brute force rule.',
        warnings: [],
      },
    });

    const user = userEvent.setup();
    renderDrawer();
    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'detect brute force logins');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByText('detect brute force logins')).toBeInTheDocument();
    });
  });

  it('appends assistant reply after a turn', async () => {
    api.post.mockResolvedValue({
      data: {
        updated_draft: STUB_DRAFT,
        assistant_reply: 'I drafted a brute force rule.',
        warnings: [],
      },
    });

    const user = userEvent.setup();
    renderDrawer();
    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'detect brute force logins');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByText('I drafted a brute force rule.')).toBeInTheDocument();
    });
  });

  it('multiple turns append in order', async () => {
    api.post
      .mockResolvedValueOnce({
        data: {
          updated_draft: STUB_DRAFT,
          assistant_reply: 'First reply.',
          warnings: [],
        },
      })
      .mockResolvedValueOnce({
        data: {
          updated_draft: { ...STUB_DRAFT, window_minutes: 20 },
          assistant_reply: 'Second reply.',
          warnings: [],
        },
      });

    const user = userEvent.setup();
    renderDrawer();

    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'first message');
    await user.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => screen.getByText('First reply.'));

    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'second message');
    await user.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => screen.getByText('Second reply.'));

    expect(screen.getByText('first message')).toBeInTheDocument();
    expect(screen.getByText('second message')).toBeInTheDocument();
    expect(screen.getByText('First reply.')).toBeInTheDocument();
    expect(screen.getByText('Second reply.')).toBeInTheDocument();
  });

  it('updates the draft name field from a turn response', async () => {
    api.post.mockResolvedValue({
      data: {
        updated_draft: STUB_DRAFT,
        assistant_reply: 'Updated.',
        warnings: [],
      },
    });

    const user = userEvent.setup();
    renderDrawer();
    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'brute force');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByDisplayValue('Brute force rule')).toBeInTheDocument();
    });
  });

  it('displays sanitizer warnings surfaced from a turn', async () => {
    api.post.mockResolvedValue({
      data: {
        updated_draft: STUB_DRAFT,
        assistant_reply: 'Done with warnings.',
        warnings: ['Unknown field removed: bad_field'],
      },
    });

    const user = userEvent.setup();
    renderDrawer();
    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'detect something');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByText('Unknown field removed: bad_field')).toBeInTheDocument();
    });
  });

  it('posts the reviewed draft to /api/correlations/rules/ on save', async () => {
    api.post.mockImplementation(url => {
      if (url.includes('/draft/')) {
        return Promise.resolve({
          data: { updated_draft: STUB_DRAFT, assistant_reply: 'Done.', warnings: [] },
        });
      }
      if (url.includes('/rules/')) {
        return Promise.resolve({ data: { ...STUB_DRAFT, id: 42 } });
      }
      return Promise.reject(new Error(`Unmocked POST: ${url}`));
    });

    const onSaved = vi.fn();
    const user = userEvent.setup();
    renderDrawer({ onSaved });

    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'detect brute force');
    await user.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => screen.getByDisplayValue('Brute force rule'));

    await user.click(screen.getByRole('button', { name: /save rule/i }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/api/correlations/rules/',
        expect.objectContaining({ name: 'Brute force rule' }),
      );
      expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: 42 }));
    });
  });

  it('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderDrawer({ onClose });
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderDrawer({ onClose });
    await user.click(screen.getByRole('button', { name: /close drawer/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it('shows API error in the footer on draft failure', async () => {
    api.post.mockRejectedValue({
      response: { data: { detail: 'Assistant unavailable.' } },
    });

    const user = userEvent.setup();
    renderDrawer();
    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'something');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByText('Assistant unavailable.')).toBeInTheDocument();
    });
  });

  it('replays messages and current_draft to the draft endpoint', async () => {
    api.post
      .mockResolvedValueOnce({
        data: { updated_draft: STUB_DRAFT, assistant_reply: 'First.', warnings: [] },
      })
      .mockResolvedValueOnce({
        data: { updated_draft: STUB_DRAFT, assistant_reply: 'Second.', warnings: [] },
      });

    const user = userEvent.setup();
    renderDrawer();

    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'first');
    await user.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => screen.getByText('First.'));

    await user.type(screen.getByPlaceholderText(/describe what to detect/i), 'second');
    await user.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => screen.getByText('Second.'));

    const secondCall = api.post.mock.calls[1];
    expect(secondCall[1].messages).toHaveLength(3); // user, assistant, user
    expect(secondCall[1].current_draft).toMatchObject({ name: 'Brute force rule' });
  });
});
