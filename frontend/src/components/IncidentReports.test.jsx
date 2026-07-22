import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

const mockUseAuth = vi.fn(() => ({ user: { id: 1, username: 'mo', is_staff: false } }));
vi.mock('../context/AuthContext', () => ({ useAuth: () => mockUseAuth() }));

// Mock the TipTap editor so ProseMirror never mounts in jsdom; expose a plain textarea
// plus the real-ish isBlankRichText so container logic (payload, revert) is exercised.
vi.mock('./RichTextEditor', () => ({
  default: ({ value, onChange, placeholder }) => (
    <textarea
      aria-label={placeholder}
      value={value || ''}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
  isBlankRichText: (html) => {
    if (!html) return true;
    let text = html;
    let prev;
    do {
      prev = text;
      text = text.replace(/<[^>]*>/g, '');
    } while (text !== prev);
    return text.trim() === '';
  },
}));

import api from '../lib/axios';
import IncidentReports from './IncidentReports';

const REPORT = {
  id: 10, reference_id: 'REP-2026-0001', template: 1, template_name: 'Customer Brief',
  audience: 'customer', tlp: 'green', incident_state: 'resolved',
  incident_display_id: 'INC-2026-0001', generated_by: 2, generated_by_username: 'sam',
  generated_at: new Date().toISOString(), size_bytes: 1234,
};

function staffUser() {
  mockUseAuth.mockReturnValue({ user: { id: 2, username: 'sam', is_staff: true } });
}

function routeStaffGets({ templates, reports = [], preview }) {
  api.get.mockImplementation((url) => {
    if (url.includes('report-templates')) return Promise.resolve({ data: templates });
    if (url.includes('/preview/')) return Promise.resolve({ data: preview });
    return Promise.resolve({ data: reports }); // .../reports/
  });
}

const SCAFFOLD_INTERNAL = {
  refused: false,
  audience: 'internal',
  sections: [{ kind: 'incident_details', editable: false, html: '<section><h2>Incident Details</h2></section>' }],
  editable: { intro_text: '<p>intro default</p>', outro_text: '', recommendations_text: '', executive_summary: '' },
};

describe('IncidentReports (org member)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ user: { id: 1, username: 'mo', is_staff: false } });
  });

  it('shows empty state when no reports', async () => {
    api.get.mockResolvedValue({ data: [] });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('No reports generated yet.'));
  });

  it('lists reports with reference id and audience', async () => {
    api.get.mockResolvedValue({ data: [REPORT] });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('REP-2026-0001'));
    expect(screen.getByText('Customer Brief')).toBeInTheDocument();
  });

  it('never shows the preview/generate surface', async () => {
    api.get.mockResolvedValue({ data: [REPORT] });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('REP-2026-0001'));
    expect(screen.queryByText('Generate report')).not.toBeInTheDocument();
    expect(screen.queryByText('Template')).not.toBeInTheDocument();
  });
});

describe('IncidentReports (staff Editor + Preview)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    staffUser();
  });

  it('loads a preview for the default template and renders read-only section html', async () => {
    routeStaffGets({ templates: [{ id: 1, name: 'Internal', audience: 'internal' }], preview: SCAFFOLD_INTERNAL });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('Generate report'));
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining('/reports/preview/?template_id=1')
    ));
    // The badge renders from the preview *response*, which lands a tick after the
    // request goes out — assert on it asynchronously or this races under CI load.
    expect(await screen.findByText('Internal audience')).toBeInTheDocument();
  });

  it('generates a report with per-Report free-text overrides', async () => {
    routeStaffGets({ templates: [{ id: 1, name: 'Internal', audience: 'internal' }], preview: SCAFFOLD_INTERNAL });
    api.post.mockResolvedValue({ data: REPORT });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('Generate report'));
    await userEvent.click(screen.getByText('Generate report'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/INC-2026-0001/reports/',
      expect.objectContaining({ template_id: 1, intro_text: '<p>intro default</p>', outro_text: '', recommendations_text: '' }),
    ));
    // never generated a summary → must NOT send executive_summary (server writes it)
    expect(api.post.mock.calls[0][1]).not.toHaveProperty('executive_summary');
  });

  it('refuses preview + disables generate for a customer template on TLP:RED', async () => {
    routeStaffGets({
      templates: [{ id: 9, name: 'Customer', audience: 'customer' }],
      preview: { refused: true, audience: 'customer', reason: 'A customer report cannot be generated for a TLP:RED incident.' },
    });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText(/Customer report unavailable at TLP:RED/));
    expect(screen.getByText('Generate report')).toBeDisabled();
  });

  it('generates the executive summary on demand and freezes it verbatim', async () => {
    const scaffold = {
      ...SCAFFOLD_INTERNAL,
      sections: [{ kind: 'executive_summary', editable: true }],
    };
    routeStaffGets({ templates: [{ id: 1, name: 'Internal', audience: 'internal' }], preview: scaffold });
    api.post.mockImplementation((url) => {
      if (url.includes('/preview/summary/')) return Promise.resolve({ data: { executive_summary: '<p>AI summary</p>' } });
      return Promise.resolve({ data: REPORT });
    });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('Generate summary'));
    await userEvent.click(screen.getByText('Generate summary'));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/incidents/INC-2026-0001/reports/preview/summary/', { template_id: 1 },
    ));
    await userEvent.click(screen.getByText('Generate report'));
    await waitFor(() => {
      const genCall = api.post.mock.calls.find((c) => c[0] === '/api/incidents/INC-2026-0001/reports/');
      expect(genCall[1]).toMatchObject({ executive_summary: '<p>AI summary</p>' });
    });
  });

  it('surfaces a generation error', async () => {
    routeStaffGets({ templates: [{ id: 1, name: 'Internal', audience: 'internal' }], preview: SCAFFOLD_INTERNAL });
    api.post.mockRejectedValue({ response: { data: { detail: 'Boom' } } });
    render(<IncidentReports incidentId="INC-2026-0001" />);
    await waitFor(() => screen.getByText('Generate report'));
    await userEvent.click(screen.getByText('Generate report'));
    await waitFor(() => screen.getByText('Boom'));
  });
});
