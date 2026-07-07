import { allowedTransitions } from './transitions';

describe('allowedTransitions', () => {
  it('mirrors the backend state machine for the common states', () => {
    expect(allowedTransitions('new')).toEqual(['triaged', 'in_progress', 'closed']);
    expect(allowedTransitions('pending_closure')).toEqual(['in_progress', 'closed']);
    expect(allowedTransitions('closed')).toEqual(['in_progress']);
  });

  it('returns nothing for unknown states', () => {
    expect(allowedTransitions('bogus')).toEqual([]);
  });
});
