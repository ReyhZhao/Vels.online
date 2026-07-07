import type { InternalAxiosRequestConfig } from 'axios';
import { attachCsrfToken, captureCsrfFromHeaders, setCsrfToken, getCsrfToken } from './api';
import { setServerUrl } from './server';

function makeConfig(method: string): InternalAxiosRequestConfig {
  return { method, headers: {} } as unknown as InternalAxiosRequestConfig;
}

describe('captureCsrfFromHeaders', () => {
  afterEach(() => setCsrfToken(null));

  it('captures the token echoed by the backend', () => {
    captureCsrfFromHeaders({ 'x-csrftoken': 'tok-123' });
    expect(getCsrfToken()).toBe('tok-123');
  });

  it('keeps the existing token when the header is absent', () => {
    setCsrfToken('existing');
    captureCsrfFromHeaders({});
    captureCsrfFromHeaders(undefined);
    expect(getCsrfToken()).toBe('existing');
  });
});

describe('attachCsrfToken', () => {
  beforeEach(() => {
    setServerUrl('https://vels.online');
    setCsrfToken('tok-123');
  });
  afterEach(() => setCsrfToken(null));

  it.each(['post', 'put', 'patch', 'delete'])('attaches the token on %s', (method) => {
    const config = attachCsrfToken(makeConfig(method));
    expect(config.headers['X-CSRFToken']).toBe('tok-123');
    expect(config.headers['Referer']).toBe('https://vels.online/');
  });

  it('does not attach the token on GET', () => {
    const config = attachCsrfToken(makeConfig('get'));
    expect(config.headers['X-CSRFToken']).toBeUndefined();
  });

  it('does nothing when no token has been captured yet', () => {
    setCsrfToken(null);
    const config = attachCsrfToken(makeConfig('post'));
    expect(config.headers['X-CSRFToken']).toBeUndefined();
  });
});
