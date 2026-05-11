import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import IncidentTimeline, {
  renderEvent,
  renderIncidentUpdated,
  renderCommentAdded,
  renderCommentEdited,
  renderCommentDeleted,
  renderIncidentDelegated,
  renderIncidentDelegationReturned,
  renderIncidentAssigneeChanged,
  renderTemplateApplied,
  renderTaskCreated,
  renderTaskStateChanged,
  renderTaskAutoCancelled,
  renderExceptionCreated,
} from './IncidentTimeline';

// ── renderer unit tests ───────────────────────────────────────────────────────

describe('renderIncidentUpdated', () => {
  it('formats a single field change', () => {
    const result = renderIncidentUpdated({ changes: { state: { old: 'new', new: 'triaged' } } });
    expect(result).toBe('state: new → triaged');
  });

  it('formats multiple field changes separated by ·', () => {
    const result = renderIncidentUpdated({
      changes: {
        state: { old: 'new', new: 'triaged' },
        severity: { old: 'medium', new: 'high' },
      },
    });
    expect(result).toContain('state: new → triaged');
    expect(result).toContain('severity: medium → high');
    expect(result).toContain(' · ');
  });

  it('falls back when changes is empty', () => {
    expect(renderIncidentUpdated({ changes: {} })).toBe('Incident updated.');
  });

  it('handles null old/new values', () => {
    const result = renderIncidentUpdated({ changes: { closure_reason: { old: null, new: 'resolved' } } });
    expect(result).toContain('— → resolved');
  });
});

describe('renderCommentAdded', () => {
  it('includes target id', () => {
    expect(renderCommentAdded({ target_id: 5, is_internal: false })).toContain('#5');
  });

  it('marks internal comments', () => {
    expect(renderCommentAdded({ target_id: 5, is_internal: true })).toContain('internal');
  });

  it('handles missing target_id', () => {
    expect(renderCommentAdded({})).toContain('Comment added');
  });
});

describe('renderCommentEdited', () => {
  it('includes target id', () => {
    expect(renderCommentEdited({ target_id: 3 })).toContain('#3');
  });
});

describe('renderCommentDeleted', () => {
  it('includes target id', () => {
    expect(renderCommentDeleted({ target_id: 7 })).toContain('#7');
  });
});

describe('renderIncidentDelegated', () => {
  it('shows delegate id and note', () => {
    const result = renderIncidentDelegated({ delegate_id: 2, by_id: 1, note: 'please help' });
    expect(result).toContain('user #2');
    expect(result).toContain('please help');
  });

  it('handles missing note', () => {
    const result = renderIncidentDelegated({ delegate_id: 2, by_id: 1, note: '' });
    expect(result).not.toContain('"');
  });
});

describe('renderIncidentDelegationReturned', () => {
  it('shows delegate id', () => {
    expect(renderIncidentDelegationReturned({ delegate_id: 3, by_id: 1 })).toContain('user #3');
  });
});

describe('renderIncidentAssigneeChanged', () => {
  it('shows from and to ids', () => {
    const result = renderIncidentAssigneeChanged({ from: 1, to: 2 });
    expect(result).toContain('#1');
    expect(result).toContain('#2');
  });

  it('handles null from (was unassigned)', () => {
    const result = renderIncidentAssigneeChanged({ from: null, to: 2 });
    expect(result).toContain('(unassigned)');
    expect(result).toContain('#2');
  });
});

describe('renderTemplateApplied', () => {
  it('shows template name when provided', () => {
    expect(renderTemplateApplied({ template_name: 'Phishing Response' })).toContain('Phishing Response');
  });

  it('falls back to template id', () => {
    expect(renderTemplateApplied({ template_id: 5 })).toContain('#5');
  });
});

describe('renderTaskCreated', () => {
  it('shows task title', () => {
    expect(renderTaskCreated({ title: 'Check logs', task_id: 1 })).toContain('Check logs');
  });
});

describe('renderTaskStateChanged', () => {
  it('shows old and new state', () => {
    const result = renderTaskStateChanged({ title: 'Collect evidence', old: 'new', new: 'done' });
    expect(result).toContain('new → done');
    expect(result).toContain('Collect evidence');
  });
});

describe('renderTaskAutoCancelled', () => {
  it('shows count', () => {
    expect(renderTaskAutoCancelled({ count: 3 })).toContain('3');
  });

  it('handles missing count', () => {
    expect(renderTaskAutoCancelled({})).toContain('auto-cancelled');
  });
});

describe('renderExceptionCreated', () => {
  it('includes description when present', () => {
    const result = renderExceptionCreated({ description: 'Suppress brute force', wazuh_rule_id: 200001 });
    expect(result).toContain('Suppress brute force');
  });

  it('falls back to rule id when description missing', () => {
    const result = renderExceptionCreated({ wazuh_rule_id: 200001 });
    expect(result).toContain('200001');
  });

  it('renderEvent dispatches exception_created', () => {
    const result = renderEvent('exception_created', { description: 'Block SSH' });
    expect(result).toContain('Block SSH');
  });
});

describe('renderEvent', () => {
  it('renders incident_created', () => {
    expect(renderEvent('incident_created', {})).toBe('Incident created.');
  });

  it('falls back for unknown kinds', () => {
    const result = renderEvent('some_future_event', { foo: 'bar' });
    expect(result).toContain('some_future_event');
  });
});

// ── component tests ───────────────────────────────────────────────────────────

const TIMELINE_PAGE = {
  count: 2,
  page: 1,
  page_size: 50,
  results: [
    { id: 1, kind: 'incident_created', actor_username: 'alice', payload: {}, created_at: new Date().toISOString() },
    { id: 2, kind: 'comment_added', actor_username: 'bob', payload: { target_id: 5, is_internal: false }, created_at: new Date().toISOString() },
  ],
};

describe('IncidentTimeline component', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows loading state', () => {
    api.get.mockReturnValue(new Promise(() => {}));
    render(<IncidentTimeline incidentId="1" />);
    expect(screen.getByText('Loading timeline…')).toBeInTheDocument();
  });

  it('renders events after load', async () => {
    api.get.mockResolvedValue({ data: TIMELINE_PAGE });
    render(<IncidentTimeline incidentId="1" />);
    await waitFor(() => screen.getByText('Incident created.'));
    expect(screen.getByText(/Comment added/)).toBeInTheDocument();
  });

  it('shows actor usernames', async () => {
    api.get.mockResolvedValue({ data: TIMELINE_PAGE });
    render(<IncidentTimeline incidentId="1" />);
    await waitFor(() => screen.getByText('alice'));
    expect(screen.getByText('bob')).toBeInTheDocument();
  });

  it('shows empty state when no events', async () => {
    api.get.mockResolvedValue({ data: { count: 0, page: 1, page_size: 50, results: [] } });
    render(<IncidentTimeline incidentId="1" />);
    await waitFor(() => screen.getByText('No events yet.'));
  });

  it('shows TLP restriction message on 403', async () => {
    api.get.mockRejectedValue({ response: { status: 403 } });
    render(<IncidentTimeline incidentId="1" />);
    await waitFor(() => screen.getByText(/not available at this classification/));
  });

  it('shows pagination controls when multiple pages', async () => {
    api.get.mockResolvedValue({
      data: { count: 55, page: 1, page_size: 50, results: TIMELINE_PAGE.results },
    });
    render(<IncidentTimeline incidentId="1" />);
    await waitFor(() => screen.getByText('Page 1 of 2'));
    expect(screen.getByRole('button', { name: /Older/ })).toBeInTheDocument();
  });

  it('loads next page when Older is clicked', async () => {
    const page1 = { count: 55, page: 1, page_size: 50, results: TIMELINE_PAGE.results };
    const page2 = { count: 55, page: 2, page_size: 50, results: [
      { id: 3, kind: 'task_created', actor_username: 'carol', payload: { title: 'Review', task_id: 3 }, created_at: new Date().toISOString() },
    ]};
    api.get.mockResolvedValueOnce({ data: page1 }).mockResolvedValueOnce({ data: page2 });
    const user = userEvent.setup();
    render(<IncidentTimeline incidentId="1" />);
    await waitFor(() => screen.getByRole('button', { name: /Older/ }));
    await user.click(screen.getByRole('button', { name: /Older/ }));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/api/incidents/1/timeline/?page=2'));
  });
});
