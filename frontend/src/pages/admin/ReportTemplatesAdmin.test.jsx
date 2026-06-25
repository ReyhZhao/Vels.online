import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import ReportTemplatesAdmin from './ReportTemplatesAdmin';

const CATALOG = [
  { kind: 'executive_summary', title: 'Executive Summary' },
  { kind: 'incident_details', title: 'Incident Details' },
  { kind: 'timeline', title: 'Timeline' },
];

const TEMPLATES = [
  { id: 1, name: 'Customer Brief', audience: 'customer', sections: ['incident_details'], intro_text: '', outro_text: '', recommendations_text: '' },
  { id: 2, name: 'Internal Full', audience: 'internal', sections: ['incident_details', 'timeline'], intro_text: '', outro_text: '', recommendations_text: '' },
];

function mockLoad(templates = TEMPLATES) {
  api.get.mockImplementation((url) => {
    if (url.includes('report-sections')) return Promise.resolve({ data: CATALOG });
    return Promise.resolve({ data: templates });
  });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ReportTemplatesAdmin />
    </MemoryRouter>
  );
}

describe('ReportTemplatesAdmin', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists templates with audience badges', async () => {
    mockLoad();
    renderPage();
    await waitFor(() => screen.getByText('Customer Brief'));
    expect(screen.getByText('Internal Full')).toBeInTheDocument();
    expect(screen.getByText('customer')).toBeInTheDocument();
    expect(screen.getByText('internal')).toBeInTheDocument();
  });

  it('creates a template with selected ordered sections and audience', async () => {
    mockLoad([]);
    api.post.mockResolvedValue({
      data: { id: 3, name: 'New', audience: 'internal', sections: ['timeline', 'incident_details'] },
    });
    renderPage();
    await waitFor(() => screen.getByText('No report templates.'));

    await userEvent.click(screen.getByText('+ New template'));
    await userEvent.type(screen.getByLabelText('Name'), 'New');
    await userEvent.selectOptions(screen.getByLabelText('Audience'), 'internal');

    // add two sections in order: Timeline then Incident Details
    await userEvent.click(screen.getByText('+ Timeline'));
    await userEvent.click(screen.getByText('+ Incident Details'));

    await userEvent.click(screen.getByText('Save'));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const payload = api.post.mock.calls[0][1];
    expect(payload.audience).toBe('internal');
    expect(payload.sections).toEqual(['timeline', 'incident_details']);
  });

  it('filters by audience', async () => {
    mockLoad();
    renderPage();
    await waitFor(() => screen.getByText('Customer Brief'));
    await userEvent.selectOptions(screen.getByLabelText('Filter by audience'), 'internal');
    expect(screen.queryByText('Customer Brief')).not.toBeInTheDocument();
    expect(screen.getByText('Internal Full')).toBeInTheDocument();
  });
});
