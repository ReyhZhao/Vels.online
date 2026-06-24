import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import PresenceRoster from './PresenceRoster';
import { PresenceContext } from '../context/PresenceContext';

function renderWith(roster) {
  return render(
    <PresenceContext.Provider value={{ roster }}>
      <PresenceRoster />
    </PresenceContext.Provider>,
  );
}

describe('PresenceRoster', () => {
  it('renders nothing for an empty roster', () => {
    const { container } = renderWith([]);
    expect(container.firstChild).toBeNull();
  });

  it('shows a human viewer chip', () => {
    renderWith([{ actor_key: 'user:1', actor_kind: 'human', display_name: 'dana', activity: 'viewing', target: null }]);
    expect(screen.getByText('dana')).toBeInTheDocument();
    expect(screen.getByText('viewing')).toBeInTheDocument();
  });

  it('labels working a task', () => {
    renderWith([{ actor_key: 'user:1', actor_kind: 'human', display_name: 'dana', activity: 'working', target: 7 }]);
    expect(screen.getByText('working task 7')).toBeInTheDocument();
  });

  it('labels editing vs writing a comment', () => {
    renderWith([
      { actor_key: 'user:1', actor_kind: 'human', display_name: 'dana', activity: 'editing', target: 9 },
      { actor_key: 'user:2', actor_kind: 'human', display_name: 'eve', activity: 'editing', target: null },
    ]);
    expect(screen.getByText('editing a comment')).toBeInTheDocument();
    expect(screen.getByText('writing a comment')).toBeInTheDocument();
  });

  it('renders an AI actor distinctly and attributes the Assistant to its invoker', () => {
    renderWith([{ actor_key: 'ai:abc', actor_kind: 'ai', display_name: 'Incident Assistant', run_by: 'dana', activity: 'working', target: null }]);
    const chip = screen.getByText('Incident Assistant').closest('[data-testid="presence-chip"]');
    expect(chip).toHaveTextContent('🤖');
    expect(chip.getAttribute('title')).toContain('run by dana');
  });
});
