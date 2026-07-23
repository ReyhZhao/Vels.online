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
    expect(screen.getByText(/ECS entities/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Assign to source.ip' })).toBeInTheDocument();
  });

  it('maps a field by clicking a leaf then Assign (Inspector)', async () => {
    api.get.mockImplementation(url => {
      if (url === '/api/security/organizations/') return Promise.resolve({ data: ORGS });
      if (url === '/api/ingest-endpoints/endpoints/') return Promise.resolve({ data: [mkEndpoint()] });
      if (url.includes('/captured/')) return Promise.resolve({ data: [
        { id: 7, status: 'pending', received_at: '2026-07-23T09:00:00Z', body: { search_name: 'Brute force' }, outcomes: [] },
      ] });
      return Promise.resolve({ data: [] });
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => within(table()).getByText('Splunk incidents'));
    await user.click(screen.getByRole('button', { name: 'Configure' }));
    await screen.findByLabelText('Mapping builder');
    // Click the leaf in the JSON tree, then Assign it to the Title field.
    await user.click(await screen.findByRole('button', { name: 'Pick search_name' }));
    await user.click(screen.getByRole('button', { name: 'Assign to title' }));
    // The field now resolves to the clicked value (shown in the per-field chip + dry-run).
    await waitFor(() => expect(screen.getAllByText('Brute force').length).toBeGreaterThan(0));
  });
});
