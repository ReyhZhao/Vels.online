import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// The canvas map is opaque to jsdom (world-atlas + <canvas>), so stub it and assert
// the surrounding stat strip / panels / feed instead (per the prototype NOTES.md).
vi.mock('../components/attackmap/CanvasMap', () => ({
  default: ({ events }) => <div data-testid="canvas-stub">{events.length} arcs</div>,
}));

vi.mock('../hooks/useAttackStream', () => ({ default: vi.fn() }));
import useAttackStream from '../hooks/useAttackStream';
import LiveAttackMap from './LiveAttackMap';

function arc(seq, level, srcCountry, dstOrg, attackType, color = '#f00') {
  return { seq, level, color, srcCountry, dstOrg, attackType, ts: '2026-06-22T10:00:00Z',
           srcLat: 1, srcLng: 2, dstLat: 3, dstLng: 4 };
}

const STREAM = {
  events: [
    arc(0, 7, 'China', 'Acme', 'web'),
    arc(1, 12, 'Russia', 'Globex', 'sshd'),
    arc(2, 14, 'Brazil', 'Acme', 'sql'),
  ],
  stats: {
    top_countries: [['China', 20], ['Russia', 12]],
    top_attack_types: [['web', 30], ['sshd', 18]],
    per_minute: 9,
    total: 135,
  },
  connected: true,
};

describe('LiveAttackMap', () => {
  beforeEach(() => {
    useAttackStream.mockReturnValue(STREAM);
  });

  it('renders the stat strip from stream stats', () => {
    render(<LiveAttackMap />);
    expect(screen.getByText('Attacks / min')).toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();      // per_minute
    expect(screen.getByText('135')).toBeInTheDocument();    // window total
  });

  it('renders top-source-countries and top-attack-types panels', () => {
    render(<LiveAttackMap />);
    const countriesPanel = screen.getByText('Top source countries').closest('div');
    expect(within(countriesPanel).getByText('China')).toBeInTheDocument();
    const typesPanel = screen.getByText('Top attack types').closest('div');
    expect(within(typesPanel).getByText('web')).toBeInTheDocument();
  });

  it('renders the recent-attack feed rows', () => {
    render(<LiveAttackMap />);
    expect(screen.getByText('→ Globex')).toBeInTheDocument();
    expect(screen.getByText('sql')).toBeInTheDocument();
  });

  it('applies the client-side severity up-filter to arcs and feed (#600)', () => {
    render(<LiveAttackMap />);
    // All three arcs visible initially.
    expect(screen.getByTestId('canvas-stub')).toHaveTextContent('3 arcs');

    // Raise the threshold to Critical ≥12 → only the level-12 and level-14 arcs remain.
    fireEvent.change(screen.getByLabelText('Minimum severity'), { target: { value: '12' } });
    expect(screen.getByTestId('canvas-stub')).toHaveTextContent('2 arcs');
    expect(screen.queryByText('China')).not.toBeNull(); // still in the (server) panel
    // The level-7 China arc is gone from the feed.
    const feedRegion = screen.getByText('Recent attacks').closest('div').parentElement;
    expect(within(feedRegion).queryByText('web')).toBeNull();
  });

  it('shows a live connection indicator', () => {
    render(<LiveAttackMap />);
    expect(screen.getByText('Live')).toBeInTheDocument();
  });
});
