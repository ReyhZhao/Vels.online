import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../hooks/useStatus');
import { useStatus } from '../../hooks/useStatus';
import StatusIndicator from './StatusIndicator';

function renderIndicator() {
  return render(
    <MemoryRouter>
      <StatusIndicator />
    </MemoryRouter>
  );
}

describe('StatusIndicator', () => {
  it('shows "Checking status…" while loading', () => {
    useStatus.mockReturnValue({ overallStatus: 'unknown', isLoading: true });
    renderIndicator();
    expect(screen.getByText('Checking status…')).toBeInTheDocument();
  });

  it('shows green label when operational', () => {
    useStatus.mockReturnValue({ overallStatus: 'operational', isLoading: false });
    renderIndicator();
    expect(screen.getByText('All systems operational')).toBeInTheDocument();
  });

  it('shows yellow label when degraded', () => {
    useStatus.mockReturnValue({ overallStatus: 'degraded', isLoading: false });
    renderIndicator();
    expect(screen.getByText('Degraded performance')).toBeInTheDocument();
  });

  it('shows red label when outage', () => {
    useStatus.mockReturnValue({ overallStatus: 'outage', isLoading: false });
    renderIndicator();
    expect(screen.getByText('Service disruption')).toBeInTheDocument();
  });

  it('shows grey label when unknown', () => {
    useStatus.mockReturnValue({ overallStatus: 'unknown', isLoading: false });
    renderIndicator();
    expect(screen.getByText('Status unknown')).toBeInTheDocument();
  });

  it('links to /status', () => {
    useStatus.mockReturnValue({ overallStatus: 'operational', isLoading: false });
    renderIndicator();
    expect(screen.getByRole('link', { name: /site status/i })).toHaveAttribute('href', '/status');
  });
});
