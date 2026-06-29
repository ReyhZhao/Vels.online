import { render, screen } from '@testing-library/react';
import { describe, it, expect, afterEach, vi } from 'vitest';

import PresenceBanner, { TaskPresenceStrip } from './PresenceBanner';
import { PresenceContext } from '../context/PresenceContext';
import { AuthContext } from '../context/AuthContext';

function renderWith(ui, roster, user = { id: 1 }) {
  return render(
    <AuthContext.Provider value={{ user }}>
      <PresenceContext.Provider value={{ roster }}>
        {ui}
      </PresenceContext.Provider>
    </AuthContext.Provider>,
  );
}

const me = { actor_key: 'user:1', actor_kind: 'human', actor_id: 1, display_name: 'me', activity: 'viewing', target: null };
const dana = { actor_key: 'user:2', actor_kind: 'human', actor_id: 2, display_name: 'dana', activity: 'viewing', target: null };
const eve = { actor_key: 'user:3', actor_kind: 'human', actor_id: 3, display_name: 'eve', activity: 'working', target: 7 };

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('PresenceBanner', () => {
  it('renders nothing for an empty roster', () => {
    const { container } = renderWith(<PresenceBanner />, []);
    expect(container.firstChild).toBeNull();
  });

  it('by default includes the current user (self-exclusion off)', () => {
    renderWith(<PresenceBanner />, [me, dana, eve]);
    expect(screen.getByText('3 people are on this incident')).toBeInTheDocument();
  });

  it('renders even when the current user is the only one present (self-exclusion off)', () => {
    renderWith(<PresenceBanner />, [me]);
    expect(screen.getByText('1 person is on this incident')).toBeInTheDocument();
  });

  it('renders an AI actor distinctly and attributes it to its invoker', () => {
    const ai = { actor_key: 'ai:abc', actor_kind: 'ai', display_name: 'Incident Assistant', run_by: 'dana', activity: 'working', target: null };
    renderWith(<PresenceBanner />, [ai]);
    const avatar = screen.getByTestId('presence-avatar');
    expect(avatar).toHaveTextContent('🤖');
    expect(avatar.getAttribute('title')).toContain('run by dana');
  });

  describe('with VITE_PRESENCE_SELF_EXCLUSION=1', () => {
    it('renders nothing when only the current user is present', () => {
      vi.stubEnv('VITE_PRESENCE_SELF_EXCLUSION', '1');
      const { container } = renderWith(<PresenceBanner />, [me]);
      expect(container.firstChild).toBeNull();
    });

    it('summarises other people and excludes the current user from the count', () => {
      vi.stubEnv('VITE_PRESENCE_SELF_EXCLUSION', '1');
      renderWith(<PresenceBanner />, [me, dana, eve]);
      expect(screen.getByText('2 people are on this incident')).toBeInTheDocument();
      expect(screen.getByText(/dana \(viewing\)/)).toBeInTheDocument();
      expect(screen.getByText(/eve \(working\)/)).toBeInTheDocument();
    });

    it('uses singular copy for a single other person', () => {
      vi.stubEnv('VITE_PRESENCE_SELF_EXCLUSION', '1');
      renderWith(<PresenceBanner />, [me, dana]);
      expect(screen.getByText('1 person is on this incident')).toBeInTheDocument();
    });
  });
});

describe('TaskPresenceStrip', () => {
  it('shows people working this specific task', () => {
    renderWith(<TaskPresenceStrip taskId={7} />, [eve]);
    expect(screen.getByText(/eve is also in this task right now/)).toBeInTheDocument();
  });

  it('ignores people working a different task or doing something else', () => {
    const otherTask = { ...eve, actor_key: 'user:4', actor_id: 4, display_name: 'otto', target: 99 };
    const { container } = renderWith(<TaskPresenceStrip taskId={7} />, [dana, otherTask]);
    expect(container.firstChild).toBeNull();
  });

  it('excludes the current user when VITE_PRESENCE_SELF_EXCLUSION=1', () => {
    vi.stubEnv('VITE_PRESENCE_SELF_EXCLUSION', '1');
    const meWorking = { ...me, activity: 'working', target: 7 };
    const { container } = renderWith(<TaskPresenceStrip taskId={7} />, [meWorking]);
    expect(container.firstChild).toBeNull();
  });
});
