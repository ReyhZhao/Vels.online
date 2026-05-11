import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import SLAPill from './SLAPill';

function sla(overrides = {}) {
  return {
    target_seconds: 3600,
    elapsed_seconds: 100,
    remaining_seconds: 3500,
    breached: false,
    applies: true,
    ...overrides,
  };
}

describe('SLAPill', () => {
  it('renders nothing when sla is null', () => {
    const { container } = render(<SLAPill sla={null} label="Response SLA" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when applies is false', () => {
    const { container } = render(<SLAPill sla={sla({ applies: false })} label="Response SLA" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows green when ample time remains (>25%)', () => {
    render(<SLAPill sla={sla({ remaining_seconds: 3000, target_seconds: 3600 })} label="Resolve SLA" />);
    const el = screen.getByText(/Resolve SLA/);
    expect(el.className).toMatch(/green/);
  });

  it('shows amber when less than 25% of time remains', () => {
    render(<SLAPill sla={sla({ remaining_seconds: 100, target_seconds: 3600 })} label="Response SLA" />);
    const el = screen.getByText(/Response SLA/);
    expect(el.className).toMatch(/amber/);
  });

  it('shows red and BREACHED text when breached', () => {
    render(<SLAPill sla={sla({ remaining_seconds: -300, target_seconds: 3600, breached: true })} label="Response SLA" />);
    const el = screen.getByText(/BREACHED/);
    expect(el.className).toMatch(/red/);
    expect(el).toHaveTextContent('BREACHED 5m ago');
  });

  it('formats remaining time in minutes', () => {
    render(<SLAPill sla={sla({ remaining_seconds: 720 })} label="Resolve SLA" />);
    expect(screen.getByText(/12m left/)).toBeInTheDocument();
  });

  it('formats remaining time in hours', () => {
    render(<SLAPill sla={sla({ remaining_seconds: 7200 })} label="Resolve SLA" />);
    expect(screen.getByText(/2h left/)).toBeInTheDocument();
  });

  it('formats remaining time in days', () => {
    render(<SLAPill sla={sla({ remaining_seconds: 2 * 86400 })} label="Resolve SLA" />);
    expect(screen.getByText(/2d left/)).toBeInTheDocument();
  });

  it('includes the label in the pill text', () => {
    render(<SLAPill sla={sla()} label="Response SLA" />);
    expect(screen.getByText(/Response SLA/)).toBeInTheDocument();
  });
});
