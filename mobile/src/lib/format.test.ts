import { humanize, timeAgo } from './format';

describe('timeAgo', () => {
  const now = new Date('2026-07-07T12:00:00Z');

  it('renders recent timestamps as "just now"', () => {
    expect(timeAgo('2026-07-07T11:59:40Z', now)).toBe('just now');
  });

  it('renders minutes, hours and days', () => {
    expect(timeAgo('2026-07-07T11:45:00Z', now)).toBe('15m ago');
    expect(timeAgo('2026-07-07T09:00:00Z', now)).toBe('3h ago');
    expect(timeAgo('2026-07-05T12:00:00Z', now)).toBe('2d ago');
  });

  it('handles null and garbage input', () => {
    expect(timeAgo(null, now)).toBe('—');
    expect(timeAgo('not-a-date', now)).toBe('—');
  });
});

describe('humanize', () => {
  it('turns snake_case states into readable labels', () => {
    expect(humanize('in_progress')).toBe('In progress');
    expect(humanize('pending_closure')).toBe('Pending closure');
  });

  it('handles empty values', () => {
    expect(humanize(null)).toBe('—');
    expect(humanize('')).toBe('—');
  });
});
