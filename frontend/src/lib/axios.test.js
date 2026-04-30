import { describe, it, expect, beforeEach } from 'vitest';
import api, { attachCsrfToken } from './axios';

const CSRF_TOKEN = 'test-csrf-token';

beforeEach(() => {
  Object.defineProperty(document, 'cookie', {
    writable: true,
    configurable: true,
    value: `csrftoken=${CSRF_TOKEN}`,
  });
});

describe('attachCsrfToken', () => {
  it.each(['post', 'put', 'patch', 'delete'])('attaches X-CSRFToken on %s', (method) => {
    const config = { method, headers: {} };
    const result = attachCsrfToken(config);
    expect(result.headers['X-CSRFToken']).toBe(CSRF_TOKEN);
  });

  it('does not attach X-CSRFToken on get', () => {
    const config = { method: 'get', headers: {} };
    const result = attachCsrfToken(config);
    expect(result.headers['X-CSRFToken']).toBeUndefined();
  });
});

describe('api instance', () => {
  it('has withCredentials enabled', () => {
    expect(api.defaults.withCredentials).toBe(true);
  });
});
