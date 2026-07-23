import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@/lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '@/lib/axios';
import IngestEndpoints from './IngestEndpoints';

const ORGS = [{ id: 1, name: 'Acme', slug: 'acme' }];

function mkEndpoint(over = {}) {
  return {
    id: 1, name: 'Splunk incidents', target_type: 'incident', organization: 1,
    org_name: 'Acme', state: 'capturing', path_uuid: 'abc',
    ingest_path: '/ingest/abc/', field_mappings: {}, entity_mappings: {},
    collection_root_path: '', idempotency_key_path: '', captured_count: 3, ...over,
  };
}

function mockList(endpoints = [mkEndpoint()]) {
  api.get.mockImplementation(url => {
    if (url === '/api/security/organizations/') return Promise.resolve({ data: ORGS });
    if (url === '/api/ingest-endpoints/endpoints/') return Promise.resolve({ data: endpoints });
    return Promise.resolve({ data: [] });
  });
}

function renderPage() {
  return render(<MemoryRouter><IngestEndpoints /></MemoryRouter>);
}
const table = () => screen.getByRole('table');

describe('IngestEndpoints', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('lists endpoints and filters by search', async () => {
    mockList([mkEndpoint(), mkEndpoint({ id: 2, name: 'Nessus assets', target_type: 'asset' })]);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Splunk incidents'));
    await user.type(screen.getByLabelText('Search endpoints'), 'nessus');
    await waitFor(() => expect(within(table()).queryByText('Splunk incidents')).not.toBeInTheDocument());
    expect(within(table()).getByText('Nessus assets')).toBeInTheDocument();
  });

  it('filters by target type', async () => {
    mockList([mkEndpoint(), mkEndpoint({ id: 2, name: 'Nessus assets', target_type: 'asset' })]);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Splunk incidents'));
    await user.selectOptions(screen.getByLabelText('Target filter'), 'asset');
    await waitFor(() => expect(within(table()).queryByText('Splunk incidents')).not.toBeInTheDocument());
    expect(within(table()).getByText('Nessus assets')).toBeInTheDocument();
  });

  it('creates an endpoint and opens its detail', async () => {
    mockList([]);
    api.post.mockResolvedValue({ data: mkEndpoint({ id: 9, name: 'New feed' }) });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: 'New Endpoint' }));
    await user.type(screen.getByLabelText('Endpoint name'), 'New feed');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/ingest-endpoints/endpoints/',
      expect.objectContaining({ name: 'New feed', target_type: 'incident', organization: 1 })));
    // Lands on the detail view showing the generated URL.
    await screen.findByText('/ingest/abc/', { exact: false });
  });

  it('shows the ECS entity section only for alert endpoints', async () => {
    mockList([mkEndpoint({ target_type: 'alert' })]);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Splunk incidents'));
    await user.click(screen.getByRole('button', { name: 'Configure' }));
    await screen.findByLabelText('Mapping builder');
    expect(screen.getByText(/ECS entity mapping/i)).toBeInTheDocument();
    expect(screen.getByLabelText('source.ip path')).toBeInTheDocument();
  });
});
