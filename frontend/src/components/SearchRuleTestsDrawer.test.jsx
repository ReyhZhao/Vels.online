import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/axios', () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

import api from '../lib/axios';
import SearchRuleTestsDrawer from './SearchRuleTestsDrawer';

const RULE = { id: 7, name: 'Brute Force' };

function renderDrawer() {
  return render(<SearchRuleTestsDrawer rule={RULE} onClose={() => {}} />);
}

describe('SearchRuleTestsDrawer', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('lists existing tests with expectation and status badges', async () => {
    api.get.mockResolvedValue({ data: [
      { id: 1, name: 'fires on burst', description: '', expect_fire: true, samples: [], last_status: 'pass' },
      { id: 2, name: 'ignores benign', description: '', expect_fire: false, samples: [], last_status: 'never' },
    ] });
    renderDrawer();

    await waitFor(() => screen.getByText('fires on burst'));
    expect(screen.getByText('should fire')).toBeInTheDocument();
    expect(screen.getByText('should not fire')).toBeInTheDocument();
    expect(screen.getByText('Pass')).toBeInTheDocument();
    expect(screen.getByText('Never run')).toBeInTheDocument();
  });

  it('creates a test with parsed JSON samples', async () => {
    api.get.mockResolvedValue({ data: [] });
    api.post.mockResolvedValue({ data: {} });
    const user = userEvent.setup();
    renderDrawer();

    await waitFor(() => screen.getByText('No tests yet.'));
    await user.click(screen.getByText('+ Add test'));
    await user.type(screen.getByLabelText('Test name'), 'TP test');
    const textarea = screen.getByLabelText('Sample documents JSON');
    fireEvent.change(textarea, { target: { value: '[{"a":1}]' } });
    await user.click(screen.getByText('Save test'));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [, payload] = api.post.mock.calls[0];
    expect(payload.name).toBe('TP test');
    expect(payload.samples).toEqual([{ a: 1 }]);
    expect(payload.expect_fire).toBe(true);
  });

  it('rejects invalid JSON without calling the API', async () => {
    api.get.mockResolvedValue({ data: [] });
    const user = userEvent.setup();
    renderDrawer();

    await waitFor(() => screen.getByText('No tests yet.'));
    await user.click(screen.getByText('+ Add test'));
    await user.type(screen.getByLabelText('Test name'), 'bad');
    const textarea = screen.getByLabelText('Sample documents JSON');
    fireEvent.change(textarea, { target: { value: 'not json' } });
    await user.click(screen.getByText('Save test'));

    expect(await screen.findByText(/must be valid JSON/i)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('generates samples with AI and fills the editor', async () => {
    api.get.mockResolvedValue({ data: [] });
    api.post.mockResolvedValue({ data: { samples: [{ '@timestamp': '2026-06-06T10:00:00Z', rule: { id: '5710' } }], warnings: ['dropped foo'] } });
    const user = userEvent.setup();
    renderDrawer();

    await waitFor(() => screen.getByText('No tests yet.'));
    await user.click(screen.getByText('+ Add test'));
    await user.click(screen.getByText('Generate with AI'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/correlations/search-rules/7/tests/generate/', { expect_fire: true }));
    const textarea = await screen.findByLabelText('Sample documents JSON');
    expect(textarea.value).toContain('5710');
    expect(screen.getByText('dropped foo')).toBeInTheDocument();
  });

  it('runs a test and shows the pass result', async () => {
    api.get.mockResolvedValue({ data: [
      { id: 1, name: 'fires on burst', description: '', expect_fire: true, samples: [], last_status: 'never' },
    ] });
    api.post.mockResolvedValue({ data: { status: 'pass', passed: true, fired: true, expect_fire: true, diagnostics: { mode: 'single' } } });
    const user = userEvent.setup();
    renderDrawer();

    await waitFor(() => screen.getByText('fires on burst'));
    await user.click(screen.getByText('Run'));

    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/correlations/search-rules/7/tests/1/run/'));
    expect(await screen.findByText(/Passed — rule behaved as expected/i)).toBeInTheDocument();
  });
});
