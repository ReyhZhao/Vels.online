import {
  DEFAULT_SERVER_URL,
  getServerUrl,
  normalizeServerUrl,
  saveServerUrl,
} from './server';

describe('normalizeServerUrl', () => {
  it('defaults to https:// when no scheme is given', () => {
    expect(normalizeServerUrl('vels.online')).toBe('https://vels.online');
  });

  it('keeps an explicit http scheme (local dev)', () => {
    expect(normalizeServerUrl('http://localhost:8000')).toBe('http://localhost:8000');
  });

  it('defaults local addresses to http:// — the dev backend has no TLS', () => {
    expect(normalizeServerUrl('localhost:8000')).toBe('http://localhost:8000');
    expect(normalizeServerUrl('127.0.0.1:8000')).toBe('http://127.0.0.1:8000');
    expect(normalizeServerUrl('eddies-mac.local:8000')).toBe('http://eddies-mac.local:8000');
  });

  it('strips trailing slashes', () => {
    expect(normalizeServerUrl('https://vels.online///')).toBe('https://vels.online');
  });

  it('trims whitespace', () => {
    expect(normalizeServerUrl('  vels.online  ')).toBe('https://vels.online');
  });

  it('falls back to the default for empty input', () => {
    expect(normalizeServerUrl('')).toBe(DEFAULT_SERVER_URL);
  });
});

describe('saveServerUrl', () => {
  it('persists the normalized URL and updates the in-memory value', async () => {
    const saved = await saveServerUrl('my-soc.example.com/');
    expect(saved).toBe('https://my-soc.example.com');
    expect(getServerUrl()).toBe('https://my-soc.example.com');
  });
});
