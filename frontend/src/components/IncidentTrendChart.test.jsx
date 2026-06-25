import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn() },
}));

// recharts needs layout; stub it so we can assert which series/bars render.
vi.mock('recharts', () => {
  const Stub = ({ children }) => <div>{children}</div>;
  const Bar = ({ name }) => <div data-testid="bar">{name}</div>;
  return {
    BarChart: Stub, Bar, XAxis: Stub, YAxis: Stub, CartesianGrid: Stub,
    Tooltip: Stub, Legend: Stub, ResponsiveContainer: Stub,
  };
});

import api from '../lib/axios';
import IncidentTrendChart from './IncidentTrendChart';

const TREND = {
  days: 30,
  start: '2026-05-27',
  end: '2026-06-25',
  buckets: [
    { date: '2026-06-24', counts: { '3': 2, other: 1, unclassified: 4 } },
    { date: '2026-06-25', counts: { '3': 1 } },
  ],
  subjects: [
    { key: '3', subject_id: 3, name: 'Brute Force', kind: 'real' },
    { key: 'other', subject_id: null, name: 'Other', kind: 'other' },
    { key: 'unclassified', subject_id: null, name: 'Unclassified', kind: 'unclassified' },
  ],
};

function renderChart(params = '') {
  return render(<IncidentTrendChart searchParams={new URLSearchParams(params)} />);
}

describe('IncidentTrendChart — read-only chart', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('fetches the 30-day trend and renders a bar per Subject series', async () => {
    api.get.mockResolvedValue({ data: TREND });
    renderChart('severity=high');

    await waitFor(() => expect(screen.getAllByTestId('bar')).toHaveLength(3));
    expect(screen.getByText('Brute Force')).toBeInTheDocument();
    expect(screen.getByText('Other')).toBeInTheDocument();
    expect(screen.getByText('Unclassified')).toBeInTheDocument();

    // Forwards the list filter and a fixed 30-day window; never its own subject.
    const url = api.get.mock.calls[0][0];
    expect(url).toContain('days=30');
    expect(url).toContain('severity=high');
    expect(url).not.toContain('subject=');
  });

  it('shows an empty state when no incidents fall in the window', async () => {
    api.get.mockResolvedValue({ data: { ...TREND, buckets: [], subjects: [] } });
    renderChart();
    await waitFor(() =>
      expect(screen.getByText('No incidents in this window.')).toBeInTheDocument());
  });

  it('shows a loading indicator while fetching', async () => {
    let resolve;
    api.get.mockReturnValue(new Promise(r => { resolve = r; }));
    renderChart();
    expect(screen.getByRole('status')).toHaveTextContent('Loading trend…');
    resolve({ data: TREND });
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument());
  });
});
