import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

import api from '../lib/axios';
import LinkedIncidents from './LinkedIncidents';

function renderLinked(props) {
  return render(
    <MemoryRouter>
      <LinkedIncidents sourceKind="cve" sourceRef={{ cve_id: 'CVE-2024-1' }} {...props} />
    </MemoryRouter>
  );
}

describe('LinkedIncidents', () => {
  beforeEach(() => {
    api.get.mockReset();
  });

  it('renders incidents that share the source', async () => {
    api.get.mockResolvedValue({
      data: { results: [
        { id: 1, display_id: 'INC-001', title: 'First', severity: 'high', state: 'new' },
        { id: 2, display_id: 'INC-002', title: 'Second', severity: 'low', state: 'in_progress' },
      ] },
    });
    renderLinked();
    expect(await screen.findByText('Linked Incidents')).toBeInTheDocument();
    expect(screen.getByText('First')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });

  it('excludes the current incident when excludeId is given', async () => {
    api.get.mockResolvedValue({
      data: { results: [
        { id: 1, display_id: 'INC-001', title: 'Self', severity: 'high', state: 'new' },
        { id: 2, display_id: 'INC-002', title: 'Sibling', severity: 'low', state: 'new' },
      ] },
    });
    renderLinked({ excludeId: 1 });
    expect(await screen.findByText('Sibling')).toBeInTheDocument();
    expect(screen.queryByText('Self')).not.toBeInTheDocument();
  });

  it('renders nothing when the only match is the current incident', async () => {
    api.get.mockResolvedValue({
      data: { results: [
        { id: 1, display_id: 'INC-001', title: 'Self', severity: 'high', state: 'new' },
      ] },
    });
    const { container } = renderLinked({ excludeId: 1 });
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(screen.queryByText('Linked Incidents')).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing without a sourceRef', async () => {
    const { container } = render(
      <MemoryRouter>
        <LinkedIncidents sourceKind="manual" sourceRef={{}} />
      </MemoryRouter>
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(api.get).not.toHaveBeenCalled();
  });
});
